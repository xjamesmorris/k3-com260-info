#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -Eeuo pipefail
set -x

usage()
{
	cat <<'EOF'
Usage: k3-install-rpm-kernel.sh [--build BUILD_ID] BUNDLE_DIR

On the K3, install exactly the five binary RPMs of one pinned COPR build
alongside the running kernel. BUILD_ID defaults to 11035571 (7.2.8), which
requires the running 7.2.7 image bootstrap; 11177969 (the 7.3.0 fan-control
upgrade) requires the running 7.2.8. Verify bytes and RPM metadata against
the adjacent public ../files/sources.lock.json, not a bundle-supplied
checksum list.

Wrong, missing, extra, symlinked or unpinned inputs, a running/installed
candidate, or a host not running the build's required pinned F45 kernel are
refused before package or boot-file writes. Installation
requires root and changes the RPM database, module tree and /boot; it retains
older kernels and restores the saved /boot/dtb link, even if dnf fails.

The recorded packages reported NOKEY, not verified publisher signatures.
--nogpgcheck is used only after pinned digest and metadata checks.

After installing 11035571, the separately named k3-com260-bootstrap.dtb for
the new release is copied from the running release only if both packaged
k3-com260-ifx.dtb files are byte-identical; otherwise it is generated with
the adjacent make-bootstrap-dtb.sh when dtc, fdtget and fdtput are present.
If neither is possible the helper stops with a clear error after installing.

11177969 instead boots its packaged k3-com260-ifx.dtb, which already has the
K3 regulator settings and thermal zones: no bootstrap DTB is created and the
dtc tools are not needed. If the installed DTB differs from the SHA-256 in
the lock, the helper stops after installing; do not boot it until reviewed.
It never reboots or saves a U-Boot environment. Read the canonical
Fedora-45-Recipe before using this helper.
EOF
}

