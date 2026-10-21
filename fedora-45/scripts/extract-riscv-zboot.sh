#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -Eeuo pipefail
set -x

usage()
{
	cat <<'EOF'
Usage: extract-riscv-zboot.sh INPUT OUTPUT

Extract a gzip- or zstd-compressed raw RISC-V Linux Image from an EFI zboot
container. This standalone file-to-file helper needs Python 3; zstd input
also needs the zstd command. OUTPUT's parent must exist.

OUTPUT, OUTPUT.partial and OUTPUT.payload.partial must not already exist.
Header, payload bounds, compression, declared length and raw Image header
are checked before atomic, non-overwriting publication. Failure cleans only
this invocation's partial files. No package, disk or boot state is changed.
EOF
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	usage
	exit 0
fi
[[ $# -eq 2 ]] || { usage >&2; exit 2; }
command -v python3 >/dev/null || {
	printf 'error: Required command not found: python3\n' >&2
	exit 1
}

python3 -I -B - "$@" <<'PY'
import gzip
import hashlib
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import zlib


class Error(Exception):
    pass


def raw_header(path, expected_size):
    with open(path, "rb") as stream:
        header = stream.read(64)
    if len(header) != 64:
        raise Error("raw RISC-V Image header is short")
    text_offset, image_size, flags = struct.unpack_from("<QQQ", header, 8)
    version, reserved_24, reserved_28 = struct.unpack_from("<IIQ", header, 0x20)
    if text_offset != 0x200000:
        raise Error("unexpected raw Image text offset")
    if image_size != expected_size or os.stat(path).st_size != expected_size:
        raise Error("raw Image size does not match its header")
    if flags != 0 or version != 2 or reserved_24 != 0 or reserved_28 != 0:
        raise Error("invalid raw RISC-V Image header fields")
    if header[0x30:0x38] != b"RISCV\0\0\0" or header[0x38:0x3C] != b"RSC\x05":
        raise Error("invalid raw RISC-V Image magic")


def extract(input_arg, output_arg):
    source_path = Path(input_arg)
    output_arg = Path(output_arg)
    parent = output_arg.parent.resolve(strict=True)
    output = parent / output_arg.name
    partial = Path(str(output) + ".partial")
    payload_path = Path(str(output) + ".payload.partial")
    for path in (output, partial, payload_path):
        if os.path.lexists(path):
            raise Error("output or partial file already exists")

    owned = []
    decoder = None
    try:
        fd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as source:
            before = os.fstat(source.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise Error("INPUT must be a readable regular non-symlink file")
            header = source.read(0x5A)
            if len(header) != 0x5A:
                raise Error("zboot container is too short")
            if header[:4] != b"MZ\0\0" or header[4:8] != b"zimg":
                raise Error("invalid EFI zboot signature or image type")
            offset, payload_size = struct.unpack_from("<II", header, 8)
            if struct.unpack_from("<II", header, 0x10) != (0, 0):
                raise Error("nonzero EFI zboot reserved fields")
            slot = header[0x18:0x38]
            if slot == b"zstd\0" + b"\0" * 27:
                compression = "zstd"
            elif slot == b"gzip\0" + b"\0" * 27:
                compression = "gzip"
            else:
                raise Error("unsupported or malformed compression slot")
            if (
                struct.unpack_from("<I", header, 0x38)[0] != 0x818223CD
                or struct.unpack_from("<I", header, 0x3C)[0] != 0x40
                or header[0x40:0x44] != b"PE\0\0"
                or struct.unpack_from("<H", header, 0x44)[0] != 0x5064
                or struct.unpack_from("<H", header, 0x58)[0] != 0x020B
            ):
                raise Error("invalid RISC-V 64 PE32+ zboot header")
            if offset < 4096 or offset % 8 or payload_size == 0:
                raise Error("unsafe zboot payload offset or length")
            end = offset + payload_size
            if end > before.st_size:
                raise Error("zboot payload extends past the input")
            if compression == "zstd":
                if end + 4 > before.st_size:
                    raise Error("zstd payload lacks its output-size trailer")
                source.seek(end)
            else:
                if payload_size < 18:
                    raise Error("gzip payload is too short")
                source.seek(end - 4)
            expected_size = struct.unpack("<I", source.read(4))[0]
            if expected_size < 64:
                raise Error("invalid declared raw Image size")

            payload_fd = os.open(
                payload_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            owned.append(payload_path)
            with os.fdopen(payload_fd, "wb") as payload:
                source.seek(offset)
                remaining = payload_size
                while remaining:
                    data = source.read(min(1024 * 1024, remaining))
                    if not data:
                        raise Error("short read of zboot payload")
                    payload.write(data)
                    remaining -= len(data)

            output_fd = os.open(
                partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            owned.append(partial)
            with os.fdopen(output_fd, "wb") as destination:
                if compression == "gzip":
                    recovered = gzip.open(payload_path, "rb")
                else:
                    decoder = subprocess.Popen(
                        ["zstd", "--decompress", "--stdout", "--quiet", "--",
                         str(payload_path)], stdout=subprocess.PIPE,
                    )
                    recovered = decoder.stdout
                checksum = hashlib.sha256()
                with recovered:
                    written = 0
                    while True:
                        data = recovered.read(min(1024 * 1024,
                                                  expected_size - written + 1))
                        if not data:
                            break
                        written += len(data)
                        if written > expected_size:
                            raise Error("decompressed Image exceeds declared size")
                        destination.write(data)
                        checksum.update(data)
                if decoder is not None and decoder.wait() != 0:
                    raise Error("zstd payload validation failed")
                if written != expected_size:
                    raise Error("recovered Image length does not match declaration")
                destination.flush()
                os.fchmod(destination.fileno(), 0o644)
                os.fsync(destination.fileno())
            raw_header(partial, expected_size)
            after = os.fstat(source.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns
            ):
                raise Error("INPUT changed during extraction")
            source.seek(0)
            input_checksum = hashlib.sha256()
            for block in iter(lambda: source.read(1024 * 1024), b""):
                input_checksum.update(block)
            # link() publishes atomically without replacing an existing name.
            os.link(partial, output, follow_symlinks=False)
            print("Input SHA-256: ", input_checksum.hexdigest())
            print("Output SHA-256:", checksum.hexdigest())
            print("Output bytes:  ", expected_size)
    finally:
        if decoder is not None and decoder.poll() is None:
            decoder.kill()
            decoder.wait()
        for path in reversed(owned):
            path.unlink(missing_ok=True)


try:
    extract(*sys.argv[1:])
except (Error, OSError, ValueError, EOFError, struct.error, zlib.error) as exc:
    print(f"error: {exc}", file=sys.stderr)
    sys.exit(1)
PY
