#!/usr/bin/env bash
set -Eeuo pipefail
set -x

usage()
{
	cat <<'EOF'
Usage: build-k3-kvm-host.sh KERNEL_REPO [CONFIG_SEED]

Build and stage the preferred upstream-based SpacemiT K3 KVM host kernel.
KERNEL_REPO must name an explicit clean, non-bare public Linux checkout.
The helper fetches the exact pinned kvm-riscv commit, creates a detached
worktree, replays the recorded PHY, PCIe, CoM260 DTS, and dldo4 patches,
builds the kernel, and verifies the complete stage.

Environment overrides:
  OUTPUT_ROOT    New output/worktree root
  LOCAL_TAG      LOCALVERSION suffix
  JOBS           Positive parallel build count
  KVM_URL        kvm-riscv Linux Git URL
  SOURCE_BRANCH  Advertised provenance branch used only as a fetch fallback
  SOURCE_COMMIT  Required full commit ID fetched and checked out exactly
  EXPECTED_TREE  Required tree after all 14 patches

Defaults:
  CONFIG_SEED:
    ../files/kernel/config.seed relative to this script
  OUTPUT_ROOT:
    k3-kvm-host-a1 beside KERNEL_REPO
  KVM_URL:
    https://github.com/kvm-riscv/linux.git
  SOURCE_BRANCH:
    riscv_kvm_fixes
  SOURCE_COMMIT:
    a5f72fd298f6bd02e6d30599dafb43cfa16576b6
  EXPECTED_TREE:
    a5f77b5acef26d8975fe756512edbd2413fa1239
  LOCAL_TAG:
    -k3-kvm-host-a1

The source pin was the observed riscv_kvm_fixes head on September 24, 2026.
The branch is provenance, not a floating selector. If a direct object fetch
is unavailable, the advertised branch may supply the same pinned object.
The script never substitutes a newer branch head. If the pin is unavailable,
refresh SOURCE_COMMIT and EXPECTED_TREE only after review and validation.

The script does not transfer or install files, access or reboot a K3, or
modify U-Boot.
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

on_error()
{
	local status=$?

	trap - ERR
	printf 'build-k3-kvm-host.sh failed with status %d at line %s.\n' \
		"$status" "${BASH_LINENO[0]:-unknown}" >&2
	exit "$status"
}

require_command()
{
	command -v "$1" >/dev/null ||
		fail "Required command not found: $1"
}

resolve_new_path()
{
	local input=$1
	local parent
	local name

	case "$input" in
		''|*$'\n'*|*$'\r'*)
			fail "Unsafe or empty OUTPUT_ROOT."
			;;
	esac
	parent=$(dirname -- "$input")
	name=$(basename -- "$input")
	case "$name" in
		''|.|..)
			fail "Unsafe OUTPUT_ROOT basename: $name"
			;;
	esac
	parent=$(realpath -e -- "$parent") ||
		fail "OUTPUT_ROOT parent does not exist: $parent"
	printf '%s/%s\n' "$parent" "$name"
}

verify_sha256_manifest()
{
	local root=$1
	local manifest=$2
	local expected
	local recorded
	local file
	local actual
	local count=0

	test -f "$manifest" ||
		fail "Missing SHA256SUMS file: $manifest"
	while read -r expected recorded; do
		test -n "${expected:-}" || continue
		[[ $expected =~ ^[0-9a-f]{64}$ ]] ||
			fail "Malformed SHA256SUMS entry in $manifest"
		recorded=${recorded#\*}
		test -n "$recorded" ||
			fail "Missing path in SHA256SUMS entry: $manifest"
		case "$recorded" in
			.|..|/*|../*|*/../*|*/..)
				fail "SHA256SUMS path must stay below $root: $recorded"
				;;
		esac
		file=$root/$recorded
		test -f "$file" ||
			fail "SHA256SUMS entry is missing: $file"
		actual=$(sha256sum "$file")
		actual=${actual%% *}
		test "$actual" = "$expected" ||
			fail "SHA256 mismatch for $file"
		count=$((count + 1))
	done < "$manifest"
	test "$count" -gt 0 ||
		fail "Empty SHA256SUMS file: $manifest"
}

