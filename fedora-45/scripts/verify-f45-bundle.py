#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read the adjacent public lock and verify one pinned update's five binary RPMs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


IMAGE_RELEASE = "7.2.7-300.0.riscv64.omni.fc45.riscv64"
KERNEL_BUILD = 11035571
KERNEL_RELEASE = "7.2.8-300.0.riscv64.omni.fc45.riscv64"
SOURCE_RPM = "kernel-7.2.8-300.0.riscv64.omni.fc45.src.rpm"
UPGRADE_BUILD = 11177969
UPGRADE_PROJECT = "@forge-riscv-members/riscv64_omni_mainline_kernel"
UPGRADE_RELEASE = "7.3.0-65.1.riscv64.omni.fc45.riscv64"
UPGRADE_SOURCE_RPM = "kernel-7.3.0-65.1.riscv64.omni.fc45.src.rpm"
UPGRADE_DTB = "spacemit/k3-com260-ifx.dtb"
PACKAGE_NAMES = (
    "kernel", "kernel-core", "kernel-modules-core", "kernel-modules",
    "kernel-modules-extra",
)
IMAGE_FILENAME = "Fedora-Server-Host-Omni-45-20260923.2.riscv64.raw.xz"
IMAGE_BASE = (
    "https://dl.fedoraproject.org/pub/alt/risc-v/releases/test/"
    "45_Beta/Server/riscv64/images/"
)
BINARY_BASE = (
    "https://download.copr.fedorainfracloud.org/results/"
    "@forge-riscv-members/riscv64_omni_kernel/fedora-45-riscv64/Packages/k/"
)
UPGRADE_BASE = (
    "https://download.copr.fedorainfracloud.org/results/"
    "@forge-riscv-members/riscv64_omni_mainline_kernel/fedora-45-riscv64/"
    "Packages/k/"
)
RPM_QUERY = (
    "%{NAME}\t%{EPOCHNUM}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\t%{SOURCERPM}\n"
)


class Error(Exception):
    pass


def directory(path):
    if ".." in Path(path).parts:
        raise Error("Parent traversal is not accepted in input paths.")
    path = Path(os.path.abspath(path))
    for component in (*reversed(path.parents), path):
        if not stat.S_ISDIR(component.lstat().st_mode):
            raise Error("Directory path contains a symlink or non-directory.")
    return path


def open_regular(path):
    path = directory(Path(path).parent) / Path(path).name
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        os.close(fd)
        raise Error("Input must be a regular, single-link, non-symlink file.")
    return os.fdopen(fd, "rb")


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Error("Duplicate JSON key in sources.lock.json.")
        result[key] = value
    return result


def keys(value, expected, label):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise Error(f"Invalid {label} keys in sources.lock.json.")


