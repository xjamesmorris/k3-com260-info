#!/usr/bin/env bash
set -euo pipefail
set -x

usage()
{
	cat <<'EOF'
Usage: k3-install-manual-kernel.sh STAGE_DIR EXPECTED_SUFFIX

Install one manually staged kernel alongside the running K3 kernel without
changing the RPM database or the saved /boot/dtb symlink.

Examples:
  sudo ./k3-install-manual-kernel.sh \
    /home/fedora/kernel-stage-k3-dldo4-base1 \
    k3-dldo4-base1

  sudo ./k3-install-manual-kernel.sh \
    /home/fedora/kernel-stage-k3-dldo4-test1 \
    k3-dldo4-test1
EOF
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	usage
	exit 0
fi

if [[ $# -ne 2 ]]; then
	usage >&2
	exit 2
fi

if [[ $EUID -ne 0 ]]; then
	echo "Run this script with sudo on the K3." >&2
	exit 1
fi

stage=$(realpath "$1")
expected_suffix=$2
oldrel=$(uname -r)
newrel=$(cat "$stage/kernelrelease")

test -n "$expected_suffix"
test "$newrel" != "$oldrel"
test -L /boot/dtb
old_dtb_target=$(readlink /boot/dtb)
case "$old_dtb_target" in
	dtb-*) ;;
	*)
		echo "Unexpected saved DTB link target: $old_dtb_target" >&2
		exit 1
		;;
esac
case "$old_dtb_target" in
	*[!A-Za-z0-9._+-]*)
		echo "Unsafe saved DTB link target: $old_dtb_target" >&2
		exit 1
		;;
esac
test -d "/boot/$old_dtb_target"
test -e "/boot/$old_dtb_target/spacemit/k3-com260-ifx.dtb"
case "$newrel" in
	*-"$expected_suffix") ;;
	*)
		echo "Unexpected kernel release: $newrel" >&2
		exit 1
		;;
esac

test ! -e "/lib/modules/$newrel"
test ! -e "/boot/Image-$newrel"
test ! -e "/boot/initramfs-$newrel.img"
test ! -e "/boot/config-$newrel"
test ! -e "/boot/System.map-$newrel"
test ! -e "/boot/dtb-$newrel"

test -d "$stage/lib/modules/$newrel"
test -e "$stage/boot/Image-$newrel"
test -e "$stage/boot/config-$newrel"
test -e "$stage/boot/System.map-$newrel"
test -e "$stage/boot/dtb-$newrel/spacemit/k3-com260-ifx.dtb"

install -d -m 0755 \
	"/lib/modules/$newrel" \
	"/boot/dtb-$newrel/spacemit"
rsync -a --chown=root:root \
	"$stage/lib/modules/$newrel/" \
	"/lib/modules/$newrel/"
install -m 0644 "$stage/boot/Image-$newrel" "/boot/Image-$newrel"
install -m 0644 "$stage/boot/config-$newrel" "/boot/config-$newrel"
install -m 0644 "$stage/boot/System.map-$newrel" "/boot/System.map-$newrel"
install -m 0644 \
	"$stage/boot/dtb-$newrel/spacemit/k3-com260-ifx.dtb" \
	"/boot/dtb-$newrel/spacemit/k3-com260-ifx.dtb"

depmod "$newrel"
dracut --force "/boot/initramfs-$newrel.img" "$newrel"

if command -v restorecon >/dev/null; then
	restorecon -RF \
		"/lib/modules/$newrel" \
		"/boot/Image-$newrel" \
		"/boot/config-$newrel" \
		"/boot/System.map-$newrel" \
		"/boot/initramfs-$newrel.img" \
		"/boot/dtb-$newrel"
fi

test "$(readlink /boot/dtb)" = "$old_dtb_target"
sha256sum \
	"/boot/Image-$newrel" \
	"/boot/initramfs-$newrel.img" \
	"/boot/dtb-$newrel/spacemit/k3-com260-ifx.dtb"

cat <<EOF
Kernel installed alongside the running kernel.

Running kernel: $oldrel
New kernel:     $newrel
DTB link:       $(readlink /boot/dtb)

Do not run env save when testing this kernel from U-Boot.
EOF
