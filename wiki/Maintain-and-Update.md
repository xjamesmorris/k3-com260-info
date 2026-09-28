<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Maintain and update

This page is for operators maintaining the recorded Fedora 44 NVMe system
after the bootstrap installation or optional KVM-host transition. It
distinguishes running, installed, and temporarily selected boot sets when
Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot remains the manual selector. Use it
to plan kernel and package changes without assuming a conventional GRUB,
grubby, or RPM-managed boot workflow.

**Installing a kernel does not select it for this direct-boot route.** The
exercised change was a side-by-side installation followed by temporary U-Boot
selection, with the older boot files retained. Use
[Fedora-Recipe: build and install the KVM host](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#build-and-install-the-kvm-host)
for the commands. This page explains the identities and decisions around them.

## Running, installed, and selected are different

| State | What establishes it | What it does not establish |
| --- | --- | --- |
| Running kernel | The host's `uname -r` after Linux boots; the recipe also checks the mounted root filesystem. | Which files an installer just added, or what will boot after reset. |
| Installed candidate | A complete, release-qualified Image, DTB, initramfs, modules, configuration, and `System.map`. | That the candidate has ever executed successfully. A transferred stage is not yet an installation. |
| Temporarily selected kernel | The exact Image, initramfs, and DTB loaded in the current U-Boot session, with the intended root UUID and boot arguments. | A saved default or a successful Linux boot. |
| Existing saved boot path | The board's pre-existing boot environment, which the recipe leaves unchanged. | An automatic return to either Fedora kernel. Reset may return to Bianbu. |

Do not use the RPM database, a BLS entry, or the `/boot/dtb` symlink alone as
evidence of the running or temporarily selected kernel. The
[manual installer](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/scripts/k3-install-manual-kernel.sh)
does not update the RPM database and preserves that symlink.

## Keep each boot set together

The bootstrap release is
`7.1.5-201.0.riscv64.omni.fc44.riscv64`, from the Fedora 44 Omni July 31
image. The later host release is `7.3.0-rc4-k3-kvm-host-a1`, built from the
pinned source plus 14 patches. These are separate stages, not interchangeable
files with similar names.

| Artifact | Bootstrap provenance | Source-built host provenance |
| --- | --- | --- |
| `Image-<release>` | Raw RISC-V Image extracted from that release's packaged zstd EFI zboot `vmlinuz`, with the recipe's header and size checks. | Image built from the pinned, patched tree and final configuration. |
| DTB | Separately named `k3-com260-bootstrap.dtb`, derived from the same package's DTB with **both** `dldo4` and `hub-reset` properties added. Original DTB retained. | `dtb-<release>/spacemit/k3-com260-ifx.dtb`, from the same build as the Image; PCIe enablement and the **dldo4-only** source fix, not the USB/hub series. |
| `initramfs-<release>.img` | The matching packaged initramfs selected during NVMe preparation. | Generated on the K3 by the installer for the new release, after installing its modules and running `depmod`. It is not a workstation-built stage payload. |
| `/lib/modules/<release>` | The modules supplied with the bootstrap system. | The staged modules for that exact kernel release, with the builder's relocation, BTF, and vermagic checks. |
| Configuration and map | Retain package/image identity and the recorded original-file hashes. | Preserve `config-<release>`, `System.map-<release>`, the seed/final-config identities, source pin, patch order, and stage manifest. |

Matching names are necessary, but not sufficient provenance. Keep the
recipe's original-file hashes, verified stage manifest, and the installed
Image/DTB/initramfs hashes and load sizes. A new initramfs has its own
identity: do not describe the workstation stage checksum as verification of
that later-generated file. See
[kernel and device-tree development](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development)
for the source/configuration checks.

## The exercised maintenance sequence

**Build and stage on the Linux workstation.** Follow the
[host-build section](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#build-and-install-the-kvm-host)
with a fresh output area. The expected release and stage checksums are
checkpoints, not optional diagnostics. Stop if the pinned object, 14-patch
tree, release, or manifest cannot be reproduced; choosing a newer branch tip
is a different experiment.

**Transfer, then install beside the running kernel.** The recipe separates
the transfer from the privileged K3-local installation. The
[transfer helper](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/scripts/transfer-omni-baseline-to-k3.sh)
checks selected transferred artifacts; it does not boot or install them.
The installer refuses an already present candidate release and adds the new
set without replacing the running set. Installation is not transactional:
an interruption can leave candidate files behind. Stop at the failure rather
than deleting paths to defeat the guard or assuming a completed install.

**Select the candidate at an attended reset.** Keep serial and physical
reset/power access available. In the same
[host-transition section](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#build-and-install-the-kvm-host),
derive the root UUID from the actual mounted root and record all three
installed file sizes. At U-Boot, compare every load size and check the load
ranges do not overlap. An undefined address, failed load, unexpected size,
wrong UUID, continuation prompt, or malformed boot arguments is a stop point
before `booti`. **Never run `env save` or `saveenv`.**

**Confirm what actually returned.** The recipe checks the running release,
root mount, KVM-related kernel messages, `/dev/kvm` access, and QEMU package
and executable versions. A login prompt alone is insufficient: the earlier
regulator failure occurred after early boot. Only then proceed to the
[recorded guest section](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#prepare-and-run-the-persistent-guest).
A host boot does not by itself establish a guest or persistence result.

## Preserve the fallback and recovery access

Keep the original bootstrap files, its separately patched DTB, matching
initramfs/modules, and their identities. If a candidate fails, the retained
bootstrap's
[temporary boot selection](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#boot-the-bootstrap-fedora-host)
remains the recorded route when those files and the NVMe root are intact.
Do not launch the guest on that older Omni bootstrap kernel.

Retained files are not an automatic rollback system. Reset discards the
temporary selection, not disk writes, and the existing saved path may boot
Bianbu instead. If serial/U-Boot access or the retained files are unavailable,
stop and use the scope and stop points in
[console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery).
Factory recovery is a separate, destructive operation: it rewrites NOR and
all UFS contents, including the environment, but leaves NVMe untouched. It
does not repair or roll back Fedora files on NVMe.

## What a package update does not do

The recipe's
[snapshot-update boundary](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#updating-this-snapshot)
is explicit: a packaged kernel update needs another raw-Image extraction and
deliberate U-Boot selection. Installing newer packages does not automatically
replace the manually selected Image/DTB/initramfs triple with a matched,
tested set. A familiar filename or successful package transaction is not a
new hardware result.

No automatic-upgrade, GRUB/`grubby` selection, DNF transaction-undo rollback,
major Fedora release upgrade, or firmware-reversion procedure was established
by this work. Retaining an older boot set is a recovery measure, not a claim
about its security status. New versions need their own reviewed evidence;
this page does not supply an unperformed upgrade walkthrough.

## Sources

- [Preserved Fedora/KVM record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md) and [kernel provenance](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md): the dated maintenance and artifact contract.
- [Recovery tool and recorded image results](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/tools/README.md): destructive scope; manifest pins are separate from successful flashing.
- [U-Boot `booti` documentation](https://docs.u-boot.org/en/latest/usage/cmd/booti.html): upstream command semantics only, not a replacement for the recorded board-specific boot sequence.

## Technical notes

**Applies to:** Firefly-sold 8 GiB K3-CoM260 kit, Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot, and the recorded Fedora 44 NVMe route. `k3-com260-ifx` is a DT filename, not proof of the carrier PCB revision.

**Evidence:** The public September 25 Fedora/KVM snapshot and its exported build, transfer, and installation helpers; not a general Fedora upgrade procedure.

**Source review:** 2026-09-27.

**Hardware observation:** 2026-09-25 recorded Fedora/NVMe and KVM-host setup; individual historical step dates are not specified. No new hardware run or end-to-end rerun of the portable bundle.

**Destructive operations:** The linked host transition writes new files under `/boot` and `/lib/modules` and requires an attended reset. Reimaging destroys the selected disk; factory recovery rewrites NOR and all UFS contents. Neither is a routine update step.

**Previous:** [Install Fedora](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora) | **Next:** [Diagnostics and known limits](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits) | [Home](https://github.com/xjamesmorris/k3-com260-info/wiki/Home)