extract_dts_node()
{
	local file=$1
	local node_pattern=$2

	awk -v node_pattern="$node_pattern" '
		!printing && $0 ~ node_pattern {
			printing = 1
		}
		printing {
			print
			open_line = $0
			close_line = $0
			opens = gsub(/[{]/, "", open_line)
			closes = gsub(/[}]/, "", close_line)
			depth += opens - closes
			if (opens > 0)
				started = 1
			if (started && depth == 0)
				exit
		}
	' "$file"
}

assert_config_y()
{
	grep -Fxq "CONFIG_$1=y" "$2" ||
		fail "Required built-in setting is missing: CONFIG_$1=y"
}

assert_config_m()
{
	grep -Fxq "CONFIG_$1=m" "$2" ||
		fail "Required module setting is missing: CONFIG_$1=m"
}

assert_config_n()
{
	grep -Fxq "# CONFIG_$1 is not set" "$2" ||
		fail "Required disabled setting is missing: CONFIG_$1=n"
}

first_line()
{
	local output

	output=$("$@")
	printf '%s\n' "${output%%$'\n'*}"
}

trap on_error ERR

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	usage
	exit 0
fi
if [[ $# -lt 1 || $# -gt 2 ]]; then
	usage_error "Expected KERNEL_REPO and optional CONFIG_SEED."
fi

export LC_ALL=C
umask 022

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
patch_root=$(realpath -e -- "$script_dir/../files/kernel")
repo_arg=$1
repo=$repo_arg
repo=$(realpath -e -- "$repo") ||
	fail "Kernel repository does not exist: $repo_arg"
default_config=$patch_root/config.seed
config_seed=${2:-$default_config}
config_seed=$(realpath -e -- "$config_seed") ||
	fail "Config seed does not exist: ${2:-$default_config}"

kvm_url=${KVM_URL:-https://github.com/kvm-riscv/linux.git}
source_branch=${SOURCE_BRANCH:-riscv_kvm_fixes}
source_commit=${SOURCE_COMMIT:-a5f72fd298f6bd02e6d30599dafb43cfa16576b6}
expected_tree=${EXPECTED_TREE:-a5f77b5acef26d8975fe756512edbd2413fa1239}
local_tag=${LOCAL_TAG:--k3-kvm-host-a1}
jobs=${JOBS:-$(nproc)}
default_output=$(dirname "$repo")/k3-kvm-host-a1
output_root=$(resolve_new_path "${OUTPUT_ROOT:-$default_output}")
source_dir=$output_root/source
build_dir=$output_root/build
stage_dir=$output_root/stage
partial_stage=$output_root/stage.partial
fetch_ref=refs/k3-build/kvm-riscv/$source_branch
target_dtsi=arch/riscv/boot/dts/spacemit/k3-com260.dtsi
target_soc_dtsi=arch/riscv/boot/dts/spacemit/k3.dtsi
target_board=arch/riscv/boot/dts/spacemit/k3-com260-ifx.dts
target_dtb=spacemit/k3-com260-ifx.dtb

case "$kvm_url" in
	''|-*|*$'\n'*|*$'\r'*)
		usage_error "Unsafe or empty KVM_URL."
		;;
esac
git check-ref-format --branch "$source_branch" >/dev/null ||
	usage_error "Invalid SOURCE_BRANCH: $source_branch"
git check-ref-format "$fetch_ref" >/dev/null ||
	usage_error "SOURCE_BRANCH cannot form a private fetch ref: $source_branch"
[[ $source_commit =~ ^[0-9a-f]{40}$ ]] ||
	usage_error "SOURCE_COMMIT must be a full lowercase 40-hex commit ID."
[[ $expected_tree =~ ^[0-9a-f]{40}$ ]] ||
	usage_error "EXPECTED_TREE must be a full lowercase 40-hex tree ID."
[[ $jobs =~ ^[1-9][0-9]*$ ]] ||
	usage_error "JOBS must be a positive integer: $jobs"
case "$local_tag" in
	-*) ;;
	*)
		usage_error "LOCAL_TAG must begin with '-': $local_tag"
		;;
