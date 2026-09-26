<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Fedora 44 and a persistent KVM guest on K3 CoM260

For experienced Linux bring-up users: stock non-UEFI Bianbu/U-Boot on a
SpacemiT K3 CoM260 IFX/Firefly carrier, Fedora on NVMe, a locally built
dldo4-patched host, and the persistent Fedora guest used for our interactive
QEMU/KVM sessions.

Every U-Boot choice below is temporary. Never run `env save` or `saveenv`.
Reset returns to the board's existing saved boot path, which may be Bianbu
rather than either Fedora kernel.

This is bring-up material, not a production or hostile-guest isolation claim.
Keep the bootstrap host on a trusted, isolated LAN and change its shipped
credentials before exposing it to another network.

## Recorded snapshot

| Item | Recorded value |
| --- | --- |
| Hardware | CoM260/Firefly, 8 GiB RAM; WD Red SN700 500 GB in the 2280 slot, imaged through a USB NVMe enclosure |
| Firmware | Bianbu Minimal K3 v4.0.1, non-UEFI U-Boot |
| Bootstrap | Fedora 44 Omni, July 31 image, `7.1.5-201.0.riscv64.omni.fc44.riscv64` |
| KVM host | `7.3.0-rc4-k3-kvm-host-a1` |
| QEMU | Fedora `10.2.2-1.fc44` |
| Guest | Fedora 44 Cloud, June 4 image, `6.19.8-200.0.riscv64.fc43.riscv64`, 4 vCPUs / 4 GiB |

This is the September 25, 2026 setup, not a "latest" recommendation. Image
checksums are enforced below and by the guest preparer. The pinned host
source, 14-patch order, config, and refresh rules are in
[`files/kernel/README.md`](files/kernel/README.md).

## Workstation, serial, and notation

Use Bash and simple paths without spaces. Commands identify their machine;
variables do not cross SSH sessions or tmux windows. These are interactive
steps, not one script: stop on any failed check rather than pasting onward.
Do not enable `set -u` in the interactive Fedora shell; its prompt hook uses
an unset variable.

Have Git, SSH, tmux, picocom, curl, xz, zstd, dtc, util-linux, udevadm, GNU
coreutils, and `partprobe` (parted) available before preparing the SSD.
Build and guest-preparation dependencies are listed in their sections.

```sh
# workstation
export WORK="$HOME/k3-fedora-howto"
mkdir -p "$WORK"
git clone https://github.com/xjamesmorris/k3-com260-info.git "$WORK/k3-com260-info"
export HOWTO="$WORK/k3-com260-info/docs/k3-fedora-howto"
export SERIAL=/dev/serial/by-id/usb-REPLACE_WITH_YOUR_ADAPTER
export NVME_DISK=/dev/disk/by-id/usb-REPLACE_WITH_YOUR_NVME
export K3_SSH=fedora@k3-host.example
export GUEST_KEY="$HOME/.ssh/k3-fedora-guest"
cd "$HOWTO"
```

Replace the placeholders. `NVME_DISK` must be the enclosure's stable whole
disk ID. `K3_SSH` must be an explicit `fedora@operator-chosen-host`; the
transfer helper intentionally uses that image account and `/home/fedora`.

Connect a 3.3 V USB serial adapter to RX, TX, and ground only. Use 115200 8N1,
no flow control:

```sh
# workstation
tmux new-session -s k3-serial
export SERIAL=/dev/serial/by-id/usb-REPLACE_WITH_YOUR_ADAPTER
picocom --baud 115200 --flow n "$SERIAL"
```

