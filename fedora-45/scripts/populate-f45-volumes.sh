#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -Eeuo pipefail
set -x

readonly ACK=YES-FORMAT-F45-VOLUMES

usage()
{
	cat <<'EOF'
Usage:
  populate-f45-volumes.sh [--check] IMAGE.raw.xz WHOLE_DISK BOOT_PART ROOT_PART

Freshly install the pinned Fedora 45 Beta Omni image into two existing
partitions of WHOLE_DISK: BOOT_PART becomes ext4 /boot and ROOT_PART becomes
Btrfs with root, home and var subvolumes. No partition table, other
partition, firmware or U-Boot environment is changed.

Run as root on a Linux maintenance host where neither target is mounted.
With --check, every input and target guard runs and the image is hash- and
xz-verified, but nothing is written. Without --check, both targets are
reformatted and repopulated.

Paths:
  WHOLE_DISK            a /dev/disk/by-id/ whole-disk path
  BOOT_PART, ROOT_PART  WHOLE_DISK-partN paths on that disk; boot at least
                        2 GiB, root at least 32 GiB

Required environment (pass through sudo as env NAME=VALUE ...):
  K3_NVME_EXPECTED_MODEL       exact whole-disk model
  K3_NVME_EXPECTED_SERIAL      exact whole-disk serial
  K3_NVME_EXPECTED_SIZE_BYTES  exact whole-disk size in bytes
  K3_F45_EXPECTED_BOOT         "empty", or BOOT_PART's current ext4 UUID
  K3_F45_EXPECTED_ROOT         "empty", or ROOT_PART's current single-device
                               Btrfs UUID
  K3_F45_FWUPD                 "mask" or "keep": mask writes systemd masks
                               for fwupd.service and fwupd-refresh.timer in
                               the new F45 root only
  K3_F45_ACK_FORMAT            YES-FORMAT-F45-VOLUMES (not used by --check)

Optional:
  K3_F45_WORK_PARENT           directory for the decompressed raw image
                               (default /var/tmp); needs its size + 1 GiB

Any other existing signature, an identity or UUID mismatch, a mount, swap
use, holders or child devices refuses before formatting. The image must be
the file pinned in the adjacent ../files/sources.lock.json. After copying,
the helper rewrites only the new F45 fstab, BLS and kernel command-line root
references, extracts the raw bootstrap Image, and creates the separately
named two-property bootstrap DTB. It never reboots or writes U-Boot state.
EOF
}

fail()
{
	printf 'error: %s\n' "$*" >&2
	exit 1
}

check_only=0
if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	usage
	exit 0
fi
if [[ ${1:-} == --check ]]; then
	check_only=1
	shift
fi
[[ $# -eq 4 ]] || { usage >&2; exit 2; }

image_arg=$1
disk_stable=$2
boot_stable=$3
root_stable=$4
for value in "$image_arg" "$disk_stable" "$boot_stable" "$root_stable"; do
	[[ -n $value && $value != *$'\n'* && $value != *$'\r'* ]] ||
		fail "Empty or multi-line argument."
done

: "${K3_NVME_EXPECTED_MODEL:?Set the exact whole-disk model}"
: "${K3_NVME_EXPECTED_SERIAL:?Set the exact whole-disk serial}"
: "${K3_NVME_EXPECTED_SIZE_BYTES:?Set the exact whole-disk size in bytes}"
: "${K3_F45_EXPECTED_BOOT:?Set empty or the current boot filesystem UUID}"
: "${K3_F45_EXPECTED_ROOT:?Set empty or the current root filesystem UUID}"
: "${K3_F45_FWUPD:?Choose mask or keep for fwupd in the new F45 root}"
[[ $K3_NVME_EXPECTED_SIZE_BYTES =~ ^[1-9][0-9]*$ ]] ||
	fail "K3_NVME_EXPECTED_SIZE_BYTES must be a decimal byte count."
uuid_re='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
for expected in "$K3_F45_EXPECTED_BOOT" "$K3_F45_EXPECTED_ROOT"; do
	[[ $expected == empty || $expected =~ $uuid_re ]] ||
		fail "Expected target content must be empty or a lowercase filesystem UUID."
done
case $K3_F45_FWUPD in
mask|keep) ;;
*) fail "K3_F45_FWUPD must be mask or keep." ;;
esac
if [[ $check_only -eq 0 && ${K3_F45_ACK_FORMAT:-} != "$ACK" ]]; then
	fail "Formatting requires K3_F45_ACK_FORMAT=$ACK."
