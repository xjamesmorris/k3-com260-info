#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read the adjacent public lock and verify the exact five binary RPMs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


KERNEL_RELEASE = "7.2.8-300.0.riscv64.omni.fc45.riscv64"
SOURCE_RPM = "kernel-7.2.8-300.0.riscv64.omni.fc45.src.rpm"
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
    keys(lock, ("schema", "recorded_on", "image", "kernel"), "top-level")
    if type(lock["schema"]) is not int or lock["schema"] != 1:
        raise Error("Unsupported sources.lock.json schema.")
    if lock["recorded_on"] != "2026-10-19":
        raise Error("Unexpected lock recording date.")

    image = lock["image"]
    keys(image, ("url", "checksum_url", "filename", "sha256", "kernel_release"),
         "image")
    if (
        image["filename"] != IMAGE_FILENAME
        or image["url"] != IMAGE_BASE + IMAGE_FILENAME
        or image["checksum_url"] != IMAGE_BASE + IMAGE_FILENAME + ".sha256"
        or image["kernel_release"] != "7.2.7-300.0.riscv64.omni.fc45.riscv64"
    ):
        raise Error("Unexpected image identity in sources.lock.json.")
    digest(image["sha256"])

    kernel = lock["kernel"]
    keys(kernel, (
        "build_id", "kernel_release", "source_rpm", "source_git_commit",
        "primary_metadata_sha256", "packages",
    ), "kernel")
    if (
        type(kernel["build_id"]) is not int or kernel["build_id"] != 11035571
        or kernel["kernel_release"] != KERNEL_RELEASE
        or kernel["source_rpm"] != SOURCE_RPM
        or kernel["source_git_commit"] is not None
    ):
        raise Error("Unexpected kernel identity in sources.lock.json.")
    digest(kernel["primary_metadata_sha256"])
    packages = kernel["packages"]
    if not isinstance(packages, list) or len(packages) != len(PACKAGE_NAMES):
        raise Error("The lock must contain exactly five binary RPMs.")
    for package, name in zip(packages, PACKAGE_NAMES):
        keys(package, ("name", "filename", "url", "sha256"), "package")
        filename = f"{name}-{KERNEL_RELEASE}.rpm"
        if (
            package["name"] != name or package["filename"] != filename
            or package["url"] != BINARY_BASE + filename
        ):
            raise Error("Unexpected package identity or unsafe lock path/URL.")
        digest(package["sha256"])
    return lock


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns)


def check_rpm(path, lock):
    path = Path(path)
    matches = [
        item for item in lock["kernel"]["packages"]
        if item["filename"] == path.name
    ]
    if len(matches) != 1:
        raise Error("Unpinned RPM filename.")
    package = matches[0]
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
            f'{package["name"]}\t0\t7.2.8\t300.0.riscv64.omni.fc45'
            f'\triscv64\t{lock["kernel"]["source_rpm"]}\n'
        )
        if result.returncode or result.stdout != expected:
            raise Error(f"Unexpected RPM metadata for {path.name}.")
        if (
            file_identity(os.fstat(stream.fileno())) != before
            or file_identity(path.lstat()) != before
        ):
            raise Error("RPM changed during verification.")


def verify_bundle(bundle, lock):
    bundle = directory(bundle)
    expected = {item["filename"] for item in lock["kernel"]["packages"]}
    actual = {entry.name for entry in bundle.iterdir()}
    if actual != expected:
        raise Error("Bundle must contain exactly the five pinned RPMs; "
                    "missing or extra entries are not accepted.")
    for package in lock["kernel"]["packages"]:
        check_rpm(bundle / package["filename"], lock)
    if {entry.name for entry in bundle.iterdir()} != expected:
        raise Error("Bundle inventory changed during verification.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan", help="Print locked SHA-256, filename, URL rows.")
    commands.add_parser("release", help="Print the locked candidate release.")
    commands.add_parser("bootstrap-release", help="Print the required running bootstrap release.")
    commands.add_parser("image", help="Print locked image SHA-256, filename and bootstrap release.")
    verify = commands.add_parser("verify", help="Verify an exact RPM directory.")
    verify.add_argument("bundle")
    single = commands.add_parser("check-rpm", help="Verify one locked RPM.")
    single.add_argument("rpm")
    args = parser.parse_args()
    try:
        lock = load_lock()
        if args.command == "plan":
            for package in lock["kernel"]["packages"]:
                print(package["sha256"], package["filename"], package["url"],
                      sep="\t")
        elif args.command == "release":
            print(lock["kernel"]["kernel_release"])
        elif args.command == "bootstrap-release":
            print(lock["image"]["kernel_release"])
        elif args.command == "image":
            image = lock["image"]
            print(image["sha256"], image["filename"], image["kernel_release"],
                  sep="\t")
        elif args.command == "check-rpm":
            check_rpm(args.rpm, lock)
        else:
            verify_bundle(args.bundle, lock)
            print("Verified five binary RPMs against the public lock; "
                  "this is not publisher-signature verification.")
    except (Error, OSError, ValueError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