def digest(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise Error("Invalid SHA-256 in sources.lock.json.")


def check_packages(packages, base, release):
    if not isinstance(packages, list) or len(packages) != len(PACKAGE_NAMES):
        raise Error("Each pinned update must contain exactly five binary RPMs.")
    for package, name in zip(packages, PACKAGE_NAMES):
        keys(package, ("name", "filename", "url", "sha256"), "package")
        filename = f"{name}-{release}.rpm"
        if (
            package["name"] != name or package["filename"] != filename
            or package["url"] != base + filename
        ):
            raise Error("Unexpected package identity or unsafe lock path/URL.")
        digest(package["sha256"])


def load_lock():
    script = Path(__file__).absolute()
    with open_regular(script):
        pass
    path = script.parent.parent / "files" / "sources.lock.json"
    with open_regular(path) as stream:
        encoded = stream.read(65537)
    if len(encoded) > 65536:
        raise Error("sources.lock.json is too large.")
    lock = json.loads(encoded.decode("utf-8"), object_pairs_hook=object_pairs)
    keys(lock, ("schema", "recorded_on", "image", "kernel", "upgrades"),
         "top-level")
    if type(lock["schema"]) is not int or lock["schema"] != 2:
        raise Error("Unsupported sources.lock.json schema.")
    if lock["recorded_on"] != "2026-10-21":
        raise Error("Unexpected lock recording date.")

    image = lock["image"]
    keys(image, ("url", "checksum_url", "filename", "sha256", "kernel_release"),
         "image")
    if (
        image["filename"] != IMAGE_FILENAME
        or image["url"] != IMAGE_BASE + IMAGE_FILENAME
        or image["checksum_url"] != IMAGE_BASE + IMAGE_FILENAME + ".sha256"
        or image["kernel_release"] != IMAGE_RELEASE
    ):
        raise Error("Unexpected image identity in sources.lock.json.")
    digest(image["sha256"])

    kernel = lock["kernel"]
    keys(kernel, (
        "build_id", "kernel_release", "source_rpm", "source_git_commit",
        "primary_metadata_sha256", "packages",
    ), "kernel")
    if (
        type(kernel["build_id"]) is not int or kernel["build_id"] != KERNEL_BUILD
        or kernel["kernel_release"] != KERNEL_RELEASE
        or kernel["source_rpm"] != SOURCE_RPM
        or kernel["source_git_commit"] is not None
    ):
        raise Error("Unexpected kernel identity in sources.lock.json.")
    digest(kernel["primary_metadata_sha256"])
    check_packages(kernel["packages"], BINARY_BASE, KERNEL_RELEASE)

    upgrades = lock["upgrades"]
    if not isinstance(upgrades, list) or len(upgrades) != 1:
        raise Error("The lock must contain exactly the one pinned upgrade.")
    upgrade = upgrades[0]
    keys(upgrade, (
        "build_id", "copr_project", "kernel_release", "source_rpm",
        "source_git_commit", "primary_metadata_sha256", "requires_running",
        "boot_dtb", "packages",
    ), "upgrade")
    if (
        type(upgrade["build_id"]) is not int
        or upgrade["build_id"] != UPGRADE_BUILD
        or upgrade["copr_project"] != UPGRADE_PROJECT
        or upgrade["kernel_release"] != UPGRADE_RELEASE
        or upgrade["source_rpm"] != UPGRADE_SOURCE_RPM
        or upgrade["source_git_commit"] is not None
        or upgrade["requires_running"] != [KERNEL_RELEASE]
    ):
        raise Error("Unexpected upgrade identity in sources.lock.json.")
    digest(upgrade["primary_metadata_sha256"])
    keys(upgrade["boot_dtb"], ("path", "sha256"), "boot_dtb")
    if upgrade["boot_dtb"]["path"] != UPGRADE_DTB:
        raise Error("Unexpected boot DTB path in sources.lock.json.")
    digest(upgrade["boot_dtb"]["sha256"])
    check_packages(upgrade["packages"], UPGRADE_BASE, UPGRADE_RELEASE)
    return lock


def updates(lock):
    """Return every pinned update in lock order, in one common shape."""
    kernel = lock["kernel"]
    first = {
        "build_id": kernel["build_id"],
        "kernel_release": kernel["kernel_release"],
        "source_rpm": kernel["source_rpm"],
        "requires_running": [lock["image"]["kernel_release"]],
        "boot_dtb": None,
        "packages": kernel["packages"],
    }
    return [first, *lock["upgrades"]]


def select(lock, build):
    matches = [item for item in updates(lock) if item["build_id"] == build]
    if len(matches) != 1:
        raise Error(f"COPR build {build} is not pinned in sources.lock.json.")
    return matches[0]


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns)


