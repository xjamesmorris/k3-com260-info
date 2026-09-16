# Repository purpose

This repository is a lightweight public collection of what the maintainer
learns and does with the **SpacemiT K3-CoM260**. It shares and maintains
practical notes, hardware findings, firmware and OS bring-up work, recovery
procedures, small tools, scripts, and patches. Flashing utilities are one
component, not the repository's primary identity. Keep organization and
workflows proportionate to this informal, evolving collection.
The root `README.md` introduces the resource and links to its documentation
and tools.

Give shared scripts and patches enough board-specific context to be reusable:
their purpose, applicable hardware/software versions, usage or application
steps, and what was actually tried. For patches, identify the target project
and revision when known.

The project will also have a GitHub wiki, which the maintainer will frequently
maintain via `gh`. Treat the wiki as part of the public documentation, not just
the files in this checkout. For documentation tasks, establish whether the
target is the wiki or repository files, and keep overlapping facts and
procedures consistent. Prefer the maintainer's `gh`-based workflow for wiki
work; inspect available commands and extensions before assuming a
wiki-specific command exists.

Keep module-level facts separate from carrier-specific details: the existing
recovery-header pin assignments and procedures describe the Firefly carrier.
Do not generalize results to other K3 modules or carriers without evidence.
Hardware findings should identify the relevant carrier and firmware/image
version and distinguish observed results, vendor guidance, and untested ideas.
Public instructions must not depend on unpublished notes or files elsewhere
on the maintainer's machine.

# Existing flashing tool architecture

`tools/k3-flash-bianbu.sh` is a standalone Bash factory-flashing tool, tested
on the K3-CoM260 with a Firefly carrier. It replaces the TitanFlasher GUI with
stock `fastboot`.

- `tools/README.md` documents usage, prerequisites, troubleshooting, hardware
  results, and contribution requirements. `tools/k3-flash-bianbu-HANDOFF.md`
  records measured protocol behavior, design rationale, and unimplemented ideas.
- The release tarball's `fastboot.yaml` is the authority for the flash recipe.
  The script translates it manually; it does not parse YAML. Partition selection
  currently uses the CoM260-specific `partition_4M.json` and
  `partition_universal.json`, rather than the vendor's dynamic size probes.
- Input handling converges from HTTPS URL to local archive to extracted image
  directory. Registration exits before extraction; `--check` exits after
  preflight and before device traffic. Flashing then performs RAM bootstrap,
  EC firmware update, partition-table writes, and NOR/UFS payload writes.
- `tools/k3-image-manifest.txt` supplies release pins independently of the script.
  Add releases through the manifest rather than hardcoding them in Bash.

# Flashing tool commands

Run these from the repository root:

```sh
# Bash syntax check
bash -n tools/k3-flash-bianbu.sh

# Lint (the contribution docs require ShellCheck-clean changes)
shellcheck tools/k3-flash-bianbu.sh

# Single-image preflight: use an existing extracted release
bash tools/k3-flash-bianbu.sh --check /absolute/path/to/release-directory

# Single-archive preflight: includes verification, extraction, and content checks
bash tools/k3-flash-bianbu.sh --check /absolute/path/to/release.tar.gz

# Register a release: validates the archive and modifies the adjacent manifest
bash tools/k3-flash-bianbu.sh --register-image /absolute/path/to/release.tar.gz
```

`--check` works without a board or `fastboot` installed, but may download and
extract multi-GB images; it is not a side-effect-free command preview. Archive
extraction requires free space of at least five times the compressed file size.
The script uses Bash and GNU/Linux utilities, including GNU `stat`/`df`,
`sha256sum`, `tar`, and `timeout`; URL input additionally requires `curl`.

Normal invocation **erases NOR firmware and all UFS contents**, including the
environment; NVMe is untouched. Never use a real flash as an automated check.
Changes to the flash sequence require a hardware result recorded in the PR,
including the image used and observed outcome. Keep manifest-pinned status
separate from successfully flashed/booted status in the documentation.

# Flashing tool conventions and invariants

- Resolve resource paths from `BASH_SOURCE[0]`, not the caller's working
  directory: the script later changes into the image directory. The manifest
  and extraction area are adjacent to the script (`tools/images/<release>/`);
  default downloads are in `downloads/` at the repository root. Both generated
  directories are gitignored; `/images/` remains ignored for the original
  script layout.
- Preserve `set -euo pipefail`, fatal diagnostics through `die()`, and progress
  through `step()`. Expected failures must be handled explicitly.
- `REQUIRED` is shared by archive registration and extracted-content preflight.
  Keep it aligned with every flash payload. Registration checks member names;
  extracted-content checks require each file to be non-empty before any
  fastboot traffic.
- Manifest records are `sha256 size-bytes archive-filename`, with blank lines
  and `#` comments allowed. The basename is the key. Validate the entire
  manifest, rejecting malformed records and duplicate names. Known archives
  must match size first, then SHA-256; unknown names warn and receive a member
  path scan before continuing. Re-registering a known name verifies rather
  than duplicates or overwrites its pin.
- Downloads require HTTPS across redirects. Downloads and extractions use
  hidden `.partial` paths, EXIT cleanup traps, and rename-on-success.
  Reusing an extraction requires a matching archive hash in
  `.k3-extracted-from`, followed by content checks. Preserve failed-flash
  extractions for retry; `--rm` removes only script-created extractions after
  successful flashing, never the source archive or a user-supplied directory.
- Detect BootROM with a timeout-bounded `getvar version-brom` probe. Bootstrap
  stages FSBL, then U-Boot, with `continue` and a readiness probe after each.
  USB readiness requires a real `getvar` response, including remote `FAILED`;
  fixed sleeps or `fastboot devices` alone are unreliable. A remote failure
  of the initial BootROM probe means loaders are already staged.
- EC stage/flash refusals are deliberately non-fatal, matching vendor
  `skip_fail`; do not extend that exception to partition or payload writes.
  NOR uses `factory/bootinfo_spinor.bin`, not the block or SPI-NAND variants.
  Do not add an `esp` flash target: the universal layout stores ESP contents
  inside `bootfs`.
- Keep CLI behavior and hardware findings synchronized with `tools/README.md`
  and the tool's handoff. The handoff's development ideas are proposals, not
  implemented options or established hardware results.
