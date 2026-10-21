#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -Eeuo pipefail
set -x

usage()
{
	cat <<'EOF'
Usage: transfer-f45-copr-kernel-to-k3.sh [--build BUILD_ID] BUNDLE_DIR SSH_TARGET

Verify the exact five binary RPMs of one pinned COPR build against the
adjacent public lock, then copy them and the lock, verifier, extractor,
bootstrap-DTB helper and installer to the fedora account. BUILD_ID defaults
to 11035571, the first 7.2.8 update; 11177969 is the 7.3.0 fan-control
upgrade. SSH_TARGET must be fedora@HOST, using a hostname, ssh_config alias
or IPv4 address, not an IPv6 literal. HOST must already have a trusted SSH
host key. Normal SSH authentication is required; host-key checks are not
bypassed.

Remote layout: ~/f45-copr-kernel-BUILD_ID/{rpms,files,scripts}/
The final name and its .partial directory must not exist. Transfer uses
rsync over SSH, rechecks the remote RPM bytes/metadata for the same build,
then renames the complete directory. No sudo, installation, reboot or
boot-state change is performed. An interrupted remote .partial directory is
left for inspection.
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
default_build=11035571
build=$default_build
if [[ ${1:-} == --build ]]; then
	[[ $# -ge 2 ]] || { usage >&2; exit 2; }
	build=$2
	shift 2
fi
[[ $# -eq 2 ]] || { usage >&2; exit 2; }
[[ $build =~ ^[1-9][0-9]{0,15}$ ]] ||
	fail "BUILD_ID must be a decimal COPR build ID."

for tool in awk dirname du python3 rpm rsync ssh; do
	command -v "$tool" >/dev/null ||
		fail "Required command not found: $tool"
done
case "$2" in
fedora@*) ssh_host=${2#fedora@} ;;
*) fail "SSH_TARGET must use the fedora account." ;;
esac
[[ $ssh_host =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] ||
	fail "SSH host must be a hostname or IPv4 address, without a port or IPv6 literal."
ssh_target=$2
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
verifier=$script_dir/verify-f45-bundle.py
installer=$script_dir/k3-install-rpm-kernel.sh
extractor=$script_dir/extract-riscv-zboot.sh
dtb_helper=$script_dir/make-bootstrap-dtb.sh
lock=$script_dir/../files/sources.lock.json
for file in "$verifier" "$installer" "$extractor" "$dtb_helper" "$lock"; do
	test -f "$file" && test ! -L "$file" ||
		fail "Missing regular transfer input."
done
test -x "$installer" && test -x "$extractor" && test -x "$dtb_helper" ||
	fail "Installer, extractor and DTB helper must be executable."
python3 -I -B "$verifier" --build "$build" verify "$1"
bundle=$(cd -- "$1" && pwd -P)
bundle_bytes=$(du -sb -- "$bundle" | awk '{print $1}')
required_bytes=$((bundle_bytes + 100 * 1024 * 1024))
ssh_options=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes)
remote_name=f45-copr-kernel-$build
remote_partial=$remote_name.partial

# Run a quoted remote script after a preamble naming the validated build.
remote()
{
	{
		printf 'build=%s\nbundle=%s\n' "$build" "$remote_name"
		cat
	} | ssh "${ssh_options[@]}" "$ssh_target" 'sh -s'
}

remote_available=$(remote <<'REMOTE'
set -eu
test "$(id -un)" = fedora
test -d "$HOME"
test ! -L "$HOME"
cd -- "$HOME"
for tool in bash python3 rpm rsync df awk; do
	command -v "$tool" >/dev/null
done
for target in "$bundle" "$bundle.partial"; do
	if test -e "$target" || test -L "$target"; then
		printf 'error: Remote bundle path already exists: %s\n' "$target" >&2
		exit 1
	fi
done
df -PB1 . | awk 'NR == 2 { print $4 }'
REMOTE
)
[[ $remote_available =~ ^[0-9]+$ ]] ||
	fail "Remote free-space result is not numeric."
test "$remote_available" -gt "$required_bytes" ||
	fail "Insufficient remote space."

partial_created=0
transfer_complete=0
cleanup()
{
	if [[ $partial_created -eq 1 && $transfer_complete -eq 0 ]]; then
		printf 'error: Inspect ~/%s before retrying.\n' "$remote_partial" >&2
	fi
}
trap cleanup EXIT
remote <<'REMOTE'
set -eu
test "$(id -un)" = fedora
cd -- "$HOME"
for target in "$bundle" "$bundle.partial"; do
	if test -e "$target" || test -L "$target"; then
		printf 'error: Remote bundle path already exists: %s\n' "$target" >&2
		exit 1
	fi
done
mkdir -m 0700 -- "$bundle.partial"
mkdir -m 0700 -- "$bundle.partial/rpms" \
	"$bundle.partial/files" "$bundle.partial/scripts"
REMOTE
partial_created=1

rsync_options=(
	--archive --protect-args
	--rsync-path="cd \"\$HOME\" && exec rsync"
	-e 'ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes'
)
rsync "${rsync_options[@]}" "$bundle/" "$ssh_target:$remote_partial/rpms/"
rsync "${rsync_options[@]}" "$verifier" "$installer" "$extractor" "$dtb_helper" \
	"$ssh_target:$remote_partial/scripts/"
rsync "${rsync_options[@]}" "$lock" \
	"$ssh_target:$remote_partial/files/sources.lock.json"

remote <<'REMOTE'
set -eu
test "$(id -un)" = fedora
cd -- "$HOME"
cd -- "$bundle.partial"
test -x scripts/k3-install-rpm-kernel.sh
test ! -L scripts/k3-install-rpm-kernel.sh
test -x scripts/extract-riscv-zboot.sh
test ! -L scripts/extract-riscv-zboot.sh
test -x scripts/make-bootstrap-dtb.sh
test ! -L scripts/make-bootstrap-dtb.sh
python3 -I -B scripts/verify-f45-bundle.py --build "$build" verify rpms
cd ..
if test -e "$bundle" || test -L "$bundle"; then
	printf 'error: Remote final bundle appeared during transfer.\n' >&2
	exit 1
fi
mv -nT -- "$bundle.partial" "$bundle"
test ! -e "$bundle.partial"
test ! -L "$bundle.partial"
REMOTE
transfer_complete=1
install_build=
if [[ $build != "$default_build" ]]; then
	install_build="--build $build "
fi
cat <<EOF
Transfer complete: ~/$remote_name/

After reviewing the recipe, install manually on the K3 with authorized sudo:
  sudo "\$HOME/$remote_name/scripts/k3-install-rpm-kernel.sh" \\
    $install_build"\$HOME/$remote_name/rpms"

This transfer did not install or boot the kernel.
EOF