esac
case "${local_tag#-}" in
	''|*[!A-Za-z0-9._+-]*)
		usage_error "Unsafe LOCAL_TAG suffix: $local_tag"
		;;
esac

for tool in \
	awk \
	basename \
	clang \
	date \
	dirname \
	dtc \
	find \
	git \
	grep \
	ld.lld \
	make \
	modinfo \
	nproc \
	pahole \
	realpath \
	riscv64-linux-gnu-as \
	riscv64-linux-gnu-ld \
	sed \
	sha256sum \
	sort \
	xargs \
	llvm-ar \
	llvm-nm \
	llvm-objcopy \
	llvm-objdump \
	llvm-readelf \
	llvm-strip; do
	require_command "$tool"
done

git -C "$repo" rev-parse --git-dir >/dev/null
test "$(git -C "$repo" rev-parse --is-bare-repository)" = false ||
	fail "KERNEL_REPO must be a non-bare Git repository."
test -z "$(git -C "$repo" status --porcelain --untracked-files=normal)" ||
	fail "KERNEL_REPO is dirty: $repo"
git -C "$repo" var GIT_COMMITTER_IDENT >/dev/null ||
	fail "Git committer identity is required for git am."
test -f "$config_seed"
grep -Fxq 'CONFIG_ARCH_SPACEMIT=y' "$config_seed" ||
	fail "CONFIG_SEED is not a proven SpacemiT K3 config."
grep -Eq '^CONFIG_REGULATOR_SPACEMIT_P1=(y|m)$' "$config_seed" ||
	fail "CONFIG_SEED lacks the SpacemiT P1 regulator."

if test -e "$output_root" || test -L "$output_root"; then
	fail "OUTPUT_ROOT already exists: $output_root"
fi
if git -C "$repo" worktree list --porcelain |
	grep -Fxq "worktree $source_dir"; then
	fail "Detached source path is already a registered worktree: $source_dir"
fi

phy_dir=$patch_root/phy-bulk-v3
pcie_dir=$patch_root/pcie-v6
dts_dir=$patch_root/com260-pcie
dldo_dir=$patch_root/dldo4
dldo_patch=$dldo_dir/0001-riscv-dts-spacemit-k3-com260-keep-dldo4-enabled.patch

shopt -s nullglob
phy_patches=("$phy_dir"/000[1-5]-*.patch)
pcie_patches=("$pcie_dir"/000[1-6]-*.patch)
dts_patches=("$dts_dir"/000[1-2]-*.patch)
shopt -u nullglob

phy_names=(
	0001-phy-core-Add-phandle-device-link-helper.patch
	0002-phy-core-Add-phandle-by-index-helper.patch
	0003-phy-core-Add-bulk-data-helpers.patch
	0004-phy-core-Add-managed-bulk-data-helpers.patch
	0005-doc-phy-Document-some-bulk-helper-functions.patch
)
pcie_names=(
	0001-PCI-spacemit-k1-Add-device-data-support.patch
	0002-PCI-spacemit-k1-Add-multiple-PHY-handles-support.patch
	0003-PCI-spacemit-k1-Add-device-id-update-helper.patch
	0004-dt-bindings-PCI-snps-dw-pcie-Add-msi-parent.patch
	0005-dt-bindings-PCI-spacemit-Introduce-K3-host.patch
	0006-PCI-spacemit-k1-Add-K3-host-controller.patch
)
dts_names=(
	0001-riscv-dts-spacemit-k3-Add-PCIe-controller-nodes.patch
	0002-riscv-dts-spacemit-k3-com260-ifx-Enable-PCIe.patch
)

