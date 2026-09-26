#!/usr/bin/env bash
set -Eeuo pipefail
set -x

readonly DEFAULT_FEDORA_IMAGE_URL=https://dl.fedoraproject.org/pub/alt/risc-v/release/44/Cloud/riscv64/images/Fedora-Cloud-Base-Generic-44-20260604.0.riscv64.qcow2
readonly DEFAULT_FEDORA_IMAGE_SHA256=06852158be651467e3a696ce37cbade2dddb067d425689f4b5d6433b9589c27a
readonly DEFAULT_FEDORA_IMAGE_CHECKSUM_URL=https://dl.fedoraproject.org/pub/alt/risc-v/release/44/Cloud/riscv64/images/Fedora-Cloud-Base-Generic-44-20260604.0.riscv64.qcow2.sha256

usage()
{
	cat <<EOF
Usage: prepare-riscv-fedora-guest.sh OUTPUT_DIR SSH_PUBLIC_KEY_FILE

Prepare a persistent RISC-V Fedora cloud guest without booting it.
OUTPUT_DIR must not already exist. SSH_PUBLIC_KEY_FILE must contain exactly
one OpenSSH public key and must not be a symlink or private-key file.

Default pinned source:
  URL:        $DEFAULT_FEDORA_IMAGE_URL
  SHA-256:    $DEFAULT_FEDORA_IMAGE_SHA256
  Checksums:  $DEFAULT_FEDORA_IMAGE_CHECKSUM_URL
  Compression: none
  Format:      qcow2

This is a Fedora-hosted community RISC-V image. Direct-kernel suitability is
not inferred from its name; the selected BLS entry and referenced boot files
must pass this script's validation.

Source overrides:
  FEDORA_IMAGE_URL      HTTPS image URL without credentials, query, or fragment
  FEDORA_IMAGE_PATH     Existing local regular image file
                        Set at most one. If neither is set, the pinned URL above
                        is used.
  FEDORA_IMAGE_SHA256   SHA-256 of the source bytes, exactly 64 lowercase hex.
                        Required for a custom URL or path; otherwise defaults
                        to the pinned checksum above. An explicit hash for the
                        pinned URL must match that checksum.

Optional:
  FEDORA_IMAGE_COMPRESSION
                        auto, none, or xz (pinned default: none;
                        custom-source default: auto)
  FEDORA_IMAGE_FORMAT   auto, raw, or qcow2 (pinned default: qcow2;
                        custom-source default: auto)
  FEDORA_BLS_ENTRY      Exact loader/entries/*.conf basename to select
  FEDORA_GUEST_USER     Guest account name (default: fedora)
  FEDORA_GUEST_HOSTNAME Guest hostname (default: k3-fedora-guest)
  FEDORA_OVERLAY_SIZE   Enlarged qcow2 virtual size (default: 20G);
                        byte counts are rounded up to a 512-byte sector

Successful output:
  base.img
  base-format.txt
  overlay.qcow2
  seed.img
  user-data
  meta-data
  boot/vmlinuz      (canonical zero-padded raw RISC-V Linux Image)
  boot/initramfs.img
  boot/cmdline.txt
  source.txt
  SHA256SUMS

The source checksum is verified before transformation. The inner image format
is identified and checked with qemu-img, /boot is copied out read-only with
libguestfs, and the selected BLS kernel is snapshotted into the private work
tree. A valid raw RISC-V Image is copied into private staging and canonically
zero-padded to its header image_size. A strict gzip or zstd EFI zboot container
is boundedly decompressed, and the recovered raw Image must already have its
exact trailer and header length before atomic publication as boot/vmlinuz. BLS
readability alone does not establish direct-kernel suitability. Other kernel
formats are rejected. A zstd-compressed zboot input dynamically requires the
zstd command. The overlay records the relative backing file "base.img". The
mutable overlay is intentionally excluded from SHA256SUMS.

This script does not install packages, use sudo, access target hardware,
transfer files to another host, run a guest, alter networking, or reboot.
EOF
}

fail()
{
	printf 'error: %s\n' "$*" >&2
	exit 1
}

usage_error()
{
	printf 'error: %s\n\n' "$*" >&2
	usage >&2
	exit 2
}

require_command()
{
	command -v "$1" >/dev/null ||
		fail "required command not found: $1"
}

make_work_tree_owner_accessible()
{
	if [[ -n ${work_dir:-} && -d $work_dir && ! -L $work_dir ]]; then
		chmod -R u+rwX -- "$work_dir"
	fi
}

reject_control_characters()
{
	local value=$1
	local label=$2

	if [[ $value =~ [[:cntrl:]] ]]; then
		fail "$label contains control characters"
	fi
}

sha256_file()
{
	local output

	output=$(sha256sum -- "$1") ||
		return 1
	[[ $output =~ ^[0-9a-f]{64}[[:space:]] ]] ||
		return 1
	printf '%s\n' "${output%% *}"
}

write_kernel_image_tool()
{
	cat > "$1" <<'PY'
import hashlib
import os
import platform
import struct
import sys
import zlib


CHUNK_SIZE = 1024 * 1024
UINT32_MAX = (1 << 32) - 1
ZERO_CHUNK = b"\0" * CHUNK_SIZE


class KernelImageError(Exception):
    pass


def hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            data = stream.read(CHUNK_SIZE)
            if not data:
                break
            digest.update(data)
    return digest.hexdigest()


def hash_file_prefix(path, length):
    digest = hashlib.sha256()
    remaining = length
    with open(path, "rb") as stream:
        while remaining:
            data = stream.read(min(CHUNK_SIZE, remaining))
            if not data:
                raise KernelImageError(
                    "canonical raw RISC-V Image is shorter than the original input"
                )
            digest.update(data)
            remaining -= len(data)
    return digest.hexdigest()


def read_prefix(path, length):
    with open(path, "rb") as stream:
        return stream.read(length)


def validate_raw_image(path, allow_short=False):
    size = os.stat(path).st_size
    if size < 64:
        raise KernelImageError(
            f"raw RISC-V Image is shorter than 64 bytes: {size}"
        )

    header = read_prefix(path, 64)
    code0, code1 = struct.unpack_from("<II", header, 0)
    text_offset = struct.unpack_from("<Q", header, 0x08)[0]
    image_size = struct.unpack_from("<Q", header, 0x10)[0]
    flags = struct.unpack_from("<Q", header, 0x18)[0]
    version = struct.unpack_from("<I", header, 0x20)[0]
    reserved_24 = struct.unpack_from("<I", header, 0x24)[0]
    reserved_28 = struct.unpack_from("<Q", header, 0x28)[0]
    magic_30 = header[0x30:0x38]
    magic_38 = header[0x38:0x3c]
    field_3c = struct.unpack_from("<I", header, 0x3c)[0]

    if text_offset != 0x200000:
        raise KernelImageError(
            "raw RISC-V Image text_offset is "
            f"0x{text_offset:016x}, expected 0x0000000000200000"
        )
    if not 64 <= image_size <= UINT32_MAX:
        raise KernelImageError(
            f"raw RISC-V Image image_size is outside 64..0xffffffff: {image_size}"
        )
    if size > image_size:
        raise KernelImageError(
            f"raw RISC-V Image length {size} exceeds image_size {image_size}"
        )
    if not allow_short and size != image_size:
        raise KernelImageError(
            f"raw RISC-V Image length {size} does not equal image_size {image_size}"
        )
    if flags != 0:
        raise KernelImageError(
            f"raw RISC-V Image flags are 0x{flags:016x}, expected zero"
        )
    if version != 2:
        raise KernelImageError(
            f"raw RISC-V Image version is {version}, expected 2"
        )
    if reserved_24 != 0:
        raise KernelImageError(
            "raw RISC-V Image reserved field at 0x24 is "
            f"0x{reserved_24:08x}, expected zero"
        )
    if reserved_28 != 0:
        raise KernelImageError(
            "raw RISC-V Image reserved field at 0x28 is "
            f"0x{reserved_28:016x}, expected zero"
        )
    if magic_30 != b"RISCV\0\0\0":
        raise KernelImageError(
            "raw RISC-V Image magic at 0x30 is "
            f"{magic_30.hex()}, expected 5249534356000000"
        )
    if magic_38 != b"RSC\x05":
        raise KernelImageError(
            "raw RISC-V Image magic at 0x38 is "
            f"{magic_38.hex()}, expected 52534305"
        )

    return {
        "code0": code0,
        "code1": code1,
        "text_offset": text_offset,
        "image_size": image_size,
        "flags": flags,
        "version": version,
        "reserved_24": reserved_24,
        "reserved_28": reserved_28,
        "magic_30": magic_30,
        "magic_38": magic_38,
        "field_3c": field_3c,
    }


def parse_zboot(path):
    size = os.stat(path).st_size
    if size < 0x5A:
        raise KernelImageError(
            f"EFI zboot container is shorter than 0x5a bytes: {size}"
        )

    header = read_prefix(path, 0x5A)
    dos_magic = struct.unpack_from("<I", header, 0x00)[0]
    if dos_magic != 0x00005A4D:
        raise KernelImageError(
            "EFI zboot DOS signature is "
            f"0x{dos_magic:08x}, expected 0x00005a4d"
        )
    if header[0x04:0x08] != b"zimg":
        raise KernelImageError(
            "EFI zboot image type is "
            f"{header[0x04:0x08].hex()}, expected 7a696d67"
        )

    payload_offset, payload_size = struct.unpack_from("<II", header, 0x08)
    reserved_10, reserved_14 = struct.unpack_from("<II", header, 0x10)
    if reserved_10 != 0 or reserved_14 != 0:
        raise KernelImageError(
            "EFI zboot reserved fields at 0x10 and 0x14 must both be zero"
        )

    compression_slot = header[0x18:0x38]
    gzip_slot = b"gzip\0" + (b"\0" * 27)
    zstd_slot = b"zstd\0" + (b"\0" * 27)
    if compression_slot == gzip_slot:
        compression = "gzip"
    elif compression_slot == zstd_slot:
        compression = "zstd"
    elif compression_slot.startswith(b"gzip\0") or compression_slot.startswith(
        b"zstd\0"
    ):
        raise KernelImageError(
            "EFI zboot compression slot has nonzero bytes after its NUL terminator"
        )
    else:
        slot_name = compression_slot.split(b"\0", 1)[0]
        raise KernelImageError(
            "unsupported EFI zboot compression slot: "
            f"{slot_name.decode('ascii', errors='backslashreplace')!r}"
        )

    linux_pe_magic = struct.unpack_from("<I", header, 0x38)[0]
    pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
    pe_signature = header[0x40:0x44]
    machine = struct.unpack_from("<H", header, 0x44)[0]
    optional_magic = struct.unpack_from("<H", header, 0x58)[0]
    if linux_pe_magic != 0x818223CD:
        raise KernelImageError(
            "EFI zboot Linux PE magic is "
            f"0x{linux_pe_magic:08x}, expected 0x818223cd"
        )
    if pe_offset != 0x40:
        raise KernelImageError(
            f"EFI zboot PE header offset is 0x{pe_offset:x}, expected 0x40"
        )
    if pe_signature != b"PE\0\0":
        raise KernelImageError(
            "EFI zboot PE signature is "
            f"{pe_signature.hex()}, expected 50450000"
        )
    if machine != 0x5064:
        raise KernelImageError(
            f"EFI zboot machine is 0x{machine:04x}, expected RISC-V 64 (0x5064)"
        )
    if optional_magic != 0x020B:
        raise KernelImageError(
            "EFI zboot optional-header magic is "
            f"0x{optional_magic:04x}, expected PE32+ (0x020b)"
        )

    if payload_offset < 4096:
        raise KernelImageError(
            f"EFI zboot payload offset {payload_offset} is below 4096"
        )
    if payload_offset % 8 != 0:
        raise KernelImageError(
            f"EFI zboot payload offset {payload_offset} is not 8-byte aligned"
        )
    if payload_size == 0:
        raise KernelImageError("EFI zboot payload size is zero")
    if payload_offset > UINT32_MAX - payload_size:
        raise KernelImageError(
            "EFI zboot payload offset plus size overflows 32-bit arithmetic"
        )
    payload_end = payload_offset + payload_size
    if payload_end > size:
        raise KernelImageError(
            "EFI zboot payload range ends outside the container: "
            f"{payload_end} > {size}"
        )

    expected_size = None
    if compression == "zstd":
        if payload_end > UINT32_MAX - 4:
            raise KernelImageError(
                "EFI zboot zstd trailer offset overflows 32-bit arithmetic"
            )
        if payload_end + 4 > size:
            raise KernelImageError(
                "EFI zboot zstd payload lacks its four-byte size trailer"
            )
        with open(path, "rb") as stream:
            stream.seek(payload_end)
            trailer = stream.read(4)
        expected_size = struct.unpack("<I", trailer)[0]

    return {
        "compression": compression,
        "payload_offset": payload_offset,
        "payload_size": payload_size,
        "payload_end": payload_end,
        "expected_size": expected_size,
    }


def atomic_canonicalize_raw_image(source_path, output_path, expected_size):
    partial_path = output_path + ".partial"
    written = 0
    with open(source_path, "rb") as source, open(partial_path, "xb") as output:
        while True:
            data = source.read(CHUNK_SIZE)
            if not data:
                break
            remaining = expected_size - written
            if len(data) > remaining:
                raise KernelImageError(
                    "raw RISC-V Image grew beyond image_size during private staging"
                )
            output.write(data)
            written += len(data)
        padding_size = expected_size - written
        remaining = padding_size
        while remaining:
            data = ZERO_CHUNK[:min(CHUNK_SIZE, remaining)]
            output.write(data)
            remaining -= len(data)
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial_path, output_path)
    return padding_size


def validate_canonical_raw_image(
    path, source_size, source_hash, expected_size
):
    fields = validate_raw_image(path)
    if fields["image_size"] != expected_size:
        raise KernelImageError(
            "canonical raw RISC-V Image image_size changed during private staging"
        )
    if hash_file_prefix(path, source_size) != source_hash:
        raise KernelImageError(
            "canonical raw RISC-V Image does not preserve the original input prefix"
        )

    remaining = expected_size - source_size
    with open(path, "rb") as stream:
        stream.seek(source_size)
        while remaining:
            data = stream.read(min(CHUNK_SIZE, remaining))
            if not data:
                raise KernelImageError(
                    "canonical raw RISC-V Image zero padding is truncated"
                )
            if any(data):
                raise KernelImageError(
                    "canonical raw RISC-V Image padding contains nonzero bytes"
                )
            remaining -= len(data)
    return fields


def atomic_extract_range(source_path, offset, length, output_path):
    partial_path = output_path + ".partial"
    digest = hashlib.sha256()
    remaining = length
    with open(source_path, "rb") as source, open(partial_path, "xb") as output:
        source.seek(offset)
        while remaining:
            data = source.read(min(CHUNK_SIZE, remaining))
            if not data:
                raise KernelImageError(
                    "EFI zboot payload became truncated while being extracted"
                )
            output.write(data)
            digest.update(data)
            remaining -= len(data)
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial_path, output_path)
    return digest.hexdigest()


def write_lines_atomic(path, lines):
    partial_path = path + ".partial"
    with open(partial_path, "x", encoding="ascii", newline="\n") as output:
        for line in lines:
            if "\n" in line or "\r" in line:
                raise KernelImageError("internal metadata line contains a newline")
            output.write(line)
            output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial_path, path)


def raw_metadata_lines(fields):
    return [
        f"Raw Image header code0 at 0x00: 0x{fields['code0']:08x}",
        f"Raw Image header code1 at 0x04: 0x{fields['code1']:08x}",
        (
            "Raw Image header text_offset at 0x08: "
            f"0x{fields['text_offset']:016x}"
        ),
        f"Raw Image header image_size at 0x10: {fields['image_size']}",
        f"Raw Image header flags at 0x18: 0x{fields['flags']:016x}",
        f"Raw Image header version at 0x20: {fields['version']}",
        (
            "Raw Image header reserved field at 0x24: "
            f"0x{fields['reserved_24']:08x}"
        ),
        (
            "Raw Image header reserved field at 0x28: "
            f"0x{fields['reserved_28']:016x}"
        ),
        f"Raw Image header magic at 0x30: {fields['magic_30'].hex()}",
        f"Raw Image header magic at 0x38: {fields['magic_38'].hex()}",
        (
            "Raw Image header field at 0x3c (not required to be zero): "
            f"0x{fields['field_3c']:08x}"
        ),
    ]


def validate_expected_size(expected_size, source):
    if not 64 <= expected_size <= UINT32_MAX:
        raise KernelImageError(
            f"{source} is outside the valid raw Image size range: {expected_size}"
        )


def bounded_gzip_decompress(payload_path, expected_size, output_path):
    payload_size = os.stat(payload_path).st_size
    if payload_size < 18:
        raise KernelImageError(
            f"EFI zboot gzip payload is too short for header and trailer: {payload_size}"
        )
    gzip_header = read_prefix(payload_path, 10)
    if gzip_header[0:3] != b"\x1f\x8b\x08":
        raise KernelImageError(
            "EFI zboot gzip payload lacks the conventional gzip signature and method"
        )
    if gzip_header[3] != 0:
        raise KernelImageError(
            "EFI zboot gzip payload uses non-conventional optional header flags"
        )

    partial_path = output_path + ".partial"
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    written = 0
    with open(payload_path, "rb") as source, open(partial_path, "xb") as output:
        while True:
            compressed = source.read(CHUNK_SIZE)
            if not compressed:
                break
            if decompressor.eof:
                raise KernelImageError(
                    "EFI zboot gzip payload has trailing or concatenated data"
                )
            pending = compressed
            while pending:
                remaining = expected_size - written
                before = len(pending)
                output_limit = min(CHUNK_SIZE, remaining + 1)
                recovered = decompressor.decompress(pending, output_limit)
                pending = decompressor.unconsumed_tail
                if recovered:
                    allowed = min(len(recovered), remaining)
                    if allowed:
                        output.write(recovered[:allowed])
                        written += allowed
                    if len(recovered) > remaining:
                        output.flush()
                        os.fsync(output.fileno())
                        raise KernelImageError(
                            "EFI zboot gzip output exceeds its ISIZE"
                        )
                if decompressor.unused_data:
                    raise KernelImageError(
                        "EFI zboot gzip payload has trailing or concatenated data"
                    )
                if decompressor.eof:
                    if pending:
                        raise KernelImageError(
                            "EFI zboot gzip payload has trailing or concatenated data"
                        )
                    break
                if len(pending) == before and not recovered:
                    raise KernelImageError(
                        "EFI zboot gzip decompressor made no progress"
                    )
            if decompressor.eof:
                if source.read(1):
                    raise KernelImageError(
                        "EFI zboot gzip payload has trailing or concatenated data"
                    )
                break

        if not decompressor.eof:
            raise KernelImageError("EFI zboot gzip payload is truncated")
        remaining = expected_size - written
        recovered = decompressor.flush(min(CHUNK_SIZE, remaining + 1))
        if recovered:
            allowed = min(len(recovered), remaining)
            if allowed:
                output.write(recovered[:allowed])
                written += allowed
            if len(recovered) > remaining:
                output.flush()
                os.fsync(output.fileno())
                raise KernelImageError(
                    "EFI zboot gzip output exceeds its ISIZE"
                )
        if decompressor.unused_data:
            raise KernelImageError(
                "EFI zboot gzip payload has trailing or concatenated data"
            )
        if written != expected_size:
            raise KernelImageError(
                "EFI zboot gzip output length "
                f"{written} does not equal ISIZE {expected_size}"
            )
        output.flush()
        os.fsync(output.fileno())

    fields = validate_raw_image(partial_path)
    if fields["image_size"] != expected_size:
        raise KernelImageError(
            "recovered raw Image image_size does not equal gzip ISIZE"
        )
    os.replace(partial_path, output_path)
    return fields


def prepare(input_path, raw_output_path, payload_path, analysis_path, raw_meta_path):
    input_size = os.stat(input_path).st_size
    input_hash = hash_file(input_path)
    try:
        raw_fields = validate_raw_image(input_path, allow_short=True)
    except KernelImageError as raw_error:
        prefix = read_prefix(input_path, 8)
        if prefix.startswith(b"\x7fELF"):
            raise KernelImageError(
                "ELF kernel input is unsupported for this Fedora workflow"
            )
        if prefix[:4] != b"MZ\0\0" and prefix[4:8] != b"zimg":
            raise KernelImageError(
                f"invalid raw RISC-V Image: {raw_error}"
            )

        zboot = parse_zboot(input_path)
        payload_hash = atomic_extract_range(
            input_path,
            zboot["payload_offset"],
            zboot["payload_size"],
            payload_path,
        )
        if zboot["compression"] == "gzip":
            if zboot["payload_size"] < 4:
                raise KernelImageError(
                    "EFI zboot gzip payload is too short to contain ISIZE"
                )
            with open(payload_path, "rb") as payload:
                payload.seek(-4, os.SEEK_END)
                expected_size = struct.unpack("<I", payload.read(4))[0]
            expected_source = (
                "gzip payload ISIZE (final little-endian u32)"
            )
            decompressor_identity = (
                f"Python {platform.python_version()} zlib runtime "
                f"{zlib.ZLIB_RUNTIME_VERSION}"
            )
        else:
            expected_size = zboot["expected_size"]
            expected_source = (
                "zstd trailer immediately after payload (little-endian u32)"
            )
            decompressor_identity = "external zstd required"
        validate_expected_size(expected_size, expected_source)
        write_lines_atomic(
            analysis_path,
            [
                "efi-zboot",
                zboot["compression"],
                str(input_size),
                input_hash,
                str(zboot["payload_offset"]),
                str(zboot["payload_size"]),
                payload_hash,
                str(expected_size),
                expected_source,
                decompressor_identity,
                "0",
            ],
        )
        if zboot["compression"] == "gzip":
            raw_fields = bounded_gzip_decompress(
                payload_path, expected_size, raw_output_path
            )
            write_lines_atomic(raw_meta_path, raw_metadata_lines(raw_fields))
        return

    padding_size = atomic_canonicalize_raw_image(
        input_path, raw_output_path, raw_fields["image_size"]
    )
    if hash_file(input_path) != input_hash:
        raise KernelImageError(
            "original raw RISC-V Image changed during private staging"
        )
    copied_fields = validate_canonical_raw_image(
        raw_output_path,
        input_size,
        input_hash,
        raw_fields["image_size"],
    )
    if padding_size != raw_fields["image_size"] - input_size:
        raise KernelImageError(
            "canonical raw RISC-V Image padding size is inconsistent"
        )
    write_lines_atomic(
        analysis_path,
        [
            "raw-riscv-image",
            "none",
            str(input_size),
            input_hash,
            "not-applicable",
            "not-applicable",
            "not-applicable",
            str(copied_fields["image_size"]),
            "raw Image header image_size",
            "none (canonical zero-padding only)",
            str(padding_size),
        ],
    )
    write_lines_atomic(raw_meta_path, raw_metadata_lines(copied_fields))


def bounded_copy_stdin(expected_size, output_path):
    validate_expected_size(expected_size, "zstd trailer size")
    partial_path = output_path + ".partial"
    written = 0
    with open(partial_path, "xb") as output:
        while True:
            remaining = expected_size - written
            data = sys.stdin.buffer.read(min(CHUNK_SIZE, remaining + 1))
            if not data:
                break
            allowed = min(len(data), remaining)
            if allowed:
                output.write(data[:allowed])
                written += allowed
            if len(data) > remaining:
                output.flush()
                os.fsync(output.fileno())
                raise KernelImageError(
                    "EFI zboot zstd output exceeds its size trailer"
                )
        if written != expected_size:
            raise KernelImageError(
                "EFI zboot zstd output length "
                f"{written} does not equal trailer size {expected_size}"
            )
        output.flush()
        os.fsync(output.fileno())
    os.replace(partial_path, output_path)


def validate_recovered_raw(path, expected_size, raw_meta_path):
    fields = validate_raw_image(path)
    if fields["image_size"] != expected_size:
        raise KernelImageError(
            "recovered raw Image image_size does not equal expected output size"
        )
    write_lines_atomic(raw_meta_path, raw_metadata_lines(fields))


def main():
    if len(sys.argv) < 2:
        raise KernelImageError("missing kernel image tool operation")
    operation = sys.argv[1]
    if operation == "prepare" and len(sys.argv) == 7:
        prepare(*sys.argv[2:])
    elif operation == "bounded-copy" and len(sys.argv) == 4:
        try:
            expected_size = int(sys.argv[2], 10)
        except ValueError as error:
            raise KernelImageError(
                f"invalid expected zstd output size: {sys.argv[2]!r}"
            ) from error
        bounded_copy_stdin(expected_size, sys.argv[3])
    elif operation == "validate-raw" and len(sys.argv) == 5:
        try:
            expected_size = int(sys.argv[3], 10)
        except ValueError as error:
            raise KernelImageError(
                f"invalid expected raw Image size: {sys.argv[3]!r}"
            ) from error
        validate_recovered_raw(sys.argv[2], expected_size, sys.argv[4])
    else:
        raise KernelImageError(
            f"invalid kernel image tool invocation for operation {operation!r}"
        )


try:
    main()
except (KernelImageError, OSError, zlib.error) as error:
    print(f"kernel image error: {error}", file=sys.stderr)
    raise SystemExit(1)
PY
	chmod 0400 -- "$1"
}

prepare_direct_kernel()
{
	local source_file=$1
	local destination=$2
	local kernel_analysis=$work_dir/kernel-analysis.txt
	local kernel_payload=$work_dir/kernel-payload.bin
	local kernel_raw_candidate=$work_dir/kernel.raw
	local kernel_snapshot=$work_dir/kernel-input.snapshot
	local kernel_tool=$work_dir/kernel-image-tool.py
	local zstd_identity

	cp --reflink=auto --sparse=always -- "$source_file" "$kernel_snapshot"
	chmod 0400 -- "$kernel_snapshot"
	write_kernel_image_tool "$kernel_tool"
	python3 "$kernel_tool" prepare \
		"$kernel_snapshot" \
		"$kernel_raw_candidate" \
		"$kernel_payload" \
		"$kernel_analysis" \
		"$work_dir/kernel-raw-header.txt" ||
		fail "selected BLS kernel is not a supported raw RISC-V Image or EFI zboot container"

	mapfile -t kernel_info < "$kernel_analysis"
	((${#kernel_info[@]} == 11)) ||
		fail "kernel image analysis did not return the expected metadata"
	kernel_input_format=${kernel_info[0]}
	kernel_compression=${kernel_info[1]}
	kernel_input_size=${kernel_info[2]}
	kernel_input_hash=${kernel_info[3]}
	kernel_payload_offset=${kernel_info[4]}
	kernel_payload_size=${kernel_info[5]}
	kernel_payload_hash=${kernel_info[6]}
	kernel_expected_output_size=${kernel_info[7]}
	kernel_expected_size_source=${kernel_info[8]}
	kernel_decompressor_identity=${kernel_info[9]}
	kernel_canonical_padding_size=${kernel_info[10]}

	[[ $kernel_input_size =~ ^[1-9][0-9]*$ ]] ||
		fail "kernel image analysis returned an invalid input size"
	[[ $kernel_input_hash =~ ^[0-9a-f]{64}$ ]] ||
		fail "kernel image analysis returned an invalid input hash"
	[[ $kernel_expected_output_size =~ ^[1-9][0-9]*$ ]] ||
		fail "kernel image analysis returned an invalid expected output size"
	[[ $kernel_canonical_padding_size =~ ^(0|[1-9][0-9]*)$ ]] ||
		fail "kernel image analysis returned an invalid canonical padding size"
	case "$kernel_input_format:$kernel_compression" in
		raw-riscv-image:none)
			[[ $kernel_payload_offset == not-applicable &&
				$kernel_payload_size == not-applicable &&
				$kernel_payload_hash == not-applicable ]] ||
				fail "raw kernel image analysis returned unexpected payload metadata"
			((kernel_input_size + kernel_canonical_padding_size ==
				kernel_expected_output_size)) ||
				fail "raw kernel image analysis returned inconsistent canonical padding"
			;;
		efi-zboot:gzip|efi-zboot:zstd)
			[[ $kernel_payload_offset =~ ^[1-9][0-9]*$ &&
				$kernel_payload_size =~ ^[1-9][0-9]*$ &&
				$kernel_payload_hash =~ ^[0-9a-f]{64}$ ]] ||
				fail "EFI zboot analysis returned invalid payload metadata"
			[[ $kernel_canonical_padding_size == 0 ]] ||
				fail "EFI zboot analysis unexpectedly requested canonical padding"
			;;
		*)
			fail "kernel image analysis returned an unsupported format/compression pair"
			;;
	esac

	if [[ $kernel_compression == zstd ]]; then
		require_command zstd
		zstd_identity=$(zstd --version) ||
			fail "could not determine zstd decompressor version"
		reject_control_characters "$zstd_identity" "zstd version"
		[[ -n $zstd_identity ]] ||
			fail "zstd returned an empty version string"
		kernel_decompressor_identity=$zstd_identity
		zstd --test --quiet -- "$kernel_payload" ||
			fail "zstd rejected the exact bounded EFI zboot payload"
		if ! zstd --decompress --stdout --quiet -- "$kernel_payload" |
			python3 "$kernel_tool" bounded-copy \
				"$kernel_expected_output_size" \
				"$kernel_raw_candidate"; then
			fail "bounded zstd decompression of the EFI zboot payload failed"
		fi
		python3 "$kernel_tool" validate-raw \
			"$kernel_raw_candidate" \
			"$kernel_expected_output_size" \
			"$work_dir/kernel-raw-header.txt" ||
			fail "zstd-recovered kernel is not a valid raw RISC-V Image"
	fi

	[[ -f $kernel_raw_candidate && ! -L $kernel_raw_candidate &&
		-s $kernel_raw_candidate ]] ||
		fail "kernel conversion did not produce a regular non-empty raw Image"
	kernel_staged_size=$(stat -c '%s' -- "$kernel_raw_candidate")
	[[ $kernel_staged_size == "$kernel_expected_output_size" ]] ||
		fail "validated raw Image size does not match the expected output size"
	kernel_staged_hash=$(sha256_file "$kernel_raw_candidate") ||
		fail "could not hash the validated raw Image"
	if [[ $kernel_input_format == raw-riscv-image &&
		$kernel_canonical_padding_size == 0 &&
		$kernel_staged_hash != "$kernel_input_hash" ]]; then
		fail "exact-size raw RISC-V Image changed during canonical staging"
	fi
	[[ ! -e $destination && ! -L $destination ]] ||
		fail "refusing to replace an existing staged boot/vmlinuz"
	chmod 0400 -- "$kernel_raw_candidate"
	mv -- "$kernel_raw_candidate" "$destination"
	[[ $(stat -c '%s' -- "$destination") == "$kernel_staged_size" &&
		$(sha256_file "$destination") == "$kernel_staged_hash" ]] ||
		fail "atomically published boot/vmlinuz does not match the validated raw Image"
}

validate_hostname()
{
	local hostname=$1
	local label
	local labels=()

	((${#hostname} <= 253)) ||
		fail "FEDORA_GUEST_HOSTNAME is longer than 253 characters"
	[[ $hostname != .* && $hostname != *. && $hostname != *..* ]] ||
		fail "FEDORA_GUEST_HOSTNAME has an empty label"
	IFS=. read -r -a labels <<< "$hostname"
	((${#labels[@]} > 0)) ||
		fail "FEDORA_GUEST_HOSTNAME is empty"
	for label in "${labels[@]}"; do
		[[ $label =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] ||
			fail "FEDORA_GUEST_HOSTNAME has an invalid label: $label"
	done
}

parse_overlay_size()
{
	python3 - "$1" <<'PY'
import re
import sys

value = sys.argv[1]
match = re.fullmatch(r"([1-9][0-9]*)([KMGTPE]?)", value)
if not match:
    raise SystemExit(
        "FEDORA_OVERLAY_SIZE must be a positive integer with an optional "
        "uppercase K, M, G, T, P, or E suffix"
    )
scale = 1024 ** ("KMGTPE".find(match.group(2)) + 1) if match.group(2) else 1
size = int(match.group(1)) * scale
size = ((size + 511) // 512) * 512
if size > (2**63 - 1):
    raise SystemExit("FEDORA_OVERLAY_SIZE exceeds qemu-img's signed 64-bit limit")
print(size)
PY
}

preflight_qcow2_header()
{
	# Reject external qcow2 storage before qemu-img can follow host paths.
	python3 - "$1" <<'PY'
import struct
import sys

path = sys.argv[1]
with open(path, "rb") as image:
    header = image.read(104)

if header[:4] != b"QFI\xfb":
    print("raw")
    raise SystemExit(0)
if len(header) < 24:
    raise SystemExit("truncated qcow header")

version = struct.unpack(">I", header[4:8])[0]
if version not in (2, 3):
    raise SystemExit(f"unsupported qcow header version: {version}")
backing_offset = struct.unpack(">Q", header[8:16])[0]
backing_size = struct.unpack(">I", header[16:20])[0]
if backing_offset or backing_size:
    raise SystemExit("source qcow2 image has an external backing file")
if version == 3:
    if len(header) < 80:
        raise SystemExit("truncated qcow2 v3 header")
    incompatible_features = struct.unpack(">Q", header[72:80])[0]
    if incompatible_features & (1 << 2):
        raise SystemExit("source qcow2 image has an external data file")
print("qcow2")
PY
}

parse_base_info()
{
	python3 - "$1" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    info = json.load(stream)

image_format = info.get("format")
virtual_size = info.get("virtual-size")
if image_format not in {"raw", "qcow2"}:
    raise SystemExit(f"unsupported inner image format reported by qemu-img: {image_format!r}")
if not isinstance(virtual_size, int) or virtual_size <= 0:
    raise SystemExit("qemu-img did not report a positive virtual size")
if info.get("dirty-flag"):
    raise SystemExit("qemu-img reports a dirty source image")

def walk(value):
    if isinstance(value, dict):
        if value.get("name") in {"backing", "data-file"}:
            raise SystemExit("source image exposes external storage")
        for key, child in value.items():
            if key in {
                "backing-filename",
                "full-backing-filename",
                "data-file",
                "full-data-file",
            } and child is not None and child != "":
                raise SystemExit(f"source image has external reference {key}: {child!r}")
            if key == "corrupt" and child is True:
                raise SystemExit("qemu-img reports a corrupt source image")
            walk(child)
    elif isinstance(value, list):
        for child in value:
            walk(child)

walk(info)
print(image_format)
print(virtual_size)
PY
}

parse_overlay_info()
{
	python3 - "$1" "$2" "$3" "$4" <<'PY'
import json
import os
import sys

info_path, expected_base, expected_format, expected_size = sys.argv[1:]
with open(info_path, encoding="utf-8") as stream:
    info = json.load(stream)

if info.get("format") != "qcow2":
    raise SystemExit("created overlay is not qcow2")
if info.get("virtual-size") != int(expected_size):
    raise SystemExit("created overlay virtual size does not match the request")
if info.get("backing-filename") != "base.img":
    raise SystemExit("created overlay does not store the relative backing file base.img")
if info.get("backing-filename-format") != expected_format:
    raise SystemExit("created overlay backing format does not match base-format.txt")
full_backing = info.get("full-backing-filename")
if not isinstance(full_backing, str) or os.path.realpath(full_backing) != expected_base:
    raise SystemExit("created overlay backing file resolves outside OUTPUT_DIR")
if info.get("dirty-flag"):
    raise SystemExit("qemu-img reports a dirty new overlay")

print(info["virtual-size"])
print(info["backing-filename"])
print(info["backing-filename-format"])
PY
}

is_safe_bls_basename()
{
	[[ $1 =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*\.conf$ ]]
}

resolve_boot_path()
{
	local configured_path=$1
	local candidate
	local relative_path
	local resolved

	resolved_boot_path=
	if [[ $configured_path != /* ]]; then
		bls_reason="boot path is not absolute: $configured_path"
		return 1
	fi
	if [[ $configured_path =~ [[:space:]] || $configured_path == *\\* ]]; then
		bls_reason="boot path contains unsupported whitespace or escapes: $configured_path"
		return 1
	fi
	if [[ $configured_path == /boot/* ]]; then
		relative_path=${configured_path#/boot/}
	else
		relative_path=${configured_path#/}
	fi
	case "/$relative_path/" in
		*'/../'*|*'/./'*|*'//'*)
			bls_reason="boot path is not normalized: $configured_path"
			return 1
			;;
	esac
	candidate=$boot_root/$relative_path
	if [[ ! -e $candidate && ! -L $candidate ]]; then
		bls_reason="boot path is stale or missing: $configured_path"
		return 1
	fi
	if ! resolved=$(realpath -e -- "$candidate"); then
		bls_reason="boot path cannot be resolved: $configured_path"
		return 1
	fi
	case "$resolved" in
		"$boot_root"/*)
			;;
		*)
			bls_reason="boot path escapes the extracted /boot tree: $configured_path"
			return 1
			;;
	esac
	if [[ ! -f $resolved || ! -r $resolved || ! -s $resolved ]]; then
		bls_reason="boot path is not a readable non-empty regular file: $configured_path"
		return 1
	fi
	resolved_boot_path=$resolved
}

parse_bls_entry()
{
	local entry=$1
	local entry_name
	local field
	local fields=()
	local line
	local linux_count=0
	local options_count=0
	local root_count=0
	local value

	bls_reason=
	bls_linux=
	bls_options=
	bls_initrds=()
	bls_kernel_file=
	bls_initrd_files=()

	entry_name=$(basename -- "$entry")
	if ! is_safe_bls_basename "$entry_name"; then
		bls_reason="unsafe BLS entry basename"
		return 1
	fi
	if [[ ! -f $entry || ! -r $entry || -L $entry ]]; then
		bls_reason="BLS entry is not a readable regular non-symlink file"
		return 1
	fi
	while IFS= read -r line || [[ -n $line ]]; do
		if [[ $line == *$'\r'* ]]; then
			bls_reason="BLS entry contains carriage returns"
			return 1
		fi
		if [[ $line =~ ^[[:blank:]]*($|#) ]]; then
			continue
		fi
		if [[ ! $line =~ ^[[:blank:]]*([^[:blank:]#]+)[[:blank:]]+(.*)$ ]]; then
			bls_reason="BLS entry contains a malformed line"
			return 1
		fi
		field=${BASH_REMATCH[1]}
		value=${BASH_REMATCH[2]}
		case "$field" in
			linux)
				linux_count=$((linux_count + 1))
				read -r -a fields <<< "$value"
				if ((${#fields[@]} != 1)); then
					bls_reason="linux must name exactly one path"
					return 1
				fi
				bls_linux=${fields[0]}
				;;
			initrd)
				read -r -a fields <<< "$value"
				if ((${#fields[@]} == 0)); then
					bls_reason="initrd line has no paths"
					return 1
				fi
				bls_initrds+=("${fields[@]}")
				;;
			options)
				options_count=$((options_count + 1))
				bls_options=$value
				;;
		esac
	done < "$entry"

	if ((linux_count != 1)); then
		bls_reason="BLS entry must contain exactly one linux line"
		return 1
	fi
	if ((options_count != 1)) || [[ -z $bls_options ]]; then
		bls_reason="BLS entry must contain exactly one non-empty options line"
		return 1
	fi
	if ((${#bls_initrds[@]} == 0)); then
		bls_reason="BLS entry must contain at least one initrd path"
		return 1
	fi
	if [[ $bls_options == *'$'* ]]; then
		bls_reason="BLS options contain an unresolved variable"
		return 1
	fi
	read -r -a fields <<< "$bls_options"
	for field in "${fields[@]}"; do
		if [[ $field == root=?* ]]; then
			root_count=$((root_count + 1))
		fi
	done
	if ((root_count != 1)); then
		bls_reason="BLS options must contain exactly one non-empty root= argument"
		return 1
	fi

	if ! resolve_boot_path "$bls_linux"; then
		return 1
	fi
	bls_kernel_file=$resolved_boot_path
	for field in "${bls_initrds[@]}"; do
		if ! resolve_boot_path "$field"; then
			return 1
		fi
		bls_initrd_files+=("$resolved_boot_path")
	done
}

output_created=0
output_dir=

on_exit()
{
	local status=$?

	trap - EXIT
	if ((status != 0)) && ((output_created == 1)); then
		set +e
		make_work_tree_owner_accessible ||
			printf 'warning: could not make partial work files owner-accessible\n' >&2
		printf 'Preparation failed; partial output is preserved at %s\n' \
			"$output_dir" >&2
	fi
	exit "$status"
}
trap on_exit EXIT

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	if (($# != 1)); then
		usage_error "--help does not accept additional arguments"
	fi
	usage
	exit 0
fi
if (($# != 2)); then
	usage_error "expected OUTPUT_DIR and SSH_PUBLIC_KEY_FILE"
fi

export LC_ALL=C
export TZ=UTC
umask 077

output_arg=$1
key_arg=$2
reject_control_characters "$output_arg" "OUTPUT_DIR"
reject_control_characters "$key_arg" "SSH_PUBLIC_KEY_FILE"

image_url_is_set=0
image_path_is_set=0
[[ -v FEDORA_IMAGE_URL ]] && image_url_is_set=1
[[ -v FEDORA_IMAGE_PATH ]] && image_path_is_set=1
if ((image_url_is_set + image_path_is_set > 1)); then
	usage_error "set at most one of FEDORA_IMAGE_URL or FEDORA_IMAGE_PATH"
fi

image_url=
image_path=
source_selection=
uses_pinned_fedora_image=0
if ((image_url_is_set == 1)); then
	image_url=$FEDORA_IMAGE_URL
	[[ -n $image_url ]] ||
		usage_error "FEDORA_IMAGE_URL must not be empty"
	source_selection=explicit-url
	if [[ $image_url == "$DEFAULT_FEDORA_IMAGE_URL" ]]; then
		uses_pinned_fedora_image=1
		source_selection=explicit-pinned-url
	fi
elif ((image_path_is_set == 1)); then
	image_path=$FEDORA_IMAGE_PATH
	[[ -n $image_path ]] ||
		usage_error "FEDORA_IMAGE_PATH must not be empty"
	source_selection=explicit-path
else
	image_url_is_set=1
	image_url=$DEFAULT_FEDORA_IMAGE_URL
	source_selection=pinned-default
	uses_pinned_fedora_image=1
fi

if [[ -v FEDORA_IMAGE_SHA256 ]]; then
	image_sha256=$FEDORA_IMAGE_SHA256
elif ((uses_pinned_fedora_image == 1)); then
	image_sha256=$DEFAULT_FEDORA_IMAGE_SHA256
else
	usage_error "FEDORA_IMAGE_SHA256 is required for a custom source"
fi
if [[ -v FEDORA_IMAGE_COMPRESSION ]]; then
	image_compression=$FEDORA_IMAGE_COMPRESSION
elif ((uses_pinned_fedora_image == 1)); then
	image_compression=none
else
	image_compression=auto
fi
if [[ -v FEDORA_IMAGE_FORMAT ]]; then
	image_format=$FEDORA_IMAGE_FORMAT
elif ((uses_pinned_fedora_image == 1)); then
	image_format=qcow2
else
	image_format=auto
fi
guest_user=${FEDORA_GUEST_USER-fedora}
guest_hostname=${FEDORA_GUEST_HOSTNAME-k3-fedora-guest}
overlay_size=${FEDORA_OVERLAY_SIZE-20G}
bls_entry_is_set=0
bls_entry=
if [[ -v FEDORA_BLS_ENTRY ]]; then
	bls_entry_is_set=1
	bls_entry=$FEDORA_BLS_ENTRY
fi

[[ $image_sha256 =~ ^[0-9a-f]{64}$ ]] ||
	usage_error "FEDORA_IMAGE_SHA256 must be exactly 64 lowercase hexadecimal digits"
if ((uses_pinned_fedora_image == 1)) &&
	[[ $image_sha256 != "$DEFAULT_FEDORA_IMAGE_SHA256" ]]; then
	usage_error "FEDORA_IMAGE_SHA256 must match the official checksum for the pinned Fedora URL"
fi
case "$image_compression" in
	auto|none|xz)
		;;
	*)
		usage_error "FEDORA_IMAGE_COMPRESSION must be auto, none, or xz"
		;;
esac
case "$image_format" in
	auto|raw|qcow2)
		;;
	*)
		usage_error "FEDORA_IMAGE_FORMAT must be auto, raw, or qcow2"
		;;
esac
[[ $guest_user =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] ||
	usage_error "FEDORA_GUEST_USER must be a safe lowercase Linux account name"
[[ $guest_user != root ]] ||
	usage_error "FEDORA_GUEST_USER must not be root"
validate_hostname "$guest_hostname"
[[ $overlay_size =~ ^[1-9][0-9]*[KMGTPE]?$ ]] ||
	usage_error "FEDORA_OVERLAY_SIZE must be a positive integer with an optional uppercase K, M, G, T, P, or E suffix"
if ((bls_entry_is_set == 1)); then
	reject_control_characters "$bls_entry" "FEDORA_BLS_ENTRY"
	is_safe_bls_basename "$bls_entry" ||
		usage_error "FEDORA_BLS_ENTRY must be an exact safe .conf basename"
fi

for command_name in \
	basename \
	cat \
	chmod \
	cloud-localds \
	cp \
	dirname \
	grep \
	mkdir \
	mv \
	od \
	python3 \
	qemu-img \
	realpath \
	rm \
	sha256sum \
	ssh-keygen \
	stat \
	tr \
	virt-copy-out; do
	require_command "$command_name"
done
if ((image_url_is_set == 1)); then
	require_command curl
fi
if [[ $image_compression != none ]]; then
	require_command xz
fi

overlay_size_bytes=$(parse_overlay_size "$overlay_size") ||
	fail "invalid FEDORA_OVERLAY_SIZE: $overlay_size"

output_parent_arg=$(dirname -- "$output_arg")
output_name=$(basename -- "$output_arg")
case "$output_name" in
	''|.|..|/)
		fail "unsafe OUTPUT_DIR basename: $output_name"
		;;
esac
[[ -d $output_parent_arg ]] ||
	fail "OUTPUT_DIR parent is not a directory: $output_parent_arg"
output_parent=$(realpath -e -- "$output_parent_arg") ||
	fail "OUTPUT_DIR parent cannot be resolved: $output_parent_arg"
[[ -d $output_parent && -w $output_parent && -x $output_parent ]] ||
	fail "OUTPUT_DIR parent is not writable and searchable: $output_parent"
output_dir=$output_parent/$output_name
if [[ -e $output_dir || -L $output_dir ]]; then
	fail "refusing pre-existing or symlink OUTPUT_DIR: $output_dir"
fi

if [[ ! -e $key_arg && ! -L $key_arg ]]; then
	fail "SSH public key file does not exist: $key_arg"
fi
[[ ! -L $key_arg ]] ||
	fail "refusing symlink SSH public key file: $key_arg"
[[ -f $key_arg && -r $key_arg && -s $key_arg ]] ||
	fail "SSH public key file must be a readable non-empty regular file: $key_arg"
key_file=$(realpath -e -- "$key_arg") ||
	fail "SSH public key file cannot be resolved: $key_arg"
reject_control_characters "$key_file" "resolved SSH public key path"
key_size=$(stat -c '%s' -- "$key_file")
((key_size <= 16384)) ||
	fail "SSH public key file is unexpectedly large"
mapfile -t key_lines < "$key_file"
for key_line_candidate in "${key_lines[@]}"; do
	case "$key_line_candidate" in
		*'PRIVATE KEY'*|PuTTY-User-Key-File:*|*'SSH2 ENCRYPTED'*)
			fail "SSH_PUBLIC_KEY_FILE appears to contain private-key material"
			;;
	esac
done
((${#key_lines[@]} == 1)) ||
	fail "SSH public key file must contain exactly one line"
ssh_public_key=${key_lines[0]}
[[ -n $ssh_public_key ]] ||
	fail "SSH public key file contains an empty key"
reject_control_characters "$ssh_public_key" "SSH public key"
[[ $ssh_public_key =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)|sk-ssh-ed25519@openssh.com|sk-ecdsa-sha2-nistp256@openssh.com)[[:blank:]]+[A-Za-z0-9+/]+={0,3}([[:blank:]].*)?$ ]] ||
	fail "SSH_PUBLIC_KEY_FILE is not a supported single OpenSSH public key"
ssh-keygen -l -E sha256 -f "$key_file" >/dev/null ||
	fail "ssh-keygen rejected SSH_PUBLIC_KEY_FILE"
ssh_key_info=$(ssh-keygen -l -E sha256 -f "$key_file")
read -r _ ssh_key_fingerprint _ <<< "$ssh_key_info"
[[ $ssh_key_fingerprint == SHA256:* ]] ||
	fail "could not determine the SSH public key fingerprint"

source_kind=
source_identity=
source_path=
if ((image_url_is_set == 1)); then
	reject_control_characters "$image_url" "FEDORA_IMAGE_URL"
	https_url_pattern='^https://[^/?#@[:space:]]+(/[^?#[:space:]]*)?$'
	[[ $image_url =~ $https_url_pattern ]] ||
		usage_error "FEDORA_IMAGE_URL must be a credential-free HTTPS URL without a query or fragment"
	source_kind=url
	source_identity=$image_url
else
	reject_control_characters "$image_path" "FEDORA_IMAGE_PATH"
	if [[ ! -e $image_path && ! -L $image_path ]]; then
		fail "FEDORA_IMAGE_PATH does not exist: $image_path"
	fi
	[[ ! -L $image_path ]] ||
		fail "refusing symlink FEDORA_IMAGE_PATH: $image_path"
	[[ -f $image_path && -r $image_path && -s $image_path ]] ||
		fail "FEDORA_IMAGE_PATH must be a readable non-empty regular file: $image_path"
	source_path=$(realpath -e -- "$image_path") ||
		fail "FEDORA_IMAGE_PATH cannot be resolved: $image_path"
	reject_control_characters "$source_path" "resolved FEDORA_IMAGE_PATH"
	source_kind=path
	source_identity=$source_path
fi

mkdir -m 0700 -- "$output_dir"
output_created=1
[[ ! -L $output_dir ]] ||
	fail "OUTPUT_DIR became a symlink: $output_dir"
[[ $(realpath -e -- "$output_dir") == "$output_dir" ]] ||
	fail "OUTPUT_DIR did not resolve to the validated path: $output_dir"

work_dir=$output_dir/.work
mkdir -m 0700 -- "$work_dir"
verified_source=$work_dir/source.verified

if [[ $source_kind == url ]]; then
	curl \
		--fail \
		--location \
		--max-redirs 10 \
		--proto '=https' \
		--proto-redir '=https' \
		--show-error \
		--silent \
		--output "$verified_source" \
		"$source_identity"
	[[ -s $verified_source ]] ||
		fail "downloaded Fedora source image is empty"
else
	source_hash_before=$(sha256_file "$source_path")
	[[ $source_hash_before == "$image_sha256" ]] ||
		fail "FEDORA_IMAGE_PATH checksum does not match FEDORA_IMAGE_SHA256"
	cp --reflink=auto --sparse=always -- "$source_path" "$verified_source"
fi

verified_source_hash=$(sha256_file "$verified_source")
[[ $verified_source_hash == "$image_sha256" ]] ||
	fail "staged source checksum does not match FEDORA_IMAGE_SHA256"
chmod 0400 -- "$verified_source"

source_magic=$(od -An -tx1 -N6 "$verified_source" | tr -d '[:space:]')
detected_compression=none
if [[ $source_magic == fd377a585a00 ]]; then
	detected_compression=xz
fi
case "$image_compression" in
	auto)
		resolved_compression=$detected_compression
		;;
	none)
		[[ $detected_compression == none ]] ||
			fail "FEDORA_IMAGE_COMPRESSION=none conflicts with xz source magic"
		resolved_compression=none
		;;
	xz)
		[[ $detected_compression == xz ]] ||
			fail "FEDORA_IMAGE_COMPRESSION=xz but the source lacks xz magic"
		resolved_compression=xz
		;;
esac

base_img=$output_dir/base.img
if [[ $resolved_compression == xz ]]; then
	require_command xz
	xz --test -- "$verified_source"
	xz --decompress --stdout -- "$verified_source" > "$base_img"
else
	mv -- "$verified_source" "$base_img"
fi
[[ -s $base_img ]] ||
	fail "inner Fedora image is empty"
if [[ $resolved_compression == none ]]; then
	[[ $(sha256_file "$base_img") == "$image_sha256" ]] ||
		fail "base.img changed after source verification"
fi
chmod 0444 -- "$base_img"

preflight_qcow2_header "$base_img" > "$work_dir/header-format.txt"
inner_format=$(<"$work_dir/header-format.txt")
case "$inner_format" in
	raw|qcow2)
		;;
	*)
		fail "header preflight returned an unsupported image format: $inner_format"
		;;
esac
if [[ $image_format != auto && $image_format != "$inner_format" ]]; then
	fail "FEDORA_IMAGE_FORMAT=$image_format does not match header format $inner_format"
fi

qemu-img info -f "$inner_format" --output=json "$base_img" \
	> "$work_dir/base-info.json"
parse_base_info "$work_dir/base-info.json" > "$work_dir/base-info.txt"
mapfile -t base_info < "$work_dir/base-info.txt"
((${#base_info[@]} == 2)) ||
	fail "could not parse qemu-img base image information"
reported_format=${base_info[0]}
base_virtual_size=${base_info[1]}
[[ $reported_format == "$inner_format" ]] ||
	fail "qemu-img format $reported_format conflicts with header format $inner_format"

if [[ $inner_format == raw ]]; then
	raw_check_status=0
	qemu-img check -f raw "$base_img" > "$work_dir/qemu-img-check.txt" 2>&1 ||
		raw_check_status=$?
	if ((raw_check_status == 0)); then
		qemu_check_identity=passed
	else
		if ((raw_check_status != 63)) ||
			! grep -Fq 'This image format does not support checks' \
				"$work_dir/qemu-img-check.txt"; then
			fail "qemu-img check failed for raw base.img"
		fi
		qemu_check_identity="unsupported-for-raw (qemu-img status $raw_check_status)"
	fi
else
	qemu-img check -f qcow2 "$base_img" \
		> "$work_dir/qemu-img-check.txt" 2>&1 ||
		fail "qemu-img check failed for qcow2 base.img"
	qemu_check_identity=passed
fi

((overlay_size_bytes > base_virtual_size)) ||
	fail "FEDORA_OVERLAY_SIZE must be larger than the base virtual size ($base_virtual_size bytes)"
printf '%s\n' "$inner_format" > "$output_dir/base-format.txt"

extract_root=$work_dir/extracted
mkdir -m 0700 -- "$extract_root"
virt-copy-out \
	--format="$inner_format" \
	-a "$base_img" \
	/boot \
	"$extract_root"
# Fedora's read-only /boot mode must not make the private copy uninspectable.
make_work_tree_owner_accessible
[[ -d $extract_root/boot ]] ||
	fail "virt-copy-out did not produce an extracted /boot directory"
extract_root=$(realpath -e -- "$extract_root")
boot_root=$(realpath -e -- "$extract_root/boot") ||
	fail "extracted /boot directory cannot be resolved"
case "$boot_root" in
	"$extract_root"/*)
		;;
	*)
		fail "extracted /boot directory escapes the private work tree"
		;;
esac

entries_candidate=$boot_root/loader/entries
[[ -d $entries_candidate ]] ||
	fail "extracted image has no /boot/loader/entries directory"
entries_dir=$(realpath -e -- "$entries_candidate") ||
	fail "BLS entries directory cannot be resolved"
case "$entries_dir" in
	"$boot_root"/*)
		;;
	*)
		fail "BLS entries directory escapes the extracted /boot tree"
		;;
esac

selected_bls=
: > "$work_dir/bls-scan.txt"
if ((bls_entry_is_set == 1)); then
	selected_bls=$entries_dir/$bls_entry
	if ! parse_bls_entry "$selected_bls"; then
		printf 'unusable selected entry: %q: %s\n' \
			"$selected_bls" "$bls_reason" >> "$work_dir/bls-scan.txt"
		fail "selected BLS entry is missing, stale, or unusable: $bls_entry ($bls_reason)"
	fi
	printf 'usable selected entry: %q\n' "$selected_bls" \
		>> "$work_dir/bls-scan.txt"
else
	shopt -s nullglob
	entry_files=("$entries_dir"/*.conf)
	shopt -u nullglob
	usable_entries=()
	for entry in "${entry_files[@]}"; do
		if parse_bls_entry "$entry"; then
			usable_entries+=("$entry")
			printf 'usable: %q\n' "$entry" >> "$work_dir/bls-scan.txt"
		else
			printf 'unusable: %q: %s\n' "$entry" "$bls_reason" \
				>> "$work_dir/bls-scan.txt"
		fi
	done
	if ((${#usable_entries[@]} != 1)); then
		fail "expected exactly one usable BLS entry, found ${#usable_entries[@]} (see $work_dir/bls-scan.txt)"
	fi
	selected_bls=${usable_entries[0]}
	parse_bls_entry "$selected_bls" ||
		fail "selected BLS entry changed while being staged: $bls_reason"
fi

selected_bls_name=$(basename -- "$selected_bls")
selected_bls_hash=$(sha256_file "$selected_bls") ||
	fail "could not hash the selected BLS entry"
boot_output=$output_dir/boot
mkdir -m 0700 -- "$boot_output"
prepare_direct_kernel "$bls_kernel_file" "$boot_output/vmlinuz"
cat -- "${bls_initrd_files[@]}" > "$boot_output/initramfs.img"
printf '%s\n' "$bls_options" > "$boot_output/cmdline.txt"
[[ -s $boot_output/vmlinuz && -s $boot_output/initramfs.img &&
	-s $boot_output/cmdline.txt ]] ||
	fail "one or more staged boot inputs are empty"

identity_output=$(
	printf '%s\n%s\n%s\n%s\n' \
		"$image_sha256" \
		"$guest_hostname" \
		"$guest_user" \
		"$ssh_key_fingerprint" |
		sha256sum
)
guest_identity=${identity_output%% *}
instance_id=k3-fedora-${guest_identity:0:24}

cat > "$output_dir/user-data" <<EOF
#cloud-config
preserve_hostname: false
hostname: "$guest_hostname"
manage_etc_hosts: true
users:
  - name: "$guest_user"
    gecos: Fedora Cloud User
    groups:
      - wheel
    shell: /bin/bash
    lock_passwd: true
    sudo:
      - "ALL=(ALL) NOPASSWD:ALL"
    ssh_authorized_keys:
      - >-
          $ssh_public_key
ssh_pwauth: false
disable_root: true
growpart:
  mode: auto
  devices:
    - /
  ignore_growroot_disabled: false
resize_rootfs: true
runcmd:
  - [systemctl, enable, --now, serial-getty@ttyS0.service, sshd.service]
EOF

cat > "$output_dir/meta-data" <<EOF
instance-id: $instance_id
local-hostname: "$guest_hostname"
EOF

cloud-localds \
	"$output_dir/seed.img" \
	"$output_dir/user-data" \
	"$output_dir/meta-data"
[[ -s $output_dir/seed.img ]] ||
	fail "cloud-localds produced an empty seed.img"

(
	cd "$output_dir"
	qemu-img create \
		-f qcow2 \
		-F "$inner_format" \
		-b base.img \
		overlay.qcow2 \
		"$overlay_size_bytes"
)
[[ -s $output_dir/overlay.qcow2 ]] ||
	fail "qemu-img produced an empty overlay.qcow2"
chmod 0600 -- "$output_dir/overlay.qcow2"
qemu-img info -f qcow2 --output=json "$output_dir/overlay.qcow2" \
	> "$work_dir/overlay-info.json"
parse_overlay_info \
	"$work_dir/overlay-info.json" \
	"$base_img" \
	"$inner_format" \
	"$overlay_size_bytes" \
	> "$work_dir/overlay-info.txt"
mapfile -t overlay_info < "$work_dir/overlay-info.txt"
((${#overlay_info[@]} == 3)) ||
	fail "could not parse qemu-img overlay information"
overlay_virtual_size=${overlay_info[0]}
overlay_backing_file=${overlay_info[1]}
overlay_backing_format=${overlay_info[2]}

base_hash=$(sha256_file "$base_img") ||
	fail "could not hash base.img"
overlay_initial_hash=$(sha256_file "$output_dir/overlay.qcow2") ||
	fail "could not hash overlay.qcow2"
kernel_hash=$(sha256_file "$boot_output/vmlinuz") ||
	fail "could not hash staged boot/vmlinuz"
initramfs_hash=$(sha256_file "$boot_output/initramfs.img") ||
	fail "could not hash staged boot/initramfs.img"
cmdline_hash=$(sha256_file "$boot_output/cmdline.txt") ||
	fail "could not hash staged boot/cmdline.txt"
user_data_hash=$(sha256_file "$output_dir/user-data") ||
	fail "could not hash user-data"
meta_data_hash=$(sha256_file "$output_dir/meta-data") ||
	fail "could not hash meta-data"
seed_hash=$(sha256_file "$output_dir/seed.img") ||
	fail "could not hash seed.img"
kernel_output_size=$(stat -c '%s' -- "$boot_output/vmlinuz") ||
	fail "could not determine staged boot/vmlinuz size"
initramfs_output_size=$(stat -c '%s' -- "$boot_output/initramfs.img") ||
	fail "could not determine staged boot/initramfs.img size"
[[ $kernel_output_size == "$kernel_staged_size" &&
	$kernel_hash == "$kernel_staged_hash" ]] ||
	fail "staged boot/vmlinuz changed after validated publication"
bls_initrd_hashes=()
for index in "${!bls_initrd_files[@]}"; do
	bls_initrd_hash=$(sha256_file "${bls_initrd_files[index]}") ||
		fail "could not hash selected BLS initrd $((index + 1))"
	bls_initrd_hashes+=("$bls_initrd_hash")
done

{
	printf 'Source selection: %s\n' "$source_selection"
	printf 'Source kind: %s\n' "$source_kind"
	if [[ $source_kind == url ]]; then
		printf 'Source URL: %s\n' "$source_identity"
	else
		printf 'Source path: %s\n' "$source_identity"
	fi
	if ((uses_pinned_fedora_image == 1)); then
		printf 'Source image class: Fedora-hosted community RISC-V image\n'
		printf 'Official checksum URL: %s\n' \
			"$DEFAULT_FEDORA_IMAGE_CHECKSUM_URL"
	else
		printf 'Source image class: operator-supplied image\n'
	fi
	printf 'Required source SHA-256: %s\n' "$image_sha256"
	printf 'Verified source SHA-256: %s\n' "$verified_source_hash"
	printf 'Requested source compression: %s\n' "$image_compression"
	printf 'Verified source compression: %s\n' "$resolved_compression"
	printf 'Requested inner image format: %s\n' "$image_format"
	printf 'Verified inner image format: %s\n' "$inner_format"
	printf 'qemu-img check: %s\n' "$qemu_check_identity"
	printf 'Base virtual size bytes: %s\n' "$base_virtual_size"
	printf 'Base image SHA-256: %s\n' "$base_hash"
	printf 'Selected BLS entry: %s\n' "$selected_bls_name"
	printf 'Selected BLS entry SHA-256: %s\n' "$selected_bls_hash"
	printf 'Selected BLS linux path: %s\n' "$bls_linux"
	printf 'Selected BLS options: %s\n' "$bls_options"
	printf 'Selected BLS initrd count: %s\n' "${#bls_initrds[@]}"
	for index in "${!bls_initrds[@]}"; do
		printf 'Selected BLS initrd %d path: %s\n' \
			"$((index + 1))" "${bls_initrds[index]}"
		printf 'Selected BLS initrd %d SHA-256: %s\n' \
			"$((index + 1))" \
			"${bls_initrd_hashes[index]}"
	done
	printf 'Original BLS kernel path: %s\n' "$bls_linux"
	printf 'Original BLS kernel snapshot size bytes: %s\n' \
		"$kernel_input_size"
	printf 'Original BLS kernel snapshot SHA-256: %s\n' \
		"$kernel_input_hash"
	printf 'Original raw/container size bytes: %s\n' "$kernel_input_size"
	printf 'Kernel input format: %s\n' "$kernel_input_format"
	printf 'Kernel compression: %s\n' "$kernel_compression"
	printf 'Kernel parsed payload offset bytes: %s\n' \
		"$kernel_payload_offset"
	printf 'Kernel parsed payload size bytes: %s\n' "$kernel_payload_size"
	printf 'Kernel parsed payload SHA-256: %s\n' "$kernel_payload_hash"
	printf 'Kernel expected raw Image size bytes: %s\n' \
		"$kernel_expected_output_size"
	printf 'Raw Image header image_size bytes: %s\n' \
		"$kernel_expected_output_size"
	printf 'Canonical padding byte count: %s\n' \
		"$kernel_canonical_padding_size"
	printf 'Kernel expected size source/trailer: %s\n' \
		"$kernel_expected_size_source"
	printf 'Kernel decompressor: %s\n' "$kernel_decompressor_identity"
	cat -- "$work_dir/kernel-raw-header.txt"
	printf 'Direct-kernel suitability basis: boot/vmlinuz is a canonical zero-padded, strictly validated raw RISC-V Linux Image; BLS readability alone is insufficient\n'
	printf 'Guest user: %s\n' "$guest_user"
	printf 'Guest hostname: %s\n' "$guest_hostname"
	printf 'SSH public key fingerprint: %s\n' "$ssh_key_fingerprint"
	printf 'NoCloud instance ID: %s\n' "$instance_id"
	printf 'Requested overlay size: %s\n' "$overlay_size"
	printf 'Effective overlay size bytes: %s\n' "$overlay_size_bytes"
	printf 'Initial overlay format: qcow2\n'
	printf 'Initial overlay virtual size bytes: %s\n' "$overlay_virtual_size"
	printf 'Initial overlay backing file: %s\n' "$overlay_backing_file"
	printf 'Initial overlay backing format: %s\n' "$overlay_backing_format"
	printf 'Initial overlay SHA-256: %s\n' "$overlay_initial_hash"
	printf 'Staged boot/vmlinuz format: raw-riscv-image\n'
	printf 'Staged boot/vmlinuz representation: canonical zero-padded raw RISC-V Image\n'
	printf 'Staged boot/vmlinuz original BLS path: %s\n' "$bls_linux"
	printf 'Staged boot/vmlinuz size bytes: %s\n' "$kernel_output_size"
	printf 'Staged boot/vmlinuz SHA-256: %s\n' "$kernel_hash"
	printf 'Staged boot/initramfs.img construction: concatenated BLS initrd paths in listed order\n'
	printf 'Staged boot/initramfs.img size bytes: %s\n' \
		"$initramfs_output_size"
	printf 'Staged boot/initramfs.img SHA-256: %s\n' "$initramfs_hash"
	printf 'Staged boot/cmdline.txt source: exact selected BLS options value plus newline\n'
	printf 'Staged boot/cmdline.txt SHA-256: %s\n' "$cmdline_hash"
	printf 'user-data SHA-256: %s\n' "$user_data_hash"
	printf 'meta-data SHA-256: %s\n' "$meta_data_hash"
	printf 'seed.img SHA-256: %s\n' "$seed_hash"
} > "$output_dir/source.txt"

chmod 0444 -- \
	"$base_img" \
	"$output_dir/base-format.txt" \
	"$output_dir/seed.img" \
	"$output_dir/user-data" \
	"$output_dir/meta-data" \
	"$boot_output/vmlinuz" \
	"$boot_output/initramfs.img" \
	"$boot_output/cmdline.txt" \
	"$output_dir/source.txt"

(
	cd "$output_dir"
	sha256sum \
		base.img \
		base-format.txt \
		seed.img \
		user-data \
		meta-data \
		boot/vmlinuz \
		boot/initramfs.img \
		boot/cmdline.txt \
		source.txt \
		> SHA256SUMS
	sha256sum --check --strict SHA256SUMS
)
chmod 0444 -- "$output_dir/SHA256SUMS"

make_work_tree_owner_accessible
rm -rf -- "$work_dir"

cat <<EOF
Fedora RISC-V guest prepared successfully.

Output:       $output_dir
Base format:  $inner_format
BLS entry:    $selected_bls_name
Kernel:       canonical zero-padded raw RISC-V Image
Guest user:   $guest_user
Guest host:   $guest_hostname
Overlay size: $overlay_size

The guest has not been booted or transferred.
EOF
