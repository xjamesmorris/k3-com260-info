<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Ecosystem and resources

**Applies to:** Reference resources for Fedora/RISC-V developers using K3-CoM260; links to other boards and distributions are not compatibility claims.

**Evidence:** Official project/vendor resources and explicitly labeled public prior art.

**Source review:** 2026-09-27.

**Hardware observation:** Not applicable; resource review only.

**Destructive operations:** None on this page. Linked distribution and vendor instructions may overwrite storage or firmware; they are not validated substitutes for this wiki's route.

Start with [the recorded Fedora route](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora).
Use this directory to find the owner of a problem or understand adjacent
work, not to assemble a new installation recipe from unrelated boards.
The [dated status](https://github.com/xjamesmorris/k3-com260-info/wiki/Status-and-Sources)
separates the Fedora 44 community baseline from Fedora 45 Beta.

## Fedora and upstream development

| Resource | Purpose and relevance | Language and support boundary | Checked |
| --- | --- | --- | --- |
| [Fedora RISC-V SIG](https://fedoraproject.org/wiki/Architectures/RISC-V) and [Omni kernel](https://fedoraproject.org/wiki/Architectures/RISC-V/OmniKernel) | Images, package work, Matrix/Discussion contacts, and the rationale for selected downstream board enablement. First stop for Fedora/Omni integration questions. | English. Community riscv64 effort; support varies by board, image, and feature. Omni is not pristine mainline. | 2026-09-27 |
| [Linux RISC-V](https://docs.kernel.org/arch/riscv/patch-acceptance.html) and [KVM review guidance](https://docs.kernel.org/virt/kvm/review-checklist.html) | Architecture acceptance rules and the tests/userspace evidence expected for virtualization work. | English. Upstream process, not certification of this carrier or a passing KVM test suite. | 2026-09-27 |
| [QEMU RISC-V `virt`](https://www.qemu.org/docs/master/system/riscv/virt.html) and [contributing](https://www.qemu.org/contribute/) | Understand the synthetic guest machine and find bug-report versus email-patch routes. | English. `virt` is not a K3 hardware model; master documentation is not a test of Fedora's recorded QEMU package. | 2026-09-27 |
| [GCC RISC-V options](https://gcc.gnu.org/onlinedocs/gcc/RISC-V-Options.html) and [LLVM RISC-V guide](https://llvm.org/docs/RISCVUsage.html) | ISA/profile, ABI, vector, and vendor-extension references for compiler and build-system work. | English. Check the installed compiler's revision; online development documentation may describe newer features. | 2026-09-27 |
| [RISC-V technical groups](https://riscv.org/developers/technical-committees/) and [RVA23 specification](https://docs.riscv.org/reference/rva23/v1.0/index.html) | Original ISA/profile definitions and the groups maintaining hardware/software specifications. | English. A ratified specification is not evidence that an OS exposes every feature on this board; participation rules vary by group. | 2026-09-27 |

For actionable report and patch preparation, use
[Contributing upstream](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream).
For RVV/IME and llama.cpp, use the
[AI/toolchain brief](https://github.com/xjamesmorris/k3-com260-info/wiki/AI-and-Toolchains),
which separates public code, vendor inference reports, and Fedora evidence.

## Vendor, other distributions, and the China ecosystem

| Resource | Purpose and relevance | Language and support boundary | Checked |
| --- | --- | --- | --- |
| [SpacemiT Bianbu documentation](https://github.com/spacemit-com/docs-bianbu/blob/main/en/root_overview.md) and [K3 CPU documentation](https://github.com/spacemit-com/docs-chip/blob/main/en/key_stone/k3/k3_docs/k3_usermanual/08_cpu.md) | Vendor OS/source-stack orientation and the X100 versus SpacemiT A100 capability definitions. Useful for understanding downstream dependencies. | Linked English documents, with Chinese originals/companions. Vendor instructions and capabilities are not Fedora results; match firmware family and carrier before using them. | 2026-09-27 |
| [Debian riscv64 installation material](https://www.debian.org/releases/stable/riscv64/) | Distribution-level port and installer background for developers comparing userspace or packaging. | English entry point, translations available. The guide warns that riscv64 content is not fully updated/fact-checked; it does not establish this Firefly route. | 2026-09-27 |
| [Canonical's K3 guide](https://ubuntu.com/hardware/docs/boards/how-to/ubuntu_supported/spacemit-k3/) | Ubuntu-specific boot/firmware and installation context; distinguishes Canonical images from vendor Ubuntu images. | English. It states official K3 support starts with Ubuntu 26.10; that prospective support statement is not a local test. Vendor images have vendor support. Do not transplant its firmware or storage steps into Fedora. | 2026-09-27 |
| [openEuler RISC-V SIG](https://www.openeuler.org/en/sig/sig-RISC-V) | Find the distribution's RISC-V community and porting work. | English entry point; linked collaboration may be Chinese. A SIG listing is not a K3 image or Firefly-carrier support claim. | 2026-09-27 |
| [RuyiSDK](https://ruyisdk.org/en/downloads/) | RISC-V package/toolchain environment and tooling discovery, including IDE integration. | English and Chinese. Resource lead only; not a replacement for the recorded Linux-workstation tools or permission to run a board-flashing helper. | 2026-09-27 |
| [PLCT Lab](https://plctlab.org/en/) | Compiler, runtime, emulator, and upstream contribution activity; useful for finding maintainers' work and learning opportunities. | English and Chinese. Project/research community, not the authority for Fedora image support. | 2026-09-27 |
| [RISC-V China](https://riscv.org/risc-v-china/) | RISC-V International's regional community entry point. | Primarily Chinese. Community and standards context, not a distribution or board-support guarantee. | 2026-09-27 |

## Selected public prior art

- [Bo Gan's K3 documentation collection](https://github.com/ganboing/K3-Docs/blob/master/README.md)
  is an English-language, work-in-progress collection with original firmware
  investigation and pointers to vendor documents. Use it as a research lead;
  confirm technical claims against original sources and the applicable
  hardware. Checked 2026-09-27.
- The [public dldo4 RFC](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/dldo4/0001-riscv-dts-spacemit-k3-com260-keep-dldo4-enabled.patch)
  is English-language prior art for a tightly scoped regulator observation
  and a maintainer-facing question. It is retained as a draft; the cited
  record does not establish submission or acceptance upstream. See the
  [worked preparation example](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream#worked-preparation-dldo4-rfc).
  Checked 2026-09-27.

Prefer original-language sources when translations disagree; identify the
document revision and uncertainty rather than silently choosing a pinout or
procedure. These links do not grant permission to copy whole translations,
manual figures, or third-party logs.

**Previous:** [Contributing upstream](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream).
**Next:** [Status and sources](https://github.com/xjamesmorris/k3-com260-info/wiki/Status-and-Sources).