test "${#phy_patches[@]}" -eq "${#phy_names[@]}" ||
	fail "Expected exactly five PHY bulk v3 patches."
for index in "${!phy_names[@]}"; do
	test "$(basename -- "${phy_patches[$index]}")" = "${phy_names[$index]}" ||
		fail "Unexpected PHY bulk v3 patch set."
done
test "${#pcie_patches[@]}" -eq "${#pcie_names[@]}" ||
	fail "Expected exactly six PCIe v6 patches."
for index in "${!pcie_names[@]}"; do
	test "$(basename -- "${pcie_patches[$index]}")" = "${pcie_names[$index]}" ||
		fail "Unexpected PCIe v6 patch set."
done
test "${#dts_patches[@]}" -eq "${#dts_names[@]}" ||
	fail "Expected exactly two standalone CoM260 PCIe DTS patches."
for index in "${!dts_names[@]}"; do
	test "$(basename -- "${dts_patches[$index]}")" = "${dts_names[$index]}" ||
		fail "Unexpected standalone CoM260 PCIe DTS patch set."
done
test -f "$dldo_patch" ||
	fail "Missing dldo4 patch: $dldo_patch"

patches=(
	"${phy_patches[@]}"
	"${pcie_patches[@]}"
	"${dts_patches[@]}"
	"$dldo_patch"
)
test "${#patches[@]}" -eq 14 ||
	fail "Expected exactly 14 patches, found ${#patches[@]}."

verify_sha256_manifest "$phy_dir" "$phy_dir/SHA256SUMS"
verify_sha256_manifest "$pcie_dir" "$pcie_dir/SHA256SUMS"
verify_sha256_manifest "$dts_dir" "$dts_dir/SHA256SUMS"
verify_sha256_manifest "$dldo_dir" "$dldo_dir/SHA256SUMS"

fetch_method=exact-commit
if git -C "$repo" fetch --no-tags "$kvm_url" "$source_commit"; then
	fetched_commit=$(git -C "$repo" rev-parse 'FETCH_HEAD^{commit}') ||
		fail "Unable to resolve the directly fetched SOURCE_COMMIT."
	test "$fetched_commit" = "$source_commit" ||
		fail "Direct fetch resolved $fetched_commit, not pinned $source_commit."
else
	fetch_method="advertised $source_branch branch containing pinned commit"
	printf '%s\n' \
		"Direct SOURCE_COMMIT fetch unavailable; checking $source_branch." \
		>&2
	if ! git -C "$repo" fetch --no-tags "$kvm_url" \
		"refs/heads/$source_branch"; then
		fail "Pinned source $source_commit is unavailable from $kvm_url; refresh this stale recipe deliberately."
	fi
	advertised_commit=$(git -C "$repo" rev-parse 'FETCH_HEAD^{commit}') ||
		fail "Unable to resolve fetched provenance branch $source_branch."
	git -C "$repo" merge-base --is-ancestor \
		"$source_commit" "$advertised_commit" ||
		fail "Pinned source $source_commit is not supplied by advertised branch $source_branch; refresh this stale recipe deliberately."
	fetched_commit=$(git -C "$repo" rev-parse "$source_commit^{commit}") ||
		fail "Advertised branch $source_branch did not supply pinned source $source_commit."
	test "$fetched_commit" = "$source_commit" ||
		fail "Fetched object resolved $fetched_commit, not pinned $source_commit."
fi
git -C "$repo" update-ref "$fetch_ref" "$source_commit"
test "$(git -C "$repo" rev-parse "$fetch_ref^{commit}")" = "$source_commit" ||
	fail "Private fetch ref does not resolve to pinned source $source_commit."

