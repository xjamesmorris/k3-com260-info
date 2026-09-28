<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Kernel and device-tree development

This page is for kernel and device-tree developers working from the pinned
patched Fedora/NVMe host rather than the Omni bootstrap. The useful
development unit is **a source tree, patch sequence, final config, toolchain,
and matched boot set**, not just a kernel version string. Follow
[Fedora-Recipe: build and install the KVM host](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-Recipe#build-and-install-the-kvm-host)
for the exercised commands. The explanations below do not introduce another
build or installation recipe.

## Keep the two kernel lineages distinct

The bootstrap is the packaged Fedora 44 Omni July 31 kernel,
`7.1.5-201.0.riscv64.omni.fc44.riscv64`, with the recipe's separate DTB
containing both `dldo4` and `hub-reset` changes.
[Fedora describes Omni](https://fedoraproject.org/wiki/Architectures/RISC-V/OmniKernel)
as its kernel plus selected vendor-enablement patches. An Omni result is
therefore not automatically a pristine-upstream result.

The later KVM host is an upstream-based **patched** tree, not stock
`7.3.0-rc4` or whichever branch head exists now. The
[public kernel provenance](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md)
fixes these identities:

| Input/output | Recorded identity |
| --- | --- |
| Public source | [kvm-riscv/linux at `a5f72fd298f6bd02e6d30599dafb43cfa16576b6`](https://github.com/kvm-riscv/linux/commit/a5f72fd298f6bd02e6d30599dafb43cfa16576b6) |
| Provenance branch | `riscv_kvm_fixes`; a provenance label, not a floating selector |
| Tree after all 14 patches | `a5f77b5acef26d8975fe756512edbd2413fa1239` |
| Kernel release | `7.3.0-rc4-k3-kvm-host-a1` |
| Configuration seed SHA-256 | `3a39faf6f915f18dc1d9f0d4035606fe0ee1f8e8ae1e41729fb0730cb01aaef8` |
| Recorded tools | Clang/LLD 22.1.8, GNU assembler 2.46.1, pahole 1.30 |
| Build tuple | `ARCH=riscv LLVM=1 LLVM_IAS=0 CROSS_COMPILE=riscv64-linux-gnu-` |

| Order | Bundle | Application mode and provenance |
| --- | --- | --- |
| 1-5 | PHY bulk helpers v3 | `git am --no-3way`; five patches from Inochi Amaoto's posted series |
| 6-11 | K3 PCIe v6 | `git am --no-3way`; six patches from Inochi Amaoto's posted series |
| 12-13 | CoM260 PCIe DTS | `git am --3way`; two local technical drafts retaining their original authorship |
| 14 | dldo4 | `git am --3way`; James Morris's unsubmitted RFC at the exported snapshot |

The provenance page supplies the public origins and per-bundle manifests.
These status labels describe that export, not a current merge-status survey.
The builder verifies the allow-listed patch bytes and prepared **tree**; a
branch name or locally generated replay commit alone is not the content
identity. If the source object is unavailable or the resulting tree differs,
stop rather than advancing the pin or changing the expected hash to make the
check pass.

## Build and stage with the recorded guards

The [exported builder](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/scripts/build-k3-kvm-host.sh)
uses a clean public Linux checkout and a fresh detached worktree/output area.
It verifies the source/patch tree before configuring and keeps build output
separate from source. It retains the seed, final configuration and their
difference; the seed hash is not a substitute for the final-config hash.

| Guard | Reason in this build | What the helper checks |
| --- | --- | --- |
| GNU `as` with Clang/LLD | The recorded module-relocation problem motivated `LLVM_IAS=0`. | GNU assembler configuration and no `R_RISCV_ALIGN` relocations in staged modules. |
| Kernel BTF enabled, split module BTF disabled | The tested Clang/pahole module output was rejected by this kernel. This is not a blanket prohibition on BTF. | `CONFIG_DEBUG_INFO_BTF=y`, disabled `CONFIG_DEBUG_INFO_BTF_MODULES`, and no module `.BTF` sections. |
| Storage and virtualization configuration | NVMe/Btrfs are modules in this configuration; KVM, the relevant interrupt-controller support, and the board PCIe/PHY support must survive config resolution. | Required built-in/module settings after `olddefconfig`, plus the retained config difference. |
| Inspectable matching modules | An Image alone is not a usable release set. | Uncompressed staged modules, matching release/vermagic, required module metadata, and nonzero module count. |
| Specific board DTB | A build for some other board is not this result. | Source properties, then compiled/decompiled `spacemit/k3-com260-ifx.dtb` with enabled PCIe0 and always-on dldo4. |

Upstream's [LLVM build documentation](https://docs.kernel.org/kbuild/llvm.html)
explains that `LLVM_IAS=0` selects a non-integrated assembler and that
cross-compilation then needs the appropriate GNU tool prefix. It explains
the mechanism; it does not extend the local workaround to every compiler
version.

The helper builds the Image, modules, and that target DTB, stages them with
the final config and map, checks release consistency and output hashes, then
completes the stage. Those checks describe the exported implementation, not
a new build result. The historical patch bytes were used for the host;
the portable layout, relative manifests, and exact-object fetch path have
not been rerun end to end.

The initramfs is produced later on the K3, after installing that release's
modules. Use the recipe's separate transfer, installation, and temporary-boot
checkpoints and the
[maintenance identity checklist](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update#keep-each-boot-set-together).
A completed stage is not evidence of an installed or running kernel.

## Source, staged DTB, and live tree are different evidence

| Evidence | What it establishes | Remaining gap |
| --- | --- | --- |
| Pinned source and patch diff | Which DTS/DTSI text was intended for this build. | Whether that source was built, installed, or loaded. |
| Built DTB, its hash, and decompilation | Properties in that compiled file. The builder checks dldo4 and PCIe0 here. | Whether U-Boot selected this file rather than a package DTB or another release. |
| Release-qualified installation and U-Boot load record | The intended file, its load size, and the temporary selection in the recipe. | A filename or load-size match alone is not a complete live-tree identity check. |
| Live-tree evidence from a particular boot | Only the properties/identity actually captured from that running system. | Do not infer a capture from `uname -r`, a source diff, or `/boot/dtb`. |

The exported recipe records explicit U-Boot file selection and sizes, but
does not export a separate live-tree capture/reconciliation helper. Report
that evidence as **not collected** when it is missing; no machine-local
helper is a prerequisite to use this guide. Likewise, do not equate an Omni
package name with the source-built tree or claim a byte-identical DTB after
a decompile/edit/recompile round trip.

### Compilation and schema validation

The exported builder performs a targeted DTB build, decompilation, and
property checks. It does **not** invoke a full schema-validation pass, and
the exported record does not establish one. A compiled DTB is not evidence
that all bindings or all boards passed.

As reference context, the
[upstream schema guide](https://docs.kernel.org/devicetree/bindings/writing-schema.html#running-checks)
distinguishes `dt_binding_check` (binding schemas and examples) from
`dtbs_check` (DT validation). The latter can skip erroneous schemas, so it
does not replace the former. `DT_SCHEMA_FILES` limits the schemas considered;
a targeted pass must name that scope rather than being reported as an
unqualified tree-wide pass. These are validation concepts, not an additional
performed command sequence or a schema-pass claim for this bundle.

## The dldo4 example

The [public RFC patch](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/dldo4/0001-riscv-dts-spacemit-k3-com260-keep-dldo4-enabled.patch)
is a useful example of a small change with bounded evidence:

| Metadata | Public record |
| --- | --- |
| Review commit | [`e5c5b7735439e40eb8ed6522174bc9a760c99c5d`](https://github.com/xjamesmorris/kernel-ark/commit/e5c5b7735439e40eb8ed6522174bc9a760c99c5d) |
| Patch-header date | September 22, 2026; not a separately specified hardware-test date |
| Target | `arch/riscv/boot/dts/spacemit/k3-com260.dtsi` |
| Declared base | `4b98722be2911a922fb29b54adccdee46f6a9f41` |
| Change | Add `regulator-always-on;` to dldo4, retaining `regulator-boot-on;` and its existing voltage constraints. |
| Historical `Fixes` tag | `cfe5c91cb73c` for the initial CoM260-IFX support |
| Authorship/submission boundary | The exported RFC retains `Assisted-by: LLM`, has no human `Signed-off-by`, and has no posted Message-ID. A public review commit is not upstream submission or acceptance. |

The RFC reports that dldo4 was disabled at 31.857578 seconds and CPU1
hard-locked at 44.017326 seconds. In its matched comparison, with source,
configuration, tools, PCIe graph, boot arguments and root filesystem held
constant, the one-property change left the system healthy at 302.45 seconds;
NVMe and the RTL8852BE endpoint remained active. That is one boot, not a
long-duration or wireless-functionality result.

This comparison belongs to the RFC's SpacemiT development-tree-plus-PCIe
setup, not an end-to-end retest of the later KVM bundle. The rail's actual
consumer remains undocumented. The RFC does not validate another carrier or
the Pico-ITX board, and it does not justify importing the bootstrap's
`hub-reset` change into the source-built host.

A useful follow-on record preserves the target/base, dependency order,
small diff, actual config/tool identities, checks performed, exact observed
scope, and remaining unknowns. Preserve existing authorship and trailers;
do not manufacture a DCO certification, review, test, or acceptance claim.
[Contributing upstream](https://github.com/xjamesmorris/k3-com260-info/wiki/Contributing-Upstream)
covers preparation and the remaining human review/submission decisions.
Refreshing source or patch pins requires a separate reviewed build and
appropriate hardware evidence, not just a new version label.

## Sources

- [Pinned kernel input/provenance record](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/README.md) and [preserved Fedora/KVM recipe](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/README.md): historical build, boot, and packaging boundaries.
- [Public dldo4 RFC](https://github.com/xjamesmorris/k3-com260-info/blob/57400da095e944c75e63154b1c187e18a3ac3359/k3-com260-fedora-howto/files/kernel/dldo4/0001-riscv-dts-spacemit-k3-com260-keep-dldo4-enabled.patch): patch metadata and the limited matched hardware observation.
- [Fedora Omni description](https://fedoraproject.org/wiki/Architectures/RISC-V/OmniKernel): downstream lineage, not a new CoM260 test.
- [LLVM build guidance](https://docs.kernel.org/kbuild/llvm.html) and [DT schema guidance](https://docs.kernel.org/devicetree/bindings/writing-schema.html): upstream mechanisms and validation scope, not new local results.

## Technical notes

**Applies to:** The Firefly-sold 8 GiB K3-CoM260 kit and the pinned `7.3.0-rc4-k3-kvm-host-a1` Fedora/NVMe host, built on a Linux workstation and temporarily booted by Bianbu v4.0.1 non-UEFI U-Boot. `k3-com260-ifx` does not establish the carrier PCB revision.

**Evidence:** Public source/patch/configuration pins, exported builder and recipe, and the separate public dldo4 RFC; upstream documentation is reference context.

**Source review:** 2026-09-27.

**Hardware observation:** 2026-09-25 recorded host setup; the dldo4 RFC's individual test date is not specified. No new build/boot result or portable-bundle end-to-end rerun is claimed.

**Destructive operations:** The linked builder writes a fresh workstation worktree/build/stage; the separate installer writes `/boot` and `/lib/modules`, and boot testing resets the board. This page supplies no flashing, disk-writing, or saved-environment procedure.

**Previous:** [Diagnostics and known limits](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits) | **Next:** [KVM and QEMU](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU) | [Home](https://github.com/xjamesmorris/k3-com260-info/wiki/Home)
