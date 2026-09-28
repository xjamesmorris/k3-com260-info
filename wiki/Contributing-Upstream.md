<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Contributing upstream

This page is for readers turning public K3-CoM260/Firefly evidence into an
upstream report or patch. A useful contribution connects **one reproducible
observation, an exact target, and an honestly bounded result**. The page
teaches preparation, not autonomous submission: the human author reviews the
evidence, understands the change, checks provenance, and decides whether and
where to send it. Handling incoming contributions to this wiki/repository is
deferred; helping readers contribute to the projects below is not.

## Worked preparation: dldo4 RFC

The existing
[public RFC patch](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/dldo4/0001-riscv-dts-spacemit-k3-com260-keep-dldo4-enabled.patch)
is a concrete example of turning bring-up into a reviewable question.
It is retained from James Morris's
[public review commit](https://github.com/xjamesmorris/kernel-ark/commit/e5c5b7735439e40eb8ed6522174bc9a760c99c5d),
not evidence that a patch was emailed or accepted.

| Preparation item | What the public artifact supplies |
| --- | --- |
| Target and revision | Linux `arch/riscv/boot/dts/spacemit/k3-com260.dtsi`; RFC base commit `4b98722be2911a922fb29b54adccdee46f6a9f41`. The description identifies SpacemiT `for-next` plus local PCIe enablement, not pristine released mainline. |
| Reproducible observation | On CoM260 IFX, unused-regulator cleanup disabled `dldo4` at 31.857578 seconds; CPU1 hard-locked at 44.017326 seconds, with other CPU and RCU stalls. |
| Single change under discussion | Add `regulator-always-on` to `dldo4`. The patch asks whether an undocumented supply consumer should instead be described; it does not claim to identify that consumer. |
| Recorded comparison | The RFC says source, configuration, toolchain, PCIe graph, boot arguments, and root filesystem were matched. With only that property added, NVMe and the RTL8852BE endpoint remained active and the host was healthy at 302.45 seconds without the reported lockup, RCU stall, panic, or Oops. |
| Exact validation boundary | One candidate boot, not a stability campaign. The endpoint remaining active is not a Wi-Fi throughput result. Pico-ITX was not tested or changed. The RFC explicitly does not request stable backporting because its reproducer depends on PCIe enablement outside released mainline. |
| Missing reproduction detail | The RFC does not embed the matched test's complete configuration, tool versions, or full boot artifacts. Those gaps must not be filled with assumptions. No checkpatch or DT-schema pass is claimed in its text. |
| Authorship and submission state | The [bundle provenance](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md#patch-origins-and-status) records an unsubmitted RFC, no posted Message-ID, `Assisted-by: LLM`, and no human `Signed-off-by`. Preserve existing authorship and trailers. |

**Do not merge this with the earlier bootstrap workaround.** The Omni 7.1.5
bootstrap used both `dldo4` and `hub-reset`. The later
`7.3.0-rc4-k3-kvm-host-a1` has a different public source pin, 14-patch bundle,
and [retained configuration](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/config.seed).
That later successful build is useful integration evidence, but its config
must not be presented as the unpublished identity of the RFC's earlier
matched test.

The next preparation artifact is a human-reviewed, self-contained account
of the intended target and missing reproduction details. Before submission,
the author needs to check current maintainer routing, preserve the PCIe
dependencies, and record any newly performed build, targeted DT/schema,
checkpatch, and hardware comparisons with their actual limits. These are
**remaining expectations, not checks claimed complete here**.
The [kernel/DT development page](https://github.com/xjamesmorris/k3-com260-info/wiki/Kernel-and-Device-Tree-Development)
and [upstream submission guide](https://docs.kernel.org/process/submitting-patches.html)
explain the source/build and review context.

## Worked preparation: Fedora guest report

Use the September 25
[public Fedora record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md)
to prepare an **integration report for Fedora RISC-V**, not a claim that a
new upstream bug has been found. A success baseline is useful; it is not a
bug reproducer or a QEMU patch submission.

| Report artifact | What can be prepared from the public record |
| --- | --- |
| Scope and target | 8 GiB CoM260/Firefly, Bianbu Minimal K3 v4.0.1 non-UEFI firmware, NVMe host; patched `7.3.0-rc4-k3-kvm-host-a1` and Fedora QEMU `10.2.2-1.fc44`. Include the public host source pin and patch order, not just the release string. |
| Guest configuration | Reference the separate [PLIC and AIA result rows](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU#published-guest-results), including the exact guest kernel, CPU filter, Sstc, extra kernel arguments, vCPU count, and RAM. Do not substitute a minimal guest or bare-`host` invocation. |
| Public config and helper provenance | Link the [kernel input record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md), [guest preparer](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/scripts/prepare-riscv-fedora-guest.sh), and [runner](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/scripts/k3-run-fedora-guest.sh). These public artifacts identify the image pins, persistent disk arrangement, and KVM-only launch behavior. |
| Bounded observation | Full Fedora interactive guest operation is recorded; AIA is described as the tested alternative after clean PLIC shutdown. The recipe describes root, virtualization, CPU-count, interrupt, and SSH checks. It does not publish every check's raw output separately for each mode. |
| Unknowns to retain | No per-mode test counts, disk-integrity benchmark, long-duration result, migration/VFIO result, or clean-current-upstream comparison is supplied. Historical stages ran on hardware; the portable bundle was not rerun end to end. |

The executable steps remain in
[the canonical guest section](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#prepare-and-run-the-persistent-guest).
For a new failure, prepare expected versus actual behavior, the first failing
stage, exact package/source identities, and a small public-safe reproducer.
Use the [diagnostic report guidance](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits).
Do not attach private keys, host identifiers, or unreviewed raw logs.

## Project-specific routes and policies

The remaining entries are **official routing and report expectations**, not
QEMU/compiler/llama workflows claimed to have been performed here. Search
the destination's existing reports first. A downstream-only failure should
not be labeled an upstream regression without evidence.

| Owner | Route and useful preparation |
| --- | --- |
| Fedora RISC-V images, repositories, Omni integration | Start with the Matrix/Discussion channels linked by the [Fedora RISC-V SIG](https://fedoraproject.org/wiki/Architectures/RISC-V). The [Omni explanation](https://fedoraproject.org/wiki/Architectures/RISC-V/OmniKernel) identifies selected downstream enablement on top of Fedora. Give image, package, board/carrier, boot method, and failure stage so the SIG can identify the right owner. |
| Fedora package bug or packaging change | Use Fedora's [package-aware bug-reporting route](https://docs.fedoraproject.org/en-US/quick-docs/bugzilla-file-a-bug/) for defects and [dist-git contribution guide](https://docs.fedoraproject.org/en-US/package-maintainers/Pull_Request_Guide/) for changes. Record release, source package and exact version, reproduction frequency, and expected/actual result. A dist-git PR is not permission to perform maintainer-only builds or updates. |
| Linux/RISC-V and KVM | Follow [kernel reporting](https://docs.kernel.org/admin-guide/reporting-issues.html), [patch submission](https://docs.kernel.org/process/submitting-patches.html), and [RISC-V acceptance](https://docs.kernel.org/arch/riscv/patch-acceptance.html). Use the target tree's `MAINTAINERS` and `scripts/get_maintainer.pl` rather than a stale address list. Disclose downstream patches. The [KVM checklist](https://docs.kernel.org/virt/kvm/review-checklist.html) calls for appropriate selftests/kvm-unit-tests and userspace support; list what actually ran and what could not. |
| QEMU | Ordinary bugs use the [GitLab tracker via QEMU's bug guide](https://www.qemu.org/contribute/report-a-bug/); patches use the [email submission process](https://www.qemu.org/docs/master/devel/submitting-a-patch.html) to `qemu-devel`, **not GitLab merge requests**. Distribution-only failures go to the distribution or need upstream reproduction. Supply a direct QEMU invocation, exact accelerator/machine/CPU, host/guest identities, and a reduced reproducer. |
| GCC | Use [GCC's contribution guide](https://gcc.gnu.org/contribute.html) for the appropriate mailing list, tests, ChangeLog, and provenance requirements. Reduce the issue to source plus complete target/ABI/options; distinguish a compiler failure from an unavailable runtime instruction. Test requirements depend on which compiler component changes. |
| LLVM | The [LLVM contribution guide](https://llvm.org/docs/Contributing.html) routes work through GitHub issues/PRs. Prepare a small source or IR reproducer, exact target triple/options and revision, and a relevant regression test. |
| llama.cpp/ggml | Read [CONTRIBUTING.md](https://github.com/ggml-org/llama.cpp/blob/master/CONTRIBUTING.md) and [AGENTS.md](https://github.com/ggml-org/llama.cpp/blob/master/AGENTS.md) first. Check existing work; discuss features before implementation. Fixes need a reproducible issue and regression test; backend/operator work needs the project's numerical-correctness checks. State upstream versus vendor fork and exact backend/build identity. |

For suspected security impact, use the
[kernel security-reporting guidance](https://docs.kernel.org/process/security-bugs.html)
or [QEMU security process](https://www.qemu.org/contribute/security-process/)
instead of assuming an ordinary public issue is appropriate. QEMU currently
requires a GitLab issue marked confidential before submission, not a security
email; its attachments are not themselves confidential and disclosures
eventually become public. Scrub private information before sharing anything.
Record affected revisions, conditions, and a validated reproducer; a crash
alone is not an established vulnerability. The human decides and submits.

### Destination AI-use rules are not interchangeable

As reviewed on September 27, 2026:

- **Linux and this repository:** follow the
  [kernel tool-generated-content guidance](https://docs.kernel.org/process/generated-content.html),
  [coding-assistant guidance](https://docs.kernel.org/process/coding-assistants.html),
  and [repository LLM policy](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/LLM-POLICY.md).
  Disclose meaningful assistance and how it was checked; use the applicable
  `Assisted-by: LLM` attribution. Only a human can certify the DCO with
  `Signed-off-by`. A generated draft or review is not human approval.
- **QEMU:** its [code-provenance policy](https://www.qemu.org/docs/master/devel/code-provenance.html)
  declines contributions containing or derived from AI-generated content.
  Research/debugging assistance is distinguished from putting generated
  output into a contribution. Human review or a sign-off alone does not
  waive that restriction; do not paste this assisted preparation text into
  a QEMU submission.
- **GCC:** the [GCC AI policy](https://gcc.gnu.org/ai-policy.html) declines
  legally significant LLM-generated or derived contributions, with limited
  maintainer-discretion exceptions, including test cases. It also requires
  disclosure for accepted generated content and human submission/DCO.
  Do not assume kernel rules make a GCC patch eligible.
- **LLVM:** the [LLVM AI Tool Use Policy](https://llvm.org/docs/AIToolPolicy.html)
  requires human review, understanding, accountability, and substantial-use
  disclosure. It bars agents acting in project spaces without human approval
  and prohibits using AI to fix issues labeled `good first issue`.
- **llama.cpp:** the live policies linked above require manual review,
  understanding, and disclosure, and prohibit AI-written posts, PR
  descriptions, commit messages, and reviewer responses as well as autonomous
  submissions. The human must write their own contribution communication.

Re-read the destination's policy immediately before preparing and sending
work. Preserve licenses and genuine existing author/review/test trailers;
never manufacture a human sign-off or test endorsement. Submission, issue
creation, email, and publication remain human-controlled actions.

## Technical notes

**Applies to:** Preparing Fedora, Linux/RISC-V, KVM, QEMU, toolchain, and llama.cpp contributions from public K3-CoM260/Firefly evidence.

**Evidence:** Worked preparation examples from the public dldo4 RFC and Fedora guest record; official project routes and policies for other work.

**Source review:** 2026-09-27.

**Hardware observation:** Fedora/KVM snapshot dated 2026-09-25. The dldo4 RFC is dated 2026-09-22 PDT but does not separately date its hardware test. No new tests performed here.

**Destructive operations:** None on this page. Reproduction that boots another kernel or writes storage is separate, attended work; the examples on this page do not authorize it.

**Previous:** [AI and toolchains](https://github.com/xjamesmorris/k3-com260-info/wiki/AI-and-Toolchains).
**Next:** [Ecosystem and resources](https://github.com/xjamesmorris/k3-com260-info/wiki/Ecosystem-and-Resources).
