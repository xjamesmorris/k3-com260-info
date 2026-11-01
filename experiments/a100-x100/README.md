<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Experimental K3 A100/X100 Device Tree artifact

**Experimental and buggy: not for routine or unattended use.** Two boots
of the no-Ziccrse variant produced three stall/lockup events on a
Firefly-carrier K3-CoM260 IFX with Fedora 45 and Omni
`7.3.1-300.0.riscv64.omni.fc45.riscv64`. A separate Ziccrse-declaring
variant completed one build and soak; this is not an established fix.

The dedicated [A100/X100 experiment page](https://github.com/xjamesmorris/k3-com260-info/wiki/A100-and-X100-Experiments)
contains the stack, DT delta, results, failure chronology, and draft
maintainer-report material. This directory supplies the inspectable
generator; it is not an installation or boot recipe.

## Provenance and scope

`k3-make-a100-novector-dtb.sh` is an unchanged import of the maintainer's
experimental helper. Its imported bytes are SHA-256
`b0d46ef4b9538822b0c3c5253e85ff62f31f42b1d8853e8eb3ae87f89f1db455`,
Git blob `749860da8022b64ca7cce3f539e39a3a91130bdd`, executable mode
`100755`. No new license header or authorship trailer has been inserted
into those bytes; the original helper has no SPDX header.

The CPU, cache, cluster and S-mode IMSIC additions derive from SpacemiT's
public Linux change
[`558f896383b50843c09a8d229a0cb40fa9d4dc41`](https://github.com/spacemit-com/linux/commit/558f896383b50843c09a8d229a0cb40fa9d4dc41).
The experiment omits A100 `v`, all `zv*`, and `cpu-ai`. The optional
`--ziccrse` declaration is an unverified claim about A100 hardware, not a
feature that the script can enable.

The recorded input was the 47,633-byte packaged CoM260 IFX DTB with SHA-256
`a096de8c2a6478c9a7f29e01a97f029449e114feba5faae6de8ab0ef726856ef`.
Recorded generated sizes were 54,257 bytes without Ziccrse and 54,321 bytes
with it. Sizes are observations, not validation of a different kernel's
DTB. The helper has structural preconditions but does not enforce this
input hash or establish hardware compatibility for other releases.

## Local generation and review only

Requirements: Bash, `dtc`, `fdtget`, GNU/Linux `diff`, `cmp`, `sha256sum`,
and the ordinary GNU utilities used in the helper. Run from the repository
root, with a reviewed copy of the matching packaged DTB:

```sh
bash experiments/a100-x100/k3-make-a100-novector-dtb.sh INPUT_DTB OUTPUT_DTB
bash experiments/a100-x100/k3-make-a100-novector-dtb.sh --ziccrse INPUT_DTB ZICCRSE_OUTPUT_DTB
```

Replace the uppercase placeholders with local file paths. Choose distinct,
previously absent outputs. Each invocation writes the generated DTB and
its adjacent `.diff`, prints input/output SHA-256 values, and refuses an
existing output or diff. The `.diff` is generated against the supplied
input; it is not a checked-in capture from the November 1 hardware run.
The helper uses shell tracing, so its diagnostics include local file paths.

It does **not** install, transfer, flash, reboot, or change a saved boot
selection. Generated DTBs must not become routine defaults. Hardware
experiments require separate human approval, attendance and recovery
planning; do not interpret successful local generation as a successful
hardware test.

Local checks for this artifact:

```sh
bash -n experiments/a100-x100/k3-make-a100-novector-dtb.sh
shellcheck experiments/a100-x100/k3-make-a100-novector-dtb.sh
```

For this public import, byte identity and executable mode were checked;
`bash -n`, ShellCheck, help/error handling and both generator variants
passed local checks with DTC 1.8.1. A synthetic eight-hart fixture exercised
the additions, preserved X100 declarations, IMSIC wiring, Ziccrse gating,
existing-output refusal and rejection of a 16-hart input. The fixture was
not a packaged board DTB, and these checks were not new hardware tests.