mkdir "$output_root"
git -C "$repo" worktree add --detach "$source_dir" "$source_commit"

patch_metadata=$output_root/patches.txt
{
	printf 'Patch count: %d\n' "${#patches[@]}"
	printf 'PHY bulk v3 count: %d; git am mode: --no-3way\n' \
		"${#phy_patches[@]}"
	printf 'PCIe v6 count: %d; git am mode: --no-3way\n' \
		"${#pcie_patches[@]}"
	printf 'CoM260 PCIe DTS count: %d; git am mode: --3way\n' \
		"${#dts_patches[@]}"
	printf 'dldo4 count: 1; git am mode: --3way\n'
	printf '\nVerified manifests:\n'
	for manifest in \
		"$phy_dir/SHA256SUMS" \
		"$pcie_dir/SHA256SUMS" \
		"$dts_dir/SHA256SUMS" \
		"$dldo_dir/SHA256SUMS"; do
		digest=$(sha256sum "$manifest")
		digest=${digest%% *}
		printf '%s  %s\n' "$digest" "${manifest#"$patch_root"/}"
	done
	printf '\nApplication order:\n'
	patch_index=0
	for patch in "${patches[@]}"; do
		patch_index=$((patch_index + 1))
		digest=$(sha256sum "$patch")
		digest=${digest%% *}
		case "$patch_index" in
			1|2|3|4|5|6|7|8|9|10|11)
				am_mode=--no-3way
				;;
			*)
				am_mode=--3way
				;;
		esac
		printf '%02d  %-10s %s  %s\n' \
			"$patch_index" \
			"$am_mode" \
			"$digest" \
			"${patch#"$patch_root"/}"
	done
} > "$patch_metadata"

git -C "$source_dir" -c commit.gpgSign=false \
	am --no-3way "${phy_patches[@]}"
git -C "$source_dir" -c commit.gpgSign=false \
	am --no-3way "${pcie_patches[@]}"
git -C "$source_dir" -c commit.gpgSign=false \
	am --3way "${dts_patches[@]}"
git -C "$source_dir" -c commit.gpgSign=false \
	am --3way "$dldo_patch"

test "$(git -C "$source_dir" rev-list --count "$source_commit..HEAD")" -eq 14 ||
	fail "The prepared worktree does not contain exactly 14 new commits."
prepared_commit=$(git -C "$source_dir" rev-parse HEAD)
prepared_tree=$(git -C "$source_dir" rev-parse 'HEAD^{tree}')
test "$prepared_tree" = "$expected_tree" ||
	fail "Prepared tree $prepared_tree does not match $expected_tree."
git -C "$source_dir" diff --check "$source_commit..HEAD"
test -z "$(git -C "$source_dir" status --porcelain --untracked-files=normal)" ||
	fail "Prepared source worktree is dirty."

for source_file in "$target_dtsi" "$target_soc_dtsi" "$target_board"; do
	test -f "$source_dir/$source_file" ||
		fail "Prepared source is missing $source_file"
done
dldo4_source=$(extract_dts_node \
	"$source_dir/$target_dtsi" \
	'^[[:space:]]*dldo4: dldo4[[:space:]]*[{]')
test -n "$dldo4_source" ||
	fail "Unable to locate dldo4 in the prepared source."
grep -Fq 'regulator-always-on;' <<<"$dldo4_source" ||
	fail "Prepared source does not keep dldo4 always on."
grep -Fq 'regulator-boot-on;' <<<"$dldo4_source" ||
	fail "Prepared source lost dldo4 regulator-boot-on."
grep -Fq 'compatible = "spacemit,k3-pcie";' \
	"$source_dir/$target_soc_dtsi" ||
	fail "Prepared source lacks the SpacemiT K3 PCIe compatible."
pcie0_source=$(extract_dts_node \
	"$source_dir/$target_board" \
	'^[[:space:]]*&pcie0_rc[[:space:]]*[{]')
