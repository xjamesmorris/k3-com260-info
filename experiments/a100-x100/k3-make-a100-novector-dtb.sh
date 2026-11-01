#!/usr/bin/env bash
set -Eeuo pipefail
set -x

usage()
{
	cat <<'EOF'
Usage:
  k3-make-a100-novector-dtb.sh [--ziccrse] INPUT_DTB OUTPUT_DTB

Build an experimental SpacemiT K3 DTB that also describes the eight A100
harts (cpu@8 to cpu@15), so that a mainline-based kernel can bring all 16
harts online. The A100 nodes, their L2 caches, cpu-map clusters and S-mode
IMSIC wiring follow SpacemiT's k3/hmp-on-7.3 commit 558f896383b5
("riscv: dts: spacemit: Add A100 cpu nodes for K3"), except that the A100
nodes omit "v" and every "zv*" extension and the vendor-only "cpu-ai"
property.

Linux uses the intersection of every hart's extensions. With this DTB the
whole system therefore loses vector (RVV), KVM (A100 has no H extension)
and Ziccrse (absent from the vendor A100 list), while X100 nodes still
describe their own hardware.

--ziccrse also appends "ziccrse" to each A100 node, so the kernel keeps
queued spinlocks instead of falling back to ticket spinlocks. This is an
unverified hardware claim: SpacemiT's A100 list omits it, although A100 is
modelled as RVA23U64, which mandates it. Use only for testing.

INPUT_DTB must be an unmodified 8-hart K3 DTB with the S-mode IMSIC at
/soc/interrupt-controller@e0400000, such as Fedora 7.3.1's
/boot/dtb-<release>/spacemit/k3-com260-ifx.dtb. The script writes
OUTPUT_DTB and OUTPUT_DTB.diff (decompiled input-to-output diff). It
refuses to overwrite either file and does not install, transfer or boot
anything.
EOF
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	usage
	exit 0
fi

ziccrse=0
if [[ ${1:-} == --ziccrse ]]; then
	ziccrse=1
	shift
fi

if [[ $# -ne 2 ]]; then
	usage >&2
	exit 2
fi

input=$1
output=$2
imsic=/soc/interrupt-controller@e0400000

die()
{
	echo "error: $*" >&2
	exit 1
}

for tool in dtc fdtget diff sha256sum; do
	command -v "$tool" >/dev/null || die "missing tool: $tool"
done

[[ -f $input ]] || die "input DTB not found: $input"
[[ ! -e $output ]] || die "refusing to overwrite $output"
[[ ! -e $output.diff ]] || die "refusing to overwrite $output.diff"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# fdtget prints hex cells separated by spaces; normalize to one per line.
cells()
{
	fdtget -t x "$@" | tr ' ' '\n' | sed '/^$/d'
}

# Input preconditions: exactly the 8 X100 harts and the 8-hart IMSIC.
mapfile -t cpus < <(fdtget -l "$input" /cpus | grep '^cpu@' | sort -V)
[[ ${cpus[*]} == "cpu@0 cpu@1 cpu@2 cpu@3 cpu@4 cpu@5 cpu@6 cpu@7" ]] ||
	die "expected exactly cpu@0..cpu@7 in /cpus, found: ${cpus[*]}"
[[ $(fdtget "$input" /cpus '#address-cells') == 1 ]] ||
	die "/cpus #address-cells is not 1"
[[ $(fdtget -l "$input" /cpus/cpu-map | tr '\n' ' ') == "cluster0 cluster1 " ]] ||
	die "expected cpu-map clusters cluster0 and cluster1 only"
for node in cache-controller-2 cache-controller-3; do
	if fdtget -l "$input" /cpus | grep -qx "$node"; then
		die "/cpus/$node already exists"
	fi
done
fdtget "$input" "$imsic" compatible | grep -qw 'riscv,imsics' ||
	die "$imsic is not a RISC-V IMSIC"
[[ $(cells "$input" "$imsic" reg | tr '\n' ' ') == "0 e0400000 0 200000 " ]] ||
	die "unexpected $imsic reg"
[[ $(fdtget "$input" "$imsic" riscv,hart-index-bits) == 4 ]] ||
	die "IMSIC hart-index-bits is not 4"
[[ $(fdtget "$input" "$imsic" riscv,guest-index-bits) == 6 ]] ||
	die "IMSIC guest-index-bits is not 6"
mapfile -t old_ie < <(cells "$input" "$imsic" interrupts-extended)
[[ ${#old_ie[@]} -eq 16 ]] || die "IMSIC interrupts-extended is not 8 entries"
for i in {0..7}; do
	intc=$(fdtget -t x "$input" "/cpus/cpu@$i/interrupt-controller" phandle)
	[[ ${old_ie[2 * i]} == "$intc" && ${old_ie[2 * i + 1]} == 9 ]] ||
		die "IMSIC entry $i does not target cpu@$i S-mode external IRQ"
done

# Vendor A100 list from 558f896383b5 without "v" and "zv*".
a100_isa='"i", "m", "a", "f", "d", "c", "b",
				"smaia", "smstateen", "ssaia", "ssccptr", "sscofpmf",
				"sscounterenw", "ssnpm", "ssstateen", "sstc",
				"sstvala", "sstvecd", "ssu64xl", "svade",
				"svinval", "svnapot", "svpbmt", "za64rs",
				"zawrs", "zba", "zbb", "zbc", "zbs", "zca",
				"zcb", "zcd", "zcmop", "zfa", "zfbfmin",
				"zfh", "zfhmin", "zicbom", "zicbop", "zicboz",
				"ziccamoa", "ziccif", "zicclsm", "zicntr",
				"zicond", "zicsr", "zifencei", "zihintntl",
				"zihintpause", "zihpm", "zimop", "zkt", "sdtrig"'
if ((ziccrse)); then
	a100_isa+=', "ziccrse"'
fi

dtc -q -I dtb -O dts -o "$tmp/base.dts" "$input"

# Sanity check that dtc round-trips the input without changes.
dtc -q -I dts -O dtb -o "$tmp/roundtrip.dtb" "$tmp/base.dts"
dtc -q -I dtb -O dts -o "$tmp/roundtrip.dts" "$tmp/roundtrip.dtb"
cmp "$tmp/base.dts" "$tmp/roundtrip.dts" || die "dtc does not round-trip the input"

{
	cat "$tmp/base.dts"
	printf '\n&{/cpus} {\n'
	for n in {8..15}; do
		if ((n < 12)); then l2=a100_l2_cache2; else l2=a100_l2_cache3; fi
		cat <<EOF
	a100_cpu$n: cpu@$n {
		compatible = "spacemit,a100", "riscv";
		device_type = "cpu";
		reg = <$n>;
		riscv,isa-base = "rv64i";
		riscv,isa-extensions = $a100_isa;
		riscv,cbom-block-size = <64>;
		riscv,cbop-block-size = <64>;
		riscv,cboz-block-size = <64>;
		i-cache-block-size = <64>;
		i-cache-size = <32768>;
		i-cache-sets = <128>;
		d-cache-block-size = <64>;
		d-cache-size = <32768>;
		d-cache-sets = <128>;
		next-level-cache = <&$l2>;
		mmu-type = "riscv,sv39";

		a100_cpu${n}_intc: interrupt-controller {
			compatible = "riscv,cpu-intc";
			#interrupt-cells = <1>;
			interrupt-controller;
		};
	};

EOF
	done
	for c in 2 3; do
		cat <<EOF
	a100_l2_cache$c: cache-controller-$c {
		compatible = "cache";
		cache-block-size = <64>;
		cache-level = <2>;
		cache-size = <1048576>;
		cache-sets = <1024>;
		cache-unified;
	};

EOF
	done
	printf '\tcpu-map {\n'
	for c in 2 3; do
		printf '\t\tcluster%d {\n' "$c"
		for core in {0..3}; do
			printf '\t\t\tcore%d {\n\t\t\t\tcpu = <&a100_cpu%d>;\n\t\t\t};\n' \
				"$core" $(((c - 2) * 4 + core + 8))
		done
		printf '\t\t};\n'
	done
	printf '\t};\n};\n\n'
	printf '&{%s} {\n\treg = <0x0 0xe0400000 0x0 0x400000>;\n' "$imsic"
	printf '\tinterrupts-extended ='
	for n in {0..15}; do
		if ((n < 8)); then
			ref="&{/cpus/cpu@$n/interrupt-controller}"
		else
			ref="&a100_cpu${n}_intc"
		fi
		if ((n < 15)); then sep=','; else sep=';'; fi
		printf ' <%s 9>%s' "$ref" "$sep"
	done
	printf '\n};\n'
} >"$tmp/combined.dts"

dtc -q -I dts -O dtb -o "$tmp/out.dtb" "$tmp/combined.dts"
out=$tmp/out.dtb

# Output checks.
mapfile -t cpus < <(fdtget -l "$out" /cpus | grep '^cpu@' | sort -V)
[[ ${#cpus[@]} -eq 16 ]] || die "output does not have 16 cpu nodes"
mapfile -t new_ie < <(cells "$out" "$imsic" interrupts-extended)
[[ ${#new_ie[@]} -eq 32 ]] || die "output IMSIC is not 16 entries"
[[ ${new_ie[*]:0:16} == "${old_ie[*]}" ]] || die "X100 IMSIC entries changed"
[[ $(cells "$out" "$imsic" reg | tr '\n' ' ') == "0 e0400000 0 400000 " ]] ||
	die "output IMSIC reg is wrong"
l2_2=$(fdtget -t x "$out" /cpus/cache-controller-2 phandle)
l2_3=$(fdtget -t x "$out" /cpus/cache-controller-3 phandle)
for n in {8..15}; do
	node=/cpus/cpu@$n
	[[ $(fdtget -t x "$out" "$node" reg) == "$(printf '%x' "$n")" ]] ||
		die "$node reg is wrong"
	[[ $(fdtget "$out" "$node" compatible) == "spacemit,a100 riscv" ]] ||
		die "$node compatible is wrong"
	isa=$(fdtget "$out" "$node" riscv,isa-extensions | tr ' ' '\n')
	if grep -qE '^(v|h|zv.*|sh.*)$' <<<"$isa"; then
		die "$node lists a vector or hypervisor extension"
	fi
	grep -qx zicbom <<<"$isa" || die "$node lost zicbom"
	if grep -qx ziccrse <<<"$isa"; then
		((ziccrse)) || die "$node lists ziccrse without --ziccrse"
	else
		((!ziccrse)) || die "$node lacks ziccrse"
	fi
	intc=$(fdtget -t x "$out" "$node/interrupt-controller" phandle)
	[[ ${new_ie[2 * n]} == "$intc" && ${new_ie[2 * n + 1]} == 9 ]] ||
		die "IMSIC entry $n does not target $node"
	if ((n < 12)); then l2=$l2_2; else l2=$l2_3; fi
	[[ $(fdtget -t x "$out" "$node" next-level-cache) == "$l2" ]] ||
		die "$node next-level-cache is wrong"
	cpuph=$(fdtget -t x "$out" "$node" phandle)
	cluster=$((n < 12 ? 2 : 3))
	core=$(((n - 8) % 4))
	[[ $(fdtget -t x "$out" "/cpus/cpu-map/cluster$cluster/core$core" cpu) == "$cpuph" ]] ||
		die "cpu-map cluster$cluster/core$core does not point at $node"
done
for i in {0..7}; do
	[[ $(fdtget "$out" "/cpus/cpu@$i" riscv,isa-extensions) == \
	   "$(fdtget "$input" "/cpus/cpu@$i" riscv,isa-extensions)" ]] ||
		die "cpu@$i extensions changed"
done

# The decompiled diff may only remove the two replaced IMSIC lines.
dtc -q -I dtb -O dts -o "$tmp/out.dts" "$out"
diff -u "$tmp/base.dts" "$tmp/out.dts" >"$tmp/out.diff" && die "output is identical"
removed=$(tail -n +3 "$tmp/out.diff" | grep -c '^-' || true)
[[ $removed -eq 2 ]] || die "diff removes $removed lines, expected 2"
tail -n +3 "$tmp/out.diff" | grep '^-' | grep -qE '^-[[:space:]]+reg = <0x00 0xe0400000 0x00 0x200000>;$' ||
	die "diff does not replace the IMSIC reg line"
tail -n +3 "$tmp/out.diff" | grep '^-' | grep -qE '^-[[:space:]]+interrupts-extended = ' ||
	die "diff does not replace the IMSIC interrupts-extended line"

cp "$out" "$output"
cp "$tmp/out.diff" "$output.diff"
sha256sum "$input" "$output"
