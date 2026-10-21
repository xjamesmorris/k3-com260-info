<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Fedora 45 Beta on the K3-CoM260: install recipe

This is the canonical command guide for installing the packaged Fedora 45
Beta host on the **8 GiB SpacemiT K3-CoM260 with a Firefly carrier**. It keeps
the working **Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot** and boots Fedora by
temporary, attended U-Boot commands. It needs no F44 installation, F44 kernel
build or private bring-up files.

**Tested route (October 20, 2026):** a fresh installation of the pinned image
into **two existing NVMe partitions** from a Linux maintenance host, then the
7.2.7 bootstrap boot, first login, the exact COPR 7.2.8 update and three
attended 7.2.8 boots, with everything else on the disk verified unchanged.
**On October 21** the exact COPR 7.3.0 upgrade, which adds kernel fan
control, was installed from 7.2.8 and booted once, attended.
See the [result record](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md).
Creating the partitions, other kinds of maintenance host and whole-disk
imaging were **not** performed; see
[Unverified alternatives](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#unverified-alternatives).

## Readiness and recorded scope

Read [Hardware and setup](https://github.com/xjamesmorris/k3-com260-info/wiki/Hardware-and-Setup)
and [Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery)
first. The carrier PCB revision is not recorded; the Firefly wiring and
results are not a compatibility claim for other carriers.

| Input or stage | Exact scope |
| --- | --- |
| Image | `Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz`: community-contributed, **non-official Fedora RISC-V Beta** bytes, not a latest/final compose. |
| Bootstrap kernel | `7.2.7-300.0.riscv64.omni.fc45.riscv64`, from that image. |
| First kernel update | COPR build **11035571**, `7.2.8-300.0.riscv64.omni.fc45.riscv64`, exactly five locked binary RPMs. |
| Fan-control upgrade | COPR build **11177969**, `7.3.0-65.1.riscv64.omni.fc45.riscv64`, five locked binary RPMs installed from 7.2.8 and booted with their packaged DTB. One attended boot (October 21). |
| Tested installation | October 20: fresh F45 into existing **p4** (ext4 `/boot`) and **p5** (Btrfs root) of the K3's NVMe, made from an F44 maintenance host on p1–p3 of the same disk. The partition table, the F44 boot files and the Bianbu UFS ESP were byte-identical afterwards. |
| Earlier result | October 19: side-by-side p4/p5 bring-up, before these public helpers existed; one bootstrap and three 7.2.8 smoke boots. |
| Not performed | Creating the partitions, a workstation-enclosure or Bianbu maintenance host, whole-disk imaging, and any F45 guest workload. |
| Virtualization | F45 KVM host initialization and `/dev/kvm` were observed. **No F45 guest workload was tested.** |

Your partition numbers and filesystem UUIDs will differ from the recorded
ones. The helpers bind the values you state and refuse anything else; never
copy a historical partition number, UUID or disk identity from this page.
The public [support-bundle contract](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/README.md)
and [source lock](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/files/sources.lock.json)
bound these claims. The historical
[F44 archive](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-44-Archive)
is neither a prerequisite nor F45 guest evidence.

**Before you start, have:**

1. **Two target partitions** on the NVMe the K3 boots from: at least
   **2 GiB** for `/boot` and at least **32 GiB** for the Btrfs root.
   **Everything on them is destroyed**; other partitions are left alone.
   Each must be either empty (no filesystem signature) or an ext4 (`/boot`)
   or single-device Btrfs (root) filesystem whose current UUID you state.
   Back up anything you need first.
2. **A Linux maintenance host** that can see that NVMe and is running from
   neither target. The tested host was Fedora 44 on the K3 itself, from other
   partitions of the same disk. It needs root through sudo, Python 3.10+,
   util-linux, e2fsprogs, btrfs-progs, rsync, curl, xz, zstd, dtc with
   `fdtget`/`fdtput`, systemd and udev, plus about 12 GiB free below
   `/var/tmp` for the decompressed image.
3. **A Linux workstation** with the serial console and SSH. It may be the
   same computer as the maintenance host only if that computer can also
   reach the K3 over serial and the network.
4. **A trusted, isolated LAN.** The image ships the `fedora` account with
   the documented default password `linux`, and SSH password login is
   enabled. Change the password at the first serial login.
5. **Attended operation.** Every F45 boot is a manual U-Boot sequence typed
   at the serial console; nothing here changes the saved boot default.

**Fan control needs the 7.3.0 upgrade.** The 7.2.7 and 7.2.8 kernels have
no fan control: the fan ran at **full speed, loudly,** in every recorded boot
of them, and they exposed no SoC thermal zones. After the
[7.3.0 upgrade](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#upgrade-to-73-with-fan-control)
the kernel sets the fan speed from the SoC temperature; one attended boot is
recorded. No thermal protection, fail-safe, sustained-load or
unattended-operation guarantee is established.

## Workstation, serial, and notation

These are **interactive checkpoints, not a script to paste as a whole**.
Run only the block for the named machine, inspect its result, and stop on any
failed check. Variables do not cross terminals, machines or SSH sessions;
re-enter them where shown. Strict-mode subshells stop a block without
changing the interactive shell; do not enable `set -u` in an interactive
Fedora shell.

| Machine | Role | Required tools |
| --- | --- | --- |
| Linux workstation | Serial console, SSH, RPM download and transfer | Git, Bash, Python 3.10+, curl, rpm, rsync, OpenSSH client and key tools (`ssh-keyscan`, `ssh-copy-id`), tmux, picocom, GNU coreutils. |
| Maintenance host | Image download and the destructive populate step | Git, Bash, sudo and the tools listed above under **Before you start**. |
| K3 Fedora 45 host | Kernel update | Supplied by the image: rpm, dnf, dracut, zstd and Python 3. `dtc` with `fdtget`/`fdtput` is needed only if the installer must generate a DTB. |

The fetch, transfer and extraction helpers run as ordinary users. Only
`populate-f45-volumes.sh` (maintenance host) and `k3-install-rpm-kernel.sh`
(K3) run as root, each started explicitly with sudo. Do not add a `NOPASSWD`
rule, disable SELinux or firewalls, or run a whole shell as root.

Create the workspace on the workstation, and again on the maintenance host
if that is a different system:

```sh
# Linux workstation or maintenance host: a new workspace, not an existing checkout.
export WORK="$HOME/k3-fedora-45"
export REPO="$WORK/k3-com260-info"
export F45="$REPO/fedora-45"
(
  set -euo pipefail
  [[ ! -e "$WORK" && ! -L "$WORK" ]]
  mkdir -- "$WORK"
  git clone --branch main --single-branch \
    https://github.com/xjamesmorris/k3-com260-info.git "$REPO"
  test -f "$F45/files/sources.lock.json"
  python3 -c 'import sys; assert sys.version_info >= (3, 10)'
  python3 -B "$F45/scripts/verify-f45-bundle.py" release
)
```

If the public `main` checkout does not contain the `fedora-45/` bundle, stop.
Review the
[populate helper](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/scripts/populate-f45-volumes.sh),
[bootstrap-DTB helper](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/scripts/make-bootstrap-dtb.sh),
[extractor](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/scripts/extract-riscv-zboot.sh),
[fetcher](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/scripts/fetch-f45-copr-kernel.sh),
[transfer helper](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/scripts/transfer-f45-copr-kernel-to-k3.sh),
[installer](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/scripts/k3-install-rpm-kernel.sh)
and [verifier](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/scripts/verify-f45-bundle.py)
with the lock before running them; do not edit a pin to accept other bytes.

Match the carrier's conditional header reference before connecting **3.3 V
TTL RX, TX and ground only**; leave the adapter's VCC/power lead disconnected.
Use 115200 8N1, no flow control. Keep a console log; it is your record of
banners, fingerprints and load sizes:

```sh
# Linux workstation: a dedicated terminal for the console.
tmux new-session -s k3-f45-serial
export SERIAL=/dev/serial/by-id/usb-REPLACE_WITH_YOUR_SERIAL_ADAPTER
picocom --baud 115200 --flow n --logfile "$HOME/k3-fedora-45/serial.log" "$SERIAL"
```

Confirm the **Bianbu Minimal K3 v4.0.1 non-UEFI** U-Boot banner (the recorded
build reports U-Boot 2022.10 dated May 21, 2026). Keep matching working
firmware and UFS contents: **do not factory-flash as an installation step**.
If the banner differs or serial is silent, stop at
[Console and recovery](https://github.com/xjamesmorris/k3-com260-info/wiki/Console-and-Recovery);
recovery writes have a different destructive scope.

## Image and prepare the NVMe

### Download and verify the fixed image

On the maintenance host, allow about 1.2 GB for the compressed image. No
command here selects a newer compose.

```sh
# Maintenance host
export OMNI_URL=https://dl.fedoraproject.org/pub/alt/risc-v/releases/test/45_Beta/Server/riscv64/images/Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz
export OMNI_IMAGE="$WORK/Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz"
export OMNI_SHA256=6f0ebebc251149ba814fcb0e73c2535bc0a65437eff4827bdc4496916a8eebca
(
  set -euo pipefail
  [[ ! -e "$OMNI_IMAGE" && ! -L "$OMNI_IMAGE" ]]
  [[ ! -e "$OMNI_IMAGE.partial" && ! -L "$OMNI_IMAGE.partial" ]]
  curl --fail --location --max-redirs 10 --retry 3 \
    --proto '=https' --proto-redir '=https' --show-error \
    --output "$OMNI_IMAGE.partial" "$OMNI_URL"
  printf '%s  %s\n' "$OMNI_SHA256" "$OMNI_IMAGE.partial" |
    sha256sum --check --strict -
  xz --test -- "$OMNI_IMAGE.partial"
  mv -nT -- "$OMNI_IMAGE.partial" "$OMNI_IMAGE"
  [[ ! -e "$OMNI_IMAGE.partial" && ! -L "$OMNI_IMAGE.partial" ]]
)
```

The pin checks the compressed bytes (1,216,442,944 bytes) and `xz --test`
checks the container. A failed download leaves a named partial file for
inspection; do not reuse it as a completed image. The populate helper checks
the image against the public lock again before writing anything.

### Identify the disk and the two targets

Inspect the disk the K3 boots from, using stable `/dev/disk/by-id/` names
rather than guessed `/dev/nvme…` or `/dev/sd…` nodes:

```sh
# Maintenance host: inspection only.
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,MOUNTPOINTS
ls -l /dev/disk/by-id/ | grep -v -- '-part'
swapon --show
```

Choose the whole-disk ID and the two partition numbers, then check what each
target currently holds:

```sh
# Maintenance host: values from your inspection, not from this page.
export NVME_DISK=/dev/disk/by-id/REPLACE_WITH_WHOLE_DISK_ID
export BOOT_PART="$NVME_DISK-partREPLACE_WITH_BOOT_PARTITION_NUMBER"
export ROOT_PART="$NVME_DISK-partREPLACE_WITH_ROOT_PARTITION_NUMBER"
lsblk -o NAME,PATH,SIZE,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS "$NVME_DISK"
lsblk -dn -o MODEL,SERIAL "$NVME_DISK"
lsblk -dnb -o SIZE "$NVME_DISK"
for part in "$BOOT_PART" "$ROOT_PART"; do
  sudo blkid -p --no-part-details -o export -- "$part"
  printf 'probe status for %s: %s\n' "$part" "$?"
done
```

A probe status of **0** with `TYPE=ext4` (boot) or `TYPE=btrfs` (root) means
you must state that filesystem's current `UUID`. Status **2** means no
signature: state `empty`. Anything else — another filesystem type, swap,
LVM, RAID or encryption, or an ambiguous probe — is a stop: the helper never
wipes signatures, and neither should you merely to get past it. Mounted,
swap-active or held targets are also refused.

Set the identity the helper will enforce. Use the exact model and serial
printed above (whitespace trimmed) and the decimal byte size:

```sh
# Maintenance host: exact values from your disk, not from this page.
export K3_NVME_EXPECTED_MODEL='REPLACE_WITH_EXACT_MODEL'
export K3_NVME_EXPECTED_SERIAL='REPLACE_WITH_EXACT_SERIAL'
export K3_NVME_EXPECTED_SIZE_BYTES=REPLACE_WITH_DECIMAL_BYTE_SIZE
export K3_F45_EXPECTED_BOOT=REPLACE_WITH_CURRENT_BOOT_UUID_OR_empty
export K3_F45_EXPECTED_ROOT=REPLACE_WITH_CURRENT_ROOT_UUID_OR_empty
export K3_F45_FWUPD=mask
```

`K3_F45_FWUPD=mask` is the tested choice. In the October 19 bring-up, an RTC
correction triggered fwupd/udisks2, which briefly mounted another system's
NVMe ESP and the Bianbu UFS ESP **read-write**. `mask` writes systemd masks for
`fwupd.service` and `fwupd-refresh.timer` into the new F45 root before its
first boot; `keep` leaves them enabled. Either way this is not isolation of
other storage, and it is not a firmware-update procedure.

### Record what must not change

On a disk shared with other systems, save a before-state outside the targets.
List any small partitions you want to protect, such as unmounted ESPs:

```sh
# Maintenance host: read-only before-state.
export PROTECT='REPLACE_WITH_SPACE_SEPARATED_PARTITION_PATHS'
(
  set -euo pipefail
  set -C
  mkdir -- "$WORK/before"
  sudo sfdisk --dump "$(readlink -e -- "$NVME_DISK")" > "$WORK/before/gpt.txt"
  for part in $PROTECT; do
    sudo sha256sum -- "$part"
  done > "$WORK/before/protected.sha256"
  cat "$WORK/before/protected.sha256"
)
```

Raw hashes suit unmounted partitions. For a mounted boot partition or ESP of
the maintenance system itself, compare file hashes instead; the recorded run
hashed every F44 `/boot` and `/boot/efi` file before and after.

### Check, then populate the two partitions

First run the helper's read-only check. It applies every guard and verifies
the image hash and xz integrity, but writes nothing:

```sh
# Maintenance host: read-only check.
sudo env \
  K3_NVME_EXPECTED_MODEL="$K3_NVME_EXPECTED_MODEL" \
  K3_NVME_EXPECTED_SERIAL="$K3_NVME_EXPECTED_SERIAL" \
  K3_NVME_EXPECTED_SIZE_BYTES="$K3_NVME_EXPECTED_SIZE_BYTES" \
  K3_F45_EXPECTED_BOOT="$K3_F45_EXPECTED_BOOT" \
  K3_F45_EXPECTED_ROOT="$K3_F45_EXPECTED_ROOT" \
  K3_F45_FWUPD="$K3_F45_FWUPD" \
  "$F45/scripts/populate-f45-volumes.sh" --check \
  "$OMNI_IMAGE" "$NVME_DISK" "$BOOT_PART" "$ROOT_PART"
```

It must end with `Check only: nothing was written.` and name the two
partition numbers you intended. Only then, with nothing else needing those
partitions, add the format acknowledgment and run it for real. **This
destroys all data on both targets.**

```sh
# Maintenance host: DESTRUCTIVE for the two named partitions only.
(
  set -o pipefail
  sudo env \
    K3_NVME_EXPECTED_MODEL="$K3_NVME_EXPECTED_MODEL" \
    K3_NVME_EXPECTED_SERIAL="$K3_NVME_EXPECTED_SERIAL" \
    K3_NVME_EXPECTED_SIZE_BYTES="$K3_NVME_EXPECTED_SIZE_BYTES" \
    K3_F45_EXPECTED_BOOT="$K3_F45_EXPECTED_BOOT" \
    K3_F45_EXPECTED_ROOT="$K3_F45_EXPECTED_ROOT" \
    K3_F45_FWUPD="$K3_F45_FWUPD" \
    K3_F45_ACK_FORMAT=YES-FORMAT-F45-VOLUMES \
    "$F45/scripts/populate-f45-volumes.sh" \
    "$OMNI_IMAGE" "$NVME_DISK" "$BOOT_PART" "$ROOT_PART" 2>&1 |
    tee "$WORK/populate.log"
)
```

The recorded run took about 1.5 minutes on the K3. The helper repeats every
target guard immediately before formatting, then:

- formats the boot target as ext4 (`F45BOOT`) and the root target as Btrfs
  (`fedora45`) with `root`, `home` and `var` subvolumes;
- copies the image's files, preserving ownership, hard links, ACLs and
  extended attributes, including SELinux labels;
- rewrites only the new F45 fstab (no `/boot/efi` entry: this route does not
  use an ESP), the BLS `root=UUID=` options and `/etc/kernel/cmdline`;
- writes the fwupd masks if you chose `mask`;
- extracts the raw `Image-7.2.7…` from the packaged EFI zboot `vmlinuz`,
  because non-UEFI `booti` needs a raw RISC-V Image;
- creates `dtb-7.2.7…/spacemit/k3-com260-bootstrap.dtb`: the packaged DTB
  plus an empty `regulator-always-on` in the unique `dldo4` node and in
  `/hub-reset`, verified as exactly two added lines. The historical lockup
  occurred around unused-regulator cleanup; the two properties together are
  the recorded workaround, not proof that each is independently necessary.

It never changes the partition table, any other partition, firmware or the
U-Boot environment, and never reboots. Its closing summary is your record:

```sh
# Maintenance host: the summary, without the helper's trace lines.
sed -n '/^Fedora 45 volumes populated/,$p' "$WORK/populate.log" | grep -v '^+'
```

Write down the **U-Boot boot partition** (`nvme 0:N`), the **F45 `/boot`
UUID**, the **F45 root UUID**, and the three load sizes and SHA-256 values.
The same identities are stored as `/root/k3-f45-volume-install.txt` in the new
root. For the pinned image the expected load sizes are **40,109** bytes
(bootstrap DTB), **63,283,200** (raw Image) and **78,670,210** (the image's
own initramfs, `0x4b06982`).

On a shared disk, compare the before-state now:

```sh
# Maintenance host: read-only comparison; both must print nothing.
sudo sfdisk --dump "$(readlink -e -- "$NVME_DISK")" | diff -u "$WORK/before/gpt.txt" -
for part in $PROTECT; do sudo sha256sum -- "$part"; done |
  diff -u "$WORK/before/protected.sha256" -
```

Then shut down the maintenance system before booting F45. Remove microSD
cards: non-vendor SD layouts stopped BootROM before serial output in the
historical bring-up.

## Boot the bootstrap Fedora host

### Check addresses before loading

Power on with serial attached and press **`s`** at `Autoboot in 3 seconds`
to stop at the U-Boot prompt; the recorded firmware did not stop for Space.
**Enter one short line, wait for the `=> ` prompt
to return, inspect the output, then enter the next.** Input sent while a
command ran was lost in earlier work, and long chained lines were truncated.
A continuation prompt is a stop condition. Never run `saveenv` or `env save`.

```text
# U-Boot: inspection only; do not change the firmware's load addresses.
version
printenv fdt_addr_r kernel_addr_r ramdisk_addr_r
```

The recorded firmware reported `fdt_addr_r=0x138000000`,
`kernel_addr_r=0x140000000` and `ramdisk_addr_r=0x130000000`. With the
pinned sizes the three ranges do not overlap: ramdisk
`[0x130000000, 0x134b06982)`, DTB `[0x138000000, 0x138009cad)` and Image
`[0x140000000, 0x143c5a000)`. At `booti` the firmware moved the Image to
`0x102200000` and copied the ramdisk and DTB high in memory itself. If your
addresses or sizes differ, check the ranges before loading anything:

```sh
# Linux workstation: addresses from this U-Boot, sizes from the populate summary.
export FDT_LOAD=REPLACE_WITH_FDT_HEX_ADDRESS
export IMAGE_LOAD=REPLACE_WITH_KERNEL_HEX_ADDRESS
export INITRD_LOAD=REPLACE_WITH_RAMDISK_HEX_ADDRESS
export FDT_BYTES=REPLACE_WITH_DTB_DECIMAL_BYTES
export IMAGE_BYTES=REPLACE_WITH_IMAGE_DECIMAL_BYTES
export INITRD_BYTES=REPLACE_WITH_INITRAMFS_DECIMAL_BYTES
python3 - <<'PY'
import itertools
import os

ranges = []
for name in ("FDT", "IMAGE", "INITRD"):
    start = int(os.environ[name + "_LOAD"], 16)
    size = int(os.environ[name + "_BYTES"])
    if start <= 0 or size <= 0:
        raise SystemExit("STOP: invalid address or size")
    ranges.append((name, start, start + size))
    print(f"{name}: [0x{start:x}, 0x{start + size:x})")
for a, b in itertools.combinations(ranges, 2):
    if max(a[1], b[1]) < min(a[2], b[2]):
        raise SystemExit("STOP: load ranges overlap")
print("No mutual overlap; reserved firmware memory still needs human review.")
PY
```

An undefined address, an overlap or an unexplained difference means **stop
before any load**; do not invent replacement addresses.

### Load the matching bootstrap set

Use the boot partition number and root UUID from the populate summary. The
root UUID is the Btrfs filesystem UUID, not a PARTUUID or the boot UUID.

```text
# U-Boot: one line per returned prompt, with checks between lines.
setenv bootpart REPLACE_WITH_BOOT_PARTITION_NUMBER
setenv bootrel 7.2.7-300.0.riscv64.omni.fc45.riscv64
setenv rootuuid REPLACE_WITH_F45_ROOT_UUID
nvme scan
fsuuid nvme 0:${bootpart}
load nvme 0:${bootpart} ${fdt_addr_r} dtb-${bootrel}/spacemit/k3-com260-bootstrap.dtb
load nvme 0:${bootpart} ${kernel_addr_r} Image-${bootrel}
load nvme 0:${bootpart} ${ramdisk_addr_r} initramfs-${bootrel}.img
setenv initrd_size ${filesize}
printenv initrd_size
setenv bootargs root=UUID=${rootuuid}
setenv bootargs "${bootargs} rootflags=subvol=root"
setenv bootargs "${bootargs} clk_ignore_unused"
setenv bootargs "${bootargs} console=ttyS0,115200n8"
printenv bootrel bootargs
```

Check each result before the next line:

- `nvme scan` must report the occupied 2280 slot's link up (recorded:
  `PCIE-0: Link up (Gen3-x4, Bus0)`). An empty 2230 slot's `PCIE-2: Link down`
  is expected.
- `fsuuid` must print **your F45 `/boot` UUID**. Anything else means the
  wrong partition: stop.
- Each `load` must print exactly the populate summary's byte count, as
  `N bytes read`. A failed load leaves the previous `filesize`; never
  continue on a stale value.
- `initrd_size` must be the initramfs size in hexadecimal, and `bootargs`
  must read exactly
  `root=UUID=<your root UUID> rootflags=subvol=root clk_ignore_unused console=ttyS0,115200n8`.

Vendor U-Boot prefixes many output lines with `[ seconds ]` timestamps,
sometimes even between `=> ` and the echoed command; that is normal. Only
when every check passes, as a separate attended action:

```text
# U-Boot: temporary boot; never save the environment.
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}
```

The recorded boot reached `localhost login:` about 24 seconds later. Its
first-boot log included `Failed to preset all unit … Read-only file system`
for a few units (the first-boot preset runs before the root is writable) and
`Unit … fwupd-refresh.timer is masked`; both are expected. The preset failure
left only `lvm-devices-import.*`, `remote-integritysetup.target` and
`systemd-tpm2-clear.service` disabled, none of which this route uses.

### Serial first login, identity and normal privilege

Log in at the serial console as **`fedora`** with the image's default
password **`linux`**. The recorded image ships `root` locked and `fedora` in
`wheel` (`%wheel ALL=(ALL) ALL`), with no initial-setup or cloud-init step.
Because SSH password login is enabled, change the password first, then check
sudo and record the newly generated SSH host key:

```sh
# K3 Fedora serial console, logged in as fedora.
passwd
sudo -v
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
ip -brief address
```

Then check that you booted the intended system. Re-enter the identifiers in
each new K3 shell:

```sh
# K3 Fedora serial console or SSH, as fedora.
export BOOT_KREL=7.2.7-300.0.riscv64.omni.fc45.riscv64
export ROOT_UUID=REPLACE_WITH_F45_ROOT_UUID
export BOOT_UUID=REPLACE_WITH_F45_BOOT_UUID
(
  set -euo pipefail
  test "$(id -un)" = fedora
  test "$(uname -m)" = riscv64
  test "$(uname -r)" = "$BOOT_KREL"
  test "$(rpm -E '%fedora')" = 45
  test "$(findmnt -nro UUID /)" = "$ROOT_UUID"
  test "$(findmnt -nro UUID /boot)" = "$BOOT_UUID"
  test "$(findmnt -nro FSTYPE /)" = btrfs
  test "$(findmnt -nro FSROOT /)" = /root
  test "$(findmnt -nro FSTYPE /boot)" = ext4
  test "$(readlink /boot/dtb)" = "dtb-$BOOT_KREL"
  cat /proc/cmdline
  ip -brief address
  ip route
  systemctl is-system-running || true
  systemctl --failed --no-pager
  systemctl is-enabled fwupd.service fwupd-refresh.timer || true
  findmnt -rn -t vfat,msdos || echo 'no FAT filesystem mounted'
  sudo btrfs device stats /
  journalctl -b -k -p warning --no-pager
)
```

Inspect the outputs; an exit status alone does not certify a healthy boot.
The recorded system was `running` with no failed units and zero Btrfs error
counters. Its kernel warnings were all previously seen: reserved-memory
overlap reports from the firmware DT, PCIe `of_irq_parse_pci` errors, fusb301
Type-C probe messages, UFS RPMB/BOOT WLUN messages, an ONIE EEPROM header
warning and the deferred DWC3 `81400000.usb3` probe. The firmware appends
`boot_mode=nor clk_ignore_unused` to the command line.

In every October 20 F45 boot, DHCPv4 assigned the address within about 23–26
seconds of boot. One October 19 boot took about **7.5 minutes**, and the F44
system on the same board took about 145 seconds right after F45 had used
the same address. If IPv4 is slow, watch the link and address over serial
rather than rebooting repeatedly.

### Establish a key and verify SSH against serial

From the workstation, fetch the K3's host key and compare its fingerprint
**exactly** with the one printed on serial:

```sh
# Linux workstation: compare with the serial fingerprint before trusting it.
export K3_ADDR=REPLACE_WITH_K3_ADDRESS
ssh-keyscan -t ed25519 "$K3_ADDR" 2>/dev/null > "$WORK/k3-f45-hostkey.scan"
ssh-keygen -lf "$WORK/k3-f45-hostkey.scan"
```

If another system on this board uses the same address (as F44 did), give F45
its own name and known-hosts file so neither key replaces the other. Add to
`~/.ssh/config`:

```text
Host k3-f45
    HostName REPLACE_WITH_K3_ADDRESS
    HostKeyAlias k3-f45
    UserKnownHostsFile ~/.ssh/known_hosts.k3-f45
    StrictHostKeyChecking yes
```

Only after the fingerprints match, record the key under that name, install
your public key with the new password, and confirm key-only login:

```sh
# Linux workstation: after the fingerprint matched.
export K3_PUBKEY="$HOME/.ssh/id_ed25519.pub"
(
  set -euo pipefail
  test "$(awk 'NF == 3 && $2 == "ssh-ed25519"' "$WORK/k3-f45-hostkey.scan" | wc -l)" -eq 1
  awk 'NF == 3 && $2 == "ssh-ed25519" {print "k3-f45", $2, $3}' \
    "$WORK/k3-f45-hostkey.scan" >> "$HOME/.ssh/known_hosts.k3-f45"
  chmod 0600 "$HOME/.ssh/known_hosts.k3-f45"
  ssh-copy-id -i "$K3_PUBKEY" fedora@k3-f45
  ssh -o BatchMode=yes fedora@k3-f45 'id -un; uname -r; findmnt -no SOURCE /'
)
```

`ssh-keyscan` also prints a `#` banner line, which the guard ignores. In the
recorded run the first `ssh-copy-id` attempt left no `~/.ssh` on the K3 and
the cause was not determined; the second worked. The final `BatchMode` login
catches that case. If a key for `k3-f45` already exists from an earlier
installation, remove only that entry with
`ssh-keygen -R k3-f45 -f ~/.ssh/known_hosts.k3-f45` after confirming the new
fingerprint over serial. Never disable host-key checking to get past a
changed-key warning.

If you chose `keep` for fwupd, or later want it back on F45, decide that
separately: `sudo systemctl unmask fwupd.service fwupd-refresh.timer` on F45
can restore the probing described above. With `mask`, the recorded boots
mounted no FAT filesystem, and the protected ESPs were byte-identical
afterwards.

## Install the pinned kernel update

### Fetch and transfer the five binary RPMs

The inputs are `kernel`, `kernel-core`, `kernel-modules-core`,
`kernel-modules` and `kernel-modules-extra`, all for
**7.2.8-300.0.riscv64.omni.fc45.riscv64**, from
[COPR build 11035571](https://copr.fedorainfracloud.org/coprs/g/forge-riscv-members/riscv64_omni_kernel/build/11035571/).
The public lock supplies each complete filename, HTTPS URL and SHA-256. The
shared verifier checks that lock, the exact five-file inventory, digests and
RPM headers. Do not substitute `dnf upgrade`, a moving repository kernel, a
different build or an edited checksum list.

Recorded RPM inspection reported **`NOKEY`**, not independently verified
publisher signatures. Digest and header checks establish the selected bytes
and identity, not a trusted signing key. The installer uses `--nogpgcheck`
only after those explicit pinned checks; accept that provenance limitation
deliberately or stop. The original SRPM URL was unavailable at review: the
SRPM is **provenance-only**, is not downloaded, and is not replaced by a
different artifact. An exact source Git commit remains unproven.

```sh
# Linux workstation: ordinary user; key login to K3_SSH must already work.
export K3_SSH=fedora@k3-f45
export RPM_BUNDLE="$WORK/f45-copr-kernel-11035571-rpms"
(
  set -euo pipefail
  "$F45/scripts/fetch-f45-copr-kernel.sh" "$RPM_BUNDLE"
  python3 -B "$F45/scripts/verify-f45-bundle.py" verify "$RPM_BUNDLE"
  ssh -o BatchMode=yes "$K3_SSH" 'test "$(id -un)" = fedora'
  "$F45/scripts/transfer-f45-copr-kernel-to-k3.sh" "$RPM_BUNDLE" "$K3_SSH"
)
```

Fetch and transfer refuse existing final or partial destinations. Do not
rerun blindly over a failed stage. The remote layout is home-relative:

```text
~/f45-copr-kernel-11035571/
    files/sources.lock.json
    scripts/verify-f45-bundle.py
    scripts/extract-riscv-zboot.sh
    scripts/k3-install-rpm-kernel.sh
    scripts/make-bootstrap-dtb.sh
    rpms/                         # exactly five binary RPMs
```

The transfer re-verifies remotely; it does **not** install anything or
configure sudo.

### Install alongside 7.2.7, without a boot-default change

On the K3, check the running system, free space and the transferred bundle:

```sh
# K3 Fedora 7.2.7 host, ordinary fedora account.
export BOOT_KREL=7.2.7-300.0.riscv64.omni.fc45.riscv64
export ROOT_UUID=REPLACE_WITH_F45_ROOT_UUID
export BOOT_UUID=REPLACE_WITH_F45_BOOT_UUID
(
  set -euo pipefail
  test "$(uname -r)" = "$BOOT_KREL"
  test "$(rpm -E '%fedora')" = 45
  test "$(findmnt -nro UUID /)" = "$ROOT_UUID"
  test "$(findmnt -nro UUID /boot)" = "$BOOT_UUID"
  test "$(readlink /boot/dtb)" = "dtb-$BOOT_KREL"
  for tool in python3 rpm dnf dracut zstd; do
    command -v "$tool" >/dev/null
  done
  df -h / /boot "$HOME"
  python3 -B "$HOME/f45-copr-kernel-11035571/scripts/verify-f45-bundle.py" \
    verify "$HOME/f45-copr-kernel-11035571/rpms"
  sudo btrfs device stats /
)
```

After reviewing those checks, run the **installer only** with sudo, keeping
its output:

```sh
# K3 Fedora host: package, module and boot-file writes; no reboot.
(
  set -o pipefail
  sudo "$HOME/f45-copr-kernel-11035571/scripts/k3-install-rpm-kernel.sh" \
    "$HOME/f45-copr-kernel-11035571/rpms" 2>&1 |
    tee "$HOME/k3-install-7.2.8.log"
)
```

The installer requires the exact locked **7.2.7 F45 bootstrap** to be running,
and refuses the saved F44 boot path, an already running or installed candidate,
and pre-existing candidate paths. Matching `uname` alone does not identify
the mounted root; the UUID checks above remain necessary. It installs only the
locked local RPMs with repositories disabled, retains 7.2.7, restores the
original `/boot/dtb` symlink and extracts the new raw Image. A failure can still
leave a partial package transaction: stop and inspect rather than deleting
files and retrying automatically.

### Review the installer's summary

The installer also creates the **separately named 7.2.8 bootstrap DTB**. It
copies the 7.2.7 bootstrap DTB only when the packaged 7.2.7 and 7.2.8 DTBs
are byte-identical — as they are for these pins — and otherwise generates
one with `make-bootstrap-dtb.sh`, which needs `dtc`, `fdtget` and `fdtput`
on the K3. If neither is possible, it stops after installing and says so;
prepare the DTB before any boot. It never compares a patched DTB with an
original to infer compatibility.

The recorded summary reported DNF `Complete!`, skipped OpenPGP checks for the
five locally verified packages, `Bootstrap DTB: copied from
7.2.7-300.0.riscv64.omni.fc45.riscv64; packaged DTBs are byte-identical`,
and these U-Boot load sizes:

| File | Recorded bytes |
| --- | ---: |
| `k3-com260-bootstrap.dtb` | 40,109 (`0x9cad`) |
| `Image-7.2.8-300.0.riscv64.omni.fc45.riscv64` | 63,287,296 (`0x3c5b000`) |
| `initramfs-7.2.8-300.0.riscv64.omni.fc45.riscv64.img` | 49,058,336 (`0x2ec9220`) |

The initramfs is generated on your system, so **use your own summary's
sizes**; the DTB and Image are expected to match. The NVMe, Btrfs, PCIe
controller and PHY drivers are built into this 7.2.8 kernel, so the smaller
host-only initramfs needs no storage modules; you can confirm with
`grep -E '/(nvme|btrfs|pcie-spacemit-k1)\.ko' /lib/modules/7.2.8-300.0.riscv64.omni.fc45.riscv64/modules.builtin`.
`/boot/dtb` still points at 7.2.7, so that symlink cannot identify the DTB a
temporary boot uses.

## Boot and check the updated host

### Explicit 7.2.8 load and boot sequence

Have serial ready, then reboot. The saved boot default is unchanged; if you
do not interrupt autoboot, the firmware boots whatever it booted before.

```sh
# K3 F45: an explicit, attended reboot.
sudo systemctl reboot
```

Interrupt autoboot with `s` (power-cycle if no U-Boot banner appears), and repeat the
whole sequence with the **7.2.8** release and the installer's sizes:

```text
# U-Boot: one line per returned prompt, with checks between lines.
printenv fdt_addr_r kernel_addr_r ramdisk_addr_r
setenv bootpart REPLACE_WITH_BOOT_PARTITION_NUMBER
setenv bootrel 7.2.8-300.0.riscv64.omni.fc45.riscv64
setenv rootuuid REPLACE_WITH_F45_ROOT_UUID
nvme scan
fsuuid nvme 0:${bootpart}
load nvme 0:${bootpart} ${fdt_addr_r} dtb-${bootrel}/spacemit/k3-com260-bootstrap.dtb
load nvme 0:${bootpart} ${kernel_addr_r} Image-${bootrel}
load nvme 0:${bootpart} ${ramdisk_addr_r} initramfs-${bootrel}.img
setenv initrd_size ${filesize}
printenv initrd_size
setenv bootargs root=UUID=${rootuuid}
setenv bootargs "${bootargs} rootflags=subvol=root"
setenv bootargs "${bootargs} clk_ignore_unused"
setenv bootargs "${bootargs} console=ttyS0,115200n8"
printenv bootrel bootargs
```

Apply the same checks as for 7.2.7: unchanged addresses, the link-up report,
your `/boot` UUID from `fsuuid`, each `bytes read` equal to the installer's
summary, `initrd_size` equal to its hexadecimal initramfs size, and the exact
`bootargs`. It uses the 7.2.8 directory's `k3-com260-bootstrap.dtb`, not
`/boot/dtb`, the unpatched `k3-com260-ifx.dtb` or the old release's path.
Only after the complete check:

```text
# U-Boot: temporary boot; never save the environment.
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}
```

### Check the actual updated system

```sh
# K3 Fedora 7.2.8 host, as fedora (serial or SSH).
export UPDATE_KREL=7.2.8-300.0.riscv64.omni.fc45.riscv64
export ROOT_UUID=REPLACE_WITH_F45_ROOT_UUID
export BOOT_UUID=REPLACE_WITH_F45_BOOT_UUID
(
  set -euo pipefail
  test "$(uname -r)" = "$UPDATE_KREL"
  test "$(rpm -E '%fedora')" = 45
  test "$(findmnt -nro UUID /)" = "$ROOT_UUID"
  test "$(findmnt -nro UUID /boot)" = "$BOOT_UUID"
  test "$(findmnt -nro FSTYPE /)" = btrfs
  test "$(findmnt -nro FSROOT /)" = /root
  test "$(findmnt -nro FSTYPE /boot)" = ext4
  uname -a
  cat /proc/cmdline
  systemd-analyze
  systemctl is-system-running || true
  systemctl --failed --no-pager
  findmnt -rn -t vfat,msdos || echo 'no FAT filesystem mounted'
  sudo btrfs device stats /
  ip -brief address
  ip route
  journalctl -b -k -p warning --no-pager
  ls -l /dev/kvm || echo 'no /dev/kvm'
)
```

All three recorded 7.2.8 boots reached the login prompt about 22 seconds
after `booti`, finished startup in 22.9–23.5 seconds, obtained DHCPv4 about
23 seconds after boot, and were `running` with no failed units and no FAT
mounts. Their warnings matched the 7.2.7 list above. As before, DWC3
`81400000.usb3` stayed deferred (only USB2 enumerates), no SoC thermal zones
appeared, and `/dev/kvm` was present with the KVM banner reporting the
hypervisor extension, Sv39x4 G-stage paging and 14-bit VMIDs. `/dev/kvm` is
host initialization only, not a guest result. Stay attended, and repeat the
reboot and sequence for each further boot.

## Upgrade to 7.3 with fan control

The 7.2.7 and 7.2.8 kernels leave the fan at full speed. COPR
[build 11177969](https://copr.fedorainfracloud.org/coprs/g/forge-riscv-members/riscv64_omni_mainline_kernel/build/11177969/)
in `@forge-riscv-members/riscv64_omni_mainline_kernel`,
**7.3.0-65.1.riscv64.omni.fc45.riscv64**, includes the
[CoM260 thermal-zone and fan-cooling change](https://gitlab.com/jmontleon/kernel-ark/-/merge_requests/1)
merged into the Omni kernel's `fedora-7.3.y-riscv-omni.0` branch on
October 20, 2026. Its kernel drives the board's CTF2301 fan controller
(`lm63` driver) from the SoC temperature. Its packaged `k3-com260-ifx.dtb`
also keeps `dldo4` always on and has an always-on USB hub supply instead of
`/hub-reset`, so 7.3.0 boots **that packaged DTB**: no bootstrap DTB is
made for it.

Install it from the running, checked **7.2.8** host; the installer refuses
any other running kernel. 7.2.7 and 7.2.8 stay installed beside it. The
7.2.8 rules still apply: exactly five locked binary RPMs, digest and header
checks, `NOKEY` (no verified publisher signature) and no SRPM download.
These are fixed pins, not “the latest kernel”; do not substitute another
build. **One attended 7.3.0 boot is recorded (October 21)**, against three
for 7.2.8.

### Fetch and transfer the 7.3.0 RPMs

A checkout made before these pins existed lacks the build: update it first
with `git -C "$HOME/k3-fedora-45/k3-com260-info" pull --ff-only` and review
the changed lock and helpers. Then, on the workstation:

```sh
# Linux workstation: ordinary user; key login to K3_SSH must already work.
export WORK="$HOME/k3-fedora-45"
export F45="$WORK/k3-com260-info/fedora-45"
export K3_SSH=fedora@k3-f45
export FAN_RPMS="$WORK/f45-copr-kernel-11177969-rpms"
(
  set -euo pipefail
  python3 -B "$F45/scripts/verify-f45-bundle.py" builds
  "$F45/scripts/fetch-f45-copr-kernel.sh" --build 11177969 "$FAN_RPMS"
  python3 -B "$F45/scripts/verify-f45-bundle.py" --build 11177969 \
    verify "$FAN_RPMS"
  ssh -o BatchMode=yes "$K3_SSH" 'test "$(id -un)" = fedora'
  "$F45/scripts/transfer-f45-copr-kernel-to-k3.sh" --build 11177969 \
    "$FAN_RPMS" "$K3_SSH"
)
```

`builds` must list `11035571` and `11177969`. The transfer creates
`~/f45-copr-kernel-11177969/` on the K3, with the same layout as for 7.2.8,
re-verifies it there and prints the install command.

### Install from the running 7.2.8

On the K3, booted into 7.2.8 with the sequence above, check the system and
the transferred bundle:

```sh
# K3 Fedora 7.2.8 host, ordinary fedora account.
export UPDATE_KREL=7.2.8-300.0.riscv64.omni.fc45.riscv64
export ROOT_UUID=REPLACE_WITH_F45_ROOT_UUID
export BOOT_UUID=REPLACE_WITH_F45_BOOT_UUID
(
  set -euo pipefail
  test "$(uname -r)" = "$UPDATE_KREL"
  test "$(rpm -E '%fedora')" = 45
  test "$(findmnt -nro UUID /)" = "$ROOT_UUID"
  test "$(findmnt -nro UUID /boot)" = "$BOOT_UUID"
  df -h / /boot "$HOME"
  python3 -B "$HOME/f45-copr-kernel-11177969/scripts/verify-f45-bundle.py" \
    --build 11177969 verify "$HOME/f45-copr-kernel-11177969/rpms"
  sudo btrfs device stats /
)
```

Then run the **installer only** with sudo, keeping its output:

```sh
# K3 Fedora host: package, module and boot-file writes; no reboot.
(
  set -o pipefail
  sudo "$HOME/f45-copr-kernel-11177969/scripts/k3-install-rpm-kernel.sh" \
    --build 11177969 "$HOME/f45-copr-kernel-11177969/rpms" 2>&1 |
    tee "$HOME/k3-install-7.3.log"
)
```

Before changing anything, the installer refuses a running kernel other than
7.2.8, an already installed 7.3.0 and pre-existing 7.3.0 paths. After DNF it
requires `/boot/dtb-7.3.0-65.1.riscv64.omni.fc45.riscv64/spacemit/k3-com260-ifx.dtb`
to have the lock's SHA-256 and creates **no** bootstrap DTB; if the DTB
differs it stops, and that kernel must not be booted until reviewed.
`/boot/dtb` still points at 7.2.7. The recorded summary reported DNF
`Complete!`, `Boot DTB: packaged spacemit/k3-com260-ifx.dtb; matches the
public lock` and these U-Boot load sizes:

| File | Recorded bytes |
| --- | ---: |
| `dtb-7.3.0-65.1.riscv64.omni.fc45.riscv64/spacemit/k3-com260-ifx.dtb` | 47,633 (`0xba11`) |
| `Image-7.3.0-65.1.riscv64.omni.fc45.riscv64` | 63,361,024 (`0x3c6d000`) |
| `initramfs-7.3.0-65.1.riscv64.omni.fc45.riscv64.img` | 53,388,814 (`0x32ea60e`) |

The DTB and Image are expected to match; the initramfs is generated on your
system, so use your own summary's size. With these sizes the three load
ranges still do not overlap at the recorded addresses.

### Boot 7.3.0 with its packaged DTB

With serial open, reboot:

```sh
# K3 F45 7.2.8: an explicit, attended reboot.
sudo systemctl reboot
```

In the recorded run the console stopped at `reboot: Restarting system`
until the operator pressed reset; if no U-Boot banner follows, press reset
or power-cycle. Stop autoboot with `s`, then enter:

```text
# U-Boot: one line per returned prompt, with checks between lines.
printenv fdt_addr_r kernel_addr_r ramdisk_addr_r
setenv bootpart REPLACE_WITH_BOOT_PARTITION_NUMBER
setenv bootrel 7.3.0-65.1.riscv64.omni.fc45.riscv64
setenv rootuuid REPLACE_WITH_F45_ROOT_UUID
nvme scan
fsuuid nvme 0:${bootpart}
load nvme 0:${bootpart} ${fdt_addr_r} dtb-${bootrel}/spacemit/k3-com260-ifx.dtb
load nvme 0:${bootpart} ${kernel_addr_r} Image-${bootrel}
load nvme 0:${bootpart} ${ramdisk_addr_r} initramfs-${bootrel}.img
setenv initrd_size ${filesize}
printenv initrd_size
setenv bootargs root=UUID=${rootuuid}
setenv bootargs "${bootargs} rootflags=subvol=root"
setenv bootargs "${bootargs} clk_ignore_unused"
setenv bootargs "${bootargs} console=ttyS0,115200n8"
printenv bootrel bootargs
```

**Besides `bootrel`, only the DTB line differs from 7.2.8:** it loads the
7.3.0 directory's packaged `k3-com260-ifx.dtb`. There is no 7.3.0
`k3-com260-bootstrap.dtb`, and the 7.2.x DTBs have no thermal zones or fan
cooling map. Apply the same checks as before: unchanged addresses, the
link-up report, your `/boot` UUID, each `bytes read` equal to the
installer's summary (`47633 bytes read` for the DTB), `initrd_size` equal
to its hexadecimal initramfs size and the exact `bootargs`. Then:

```text
# U-Boot: temporary boot; never save the environment.
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}
```

Every later F45 boot repeats this sequence; the saved default is unchanged.

### Check fan control

Run the
[updated-system checks](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#check-the-actual-updated-system)
with `UPDATE_KREL=7.3.0-65.1.riscv64.omni.fc45.riscv64`, then:

```sh
# K3 Fedora 7.3.0 host, as fedora (serial or SSH); read-only.
(
  set -euo pipefail
  test "$(uname -r)" = 7.3.0-65.1.riscv64.omni.fc45.riscv64
  zones=0
  for zone in /sys/class/thermal/thermal_zone*; do
    zones=$((zones + 1))
    echo "$(cat "$zone/type"): $(( $(cat "$zone/temp") / 1000 )) C, $(cat "$zone/policy")"
  done
  test "$zones" -eq 7
  fan=
  for dev in /sys/class/thermal/cooling_device*; do
    if [ "$(cat "$dev/type")" = ctf2301 ]; then fan=$dev; fi
  done
  test -n "$fan"
  echo "fan cooling state $(cat "$fan/cur_state") of $(cat "$fan/max_state")"
  for mon in /sys/class/hwmon/hwmon*; do
    if [ "$(cat "$mon/name")" = ctf2301 ]; then
      echo "CTF2301 pwm1 $(cat "$mon/pwm1"), fan1 $(cat "$mon/fan1_input") rpm"
    fi
  done
  lsmod | grep -E '^(lm63|k3_tsensor) '
)
```

Seven zones, a `ctf2301` cooling device and both modules are the
checkpoint. Leave the fan to the kernel: do not run a userspace fan-control
script or daemon against the same controller.

The recorded boot reached the login prompt 28 seconds after `booti`,
finished startup in 25.0 seconds, had DHCPv4 at 24.3 seconds and was
`running` with no failed units and no FAT mounts. It registered the zones
`top`, `vpu`, `gpu` and `cluster0`–`cluster3`, all `step_wise`. Only
`cluster0` drives the fan: an active trip at 35 °C and passive trips at 40,
50, 60 and 70 °C, each with 5 °C hysteresis, select fan-state ranges 0–50,
64–75, 102–128, 179–204 and 255.

| Condition (October 21) | `cluster0` | Fan state | Fan speed |
| --- | ---: | ---: | ---: |
| Idle after boot | 47–48 °C | 78 | about 3,840 rpm |
| Eight busy threads for 2 minutes | up to 58 °C | 105 within 5 s | about 4,890 rpm |
| 4 minutes after the load | 47–48 °C | still 105 | about 4,890 rpm |

The operator found it much quieter than 7.2.x at idle and audibly faster
under load. It stayed at 105 after the load, consistent with the 50 °C
trip's hysteresis: `cluster0` did not cool below 45 °C. The 60 and 70 °C
trips were not reached. USB3 also changed: the `81400000.usb3` controller
probed and a USB 3.0 hub enumerated at 5 Gb/s; no USB transfer was tested.
The kernel logged some warnings not seen with 7.2.8, such as
`cma: Failed to reserve 64 MiB` and
`irq_aclint_sswi: unable to create muxed IPIs`; see the
[result record](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md).
One boot and a two-minute load are not a sustained-load, fan-failure or
unattended-use qualification.

## Return to the saved default

To leave F45, reboot or power-cycle **without** interrupting autoboot: the
unchanged saved environment boots the previous system (recorded: F44 on the
same NVMe). On a shared disk, compare the before-state again from that system
with the commands under
[Check, then populate the two partitions](https://github.com/xjamesmorris/k3-com260-info/wiki/Fedora-45-Recipe#check-then-populate-the-two-partitions).
The recorded comparison found the partition table, all 116 F44 `/boot` and
`/boot/efi` files and the raw Bianbu UFS ESP byte-identical.

## Next steps and readiness record

Keep a local record of the exact image and RPM pins, firmware banner,
hardware and carrier identity, the populate and installer summaries, the
U-Boot output for each boot, fingerprints, timings and observations. Do not
publish passwords, keys, serial numbers, hostnames, addresses, UUIDs or raw
captures without a separate privacy review.

What this route has established, and what it has not, is in the
[result record](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md).
Continue with
[Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update)
and [Diagnostics and known limits](https://github.com/xjamesmorris/k3-com260-info/wiki/Diagnostics-and-Known-Limits).
Reset follows the unchanged saved firmware path, not a newly installed
Fedora default. Keep the working 7.2.7 bootstrap set and original packaged
files for an attended temporary fallback; do not use factory flashing to
repair a wrong pathname or boot argument.

Virtualization is optional:
[KVM and QEMU](https://github.com/xjamesmorris/k3-com260-info/wiki/KVM-and-QEMU)
separates F45 host initialization from the archived F44 guest workload
results. `/dev/kvm` does not establish a QEMU or guest version, launch,
workload, CPU filter, interrupt mode, guest network or persistence result on
F45. There is no F45 guest-launch recipe here. Fan control comes from the
7.3.0 upgrade above; no sustained-load thermal qualification has been done.

## Unverified alternatives

None of these were performed. They are listed so you can recognize them,
not as tested instructions.

- **Creating the two partitions.** On a new or blank NVMe, two new GPT
  partitions of the stated minimum sizes, created with your usual tool, are
  what the populate helper expects (`empty` targets). Partition creation,
  resizing and shrinking another system are outside the tested route; the
  helper itself never edits the partition table.
- **Other maintenance hosts.** A Linux workstation with the SSD in a USB
  enclosure (stable `/dev/disk/by-id/usb-…` names, which the helper accepts;
  a bridge may report its own model and serial), or Bianbu on the K3's UFS
  with the required tools installed. After an enclosure, install the
  unpowered SSD in the carrier's **2280 slot**; never hot-insert it.
- **Whole-disk imaging.** Writing the raw image to a dedicated disk gives
  `/boot` on p2 and root on p3, but keeps the image's own filesystem UUIDs
  (shared by every copy of the image), its stock fstab and BLS entries, the
  fwupd units and no raw Image or bootstrap DTB. It would need manual
  equivalents of the populate helper's work, using
  `extract-riscv-zboot.sh` and `make-bootstrap-dtb.sh`.

## Technical notes

**Applies to:** 8 GiB SpacemiT K3-CoM260 on the recorded Firefly carrier, PCB revision unknown; Linux workstation and Linux maintenance host; two existing NVMe partitions populated by the public helper; Bianbu Minimal K3 v4.0.1 non-UEFI U-Boot; pinned F45 Beta 7.2.7 bootstrap, COPR 11035571 7.2.8 host and COPR 11177969 7.3.0 fan-control upgrade.

**Evidence:** Recorded public [F45 results](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/RESULTS.md), [artifact lock](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/files/sources.lock.json) and [helper contract](https://github.com/xjamesmorris/k3-com260-info/blob/main/fedora-45/README.md); partition creation, other maintenance hosts and whole-disk imaging are untested, and the 7.3.0 upgrade has one attended boot.

**Source review:** 2026-10-21.

**Hardware observation:** 2026-10-21 the exact COPR 7.3.0 upgrade installed from 7.2.8 and one attended 7.3.0 boot with kernel fan control and a two-minute load; 2026-10-20 fresh installation into existing p4/p5 partitions from an F44 maintenance host on the same NVMe: one 7.2.7 bootstrap boot, the exact COPR 7.2.8 install and three attended 7.2.8 boots, with the partition table, F44 boot files and UFS ESP unchanged; 2026-10-19 side-by-side bring-up. No F45 guest workload was tested.

**Destructive operations:** Reformats the two selected partitions, destroying their contents; writes the new F45 fstab, BLS entries, kernel command line, fwupd masks, SSH keys, RPM database, module tree and boot files. No partition-table, other-partition, firmware or saved U-Boot environment change. Reboots and temporary U-Boot selections require operator control; this is not an unattended-operation guarantee.

**Previous:** [Install Fedora](https://github.com/xjamesmorris/k3-com260-info/wiki/Install-Fedora) | **Next:** [Maintain and update](https://github.com/xjamesmorris/k3-com260-info/wiki/Maintain-and-Update)