test -n "$pcie0_source" ||
	fail "Unable to locate pcie0_rc in the CoM260 board source."
grep -Eq '^[[:space:]]*status = "okay";' <<<"$pcie0_source" ||
	fail "PCIe0 is not enabled in the CoM260 board source."

mkdir "$build_dir"
cp "$config_seed" "$output_root/config-seed"
cp "$config_seed" "$build_dir/.config"
"$source_dir/scripts/config" \
	--file "$build_dir/.config" \
	--enable MODULES \
	--enable KVM \
	--enable RISCV_SBI \
	--enable RISCV_IMSIC \
	--enable RISCV_APLIC \
	--enable PCIE_SPACEMIT_K1 \
	--enable PHY_SPACEMIT_K3_COMMON_OPS \
	--enable PHY_SPACEMIT_K3_COMBO_PHY \
	--module BLK_DEV_NVME \
	--module BTRFS_FS \
	--enable VIRTIO_PCI \
	--module VIRTIO_BLK \
	--module VIRTIO_NET \
	--module VHOST \
	--module VHOST_NET \
	--module TUN \
	--module TAP \
	--enable STACKPROTECTOR_STRONG \
	--enable STACKPROTECTOR_PER_TASK \
	--enable DEBUG_INFO_BTF \
	--disable DEBUG_INFO_BTF_MODULES \
	--disable MODULE_COMPRESS_ALL

make_args=(
	-C "$source_dir"
	O="$build_dir"
	ARCH=riscv
	LLVM=1
	LLVM_IAS=0
	CROSS_COMPILE=riscv64-linux-gnu-
	LOCALVERSION="$local_tag"
)
make "${make_args[@]}" olddefconfig

final_config=$build_dir/.config
for setting in \
	ARCH_SPACEMIT \
	MODULES \
	KVM \
	RISCV_SBI \
	RISCV_IMSIC \
	RISCV_APLIC \
	PCIE_SPACEMIT_K1 \
	PHY_SPACEMIT_K3_COMMON_OPS \
	PHY_SPACEMIT_K3_COMBO_PHY \
	VIRTIO_PCI \
	STACKPROTECTOR_STRONG \
	STACKPROTECTOR_PER_TASK \
	DEBUG_INFO_BTF \
	CC_IS_CLANG \
	AS_IS_GNU \
	LD_IS_LLD; do
	assert_config_y "$setting" "$final_config"
done
for setting in \
	BLK_DEV_NVME \
	BTRFS_FS \
	VIRTIO_BLK \
	VIRTIO_NET \
	VHOST \
	VHOST_NET \
	TUN \
	TAP; do
	assert_config_m "$setting" "$final_config"
done
assert_config_n DEBUG_INFO_BTF_MODULES "$final_config"
assert_config_n MODULE_COMPRESS_ALL "$final_config"

"$source_dir/scripts/diffconfig" \
	"$output_root/config-seed" \
	"$final_config" \
	> "$output_root/config-diff.txt"

make "${make_args[@]}" \
	-j"$jobs" \
	Image \
	modules \
	"$target_dtb"

release=$(make -s "${make_args[@]}" kernelrelease)
case "$release" in
	*-"${local_tag#-}") ;;
	*)
		fail "Unexpected kernel release: $release"
		;;
esac

test -f "$build_dir/arch/riscv/boot/Image"
test -f "$build_dir/arch/riscv/boot/dts/$target_dtb"
test -f "$build_dir/System.map"
test "$(cat "$build_dir/include/config/kernel.release")" = "$release"
grep -Fqx "#define UTS_RELEASE \"$release\"" \
	"$build_dir/include/generated/utsrelease.h"

test ! -e "$stage_dir"
test ! -L "$stage_dir"
test ! -e "$partial_stage"
test ! -L "$partial_stage"
mkdir -p "$partial_stage/boot/dtb-$release/spacemit"
make "${make_args[@]}" \
	INSTALL_MOD_PATH="$partial_stage" \
	INSTALL_MOD_STRIP=1 \
	modules_install
