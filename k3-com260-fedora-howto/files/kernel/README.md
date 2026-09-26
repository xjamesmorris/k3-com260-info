<!-- SPDX-License-Identifier: GPL-2.0-only -->

# K3 KVM host kernel payload provenance

This directory is the fixed kernel input set used by
`../../scripts/build-k3-kvm-host.sh`. It contains one configuration seed and
14 patch files; it is not a second build or installation guide.

## Source snapshot

- Public source remote: <https://github.com/kvm-riscv/linux.git>
- Provenance branch: `riscv_kvm_fixes`
- Exact source commit:
  `a5f72fd298f6bd02e6d30599dafb43cfa16576b6`
- Public commit:
  <https://github.com/kvm-riscv/linux/commit/a5f72fd298f6bd02e6d30599dafb43cfa16576b6>
- Expected tree after all 14 patches:
  `a5f77b5acef26d8975fe756512edbd2413fa1239`

The branch name records provenance only. The builder requests the exact
commit and checks out that object even if the branch later advances. If the
server no longer supplies the pin, the recipe fails rather than selecting a
newer commit or changing the expected tree.

The patches are applied in this exact order:

| Order | Directory | Count | `git am` mode |
| --- | --- | ---: | --- |
| 1-5 | `phy-bulk-v3/` | 5 | `--no-3way` |
| 6-11 | `pcie-v6/` | 6 | `--no-3way` |
| 12-13 | `com260-pcie/` | 2 | `--3way` |
| 14 | `dldo4/` | 1 | `--3way` |

## Patch origins and status

- `phy-bulk-v3/` is Inochi Amaoto's posted five-patch PHY bulk helper
  series v3. Cover Message-ID:
  `<20260923023304.78428-1-inochiama@gmail.com>`.
  Archive: <https://lore.kernel.org/linux-phy/20260923023304.78428-1-inochiama@gmail.com/>
- `pcie-v6/` is Inochi Amaoto's posted six-patch K3 PCIe controller series
  v6. Cover Message-ID:
  `<20260923015016.64069-1-inochiama@gmail.com>`.
  Archive: <https://lore.kernel.org/linux-pci/20260923015016.64069-1-inochiama@gmail.com/>
- `com260-pcie/` is a local technical draft, not a claim of an emailed or
  merged series. Patch 1 retains Inochi Amaoto's authorship and derives from
  the PCIe portion of Message-ID
  `<20260727094726.890179-3-inochiama@gmail.com>`. Patch 2 retains Jennifer
  Berringer's authorship and its source link:
  <https://github.com/spacemit-com/linux-6.18/commit/c4a0701a564678fb1973df9ac5e7e8cce05c3571>.
  Both patches preserve `Assisted-by: LLM` and still require human
  authorship and DCO decisions before any submission.
- `dldo4/` is James Morris's unsubmitted RFC draft from public review commit
  `e5c5b7735439e40eb8ed6522174bc9a760c99c5d`:
  <https://github.com/xjamesmorris/kernel-ark/commit/e5c5b7735439e40eb8ed6522174bc9a760c99c5d>.
  It has no posted Message-ID, preserves `Assisted-by: LLM`, and contains no
  human `Signed-off-by`.
- The local DTS drafts were prepared against public SpacemiT development
  history from
  <https://git.kernel.org/pub/scm/linux/kernel/git/spacemit/linux.git>.

The copied patch bytes, authors, existing license declarations, and existing
trailers are unchanged. This provenance page is GPL-2.0-only; bundling the
patches does not replace or alter the licenses of the Linux files they
modify. No new sign-off, review, test, email, or merge claim is added here.

## Configuration and recorded build

`config.seed` is the retained configuration from the successful
`7.3.0-rc4-k3-kvm-host-a1` build:

```text
SHA-256: 3a39faf6f915f18dc1d9f0d4035606fe0ee1f8e8ae1e41729fb0730cb01aaef8
Build tuple: ARCH=riscv LLVM=1 LLVM_IAS=0 CROSS_COMPILE=riscv64-linux-gnu-
Compiler/linker: Clang and LLD 22.1.8
Assembler: GNU assembler 2.46.1
pahole: 1.30
```

The builder preserves the recorded KVM, module, GNU-assembler, and split
module BTF guards.

## Bundle manifests

Each `SHA256SUMS` is relative and covers only the patch files shipped in its
directory. Patch hashes are unchanged from the recorded successful host
build. Manifest hashes intentionally changed because cover letters, obsolete
PHY v2 dependencies, unrelated paths, and absolute local paths were removed:

| Directory | Bundle manifest SHA-256 | Historical manifest SHA-256 |
| --- | --- | --- |
| `phy-bulk-v3/` | `c9d26e69a1f6d6ada3037e3daa7717a94e6e957031ba6fedf1c38da7c4a8b9f7` | `91a43cc1958af805b77d6e8e72ab99eab533f0bd9a0fcae6047e582eb0e1362d` |
| `pcie-v6/` | `47c9ce11a0dd131c5971fe0c7d0cdcb49e09dbcd981f94201eb5dbe42c1d7f35` | `c9b57c7853f1f7c6285824c31e96a2015d28735dc6295463a108bddab81d4c92` |
| `com260-pcie/` | `f82a925bbfbc030fb053498ee7ab06aad6d59d5abac166faf99d45b7c89d0a11` | `44fbd2a0ccd6eb324a495b524ccfdd2c55849beece901e70c018462480cff3e2` |
| `dldo4/` | `7a15254c8964c88e5f9f5d976636d505c6112175e8c1b6b519f74a8848e5cfa7` | `da561689e873a9c28f8a919bb5c6e2871181bc5262280d889ed3d5b0d082885c` |

The bundle manifests themselves were not used in the historical hardware
run. The minimally adapted helpers retain that run's tested core behavior,
but this new package layout and exact-object fetch path have not been rerun
end to end on hardware.

## Refresh policy

The source and patch pins are a dated snapshot and may become stale. There is
no automatic drift. A refresh must deliberately select reviewed public
source and patch revisions, preserve author and license metadata, regenerate
the four relative manifests from the same fixed 5/6/2/1 allow-lists, replay
all 14 patches in isolation, record the new expected tree, and repeat the
appropriate build and hardware validation before making new test claims.
