#!/usr/bin/env bash
# k3-flash-bianbu.sh — full factory flash of a SpacemiT K3 (CoM260 tested)
# from an official Bianbu K3 release tarball, using plain fastboot.
#
# Mirrors the fastboot.yaml recipe that ships inside the tarball
# (TitanFlasher's own sequence), minus TitanFlasher.
#
# Usage:
#   1. Put the board in recovery: hold FC_REC (pin 10 -> GND), power on
#      (or pulse RST), release FC_REC, connect USB-C.
#   2. ./k3-flash-bianbu.sh [--check | --register-image] [--rm]
#          [--download-dir DIR] <image-dir | release.tar.gz | https://...>
#
#   Pass an already-untarred release dir, the release .tar.gz itself, or
#   an https URL of one. A tarball is checked against k3-image-manifest.txt
#   and extracted to images/<release>/ next to this script (a matching
#   existing extraction is reused, e.g. when re-running after a partial
#   flash). A URL is downloaded first, then handled like a local tarball.
#     --check           run every verification step but skip the flash
#     --rm              delete images/<release>/ after a successful flash
#                       (archive mode only; the .tar.gz is never touched)
#     --register-image  verify the tarball and pin it in the manifest, no
#                       flash; an already-pinned name is just re-verified
#     --download-dir D  where an https URL is saved (default: ../downloads
#                       relative to this script)
#
# Erases NOR firmware + all UFS contents. NVMe is not touched.
# Verified on K3-CoM260 (Firefly kit), Bianbu v4.0.1 Minimal and v4.0.4 LXQt.

set -euo pipefail

# Resolve repo-relative paths up front — the flash sequence cd's into the
# image dir, and the script may be invoked from anywhere.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MANIFEST=$SCRIPT_DIR/k3-image-manifest.txt
IMAGES_DIR=$SCRIPT_DIR/images

# Files common to Bianbu K3 release tarballs. partition_4M.json targets the
# module's NOR (mtd); partition_universal.json targets UFS (blk).
REQUIRED=(factory/FSBL.bin factory/bootinfo_spinor.bin u-boot.itb ec.bin
          partition_4M.json partition_universal.json env.bin esos.itb
          fw_dynamic.itb bootfs.ext4 rootfs.ext4)

die()  { echo "$*" >&2; exit 1; }
step() { printf '\n== %s\n' "$*"; }
usage() { die "usage: $0 [--check | --register-image] [--rm] [--download-dir DIR] <image-dir | bianbu-release.tar.gz | https://...tar.gz>"; }

# The sdcard .img.gz images sit right next to the tarballs — refuse early.
check_tarball_name() {
    case $1 in
        *.tar.gz|*.tgz) ;;
        *) die "not a release tarball (.tar.gz): $1" ;;
    esac
}

# Fail before any fastboot traffic, not mid-flash: every needed file must
# exist and be non-empty (a disk-full extraction can leave truncated files).
check_contents() {
    local f
    for f in "${REQUIRED[@]}"; do
        [[ -s $1/$f ]] || die "missing or empty: $1/$f"
    done
}

