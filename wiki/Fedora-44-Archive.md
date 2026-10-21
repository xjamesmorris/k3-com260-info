<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Fedora 44 archive

This page keeps the **September 25, 2026 Fedora 44 bring-up route** accessible
for experienced Linux users reproducing or investigating that result.
It covers the recorded 8 GiB K3-CoM260 on a Firefly carrier, Bianbu Minimal
K3 v4.0.1 non-UEFI U-Boot, and NVMe preparation from a Linux workstation.
It is a historical reference, not a latest-image recommendation or a
security/support endorsement.

## Choose the right route

The newer **Fedora 45-first default is a separate route**: start with the
[current installation orientation](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora)
and [Fedora 45 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe),
observing their recorded scope. That route is not an automatic upgrade
of an existing Fedora 44 installation. Neither this archive nor its guest
results establish Fedora 45 guest validation.

For the historical route, use the unchanged
[Fedora 44 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe).
The **`Fedora-Recipe` wiki slug remains valid**, as does the repository's
**`k3-com260-fedora-howto/` directory**. The generated wiki recipe supplies
the documented checkout-path correction and source-link presentation
adaptations; the
[protected standalone how-to](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md)
and its helpers, image pins, configuration and patch bytes stay preserved.
Use that recipe's commands rather than mixing them with the Fedora 45 recipe.
This landing page does not maintain another installation command sequence.

## Three distinct Fedora 44 stages

