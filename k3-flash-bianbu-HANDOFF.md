# Handoff: `k3-flash-bianbu.sh`

Context document for continued development. The script factory-flashes a
SpacemiT K3 board (K3-CoM260 verified) from an official Bianbu K3 release
tarball using plain `fastboot` — a scripted replacement for TitanFlasher.

## Provenance & design authority

The sequence is a faithful translation of **`fastboot.yaml` inside each Bianbu
tarball** — TitanFlasher's own recipe. When in doubt, that yaml is the spec.
Its logic: probe `getvar version-brom` → if BootROM, `stage FSBL.bin` +
`continue`, `stage u-boot.itb` + `continue` → EC flash (`skip_fail`) →
`getvar mtd-size`/`blk-size` → flash `partition_{size}.json` tables + all
partitions.

## Hardware/protocol facts (all measured on real hardware)

- **Recovery entry:** hold FC_REC (12-pin header pin 10 → GND) → power on or
  pulse RST (pin 8 → GND) → release → connect USB-C. BootROM-level; works on a
  bricked board. Board shows as `???????????? DFU download` in
  `fastboot devices` — the blank serial is normal.
- **Re-enumeration:** after each `fastboot continue` the device drops off USB
  and returns as the next-stage fastboot device (BootROM → FSBL → U-Boot).
  Fixed sleeps are unreliable AND `fastboot devices` lies (stale node can be
  listed while writes fail with `Write to device failed (No such file or
  directory)` — observed at 3 s). Hence `wait_for_device()`: poll a real
  `getvar` round-trip under `timeout`; any answer including remote `FAILED`
  proves the transport.
- **EC (`ec.bin`):** board-management MCU (power seq, buttons, fan). Flashed
  via `oem ec:flash` side channel. Nacks are expected/benign when already
  current → non-fatal in script, matching yaml `skip_fail`.
- **Partition targets:** `partition_4M.json` = module NOR (`mtd`),
  `partition_universal.json` = UFS (`gpt`). NOR chain partitions:
  `bootinfo fsbl env esos opensbi uboot`; UFS OS: `bootfs rootfs`.
  **No `esp` partition exists** in the K3 universal layout (ESP contents live
  inside `bootfs`) — `fastboot flash esp` fails with
  `can not find partition or devices`; don't add it back.
- `bootinfo_spinor.bin` is the right bootinfo variant (NOR boot); `_block`/
  `_spinand` variants exist in `factory/` for other boot media.
- Cosmetic/ignorable output: "avb footer" warnings, "Invalid sparse file
  format at header magic" (fastboot then sends sparse chunks fine).
- NVMe is untouched by the flash; UFS and NOR env are wiped.

## Verified runs

| Image | Result |
|---|---|
| `Bianbu-Minimal-K3-v4.0.1-20260521183730` | full flash OK, boots from UFS |
| `Bianbu-LXQt-K3-v4.0.4-20260717093818` | in progress at handoff time |

## Implemented since handoff

- **Archive mode:** pass the release `.tar.gz` directly. It is verified
  against `k3-image-manifest.txt` (sha256 + size of each known release,
  size checked first so a truncated download fails instantly) and extracted
  atomically to `images/<release>/` next to the script (gitignored). A
  matching existing extraction is reused — re-runs after a partial flash
  stay cheap. Unknown archive names warn, get a member-path safety scan,
  and the script prints a paste-ready manifest line; appending that line is
  the whole new-release procedure.
- **Preflight:** required files are checked for presence and non-emptiness
  before any fastboot traffic, in both modes. `--check` runs every
  verification step (manifest, extraction, contents) without flashing.
- **`--rm`:** deletes `images/<release>/` only after a fully successful
  flash (archive mode only; the `.tar.gz` itself is never touched).
- shellcheck clean.

## Development ideas (unimplemented)

- Select partition JSONs dynamically via `getvar mtd-size` / `blk-size` like
  the yaml does, instead of hardcoding the two filenames.
- Parse `fastboot.yaml` directly (it ships in every tarball) so new releases
  can't drift from the script.
- `--dry-run` (print the flash commands), `--firmware-only` (skip
  bootfs/rootfs — exactly the firmware-refresh step of the Fedora
  conversion), `--os-only`.
- Trap for a partial-flash state message on error.

## Wider project context

The script exists so a factory restore → Fedora conversion is fully
reproducible for a blog post + public repo. The Fedora side (NVMe root, EFI
zboot unwrap, DTB regulator fix) and the carrier-board restore procedure are
documented separately and will be published alongside this repo. Bianbu
release tarballs:
<https://archive.spacemit.com/image/k3/version/bianbu/> (JS file browser:
<https://spacemit.com/community/resources-download/Images%20Collects/K3/Bianbu>).
Firmware-version caution: the Fedora conversion pins **U-Boot from Bianbu
v4.0.1** ("issues with their firmware builds" on newer) — untested whether
v4.0.4's U-Boot fixes or inherits the `bootefi`+NVMe reset bug seen during
Fedora bring-up.