cp "$build_dir/arch/riscv/boot/Image" \
	"$partial_stage/boot/Image-$release"
cp "$build_dir/arch/riscv/boot/dts/$target_dtb" \
	"$partial_stage/boot/dtb-$release/spacemit/"
cp "$final_config" \
	"$partial_stage/boot/config-$release"
cp "$build_dir/System.map" \
	"$partial_stage/boot/System.map-$release"
printf '%s\n' "$release" > "$partial_stage/kernelrelease"

module_root=$partial_stage/lib/modules/$release
test -d "$module_root"
align_report=$partial_stage/module-riscv-align.txt
btf_report=$partial_stage/module-btf.txt
vermagic_report=$partial_stage/module-vermagic-mismatch.txt
compression_report=$partial_stage/module-compression.txt
: > "$align_report"
: > "$btf_report"
: > "$vermagic_report"
: > "$compression_report"

module_count=0
while IFS= read -r -d '' module; do
	module_count=$((module_count + 1))
	module_name=${module#"$partial_stage"/}
	case "$module" in
		*.ko) ;;
		*)
			printf '%s\n' "$module_name" >> "$compression_report"
			continue
			;;
	esac
	relocations=$(llvm-readelf -rW "$module")
	if grep -Fq 'R_RISCV_ALIGN' <<<"$relocations"; then
		{
			printf '%s\n' "$module_name"
			grep -F 'R_RISCV_ALIGN' <<<"$relocations"
		} >> "$align_report"
	fi
	sections=$(llvm-readelf -SW "$module")
	if grep -Eq \
		'[[:space:]]\.BTF([.][^[:space:]]*)?([[:space:]]|$)' \
		<<<"$sections"; then
		{
			printf '%s\n' "$module_name"
			grep -E \
				'[[:space:]]\.BTF([.][^[:space:]]*)?([[:space:]]|$)' \
				<<<"$sections"
		} >> "$btf_report"
	fi
	vermagic=$(modinfo -F vermagic "$module")
	case "$vermagic" in
		"$release"|"$release "*) ;;
		*)
			printf '%s: %s\n' "$module_name" "$vermagic" \
				>> "$vermagic_report"
			;;
	esac
done < <(find "$module_root" -type f \
	\( -name '*.ko' -o -name '*.ko.*' \) -print0)

test "$module_count" -gt 0 ||
	fail "No staged kernel modules were found."
test ! -s "$compression_report" ||
	fail "Compressed staged modules could not be inspected."
test ! -s "$align_report" ||
	fail "Staged modules contain R_RISCV_ALIGN relocations."
test ! -s "$btf_report" ||
	fail "Staged modules contain split module BTF sections."
test ! -s "$vermagic_report" ||
	fail "Staged module vermagic does not match $release."
for module_metadata in \
	modules.order \
	modules.builtin \
	modules.dep \
	modules.alias; do
	test -f "$module_root/$module_metadata" ||
		fail "Missing staged module metadata: $module_metadata"
done

decompiled_dts=$output_root/k3-com260-ifx.decompiled.dts
dtc -I dtb -O dts -s \
	-o "$decompiled_dts" \
	"$partial_stage/boot/dtb-$release/spacemit/k3-com260-ifx.dtb"
pcie0_dtb=$(extract_dts_node \
	"$decompiled_dts" \
	'^[[:space:]]*pcie@80000000[[:space:]]*[{]')
test -n "$pcie0_dtb" ||
	fail "Decompiled DTB lacks the PCIe0 controller."
grep -Fq 'compatible = "spacemit,k3-pcie";' <<<"$pcie0_dtb" ||
	fail "Decompiled PCIe0 node lacks the SpacemiT K3 compatible."
