<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Hardware and setup

This page is for readers evaluating or preparing the Firefly-sold
8 GiB K3-CoM260 kit for the F45-first documentation route. It explains how to
distinguish the module from its carrier, check the dated recall and power
references, and assemble the Linux workstation, maintenance-host, serial,
and NVMe prerequisites.
Use it to decide whether hardware matches the recorded route, not as a
compatibility list for other K3 products.

## Identify the hardware first

The K3 is the SoC, the K3-CoM260 is the module, and the carrier provides the
connectors and recovery header. A module name alone is not enough to choose a
pinout or power supply.

The [F45 host record](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md)
and [historical F44 setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#recorded-snapshot)
are deliberately narrower than a product-family compatibility list:

| Item | Recorded setup |
| --- | --- |
| Kit | Firefly-sold K3-CoM260 with 8 GiB RAM, on a Firefly carrier |
| Carrier identity | Exact PCB model/revision not established; `k3-com260-ifx` is the device-tree identity, not a PCB identifier |
| Firmware | Bianbu Minimal K3 v4.0.1, non-UEFI U-Boot |
| Fedora storage | NVMe in the carrier's 2280 slot; the historical F44 setup, prepared through a USB enclosure, identifies a WD Red SN700 500 GB. F45 was tested on two existing partitions (p4/p5) of the same NVMe that holds F44, prepared from that F44 system as maintenance host. A USB enclosure is one untested way to prepare F45 partitions from a workstation. |
| Access | 3.3 V USB serial adapter, physical reset/power-cycle access, and a trusted isolated LAN for SSH |

The historical SSD model records what was used; it is not a minimum
requirement or a compatibility certification for other drives. Do not treat
Firefly's
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
[Fedora 45 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#workstation-serial-and-notation)
is the authority for commands, device selection, and per-machine variables.
Only the Linux-workstation route is documented here, with a **Linux
maintenance host** that can reach the K3's NVMe; the tested maintenance host
was Fedora 44 on other partitions of the same disk, and other kinds are
unverified. The fresh installation into two existing partitions was
performed end to end on October 20, 2026; no F44 installation or shrink
step is required. Read the
[readiness and recorded scope](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#readiness-and-recorded-scope)
before planning disk work.

| Phase | Workstation and maintenance-host requirements from the recipe |
| --- | --- |
| F45 installation and bootstrap | Workstation: Git, Bash, Python 3.10+, OpenSSH client and key tools, and serial tools. Maintenance host: sudo, Python 3.10+, util-linux, e2fsprogs, btrfs-progs, rsync, curl, xz, zstd, dtc with `fdtget`/`fdtput`, systemd and udev, plus about 12 GiB free below `/var/tmp`. Check the exact dependency list before starting. |
| Pinned F45 package update | The [public bundle's dependencies](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/README.md#interfaces-and-dependencies), including RPM inspection, transfer tools and the adjacent lock/helpers; no kernel source build is required. |

Allow maintenance-host storage for the compressed image (about 1.2 GB) and
its decompressed copy, and workstation storage for the pinned RPM bundle.
Have two erasable NVMe partitions (at least 2 GiB and 32 GiB), a maintenance
host that can reach them, the serial adapter, and a USB data cable for
recovery. Add header-compatible jumper leads/removable jumpers or
normally-open momentary switches for FC_REC and RST to ground, following the
[conditional header reference](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery#conditional-12-pin-header-reference).
You need to be able to hold recovery while applying power or pulsing reset.
Select the disk and partitions by stable `/dev/disk/by-id/` names, never by
a guessed device name.

The route uses the 2280 NVMe slot and removes microSD cards:
non-vendor SD layouts stopped the stock BootROM before serial output during
historical bring-up. This is not an SD installation guide. The exact
identification, check and populate checkpoints are in
[Image and prepare the NVMe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#image-and-prepare-the-nvme).

The [F44 archive](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-44-Archive)
retains the optional source-built host and guest tooling. Its full Linux
history, Clang/LLVM/GNU-binutils build requirements and guest-preparation
tools belong to that historical development route, not F45 host setup.

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
Cooling-fan work is explicitly deferred: the fan runs at full speed under
the pinned F45 kernels, which exposed no SoC thermal zones; an NVMe
temperature is not a SoC measurement. No thermal-protection, fail-safe, or
unattended-operation assurance is established.

## Source scope

The public F45 results establish the tested volume-route and side-by-side
host scope; the
[preserved F44 recipe](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md)
retains the older setup details. Manufacturer/seller references above retain
their **September 27, 2026** review, not a new October availability or
electrical check. The linked V2.1 vendor guide names product version
`K3-CoM260_P1_LP5315B_32X2_v03_20260312`; it is reference documentation, not
proof of this kit's carrier PCB revision. Match the actual board before using
its connector diagrams.

## Technical notes

**Applies to:** Firefly-sold 8 GiB K3-CoM260 kit; exact carrier PCB model/revision unknown; Linux workstation, Linux maintenance host and two existing NVMe partitions.

**Evidence:** Public F45 results recorded October 20 and October 19 and reviewed locally on October 20, and preserved September 25 F44 setup details. Manufacturer/seller and electrical-reference context retains its September 27 review.

**Source review:** 2026-10-20.

**Hardware observation:** 2026-10-20 fresh F45 installation into existing p4/p5 partitions: 7.2.7 bootstrap, exact 7.2.8 update and three attended 7.2.8 boots; 2026-10-19 side-by-side F45 host boots and 2026-09-25 archived setup snapshot. No new electrical measurement.

**Destructive operations:** None on this page. The linked installation reformats the two selected NVMe partitions, destroying their contents.

**Previous:** [Start here](https://github.com/xjamesmorris/k3-com260-info/wiki/Home).
**Next:** [Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery).
