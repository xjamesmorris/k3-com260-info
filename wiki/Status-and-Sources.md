<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Status and sources

This page is for readers evaluating or extending a claim made elsewhere in
the wiki. It explains the source hierarchy, dated project status, and the
distinction between Source review and Hardware observation recorded in each
page's Technical notes. **A source-review date is not a hardware-test date.**
This wiki is a curated guide to a recorded configuration and useful development
work, not a rolling certification of K3 hardware, every Fedora image, or
current upstream Linux.

**F45-first has one tested installation route, not a general
certification.** On October 20, 2026 a fresh F45 installation into two
existing NVMe partitions (p4/p5), made with the public helpers from an F44
maintenance host on p1–p3 of the same disk, was performed end to end. The
recipe's
[readiness and recorded scope](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#readiness-and-recorded-scope)
bounds it: creating the partitions, other maintenance hosts and whole-disk
imaging remain unverified, and no F45 guest workload was tested. No F44
installation or shrink step is a prerequisite, and “default” means
documentation entry points only, not a saved U-Boot change or F44 deletion.

## Source hierarchy

Use the source appropriate to the claim:

1. **F45 commands, pins and recorded behavior:** the maintained
   [Fedora 45 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe)
   is the command authority, with its recorded scope and unverified
   alternatives. The [public result record](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md)
   identifies the performed October 20 fresh installation and the earlier
   October 19 side-by-side work; the
   [exact lock](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/files/sources.lock.json)
   identifies image/package inputs. The
   [support-bundle inventory](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/README.md)
   explains helpers, not another installation recipe. File hashes and offline
   fixtures do not fill the untested-route or guest-evidence gaps.
2. **Archived F44 behavior and commands:** the
   [preserved public snapshot](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md)
   at content commit `57400da095e944c75e63154b1c187e18a3ac3359`, with its
   [kernel input/provenance record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md).
   The generated [Fedora-Recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe)
   remains the sole F44 installation, host-transition and full-guest command
   authority. Its slug and protected `k3-com260-fedora-howto/` source remain
   unchanged; the banner declares the narrow presentation/path adaptations.
   The [F44 archive](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-44-Archive)
   keeps this optional historical route discoverable, not required by F45.
3. **Software semantics, status, and contribution policy:** the exact
   upstream source revision, official documentation, and public review or
   merge record for the project concerned. A posted series, a maintainer
   branch, a merged commit, and a released distribution package are different
   states. A patch URL or vendor status summary alone does not prove all four.
4. **Hardware capabilities and vendor behavior:** the original vendor
   document for the identified module/carrier/revision and firmware family.
   A silicon capability, vendor benchmark, or connector name is not a Fedora
   result or proof that another carrier has the same wiring.
5. **Other public reports:** the original dated account with its board and
   stack, labeled as a community report. Use it to find a question or source,
   not to fill a missing local result. Unpublished material cannot establish
   a public claim without a separately reviewed, publishable evidence record.

For recovery, the
[maintained tools documentation on public `main`](https://github.com/xjamesmorris/k3-com260-info/blob/main/tools/README.md)
is the current command and safety authority. Pinned copies are historical
procedure/result provenance, not the maintained command interface. The
documentation distinguishes a manifest checksum pin from a successful
flash/boot result; never infer the latter from the former.

## Evidence vocabulary

| Label | Meaning | Does not mean |
| --- | --- | --- |
| **Recorded result** | A public record states what happened on named hardware and software, with a date and bounded checks. | Repeated reliability, all peripherals working, a new rerun, or success on another carrier. |
| **Adapted, unverified procedure** | A procedure derived from recorded work but not itself performed, such as the F45 recipe's unverified alternatives, with the changed steps and gaps explicitly identified. | A performed installation, human hardware approval, or permission to promote it as tested. |
| **Upstream/source-reviewed** | Official source or project documentation was checked on the stated review date. Cite the revision when a code-level claim depends on it. | The code was built, booted, benchmarked, or tested here. |
| **Vendor-reported** | A vendor document describes a capability, procedure, or measurement. | Independent reproduction or Fedora support. |
| **Community report** | Identified public prior art from another operator or project. | This kit's result or an upstream endorsement. |
| **Inference / untested idea** | A stated deduction or possible development direction, with its supporting source and open questions. | A working procedure. |
| **Not recorded / not performed** | The public record lacks that detail / this work has not been done here. | Failure, impossibility, or permission to substitute another test's result. |

## F45 host records, October 19 and 20, 2026

The public results cover the **8 GiB K3-CoM260, Firefly carrier, PCB
revision unknown**, Linux workstation, NVMe and **Bianbu Minimal K3 v4.0.1
non-UEFI U-Boot**. In both records F44 stayed on p1–p3 and F45 `/boot` and
Btrfs root were on p4/p5; the saved F44 boot default was retained. On
October 20 the public populate helper, run from that F44 system as the
maintenance host, reformatted p4/p5 for a fresh installation; the
October 19 bring-up preceded the public helpers.

| Stage | Recorded scope | Boundary |
| --- | --- | --- |
| Fresh volume installation (two existing partitions), October 20 | `populate-f45-volumes.sh`, read-only `--check` first, populated existing p4 (ext4 `/boot`) and p5 (Btrfs root) from the pinned image. One 7.2.7 bootstrap boot (login prompt 24 seconds after `booti`), first serial login as `fedora`, an SSH host key verified against serial, the exact COPR build `11035571` install and three attended 7.2.8 boots: login about 22 seconds after `booti`, startup 22.9–23.5 seconds, `running`, no failed units, no FAT mounts. | The partition table, all 116 F44 `/boot` and `/boot/efi` files and the raw Bianbu UFS ESP were byte-identical afterwards. The maintenance host was F44 on the same NVMe. Fan at full speed; host KVM initialization and `/dev/kvm` only. |
| F45 bootstrap, October 19 | Non-official community Beta image `Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz`; `7.2.7-300.0.riscv64.omni.fc45.riscv64`. One attended boot reached expected mounts, network/SSH and host KVM initialization. | The separately prepared bootstrap DTB kept both `dldo4` and `hub-reset` enabled. Not an untouched-image boot or independent test of either property. |
| F45 pinned package update, October 19 | COPR build `11035571`; five binary RPMs for `7.2.8-300.0.riscv64.omni.fc45.riscv64`, installed beside 7.2.7. Three attended pre-fan boots over ten minutes, expected mounts and zero recorded Btrfs device errors, no reported lockup/RCU stall/oops at the checks. | Host initialization and `/dev/kvm` only. No recorded F45 QEMU version, guest launch, CPU workaround, guest networking or persistent shutdown/resume. |
| Whole-disk imaging / partition creation | Writing the raw image to a dedicated disk (`/boot` on p2, root on p3), or creating the two partitions on a blank disk; also other maintenance hosts. | **Not performed.** Listed in the recipe's [unverified alternatives](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#unverified-alternatives), not as a tested walkthrough. |

The exact image hash is
`6f0ebebc251149ba814fcb0e73c2535bc0a65437eff4827bdc4496916a8eebca`.
Binary-RPM identity is build/NEVRA/hash-bound, **not an established source
Git head**. Recorded inspection reported `NOKEY`; the lock is not independent
signature verification. The original SRPM URL was unavailable during the
October 19 review; it is provenance-only, not a required installation input
or permission to substitute a differently hashed SRPM.

Important exceptions remain in the public results. On October 19 one DHCPv4
acquisition took about **7.5 minutes**, and fwupd/udisks2 briefly mounted
retained NVMe/UFS ESPs read-write before the release-scoped workaround. On
October 20, with fwupd masked offline before first boot, no FAT filesystem
was mounted and all four F45 boots had DHCPv4 within about 23–26 seconds,
but F44 then took about 145 seconds (cause not determined). USB3 probing
remained deferred; neither kernel exposed SoC thermal zones, and the fan ran
at full speed. **All cooling-fan work is explicitly deferred**, with no fan
installation workflow, thermal protection or safe unattended-operation
assurance. These short host checks are not peripheral, endurance, security
or thermal qualification.

## Archived F44 baseline, September 25, 2026

The public record identifies a Firefly-sold CoM260 kit with 8 GiB RAM and a
WD Red SN700 500 GB SSD in the 2280 slot, prepared through a USB NVMe
enclosure on a Linux workstation. The `k3-com260-ifx` DT identity and seller
name do **not** establish the exact carrier PCB model/revision.

| Stage in the September 25, 2026 record | What is recorded | Boundary and next reference |
| --- | --- | --- |
| Fedora bootstrap | Fedora 44 Omni July 31 image; `7.1.5-201.0.riscv64.omni.fc44.riscv64`; Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot; Fedora root on NVMe. The prepared bootstrap DTB keeps both `dldo4` and `hub-reset` enabled. | Not an untouched-image boot or an independent test of each property. Use the [F44 archive](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-44-Archive). |
| KVM host transition | Side-by-side install and temporary boot of `7.3.0-rc4-k3-kvm-host-a1`, from public `kvm-riscv/linux` pin `a5f72fd298f6bd02e6d30599dafb43cfa16576b6` plus 14 patches, including isolated `dldo4` and PCIe enablement. | Not pristine/newer mainline; no change to the saved boot selection. The [kernel development reference](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development) explains the historical build, not an F45 requirement. |
| Full Fedora guest | Fedora QEMU `10.2.2-1.fc44`; Fedora 44 Cloud June 4 guest, 4 vCPUs / 4 GiB; persistent disk and the specific CPU/kernel compatibility settings. PLIC path and AIA tested alternative are distinct entries. | See the [row-per-result matrix](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU#published-guest-results) for per-mode unknowns. No transfer of host-only or minimal-guest results into full-Fedora claims. |

These F44 historical stages ran on hardware; the public portable bundle was
**not rerun end to end**. Display, external USB, fan/thermal policy, suspend,
VFIO, long-duration stability, other carriers, UEFI/libvirt, and newer
image/kernel/toolchain combinations are outside that recipe's result scope.
There is no production or hostile-guest isolation claim.

The [public dldo4 RFC](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/dldo4/0001-riscv-dts-spacemit-k3-com260-keep-dldo4-enabled.patch)
is a separate, earlier artifact dated September 22, 2026 PDT. It records one
matched candidate boot, not a stability campaign, and does not separately
date the test. Its public presence does not imply submission or acceptance.
The [preparation example](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream#worked-preparation-dldo4-rfc)
keeps its source/configuration limits separate from the later KVM host.

## External reference context, last checked September 27, 2026

The following external-source review is retained from **September 27**;
October 19 and 20 local result reconciliation is not a new check of these
sites, current support, releases or contribution policies.

**The F44 archive and selected F45 Beta are community-image records, not
official riscv64 architecture support.** In that review, Fedora's
[hardware page](https://fedoraproject.org/wiki/Architectures/RISC-V/Hardware)
described riscv64 as unofficial, emphasized headless development/build
hosts, and listed K3 under Omni. The
[Omni overview](https://fedoraproject.org/wiki/Architectures/RISC-V/OmniKernel)
explains its selected downstream enablement. Support varies by board,
image/kernel, and device; neither page promises every Firefly peripheral.

The [August 3 Fedora 44 respin announcement](https://discussion.fedoraproject.org/t/updated-fedora-44-server-image/198341/1)
identifies the July 31 image and advertises K3 boot support. That is Fedora
community guidance; this kit's recorded route still needed its documented
preparation and dual-property bootstrap workaround.

The [September 25 Fedora 45 announcement](https://discussion.fedoraproject.org/t/fedora-45-risc-v-non-official-beta-images-are-available/202916)
explicitly calls those images **non-official, community-contributed Beta**
artifacts. That label applies to the selected `20260923.2` compose even
though October 19 and 20 local host results are now recorded. It does not
become a final/official compose, an official installation route or a
general Firefly upgrade path. No pin changes merely because a newer
directory or release exists.

For AI, the [source-reviewed brief](https://github.com/xjamesmorris/k3-com260-info/wiki/AI-and-Toolchains)
distinguishes SpacemiT's core capabilities, vendor Bianbu inference reports,
and the absence of a Fedora inference result in this public record.
For upstream work, consult the
[live destination-policy references](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream#destination-ai-use-rules-are-not-interchangeable);
the kernel, QEMU, GCC, LLVM, and llama.cpp impose different requirements.

## When evidence can be expanded

A new result needs an identified module/carrier, firmware/image, exact source
and patch/configuration provenance, commands or public reproducer, observation
date, actual checks and failures, and explicit nonclaims. Hardware work and
publication require separate human decisions. Use
[diagnostics](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits)
to prepare a public-safe record.

Preserve historical results when adding a new row. Do not rewrite a failed
or limited result into success, copy unreviewed logs, or publish private
locators. Original summaries and attributed source links are preferred to
whole translations or reproduced manual figures. The
[LLM policy](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/LLM-POLICY.md)
leaves authorship, understanding, provenance review, DCO certification, and
publication with the human author.

## Technical notes

**Applies to:** This wiki's public evidence, especially the 8 GiB K3-CoM260/Firefly, Bianbu Minimal K3 v4.0.1 non-UEFI, Linux-workstation/NVMe Fedora route.

**Evidence:** Public October 20 and October 19 F45 host results and exact lock, preserved September 25 F44 source/patch/configuration/capture record, and separately dated external references last reviewed September 27. Local reconciliation is not a new external-policy or release-status check.

**Source review:** 2026-10-20.

**Hardware observation:** 2026-10-20 fresh F45 installation into existing p4/p5 partitions: 7.2.7 bootstrap, exact 7.2.8 update and three attended 7.2.8 boots; 2026-10-19 F45 p4/p5 bootstrap and three attended pre-fan updated-host boots, plus 2026-09-25 archived F44 stages. No F45 guest or new hardware run for this review.

**Destructive operations:** None on this page. The linked Fedora installation reformats two selected NVMe partitions; factory recovery erases NOR and UFS. References are not authorization to perform either.

**Previous:** [Fedora 44 archive](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-44-Archive).
**Start again:** [Home](https://github.com/xjamesmorris/k3-com260-info/wiki/Home).
