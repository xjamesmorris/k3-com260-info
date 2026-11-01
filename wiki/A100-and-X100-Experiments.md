<!-- SPDX-License-Identifier: GPL-2.0-only -->

# A100 and X100 experiments

This page collects the November 1, 2026 mixed-hart experiment on one
Firefly-carrier SpacemiT K3-CoM260 IFX for Linux, firmware, Device Tree and
platform maintainers. It supplies the test conditions, inspectable DT
generator, measured results, failure chronology and draft report material.
SpacemiT A100 here means K3 RISC-V cores, not NVIDIA GPUs.

**Experimental and buggy: not a supported, daily, default or unattended
configuration.** Three stall/lockup events occurred in two no-Ziccrse
build boots. A Ziccrse-declaring variant completed one build and soak, but
that declaration is unverified and is not an established fix. Root cause
is unknown; this is not an AI inference or 16-core KVM result.

## Public material and evidence boundaries

| Material | Location and limit |
| --- | --- |
| Detailed report | This page: observations and draft maintainer questions, not a submitted bug report. |
| Test-DT generator | [Public helper](https://github.com/xjamesmorris/k3-com260-info/blob/main/experiments/a100-x100/k3-make-a100-novector-dtb.sh) and [provenance/usage](https://github.com/xjamesmorris/k3-com260-info/blob/main/experiments/a100-x100/README.md). Both variants can be inspected without private workspace access. |
| DT diff | The helper writes an input-specific decompiled `.diff`. This is not a published copy of the original hardware-run diff or binary DTBs. |
| Bounded result summary | [Fedora 45 results](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md#november-1-experimental-a100-harts-with-vector-disabled). Earlier F45 installation/fan records remain separate. |
| Raw captures and build artifacts | Not published. No public console/journal bundle, complete build-tool manifest or minimal reproducer is claimed. Sanitized follow-up excerpts need human review. |

## Tested stack

| Component | Recorded identity |
| --- | --- |
| Module and carrier | One SpacemiT K3-CoM260 IFX, 8 GiB RAM, Firefly carrier; physical PCB revision not recorded. |
| OS and host kernel | Fedora 45 Server prerelease; Omni-packaged `7.3.1-300.0.riscv64.omni.fc45.riscv64`, not a pristine upstream Linux build. |
| Firmware | Vendor U-Boot 2022.10, BSP build 395. SBI reported specification 2.0, OpenSBI implementation ID 1 and implementation version `0x10006`; no rebuilt firmware was tested. |
| Packaged input DTB | `k3-com260-ifx.dtb`, 47,633 bytes; SHA-256 `a096de8c2a6478c9a7f29e01a97f029449e114feba5faae6de8ab0ef726856ef`. It describes eight X100 harts. |
| Test DTBs | `k3-com260-ifx-7.3.1-a100-novector.dtb`, 54,257 bytes; Ziccrse-declaring variant 54,321 bytes. Full original generated-DTB hashes are not supplied here; sizes alone are not identity checks. |
| Loaded kernel and initramfs | Raw `Image`, 63,361,024 bytes; initramfs 53,353,024 bytes. Full artifact hashes are not supplied here. |
| Boot selection | Manual temporary DTB/kernel/initramfs selection from NVMe partition 4; root on partition 5, Btrfs subvolume `root`, `clk_ignore_unused`, serial console `ttyS0,115200n8`. No test DTB was saved in the U-Boot environment. |

The generator's imported SHA-256 is
`b0d46ef4b9538822b0c3c5253e85ff62f31f42b1d8853e8eb3ae87f89f1db455`.
Its structural checks are not a proof that a different packaged DTB is
compatible. This report does not establish an exact source/configuration,
compiler/linker or COPR-build closure for the 7.3.1 binary kernel; those
remain follow-up evidence gaps, not substitutes for the earlier 7.3.0 pin.

## Device Tree changes

The public basis is SpacemiT's `spacemit-com/linux` `k3/hmp-on-7.3`
[commit `558f896383b50843c09a8d229a0cb40fa9d4dc41`](https://github.com/spacemit-com/linux/commit/558f896383b50843c09a8d229a0cb40fa9d4dc41).
The test helper applies the corresponding CPU/cache/topology additions
to the packaged eight-hart DTB, with these experimental differences:

| Area | Change |
| --- | --- |
| `/cpus/cpu@8` through `cpu@15` | Add eight `spacemit,a100`, `riscv` CPUs, hart IDs 8–15, `rv64i` base ISA, Sv39 MMU, per-CPU interrupt controllers and the vendor-derived scalar ISA list. |
| A100 ISA declarations | Omit `v` and every `zv*` extension; the vendor-derived list also has no H or Ziccrse. Retain the other declared features, including `zawrs`, `za64rs`, `sstc`, cache-block extensions and AIA/state-enable declarations. These are DT claims, not independently verified hardware features. |
| Vendor-only property | Do not add `cpu-ai`. No IME/AI userspace path was exercised. |
| L1/cache-block properties | 32 KiB I/D caches, 128 sets, 64-byte cache blocks; 64-byte `cbom`, `cbop` and `cboz` blocks. |
| `/cpus/cache-controller-2` and `cache-controller-3` | Add two unified 1 MiB L2 caches, 1,024 sets and 64-byte blocks; CPUs 8–11 share the first and 12–15 the second. |
| `/cpus/cpu-map` | Add clusters 2 and 3, each with four cores. Existing clusters and X100 ISA declarations are retained. No differentiated CPU-capacity property was added. |
| S-mode IMSIC at `/soc/interrupt-controller@e0400000` | Increase `reg` span from `0x200000` to `0x400000`; retain hart-index bits 4 and guest-index bits 6. Append eight `interrupts-extended` CPU-controller references for S-mode external interrupt 9. |
| Ziccrse variant | Append only `"ziccrse"` to each new A100 ISA list. It changes the reported hardware guarantee, not the hardware itself. Its implementation on A100 is unverified. |

The IMSIC span represents 16 harts, 64 guest files per hart, and 4 KiB per
file; that layout does not establish usable KVM on the mixed host. The
helper verifies preservation of the first eight IMSIC entries and X100
ISA lists, and checks that the only removed lines in the decompiled diff
are the replaced IMSIC `reg` and `interrupts-extended` properties.

The firmware's own control DT already listed CPU nodes 0–15, with vector
and without H on its A100 nodes. That is distinct from the selected Linux
test DT and does not establish a supported mixed-hart Linux configuration.

## What Linux exposed

| Check | Observation |
| --- | --- |
| CPU bring-up | `smp: Brought up 1 node, 16 CPUs`; online `0-15`, `nproc` 16. |
| Core identification | CPUs 0–7: X100 `marchid` `0x8000000058000002`; CPUs 8–15: A100 `0x8000000041000002`. These are core architecture IDs, not individual device serials. |
| Common ISA, no-Ziccrse variant | Compared with the eight-X100 default, `v`, `h`, `ziccrse` and `zv*` disappeared. `AT_HWCAP` was `0x112d`, versus `0x20112d` on the default. |
| Spinlocks and KVM | `Ticket spinlock: enabled`; `kvm [1]: hypervisor extension not available`; no `/dev/kvm`. The variant declaring Ziccrse selected queued spinlocks but still had no RVV or KVM. |
| Topology and scheduling | Four clusters covering 0–3, 4–7, 8–11 and 12–15; all `cpu_capacity` values 1024 despite differing measured scalar throughput. |
| Interrupt delivery | IPIs and NVMe queue interrupts were observed on all 16 CPUs. This is a bring-up observation, not exhaustive timer/IPI qualification. |
| Kernel taint | Zero in the recorded bring-up and completed Ziccrse-declaring build/soak. |

Omitting vector from A100 nodes removes it from the Linux common ISA rather
than providing mixed-length RVV execution. H is likewise absent from the
mixed common ISA. The result is a scalar-only mixed host, not eight extra
KVM-capable cores or an A100 inference backend.

## Scalar compression observations

The recorded `xz -6` sample used a temperature-abort threshold of 85 °C,
which did not trigger:

| Workload | Wall time |
| --- | --- |
| 16 MiB, `-T1`, pinned to CPU 0 (X100) | 15.49 s, 15.42 s |
| 16 MiB, `-T1`, pinned to CPU 8 (A100) | 32.12 s, 32.43 s |
| 256 MiB, `-T8`, pinned to CPUs 0–7 | 22.02 s, 21.99 s |
| 256 MiB, `-T8`, pinned to CPUs 8–15 | 49.27 s |
| 256 MiB, `-T8`, unpinned | 28.06 s |
| 256 MiB, `-T16`, all CPUs | 17.29 s, 17.53 s |

Outputs were recorded as byte-identical across the X100, A100 and mixed
runs, with matching 256 MiB round-trip hashes. One A100 took about 2.1
times as long as one X100; all 16 harts were about 1.26 times faster than
eight X100s for the parallel sample. Unpinned eight-thread execution was
about 28% slower than X100-pinned execution. These few samples do not
establish general throughput or a scheduler fix; input corpus, full hashes
and `xz` package identity are not published here.

The recorded maximum temperatures were 61 °C on cluster0 and 58/55 °C
on the A100 clusters; fan `pwm1` peaked at 177 and 6,923 rpm. Only cluster0
was bound to fan cooling. Monitoring A100 temperatures is not proof of
appropriate A100 cooling policy or thermal/fan-failure qualification.

## Native kernel builds and follow-up

The comparison rebuilt the same Omni kernel SRPM under the packaged 7.3.1
host. The eight-hart build used `-j8`; both 16-hart builds explicitly set
`RPM_BUILD_NCPUS=16` to avoid the board's default RPM memory-based
15-job limit. A guard sampled every 30 seconds and would abort at 85 °C.

| Configuration | Module compression reached | Approximate modules phase | End-to-end result | CPU time | Peak memory | Hottest zone |
| --- | --- | --- | --- | --- | --- | --- |
| Eight X100, queued spinlocks | 6,243 s | 81 min | Completed, 6,974 s, exit 0 | 13 h 15 min | 4.9 GiB | 64 °C |
| Sixteen harts, no vector, ticket spinlocks | 5,012 s | 60 min | Hung during `xz -P16`; no completed build | Not supplied | Not supplied | 67 °C |
| Sixteen harts, no vector, queued spinlocks with Ziccrse claimed | 4,951 s | 60 min | Completed, 5,904 s, exit 0 | 19 h 32 min | 5.8 GiB | 68 °C |

Phase estimates came from 30-second samples of one-minute load averages,
not instrumented per-phase timestamps. The completed 16-hart run took
about 15% less wall time than the eight-X100 run. The two 16-hart runs
reached module compression 61 seconds (1.2%) apart; the ticket run did
not complete, so there is no measured ticket-versus-queued total-time
comparison. Do not replace that failed run with an estimated completion.

The successful queued-spinlock boot ran for 2 h 46 min, including a
58-minute idle/userdb soak after the build. Thirty rounds, approximately
two minutes apart, exercised SSH login, `sudo true`, `getent passwd` and
`userdbctl user` for the test account. No lockup or RCU stall was recorded.
`locktorture` was not run: the matching packaged internal module was
unavailable for this host. This is not a spinlock correctness test.

Reset/autoboot then restored and verified eight X100 harts, `/dev/kvm`,
queued spinlocks, kernel fan control and taint zero. A later separate
one-shot boot of the Ziccrse-declaring variant reached login in about
29 seconds and SSH in about 44 seconds; no lockup, RCU stall or call
trace was reported through 15 minutes. It was left in temporary 16-CPU
mode for the operator, with the saved eight-X100 selection unchanged.
That is not a statement about the board's current live state.

## Failure chronology

The following three events occurred across two no-Ziccrse build boots.
Elapsed times are approximate uptime, not wall-clock timestamps:

| Boot | Uptime | Recorded stop point | System behavior and recovery |
| --- | --- | --- | --- |
| First | About 40–110 s | CPU 9 (A100), `systemd-homed`, user-space `greedy_realloc+0`; RCU stall | Stall ended around Ethernet cable removal. Temporal association does not establish cause or a reliable recovery method. |
| First | About 870–1,200 s | Hard-lockup reports on CPU 10 then CPU 9 (A100), followed by CPU 2 (X100); CPU 10 backtrace at `sock_close+4` | Network failed; console nearly unresponsive. Console input coincided with more output; the system subsequently wedged and was reset. |
| Second | About 5,120–5,150 s | Parallel module compression, `xz -P16`; stalled CPU unidentified | No ARP response and no effect from serial input; reset required. Last persisted journal did not show a kernel warning. |

The internal record uses both roughly 5,120 and 5,150 seconds for the
last hang; no finer timing precision is claimed. The second event's
backtrace was attributed to the systemd userdb stack. The original
task-name and complete register-state excerpts are not published here;
sanitized capture review remains necessary for a formal report.

These observations mean user-visible system unresponsiveness, not proof
that every CPU stopped. Captured records included supervisor-timer trap
status and S-mode interrupts enabled. Reported symptoms included repeated
hard-lockup warnings about 20 seconds apart, lack of timer/IPI progress
on affected harts, and later X100/soft-lockup reports. The journal stopped
persisting during the first boot's later lockup, making the console record
important; silence in the journal is not evidence of no fault.

The two traced stop points were reported near an indirect entry to
`greedy_realloc` and the ftrace patch site at the start of `sock_close`.
This is a diagnostic lead, not evidence that ftrace, systemd or either
function caused the stall. External UART/Ethernet activity coincided with
progress in two events, but causality is not established.

## Investigated hypotheses and remaining gaps

| Question | Evidence and limit |
| --- | --- |
| Time-CSR skew or slow/trapped `rdtime` | Sampled A100/X100 time CSRs tracked at 24 MHz; `rdtime` measured about 8.5 ns on both core types. This did not support those hypotheses; it is not a complete timer/firmware exclusion. |
| Deep idle | No cpuidle driver was present; plain `wfi` and unused broadcast timer were reported. This does not rule out WFI, M-mode or firmware problems. |
| Ziccrse/spinlock choice | One successful Ziccrse-declaring build/soak, one short follow-up; two failing no-Ziccrse build boots. No controlled repeated-run causal test or `locktorture` result. |
| Network delay | An earlier bring-up boot had roughly nine minutes without network reachability. Initially attributed to DHCP; later considered potentially related to the stalls. Cause unresolved. |
| X100-only baseline | No known hangs or recorded lockup/stall warnings in 36 X100-only boots journaled since October 28; the comparison build ran 116 minutes. Unequal workloads/durations and missing journal output preclude a controlled defect-rate claim. |
| Not investigated to a conclusion | M-mode/firmware stalls, HSM/timer/IPI interactions, coherency, `zawrs`/`wrs.nto`, or another ISA/implementation problem. |
| Untested features | A100-pinned minimal reproducer, CPU hotplug, suspend, A100 performance counters, mixed RVV, AI inference, sustained thermal safety and hostile-guest isolation. |

## Draft maintainer report and questions

**Draft subject:** SpacemiT K3-CoM260: intermittent stalls with an
experimental 16-hart no-vector Device Tree

On one Firefly-carrier K3-CoM260 IFX, Fedora 45 prerelease with Omni kernel
`7.3.1-300.0.riscv64.omni.fc45.riscv64` and vendor U-Boot 2022.10
(BSP 395; SBI 2.0, implementation ID 1, version `0x10006`) brought
16 X100/A100 harts online using a temporary test DT derived from the public
SpacemiT topology commit cited above. A100 vector declarations were omitted,
so the common ISA lost RVV and H, and KVM was unavailable.

Two no-Ziccrse build boots produced the three events in the failure table.
A variant declaring Ziccrse completed one build and a 58-minute soak;
this does not establish that the declaration is correct or that it fixes
the fault. Root cause remains unknown, and the tested kernel is downstream,
not pristine mainline. Advice on a reduced reproducer or diagnostic
capture would be useful.

| Audience | Specific questions |
| --- | --- |
| SpacemiT platform/firmware maintainers | Is this mixed-hart topology supported with BSP 395 and the cited IMSIC layout? Which A100 ISA features, particularly Ziccrse and `zawrs`, are implemented and safe to advertise? Are there relevant firmware, HSM, timer/IPI or coherency errata? Which firmware revision and diagnostics would be useful? |
| Linux RISC-V maintainers | Has this combination of RCU/hard-lockup reports, S-mode interrupt status and mixed harts been observed? What would distinguish firmware/coherency/hart-progress failure from a kernel problem? Is an A100-affined userspace reproducer, targeted timer/IPI test or another reduced workload the best next step? |
| DT and scheduler maintainers | Are the CPU/cache/IMSIC declarations and scalar-only common-ISA experiment appropriate? What validated capacity data would be needed for heterogeneous scheduling, given equal reported capacities and unequal scalar throughput? |

This is report-preparation material, not an email already sent or a filed
issue. The human author must review/edit it, verify current recipients and
project policies, and decide what to send. No component is blamed.

## Follow-up material for interested maintainers

The publicly inspectable helper and this page are available without private
files. Further material would need a separately reviewed sanitized bundle:

| Requested material | Current gap or review requirement |
| --- | --- |
| Original DTBs and decompiled diffs | Full run-artifact hashes, exact selected/live DT comparison, and immutable original diffs are not published. The generator is available; generated replacement output must not be called the original capture. |
| Failure excerpts | First RCU stall, CPU 10 `sock_close` backtrace, subsequent hart/lockup reports, trap/status details and elapsed timestamps. Remove unrelated identifiers while preserving register/symbol context. |
| Matched successful-run excerpts | Boot CPU/ISA/spinlock/taint output, build end state, temperature guard and userdb soak results. One success remains one success. |
| Build provenance | Exact host COPR build/package hashes, source/SRPM hash, seed/final configuration, compiler/binutils, build command/environment and workload/input identity are needed for stronger reproduction. Build outputs were deleted after recording their hashes; they are not offered as retained artifacts. |
| Firmware diagnostics | Relevant firmware source/build/configuration and M-mode/HSM/timer/IPI capture are not available in this public report. Vendor guidance is needed before expanding the experiment. |

Do not publish full raw journals, console dumps, workstation paths, host
addresses, device serials or account identifiers merely to provide more
detail. Preserve relevant stack frames, core architecture IDs, public
version/source hashes and relative timing. No hardware was operated while
preparing this page.

## Technical notes

**Applies to:** One 8 GiB SpacemiT K3-CoM260 IFX on a Firefly carrier of unrecorded PCB revision; Fedora 45 prerelease, Omni 7.3.1 and vendor U-Boot 2022.10 BSP 395. Other modules, carriers, kernels and firmware combinations are not established.

**Evidence:** November 1 observed results summarized in the public F45 record, the inspectable experimental helper and SpacemiT's pinned topology commit. Raw captures and complete artifact/tool provenance are not public; hypotheses and proposed diagnostics are not results.

**Source review:** 2026-11-01 for the experiment record and helper; no new general capability/toolchain review.

**Hardware observation:** 2026-11-01 scalar mixed-hart bring-up, compression samples, three no-Ziccrse stall/lockup events across two build boots, one completed Ziccrse-declaring build/soak and one 15-minute one-shot. No new board operation for this documentation.

**Destructive operations:** No boot, flash, disk write or environment change is requested on this page. The linked generator writes local output files only; using its experimental DTB on hardware risks system hangs and loss of in-flight writes and needs attended, separately approved testing.

**Previous:** [AI and toolchains](https://github.com/xjamesmorris/k3-com260-info/wiki/AI-and-Toolchains) | **Next:** [Contributing upstream](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream)
