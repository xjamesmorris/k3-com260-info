<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Install Fedora

This page orients experienced Linux bring-up users to the **Fedora 45-first
installation route**, after hardware and serial-console checks.
The newcomer route installs the pinned F45 image into **two existing NVMe
partitions** from a Linux maintenance host, using the public helpers. It is
not an F44 migration guide: there is no F44 prerequisite, partition shrink,
or F44-removal step.

**Tested route (October 20, 2026).** The
[public F45 results](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md)
record a fresh installation into existing p4/p5 partitions, made from an
F44 maintenance host on p1–p3 of the same NVMe: the 7.2.7 bootstrap boot,
first login, the exact 7.2.8 update and three attended 7.2.8 boots, with
the partition table, F44 boot files and Bianbu UFS ESP verified unchanged.
Creating the partitions, other kinds of maintenance host and whole-disk
imaging were **not** performed; see the recipe's
[unverified alternatives](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#unverified-alternatives).

**Use the [Fedora 45 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe) for F45 commands.**
This page supplies orientation and checkpoints, not a duplicate command
sequence. Read its
[readiness and recorded scope](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#readiness-and-recorded-scope)
first. “Default” means documentation entry points only, never a saved
U-Boot choice or deletion of F44.

## Before starting

- Match the [hardware and workstation requirements](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup), with **two erasable partitions** on the NVMe the K3 boots from (at least 2 GiB for `/boot` and 32 GiB for the Btrfs root) and a **Linux maintenance host** that can reach that NVMe while running from neither target. Creating the partitions is outside the tested route.
- Reach the [normal serial checkpoint](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery#normal-setup-keep-working-firmware): interruptible Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot and physical reset/power-cycle access. Keep matching firmware; for working but different firmware, follow the [firmware decision](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery#decide-whether-recovery-is-needed) before proceeding.
- Keep a trusted isolated LAN for initial login: the image's `fedora` account has the documented default password `linux`, and SSH password login is enabled. Change the password at the first serial login, then follow the recipe's privilege and SSH host-key checkpoints; do not assume an inherited SSH key or passwordless sudo configuration.
- Use the [public support bundle](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/README.md) and [exact lock](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/files/sources.lock.json), not a floating “latest” image or package.

Keep bootstrap and updated kernels, DTBs and initramfs files distinct.
Hardware work requires a separate human decision and physical supervision;
each reset requires attended, temporary U-Boot selection. Never save the
environment, and never bypass a failed checkpoint.

## Phase 1: Bootstrap Fedora on NVMe

The sequence is
[Workstation, serial, and notation](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#workstation-serial-and-notation),
[Image and prepare the NVMe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#image-and-prepare-the-nvme),
including [Check, then populate the two partitions](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#check-then-populate-the-two-partitions),
then [Boot the bootstrap Fedora host](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#boot-the-bootstrap-fedora-host).

The non-official community Beta image
`Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz` supplies
`7.2.7-300.0.riscv64.omni.fc45.riscv64`. The populate helper extracts the
raw Image and creates a separately named bootstrap DTB with **both `dldo4`
and `hub-reset`** enabled, preserving the packaged DTB. The recorded result
does not isolate either property's effect.

**Before formatting:** run the helper's read-only `--check` first. It binds
the disk's stable `/dev/disk/by-id/` identity, model, serial and size, and
each target's current ext4/Btrfs UUID or `empty`, and verifies the image
hash; mounted, swap-active, held or otherwise unexpected targets are
refused. The helper never edits the partition table. Use the boot partition
number and root UUID from its populate summary; do not copy the recorded
`nvme 0:4` selection. Shut down the maintenance system before booting F45,
and remove microSD cards.

**Checkpoint:** `fsuuid` prints your F45 `/boot` UUID, every load matches
the populate summary's exact size, `bootargs` names your root UUID, and the
exact bootstrap kernel runs on the intended `/boot` and Btrfs root. Then
log in on serial as `fedora`, change the password, confirm `sudo`, and
verify the SSH host key against the serial console. (The October 20 run did
not exercise the password change.) An early prompt alone is insufficient.
The historical regulator failure occurred roughly 30–45 seconds into boot;
keep the prepared DTB and check the running host after that point. The
October 20 bootstrap reached its login prompt after 24 seconds and was
checked after that point.

## Phase 2: Install and check the pinned package update

Use [Install the pinned kernel update](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#install-the-pinned-kernel-update)
and [Boot and check the updated host](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#boot-and-check-the-updated-host).
The update is COPR build **`11035571`**,
**`7.2.8-300.0.riscv64.omni.fc45.riscv64`**, installed beside 7.2.7 from
five hash-pinned binary RPMs. This is not a source-built 14-patch kernel
requirement or a general Fedora release upgrade. Hash pins are not verified
publisher signatures: recorded RPM inspection reported `NOKEY`, and the
exact source Git binding remains unproven.

The installer also creates the **separately named 7.2.8 bootstrap DTB**:
it copies the 7.2.7 bootstrap DTB only when the packaged 7.2.7 and 7.2.8
DTBs are byte-identical, as they are for these pins, and otherwise
generates one with `make-bootstrap-dtb.sh`. Review its summary before any
boot. Do not assume the equivalence for another release or select by
`/boot/dtb` alone. Preserve the original boot set and inspect matching
initramfs support.

**Checkpoint:** exact running 7.2.8 release, expected NVMe mounts,
storage-error and kernel-message checks, and network/SSH observations over
attended boots. The three October 20 boots reached the login prompt about
22 seconds after `booti` and had DHCPv4 within about 23 seconds; in the
October 19 bring-up, one boot took about **7.5 minutes** to obtain DHCPv4.
fwupd was masked offline, before first boot, by the populate helper's
tested `mask` choice; that release-scoped workaround is not isolation of
other storage.

**Cooling-fan work is deferred.** The pinned kernels have no fan control,
so the fan runs at full speed, loudly; no SoC thermal zones were exposed.
These boots do not establish thermal protection, fail-safe behavior, or
safe unattended operation. Finish with the recipe's
[next steps and readiness record](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#next-steps-and-readiness-record)
and [Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update).

## Optional KVM and the F44 archive

KVM is **not required** to install an F45 developer host. The F45 evidence
stops at host initialization and `/dev/kvm`; there is no recorded F45 QEMU
version, guest launch, guest CPU filter, guest networking or persistence
result. Do not inherit an F44 workaround or guest check.

The [F44 archive](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-44-Archive)
retains the source-built host and full persistent-guest workflow. Its
unchanged [Fedora-Recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe)
is the sole F44 command authority. See
[KVM and QEMU](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU)
for the separate host-only F45 and historical F44 rows. Neither record
provides production or hostile-guest assurance.

## Stop and recovery decisions

| Stop condition | What to do next |
| --- | --- |
| Uncertain disk, failed checksum, missing artifact pin or unexpected boot-file layout | Stop before writing or booting. Resolve the mismatch, rather than choosing a newer input. |
| Failed U-Boot load, wrong size/UUID, undefined address or malformed command | Do not boot or save. Recheck the recipe and [Diagnostics and known limits](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits). |
| Candidate kernel fails but U-Boot remains usable | Diagnose through serial. Reset follows the saved path, possibly Bianbu; it is not automatic Fedora rollback. |
| Fresh login/privilege, DTB comparison, initramfs, or storage checks are unresolved | Stop and record the gap. Do not bypass the guard. |
| Optional guest experiment fails while the host remains usable | F45 has no tested guest walkthrough here. Record the exact stack; do not factory-flash to repair a guest or relabel an F44 check as an F45 pass. |
| Firmware recovery is necessary, or a human deliberately chooses to restore the recorded baseline | Back up needed contents and use [Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery#factory-recovery-only-when-needed). This is not a default setup step: factory flashing erases NOR/UFS and the saved environment, not NVMe. |

Before changing packages or kernels, read
[Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update)
and retain the recipe's recorded scope. Newer releases, other carriers
and alternative boot routes are separate experiments, not validated
substitutions.

## Technical notes

**Applies to:** Firefly-sold 8 GiB K3-CoM260 kit, carrier PCB revision unknown; Linux workstation and maintenance host, two existing NVMe partitions, Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot.

**Evidence:** Public October 20 fresh-installation and October 19 side-by-side F45 results, exact image/package lock and maintained F45 recipe; partition creation, other maintenance hosts and whole-disk imaging are untested. The September 25 F44 recipe remains archived, with its September 27 source review unchanged.

**Source review:** 2026-10-20.

**Hardware observation:** 2026-10-20 fresh F45 installation into existing p4/p5 partitions: 7.2.7 bootstrap, exact 7.2.8 update and three attended 7.2.8 boots; 2026-10-19 F45 p4/p5 bootstrap and three attended pre-fan 7.2.8 smoke boots. No F45 guest workload was tested.

**Destructive operations:** Populating reformats the two selected NVMe partitions, destroying their contents, without changing the partition table. Package installation changes the RPM database, modules and `/boot`; boot checks require attended resets. Deliberately chosen factory recovery erases NOR and all UFS, including the saved environment. This page authorizes none of these actions.

**Previous:** [Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery).
**Next:** [Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update).
