<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Diagnostics and known limits

Use this page when a recorded checkpoint fails or when preparing a precise
public report from the F45 host route or the F44 archive. Start with **the
last successful checkpoint**, not a board-wide conclusion: a checksum pass,
a compiled DTB, an early login prompt, and a persistent Fedora guest are
different results.
The symptom table mixes recorded failures with diagnostic checkpoints; not
every entry is an observed defect. Keep workstation, maintenance-host,
U-Boot, K3 host, and guest observations separate. F45 commands belong to the
[Fedora 45 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe);
the archived [Fedora-Recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe)
remains the sole F44 command authority. The tested F45 route is a fresh
installation into two existing NVMe partitions; whole-disk imaging and
partition creation remain unverified.

## Locate the failing stage

| Symptom | Stage | Known scope | Next recorded check or stop decision |
| --- | --- | --- | --- |
| No serial output with a non-vendor microSD layout present | BootROM, before U-Boot/Linux | Recorded during historical F44 bring-up, not a new F45 defect. This is not evidence that Fedora on NVMe failed. | The route removes microSD; return to the [serial/U-Boot checkpoint](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#workstation-serial-and-notation). If U-Boot cannot be reached, stop kernel/guest diagnosis and use [console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery). |
| Failed file load, unexpected size, or an unsuitable kernel Image | NVMe preparation or U-Boot | Checkpoint, not a new observed defect. A packaged EFI zboot `vmlinuz` is not the raw Image used here. | Reconcile the release, the populate or installer summary's sizes, and filenames in [F45 NVMe preparation](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#image-and-prepare-the-nvme). Stop before `booti` on any load, size, address, or command-line mismatch. |
| `PCIE-2: Link down` with the 2230 slot empty | U-Boot NVMe discovery | Historical F44 observation: this message can describe the empty slot, not failure of the SSD in the 2280 slot. | Use the [F45 bootstrap load checkpoints](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#boot-the-bootstrap-fedora-host): `nvme scan` must report the 2280 slot's link up, and `fsuuid` must print your F45 `/boot` UUID. Do not copy the recorded p4 boot selection. Stop if the intended drive is not found. |
| Lockup around unused-regulator cleanup, roughly 30-45 seconds into boot | Host kernel and device tree | Earlier F44 failure without the workaround. Recorded F45 boots used both `dldo4` and `hub-reset`, not an isolated causal comparison. | Compare the selected DTB with [F45 bootstrap preparation](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#image-and-prepare-the-nvme). The separate [source-built dldo4 example](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development#the-dldo4-example) is historical, not a substitute F45 DTB. |
| Root filesystem does not mount | Initramfs/root handoff | Checkpoint, not a recorded general NVMe defect. This route uses the F45 root UUID from the populate summary and Btrfs subvolume `root`. | Compare the selected release's Image/initramfs/modules, actual root identity, and boot arguments with [the matching boot set](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update#keep-each-boot-set-together). Stop if the device or UUID cannot be positively identified; do not rewrite the disk as a diagnostic shortcut. |
| Installed 7.2.8 but selected DTB or `/boot/dtb` still identifies 7.2.7 | F45 package/boot-file handoff | The installer deliberately preserves the old symlink. It also creates the separately named 7.2.8 bootstrap DTB, copied when the packaged 7.2.7/7.2.8 DTBs are byte-identical, as they are for these pins. | Use the [pinned update and the installer's summary](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#install-the-pinned-kernel-update), load the 7.2.8 directory's `k3-com260-bootstrap.dtb`, then verify the actual selected files. A symlink or package transaction is not a running-kernel check. |
| Ethernet link/IPv6 works but DHCPv4 and SSH are late | Networking after boot, including after switching between F45 and F44 | All four October 20 F45 boots obtained DHCPv4 within about 23–26 seconds, but F44 on the same board then took about 145 seconds. On October 19, two boots took about 4–9 seconds and a third about 7.5 minutes without intervention. The cause was not determined; prompt IPv4 is not established for every boot. | Keep serial access, wait, and record link, address and elapsed-time observations using the [updated-host checks](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#boot-and-check-the-updated-host) rather than rebooting repeatedly. Do not label a missing early SSH connection a kernel lockup. |
| Unexpected ESP mounts despite the direct non-UEFI route | F45 services/timers | On October 19, on the first 7.2.8 boot, RTC correction triggered catch-up timers and fwupd/udisks2 briefly mounted both the retained F44 NVMe ESP and Bianbu UFS ESP read-write. On October 20, with fwupd masked offline by the populate helper before first boot, no boot mounted a FAT filesystem. | Read the recipe's [release-scoped fwupd workaround](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe). Masking and no-FAT-mount checks are not isolation guarantees for other storage. |
| Only the USB2 root hub appears | F45 USB probing | DWC3 `81400000.usb3` remained deferred, as in the earlier F44 observation. USB3 enablement is not a result of these boots. | Preserve the reported scope; do not infer external USB support from host/NVMe success or introduce an untested hub change. |
| Fan runs at full speed, loudly | F45 fan control | Expected: the pinned 7.2.7 and 7.2.8 kernels have no fan driver, and the fan ran at full speed in every recorded F45 boot. | Cooling-fan work is deferred; this page supplies no fan-control workflow. Full speed is not thermal protection, and not a reason to reflash. |
| No SoC thermal zones | F45 thermal visibility | Neither 7.2.7 nor 7.2.8 exposed them. The recorded 43.9 °C NVMe temperature is not a SoC measurement. | Cooling-fan work is explicitly deferred. No thermal-protection, fail-safe or unattended-use assurance is established. |
| `/dev/kvm` is missing or inaccessible | F45 host initialization or access policy | The public F45 result records host initialization and the device, not a QEMU/guest workload. | Check the [updated host's release and kernel messages](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#boot-and-check-the-updated-host). Do not make the device world-writable, import an F44 CPU workaround, or report a guest pass from a node alone. |

## Historical F44 build and guest checkpoints

These entries apply to the archived source-built host and guest, **not F45
installation requirements or F45 guest results**.

| Symptom | Stage | Known scope | Next recorded check or stop decision |
| --- | --- | --- | --- |
| Module rejection, or relocation/BTF stage checks fail | Build/staging or host module loading | The recorded toolchain needed GNU `as` and disabled split module BTF. This is not a claim that all LLVM-built kernels fail. | Compare final config, tool versions, release/vermagic, and [builder guards](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development#build-and-stage-with-the-recorded-guards). Stop on a failed guard rather than weakening it. |
| `/dev/kvm` is missing or inaccessible | F44 K3 host transition or access policy | A device node alone is not proof of the recorded host configuration or usable KVM. Guests are not launched on the old F44 Omni bootstrap. | Follow the [F44 host-release, kernel-message, device-access, and QEMU checks](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#build-and-install-the-kvm-host). Use the documented group/udev decision; do not make the device world-writable. |
| Fedora guest is silent or does not boot | Guest CPU, interrupt, kernel, or launch configuration | Triage checkpoint, not a current claim that the board's KVM is broken. Bare `host` helper defaults are not the validated full Fedora guest tuple. | Compare **all** settings in [the guest recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#prepare-and-run-the-persistent-guest), not settings from a different smoke test. Do not substitute software emulation and report it as a KVM pass. |
| Guest SSH fails while QEMU is running | Guest readiness or access path | A running QEMU process does not establish guest boot, credentials, or networking. The recorded guest SSH forwarding is K3-loopback-only. | Use the recipe's separate runner-status, guest, and workstation-tunnel checkpoints. Verify host keys and the seed identity; do not disable host-key checks or expose the port as a workaround. |
| Expected guest changes are absent after `resume` | Guest disk identity/persistence | Checkpoint, not an observed data-loss result. `resume` boots the same persistent disk; it does not restore a VM snapshot. | Reconcile the complete guest directory, `overlay.qcow2` and its relative `base.img`, and the clean-shutdown step in [the guest recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#prepare-and-run-the-persistent-guest). Stop before replacing or separating backing files. |

The historical F44 comparison for the persistent guest is the pinned
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
None of this CPU filter, Sstc setting, guest argument set or per-mode
coverage has been validated on the F45 packaged host.

## Interpret checks without promoting them to hardware results

The historical [public dldo4 RFC](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/dldo4/0001-riscv-dts-spacemit-k3-com260-keep-dldo4-enabled.patch)
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

Use the appropriate release's recipe checks for the stage reached: F45
release/mount/kernel/network checks, or archived F44 QEMU/runner/guest
checks. Do not run a later destructive step merely to complete this template.
Supply short, reviewed
excerpts with the first relevant error and relative boot timestamps; a full
console dump or build transcript may expose unrelated information.

```text
Observation date and timezone: <date; not the date this page was reviewed>
Stage: <workstation or maintenance-host preparation / U-Boot / K3 host / guest>
Hardware: <K3-CoM260 RAM; carrier label and PCB revision, or unknown>
Firmware and image: <exact versions/filenames; non-UEFI or other route>
Public recipe/source revision: <public commit or URL>
Running / installed candidate / temporarily selected kernel: <each release>
Input identity: <image/package filenames, lock revision and hashes>
Source and patches if built: <public base; prepared tree; patch order, or unproven>
Config and tools: <package config, or seed/final config and actual build tools>
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

The [F45 public record](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md)
covers one fresh installation into existing p4/p5 partitions on October 20
(one bootstrap boot and three attended 7.2.8 boots) and the earlier
October 19 side-by-side bring-up. It is not a partition-creation,
other-maintenance-host or whole-disk-imaging result, guest test, thermal
qualification or long-duration result. The fan runs at full speed and all
fan work remains deferred; this page supplies no fan-control workflow.

Display, carrier external USB, suspend and VFIO remain open. A working NVMe
root or enumerated endpoint is not a test of every peripheral. Other
carriers, UEFI/libvirt, newer releases and different toolchains remain
separate combinations, not validated substitutions. The archived F44
stages are not an end-to-end rerun of the exported bundle. Neither record
provides production or hostile-guest isolation assurance.

## Sources

- [F45 host results](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md) and [exact pins](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/files/sources.lock.json): observed exceptions and host-only boundary.
- [Preserved F44 record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md): historical checkpoints, symptoms, exact guest tuple, and exclusions.
- [Kernel provenance](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md) and [factory-flashing documentation](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/tools/README.md): build versus hardware evidence and recovery scope.
- [Linux issue-reporting guide](https://docs.kernel.org/admin-guide/reporting-issues.html): upstream reporting expectations, not an additional tested board procedure.

## Technical notes

**Applies to:** Firefly-sold 8 GiB K3-CoM260 kit, Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot and Linux-workstation/NVMe F45 host route, with separately labeled archived F44 build/guest checkpoints. Carrier PCB revision is not established by `k3-com260-ifx`.

**Evidence:** Public October 20 and October 19 F45 results/pins and preserved September 25 F44 record, helper guards and dldo4 RFC. Upstream reporting references retain their September 27 review. Checkpoint failures on this page are not all observed defects.

**Source review:** 2026-10-20.

**Hardware observation:** 2026-10-20 fresh F45 installation into existing p4/p5 partitions: 7.2.7 bootstrap, exact 7.2.8 update and three attended 7.2.8 boots; 2026-10-19 F45 p4/p5 bootstrap and three pre-fan 7.2.8 boots; 2026-09-25 archived F44 setup. The dldo4 RFC has no separate test date. No F45 guest test here.

**Destructive operations:** None in the report template. Linked installation/recovery procedures can overwrite disks or NOR/UFS; a diagnostic symptom alone is not a reason to reimage or flash.

**Previous:** [Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update) | **Next:** [Kernel and device-tree development](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development) | [Home](https://github.com/xjamesmorris/k3-com260-info/wiki/Home)
