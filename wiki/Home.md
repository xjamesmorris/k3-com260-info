<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Start here

**Fedora on the SpacemiT K3-CoM260**

> **Unofficial resource:** This guide is user-developed and maintained; it is
> not an official Fedora Project resource.

This is a practical Fedora-first starting point for advanced early adopters,
developers, and security researchers using the Firefly-sold 8 GiB K3-CoM260
kit on its recorded Firefly carrier. It orients readers to the Linux-workstation
and NVMe route before they move into installation, kernel, virtualization, or
contribution work. Get a Fedora shell, understand the limits of the recorded
system, then use it for deliberate experiments or useful upstream reports.

**Start with [Hardware and setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup).**
If your hardware and serial console already match, go to
[Install Fedora](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora)
for the checkpoints around the
[Recorded Fedora recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe).

## What has worked

These are three distinct stages of the
[September 25 recorded setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#recorded-snapshot),
not a claim that an untouched stock image provides the whole system.

| Stage | Recorded stack | Result and boundary |
| --- | --- | --- |
| Fedora bootstrap | Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot; Fedora 44 Omni July 31 image, `7.1.5-201.0.riscv64.omni.fc44.riscv64` | Fedora on NVMe, reached through serial and SSH. The prepared bootstrap DTB keeps both `dldo4` and `hub-reset` enabled. |
| KVM host transition | Pinned, patched `7.3.0-rc4-k3-kvm-host-a1` | Side-by-side kernel installation and temporary U-Boot selection. This host has the isolated `dldo4` fix plus PCIe support, not the bootstrap's two-property workaround. |
| Persistent Fedora guest | Fedora QEMU `10.2.2-1.fc44`; Fedora 44 Cloud June 4 image, guest kernel `6.19.8-200.0.riscv64.fc43.riscv64`; 4 vCPUs / 4 GiB | Interactive Fedora guest and persistent disk, with recorded PLIC and AIA launches. The recipe's full CPU and guest-kernel settings are required; helper defaults are not the validated launch. |

## What remains limited

**Manual boot, not an installed default:** every Fedora U-Boot selection is
temporary. Never save the environment. Reset follows the existing saved boot
path, which may be Bianbu. The old Omni bootstrap is not the guest-running
host; the optional KVM route requires the host transition before launching
guests.

**Narrow evidence:** the historical stages ran on hardware, but the portable
bundle has not been rerun end to end. The `k3-com260-ifx` device-tree identity
does not establish the carrier's PCB model or revision. This is neither a
general K3 compatibility claim nor production or hostile-guest assurance.

**Not established by this recipe:** display, external USB, fan/thermal policy,
suspend, VFIO, long-duration stability, other carriers, UEFI, SD-root, or newer
image/kernel/toolchain combinations. See
[Diagnostics and known limits](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits)
and the recipe's
[snapshot boundaries](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#updating-this-snapshot).

## Choose your next step

- **Get Fedora running:** [Hardware and setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup), [Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery), then [Install Fedora, phase 1](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora#phase-1-bootstrap-fedora-on-nvme). Its checkpoint completes the Fedora-on-NVMe installation goal; continue to [Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update). The custom KVM host and guest are optional development work, not installation requirements. Keep working firmware that matches the recorded route.
- **Evaluate and operate the board:** use [Diagnostics and known limits](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits) to identify the complete stack, and [Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update) before changing it.
- **Develop and contribute:** start with [Kernel and device-tree development](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development) or [KVM and QEMU](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU), then [Contributing upstream](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream). [AI and toolchains](https://github.com/xjamesmorris/k3-com260-info/wiki/AI-and-Toolchains) is a separate development brief, not a Fedora acceleration recipe.

## Sources and prior art

The primary evidence is the
[preserved Fedora/KVM how-to](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md),
its [kernel payload provenance](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md),
and the [factory-flashing record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/tools/README.md#status).
[Fedora's Omni overview](https://fedoraproject.org/wiki/Architectures/RISC-V/OmniKernel)
explains the downstream enablement approach.
[Fedora's K3-Pico-ITX notes](https://fedoraproject.org/wiki/Architectures/RISC-V/SpacemiT/K3-Pico-ITX)
are useful prior art, not interchangeable carrier or boot instructions.

For the wider context, see
[Ecosystem and resources](https://github.com/xjamesmorris/k3-com260-info/wiki/Ecosystem-and-Resources)
and [Status and sources](https://github.com/xjamesmorris/k3-com260-info/wiki/Status-and-Sources).

## Technical notes

**Applies to:** Firefly-sold 8 GiB K3-CoM260 kit, Firefly carrier with unknown PCB revision; Linux workstation and NVMe.

**Evidence:** Recorded Fedora/KVM bring-up and factory-flash results, with public sources linked on this page.

**Source review:** 2026-09-29.

**Hardware observation:** 2026-09-25 Fedora/KVM snapshot; historical stages, not an end-to-end rerun of the portable bundle.

**Destructive operations:** None on this page. The installation overwrites the selected NVMe; factory recovery erases NOR and all UFS, including the saved environment.

**Next:** [Hardware and setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup).