# Look NAME up in the manifest; sets MAN_SHA/MAN_SIZE, returns 1 if absent.
# The whole file is validated on every pass — it is our own data file, so
# malformed lines and duplicate names fail loud instead of first-match-wins.
manifest_lookup() {
    local line f seen=' '
    MAN_SHA='' MAN_SIZE=''
    [[ -f $MANIFEST ]] || die "manifest not found: $MANIFEST"
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*(#|$) ]] && continue
        read -r -a f <<<"$line"
        [[ ${#f[@]} -eq 3 && ${f[0]} =~ ^[0-9a-f]{64}$ && ${f[1]} =~ ^[0-9]+$ ]] ||
            die "malformed line in $MANIFEST: $line"
        [[ $seen == *" ${f[2]} "* ]] && die "duplicate entry in $MANIFEST: ${f[2]}"
        seen+="${f[2]} "
        [[ ${f[2]} == "$1" ]] && { MAN_SHA=${f[0]}; MAN_SIZE=${f[1]}; }
    done <"$MANIFEST"
    [[ -n $MAN_SHA ]]
}

# Gate the tarball before extraction. Known names must match the pinned
# size/sha256 exactly (size first: a truncated download fails instantly,
# before the hash pass). Unknown names are allowed with a warning so new
# releases stay usable — but they get a member-path scan in place of the
# trust a pinned hash provides.
verify_archive() {
    local name size sha members
    name=$(basename "$1")
    if manifest_lookup "$name"; then
        step "Verifying $name against manifest"
        size=$(stat -c %s "$1")
        [[ $size -eq $MAN_SIZE ]] ||
            die "$name: size $size != expected $MAN_SIZE — truncated download? re-download, do not flash"
        sha=$(sha256sum "$1"); sha=${sha%% *}
        [[ $sha == "$MAN_SHA" ]] ||
            die "$name: sha256 mismatch — corrupt download, re-download, do not flash"
        echo "ok: size and sha256 match"
    else
        step "WARNING: $name is not in $(basename "$MANIFEST") — continuing unverified"
        members=$(tar -tzf "$1") || die "$name: unreadable archive"
        if grep -qE '^/|(^|/)\.\.(/|$)' <<<"$members"; then
            die "$name: archive contains unsafe member paths"
        fi
        sha=$(sha256sum "$1"); sha=${sha%% *}
        echo "if this is a good release, pin it with --register-image, or append to $(basename "$MANIFEST"):"
        echo "$sha  $(stat -c %s "$1")  $name"
    fi
    ARCHIVE_SHA=$sha
}

# Extract atomically: work in a hidden .partial dir and mv into place only
# on success, so images/<release>/ can never exist half-populated. The trap
# reclaims the multi-GB partial on any failure or Ctrl-C.
extract_archive() {
    local free need
    mkdir -p "$IMAGES_DIR"
    need=$(( $(stat -c %s "$1") * 5 ))   # LXQt release untars to ~4.6x
    free=$(df --output=avail -B1 "$IMAGES_DIR" | tail -n1)
    (( free >= need )) ||
        die "need ~$((need / 1024**2)) MiB free under $IMAGES_DIR, have $((free / 1024**2)) MiB"
    PARTIAL=$IMAGES_DIR/.$(basename "$2").partial
    rm -rf "$PARTIAL"
    mkdir "$PARTIAL"
    trap 'rm -rf "$PARTIAL"' EXIT
    step "Extracting $(basename "$1") (rootfs is large — takes a while)"
    tar --no-same-owner -xzf "$1" -C "$PARTIAL"
    printf '%s %s\n' "$ARCHIVE_SHA" "$(basename "$1")" >"$PARTIAL/.k3-extracted-from"
    mv "$PARTIAL" "$2"
    trap - EXIT
}

# Fetch an https release URL into DL_DIR. Atomic like extract_archive
# (.partial + mv), so a file already in DL_DIR is always a completed
# download and safe to reuse — verification still gates it either way.
download_archive() {
    local name dest
    name=${1%%\?*}; name=${name%%#*}; name=$(basename "$name")
    check_tarball_name "$name"
    dest=$DL_DIR/$name
    if [[ -f $dest ]]; then
        step "Using already-downloaded $dest"
    else
        command -v curl >/dev/null || die "curl not found"
        mkdir -p "$DL_DIR"
        PARTIAL=$DL_DIR/.$name.partial
        rm -f "$PARTIAL"
        trap 'rm -rf "$PARTIAL"' EXIT
        step "Downloading $name to $DL_DIR"
        # The --proto pins keep every hop https, redirects included.
        curl -fL --proto '=https' --proto-redir '=https' -o "$PARTIAL" "$1"
        mv "$PARTIAL" "$dest"
        trap - EXIT
    fi
    ARG=$dest
}

# --register-image: pin a release in the manifest. An already-pinned name is
# re-verified against its entry instead of duplicated. An unknown tarball
# must survive the member-path scan AND contain every REQUIRED file — that
# keeps a random tarball (or a source archive) out of the manifest.
register_image() {
    local name size sha members f
    name=$(basename "$1")
    size=$(stat -c %s "$1")
    if manifest_lookup "$name"; then
        step "Verifying already-registered $name"
        [[ $size -eq $MAN_SIZE ]] ||
            die "$name: size $size != pinned $MAN_SIZE — file and manifest disagree"
        sha=$(sha256sum "$1"); sha=${sha%% *}
        [[ $sha == "$MAN_SHA" ]] ||
            die "$name: sha256 differs from pinned entry — file and manifest disagree"
        echo "ok: already in $(basename "$MANIFEST") and matching"
        return 0
    fi
    step "Checking $name before registering"
    members=$(tar -tzf "$1") || die "$name: unreadable archive"
    if grep -qE '^/|(^|/)\.\.(/|$)' <<<"$members"; then
        die "$name: archive contains unsafe member paths"
    fi
    for f in "${REQUIRED[@]}"; do
        grep -qFx -e "./$f" -e "$f" <<<"$members" ||
            die "$name: no $f in archive — not a Bianbu K3 release?"
    done
    sha=$(sha256sum "$1"); sha=${sha%% *}
    printf '%s  %s  %s\n' "$sha" "$size" "$name" >>"$MANIFEST"
    echo "registered in $(basename "$MANIFEST"): $sha  $size  $name"
}

CHECK=0 RM=0 REGISTER=0 ARG='' DL_DIR=''
while (( $# )); do
    case $1 in
        --check)          CHECK=1 ;;
        --rm)             RM=1 ;;
        --register-image) REGISTER=1 ;;
        --download-dir)   [[ $# -ge 2 ]] || usage; DL_DIR=$2; shift ;;
        -h|--help)        usage ;;
        -*)               usage ;;
        *)                [[ -n $ARG ]] && usage; ARG=$1 ;;
    esac
    shift
done
[[ -n $ARG ]] || usage
(( REGISTER && CHECK )) && die "--register-image and --check are mutually exclusive"
(( REGISTER && RM ))    && die "--rm does not apply to --register-image"

# An https URL is downloaded first, then handled like a local tarball.
case $ARG in
    https://*) DL_DIR=${DL_DIR:-$SCRIPT_DIR/../downloads}
               download_archive "$ARG" ;;
    http://*)  die "refusing plain http — use https" ;;
    *)         [[ -n $DL_DIR ]] && die "--download-dir only applies to an https:// image URL" ;;
esac

if (( REGISTER )); then
    [[ -d $ARG ]] && die "--register-image takes a tarball, not a directory"
    [[ -f $ARG ]] || die "no such file: $ARG"
    check_tarball_name "$ARG"
    register_image "$ARG"
    exit 0
fi

if [[ -d $ARG ]]; then
    # Untarred-dir mode. --rm is refused: never delete a directory this
    # script did not create.
    (( RM )) && die "--rm only applies to archive mode"
    IMG_DIR=$ARG
elif [[ -f $ARG ]]; then
    check_tarball_name "$ARG"
    verify_archive "$ARG"
    stem=$(basename "$ARG"); stem=${stem%.tar.gz}; stem=${stem%.tgz}
    IMG_DIR=$IMAGES_DIR/$stem
    if [[ -d $IMG_DIR ]]; then
        # Reuse only a provably matching extraction (stamp written by
        # extract_archive) — same name with different bytes must not slip by,
        # and a half-populated dir can't exist here thanks to the .partial mv.
        stamp_sha=
        if [[ -f $IMG_DIR/.k3-extracted-from ]]; then
            read -r stamp_sha _ <"$IMG_DIR/.k3-extracted-from" || true
        fi
        [[ $stamp_sha == "$ARCHIVE_SHA" ]] ||
            die "$IMG_DIR exists but was not extracted from this archive — rm -rf it first"
        step "Reusing extraction $IMG_DIR"
    else
        extract_archive "$ARG" "$IMG_DIR"
    fi
else
    die "no such file or directory: $ARG"
fi

check_contents "$IMG_DIR"
if ! command -v fastboot >/dev/null; then
    (( CHECK )) || die "fastboot not found"
    echo "note: fastboot not installed (ok for --check)"
fi
if (( CHECK )); then
    (( RM )) && echo "--rm ignored with --check (nothing was flashed)"
    echo "all checks passed: $IMG_DIR"
    exit 0
fi

cd "$IMG_DIR"

# After each 'continue' the device drops off USB and re-enumerates. Fixed
# sleeps are unreliable, and so is 'fastboot devices' (a stale node can be
# listed while writes still fail — observed). Poll with a real protocol
# round-trip instead: the device is ready iff a getvar gets an answer.
# Any response counts, including a remote FAILED — that still proves the
# transport works. 'timeout' guards against fastboot blocking forever on
# '< waiting for any device >'.
wait_for_device() {
    local t=0 out
    printf 'waiting for re-enumeration'
    while :; do
        out=$(timeout 5 fastboot getvar version 2>&1) || true
        case $out in
            *version:*|*'FAILED (remote'*) echo ' ok'; return 0 ;;
        esac
        printf '.'
        sleep 1
        (( ++t > 30 )) && { echo; echo "device did not re-enumerate" >&2; exit 1; }
    done
}

