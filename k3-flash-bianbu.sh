#!/usr/bin/env bash
# k3-flash-bianbu.sh — full factory flash of a SpacemiT K3 (CoM260 tested)
# from an official Bianbu K3 release tarball, using plain fastboot.
#
# Mirrors the fastboot.yaml recipe that ships inside the tarball
# (TitanFlasher's own sequence), minus TitanFlasher.
#
# Usage:
#   1. Untar the Bianbu release (e.g. Bianbu-LXQt-K3-v4.0.4-*.tar.gz)
#   2. Put the board in recovery: hold FC_REC (pin 10 -> GND), power on
#      (or pulse RST), release FC_REC, connect USB-C.
#   3. ./k3-flash-bianbu.sh <untarred-image-dir>
#
# Erases NOR firmware + all UFS contents. NVMe is not touched.
# Verified on K3-CoM260 (Firefly kit), Bianbu v4.0.1 Minimal and v4.0.4 LXQt.

set -euo pipefail

IMG_DIR="${1:?usage: $0 <untarred-bianbu-image-dir>}"
cd "$IMG_DIR"

# Files common to Bianbu K3 release tarballs. partition_4M.json targets the
# module's NOR (mtd); partition_universal.json targets UFS (blk).
REQUIRED=(factory/FSBL.bin factory/bootinfo_spinor.bin u-boot.itb ec.bin
          partition_4M.json partition_universal.json env.bin esos.itb
          fw_dynamic.itb bootfs.ext4 rootfs.ext4)
for f in "${REQUIRED[@]}"; do
    [[ -f $f ]] || { echo "missing: $IMG_DIR/$f" >&2; exit 1; }
done
command -v fastboot >/dev/null || { echo "fastboot not found" >&2; exit 1; }

step() { printf '\n== %s\n' "$*"; }

# After each 'continue' the device drops off USB and re-enumerates. Fixed
# sleeps are unreliable, and so is 'fastboot devices' (a stale node can be
# listed while writes still fail — observed). Poll with a real protocol
# round-trip instead: the device is ready iff a getvar gets an answer.
# Any response counts, including a remote FAILED — that still proves the
# transport works. 'timeout' guards against fastboot blocking forever on
# '< waiting for any device >'.
wait_for_device() {
    local t=0 out
    while :; do
        out=$(timeout 5 fastboot getvar version 2>&1) || true
        case $out in
            *version:*|*'FAILED (remote'*) return 0 ;;
        esac
        sleep 1
        (( ++t > 30 )) && { echo "device did not re-enumerate" >&2; exit 1; }
    done
}

# --- Stage 1: bootstrap RAM loaders (BootROM -> FSBL -> U-Boot) -------------
# If the board is already past BootROM (e.g. re-running after a partial flash),
# the version-brom probe fails and the FSBL stage is skipped — matching the
# skip_when logic in fastboot.yaml.

step "BootROM check"
if fastboot getvar version-brom 2>&1 | grep -q '^version-brom'; then
    step "Stage FSBL"
    fastboot stage factory/FSBL.bin
    fastboot continue
    wait_for_device

    step "Stage U-Boot"
    fastboot stage u-boot.itb
    fastboot continue
    wait_for_device
else
    echo "not in BootROM — assuming loaders already staged, continuing at EC"
fi

# --- Stage 2: embedded controller ------------------------------------------
# Non-fatal by design (matches skip_fail in fastboot.yaml): an up-to-date EC
# may nack the flash.
step "EC firmware (failure here is non-fatal)"
fastboot stage ec.bin        || echo "EC stage nacked — continuing"
fastboot oem ec:flash        || echo "EC flash nacked — continuing"

# --- Stage 3: partition tables, NOR firmware chain, UFS OS ------------------
step "Partition tables"
fastboot flash mtd partition_4M.json
fastboot flash gpt partition_universal.json

step "NOR firmware chain"
fastboot flash bootinfo factory/bootinfo_spinor.bin
fastboot flash fsbl     factory/FSBL.bin
fastboot flash env      env.bin
fastboot flash esos     esos.itb
fastboot flash opensbi  fw_dynamic.itb
fastboot flash uboot    u-boot.itb

step "UFS OS partitions (rootfs is large — takes minutes)"
fastboot flash bootfs   bootfs.ext4
fastboot flash rootfs   rootfs.ext4

step "Done. Power-cycle the board and watch the serial console (115200 8N1)."