fail()
{
	printf 'error: %s\n' "$*" >&2
	exit 1
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	usage
	exit 0
fi
build=11035571
if [[ ${1:-} == --build ]]; then
	[[ $# -ge 2 ]] || { usage >&2; exit 2; }
	build=$2
	shift 2
fi
[[ $# -eq 1 ]] || { usage >&2; exit 2; }
[[ $build =~ ^[1-9][0-9]{0,15}$ ]] ||
	fail "BUILD_ID must be a decimal COPR build ID."

for tool in dirname python3 rpm uname; do
	command -v "$tool" >/dev/null ||
		fail "Required command not found: $tool"
done
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
verifier=$script_dir/verify-f45-bundle.py
extractor=$script_dir/extract-riscv-zboot.sh
dtb_helper=$script_dir/make-bootstrap-dtb.sh
test -f "$verifier" && test ! -L "$verifier" ||
	fail "Missing regular bundle verifier."
test -f "$extractor" && test ! -L "$extractor" && test -x "$extractor" ||
	fail "Missing executable regular zboot extractor."

python3 -I -B "$verifier" --build "$build" verify "$1"
newrel=$(python3 -I -B "$verifier" --build "$build" release)
dtb_record=$(python3 -I -B "$verifier" --build "$build" boot-dtb)
dtb_mode=bootstrap
boot_dtb_path=
boot_dtb_sha256=
if [[ $dtb_record != bootstrap ]]; then
	IFS=$'\t' read -r dtb_mode boot_dtb_path boot_dtb_sha256 dtb_extra \
		<<< "$dtb_record"
	[[ $dtb_mode == packaged && -z $dtb_extra &&
		$boot_dtb_path =~ ^[A-Za-z0-9_-]+/[A-Za-z0-9_-][A-Za-z0-9._-]*\.dtb$ &&
		$boot_dtb_sha256 =~ ^[0-9a-f]{64}$ ]] ||
		fail "Invalid boot-DTB record in the public lock."
fi
bundle=$(cd -- "$1" && pwd -P)
oldrel=$(uname -r)
test "$newrel" != "$oldrel" ||
	fail "The exact candidate kernel is already running."
bootstraprel=$(python3 -I -B "$verifier" bootstrap-release)
required=$(python3 -I -B "$verifier" --build "$build" requires-running)
running_ok=0
while IFS= read -r release; do
	if [[ -n $release && $release == "$oldrel" ]]; then
		running_ok=1
	fi
done <<< "$required"
if [[ $running_ok -ne 1 ]]; then
	required_label="pinned F45 kernel"
	if [[ $required == "$bootstraprel" ]]; then
		required_label="pinned F45 bootstrap"
	fi
	fail "COPR build $build requires running the $required_label ${required//$'\n'/ or }, not $oldrel; a saved F44 or other boot path is refused."
fi

names=(kernel kernel-core kernel-modules-core kernel-modules kernel-modules-extra)
binary_rpms=()
for name in "${names[@]}"; do
	if rpm -q --quiet "$name-$newrel" >/dev/null 2>&1; then
		fail "Candidate package is already installed: $name-$newrel"
	else
		status=$?
		test "$status" -eq 1 ||
			fail "Cannot query installed package state."
	fi
	binary_rpms+=("$bundle/$name-$newrel.rpm")
done
test "$(uname -m)" = riscv64 ||
	fail "Run this helper only on the documented RISC-V K3 host."
[[ $EUID -eq 0 ]] ||
	fail "Run this script with sudo on the K3 after reviewing the recipe."
for tool in cmp cp dnf dracut grep ln readlink sha256sum stat zstd; do
	command -v "$tool" >/dev/null ||
		fail "Required command not found: $tool"
done

test -d /boot && test ! -L /boot && test -L /boot/dtb ||
	fail "/boot must be a real directory with a saved dtb symlink."
old_dtb_target=$(readlink /boot/dtb)
[[ $old_dtb_target =~ ^dtb-[A-Za-z0-9._+-]+$ ]] ||
	fail "Unsafe saved DTB link target."
test -d "/boot/$old_dtb_target" && test ! -L "/boot/$old_dtb_target" ||
	fail "Saved DTB target is not a real directory."
for path in \
	"/boot/Image-$newrel" \
	"/boot/Image-$newrel.partial" \
	"/boot/Image-$newrel.payload.partial" \
	"/boot/vmlinuz-$newrel" \
	"/boot/initramfs-$newrel.img" \
	"/boot/dtb-$newrel" \
	"/lib/modules/$newrel"; do
	test ! -e "$path" && test ! -L "$path" ||
		fail "Candidate path already exists: $path"
done

restore_old_dtb_link()
{
	if [[ -e /boot/dtb && ! -L /boot/dtb ]]; then
		printf 'error: Refusing to replace a non-symlink /boot/dtb.\n' >&2
		return 1
	fi
	ln -sfnT -- "$old_dtb_target" /boot/dtb
}
trap restore_old_dtb_link EXIT
dnf \
	--disablerepo='*' --setopt=installonly_limit=0 --nogpgcheck \
	install "${binary_rpms[@]}"
restore_old_dtb_link

for name in "${names[@]}"; do
	installed=$(rpm -q --qf '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n' "$name")
	grep -Fxq "$name-$newrel" <<< "$installed" ||
		fail "Installed package identity mismatch for $name."
done
test -d "/lib/modules/$newrel" ||
	fail "Installed module directory is missing."
if ! test -e "/boot/dtb-$newrel/spacemit/k3-com260-ifx.dtb"; then
	test -f "/lib/modules/$newrel/dtb/spacemit/k3-com260-ifx.dtb" ||
		fail "Installed K3 CoM260 DTB is missing."
	test ! -e "/boot/dtb-$newrel" && test ! -L "/boot/dtb-$newrel" ||
		fail "Candidate DTB directory appeared unexpectedly."
	cp -a -- "/lib/modules/$newrel/dtb" "/boot/dtb-$newrel"
fi
if ! test -e "/boot/initramfs-$newrel.img"; then
	dracut --force "/boot/initramfs-$newrel.img" "$newrel"
fi
if test -f "/boot/vmlinuz-$newrel"; then
	vmlinuz=/boot/vmlinuz-$newrel
elif test -f "/lib/modules/$newrel/vmlinuz"; then
	vmlinuz=/lib/modules/$newrel/vmlinuz
else
	fail "Installed EFI zboot kernel is missing."
fi
"$extractor" "$vmlinuz" "/boot/Image-$newrel"

bootstrap_note=
boot_dtb_problem=
if [[ $dtb_mode == bootstrap ]]; then
	old_packaged=/boot/dtb-$oldrel/spacemit/k3-com260-ifx.dtb
	old_bootstrap=/boot/dtb-$oldrel/spacemit/k3-com260-bootstrap.dtb
	new_packaged=/boot/dtb-$newrel/spacemit/k3-com260-ifx.dtb
	new_bootstrap=/boot/dtb-$newrel/spacemit/k3-com260-bootstrap.dtb
	[[ ! -e $new_bootstrap && ! -L $new_bootstrap ]] ||
		fail "Candidate bootstrap DTB already exists: $new_bootstrap"
	dtb_tools=1
	for tool in dtc fdtget fdtput; do
		command -v "$tool" >/dev/null || dtb_tools=0
	done
	if [[ -f $old_bootstrap && ! -L $old_bootstrap && -f $old_packaged ]] &&
		cmp -s -- "$old_packaged" "$new_packaged"; then
		cp -n -- "$old_bootstrap" "$new_bootstrap"
		cmp -- "$old_bootstrap" "$new_bootstrap"
		bootstrap_note="copied from $oldrel; packaged DTBs are byte-identical"
	elif [[ -f $dtb_helper && ! -L $dtb_helper && -x $dtb_helper && $dtb_tools -eq 1 ]]; then
		"$dtb_helper" "$new_packaged" "$new_bootstrap"
		bootstrap_note="generated from the $newrel packaged DTB"
	fi
	boot_dtb_file=$new_bootstrap
else
	# This build boots its packaged DTB; never derive a bootstrap DTB from it.
	boot_dtb_file=/boot/dtb-$newrel/$boot_dtb_path
	boot_dtb_problem="is missing, a symlink or not a regular file"
	if [[ -d /boot/dtb-$newrel && ! -L /boot/dtb-$newrel &&
		! -L ${boot_dtb_file%/*} && -f $boot_dtb_file && ! -L $boot_dtb_file ]]; then
		boot_dtb_actual=$(sha256sum -- "$boot_dtb_file")
		boot_dtb_problem="differs from the SHA-256 in the public lock"
		if [[ ${boot_dtb_actual%% *} == "$boot_dtb_sha256" ]]; then
			boot_dtb_problem=
		fi
	fi
fi

if command -v restorecon >/dev/null; then
	restorecon -RF \
		"/boot/Image-$newrel" "/boot/initramfs-$newrel.img" \
		"/boot/dtb-$newrel" "/lib/modules/$newrel"
fi
test "$(readlink /boot/dtb)" = "$old_dtb_target" ||
	fail "Saved DTB symlink changed."
if [[ $dtb_mode == bootstrap ]]; then
	[[ -n $bootstrap_note ]] ||
		fail "Packages are installed, but the $newrel bootstrap DTB was not created: the packaged DTBs differ and dtc/fdtget/fdtput or make-bootstrap-dtb.sh are unavailable. Prepare it before any boot."
	sha256sum \
		"/boot/Image-$newrel" "/boot/initramfs-$newrel.img" \
		"$new_packaged" "$new_bootstrap"
	cat <<EOF
Exact COPR build $build installed alongside the running kernel.
Running kernel: $oldrel
New kernel:     $newrel
Saved DTB link: $old_dtb_target
Bootstrap DTB:  $bootstrap_note

U-Boot load sizes for $newrel:
EOF
else
	[[ -z $boot_dtb_problem ]] ||
		fail "Packages are installed, but the packaged DTB $boot_dtb_file $boot_dtb_problem (expected $boot_dtb_sha256). Do not boot $newrel until this has been reviewed."
	sha256sum \
		"/boot/Image-$newrel" "/boot/initramfs-$newrel.img" "$boot_dtb_file"
	cat <<EOF
Exact COPR build $build installed alongside the running kernel.
Running kernel: $oldrel
New kernel:     $newrel
Saved DTB link: $old_dtb_target
Boot DTB:       packaged $boot_dtb_path; matches the public lock
DTB SHA-256:    $boot_dtb_sha256

No bootstrap DTB was created. U-Boot must load the packaged DTB
dtb-$newrel/$boot_dtb_path
from the boot partition for $newrel: it already includes the K3 regulator
settings and thermal zones.

U-Boot load sizes for $newrel:
EOF
fi
for file in "$boot_dtb_file" "/boot/Image-$newrel" "/boot/initramfs-$newrel.img"; do
	bytes=$(stat -c %s -- "$file")
	printf '  %-60s %12s bytes  0x%x\n' "$(basename -- "$file")" "$bytes" "$bytes"
done
cat <<'EOF'

No reboot or saved U-Boot environment change was performed.
EOF