def check_rpm(path, update):
    path = Path(path)
    matches = [
        item for item in update["packages"] if item["filename"] == path.name
    ]
    if len(matches) != 1:
        raise Error(f"RPM filename is not pinned for COPR build "
                    f"{update['build_id']}.")
    package = matches[0]
    version, _, remainder = update["kernel_release"].partition("-")
    release, _, arch = remainder.rpartition(".")
    with open_regular(path) as stream:
        before = file_identity(os.fstat(stream.fileno()))
        checksum = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
        if checksum.hexdigest() != package["sha256"]:
            raise Error(f"SHA-256 mismatch for {path.name}.")
        result = subprocess.run(
            ["rpm", "-qp", "--qf", RPM_QUERY, str(path.absolute())],
            check=False, stdout=subprocess.PIPE, text=True,
        )
        expected = (
            f'{package["name"]}\t0\t{version}\t{release}'
            f'\t{arch}\t{update["source_rpm"]}\n'
        )
        if result.returncode or result.stdout != expected:
            raise Error(f"Unexpected RPM metadata for {path.name}.")
        if (
            file_identity(os.fstat(stream.fileno())) != before
            or file_identity(path.lstat()) != before
        ):
            raise Error("RPM changed during verification.")


def verify_bundle(bundle, update):
    bundle = directory(bundle)
    expected = {item["filename"] for item in update["packages"]}
    actual = {entry.name for entry in bundle.iterdir()}
    if actual != expected:
        raise Error(f"Bundle must contain exactly the five pinned RPMs of COPR "
                    f"build {update['build_id']}; missing or extra entries are "
                    "not accepted.")
    for package in update["packages"]:
        check_rpm(bundle / package["filename"], update)
    if {entry.name for entry in bundle.iterdir()} != expected:
        raise Error("Bundle inventory changed during verification.")


def build_id(value):
    if not re.fullmatch("[1-9][0-9]{0,15}", value):
        raise argparse.ArgumentTypeError("expected a decimal COPR build ID")
    return int(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build", type=build_id, default=KERNEL_BUILD, metavar="BUILD_ID",
        help="Pinned COPR build used by plan, release, requires-running, "
             "boot-dtb, check-rpm and verify (default: %(default)s).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan", help="Print locked SHA-256, filename, URL rows.")
    commands.add_parser("release", help="Print the locked candidate release.")
    commands.add_parser("requires-running", help="Print each release that must be running to install the build.")
    commands.add_parser("boot-dtb", help="Print bootstrap, or packaged, DTB path and SHA-256.")
    commands.add_parser("builds", help="Print every pinned build ID and release.")
    commands.add_parser("bootstrap-release", help="Print the image's bootstrap release.")
    commands.add_parser("image", help="Print locked image SHA-256, filename and bootstrap release.")
    verify = commands.add_parser("verify", help="Verify an exact RPM directory.")
    verify.add_argument("bundle")
    single = commands.add_parser("check-rpm", help="Verify one locked RPM.")
    single.add_argument("rpm")
    args = parser.parse_args()
    try:
        lock = load_lock()
        update = select(lock, args.build)
        if args.command == "plan":
            for package in update["packages"]:
                print(package["sha256"], package["filename"], package["url"],
                      sep="\t")
        elif args.command == "release":
            print(update["kernel_release"])
        elif args.command == "requires-running":
            for release in update["requires_running"]:
                print(release)
        elif args.command == "boot-dtb":
            if update["boot_dtb"] is None:
                print("bootstrap")
            else:
                print("packaged", update["boot_dtb"]["path"],
                      update["boot_dtb"]["sha256"], sep="\t")
        elif args.command == "builds":
            for item in updates(lock):
                print(item["build_id"], item["kernel_release"], sep="\t")
        elif args.command == "bootstrap-release":
            print(lock["image"]["kernel_release"])
        elif args.command == "image":
            image = lock["image"]
            print(image["sha256"], image["filename"], image["kernel_release"],
                  sep="\t")
        elif args.command == "check-rpm":
            check_rpm(args.rpm, update)
        else:
            verify_bundle(args.bundle, update)
            print(f"Verified the five COPR build {update['build_id']} binary "
                  "RPMs against the public lock; this is not "
                  "publisher-signature verification.")
    except (Error, OSError, ValueError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
