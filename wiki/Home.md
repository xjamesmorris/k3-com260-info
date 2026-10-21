<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Start here

This is a **Fedora 45-first developer guide** for advanced early adopters,
developers, and security researchers using the 8 GiB SpacemiT K3-CoM260 on
the recorded Firefly carrier. It introduces the Linux-workstation/NVMe
route, maintenance, and optional development work. The tested F45
installation route and its unverified alternatives have different evidence
boundaries.

> **Unofficial resource:** This guide is user-developed and maintained; it is
> not an official Fedora Project resource.

**Tested fresh-install route (October 20, 2026).** The
[F45 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#readiness-and-recorded-scope)
installs the pinned image into **two existing NVMe partitions** from a Linux
maintenance host, using the public helpers; that route was performed end to
end. Creating the partitions, other kinds of maintenance host and
whole-disk imaging remain **unverified**. New F45 starters do not need to
install or shrink F44 first. The route ends with the pinned
[7.3.0 fan-control upgrade](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#upgrade-to-73-with-fan-control),
booted once on October 21; until then the fan runs at full speed.

**Start with [Hardware and setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup).**
If your hardware and serial console already match, go to
[Install Fedora](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora)
for the route's checkpoints and command authority. “Default” here means the
documentation route only, never a saved U-Boot default or deletion of F44.

## What has worked

The [public F45 result record](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md)
leads with an **October 20, 2026 fresh installation** using the public
helpers: F45 went into existing partitions p4 (ext4 `/boot`) and p5 (Btrfs
root) of the K3's NVMe, from a Fedora 44 maintenance host on p1–p3 of the
same disk. The saved F44 boot path was retained. Afterwards the partition
table, all 116 F44 `/boot` and `/boot/efi` files and the raw Bianbu UFS ESP
were byte-identical to the before-state. On **October 21** the pinned 7.3.0
upgrade, installed from 7.2.8, added kernel fan control in one attended boot.

| Stage | Recorded stack | Result and boundary |
| --- | --- | --- |
| F45 fresh installation | Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot; non-official community Beta image `Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz`; `populate-f45-volumes.sh`, read-only `--check` first | Two existing partitions reformatted and populated, with no partition-table change. The helper extracted the raw Image, created a bootstrap DTB keeping both `dldo4` and `hub-reset` enabled, and masked fwupd offline before first boot. |
| F45 bootstrap | `7.2.7-300.0.riscv64.omni.fc45.riscv64`, from that image | One attended boot, login prompt 24 seconds after `booti`; first serial login as `fedora`, working sudo, and an SSH host key verified against serial. |
| F45 packaged update | COPR build `11035571`; `7.2.8-300.0.riscv64.omni.fc45.riscv64`, installed beside 7.2.7 | Exact five-RPM install; the installer also created the separately named 7.2.8 bootstrap DTB. Three attended boots: login about 22 seconds after `booti`, startup 22.9–23.5 seconds, `running`, no failed units, no FAT mounts. Host KVM initialization only, not a guest result. |
| F45 fan-control upgrade | COPR build `11177969`; `7.3.0-65.1.riscv64.omni.fc45.riscv64`, installed beside 7.2.8 | Exact five-RPM install from 7.2.8, booted with its packaged DTB. One attended boot (October 21): seven thermal zones and kernel fan control, much quieter at idle and faster under a two-minute load; USB3 hub enumerated. Not a thermal qualification. |

The earlier **October 19** side-by-side bring-up on the same p4/p5, made
before the public helpers existed, remains recorded: one bootstrap boot and
three pre-fan 7.2.8 smoke boots, each over ten minutes, with intended
mounts, zero recorded Btrfs device errors, and no reported lockup/RCU
stall/oops at the checks.

The [F44 archive](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-44-Archive)
retains its September 25 bootstrap, source-built host and persistent Fedora
guest results. Its 14-patch kernel build and guest CPU workarounds are
historical optional development references, **not F45 prerequisites**.

## What remains limited

**Manual boot, not an installed default:** every Fedora U-Boot selection is
temporary. Never save the environment. Reset follows the existing saved boot
path, which may be Bianbu or the retained F44 selection. Keep working firmware;
factory flashing is not a default setup step.

**Host-only F45 evidence:** no F45 QEMU version, guest launch, guest network,
or persistent shutdown/resume was recorded. KVM is optional, and `/dev/kvm`
or an AIA host banner is not guest-workload proof.

**Open operating limits:** under 7.2.7 and 7.2.8 the fan runs at full
speed, loudly, USB3 probing stays deferred (USB2 only) and no SoC thermal
zones are exposed; the one recorded 7.3.0 boot changed all three. DHCPv4
arrived within about 23–26 seconds in all four October 20 F45 boots, but one
October 19 boot took about 7.5 minutes, and F44 took about 145 seconds
after switching back. No thermal-protection or unattended-use assurance is
made, even with 7.3.0 fan control. Display, suspend, VFIO, long-duration
stability, other carriers, UEFI, SD-root, and newer inputs remain outside
this result. See
[Diagnostics and known limits](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits)
before planning an experiment. There is no production or hostile-guest
isolation claim.

## Choose your next step

- **Follow the F45 starting route:** [Hardware and setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup), [Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery), then [Install Fedora](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora). Read the recipe's [unverified alternatives](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#unverified-alternatives) before departing from the tested route; continue to [Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update) for package and boot-set identities.
- **Evaluate and operate the board:** use [Diagnostics and known limits](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits) to identify the complete stack, and [Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update) before changing it.
- **Develop and contribute:** start with [Kernel and device-tree development](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development) or [KVM and QEMU](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU), then [Contributing upstream](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream). [AI and toolchains](https://github.com/xjamesmorris/k3-com260-info/wiki/AI-and-Toolchains) is a separate development brief, not a Fedora acceleration recipe.
- **Reproduce the historical F44 work:** start at the [archive landing page](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-44-Archive), not the F45 recipe.

## Sources and prior art

Use the [F45 result record](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md),
[exact lock](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/files/sources.lock.json),
and [public support-bundle inventory](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/README.md)
for the current host scope. The preserved F44 sources and captures remain
linked from the archive; they are not F45 guest or installation evidence.
[Fedora's Omni overview](https://fedoraproject.org/wiki/Architectures/RISC-V/OmniKernel)
explains the downstream enablement approach.
[Fedora's K3-Pico-ITX notes](https://fedoraproject.org/wiki/Architectures/RISC-V/SpacemiT/K3-Pico-ITX)
are useful prior art, not interchangeable carrier or boot instructions.

For the wider context, see
[Ecosystem and resources](https://github.com/xjamesmorris/k3-com260-info/wiki/Ecosystem-and-Resources)
and [Status and sources](https://github.com/xjamesmorris/k3-com260-info/wiki/Status-and-Sources).

## Technical notes

**Applies to:** Firefly-sold 8 GiB K3-CoM260 kit, Firefly carrier with unknown PCB revision; Linux workstation and maintenance host, two existing NVMe partitions and Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot.

**Evidence:** Public October 21, 20 and 19 F45 host results and pins, plus the preserved September 25 F44 archive. External Omni/Pico-ITX reference context retains its September 29 source review; it was not refreshed for this local route review.

**Source review:** 2026-10-21.

**Hardware observation:** 2026-10-21 one attended boot of the COPR 7.3.0 fan-control upgrade installed from 7.2.8; 2026-10-20 fresh F45 installation into existing p4/p5 partitions: 7.2.7 bootstrap, exact 7.2.8 update and three attended 7.2.8 boots; 2026-10-19 side-by-side F45 bootstrap and three pre-fan updated-host smoke boots; 2026-09-25 archived F44 stages. No F45 guest workload or new test for this page.

**Destructive operations:** None on this page. The installation reformats the two selected NVMe partitions; factory recovery erases NOR and all UFS, including the saved environment.

**Next:** [Hardware and setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup).