1. **Bootstrap Fedora on NVMe.** The July 31, 2026 Fedora 44 Omni image uses
   `7.1.5-201.0.riscv64.omni.fc44.riscv64`. Its separately prepared bootstrap
   DTB keeps **both `dldo4` and `hub-reset` enabled**. This was not an
   untouched-image boot or proof that either change alone suffices.
   Follow the archived
   [image preparation](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#image-and-prepare-the-nvme)
   and [bootstrap boot](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#boot-the-bootstrap-fedora-host).
   The recipe explicitly says not to launch guests on this bootstrap kernel.
2. **Build and temporarily select the patched KVM host.**
   `7.3.0-rc4-k3-kvm-host-a1` is based on `kvm-riscv/linux` commit
   `a5f72fd298f6bd02e6d30599dafb43cfa16576b6` plus **14 patches**.
   The fixed order is five PHY-helper patches, six PCIe-controller patches,
   two CoM260 PCIe DT patches, and the isolated `dldo4` patch; it does not
   include the unrelated USB/hub series.
   The [kernel provenance record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md)
   retains the source pin, expected patched tree, configuration, toolchain,
   patch origins, authorship, licenses and status limits.
   Follow the [host transition and checks](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#build-and-install-the-kvm-host),
   not a newer unpatched kernel substitution. An AIA host banner or
   `/dev/kvm` alone is not a guest result.
3. **Run the persistent Fedora guest on that host.** The recorded combination
   is Fedora QEMU **`10.2.2-1.fc44`**, the June 4, 2026 Fedora 44 Cloud image,
   guest kernel `6.19.8-200.0.riscv64.fc43.riscv64`, **4 vCPUs / 4 GiB**,
   and CPU model/filter
   **`host,svpbmt=false,zicbom=false,zicbop=false,zicboz=false`**.
   The guest kernel's `fc43` suffix is intentional in this Fedora 44 image
   record. Sstc stays enabled, and the recipe's extra kernel arguments remain
   compatibility workarounds, not tuning suggestions. The helper's generic
   bare-`host` default is not the tested full-Fedora recipe.
   Follow [guest preparation and operation](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#prepare-and-run-the-persistent-guest)
   with the complete recorded environment on every launch. Keep `base.img`
   and `overlay.qcow2` together; `resume` boots that persistent disk again,
   not a saved RAM snapshot.

## Evidence and public archive

The [canonical KVM result matrix](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU#published-guest-results)
keeps the full host/QEMU/guest tuples, CPU settings, storage/persistence,
network checks and unknowns separate for **PLIC** and the tested
**`aplic-imsic` AIA alternative**. Do not transfer every PLIC check into
the AIA row: the public AIA statement does not provide independent per-mode
storage, persistence or networking check outputs.

The [public guest capture set](https://github.com/xjamesmorris/k3-com260-info/tree/57400da095e944c75e63154b1c187e18a3ac3359/files/f44-kvm-guest-01)
includes [guest dmesg](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/files/f44-kvm-guest-01/k3-dmesg.txt),
[fastfetch](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/files/f44-kvm-guest-01/k3-fastfetch.txt)
and [inxi](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/files/f44-kvm-guest-01/k3-inxi.txt).
These are consistent with the recorded PLIC guest, not a new test or an AIA
capture. They show the guest kernel, four CPUs, about 4 GiB RAM, virtio
storage, a mounted Btrfs root, an active network interface and an SSH
terminal. They do not independently establish the host launch/QEMU package,
overlay backing relationship, forwarding/tunnel path or clean shutdown/resume.
Those procedure/result statements and their limits remain in the
[pinned how-to](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md#prepare-and-run-the-persistent-guest)
and the matrix, not inferred from a system-summary screenshot.

The complete [historical bundle](https://github.com/xjamesmorris/k3-com260-info/tree/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto)
is pinned here to public baseline
`57400da095e944c75e63154b1c187e18a3ac3359`.
Its checksums and source/patch pins are historical inputs, not invitations
to silently refresh them. The
[worked Fedora guest report preparation](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream#worked-preparation-fedora-guest-report)
and [dldo4 RFC preparation](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream#worked-preparation-dldo4-rfc)
remain useful historical development examples. Bundling local drafts does
not imply their submission or upstream acceptance.

## Scope and safe reuse

The exact Firefly carrier PCB revision was not recorded. These observations
do not establish another carrier, UEFI/libvirt route, newer image/kernel/
toolchain combination, display or external USB support, suspend, VFIO, or
long-duration stability. The historical stages ran on hardware, but the
portable bundle was **not rerun end to end**. There is no production or
hostile-guest isolation claim.

The older route remains usable **as recorded**, with its existing checks
and stop conditions; archive status is neither a claim of current security
nor a promise that pinned downloads remain available. Keep the bootstrap on
a trusted isolated LAN and change the shipped credentials. All U-Boot boot
selections are temporary: never save the environment. Preserve working
firmware; use [maintained recovery guidance](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery)
only when recovery is actually needed. For evidence terminology and dates,
see [Status and sources](https://github.com/xjamesmorris/k3-com260-info/wiki/Status-and-Sources).

## Technical notes

**Applies to:** The September 25, 2026 Fedora 44 route on an 8 GiB K3-CoM260 and Firefly carrier, exact PCB revision unknown; Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot, NVMe and a Linux workstation, with the pinned host/guest stack above.

**Evidence:** Preserved public how-to, source/configuration and patch provenance, guest captures, and separately bounded PLIC/AIA result statements at public baseline `57400da095e944c75e63154b1c187e18a3ac3359`; no Fedora 45 guest result is asserted.

**Source review:** 2026-10-19.

**Hardware observation:** 2026-09-25 historical Fedora 44 bootstrap, patched KVM host and persistent Fedora Cloud guest snapshot; no new hardware testing for this archive.

**Destructive operations:** None on this page. The linked installation overwrites the selected NVMe disk; guest operation writes the persistent guest disk. Factory recovery erases NOR and UFS, including the saved environment. Archive access authorizes none of these operations.

**Previous:** [Ecosystem and resources](https://github.com/xjamesmorris/k3-com260-info/wiki/Ecosystem-and-Resources).
**Next:** [Status and sources](https://github.com/xjamesmorris/k3-com260-info/wiki/Status-and-Sources).
**Start again:** [Home](https://github.com/xjamesmorris/k3-com260-info/wiki/Home).
