<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Install Fedora

**Applies to:** Firefly-sold 8 GiB K3-CoM260 kit, carrier PCB revision unknown; Linux workstation, NVMe, Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot.

**Evidence:** The preserved September 25 Fedora/KVM recipe and pinned kernel provenance, not a newer-image recommendation.

**Source review:** 2026-09-27.

**Hardware observation:** 2026-09-25 historical bootstrap, patched-host and persistent-Fedora-guest stages; portable bundle not rerun end to end.

**Destructive operations:** Imaging overwrites the entire selected NVMe. Optional development stages add host kernel and guest files on NVMe. Deliberately chosen factory recovery erases NOR and all UFS, including the saved environment.

**Use the [Recorded Fedora recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe) for every installation, host-transition and guest command.**
This page supplies orientation and checkpoints, not a second recipe. The
generated page preserves the
[public how-to](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md),
apart from relocated links and the documented checkout-path correction to
`k3-com260-fedora-howto/`; the source is unchanged.

## Before starting

- Match the [hardware and workstation requirements](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup), with an expendable or backed-up NVMe and a USB enclosure for imaging.
- Reach the [normal serial checkpoint](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery#normal-setup-keep-working-firmware): interruptible Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot and physical reset/power-cycle access. Keep matching firmware; for working but different firmware, follow the [firmware decision](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery#decide-whether-recovery-is-needed) before proceeding.
- Keep a trusted isolated LAN for the initial Fedora login, then follow the recipe's credential and SSH host-key checks. Never bypass a failed check to get to the next phase.

Keep the three systems' kernels, DTBs and launch settings distinct. Each reset
requires attended, temporary U-Boot selection; never save the environment.

## Phase 1: Bootstrap Fedora on NVMe

Follow [Workstation, serial, and notation](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#workstation-serial-and-notation),
[Image and prepare the NVMe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#image-and-prepare-the-nvme),
then [Boot the bootstrap Fedora host](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#boot-the-bootstrap-fedora-host).

Fedora 44 Omni's July 31 image supplies
`7.1.5-201.0.riscv64.omni.fc44.riscv64`. The recipe prepares a raw Image and
a separate bootstrap DTB with **both `dldo4` and `hub-reset`** enabled,
leaving the original DTB intact. This result does not isolate either change;
do not substitute the later host's `dldo4`-only fix.

**Before writing:** the image checksum, enclosure's stable whole-disk
identity, model/size/serial, USB transport, and absence of mounts or swap must
pass the recipe's checks. The prepared, unmounted SSD becomes the sole NVMe
device in the 2280 slot; remove microSD cards for this route.

**Checkpoint:** matching boot files and load sizes, the discovered root UUID,
then the expected Omni kernel and NVMe root from a responsive Fedora console
and verified SSH connection. An early login prompt is insufficient: without
the DTB workaround, bring-up locked up around unused-regulator cleanup,
roughly 30-45 seconds into boot. Do not launch guests on this bootstrap kernel.

**The Fedora-on-NVMe installation goal is complete when this checkpoint
passes.** If you only want Fedora, stop here and continue to
[Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update).
This completes the recorded manual-boot installation, not a current security
or production-readiness assessment; retain the trusted, isolated-LAN boundary.

## Optional KVM development route

Phases 2 and 3 reproduce the recorded custom KVM host and persistent guest.
Neither is required to finish installing Fedora on NVMe. Choose them only for
that development goal; phase 3 requires the phase-2 host, not the old Omni
bootstrap.

### Phase 2: Move to the pinned KVM host

Follow [Build and install the KVM host](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#build-and-install-the-kvm-host).
The [kernel provenance record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md)
binds the source commit, 14 patches, configuration and expected tree for
`7.3.0-rc4-k3-kvm-host-a1`. This patched host includes PCIe support and the
isolated `dldo4` fix, not the unrelated USB/hub series or pristine mainline.

Installation adds the candidate alongside the bootstrap kernel without
changing the saved boot path. The recipe temporarily selects its matched
Image/DTB/initramfs through U-Boot, checking sizes and non-overlapping load
ranges.

**Checkpoint:** the running release is exactly
`7.3.0-rc4-k3-kvm-host-a1`, root is still the intended NVMe filesystem,
KVM initialization is visible, and the normal `fedora` user has read/write
access to `/dev/kvm`. The recorded QEMU package is `10.2.2-1.fc44`.
Installed files alone do not establish which kernel is running.

### Phase 3: Run the persistent Fedora guest

Follow [Prepare and run the persistent guest](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#prepare-and-run-the-persistent-guest).
This is the full Fedora 44 Cloud June 4 guest, not a minimal smoke test.
Keep its base image, seed, boot files and persistent overlay together.
Use the recipe's **entire CPU and guest-kernel settings**, with Sstc left
enabled; the runner's bare-`host` default is not the validated Fedora launch.
Start with PLIC; AIA is the recorded alternative after a clean guest shutdown.

**Checkpoint:** the 4-vCPU / 4-GiB Fedora guest is accessible through the
documented loopback SSH tunnel, with its expected kernel
`6.19.8-200.0.riscv64.fc43.riscv64` and root filesystem. The runner requires
KVM without a software-emulation fallback. Shut down cleanly before
`resume`, which boots the persistent disk rather than restoring a VM snapshot.

See [KVM and QEMU](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU)
for the result matrix and the limits of this configuration. None of these
checkpoints is production or hostile-guest assurance.

## Stop and recovery decisions

| Stop condition | What to do next |
| --- | --- |
| Uncertain disk, failed checksum, missing source pin or unexpected boot-file layout | Stop before writing or booting. Resolve the mismatch, rather than choosing a newer input. |
| Failed U-Boot load, wrong size/UUID, undefined address or malformed command | Do not boot or save. Recheck the recipe and [Diagnostics and known limits](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits). |
| Candidate kernel fails but U-Boot remains usable | Diagnose through serial. Reset follows the saved path, possibly Bianbu; it is not automatic Fedora rollback. |
| Guest fails while the host remains usable | Stay on the host and check the recorded guest settings. Do not factory-flash to repair a guest. |
| Firmware recovery is necessary, or a human deliberately chooses to restore the recorded baseline | Back up needed contents and use [Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery#factory-recovery-only-when-needed). This is not a default setup step: factory flashing erases NOR/UFS and the saved environment, not NVMe. |

Before changing packages or kernels, read
[Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update)
and [Updating this snapshot](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#updating-this-snapshot).
Newer releases, other carriers and alternative boot routes are not validated
substitutions.

**Previous:** [Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery).
**Next:** [Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update).
