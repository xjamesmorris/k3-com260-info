<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Status and sources

**Applies to:** This wiki's public evidence, especially the 8 GiB K3-CoM260/Firefly, Bianbu Minimal K3 v4.0.1 non-UEFI, Linux-workstation/NVMe Fedora route.

**Evidence:** Dated public hardware record, pinned public patch/configuration provenance, and separately reviewed official project/vendor references.

**Source review:** 2026-09-27.

**Hardware observation:** 2026-09-25 Fedora/KVM snapshot. No hardware result was added by this source review.

**Destructive operations:** None on this page. The linked Fedora installation overwrites the selected NVMe disk; factory recovery erases NOR and UFS. References are not authorization to perform either.

**A source-review date is not a hardware-test date.** This wiki is a curated
guide to a recorded configuration and useful development work, not a rolling
certification of K3 hardware, every Fedora image, or current upstream Linux.

## Source hierarchy

Use the source appropriate to the claim:

1. **Recorded behavior and commands:** the
   [public Fedora snapshot](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md)
   at content commit `57400da095e944c75e63154b1c187e18a3ac3359`, with its
   [kernel input/provenance record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md).
   The generated [Fedora recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe)
   is the sole installation, host-transition, and full-guest command
   authority. Its banner identifies the preserved source and the narrowly
   declared presentation/path adaptations. Curated pages explain it rather
   than maintain another recipe.
2. **Software semantics, status, and contribution policy:** the exact
   upstream source revision, official documentation, and public review or
   merge record for the project concerned. A posted series, a maintainer
   branch, a merged commit, and a released distribution package are different
   states. A patch URL or vendor status summary alone does not prove all four.
3. **Hardware capabilities and vendor behavior:** the original vendor
   document for the identified module/carrier/revision and firmware family.
   A silicon capability, vendor benchmark, or connector name is not a Fedora
   result or proof that another carrier has the same wiring.
4. **Other public reports:** the original dated account with its board and
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
| **Upstream/source-reviewed** | Official source or project documentation was checked on the stated review date. Cite the revision when a code-level claim depends on it. | The code was built, booted, benchmarked, or tested here. |
| **Vendor-reported** | A vendor document describes a capability, procedure, or measurement. | Independent reproduction or Fedora support. |
| **Community report** | Identified public prior art from another operator or project. | This kit's result or an upstream endorsement. |
| **Inference / untested idea** | A stated deduction or possible development direction, with its supporting source and open questions. | A working procedure. |
| **Not recorded / not performed** | The public record lacks that detail / this work has not been done here. | Failure, impossibility, or permission to substitute another test's result. |

## Dated baseline

The public record identifies a Firefly-sold CoM260 kit with 8 GiB RAM and a
WD Red SN700 500 GB SSD in the 2280 slot, prepared through a USB NVMe
enclosure on a Linux workstation. The `k3-com260-ifx` DT identity and seller
name do **not** establish the exact carrier PCB model/revision.

| Stage in the September 25, 2026 record | What is recorded | Boundary and next reference |
| --- | --- | --- |
| Fedora bootstrap | Fedora 44 Omni July 31 image; `7.1.5-201.0.riscv64.omni.fc44.riscv64`; Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot; Fedora root on NVMe. The prepared bootstrap DTB keeps both `dldo4` and `hub-reset` enabled. | Not an untouched-image boot or an independent test of each property. Start with [installation orientation](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora). |
| KVM host transition | Side-by-side install and temporary boot of `7.3.0-rc4-k3-kvm-host-a1`, from public `kvm-riscv/linux` pin `a5f72fd298f6bd02e6d30599dafb43cfa16576b6` plus 14 patches, including isolated `dldo4` and PCIe enablement. | Not pristine/newer mainline; no change to the saved boot selection. See [kernel development](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development) and [maintenance](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update). |
| Full Fedora guest | Fedora QEMU `10.2.2-1.fc44`; Fedora 44 Cloud June 4 guest, 4 vCPUs / 4 GiB; persistent disk and the specific CPU/kernel compatibility settings. PLIC path and AIA tested alternative are distinct entries. | See the [row-per-result matrix](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU#published-guest-results) for per-mode unknowns. No transfer of host-only or minimal-guest results into full-Fedora claims. |

The historical stages ran on hardware; the public portable bundle was
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

## Current reference status, checked September 27, 2026

**Fedora 44 is the recorded community-image path, not official riscv64
architecture support.** Fedora's [hardware page](https://fedoraproject.org/wiki/Architectures/RISC-V/Hardware)
still describes riscv64 as unofficial, emphasizes headless development/build
hosts, and lists K3 under Omni. The
[Omni overview](https://fedoraproject.org/wiki/Architectures/RISC-V/OmniKernel)
explains its selected downstream enablement. Support varies by board,
image/kernel, and device; neither page promises every Firefly peripheral.

The [August 3 Fedora 44 respin announcement](https://discussion.fedoraproject.org/t/updated-fedora-44-server-image/198341/1)
identifies the July 31 image and advertises K3 boot support. That is Fedora
community guidance; this kit's recorded route still needed its documented
preparation and dual-property bootstrap workaround.

The [September 25 Fedora 45 announcement](https://discussion.fedoraproject.org/t/fedora-45-risc-v-non-official-beta-images-are-available/202916)
explicitly calls those images **non-official, community-contributed Beta**
artifacts. They are a newer testing resource, not an automatically promoted
replacement for the Fedora 44 baseline or a tested Firefly upgrade path.
No kernel, image, toolchain, or firmware pin changes merely because a newer
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

**Previous:** [Ecosystem and resources](https://github.com/xjamesmorris/k3-com260-info/wiki/Ecosystem-and-Resources).
**Start again:** [Home](https://github.com/xjamesmorris/k3-com260-info/wiki/Home).