grep -Eq '^[[:space:]]*status = "okay";' <<<"$pcie0_dtb" ||
	fail "Decompiled PCIe0 node is not enabled."
dldo4_dtb=$(extract_dts_node \
	"$decompiled_dts" \
	'^[[:space:]]*dldo4[[:space:]]*[{]')
test -n "$dldo4_dtb" ||
	fail "Decompiled DTB lacks dldo4."
grep -Fq 'regulator-always-on;' <<<"$dldo4_dtb" ||
	fail "Decompiled DTB does not keep dldo4 always on."

(
	cd "$partial_stage"
	find . -type f ! -path './SHA256SUMS' -print0 |
		sort -z |
		xargs -0 sha256sum -- > SHA256SUMS
	test -s SHA256SUMS
	sha256sum --strict -c SHA256SUMS >/dev/null
)
mv "$partial_stage" "$stage_dir"
(
	cd "$stage_dir"
	sha256sum --strict -c SHA256SUMS >/dev/null
)

test -z "$(git -C "$source_dir" status --porcelain --untracked-files=normal)" ||
	fail "Kernel build modified the prepared source worktree."

compiler=$(first_line clang --version)
linker=$(first_line ld.lld --version)
assembler=$(first_line riscv64-linux-gnu-as --version)
readelf_version=$(first_line llvm-readelf --version)
pahole_version=$(first_line pahole --version)
dtc_version=$(first_line dtc --version)
make_version=$(first_line make --version)
git_version=$(first_line git --version)
config_seed_sha=$(sha256sum "$output_root/config-seed")
config_seed_sha=${config_seed_sha%% *}
final_config_sha=$(sha256sum "$final_config")
final_config_sha=${final_config_sha%% *}

cat > "$output_root/source.txt" <<EOF
Build completed UTC: $(date -u +%Y-%m-%dT%H:%M:%SZ)
KVM URL: $kvm_url
Source branch: $source_branch
Source acquisition: $fetch_method
Private fetch ref: $fetch_ref
Source commit: $source_commit
Prepared commit: $prepared_commit
Prepared tree: $prepared_tree
Expected tree: $expected_tree
Patch count: ${#patches[@]}
Patch metadata: $patch_metadata
Config seed: $config_seed
Config seed SHA256: $config_seed_sha
Final config SHA256: $final_config_sha
Config diff: $output_root/config-diff.txt
Kernel release: $release
Local version: $local_tag
Build jobs: $jobs
Build tuple: ARCH=riscv LLVM=1 LLVM_IAS=0 CROSS_COMPILE=riscv64-linux-gnu-
Compiler: $compiler
Linker: $linker
Assembler: $assembler
Readelf: $readelf_version
Pahole: $pahole_version
DTC: $dtc_version
Make: $make_version
Git: $git_version
Staged modules: $module_count
Module install stripping: enabled
Split module BTF: disabled
EOF

(
	cd "$output_root"
	sha256sum \
		config-seed \
		config-diff.txt \
		patches.txt \
		source.txt \
		k3-com260-ifx.decompiled.dts \
		build/.config \
		build/arch/riscv/boot/Image \
		build/arch/riscv/boot/dts/spacemit/k3-com260-ifx.dtb \
		build/System.map \
		stage/SHA256SUMS \
		stage/kernelrelease \
		"stage/boot/Image-$release" \
		"stage/boot/config-$release" \
		"stage/boot/System.map-$release" \
		"stage/boot/dtb-$release/spacemit/k3-com260-ifx.dtb" \
		> SHA256SUMS
	sha256sum --strict -c SHA256SUMS >/dev/null
)

cat <<EOF
K3 KVM host kernel built and staged successfully.

Base:    $source_commit
Tree:    $prepared_tree
Patches: ${#patches[@]}
Kernel:  $release
Modules: $module_count
Stage:   $stage_dir

Nothing was transferred or installed, no K3 was accessed or rebooted, and
U-Boot was not modified.
EOF
