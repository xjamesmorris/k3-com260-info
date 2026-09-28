<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Hardware and setup

This page is for readers evaluating or preparing the recorded Firefly-sold
8 GiB K3-CoM260 kit before firmware or disk work. It explains how to
distinguish the module from its carrier, check the dated recall and power
references, and assemble the Linux workstation, serial, and NVMe prerequisites.
Use it to decide whether hardware matches the recorded route, not as a
compatibility list for other K3 products.

## Identify the hardware first

The K3 is the SoC, the K3-CoM260 is the module, and the carrier provides the
connectors and recovery header. A module name alone is not enough to choose a
pinout or power supply.

The [recorded setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#recorded-snapshot)
is deliberately narrower than a product-family compatibility list:

| Item | Recorded setup |
| --- | --- |
| Kit | Firefly-sold K3-CoM260 with 8 GiB RAM, on a Firefly carrier |
| Carrier identity | Exact PCB model/revision not established; `k3-com260-ifx` is the device-tree identity, not a PCB identifier |
| Firmware | Bianbu Minimal K3 v4.0.1, non-UEFI U-Boot |
| Fedora storage | WD Red SN700 500 GB in the carrier's 2280 slot; prepared through a USB NVMe enclosure; the only NVMe device in this route |
| Access | 3.3 V USB serial adapter, physical reset/power-cycle access, and a trusted isolated LAN for SSH |

The SSD model records what was used; it is not a minimum requirement or a
compatibility certification for other drives. Do not treat Firefly's
`CORE-K3JD4` system-on-module/product family as the identity of this kit's
carrier, or transfer these wiring instructions to another carrier.

## Buying, power, and the manufacturer notice

The [Firefly K3-CoM260 kit listing](https://www.t-firefly.com/products/k3-com260-robotics-development-kit)
is a procurement starting point, not a promise about the configuration in a
future shipment. Confirm the module RAM/UFS variant, carrier model and PCB
revision, supplied cooling and PSU, SSD mounting hardware, and access to the
serial/recovery header before ordering. Firefly's separate
[CORE-K3JD4 listing](https://www.t-firefly.com/products/core-k3jd4-risc-v-edge-system-on-module)
describes a system-on-module/product family; it must not be used to infer that
this recorded carrier is the same board.

Use the kit's bundled PSU or a supply approved for the **exact carrier and
revision**. The
[SpacemiT K3 CoM260 Kit User Guide V2.1, July 16, 2026](https://cdn-resource.spacemit.com/file/product/K3/k3_com260_ug_en.pdf)
has conflicting current ratings between its power sections; this page does
not choose a replacement rating by inference. The guide describes its
reference kit's USB-C OTG connector as **not a power input**. Confirm your
carrier's power connection rather than treating a USB-C data cable as its PSU.

**Check the dated 8 GB recall notice.** SpacemiT's
[August 23, 2026 Chinese-language manufacturer notice](https://forum.spacemit.com/t/topic/1609)
covers 8 GB K3 CoM260 Kit/core-board products shipped **August 4-14, 2026**,
reporting a risk of early PCB failure and recall, replacement, or refund
handling. This page summarizes the notice in English; consult the original
for its wording and contact route. Check your shipment records privately if
potentially affected. This is a summary of the manufacturer's scope, not an
assessment of any reader's unit.

## Prepare the Linux workstation

Use Bash and simple working paths without spaces. The
[Recorded Fedora recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#workstation-serial-and-notation)
is the authority for commands, device selection, and per-machine variables.
Only the Linux-workstation route is documented here.

| Phase | Workstation requirements from the recipe |
| --- | --- |
| Bootstrap | Git, SSH, tmux, picocom, curl, xz, zstd, dtc, util-linux, udevadm, GNU coreutils, and `partprobe` from parted |
| Optional KVM host build | Normal kernel build dependencies, Clang/LLD and LLVM tools, GNU `riscv64-linux-gnu-` binutils, dtc, pahole, Git, and rsync |
| Optional persistent guest | `qemu-img`, libguestfs `virt-copy-out`, `cloud-localds`, Python 3, curl, zstd, and `ssh-keygen` |

Allow workstation storage for the Fedora image; the optional KVM route also
needs space for a full Linux history, separate build output and guest
preparation. Have an expendable or backed-up NVMe, its USB enclosure, the
serial adapter, and a USB data cable for recovery. Add header-compatible
jumper leads/removable jumpers or normally-open momentary switches for
FC_REC and RST to ground, following the
[conditional header reference](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery#conditional-12-pin-header-reference).
You need to be able to hold recovery while applying power or pulsing reset.
Do not select a workstation disk for imaging by a guessed device name.

The recorded route uses the 2280 NVMe slot and removes microSD cards:
non-vendor SD layouts stopped the stock BootROM before serial output during
bring-up. This is not an SD installation guide. The exact preparation and
unmount checkpoints are in
[Image and prepare the NVMe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#image-and-prepare-the-nvme).

## Ready to continue

First establish a readable, interruptible **Bianbu Minimal K3 v4.0.1 non-UEFI
U-Boot** console and physical reset/power-cycle access. If that matches, keep
the existing firmware and UFS contents. Working but different or unidentified
firmware is outside this recorded route: identify it and follow the
[firmware decision](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery#decide-whether-recovery-is-needed),
not an automatic reflash. Use
[Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery)
before any disk write; then follow
[Install Fedora](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora).
Keep the initial host on a trusted isolated LAN and follow the recipe's
credential and SSH host-key checks before wider network exposure.

## Source scope

The [preserved public recipe](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md)
is the setup evidence. The linked V2.1 vendor guide names product version
`K3-CoM260_P1_LP5315B_32X2_v03_20260312`; it is reference documentation, not
proof of this kit's carrier PCB revision. Match the actual board before using
its connector diagrams.

## Technical notes

**Applies to:** Firefly-sold 8 GiB K3-CoM260 kit; exact carrier PCB model/revision unknown; Linux-workstation/NVMe route.

**Evidence:** Recorded setup in the public Fedora recipe; separately identified manufacturer and seller references.

**Source review:** 2026-09-27.

**Hardware observation:** 2026-09-25 Fedora/KVM setup snapshot; no new hardware or electrical measurements.

**Destructive operations:** None on this page. The linked Install Fedora procedure overwrites the entire selected NVMe disk.

**Previous:** [Start here](https://github.com/xjamesmorris/k3-com260-info/wiki/Home).
**Next:** [Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery).