Confirm that Bianbu 4.0.1 U-Boot appears and autoboot can be interrupted.
Keep physical reset or power-cycle access. If this works, do not reflash
firmware or erase UFS. Only for actual recovery, use the public
[K3-CoM260 recovery guide](https://github.com/xjamesmorris/k3-com260-info/blob/main/tools/README.md);
factory flashing erases NOR and UFS, including the saved environment, but
does not erase NVMe.

## Image and prepare the NVMe

Download the pinned image; its checksum is checked again inside the write
step:

```sh
# workstation
set -o pipefail
export OMNI_IMAGE="$WORK/Fedora-Server-Host-Omni-44-20260731.0.riscv64.raw.xz"
curl --fail --location --output "$OMNI_IMAGE" https://dl.fedoraproject.org/pub/alt/risc-v/release/44/Server/riscv64/images/Fedora-Server-Host-Omni-44-20260731.0.riscv64.raw.xz
printf '%s  %s\n' bcbf6fcadc506b4b09ea46c88bf461ce3fb31bd54f125da3604969c3c06d0923 "$OMNI_IMAGE" |
  sha256sum --check --strict -
xz --test -- "$OMNI_IMAGE"
```

**The write below destroys the selected disk.** Positively identify the
stable ID, model, size, serial, and USB transport:

```sh
# workstation
export NVME_NODE
NVME_NODE=$(readlink -e -- "$NVME_DISK")
test -b "$NVME_NODE"
test "$(lsblk -dnro TYPE "$NVME_NODE")" = disk
test "$(lsblk -dnro TRAN "$NVME_NODE")" = usb
ls -l "$NVME_DISK"
lsblk -o NAME,PATH,SIZE,MODEL,SERIAL,TRAN,FSTYPE,MOUNTPOINTS "$NVME_NODE"
udevadm info --query=property --name="$NVME_NODE" | grep -E '^(ID_MODEL|ID_SERIAL|ID_WWN|ID_BUS)='
swapon --show=NAME,TYPE,SIZE
```

Unmount each listed filesystem with `sudo umount /dev/ACTUAL_PARTITION`;
disable any target-disk swap with `sudo swapoff /dev/ACTUAL_SWAP_PARTITION`.
Use the actual devices shown above, not those literal example names.
Do not disconnect or move the enclosure between inspection and writing.

Run the following block as a unit. Its subshell stops on a failed identity,
mount/swap, or checksum check before `dd`; strict mode does not leak into the
interactive shell. `lsblk` includes active swap as `[SWAP]`.

```sh
# workstation
(
  set -euo pipefail
  set -x
  : "${NVME_DISK:?}" "${NVME_NODE:?}" "${OMNI_IMAGE:?}"
  test "$(readlink -e -- "$NVME_DISK")" = "$NVME_NODE"
  test -b "$NVME_NODE"
  test "$(lsblk -dnro TYPE "$NVME_NODE")" = disk
  test "$(lsblk -dnro TRAN "$NVME_NODE")" = usb
  mountpoints=$(lsblk -nro MOUNTPOINTS "$NVME_NODE")
  if [[ "$mountpoints" =~ [^[:space:]] ]]; then
    printf 'Refusing an in-use disk (mounts or swap):\n%s\n' "$mountpoints" >&2
    exit 1
  fi
  printf '%s  %s\n' bcbf6fcadc506b4b09ea46c88bf461ce3fb31bd54f125da3604969c3c06d0923 "$OMNI_IMAGE" |
    sha256sum --check --strict -
  xz --test -- "$OMNI_IMAGE"
  lsblk -dn -o PATH,SIZE,MODEL,SERIAL,TRAN "$NVME_NODE"
  xz --decompress --stdout -- "$OMNI_IMAGE" |
    sudo dd of="$NVME_NODE" bs=16M oflag=direct conv=fsync status=progress
)
```

Only after that block succeeds, discover the new partitions:

```sh
# workstation
sync
sudo partprobe "$NVME_NODE"
udevadm settle
export NVME_BOOT="${NVME_DISK}-part2" NVME_ROOT="${NVME_DISK}-part3"
test -b "$NVME_BOOT" && test -b "$NVME_ROOT"
lsblk -o NAME,PATH,SIZE,FSTYPE,UUID,MOUNTPOINTS "$NVME_NODE"
export ROOT_UUID
ROOT_UUID=$(sudo blkid -s UUID -o value "$NVME_ROOT")
test -n "$ROOT_UUID"
printf 'NVMe root UUID: %s\n' "$ROOT_UUID"
```

The recorded layout is partition 1 ESP, partition 2 ext4 `/boot`, and
partition 3 Btrfs root with subvolume `root`. Use the UUID just discovered,
never a historical value.

Mount `/boot`, inspect its BLS entry, and select matching boot files:

```sh
# workstation
export BOOT_MNT="$WORK/omni-boot"
mkdir -p "$BOOT_MNT"
sudo mount -o rw "$NVME_BOOT" "$BOOT_MNT"
sudo find "$BOOT_MNT/loader/entries" -maxdepth 1 -type f -name '*.conf' \
  -exec sed -n '/^\(title\|version\|linux\|initrd\|options\) /p' {} +
export BOOT_KREL=7.1.5-201.0.riscv64.omni.fc44.riscv64
export VMLINUX="$BOOT_MNT/vmlinuz-$BOOT_KREL"
export INITRAMFS="$BOOT_MNT/initramfs-$BOOT_KREL.img"
export DTB="$BOOT_MNT/dtb-$BOOT_KREL/spacemit/k3-com260-ifx.dtb"
export RAW_IMAGE="$BOOT_MNT/Image-$BOOT_KREL"
export FIXED_DTB="$BOOT_MNT/dtb-$BOOT_KREL/spacemit/k3-com260-bootstrap.dtb"
test -f "$VMLINUX" && test -f "$INITRAMFS" && test -f "$DTB"
sudo sha256sum "$VMLINUX" "$INITRAMFS" "$DTB" > "$WORK/omni-original-boot.sha256"
```

Stop if the BLS entry or paths do not match this pinned kernel. Fedora
protects BLS entries and initramfs files; their inspection needs privilege.

The packaged `vmlinuz` is a zstd EFI zboot container; `booti` needs its raw
RISC-V Image. Parse and bound the little-endian payload:

```sh
# workstation
test "$(od -An -tx1 -N8 "$VMLINUX" | tr -d '[:space:]')" = 4d5a00007a696d67
test "$(od -An -tx1 -j24 -N5 "$VMLINUX" | tr -d '[:space:]')" = 7a73746400
OFF=$(od --endian=little -An -tu4 -j8 -N4 "$VMLINUX" | tr -d '[:space:]')
SIZE=$(od --endian=little -An -tu4 -j12 -N4 "$VMLINUX" | tr -d '[:space:]')
RAW_SIZE=$(od --endian=little -An -tu4 -j "$((OFF + SIZE))" -N4 "$VMLINUX" | tr -d '[:space:]')
test "$OFF" -ge 4096
test "$SIZE" -gt 0
test "$((OFF + SIZE + 4))" -le "$(stat -c %s "$VMLINUX")"
PAYLOAD="$WORK/$BOOT_KREL.zstd"
RAW_TMP="$WORK/Image-$BOOT_KREL"
test ! -e "$PAYLOAD" && test ! -e "$RAW_TMP" && test ! -e "$RAW_IMAGE"
dd if="$VMLINUX" of="$PAYLOAD" bs=1M iflag=skip_bytes,count_bytes skip="$OFF" count="$SIZE" status=progress
zstd --test --quiet -- "$PAYLOAD"
zstd --decompress --stdout --quiet -- "$PAYLOAD" > "$RAW_TMP"
test "$(od -An -tx1 -j48 -N8 "$RAW_TMP" | tr -d '[:space:]')" = 5249534356000000
HEADER_SIZE=$(od --endian=little -An -tu8 -j16 -N8 "$RAW_TMP" | tr -d '[:space:]')
test "$(stat -c %s "$RAW_TMP")" -eq "$RAW_SIZE"
test "$HEADER_SIZE" -eq "$RAW_SIZE"
sudo install -m 0644 -- "$RAW_TMP" "$RAW_IMAGE"
```

Leave the original DTB untouched. Decompile it, add
`regulator-always-on;` inside both `dldo4` and the root-level `hub-reset`
node, then build a separately named bootstrap DTB:

```sh
# workstation
DTS="$WORK/k3-com260-bootstrap.dts"
DTB_TMP="$WORK/k3-com260-bootstrap.dtb"
test ! -e "$DTS" && test ! -e "$DTB_TMP" && test ! -e "$FIXED_DTB"
dtc -I dtb -O dts -o "$DTS" "$DTB"
grep -n -E 'dldo4|hub-reset|regulator-always-on' "$DTS"
${EDITOR:-vi} "$DTS"
dtc -I dts -O dtb -o "$DTB_TMP" "$DTS"
dtc -I dtb -O dts "$DTB_TMP" | grep -n -E 'dldo4|hub-reset|regulator-always-on'
sudo install -m 0644 -- "$DTB_TMP" "$FIXED_DTB"
```

Inspect the regenerated DTS and confirm the property in both nodes. A DTB
round trip is not byte-identical, and this successful two-property workaround
does not prove both changes independently necessary. The later source-built
host carries the isolated dldo4 fix plus PCIe support, not the unrelated
USB/hub series.
Without the workaround, bring-up hit a hard lockup around unused-regulator
cleanup, roughly 30-45 seconds into boot; an early login prompt is not enough.

Record actual decimal and U-Boot hexadecimal sizes, then unmount:

```sh
# workstation
for file in "$FIXED_DTB" "$RAW_IMAGE" "$INITRAMFS"; do
  bytes=$(stat -c %s "$file")
  printf '%s: %u bytes, %x hex\n' "$(basename "$file")" "$bytes" "$bytes"
done | tee "$WORK/bootstrap-load-sizes.txt"
sync
sudo umount "$BOOT_MNT"
test -z "$(findmnt -rn -S "$NVME_BOOT" -o TARGET)"
```

Install the unmounted SSD in the carrier's 2280 slot; this recipe assumes it
is the only NVMe device. Remove microSD cards for this route: non-vendor SD
layouts stopped the stock BootROM before serial output during bring-up.

## Boot the bootstrap Fedora host

Interrupt U-Boot, replace the UUID, enter one line at a time, and compare all
three reported load sizes with `bootstrap-load-sizes.txt`. Before loading,
use the printed addresses and file sizes to check that the three memory
ranges `[address, address + size)` do not overlap. An empty 2230 slot may
report `PCIE-2: Link down`; that is not failure of the occupied 2280 slot.

```text
# U-Boot
printenv fdt_addr_r kernel_addr_r ramdisk_addr_r bootcmd
setenv bootrel 7.1.5-201.0.riscv64.omni.fc44.riscv64
setenv rootuuid REPLACE_WITH_DISCOVERED_UUID
nvme scan
load nvme 0:2 ${fdt_addr_r} dtb-${bootrel}/spacemit/k3-com260-bootstrap.dtb
printenv fileaddr filesize
load nvme 0:2 ${kernel_addr_r} Image-${bootrel}
printenv fileaddr filesize
load nvme 0:2 ${ramdisk_addr_r} initramfs-${bootrel}.img
setenv initrd_size ${filesize}
printenv fileaddr filesize initrd_size
setenv bootargs "root=UUID=${rootuuid} rootflags=subvol=root clk_ignore_unused console=ttyS0,115200n8"
printenv bootargs
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}
```

Stop before `booti` on an undefined address, failed load, size mismatch,
continuation prompt, malformed command line, or wrong UUID. Save nothing.

The pinned image shipped with `fedora` / `linux`. On the isolated LAN, log in
over serial, run `passwd`, record
`sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`, and inspect
`ip -brief address`, `uname -r`, and `findmnt /`. Install a normal workstation
public key for `fedora`, verify the SSH host key against the serial
fingerprint, and test `$K3_SSH`; never disable host-key checking. Do not
launch guests on this old Omni kernel.

## Build and install the KVM host

Use normal kernel build dependencies, Clang/LLD and LLVM tools, GNU
`riscv64-linux-gnu-` binutils, `dtc`, `pahole`, Git, and rsync. No earlier
build is required. `git am` needs your committer identity. Allow disk space
for a full Linux history plus the separate build:

```sh
# workstation
export KERNEL_REPO="$WORK/linux-kvm-riscv"
export HOST_OUTPUT="$WORK/k3-kvm-host-a1"
test ! -e "$KERNEL_REPO" && test ! -e "$HOST_OUTPUT"
git clone https://github.com/kvm-riscv/linux.git "$KERNEL_REPO"
test -z "$(git -C "$KERNEL_REPO" status --porcelain)"
git -C "$KERNEL_REPO" var GIT_COMMITTER_IDENT
cd "$HOWTO"
OUTPUT_ROOT="$HOST_OUTPUT" LOCAL_TAG=-k3-kvm-host-a1 JOBS="$(nproc)" \
  ./scripts/build-k3-kvm-host.sh "$KERNEL_REPO" "$HOWTO/files/kernel/config.seed"
test "$(cat "$HOST_OUTPUT/stage/kernelrelease")" = 7.3.0-rc4-k3-kvm-host-a1
(cd "$HOST_OUTPUT/stage" && sha256sum --check --strict SHA256SUMS)
```

The helper fetches the exact public commit into a private ref, creates a
detached worktree under the fresh output root, applies all 14 patches, and
verifies the prepared tree. It builds with
`ARCH=riscv LLVM=1 LLVM_IAS=0 CROSS_COMPILE=riscv64-linux-gnu-`; GNU `as`
avoids the tested module relocation problem, while split module BTF remains
disabled because the tested Clang/pahole output was rejected by this kernel.
If the object or tree cannot be reproduced, stop rather than advancing a ref.

Transfer from the workstation and install locally on the K3:

```sh
# workstation
export HOST_SUFFIX=k3-kvm-host-a1
cd "$HOWTO"
./scripts/transfer-omni-baseline-to-k3.sh "$HOST_OUTPUT/stage" "$K3_SSH" "$HOST_SUFFIX"
```

```sh
# K3 bootstrap host
export HOST_SUFFIX=k3-kvm-host-a1
export HOST_STAGE="/home/fedora/kernel-stage-$HOST_SUFFIX"
sudo "$HOST_STAGE/k3-install-manual-kernel.sh" "$HOST_STAGE" "$HOST_SUFFIX"
```

The installer adds the new kernel beside the running one and preserves
`/boot/dtb`. Derive the live root UUID and actual candidate sizes:

```sh
# K3 bootstrap host
export TESTREL=7.3.0-rc4-k3-kvm-host-a1
ROOT_SOURCE=$(findmnt -nro SOURCE /)
ROOT_DEVICE=${ROOT_SOURCE%%\[*}
ROOT_UUID=$(sudo blkid -s UUID -o value "$ROOT_DEVICE")
test -n "$ROOT_UUID"
printf 'root UUID: %s\n' "$ROOT_UUID"
for file in "/boot/dtb-$TESTREL/spacemit/k3-com260-ifx.dtb" "/boot/Image-$TESTREL" "/boot/initramfs-$TESTREL.img"; do
  bytes=$(stat -c %s "$file")
  printf '%s: %u bytes, %x hex\n' "$file" "$bytes" "$bytes"
done
```

At an attended reset, interrupt U-Boot and select the matching installed
triple. Check non-overlapping load ranges again and compare each load with
the sizes above. `boot_mode=nor` retains the recorded vendor token; Linux
may report it as an unknown parameter.

```text
# U-Boot
printenv fdt_addr_r kernel_addr_r ramdisk_addr_r bootcmd
setenv testrel 7.3.0-rc4-k3-kvm-host-a1
setenv rootuuid REPLACE_WITH_DISCOVERED_UUID
nvme scan
load nvme 0:2 ${fdt_addr_r} dtb-${testrel}/spacemit/k3-com260-ifx.dtb
printenv fileaddr filesize
load nvme 0:2 ${kernel_addr_r} Image-${testrel}
printenv fileaddr filesize
load nvme 0:2 ${ramdisk_addr_r} initramfs-${testrel}.img
setenv initrd_size ${filesize}
printenv fileaddr filesize initrd_size
setenv bootargs "root=UUID=${rootuuid} rootflags=subvol=root clk_ignore_unused console=ttyS0,115200n8 boot_mode=nor"
printenv bootargs
booti ${kernel_addr_r} ${ramdisk_addr_r}:${initrd_size} ${fdt_addr_r}
```

Again, save nothing and select this kernel manually after every reset. Once
Fedora returns:

```sh
# K3 KVM host
test "$(uname -r)" = 7.3.0-rc4-k3-kvm-host-a1
sudo dnf install qemu-system-riscv-core qemu-img python3 rsync tmux
findmnt -no SOURCE,FSTYPE,OPTIONS /
sudo dmesg --color=never | grep -iE 'hypervisor extension|G-stage|VMID|AIA'
test -c /dev/kvm
rpm -q qemu-system-riscv-core qemu-img
/usr/bin/qemu-system-riscv64 --version
test -r /dev/kvm && test -w /dev/kvm
```

The recorded endpoint used distro QEMU `10.2.2-1.fc44`. Run it as `fedora`;
if `/dev/kvm` is owned by group `kvm` but inaccessible, use
`sudo usermod -aG kvm fedora` and log in again. Otherwise inspect the normal
udev/group policy; never make the device world-writable.

## Prepare and run the persistent guest

The workstation needs `qemu-img`, libguestfs `virt-copy-out`,
`cloud-localds`, Python 3, `curl`, `zstd`, and `ssh-keygen`. Select or create
a key, retaining its private half only on the workstation:

```sh
# workstation
export GUEST_KEY="$HOME/.ssh/k3-fedora-guest"
test -f "$GUEST_KEY" && test -f "$GUEST_KEY.pub" || ssh-keygen -t ed25519 -f "$GUEST_KEY"
export GUEST_NAME=k3-fedora-44-20260604-a1
export GUEST_STAGE="$WORK/$GUEST_NAME"
test ! -e "$GUEST_STAGE"
cd "$HOWTO"
./scripts/prepare-riscv-fedora-guest.sh "$GUEST_STAGE" "$GUEST_KEY.pub"
(cd "$GUEST_STAGE" && sha256sum --check --strict SHA256SUMS)
```

The fresh stage contains the pinned base, NoCloud seed, validated raw guest
Image, initramfs, and a persistent `overlay.qcow2` whose relative backing
file is `base.img`. Transfer the complete tree with sparse-file handling:

```sh
# workstation
ssh "$K3_SSH" "test ! -e '/home/fedora/$GUEST_NAME' && test ! -e '/home/fedora/$GUEST_NAME.partial' && mkdir -m 0700 '/home/fedora/$GUEST_NAME.partial'"
rsync -aS --info=progress2 -- "$GUEST_STAGE/" "$K3_SSH:/home/fedora/$GUEST_NAME.partial/"
rsync -a -- "$HOWTO/scripts/k3-run-fedora-guest.sh" "$K3_SSH:/home/fedora/"
ssh "$K3_SSH" "set -eu; cd '/home/fedora/$GUEST_NAME.partial'; sha256sum --check --strict SHA256SUMS; cd /home/fedora; mv -- '$GUEST_NAME.partial' '$GUEST_NAME'"
```

Do not rename or separate `base.img` and `overlay.qcow2`.

Start `tmux new-session -s k3-fedora-guest` on the K3. These CPU overrides and
kernel arguments are **compatibility workarounds, not tuning preferences**.
Use the entire environment for this host/QEMU/guest combination: the helper's
generic bare-`host` defaults are not the validated Fedora guest recipe.
Leave Sstc enabled as recorded. Re-enter the block in every launch shell:

```sh
# K3 KVM host, inside tmux
export RUNNER=/home/fedora/k3-run-fedora-guest.sh
export GUEST_DIR=/home/fedora/k3-fedora-44-20260604-a1
export K3_FEDORA_AIA=plic
export K3_FEDORA_CPU='host,svpbmt=false,zicbom=false,zicbop=false,zicboz=false'
export K3_FEDORA_VCPUS=4 K3_FEDORA_MEMORY=4G K3_FEDORA_SSH_PORT=2222
export K3_FEDORA_EXTRA_APPEND='earlycon=sbi unaligned_scalar_speed=slow unaligned_vector_speed=unsupported'
test "$(uname -r)" = 7.3.0-rc4-k3-kvm-host-a1 &&
  "$RUNNER" run "$GUEST_DIR" /usr/bin/qemu-system-riscv64
```

Keep these settings, including enabled Sstc, on subsequent launches. The
recorded interactive session used `resume`:

```sh
# K3 KVM host, after a clean shutdown
test "$(uname -r)" = 7.3.0-rc4-k3-kvm-host-a1 &&
  "$RUNNER" resume "$GUEST_DIR" /usr/bin/qemu-system-riscv64
```

`resume` boots the same persistent disk; it does not restore a VM snapshot.
For status from another K3 shell:

```sh
# K3 KVM host, second shell
~/k3-run-fedora-guest.sh status ~/k3-fedora-44-20260604-a1
```

The guest's port 22 is exposed only on K3 loopback port 2222. Tunnel from one
workstation shell, then connect from another with the same seed identity:

```sh
# workstation; keep running
export K3_SSH=fedora@k3-host.example
ssh -N -o ExitOnForwardFailure=yes -o ForwardAgent=no \
  -L 127.0.0.1:2222:127.0.0.1:2222 "$K3_SSH"
```

```sh
# workstation, second shell
export GUEST_KEY="$HOME/.ssh/k3-fedora-guest"
ssh -o IdentitiesOnly=yes -o HostKeyAlias=k3-fedora-44-20260604-a1 \
  -i "$GUEST_KEY" -p 2222 fedora@127.0.0.1
```

Never use `StrictHostKeyChecking=no`. Verify the K3 key over serial. For the
new guest key, use a trusted inspection path or record an explicit
trust-on-first-use decision over this verified tunnel. Do not copy the guest
private key to the K3 or assume agent forwarding.

```sh
# guest
sudo dnf install fastfetch
fastfetch
systemd-detect-virt --vm
nproc
findmnt -no SOURCE,FSTYPE,OPTIONS /
sudo journalctl -k -b | grep -iE 'SBI specification|SBI implementation|earlycon|PLIC|IMSIC|APLIC'
```

`fastfetch` is a summary, not proof of KVM. The helper requires `-accel kvm`
and `/dev/kvm`; it never falls back to software emulation.

The seeded `fedora` account is password-locked. From authenticated guest SSH,
run `sudo passwd fedora` only if serial login is wanted. Prefer
`sudo systemctl poweroff` from that SSH session, let foreground QEMU exit,
then use `resume`. Do not use `Ctrl-a x`, QMP `quit`, SIGKILL, or force-kill
for normal shutdown.

The optional runner `stop` action needs a usable guest identity or agent on
the K3; it does not acquire the workstation's private key. After PLIC has
booted and shut down cleanly, AIA is the tested alternative:

```sh
# K3 KVM host; other exported settings unchanged
test "$(uname -r)" = 7.3.0-rc4-k3-kvm-host-a1 &&
  K3_FEDORA_AIA=aplic-imsic "$RUNNER" resume "$GUEST_DIR" /usr/bin/qemu-system-riscv64
```

## Updating this snapshot

Keep the Image, initramfs, DTB, modules, and release name matched. Packaged
kernel updates need another raw-Image extraction and deliberate U-Boot
selection; they do not update this direct-boot path automatically.

Display, external USB, fan/thermal policy, suspend, VFIO, and long-duration
stability are outside this recipe. Other carriers, UEFI/libvirt, and newer
image/kernel/toolchain combinations are alternatives, not validated
substitutions. The historical stages ran on hardware; this portable bundle
has not been rerun end to end. License: GPL-2.0-only.