fi

case $disk_stable in
/dev/disk/by-id/*-part[0-9]*)
	fail "WHOLE_DISK must be a whole disk, not a partition."
	;;
/dev/disk/by-id/?*) ;;
*)
	fail "WHOLE_DISK must be a /dev/disk/by-id/ path."
	;;
esac
[[ ${disk_stable#/dev/disk/by-id/} != */* ]] ||
	fail "WHOLE_DISK must name a /dev/disk/by-id/ entry directly."
for path in "$boot_stable" "$root_stable"; do
	number=${path#"$disk_stable"-part}
	[[ $path == "$disk_stable"-part* && $number =~ ^[1-9][0-9]*$ ]] ||
		fail "BOOT_PART and ROOT_PART must be WHOLE_DISK-partN paths."
done
[[ $boot_stable != "$root_stable" ]] ||
	fail "BOOT_PART and ROOT_PART must differ."

[[ $EUID -eq 0 ]] ||
	fail "Run as root (see --help); --check also needs root to probe devices."

export LC_ALL=C
umask 022
for tool in awk basename blkid btrfs df dirname dtc fdtget fdtput findmnt \
	grep losetup lsblk mkdir mkfs.btrfs mkfs.ext4 mktemp mount mountpoint \
	python3 readlink rm rsync sed sha256sum stat swapon sync systemctl umount \
	udevadm wc xz zstd; do
	command -v "$tool" >/dev/null ||
		fail "Required command not found: $tool"
done

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
verifier=$script_dir/verify-f45-bundle.py
extractor=$script_dir/extract-riscv-zboot.sh
dtb_helper=$script_dir/make-bootstrap-dtb.sh
for file in "$verifier" "$extractor" "$dtb_helper"; do
	[[ -f $file && ! -L $file ]] ||
		fail "Missing regular companion helper: $file"
done
[[ -x $extractor && -x $dtb_helper ]] ||
	fail "Companion shell helpers must be executable."

image_record=$(python3 -I -B "$verifier" image)
IFS=$'\t' read -r image_sha256 image_filename boot_release <<< "$image_record"
[[ $image_sha256 =~ ^[0-9a-f]{64}$ && -n $image_filename && -n $boot_release ]] ||
	fail "Invalid image record in the public lock."
[[ -f $image_arg && ! -L $image_arg && -r $image_arg ]] ||
	fail "IMAGE must be a readable regular non-symlink file."
image=$(readlink -e -- "$image_arg")
[[ $(basename -- "$image") == "$image_filename" ]] ||
	fail "IMAGE must be the pinned $image_filename."

disk=$(readlink -e -- "$disk_stable") || fail "Cannot resolve WHOLE_DISK."
boot=$(readlink -e -- "$boot_stable") || fail "Cannot resolve BOOT_PART."
root=$(readlink -e -- "$root_stable") || fail "Cannot resolve ROOT_PART."
[[ -b $disk && -b $boot && -b $root ]] ||
	fail "Disk and partition paths must resolve to block devices."
[[ $boot != "$root" ]] ||
	fail "BOOT_PART and ROOT_PART resolve to the same device."
disk_name=$(basename -- "$disk")

trim()
{
	sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

check_disk()
{
	local model serial size
	[[ $(lsblk -dnro TYPE "$disk") == disk ]] ||
		fail "WHOLE_DISK is not a whole disk."
	model=$(lsblk -dn -o MODEL "$disk" | trim)
	serial=$(lsblk -dn -o SERIAL "$disk" | trim)
	size=$(lsblk -dnb -o SIZE "$disk" | trim)
	[[ -n $model && $model == "$K3_NVME_EXPECTED_MODEL" ]] ||
		fail "Whole-disk model differs from K3_NVME_EXPECTED_MODEL."
	[[ -n $serial && $serial == "$K3_NVME_EXPECTED_SERIAL" ]] ||
		fail "Whole-disk serial differs from K3_NVME_EXPECTED_SERIAL."
	[[ $size == "$K3_NVME_EXPECTED_SIZE_BYTES" ]] ||
		fail "Whole-disk size differs from K3_NVME_EXPECTED_SIZE_BYTES."
}

check_target()
{
	local label=$1 device=$2 stable=$3 expected=$4 allowed=$5 minimum=$6
	local name number size probe status type uuid devices
	name=$(basename -- "$device")
	[[ $(lsblk -dnro TYPE "$device") == part ]] ||
		fail "The $label target is not a partition."
	[[ $(lsblk -dnro PKNAME "$device") == "$disk_name" ]] ||
		fail "The $label target is not on WHOLE_DISK."
	number=$(lsblk -dnro PARTN "$device")
	[[ $number == "${stable##*-part}" ]] ||
		fail "The $label partition number differs from its stable path."
	size=$(lsblk -dnbro SIZE "$device")
	if [[ ! $size =~ ^[0-9]+$ ]] || (( size < minimum )); then
		fail "The $label target is smaller than required."
	fi
	[[ $(lsblk -nro NAME "$device" | wc -l) -eq 1 ]] ||
		fail "The $label target has child devices."
	if compgen -G "/sys/class/block/$name/holders/*" >/dev/null; then
		fail "The $label target has holders."
	fi
	[[ -z $(findmnt -rn -S "$device" -o TARGET) ]] ||
		fail "The $label target is mounted."
	if swapon --noheadings --raw --show=NAME | grep -Fxq -- "$device"; then
		fail "The $label target is active swap."
	fi
	if probe=$(blkid -p --no-part-details -o export -- "$device" 2>/dev/null); then
		status=0
	else
		status=$?
	fi
	case $status in
	0)
		type=$(sed -n 's/^TYPE=//p' <<< "$probe")
		uuid=$(sed -n 's/^UUID=//p' <<< "$probe")
		[[ $type == "$allowed" ]] ||
			fail "The $label target has unsupported existing content: ${type:-unknown}."
		[[ -n $uuid && $uuid == "$expected" ]] ||
			fail "The $label target UUID differs from K3_F45_EXPECTED_${label^^}."
		[[ -z $(findmnt -rn -S "UUID=$uuid" -o TARGET) ]] ||
			fail "A filesystem with the $label target UUID is mounted."
		if [[ $allowed == btrfs ]]; then
			devices=$(btrfs filesystem show --raw "$uuid" |
				awk '/Total devices/ {print $3}')
			[[ $devices == 1 ]] ||
				fail "The root target is not a single-device Btrfs filesystem."
		fi
		;;
	2)
		[[ $expected == empty ]] ||
			fail "The $label target has no filesystem; its expected value must be empty."
		;;
	*)
		fail "The $label target probe was ambiguous or failed (blkid status $status)."
		;;
	esac
}

