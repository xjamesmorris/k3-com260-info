<!-- SPDX-License-Identifier: GPL-2.0-only -->

# AI and toolchains

This page is a source and vendor orientation for developers evaluating
SpacemiT K3 CPU capabilities from the recorded Fedora host. It separates
vendor-described X100 and SpacemiT A100 capabilities from Fedora/KVM evidence
and does not document an AI inference experiment. Use it to frame compiler,
runtime, packaging, or library work rather than as an enablement or
performance guide.

**SpacemiT A100 AI cores are not NVIDIA A100 accelerators.** SpacemiT uses
the name for RISC-V cores inside K3; NVIDIA's
[A100](https://www.nvidia.com/en-us/data-center/a100/) is an unrelated GPU.
Use the vendor-qualified name in reports, searches, and benchmark labels.

## Separate silicon capability from Fedora evidence

| Subject | Public basis | What it establishes |
| --- | --- | --- |
| SpacemiT X100 | [SpacemiT CPU System, section 8.1](https://github.com/spacemit-com/docs-chip/blob/main/en/key_stone/k3/k3_docs/k3_usermanual/08_cpu.md) | Vendor-described high-performance RVA23 cores with RVV VLEN 256 and RVH 1.0. This is a capability description, not a software test. |
| SpacemiT A100 | [SpacemiT CPU System, section 8.2](https://github.com/spacemit-com/docs-chip/blob/main/en/key_stone/k3/k3_docs/k3_usermanual/08_cpu.md) | Vendor-described RISC-V AI cores with IME, RVV VLEN 1024, and explicitly no Hypervisor extension. Do not count them as extra KVM vCPU-hosting cores. |
| Recorded Fedora host and guest | [September 25 public snapshot](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md#recorded-snapshot) | Fedora/KVM operation on the pinned Firefly/NVMe stack. Classifying this as X100 virtualization follows the vendor RVH distinction; the snapshot does not publish a per-hart inventory or a Fedora SpacemiT A100 inference result. |

Do not turn that last row into a claim that a particular number of AI cores
was observed online or offline. There is also **no documented Fedora X100
inference demonstration here**. The practical Linux-workstation/NVMe journey
remains [the Fedora recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe);
working host and guest kernels are not evidence of an inference backend.

There is a concrete kernel-development boundary: the reviewed upstream
[`riscv_v_setup_vsize()` implementation at `fd179f8a05be`](https://github.com/torvalds/linux/blob/fd179f8a05be3ccae366b9b96e176b51fbe54aab/arch/riscv/kernel/vector.c)
rejects differing vector-register lengths in its normal RVV SMP size check. Combined with
SpacemiT's different X100/A100 VLENs, this is a **source-based reason not to
assume mixed-core enablement is a DT-only change**. It is not a new Fedora
hardware observation, a complete diagnosis of vendor scheduling, or an
instruction to online additional cores. This code reference does not replace
the recorded host-kernel pin.

## What the inference references actually show

The upstream llama.cpp
[SpacemiT build guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/build-riscv64-spacemit.md)
documents a SpacemiT-specific RVV/IME CPU build path and labels its example
backend `CPU`. It is a useful starting point for reading the implementation,
not proof that Fedora's packaged compiler, runtime, or kernel provides that
path.

SpacemiT's [ModelZoo](https://github.com/spacemit-com/docs-ai/blob/main/en/compute_stack/ai_compute_stack/modelzoo.md#large-language-models)
records K3 llama.cpp 0.1.1 on Bianbu 4.0rc3, dated May 26, 2026.
Its example selects the vendor CPU backend and preferred AI cores, and
reports a TCM allocation failure followed by heap fallback. The companion
[vendor llama.cpp guide](https://github.com/spacemit-com/docs-ai/blob/main/en/compute_stack/ai_compute_stack/llama.cpp.md)
describes the vendor packages and runtime. These are **vendor-reported
Bianbu results**, not independent Fedora measurements, NPU/GPU offload
evidence, or performance expectations for this 8 GiB kit. No model or
benchmark recipe is reproduced here.

## Useful development work

Choose a narrow question that can produce reviewable evidence. These are
source-backed opportunities and report expectations, not workflows claimed
to have been performed on this board.

| Area | Useful contribution to prepare | Evidence expected |
| --- | --- | --- |
| Portable versus tuned RISC-V code | Reduce a compiler or build-system problem using [GCC RISC-V options](https://gcc.gnu.org/onlinedocs/gcc/RISC-V-Options.html) or [LLVM's RISC-V guide](https://llvm.org/docs/RISCVUsage.html). Keep generic RVV and vendor IME requirements distinct. | Minimal source/IR reproducer; compiler and binutils revisions; target triple, sysroot, ABI, complete ISA/CPU/vector options; expected and actual behavior. An accepted flag is not a runtime result. |
| Runtime feature selection | Review a library's assumptions against Linux [hardware probing](https://docs.kernel.org/arch/riscv/hwprobe.html) and [vector userspace control](https://docs.kernel.org/arch/riscv/vector.html). | Exact kernel and exposed CPU set, discovery API results, thread/vector assumptions, and a reduced correctness test. A marketing profile or aggregate ISA string is not sufficient. |
| llama.cpp RVV/IME correctness or documentation | Start from an existing public issue and the upstream SpacemiT guide; isolate generic-backend behavior from vendor-specific code and dependencies. | Exact project commit, backend, toolchain and build configuration; a reproducer and relevant regression/operator tests. Any performance comparison needs matched workload/configuration and numerical-correctness evidence, not just tokens per second. |
| Fedora packaging/integration | Take a reproducible package or dependency gap to the [Fedora RISC-V SIG](https://fedoraproject.org/wiki/Architectures/RISC-V), rather than describing a vendor binary bundle as a Fedora package. | Package version/source, build failure or missing dependency, licensing/provenance, and the affected Fedora release. |

Online GCC/LLVM documentation can describe development versions newer than
the installed compiler. Record the actual tools; do not silently replace the
[host build's retained toolchain/configuration](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md#configuration-and-recorded-build)
with a new compiler pin.

Before preparing a contribution, read the
[project-specific routes and policies](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream#project-specific-routes-and-policies).
GCC, LLVM, and llama.cpp do not share one AI-use policy. In particular,
llama.cpp requires human-written contribution communication; this page is
orientation, not text to paste into an upstream report.

## Technical notes

**Applies to:** SpacemiT K3 X100 and SpacemiT A100 core capabilities; Fedora development on the recorded K3-CoM260/Firefly host. Other software stacks are references only.

**Evidence:** Public Fedora/KVM record, vendor architecture and inference documentation, and upstream source/documentation review; development opportunities are not completed experiments.

**Source review:** 2026-09-27.

**Hardware observation:** No AI inference experiment recorded here. The cited Fedora/KVM hardware snapshot is 2026-09-25, not an AI result.

**Destructive operations:** None on this page. No model download, inference, affinity change, or CPU-enablement procedure is provided.

**Previous:** [KVM and QEMU](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU).
**Next:** [Contributing upstream](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream).
