#!/usr/bin/env bash
set -euo pipefail
set -x

usage()
{
	cat <<'EOF'
Usage:
  transfer-omni-baseline-to-k3.sh [STAGE_DIR] [SSH_TARGET] [EXPECTED_SUFFIX]

Validate and transfer a staged Omni kernel to the K3. The script copies the
stage and guarded manual installer, verifies key hashes remotely, and leaves
the kernel ready for a local sudo install. It does not install or boot it.

This exported copy requires STAGE_DIR and SSH_TARGET to be supplied.
SSH_TARGET must use the image-defined fedora account, for example:
  fedora@k3-host.example

Default:
  EXPECTED_SUFFIX:
    k3-kvm-host-a1

Example:
  transfer-omni-baseline-to-k3.sh \
    "$HOME/k3-kvm-host-a1/stage" \
    fedora@k3-host.example \
    k3-kvm-host-a1
EOF
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	usage
	exit 0
fi
if [[ $# -lt 2 || $# -gt 3 ]]; then
	usage >&2
	exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
stage_arg=$1
ssh_target=$2
expected_suffix=${3:-k3-kvm-host-a1}
installer=$script_dir/k3-install-manual-kernel.sh

case "$ssh_target" in
	fedora@*)
		ssh_host=${ssh_target#fedora@}
		;;
	*)
		echo "SSH target must use the Fedora account: $ssh_target" >&2
		exit 1
		;;
esac

case "$ssh_host" in
	*[!A-Za-z0-9._:-]*|'')
		echo "Unsafe or empty SSH hostname: $ssh_host" >&2
		exit 1
		;;
esac

case "$expected_suffix" in
	*[!A-Za-z0-9._+-]*|'')
		echo "Unsafe or empty expected suffix: $expected_suffix" >&2
		exit 1
		;;
esac

stage=$(realpath "$stage_arg")
release=$(cat "$stage/kernelrelease")
remote_stage=/home/fedora/kernel-stage-$expected_suffix
remote_partial=$remote_stage.partial
manifest=$(mktemp)
partial_created=0
transfer_complete=0

cleanup()
{
	rm -f "$manifest"
	if [[ $partial_created -eq 1 && $transfer_complete -eq 0 ]]; then
		cat >&2 <<EOF
Transfer did not complete.

A partial directory may remain on K3:
  $remote_partial

After inspecting it, remove that exact directory before retrying.
EOF
	fi
}

trap cleanup EXIT

case "$release" in
	*[!A-Za-z0-9._+-]*|'')
		echo "Unsafe or empty staged kernel release: $release" >&2
		exit 1
		;;
esac

case "$release" in
	*-"$expected_suffix") ;;
	*)
		echo "Unexpected staged kernel release: $release" >&2
		exit 1
		;;
esac

test -x "$installer"
test -d "$stage/lib/modules/$release"
test -e "$stage/boot/Image-$release"
test -e "$stage/boot/config-$release"
test -e "$stage/boot/System.map-$release"
test -e "$stage/boot/dtb-$release/spacemit/k3-com260-ifx.dtb"
test -e "$stage/lib/modules/$release/modules.order"
test -e "$stage/lib/modules/$release/modules.dep"

(
	cd "$stage"
	sha256sum \
		kernelrelease \
		"boot/Image-$release" \
		"boot/config-$release" \
		"boot/System.map-$release" \
		"boot/dtb-$release/spacemit/k3-com260-ifx.dtb" \
		"lib/modules/$release/modules.order" \
		"lib/modules/$release/modules.builtin" \
		"lib/modules/$release/modules.dep" \
		"lib/modules/$release/modules.alias"
) > "$manifest"

installer_hash=$(sha256sum "$installer" | cut -d' ' -f1)
printf '%s  %s\n' \
	"$installer_hash" \
	k3-install-manual-kernel.sh \
	>> "$manifest"

stage_bytes=$(du -sb "$stage" | awk '{print $1}')
required_bytes=$((stage_bytes + 100 * 1024 * 1024))
remote_available=$(ssh \
	-o BatchMode=yes \
	-o ConnectTimeout=10 \
	"$ssh_target" \
	"set -eu
	test \"\$(id -un)\" = fedora
	command -v rsync >/dev/null
	command -v sha256sum >/dev/null
	test ! -e '$remote_stage' && test ! -L '$remote_stage'
	test ! -e '$remote_partial' && test ! -L '$remote_partial'
	df -PB1 /home/fedora | awk 'NR == 2 { print \$4 }'")

test "$remote_available" -gt "$required_bytes"

partial_created=1
ssh \
	-o BatchMode=yes \
	-o ConnectTimeout=10 \
	"$ssh_target" \
	"set -eu
	mkdir -m 0755 '$remote_partial'"

rsync \
	--archive \
	--human-readable \
	--itemize-changes \
	--info=progress2 \
	-e 'ssh -o BatchMode=yes -o ConnectTimeout=10' \
	"$stage/" \
	"$ssh_target:$remote_partial/"

rsync \
	--archive \
	--human-readable \
	--itemize-changes \
	-e 'ssh -o BatchMode=yes -o ConnectTimeout=10' \
	"$installer" \
	"$ssh_target:$remote_partial/k3-install-manual-kernel.sh"

rsync \
	--archive \
	--human-readable \
	--itemize-changes \
	-e 'ssh -o BatchMode=yes -o ConnectTimeout=10' \
	"$manifest" \
	"$ssh_target:$remote_partial/TRANSFER-SHA256.txt"

ssh \
	-o BatchMode=yes \
	-o ConnectTimeout=10 \
	"$ssh_target" \
	"set -eu
	cd '$remote_partial'
	test \"\$(cat kernelrelease)\" = '$release'
	test -x k3-install-manual-kernel.sh
	sha256sum -c TRANSFER-SHA256.txt
	cd /home/fedora
	test ! -e '$remote_stage' && test ! -L '$remote_stage'
	mv -nT -- '$remote_partial' '$remote_stage'
	test ! -e '$remote_partial' && test ! -L '$remote_partial'"

transfer_complete=1

cat <<EOF
Transfer complete.

K3 stage:
  $remote_stage

Kernel release:
  $release

Log in to the K3 and install manually:

  ssh -t $ssh_target
  sudo $remote_stage/k3-install-manual-kernel.sh \\
    $remote_stage \\
    $expected_suffix

The transfer script did not install the kernel or change the boot path.
EOF
