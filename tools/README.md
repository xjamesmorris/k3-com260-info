# K3-CoM260 tools

Tools for working with the [SpacemiT K3](https://www.spacemit.com/) RISC-V
compute module — developed and tested against a **K3-CoM260** on a Firefly
carrier board.

Currently one tool: **`k3-flash-bianbu.sh`**, which factory-flashes a board
from an official Bianbu K3 release tarball using plain `fastboot`.

> **This erases the board.** It rewrites the NOR firmware and wipes every UFS
> partition, including the environment. An attached NVMe drive is *not*
> touched. Do not run it against a board whose contents you need.

## Why

The vendor flow uses **TitanFlasher**, a GUI tool. Every Bianbu release
tarball ships a `fastboot.yaml` describing the flash recipe TitanFlasher
follows, so the same result is reachable with stock `fastboot` and a shell
script — scriptable, reviewable, and usable over SSH on a headless host.

This script is a faithful translation of that `fastboot.yaml`. When the two
disagree, the yaml in your tarball is the spec.

It recovers a bricked board: recovery entry is handled by the BootROM, so it
does not depend on anything already on the module.

## Requirements

`bash`, `fastboot`, `tar`, and coreutils (`sha256sum`, `timeout`, `df`).
`curl` is needed only when passing an `https://` URL.

```sh
sudo dnf install android-tools     # Fedora
sudo apt install fastboot          # Debian/Ubuntu
```

Non-root use needs udev rules granting access to the board's USB IDs. Without
them the device appears in `fastboot devices` with `no permissions`.

## Putting the board in recovery

The flash cannot start until the module is in BootROM recovery mode. On the
Firefly carrier's 12-pin header:

1. Hold **FC_REC** (pin 10) shorted to **GND**.
2. Power on the board — or, if it is already powered, pulse **RST** (pin 8)
   to GND.
3. Release FC_REC.
4. Connect the USB-C port to your host.

Confirm with `fastboot devices`. The board enumerates as
`???????????? DFU download` — **the blank serial is normal**, not a fault.

## Usage

From the repository root, run `cd tools` before using the commands below.

```
k3-flash-bianbu.sh [--check | --register-image] [--rm] [--download-dir DIR]
                   <image-dir | release.tar.gz | https://…tar.gz>
```

The image argument takes three forms, and the last two are equivalent once
the bytes are on disk:

```sh
# 1. An already-untarred release directory
./k3-flash-bianbu.sh /path/to/untarred-release/

# 2. A release tarball — verified, then extracted to images/<release>/
./k3-flash-bianbu.sh ~/downloads/Bianbu-Minimal-K3-v4.0.1-20260521183730.tar.gz

# 3. An https URL — downloaded first, then treated as a local tarball
./k3-flash-bianbu.sh https://archive.spacemit.com/…/Bianbu-Minimal-K3-v4.0.1-….tar.gz
```

| Flag | Effect |
|---|---|
| `--check` | Run every verification step — manifest, download, extraction, contents — then stop without flashing. Works without `fastboot` installed. |
| `--rm` | Delete `images/<release>/` after a **successful** flash. Archive mode only; the tarball itself is never deleted. |
| `--register-image` | Verify a tarball and pin it in the manifest. No flash. See below. |
| `--download-dir DIR` | Where an `https://` URL is saved. Default: `../downloads` relative to the script. |

Releases are published at
<https://archive.spacemit.com/image/k3/version/bianbu/> (there is also a
[JS file browser](https://spacemit.com/community/resources-download/Images%20Collects/K3/Bianbu)).

Extractions land in `tools/images/` relative to the repository root, which is
gitignored — a full release is
several GB, and the LXQt rootfs alone is 8 GB. Re-running against the same
tarball reuses an existing extraction instead of unpacking it again, so
retrying after an interrupted flash is cheap.

### Verifying before you write

A failed flash can leave a board unbootable, so everything is checked before
the first byte is written:

- **The tarball** is matched against `k3-image-manifest.txt` by size and
  sha256. Size is compared first, so a truncated download fails instantly
  rather than after hashing several GB. A mismatch is fatal — a corrupt image
  is never flashed. An unrecognised *filename* is not fatal (new releases
  appear all the time); it warns, scans the archive for unsafe member paths,
  and prints a ready-to-paste manifest line.
- **The extracted tree** must contain every file the flash sequence uses,
  each non-empty — which also catches a truncated extraction from a full disk.
- **Extraction is atomic.** Unpacking happens in a hidden `.partial`
  directory that is renamed into place only on success, so `images/<release>/`
  can never exist half-populated. Interrupting it leaves nothing behind.

Downloads are atomic the same way, so a file already in the download
directory is always a complete one and gets reused.

### Registering a new release

```sh
./k3-flash-bianbu.sh --register-image <tarball or https URL>
```

This verifies the archive and appends its `sha256  size  filename` line to
`k3-image-manifest.txt`. To be pinned, an archive must pass a member-path
safety scan *and* contain every file a Bianbu K3 release is expected to
have — so an unrelated or truncated tarball cannot be registered by mistake.
Re-registering an already-pinned name re-verifies it rather than adding a
duplicate.

The manifest is a plain data file: `#` comments, then three whitespace-
separated fields per line. Adding a release never requires touching the
script.

## What gets flashed

Bootstrap runs first: if the board answers as BootROM, `FSBL.bin` and then
`u-boot.itb` are staged into RAM, each followed by re-enumeration on USB. If
the board is already past BootROM — say you are re-running after a partial
flash — that stage is skipped automatically.

Next the EC firmware (`ec.bin`), the board-management MCU handling power
sequencing, buttons and fan. It is flashed through an `oem ec:flash` side
channel, and **a refusal here is expected and non-fatal** when the EC is
already current, matching `skip_fail` in the vendor yaml.

Then the partition tables and payloads:

| Target | Source | Medium |
|---|---|---|
| `mtd` | `partition_4M.json` | module NOR layout |
| `gpt` | `partition_universal.json` | UFS layout |
| `bootinfo` `fsbl` `env` `esos` `opensbi` `uboot` | `bootinfo_spinor.bin`, `FSBL.bin`, `env.bin`, `esos.itb`, `fw_dynamic.itb`, `u-boot.itb` | NOR |
| `bootfs` `rootfs` | `bootfs.ext4`, `rootfs.ext4` | UFS |

`bootinfo_spinor.bin` is the correct variant for NOR boot; the `_block` and
`_spinand` variants in `factory/` are for other boot media. There is **no
`esp` partition** in the K3 universal layout — the ESP contents live inside
`bootfs`, and `fastboot flash esp` fails with `can not find partition or
devices`.

`rootfs` is the slow step, taking minutes. When the script finishes,
power-cycle the board and watch the serial console at **115200 8N1**.

## Troubleshooting

**It sits at "Waiting for fastboot device".** No board is visible on USB.
Check `fastboot devices`: empty means the module is not in recovery — redo
the FC_REC sequence above and confirm the USB-C cable carries data, not power
only. An entry reading `no permissions` means udev rules are missing. The
script gives up after about two minutes rather than hanging forever.

**"EC stage nacked" / "EC flash nacked".** Benign. An up-to-date EC refuses
the write and the script continues, by design.

**`avb footer` warnings, or `Invalid sparse file format at header magic`.**
Cosmetic. `fastboot` proceeds to send sparse chunks correctly.

**"exists but was not extracted from this archive".** A directory in
`images/` has the name of your release but does not carry a stamp proving it
came from that exact archive — typically an older or hand-made extraction.
The script refuses to guess; remove that directory and re-run.

**Re-running after a failed flash.** Safe, and the intended recovery path.
The board may need the FC_REC sequence again if it no longer boots. An
extraction is kept on failure precisely so a retry does not re-unpack it.

## Status

| Image | Pinned in manifest | Flashed on hardware |
|---|---|---|
| `Bianbu-Minimal-K3-v4.0.1-20260521183730` | yes | full flash OK, boots from UFS |
| `Bianbu-LXQt-K3-v4.0.1-20260521185240` | yes | not yet recorded |
| `Bianbu-LXQt-K3-v4.0.4-20260717093818` | yes | started, outcome not recorded |

Only the K3-CoM260 has been tested. Other K3 modules may differ in NOR size
or partition layout — the vendor yaml selects partition tables dynamically
from `getvar mtd-size`/`blk-size`, whereas this script currently hardcodes
the two filenames that suit the CoM260.

`k3-flash-bianbu-HANDOFF.md` holds the development context: hardware and
protocol findings measured on real boards, design rationale, and the list of
unimplemented ideas.

## License

GPL-2.0-only. See [`LICENSE`](../LICENSE).

Copyright © 2026 James Morris.

## Contributing

Bug reports and patches are welcome, particularly hardware results from other
K3 modules and carrier boards.

The flash sequence itself is verified on real hardware, so changes to it need
a hardware test — please say in the PR what you flashed and what happened.
Everything around it (verification, extraction, CLI) can be exercised without
a board using `--check`. Please keep `shellcheck` clean.