# --- Stage 1: bootstrap RAM loaders (BootROM -> FSBL -> U-Boot) -------------
# If the board is already past BootROM (e.g. re-running after a partial flash),
# the version-brom probe fails and the FSBL stage is skipped — matching the
# skip_when logic in fastboot.yaml.

# The first fastboot command must never run bare: with no usable device
# (board not in recovery, USB-C not connected, udev perms) fastboot blocks
# forever on '< waiting for any device >' — and the old pipe-to-grep
# swallowed that message, so the script sat at "BootROM check" silently.
# Poll the same probe under timeout with visible progress instead; its
# answer also tells us the entry stage (BootROM answers 'version-brom: ...',
# a later stage answers remote FAILED — either way the transport is up).
# fastboot.yaml puts a 1 s timeout on this exact getvar for the same reason.
step "Waiting for fastboot device (Ctrl-C to abort)"
t=0 IN_BROM=
while [[ -z $IN_BROM ]]; do
    out=$(timeout 5 fastboot getvar version-brom 2>&1) || true
    if grep -q '^version-brom' <<<"$out"; then
        IN_BROM=1
    elif [[ $out == *'FAILED (remote'* ]]; then
        IN_BROM=0
    else
        printf '.'
        (( t == 6 )) && printf '\nno device yet — recovery entry: hold FC_REC (pin 10 -> GND), power on or pulse RST, release, connect USB-C\n'
        (( ++t >= 24 )) && { echo
            die "no fastboot device after ~2 min; check 'fastboot devices' (a 'no permissions' entry means udev rules are missing)"; }
    fi
done
echo

step "BootROM check"
if (( IN_BROM )); then
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

# Reaching here means every flash step succeeded (set -e) — only then may
# the extraction be reclaimed. Guard the rm to the directory we created.
if (( RM )); then
    [[ $IMG_DIR == "$IMAGES_DIR"/* ]] || die "refusing to delete $IMG_DIR: outside $IMAGES_DIR"
    step "Removing extraction $IMG_DIR (--rm)"
    cd "$SCRIPT_DIR"
    rm -rf "$IMG_DIR"
fi
