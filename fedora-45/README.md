<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Fedora 45 Beta support bundle

This directory supplies the public pins and minimal package-bootstrap helpers
for the **SpacemiT K3-CoM260, 8 GiB, Firefly carrier**, with **Bianbu Minimal
K3 v4.0.1 non-UEFI U-Boot**. The maintained command walkthrough is the
[Fedora 45 recipe](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe);
this inventory is not a second installation recipe.

**Tested route:** on October 20, 2026 these helpers performed a fresh F45
installation into two existing NVMe partitions, followed by the 7.2.7 boot,
the exact 7.2.8 update and three attended 7.2.8 boots; see
[RESULTS.md](RESULTS.md), which also keeps the earlier October 19
side-by-side record. Creating partitions, other maintenance hosts and
whole-disk imaging remain unverified. Host KVM initialization and `/dev/kvm`
were observed; an F45 guest workload was **not** tested. **All cooling-fan
work is deferred:** this bundle supplies neither fan code nor fan
installation instructions, thermal protection, or assurance of safe
unattended operation; the fan runs at full speed under the pinned kernels.

**Publication check:** the pinned COPR RPM URLs redirect through Red Hat's Pulp
content service to short-lived signed S3 links. The wiki publication checker
accepts that hop only for these five locked RPMs, and only when the S3 object
path is the RPM's pinned SHA-256; the signed link is never recorded. See the
[publication contract](../tools/wiki/README.md#fedora-45-inputs). The helpers
still verify every downloaded RPM against the lock.

The [Fedora 44 archive](../k3-com260-fedora-howto/README.md) remains unchanged,
including its separate source-built host and persistent-guest observations.
F44 is neither an F45 prerequisite nor evidence of F45 guest operation.

## Inventory and provenance

| Path | Purpose |
| --- | --- |
| [`files/sources.lock.json`](files/sources.lock.json) | Public image and five-binary-RPM artifact identities, recorded October 19, 2026. |
| [`RESULTS.md`](RESULTS.md) | Bounded hardware observations, stack, failures and nonclaims. |
| [`scripts/extract-riscv-zboot.sh`](scripts/extract-riscv-zboot.sh) | Standalone validated gzip/zstd EFI-zboot-to-raw-Image extraction. |
| [`scripts/fetch-f45-copr-kernel.sh`](scripts/fetch-f45-copr-kernel.sh) | Download exactly the locked five binary RPMs; no SRPM. |
| [`scripts/transfer-f45-copr-kernel-to-k3.sh`](scripts/transfer-f45-copr-kernel-to-k3.sh) | Verify locally, transfer the self-contained installer bundle over SSH, verify remotely. |
| [`scripts/k3-install-rpm-kernel.sh`](scripts/k3-install-rpm-kernel.sh) | Guarded side-by-side kernel installation; no reboot or saved boot-default change. |
| [`scripts/populate-f45-volumes.sh`](scripts/populate-f45-volumes.sh) | Guarded fresh installation of the locked image into two existing partitions, with a read-only `--check`; no partition-table, other-partition, firmware or U-Boot change. |
| [`scripts/make-bootstrap-dtb.sh`](scripts/make-bootstrap-dtb.sh) | Separately named two-property bootstrap DTB from a packaged DTB, verified by a decompiled diff. |
| [`scripts/verify-f45-bundle.py`](scripts/verify-f45-bundle.py) | Shared standard-library lock, inventory, digest and RPM-header verifier. |
| [`tests/test_helpers.py`](tests/test_helpers.py) | Offline file fixtures and mocked external commands. |

The locked image is the community-contributed, **non-official Fedora RISC-V
Beta** compose `Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz`, with
bootstrap kernel `7.2.7-300.0.riscv64.omni.fc45.riscv64`. Its URL and explicit
`.sha256` sidecar are in the lock. The compressed image's recorded SHA-256 is
`6f0ebebc251149ba814fcb0e73c2535bc0a65437eff4827bdc4496916a8eebca`.
The package helpers do not download this large image.

The first update is
[`@forge-riscv-members/riscv64_omni_kernel`, COPR build 11035571](https://copr.fedorainfracloud.org/coprs/g/forge-riscv-members/riscv64_omni_kernel/build/11035571/),
chroot `fedora-45-riscv64`, kernel
`7.2.8-300.0.riscv64.omni.fc45.riscv64`. The five required packages, in lock
order, are `kernel`, `kernel-core`, `kernel-modules-core`, `kernel-modules`,
and `kernel-modules-extra`. Their recorded hashes came from repository
primary metadata with SHA-256
`e8ea2f04bb1fbf3c4465676cd608b33f0a90d39a8400733e04da4ccc1a823fa3`
and were compared with the downloaded bytes during the recorded work.
These fixed inputs are not an automatic “latest kernel” selection.

The RPM headers carried an OpenPGP key ID, but inspection reported **`NOKEY`**:
the pins do **not** constitute verified publisher signatures. The installer
uses `--nogpgcheck` only after exact digest and metadata verification.
`kernel-7.2.8-300.0.riscv64.omni.fc45.src.rpm` is a provenance identifier,
**not** a required download. Its original URL was unavailable (HTTP 404)
during the October 19 review. No replacement SRPM is silently substituted,
and the exact source Git commit remains **unproven**, represented by `null`.
The helpers do not fetch metadata or an SRPM to repair that provenance gap.

The helper interfaces derive from the recorded bring-up workflow. The exact
helper bytes listed in [RESULTS.md](RESULTS.md) were exercised on hardware on
October 20, 2026; later changes need their own hardware check. No imported
author or sign-off is asserted. The SPDX declarations cover these project
files, not the Fedora image or COPR packages. Human authorship, provenance
review and publication remain subject to [LLM-POLICY.md](../LLM-POLICY.md).

## Interfaces and dependencies

All Bash helpers retain strict error handling and execution tracing
(`set -Eeuo pipefail`, `set -x`), support `--help`, and are executable.
Paths to the verifier, lock and companion helpers are derived from
`BASH_SOURCE`, not the caller's working directory. Keep `scripts/` beside
`files/` when relocating the bundle; the extractor alone is standalone.
Shell helpers run Python in isolated mode so current-directory modules,
`PYTHONPATH`, and the user site cannot influence privileged extraction.
No helper requires private notes, private files or an operator-specific path.

| Interface | Dependencies and privileges | Effects |
| --- | --- | --- |
| `extract-riscv-zboot.sh INPUT OUTPUT` | Bash, Python 3.10+, and `zstd` for zstd input; read access to INPUT and write access to OUTPUT's existing parent. The output filesystem must support hard links. | Validates container/header/bounds, declared decompressed size and raw RISC-V Image header; publishes OUTPUT atomically without overwriting. |
| `fetch-f45-copr-kernel.sh OUTPUT_DIR` | Bash, Python 3.10+, `curl`, `rpm`, GNU coreutils; ordinary workstation user, network access and space for the RPMs. | Downloads exactly five HTTPS binary URLs, checks pinned bytes and RPM metadata, publishes a new directory containing only those RPMs. No install. |
| `transfer-f45-copr-kernel-to-k3.sh BUNDLE_DIR fedora@HOST` | Locally: Bash, Python 3.10+, `rpm`, GNU coreutils, `awk`, `rsync`, OpenSSH client. Remotely: Bash, Python 3.10+, `rpm`, `rsync`, GNU coreutils and `awk`. Ordinary local and remote users; pretrusted host key and working SSH authentication. | Writes only a new bundle below the remote account's quoted `$HOME`; no root privilege or sudo configuration. |
| `k3-install-rpm-kernel.sh BUNDLE_DIR` | Documented RISC-V K3 host; Bash, Python 3.10+, `rpm`, `dnf`, `dracut`, `grep`, GNU coreutils and `zstd` for the packaged zboot image; `dtc`, `fdtget` and `fdtput` when the bootstrap DTB must be generated; `restorecon` used if available. **Root** via the operator's authorized sudo policy. | Changes package database, module tree and `/boot`; retains older kernels, restores `/boot/dtb`, creates missing DTBs/initramfs, extracts `Image-RELEASE` and creates the candidate's bootstrap DTB. |
| `populate-f45-volumes.sh [--check] IMAGE.raw.xz WHOLE_DISK BOOT_PART ROOT_PART` | Linux maintenance host booted from neither target; Bash, Python 3.10+, util-linux, `e2fsprogs`, `btrfs-progs`, `rsync`, `xz`, `zstd`, `dtc`/`fdtget`/`fdtput`, `systemctl`, `udevadm`, GNU coreutils. **Root**, the identity, expected-content, fwupd and acknowledgment variables listed by `--help`, and free space for the decompressed image below `K3_F45_WORK_PARENT` (default `/var/tmp`). | `--check` writes nothing. Otherwise reformats exactly BOOT_PART (ext4 `/boot`) and ROOT_PART (Btrfs `root`, `home`, `var`), copies the image preserving ownership, hard links, ACLs and extended attributes, rewrites only the new fstab, BLS and kernel command-line root references, optionally masks fwupd in the new root, extracts `Image-RELEASE` and creates the bootstrap DTB. No reboot, GPT, other-partition or U-Boot change. |
| `make-bootstrap-dtb.sh PACKAGED_DTB OUTPUT_DTB` | Bash, Python 3, `dtc`, `fdtget`, `fdtput`; write access to OUTPUT's existing parent. | Adds empty `regulator-always-on` to the unique `dldo4` node and `/hub-reset`; publishes OUTPUT without overwriting, and only if the decompiled diff is exactly those two added lines. No fan or I2C change. |
| `python3 -B verify-f45-bundle.py plan` / `release` / `bootstrap-release` / `image` / `check-rpm RPM` / `verify BUNDLE_DIR` | Python 3.10+ standard library; `rpm` for package checks. Ordinary user; read access only. | Reads only the adjacent public lock. Prints locked download rows, releases or the image record, or verifies packages without installing them. |

Fetch destinations and their `.partial` directories must not exist, and the
parent must exist. Fetch failure cleans only its newly created partial
directory, not preexisting files. The extractor likewise refuses existing
OUTPUT, `OUTPUT.partial` or `OUTPUT.payload.partial`; malformed input leaves
no new output or owned partials. Neither helper uses a system scratch directory.

The lock is the reviewed public trust input: preserve it with the scripts.
Package directories must contain **exactly the five named RPM files**, with no
extra files, subdirectories, links or self-declared `SHA256SUMS`. Verification
rejects malformed/duplicate lock keys, wrong identities or URLs, symlinked
or parent-traversing input paths, hardlinked inputs, changed bytes and
mismatched RPM metadata.
Do not edit a checksum list to “accept” a package, or concurrently modify
the trusted lock, helpers or RPM directory during use.

Transfer produces this layout, using a home-relative destination even when
the account's home is not at a conventional path:

```text
~/f45-copr-kernel-11035571/
    files/sources.lock.json
    scripts/verify-f45-bundle.py
    scripts/extract-riscv-zboot.sh
    scripts/k3-install-rpm-kernel.sh
    scripts/make-bootstrap-dtb.sh
    rpms/                         # the five locked binary RPMs
```

Transfer verifies that the remote user is `fedora`, keeps normal SSH host-key
verification, accepts a hostname or IPv4 address (not an IPv6 literal), and
refuses an existing final or `.partial` destination. It
checks available space, stages the complete bundle, re-verifies RPMs against
the transferred lock, then renames. A failed remote stage remains at
`~/f45-copr-kernel-11035571.partial` for manual inspection; there is no broad
remote cleanup or automatic installation.

The installer requires the pinned 7.2.7 F45 bootstrap to be running; it refuses
the saved F44 boot path, other running kernels, a running or installed
candidate, and existing candidate paths **before** calling DNF or writing
system files. Verify the intended F45 root filesystem through the recipe as
well: the kernel release alone does not identify the root. It uses local RPMs with
repositories disabled and the install-only limit removed, not a distribution
upgrade or replacement of the current kernel. It preserves the saved
`/boot/dtb` link across the transaction, including DNF failure; a failed
installation may still leave partial package/system changes and needs human
inspection. It then creates the candidate's **separately named bootstrap
DTB** for the temporary U-Boot route: it copies the running 7.2.7 bootstrap
DTB only when the 7.2.7 and candidate packaged DTBs are byte-identical, and
otherwise generates it with `make-bootstrap-dtb.sh`. If neither is possible
it fails after installation and says to prepare the DTB before any boot. It
prints the DTB decision, SHA-256 values and U-Boot load sizes. Inspect the
generated initramfs for the actual root/storage drivers before any
separately authorized boot.

The volume helper never selects a target for you: it binds the whole disk's
model, serial and size and each target's current filesystem UUID (or
`empty`), and refuses mounts, swap, holders, child devices, other signatures
and a mounted duplicate UUID, repeating those checks just before formatting.
Run `--check` first and record the printed partition numbers; the U-Boot
route loads from the boot partition it reports.

## Local checks and limits

From the repository root, the bounded checks are:

```sh
for script in fedora-45/scripts/*.sh; do
    test -x "$script" || exit 1
    bash -n "$script" || exit 1
    "$script" --help >/dev/null || exit 1
done
shellcheck fedora-45/scripts/*.sh
python3 -B fedora-45/scripts/verify-f45-bundle.py --help
.wiki-venv/bin/python -B -m unittest discover \
    -s fedora-45/tests -p 'test_*.py' -v
```

The tests use individually cleaned regular-file fixtures beneath `tests/`,
synthetic RPM bytes/lock hashes, mocked `curl`/`rpm`/SSH/rsync and denied
system-write commands. They exercise binary-only fetch and failed-digest
cleanup, refusal of incomplete/extra/tampered/unpinned inputs before any
system or `/boot` access, running/installed candidate refusal, malformed
zboot/atomic output, standalone extraction, relocation and quoted remote-home
handling. Volume-population tests cover only argument, environment,
acknowledgment and root refusals before any device access; bootstrap-DTB
tests use the real `dtc` tools on a synthetic DTB and are skipped if those
tools are absent. No real package installation, external network, host
`/boot`, disk/mount operation, I2C, board access or boot is part of
validation.

These offline checks do not prove package signatures, online artifact
availability, hardware compatibility or F45 guest behavior; the hardware
result is the separate October 20 record. Read the canonical recipe and result
limits, and leave attended hardware work and publication to the human
operator.