check_targets()
{
	check_disk
	check_target boot "$boot" "$boot_stable" "$K3_F45_EXPECTED_BOOT" ext4 \
		$((2 * 1024 * 1024 * 1024))
	check_target root "$root" "$root_stable" "$K3_F45_EXPECTED_ROOT" btrfs \
		$((32 * 1024 * 1024 * 1024))
}

check_targets
boot_number=$(lsblk -dnro PARTN "$boot")
root_number=$(lsblk -dnro PARTN "$root")

actual_hash=$(sha256sum -- "$image")
actual_hash=${actual_hash%% *}
[[ $actual_hash == "$image_sha256" ]] ||
	fail "Fedora image SHA-256 differs from the public lock."
xz --test -- "$image"
raw_bytes=$(xz --robot --list -- "$image" | awk -F '\t' '$1 == "totals" {print $5}')
[[ $raw_bytes =~ ^[1-9][0-9]*$ ]] ||
	fail "Cannot determine the decompressed image size."
work_parent=${K3_F45_WORK_PARENT:-/var/tmp}
[[ -d $work_parent && ! -L $work_parent ]] ||
	fail "K3_F45_WORK_PARENT must be an existing real directory."
work_parent=$(readlink -e -- "$work_parent")
available=$(df -PB1 -- "$work_parent" | awk 'NR == 2 {print $4}')
if [[ ! $available =~ ^[0-9]+$ ]] ||
	(( available <= raw_bytes + 1024 * 1024 * 1024 )); then
	fail "Insufficient space below $work_parent for the decompressed image."
fi

cat <<EOF
Checked $disk_stable:
  boot target: partition $boot_number, current ${K3_F45_EXPECTED_BOOT}
  root target: partition $root_number, current ${K3_F45_EXPECTED_ROOT}
Image $image_filename matches the public lock; raw size $raw_bytes bytes.
fwupd in the new F45 root: $K3_F45_FWUPD
EOF
if [[ $check_only -eq 1 ]]; then
	printf 'Check only: nothing was written.\n'
	exit 0
fi

