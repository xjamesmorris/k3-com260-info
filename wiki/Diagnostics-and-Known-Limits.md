<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Diagnostics and known limits

Use this page when a recorded checkpoint fails or when preparing a precise
public report from the Fedora/KVM route. Start with **the last successful
checkpoint**, not a board-wide conclusion: a checksum pass, a compiled DTB,
an early login prompt, and a persistent Fedora guest are different results.
The symptom table mixes recorded failures with diagnostic checkpoints; not
every entry is an observed defect. Keep workstation, U-Boot, K3 host, and
guest observations separate; the commands remain in
[Fedora-Recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe).

## Locate the failing stage

| Symptom | Stage | Known scope | Next recorded check or stop decision |
| --- | --- | --- | --- |
| No serial output with a non-vendor microSD layout present | BootROM, before U-Boot/Linux | Such SD layouts stopped this stock boot path before serial output during bring-up. This is not evidence that Fedora on NVMe failed. | The recorded route removes microSD; return to the [serial/U-Boot checkpoint](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#workstation-serial-and-notation). If U-Boot cannot be reached, stop kernel/guest diagnosis and use [console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery). |
| Failed file load, unexpected size, or an unsuitable kernel Image | Workstation preparation or U-Boot | Checkpoint, not a new observed defect. The pinned packaged `vmlinuz` is a zstd EFI zboot container, not the raw Image used here. | Reconcile the release, extraction checks, and filenames in [NVMe preparation](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#image-and-prepare-the-nvme). Stop before `booti` on any load, size, address, or command-line mismatch. |
| `PCIE-2: Link down` with the 2230 slot empty | U-Boot NVMe discovery | This message can describe the empty slot, not failure of the SSD in the 2280 slot. | Use the [bootstrap load checks](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#boot-the-bootstrap-fedora-host) for the recorded single-NVMe layout. Successful loads from the intended drive matter; stop if it is not found. |
| Lockup around unused-regulator cleanup, roughly 30-45 seconds into boot | Host kernel and device tree | Recorded failure without the workaround. The Omni bootstrap used two DT changes; the later source-built host uses the isolated dldo4 fix with PCIe support. | Compare the actual selected DTB with the correct [bootstrap preparation](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#image-and-prepare-the-nvme) or [source-built host](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development#the-dldo4-example) stage. Do not remove a property to improvise a new comparison. |
| Root filesystem does not mount | Initramfs/root handoff | Checkpoint, not a recorded general NVMe defect. This route uses the discovered NVMe root UUID and Btrfs subvolume `root`. | Compare the selected release's Image/initramfs/modules, actual root identity, and boot arguments with [the matching boot set](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update#keep-each-boot-set-together). Stop if the device or UUID cannot be positively identified; do not rewrite the disk as a diagnostic shortcut. |
| Module rejection, or relocation/BTF stage checks fail | Build/staging or host module loading | The recorded toolchain needed GNU `as` and disabled split module BTF. This is not a claim that all LLVM-built kernels fail. | Compare final config, tool versions, release/vermagic, and [builder guards](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development#build-and-stage-with-the-recorded-guards). Stop on a failed guard rather than weakening it. |
| `/dev/kvm` is missing or inaccessible | K3 host transition or access policy | A device node alone is not proof of the recorded host configuration or usable KVM. Guests are not launched on the old Omni bootstrap. | Follow the [host-release, kernel-message, device-access, and QEMU checks](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#build-and-install-the-kvm-host). Use the documented group/udev decision; do not make the device world-writable. |
| Fedora guest is silent or does not boot | Guest CPU, interrupt, kernel, or launch configuration | Triage checkpoint, not a current claim that the board's KVM is broken. Bare `host` helper defaults are not the validated full Fedora guest tuple. | Compare **all** settings in [the guest recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#prepare-and-run-the-persistent-guest), not settings from a different smoke test. Do not substitute software emulation and report it as a KVM pass. |
| Guest SSH fails while QEMU is running | Guest readiness or access path | A running QEMU process does not establish guest boot, credentials, or networking. The recorded guest SSH forwarding is K3-loopback-only. | Use the recipe's separate runner-status, guest, and workstation-tunnel checkpoints. Verify host keys and the seed identity; do not disable host-key checks or expose the port as a workaround. |
| Expected guest changes are absent after `resume` | Guest disk identity/persistence | Checkpoint, not an observed data-loss result. `resume` boots the same persistent disk; it does not restore a VM snapshot. | Reconcile the complete guest directory, `overlay.qcow2` and its relative `base.img`, and the clean-shutdown step in [the guest recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#prepare-and-run-the-persistent-guest). Stop before replacing or separating backing files. |

The comparison for the persistent guest is the pinned
`7.3.0-rc4-k3-kvm-host-a1` host, Fedora QEMU `10.2.2-1.fc44`, and Fedora 44
Cloud June 4 image with guest kernel
`6.19.8-200.0.riscv64.fc43.riscv64`, 4 vCPUs and 4 GiB. Its CPU string is
`host,svpbmt=false,zicbom=false,zicbop=false,zicboz=false`, with Sstc left
enabled and extra arguments
`earlycon=sbi unaligned_scalar_speed=slow unaligned_vector_speed=unsupported`.
PLIC is the initial recorded mode; `aplic-imsic` is the separately recorded
alternative after clean PLIC boot and shutdown. These are compatibility
conditions, not optional tuning. See the
[KVM and QEMU evidence matrix](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU)
for result boundaries.

## Interpret checks without promoting them to hardware results

The [public dldo4 RFC](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/dldo4/0001-riscv-dts-spacemit-k3-com260-keep-dldo4-enabled.patch)
records one matched source-built comparison, with the changed system healthy
at 302.45 seconds. It does not establish long-duration stability, the actual
rail consumer, or another carrier's behavior. The successful two-property
Omni bootstrap does not independently establish that both properties were
necessary.

Similarly, source/patch hashes establish input identity, build checks
establish their stated output properties, and a temporary boot establishes
only the observations actually made on that stack. `fastfetch` is a guest
summary, not proof of KVM acceleration; the recorded runner explicitly requires
KVM. Neither host boot nor guest persistence establishes hostile-guest
isolation.

For factory recovery, the
[tool record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/tools/README.md#status)
distinguishes a successful Minimal v4.0.1 flash/boot from other merely pinned
images. `--check` verifies inputs without device traffic, but can download
and extract multi-GB archives; it is not a successful flash or a
side-effect-free preview. The recorded EC refusal is deliberately non-fatal;
do not extend that exception to partition or payload-write failures.

## A useful, sanitized report

Use the recipe's existing release, mount, kernel-message, QEMU-version,
runner-status, and guest checks for the stage you reached. Do not run a later
destructive step merely to complete this template. Supply short, reviewed
excerpts with the first relevant error and relative boot timestamps; a full
console dump or build transcript may expose unrelated information.

```text
Observation date and timezone: <date; not the date this page was reviewed>
Stage: <workstation preparation / U-Boot / K3 host / guest>
Hardware: <K3-CoM260 RAM; carrier label and PCB revision, or unknown>
Firmware and image: <exact versions/filenames; non-UEFI or other route>
Public recipe/source revision: <public commit or URL>
Running / installed candidate / temporarily selected kernel: <each release>
Source and patches: <public base commit; prepared tree; patch order>
Config and tools: <seed/final config hashes; compiler/linker/as/pahole versions>
Boot set: <Image, DTB, initramfs hashes; modules release; config identity>
Selected versus live DT: <selected filename/hash; live evidence or not collected>
Storage/root: <slot, filesystem, subvolume; consistent redacted identifiers>
Guest if relevant: <image/kernel; QEMU; CPU string; Sstc; interrupt mode>
Guest resources/arguments: <vCPUs, memory, complete compatibility arguments>
Last successful checkpoint: <what actually passed>
Expected / observed: <specific difference; first error; elapsed boot time>
Comparison: <what changed since a working case, or no matched comparison>
Checks performed: <result, scope, date; sanitized excerpt if needed>
Not tested / stopped because: <remaining gaps and stop decision>
```

Replace personal usernames, hostnames, IP/MAC addresses, UUIDs, device
serials/WWNs, and machine-local paths with consistent placeholders. Never
include private keys, tokens, passwords, or unreviewed archives. Preserve
public version strings, source/patch hashes, relevant error text, and timing:
those make the report useful without identifying the operator's machines.

For an Omni or other downstream-only problem, disclose the downstream tree
and patches rather than labelling it a pristine-mainline regression.
[Upstream reporting guidance](https://docs.kernel.org/admin-guide/reporting-issues.html)
explains that distinction; it is reporting context, not an instruction here
to install an untested kernel. Use
[contributing upstream](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream)
for report preparation and human-controlled submission.

## Limits that remain open

Display, carrier external USB, fan/thermal policy, suspend, VFIO, and
long-duration stability are outside the public recipe. A working NVMe root
or enumerated endpoint is not a test of every peripheral. Other carriers,
UEFI/libvirt, newer releases, and different toolchains remain separate
combinations, not validated substitutions. The three historical stages are
not an end-to-end rerun of the exported bundle.

## Sources

- [Preserved Fedora/KVM record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md): checkpoints, symptoms, exact guest tuple, and exclusions.
- [Kernel provenance](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md) and [factory-flashing documentation](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/tools/README.md): build versus hardware evidence and recovery scope.
- [Linux issue-reporting guide](https://docs.kernel.org/admin-guide/reporting-issues.html): upstream reporting expectations, not an additional tested board procedure.

## Technical notes

**Applies to:** Firefly-sold 8 GiB K3-CoM260 kit, Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot, Linux-workstation/NVMe Fedora bootstrap, and the pinned KVM host/guest stages. Carrier PCB revision is not established by `k3-com260-ifx`.

**Evidence:** Public Fedora/KVM record, exported helper guards, recovery-tool results, and the public dldo4 RFC. Checkpoint failures on this page are not all observed defects.

**Source review:** 2026-09-27.

**Hardware observation:** 2026-09-25 recorded Fedora/NVMe and KVM setup; the separate dldo4 RFC does not specify an independent test date. No new run; the portable bundle has not been rerun end to end.

**Destructive operations:** None in the report template. Linked installation/recovery procedures can overwrite disks or NOR/UFS; a diagnostic symptom alone is not a reason to reimage or flash.

**Previous:** [Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update) | **Next:** [Kernel and device-tree development](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development) | [Home](https://github.com/xjamesmorris/k3-com260-info/wiki/Home)