work_dir=$(mktemp -d "$work_parent/k3-f45-populate.XXXXXX")
raw=$work_dir/f45.raw
source_boot=$work_dir/source-boot
source_root=$work_dir/source-root
target_boot=$work_dir/target-boot
target_root=$work_dir/target-root
loop=
mounted=()

cleanup()
{
	local status=$?
	local cleanup_failed=0
	local mount_path

	trap - EXIT
	sync || true
	for ((index=${#mounted[@]} - 1; index >= 0; index--)); do
		mount_path=${mounted[$index]}
		if mountpoint -q "$mount_path"; then
			umount "$mount_path" 2>/dev/null || true
		fi
		if mountpoint -q "$mount_path"; then
			printf 'error: cleanup could not unmount %s; preserving %s\n' \
				"$mount_path" "$work_dir" >&2
			cleanup_failed=1
		fi
	done
	if [[ $cleanup_failed -eq 0 && -n ${loop:-} ]]; then
		losetup -d "$loop" 2>/dev/null || true
		if losetup "$loop" >/dev/null 2>&1; then
			printf 'error: cleanup could not detach %s; preserving %s\n' \
				"$loop" "$work_dir" >&2
			cleanup_failed=1
		fi
	fi
	if [[ $cleanup_failed -eq 0 ]]; then
		rm -rf -- "$work_dir"
	elif [[ $status -eq 0 ]]; then
		status=1
	fi
	exit "$status"
}
trap cleanup EXIT

xz --decompress --stdout -- "$image" > "$raw"
loop=$(losetup --find --show --partscan --read-only "$raw")
udevadm settle
[[ -b ${loop}p2 && -b ${loop}p3 ]] ||
	fail "Source image partitions 2 and 3 are unavailable."
[[ $(blkid -p -s TYPE -o value "${loop}p2") == ext4 ]] ||
	fail "Source image partition 2 is not ext4."
[[ $(blkid -p -s TYPE -o value "${loop}p3") == btrfs ]] ||
	fail "Source image partition 3 is not Btrfs."

# Recheck immediately before the destructive step.
check_targets
mkfs.ext4 -F -L F45BOOT "$boot"
mkfs.btrfs -f -L fedora45 "$root"

mkdir "$source_boot" "$source_root" "$target_boot" "$target_root"
mount -o ro,noload "${loop}p2" "$source_boot"
mounted+=("$source_boot")
mount -o ro,rescue=nologreplay,subvolid=5 "${loop}p3" "$source_root"
mounted+=("$source_root")
mount "$boot" "$target_boot"
mounted+=("$target_boot")
mount -o subvolid=5 "$root" "$target_root"
mounted+=("$target_root")

for subvolume in root home var; do
	[[ -d $source_root/$subvolume ]] ||
		fail "Source image is missing Btrfs subvolume $subvolume."
	btrfs subvolume create "$target_root/$subvolume"
	rsync -aHAXS --numeric-ids -- "$source_root/$subvolume/" \
		"$target_root/$subvolume/"
done
rsync -aHAXS --numeric-ids -- "$source_boot/" "$target_boot/"

root_uuid=$(blkid -p -s UUID -o value "$root")
boot_uuid=$(blkid -p -s UUID -o value "$boot")
[[ $root_uuid =~ $uuid_re && $boot_uuid =~ $uuid_re ]] ||
	fail "Unable to read the new filesystem UUIDs."

image_root_uuid=$(blkid -p -s UUID -o value "${loop}p3")
[[ $image_root_uuid =~ $uuid_re ]] ||
	fail "Unable to read the source image root UUID."

# Replace only root references, preserving each file's mode, owner and label.
python3 -I -B - "$target_root/root" "$target_boot" "$root_uuid" "$boot_uuid" \
	"$image_root_uuid" <<'PY'
import errno
import os
import pathlib
import re
import stat
import sys

root_dir, boot_dir = map(pathlib.Path, sys.argv[1:3])
root_uuid, boot_uuid, image_root_uuid = sys.argv[3:6]
ROOT_OPTION = re.compile(r"(?<!\S)root=UUID=[^\s]+")


def selinux_label(path):
    try:
        return os.getxattr(path, "security.selinux", follow_symlinks=False)
    except OSError as exc:
        if exc.errno in (errno.ENODATA, errno.ENOTSUP, errno.EOPNOTSUPP):
            return None
        raise


def replace_preserving(path, text):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode):
        raise SystemExit(f"{path}: not a regular file")
    label = selinux_label(path)
    temporary = path.with_name(path.name + ".f45-new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fchown(stream.fileno(), info.st_uid, info.st_gid)
            os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
            if label is not None:
                os.setxattr(stream.fileno(), "security.selinux", label)
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


rewritten = []
fstab = root_dir / "etc" / "fstab"
replace_preserving(fstab, (
    f"UUID={root_uuid} / btrfs "
    "x-systemd.growfs,compress=zstd:1,defaults,subvol=root 0 1\n"
    f"UUID={boot_uuid} /boot ext4 defaults 0 0\n"
    f"UUID={root_uuid} /home btrfs "
    "x-systemd.growfs,compress=zstd:1,subvol=home 0 0\n"
    f"UUID={root_uuid} /var btrfs "
    "x-systemd.growfs,compress=zstd:1,subvol=var 0 0\n"
))
rewritten.append(fstab)

entries = sorted((boot_dir / "loader" / "entries").glob("*.conf"))
if not entries:
    raise SystemExit("no BLS entries found")
for path in entries:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    options = 0
    for index, line in enumerate(lines):
        if line.startswith("options "):
            lines[index], count = ROOT_OPTION.subn(f"root=UUID={root_uuid}", line)
            if count != 1:
                raise SystemExit(f"{path}: expected one root=UUID option")
            options += 1
    if options != 1:
        raise SystemExit(f"{path}: expected exactly one options line")
    replace_preserving(path, "".join(lines))
    rewritten.append(path)

cmdline = root_dir / "etc" / "kernel" / "cmdline"
if os.path.lexists(cmdline):
    text, count = ROOT_OPTION.subn(
        f"root=UUID={root_uuid}", cmdline.read_text(encoding="utf-8"),
    )
    if count != 1:
        raise SystemExit(f"{cmdline}: expected one root=UUID option")
    replace_preserving(cmdline, text)
    rewritten.append(cmdline)

for path in rewritten:
    if image_root_uuid in path.read_text(encoding="utf-8"):
        raise SystemExit(f"{path}: still references the source image root")
print("Rewrote root references in", len(rewritten), "files.")
PY

if [[ $K3_F45_FWUPD == mask ]]; then
	systemctl --root="$target_root/root" mask fwupd.service fwupd-refresh.timer
	for unit in fwupd.service fwupd-refresh.timer; do
		[[ $(readlink -- "$target_root/root/etc/systemd/system/$unit") == /dev/null ]] ||
			fail "The fwupd mask was not written for $unit."
	done
fi

vmlinuz=$target_boot/vmlinuz-$boot_release
raw_image=$target_boot/Image-$boot_release
initramfs=$target_boot/initramfs-$boot_release.img
packaged_dtb=$target_boot/dtb-$boot_release/spacemit/k3-com260-ifx.dtb
bootstrap_dtb=$target_boot/dtb-$boot_release/spacemit/k3-com260-bootstrap.dtb
for file in "$vmlinuz" "$initramfs" "$packaged_dtb"; do
	[[ -f $file && ! -L $file && -s $file ]] ||
		fail "The copied image is missing $(basename -- "$file")."
done
"$extractor" "$vmlinuz" "$raw_image"
"$dtb_helper" "$packaged_dtb" "$bootstrap_dtb"

record=$target_root/root/root/k3-f45-volume-install.txt
[[ ! -e $record && ! -L $record ]] ||
	fail "Unexpected install record already exists in the new root."
cat > "$record" <<EOF
Fedora image: $image_filename
Fedora image SHA-256: $image_sha256
Bootstrap kernel: $boot_release
F45 boot partition number: $boot_number
F45 boot UUID: $boot_uuid
F45 root partition number: $root_number
F45 root UUID: $root_uuid
fwupd in this root: $K3_F45_FWUPD
EOF
chmod 0600 "$record"

sync
cat <<EOF

Fedora 45 volumes populated. Nothing was rebooted and no U-Boot state changed.
U-Boot boot partition: nvme 0:$boot_number (confirm nvme scan sees only this NVMe)
F45 /boot UUID: $boot_uuid
F45 root UUID:  $root_uuid  (pass as root=UUID=..., rootflags=subvol=root)
Load sizes for this boot set:
EOF
for file in "$bootstrap_dtb" "$raw_image" "$initramfs"; do
	bytes=$(stat -c %s -- "$file")
	printf '  %-60s %12s bytes  0x%x\n' "$(basename -- "$file")" "$bytes" "$bytes"
done
sha256sum -- "$bootstrap_dtb" "$raw_image" "$initramfs"
