# SPDX-License-Identifier: GPL-2.0-only
"""Offline fixtures only: no board, network, real RPM installation or /boot."""

import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import struct
import subprocess
import sys
import textwrap
import unittest


SUPPORT = Path(__file__).resolve().parents[1]
FIRST_BUILD = 11035571
UPGRADE_BUILD = 11177969
MOCK = textwrap.dedent(r"""\
#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

command = Path(sys.argv[0]).name
args = sys.argv[1:]
record = {"command": command, "args": args}
if command == "ssh":
    record["stdin"] = sys.stdin.read()
with open(os.environ["F45_TEST_LOG"], "a", encoding="utf-8") as stream:
    stream.write(json.dumps(record) + "\n")

lock = json.loads(Path(os.environ["F45_TEST_LOCK"]).read_text())
updates = [lock["kernel"], *lock.get("upgrades", [])]
packages = [package for update in updates for package in update["packages"]]
# VERSION and RELEASE as real rpm reports them for each pinned kernel release.
HEADERS = {
    "7.2.8-300.0.riscv64.omni.fc45.riscv64": ("7.2.8", "300.0.riscv64.omni.fc45"),
    "7.3.0-65.1.riscv64.omni.fc45.riscv64": ("7.3.0", "65.1.riscv64.omni.fc45"),
}
if command == "curl":
    matches = [p for p in packages if p["url"] == args[-1]]
    if len(matches) != 1:
        sys.exit("mock curl refuses an unpinned download")
    package = matches[0]
    data = (Path(os.environ["F45_TEST_ARTIFACTS"]) / package["filename"]).read_bytes()
    if os.environ.get("F45_TEST_BAD_SHA") == package["name"]:
        data += b"corrupted download"
    Path(args[args.index("--output") + 1]).write_bytes(data)
elif command == "rpm":
    if "-qp" in args:
        update, package = next(
            (update, package) for update in updates
            for package in update["packages"]
            if package["filename"] == Path(args[-1]).name
        )
        name = package["name"]
        if os.environ.get("F45_TEST_WRONG_METADATA"):
            name = "unrelated-package"
        if os.environ.get("F45_TEST_HEADER_OF"):
            update = next(u for u in updates
                          if u["build_id"] == int(os.environ["F45_TEST_HEADER_OF"]))
        version, release = HEADERS[update["kernel_release"]]
        print("\t".join((name, "0", version, release, "riscv64",
                         update["source_rpm"])))
    elif "-q" in args and "--quiet" in args:
        if os.environ.get("F45_TEST_RPM_DB_ERROR"):
            sys.exit(2)
        sys.exit(0 if os.environ.get("F45_TEST_INSTALLED") else 1)
    else:
        sys.exit("unexpected RPM operation")
elif command == "uname":
    print(os.environ.get("F45_TEST_RUNNING", lock["image"]["kernel_release"])
          if args == ["-r"] else "riscv64")
elif command == "id":
    assert args == ["-un"]
    print(os.environ.get("F45_TEST_REMOTE_USER", "fedora"))
elif command == "df":
    print("Filesystem 1-blocks Used Available Capacity Mounted-on")
    print("fixture 9999999999999 1 9999999999998 1% .")
elif command == "ssh":
    remote_home = Path(os.environ["F45_TEST_REMOTE_HOME"])
    env = dict(os.environ, HOME=str(remote_home))
    result = subprocess.run(
        ["/bin/sh", "-c", args[-1]], input=record["stdin"], text=True,
        cwd=remote_home.parent / "login cwd", env=env,
    )
    sys.exit(result.returncode)
elif command == "rsync":
    remote_home = Path(os.environ["F45_TEST_REMOTE_HOME"])
    target = args[-1].split(":", 1)[1]
    relative = Path(target)
    assert not relative.is_absolute() and ".." not in relative.parts
    destination = remote_home / relative
    sources = []
    index = 0
    while index < len(args) - 1:
        if args[index] == "-e":
            index += 2
        elif args[index].startswith("--"):
            index += 1
        else:
            sources.append(args[index])
            index += 1
    for source_arg in sources:
        source = Path(source_arg)
        if source.is_dir() and source_arg.endswith("/"):
            for child in source.iterdir():
                assert child.is_file() and not child.is_symlink()
                shutil.copy2(child, destination / child.name)
        else:
            shutil.copy2(source, destination / source.name
                         if target.endswith("/") else destination)
else:
    sys.exit("FORBIDDEN system-write command reached: " + command)
""").lstrip("\\\n")


class Helpers(unittest.TestCase):
    def setUp(self):
        self.work = SUPPORT / "tests" / (".fixture-" + secrets.token_hex(8))
        self.work.mkdir(mode=0o700)
        self.addCleanup(shutil.rmtree, self.work)
        self.support = self.work / "relocated support"
        shutil.copytree(SUPPORT / "scripts", self.support / "scripts")
        (self.support / "files").mkdir()
        self.lock_path = self.support / "files" / "sources.lock.json"
        self.lock = json.loads((SUPPORT / "files" / "sources.lock.json").read_text())
        self.artifacts = self.work / "download fixtures"
        self.artifacts.mkdir()
        for update in self.updates():
            for package in update["packages"]:
                data = ("offline binary fixture: " + package["filename"]).encode()
                package["sha256"] = hashlib.sha256(data).hexdigest()
                (self.artifacts / package["filename"]).write_bytes(data)
        self.bundle = self.make_bundle(FIRST_BUILD, "rpms")
        self.write_lock()
        self.bin = self.work / "mock commands"
        self.bin.mkdir()
        for command in (
            "curl", "rpm", "uname", "dnf", "dracut", "cp", "ln", "restorecon",
            "mount", "ssh", "rsync", "id", "df", "mkfs.ext4", "mkfs.btrfs",
            "losetup", "blkid", "lsblk", "systemctl", "wipefs",
        ):
            path = self.bin / command
            path.write_text(MOCK)
            path.chmod(0o755)
        self.other_cwd = self.work / "unrelated cwd"
        self.other_cwd.mkdir()
        self.remote_home = self.work / "remote fedora home"
        self.remote_home.mkdir()
        (self.work / "login cwd").mkdir()
        self.log = self.work / "commands.jsonl"
        self.env = dict(
            os.environ,
            PATH=str(self.bin) + os.pathsep + os.environ["PATH"],
            PYTHONDONTWRITEBYTECODE="1",
            F45_TEST_LOCK=str(self.lock_path),
            F45_TEST_LOG=str(self.log),
            F45_TEST_ARTIFACTS=str(self.artifacts),
            F45_TEST_REMOTE_HOME=str(self.remote_home),
        )
        for name in ("BASH_ENV", "INCLUDE_SRPM", "INCLUDE_MODULES_EXTRA"):
            self.env.pop(name, None)

    def write_lock(self):
        self.lock_path.write_text(json.dumps(self.lock, indent=2) + "\n")

    def updates(self):
        return [self.lock["kernel"], *self.lock["upgrades"]]

    def update(self, build):
        return next(item for item in self.updates() if item["build_id"] == build)

    def make_bundle(self, build, name=None):
        bundle = self.work / (name or f"rpms {build}")
        bundle.mkdir()
        for package in self.update(build)["packages"]:
            shutil.copyfile(self.artifacts / package["filename"],
                            bundle / package["filename"])
        return bundle

    def run_helper(self, name, *args, extra_env=None):
        command = [str(self.support / "scripts" / name), *map(str, args)]
        if name.endswith(".py"):
            command = [sys.executable, "-B", *command]
        return subprocess.run(
            command, cwd=self.other_cwd, env=dict(self.env, **(extra_env or {})),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30,
        )

    def commands(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def assert_preflight_refusal(self, result, diagnostic):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(diagnostic, result.stderr)
        forbidden = {"dnf", "dracut", "cp", "ln", "restorecon", "mount"}
        self.assertFalse(forbidden.intersection(c["command"] for c in self.commands()))
        self.assertNotIn("/boot", result.stderr, "preflight reached host boot paths")

    def installer(self, **env):
        return self.run_helper("k3-install-rpm-kernel.sh", self.bundle, extra_env=env)

    def test_fetch_defaults_to_exact_five_binaries_after_relocation(self):
        output = self.work / "fetched rpms"
        result = self.run_helper("fetch-f45-copr-kernel.sh", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        packages = self.lock["kernel"]["packages"]
        self.assertEqual({p.name for p in output.iterdir()},
                         {p["filename"] for p in packages})
        curls = [c for c in self.commands() if c["command"] == "curl"]
        self.assertEqual([c["args"][-1] for c in curls], [p["url"] for p in packages])
        for call in curls:
            self.assertIn("--proto-redir", call["args"])
            self.assertEqual(call["args"][call["args"].index("--proto-redir") + 1],
                             "=https")
        self.assertFalse(Path(str(output) + ".partial").exists())

    def test_bad_download_digest_removes_only_owned_partial(self):
        output = self.work / "fetched rpms"
        marker = self.work / "keep"
        marker.write_bytes(b"unrelated")
        result = self.run_helper(
            "fetch-f45-copr-kernel.sh", output,
            extra_env={"F45_TEST_BAD_SHA": "kernel-core"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SHA-256 mismatch", result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(Path(str(output) + ".partial").exists())
        self.assertEqual(marker.read_bytes(), b"unrelated")

    def test_fetch_preserves_preexisting_partial(self):
        output = self.work / "fetched rpms"
        partial = Path(str(output) + ".partial")
        partial.mkdir()
        (partial / "keep").write_bytes(b"previous attempt")
        result = self.run_helper("fetch-f45-copr-kernel.sh", output)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((partial / "keep").read_bytes(), b"previous attempt")
        self.assertFalse(self.commands())

    def test_installer_rejects_extra_package_before_system_access(self):
        (self.bundle / "unexpected.rpm").write_bytes(b"not pinned")
        self.assert_preflight_refusal(self.installer(), "missing or extra")

    def test_installer_rejects_missing_package_before_system_access(self):
        (self.bundle / self.lock["kernel"]["packages"][-1]["filename"]).unlink()
        self.assert_preflight_refusal(self.installer(), "missing or extra")

    def test_installer_rejects_tampered_bytes_before_system_access(self):
        (self.bundle / self.lock["kernel"]["packages"][0]["filename"]).write_bytes(
            b"tampered but plausible filename"
        )
        self.assert_preflight_refusal(self.installer(), "SHA-256 mismatch")

    def test_installer_rejects_unpinned_package_before_system_access(self):
        package = self.lock["kernel"]["packages"][0]
        (self.bundle / package["filename"]).rename(self.bundle / "kernel-newer.rpm")
        self.assert_preflight_refusal(self.installer(), "missing or extra")

    def test_self_declared_checksum_manifest_is_not_a_trust_source(self):
        (self.bundle / "SHA256SUMS").write_text(
            "0" * 64 + "  ../outside.rpm\n"
        )
        self.assert_preflight_refusal(self.installer(), "missing or extra")

    def test_installer_rejects_package_symlink_before_system_access(self):
        package = self.lock["kernel"]["packages"][0]
        path = self.bundle / package["filename"]
        path.unlink()
        path.symlink_to(self.artifacts / package["filename"])
        result = self.installer()
        self.assert_preflight_refusal(result, "error:")

    def test_installer_rejects_symlinked_bundle_ancestor(self):
        alias = self.work / "bundle alias"
        alias.symlink_to(self.bundle, target_is_directory=True)
        result = self.run_helper("k3-install-rpm-kernel.sh", alias)
        self.assert_preflight_refusal(result, "symlink")

    def test_installer_rejects_symlink_hidden_by_parent_traversal(self):
        other = self.work / "other location" / "child"
        other.mkdir(parents=True)
        (other.parent / "rpms").mkdir()
        alias = self.work / "alias"
        alias.symlink_to(other, target_is_directory=True)
        result = self.run_helper(
            "k3-install-rpm-kernel.sh", str(alias) + "/../rpms"
        )
        self.assert_preflight_refusal(result, "Parent traversal")

    def test_installer_rejects_hardlinked_package(self):
        package = self.lock["kernel"]["packages"][0]
        os.link(self.bundle / package["filename"], self.work / "second link")
        self.assert_preflight_refusal(self.installer(), "single-link")

    def test_installer_rejects_unsafe_or_incomplete_public_lock(self):
        original = copy.deepcopy(self.lock)
        variants = []
        extra_key = copy.deepcopy(original)
        extra_key["private_dependency"] = "forbidden"
        variants.append(extra_key)
        missing_package = copy.deepcopy(original)
        missing_package["kernel"]["packages"].pop()
        variants.append(missing_package)
        bad_path = copy.deepcopy(original)
        bad_path["kernel"]["packages"][0]["filename"] = "../outside.rpm"
        variants.append(bad_path)
        bad_url = copy.deepcopy(original)
        bad_url["kernel"]["packages"][0]["url"] = "https://example.org/other.rpm"
        variants.append(bad_url)
        boolean_schema = copy.deepcopy(original)
        boolean_schema["schema"] = True
        variants.append(boolean_schema)
        for index, variant in enumerate(variants):
            with self.subTest(index=index):
                self.lock = variant
                self.write_lock()
                self.assert_preflight_refusal(self.installer(), "error:")

    def test_installer_rejects_duplicate_lock_keys(self):
        original = self.lock_path.read_text()
        data = original.replace('"schema": 2,', '"schema": 2, "schema": 2,', 1)
        self.assertNotEqual(data, original)
        self.lock_path.write_text(data)
        self.assert_preflight_refusal(self.installer(), "Duplicate JSON key")

    def test_installer_rejects_symlinked_public_lock(self):
        saved = self.lock_path.with_name("saved.json")
        self.lock_path.rename(saved)
        self.lock_path.symlink_to(saved)
        self.assert_preflight_refusal(self.installer(), "error:")

    def test_installer_rejects_mismatched_rpm_metadata(self):
        self.assert_preflight_refusal(
            self.installer(F45_TEST_WRONG_METADATA="1"), "Unexpected RPM metadata"
        )

    def test_installer_rejects_running_candidate_before_system_access(self):
        self.assert_preflight_refusal(
            self.installer(F45_TEST_RUNNING=self.lock["kernel"]["kernel_release"]),
            "already running",
        )

    def test_installer_rejects_saved_f44_boot_before_system_access(self):
        self.assert_preflight_refusal(
            self.installer(F45_TEST_RUNNING="7.1.5-201.0.riscv64.omni.fc44.riscv64"),
            "pinned F45 bootstrap",
        )

    def test_installer_rejects_installed_candidate_before_system_access(self):
        self.assert_preflight_refusal(
            self.installer(F45_TEST_INSTALLED="1"), "already installed"
        )

    def test_installer_refuses_unreadable_rpm_database(self):
        self.assert_preflight_refusal(
            self.installer(F45_TEST_RPM_DB_ERROR="1"), "Cannot query installed"
        )

    def test_transfer_refuses_unpinned_input_without_ssh(self):
        (self.bundle / "unlisted.rpm").write_bytes(b"untrusted")
        result = self.run_helper(
            "transfer-f45-copr-kernel-to-k3.sh", self.bundle, "fedora@k3.example.org"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse({"ssh", "rsync"}.intersection(
            c["command"] for c in self.commands()
        ))

    def test_transfer_refuses_wrong_account_without_ssh(self):
        result = self.run_helper(
            "transfer-f45-copr-kernel-to-k3.sh", self.bundle, "root@k3.example.org"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fedora account", result.stderr)
        self.assertFalse(self.commands())

    def test_transfer_refuses_ipv6_literal_before_creating_remote_state(self):
        result = self.run_helper(
            "transfer-f45-copr-kernel-to-k3.sh", self.bundle, "fedora@2001:db8::1"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("hostname or IPv4 address", result.stderr)
        self.assertFalse(self.commands())

    def test_transfer_carries_self_contained_bundle_to_quoted_remote_home(self):
        result = self.run_helper(
            "transfer-f45-copr-kernel-to-k3.sh", self.bundle, "fedora@k3.example.org"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.remote_home / "f45-copr-kernel-11035571"
        self.assertEqual(
            {str(p.relative_to(destination)) for p in destination.rglob("*")
             if p.is_file()},
            {"files/sources.lock.json",
             "scripts/k3-install-rpm-kernel.sh", "scripts/make-bootstrap-dtb.sh",
             "scripts/extract-riscv-zboot.sh", "scripts/verify-f45-bundle.py"}
            | {"rpms/" + p["filename"] for p in self.lock["kernel"]["packages"]},
        )
        self.assertEqual((destination / "files" / "sources.lock.json").read_bytes(),
                         self.lock_path.read_bytes())
        self.assertFalse(Path(str(destination) + ".partial").exists())
        for name in ("k3-install-rpm-kernel.sh", "extract-riscv-zboot.sh",
                     "make-bootstrap-dtb.sh"):
            self.assertTrue(os.access(destination / "scripts" / name, os.X_OK))
        calls = self.commands()
        for call in (c for c in calls if c["command"] == "ssh"):
            self.assertIn("StrictHostKeyChecking=yes", call["args"])
            self.assertIn('test "$(id -un)" = fedora', call["stdin"])
        for call in (c for c in calls if c["command"] == "rsync"):
            self.assertIn('--rsync-path=cd "$HOME" && exec rsync', call["args"])
        self.assertFalse({"dnf", "dracut", "cp", "ln", "restorecon"}.intersection(
            c["command"] for c in calls
        ))

    def test_transfer_verifies_remote_account_before_creating_directories(self):
        result = self.run_helper(
            "transfer-f45-copr-kernel-to-k3.sh", self.bundle, "fedora@k3.example.org",
            extra_env={"F45_TEST_REMOTE_USER": "not-fedora"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.remote_home.iterdir()), [])
        self.assertFalse(any(c["command"] == "rsync" for c in self.commands()))

    def test_transfer_refuses_existing_final_before_creating_a_partial(self):
        destination = self.remote_home / "f45-copr-kernel-11035571"
        destination.mkdir()
        marker = destination / "keep"
        marker.write_bytes(b"existing bundle")
        result = self.run_helper(
            "transfer-f45-copr-kernel-to-k3.sh", self.bundle, "fedora@k3.example.org"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Remote bundle path already exists", result.stderr)
        self.assertEqual(marker.read_bytes(), b"existing bundle")
        self.assertFalse(destination.with_name(destination.name + ".partial").exists())
        calls = self.commands()
        self.assertEqual(sum(c["command"] == "ssh" for c in calls), 1)
        self.assertFalse(any(c["command"] == "rsync" for c in calls))

    def test_transfer_refuses_existing_partial_in_the_first_remote_probe(self):
        partial = self.remote_home / "f45-copr-kernel-11035571.partial"
        partial.mkdir()
        marker = partial / "keep"
        marker.write_bytes(b"previous partial")
        result = self.run_helper(
            "transfer-f45-copr-kernel-to-k3.sh", self.bundle, "fedora@k3.example.org"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Remote bundle path already exists", result.stderr)
        self.assertEqual(marker.read_bytes(), b"previous partial")
        calls = self.commands()
        self.assertEqual(sum(c["command"] == "ssh" for c in calls), 1)
        self.assertFalse(any(c["command"] == "rsync" for c in calls))

    # Build selection: 7.2.8 first update (default) and the 7.3 upgrade.
    def verifier(self, *args, **env):
        return self.run_helper("verify-f45-bundle.py", *args, extra_env=env)

    def assert_no_rpm_database_query(self):
        self.assertFalse([c for c in self.commands()
                          if c["command"] == "rpm" and "-qp" not in c["args"]])

    def test_fetch_selected_build_downloads_only_its_five_urls(self):
        output = self.work / "fetched upgrade"
        result = self.run_helper("fetch-f45-copr-kernel.sh", "--build",
                                 UPGRADE_BUILD, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        packages = self.update(UPGRADE_BUILD)["packages"]
        self.assertEqual({p.name for p in output.iterdir()},
                         {p["filename"] for p in packages})
        curls = [c["args"][-1] for c in self.commands() if c["command"] == "curl"]
        self.assertEqual(curls, [p["url"] for p in packages])

    def test_verify_binds_a_bundle_to_the_selected_build(self):
        upgrade = self.make_bundle(UPGRADE_BUILD)
        result = self.verifier("--build", UPGRADE_BUILD, "verify", upgrade)
        self.assertEqual(result.returncode, 0, result.stderr)
        first_core = self.update(FIRST_BUILD)["packages"][1]["filename"]
        upgrade_core = self.update(UPGRADE_BUILD)["packages"][1]["filename"]
        upgrade_and_first = self.make_bundle(UPGRADE_BUILD, "upgrade plus first")
        shutil.copyfile(self.artifacts / first_core, upgrade_and_first / first_core)
        first_and_upgrade = self.make_bundle(FIRST_BUILD, "first with upgrade")
        (first_and_upgrade / first_core).unlink()
        shutil.copyfile(self.artifacts / upgrade_core,
                        first_and_upgrade / upgrade_core)
        cases = (
            (("--build", UPGRADE_BUILD, "verify", upgrade_and_first), {},
             "missing or extra"),
            (("verify", first_and_upgrade), {}, "missing or extra"),
            (("verify", upgrade), {}, "missing or extra"),
            (("--build", UPGRADE_BUILD, "check-rpm", self.bundle / first_core), {},
             "not pinned for COPR build"),
            (("--build", UPGRADE_BUILD, "verify", upgrade),
             {"F45_TEST_HEADER_OF": str(FIRST_BUILD)}, "Unexpected RPM metadata"),
        )
        for args, env, diagnostic in cases:
            with self.subTest(args=args[:-1], env=env):
                result = self.verifier(*args, **env)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(diagnostic, result.stderr)

    def test_build_queries_report_each_pinned_update(self):
        upgrade = self.update(UPGRADE_BUILD)
        upgrade["boot_dtb"]["sha256"] = hashlib.sha256(b"fixture DTB").hexdigest()
        self.write_lock()
        cases = (
            (("builds",), "".join(f"{u['build_id']}\t{u['kernel_release']}\n"
                                  for u in self.updates())),
            (("requires-running",), self.lock["image"]["kernel_release"] + "\n"),
            (("--build", UPGRADE_BUILD, "requires-running"),
             self.lock["kernel"]["kernel_release"] + "\n"),
            (("boot-dtb",), "bootstrap\n"),
            (("--build", UPGRADE_BUILD, "boot-dtb"), "packaged\t{path}\t{sha256}\n"
             .format(**upgrade["boot_dtb"])),
        )
        for args, expected in cases:
            with self.subTest(args=args):
                result = self.verifier(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, expected)

    def test_unknown_or_malformed_build_is_refused(self):
        output = self.work / "fetched rpms"
        target = "fedora@k3.example.org"
        cases = (
            ("verify-f45-bundle.py", ("--build", "12345", "plan"), "not pinned"),
            ("verify-f45-bundle.py", ("--build", "011035571", "plan"),
             "decimal COPR build ID"),
            ("fetch-f45-copr-kernel.sh", ("--build", "12345", output), "not pinned"),
            ("transfer-f45-copr-kernel-to-k3.sh",
             ("--build", "12345", self.bundle, target), "not pinned"),
            ("transfer-f45-copr-kernel-to-k3.sh",
             ("--build", "1/../x", self.bundle, target), "decimal COPR build ID"),
            ("k3-install-rpm-kernel.sh", ("--build", "12345", self.bundle),
             "not pinned"),
            ("k3-install-rpm-kernel.sh", ("--build", "", self.bundle),
             "decimal COPR build ID"),
        )
        for name, args, diagnostic in cases:
            with self.subTest(name=name, build=args[1]):
                result = self.run_helper(name, *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)
        self.assertFalse(self.commands())
        self.assertFalse(output.exists() or Path(str(output) + ".partial").exists())
        self.assertEqual(list(self.remote_home.iterdir()), [])

    def test_upgrade_installer_requires_running_the_first_update(self):
        bundle = self.make_bundle(UPGRADE_BUILD)
        required = self.update(UPGRADE_BUILD)["requires_running"][0]
        for running in (self.lock["image"]["kernel_release"],
                        "6.18.3-200.fc45.riscv64"):
            with self.subTest(running=running):
                result = self.run_helper(
                    "k3-install-rpm-kernel.sh", "--build", UPGRADE_BUILD, bundle,
                    extra_env={"F45_TEST_RUNNING": running},
                )
                self.assert_preflight_refusal(
                    result, "requires running the pinned F45 kernel " + required)
                self.assert_no_rpm_database_query()

    @unittest.skipIf(os.geteuid() == 0, "root continues past the privilege check")
    def test_upgrade_installer_preflight_accepts_running_first_update(self):
        upgrade = self.update(UPGRADE_BUILD)
        result = self.run_helper(
            "k3-install-rpm-kernel.sh", "--build", UPGRADE_BUILD,
            self.make_bundle(UPGRADE_BUILD),
            extra_env={"F45_TEST_RUNNING": upgrade["requires_running"][0]},
        )
        self.assert_preflight_refusal(result, "Run this script with sudo")
        queried = [c["args"][-1] for c in self.commands()
                   if c["command"] == "rpm" and "--quiet" in c["args"]]
        self.assertEqual(queried, [p["name"] + "-" + upgrade["kernel_release"]
                                   for p in upgrade["packages"]])

    def test_default_installer_still_requires_the_image_bootstrap(self):
        result = self.installer(
            F45_TEST_RUNNING=self.update(UPGRADE_BUILD)["kernel_release"])
        self.assert_preflight_refusal(
            result, "pinned F45 bootstrap " + self.lock["image"]["kernel_release"])
        self.assert_no_rpm_database_query()

    def test_transfer_selected_build_uses_its_own_remote_directory(self):
        result = self.run_helper(
            "transfer-f45-copr-kernel-to-k3.sh", "--build", UPGRADE_BUILD,
            self.make_bundle(UPGRADE_BUILD), "fedora@k3.example.org",
        )
        # Success includes the remote re-verification, which fails for these
        # RPMs unless it also selects the upgrade build.
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = self.remote_home / f"f45-copr-kernel-{UPGRADE_BUILD}"
        self.assertEqual(list(self.remote_home.iterdir()), [destination])
        self.assertEqual(
            {p.name for p in (destination / "rpms").iterdir()},
            {p["filename"] for p in self.update(UPGRADE_BUILD)["packages"]},
        )
        self.assertIn(
            f'  sudo "$HOME/{destination.name}/scripts/k3-install-rpm-kernel.sh" \\\n'
            f'    --build {UPGRADE_BUILD} "$HOME/{destination.name}/rpms"\n',
            result.stdout,
        )

    def test_lock_with_altered_upgrade_identity_is_refused(self):
        original = copy.deepcopy(self.lock)
        first_url = original["kernel"]["packages"][0]["url"]
        changes = (
            ("upgrade identity", lambda lock, up: up.update(
                copr_project="@forge-riscv-members/riscv64_omni_kernel")),
            ("package identity", lambda lock, up: up["packages"][0].update(
                url=first_url.rsplit("/", 1)[0] + "/" + up["packages"][0]["filename"])),
            ("Invalid SHA-256", lambda lock, up: up["boot_dtb"].update(
                sha256=up["boot_dtb"]["sha256"].upper())),
            ("boot DTB path", lambda lock, up: up["boot_dtb"].update(
                path="spacemit/k3-com260-bootstrap.dtb")),
            ("upgrade identity", lambda lock, up: up.update(
                requires_running=[lock["image"]["kernel_release"]])),
            ("upgrade identity", lambda lock, up: up.update(
                requires_running=up["requires_running"][0])),
            ("upgrade identity", lambda lock, up: up.update(
                build_id=str(up["build_id"]))),
            ("upgrade identity", lambda lock, up: up.update(
                source_git_commit="0" * 40)),
            ("one pinned upgrade", lambda lock, up: lock.update(upgrades=[])),
            ("one pinned upgrade", lambda lock, up: lock["upgrades"].append(
                copy.deepcopy(up))),
            ("top-level keys", lambda lock, up: (lock.pop("upgrades"), lock.update(
                schema=1, recorded_on="2026-10-19"))),
        )
        bundles = {FIRST_BUILD: self.bundle,
                   UPGRADE_BUILD: self.make_bundle(UPGRADE_BUILD)}
        for index, (diagnostic, change) in enumerate(changes):
            self.lock = copy.deepcopy(original)
            change(self.lock, self.lock["upgrades"][0])
            self.write_lock()
            for build, bundle in bundles.items():
                with self.subTest(index=index, build=build):
                    result = self.run_helper("k3-install-rpm-kernel.sh",
                                             "--build", build, bundle)
                    self.assert_preflight_refusal(result, diagnostic)
        self.assert_no_rpm_database_query()

    @staticmethod
    def raw_image():
        image = bytearray(512)
        struct.pack_into("<QQQIIQ", image, 8, 0x200000, len(image), 0, 2, 0, 0)
        image[0x30:0x38] = b"RISCV\0\0\0"
        image[0x38:0x3C] = b"RSC\x05"
        return bytes(image)

    def zboot(self, image=None, compression="gzip"):
        image = self.raw_image() if image is None else image
        if compression == "gzip":
            payload = gzip.compress(image, mtime=0)
        else:
            result = subprocess.run(
                ["zstd", "--compress", "--stdout", "--quiet"], input=image,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
                env=self.env, cwd=self.other_cwd,
            )
            payload = result.stdout
        header = bytearray(4096)
        header[:8] = b"MZ\0\0zimg"
        struct.pack_into("<II", header, 8, len(header), len(payload))
        header[0x18:0x38] = compression.encode().ljust(32, b"\0")
        struct.pack_into("<II", header, 0x38, 0x818223CD, 0x40)
        header[0x40:0x44] = b"PE\0\0"
        struct.pack_into("<H", header, 0x44, 0x5064)
        struct.pack_into("<H", header, 0x58, 0x020B)
        return bytes(header) + payload + (
            struct.pack("<I", len(image)) if compression == "zstd" else b""
        )

    def test_extracts_gzip_and_zstd_atomically(self):
        for compression in ("gzip", "zstd"):
            with self.subTest(compression=compression):
                source = self.work / (compression + ".zboot")
                source.write_bytes(self.zboot(compression=compression))
                output = self.work / ("Image-" + compression)
                result = self.run_helper("extract-riscv-zboot.sh", source, output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.read_bytes(), self.raw_image())
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o644)
                self.assertFalse(Path(str(output) + ".partial").exists())
                self.assertFalse(Path(str(output) + ".payload.partial").exists())

    def test_malformed_zboot_never_publishes_or_leaves_partials(self):
        malformed = [b"short", self.zboot()[:80]]
        bad_machine = bytearray(self.zboot())
        struct.pack_into("<H", bad_machine, 0x44, 0x8664)
        malformed.append(bytes(bad_machine))
        bad_offset = bytearray(self.zboot())
        struct.pack_into("<I", bad_offset, 8, 4095)
        malformed.append(bytes(bad_offset))
        bad_bounds = bytearray(self.zboot())
        struct.pack_into("<I", bad_bounds, 12, len(bad_bounds) + 1)
        malformed.append(bytes(bad_bounds))
        bad_magic = bytearray(self.raw_image())
        bad_magic[0x30] = 0
        malformed.append(self.zboot(image=bytes(bad_magic)))
        bad_raw_size = bytearray(self.raw_image())
        struct.pack_into("<Q", bad_raw_size, 0x10, len(bad_raw_size) + 1)
        malformed.append(self.zboot(image=bytes(bad_raw_size)))
        bad_trailer = bytearray(self.zboot(compression="zstd"))
        struct.pack_into("<I", bad_trailer, len(bad_trailer) - 4, 65)
        malformed.append(bytes(bad_trailer))
        malformed.append(self.zboot(compression="zstd")[:-4])
        for index, data in enumerate(malformed):
            with self.subTest(index=index):
                source = self.work / ("bad-" + str(index))
                source.write_bytes(data)
                output = self.work / ("output-" + str(index))
                result = self.run_helper("extract-riscv-zboot.sh", source, output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("error:", result.stderr)
                self.assertFalse(output.exists())
                self.assertFalse(Path(str(output) + ".partial").exists())
                self.assertFalse(Path(str(output) + ".payload.partial").exists())

    def test_extractor_preserves_existing_output_and_partial(self):
        source = self.work / "valid.zboot"
        source.write_bytes(self.zboot())
        for suffix in ("", ".partial", ".payload.partial"):
            with self.subTest(suffix=suffix):
                output = self.work / ("protected-" + str(len(suffix)))
                protected = Path(str(output) + suffix)
                protected.write_bytes(b"keep")
                result = self.run_helper("extract-riscv-zboot.sh", source, output)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(protected.read_bytes(), b"keep")

    def test_extractor_rejects_symlink_input(self):
        source = self.work / "valid.zboot"
        source.write_bytes(self.zboot())
        alias = self.work / "source alias"
        alias.symlink_to(source)
        output = self.work / "Image"
        result = self.run_helper("extract-riscv-zboot.sh", alias, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_extractor_does_not_replace_output_created_during_decompression(self):
        source = self.work / "valid.zboot"
        source.write_bytes(self.zboot(compression="zstd"))
        raw = self.work / "raw fixture"
        raw.write_bytes(self.raw_image())
        output = self.work / "Image"
        decoder = self.bin / "zstd"
        decoder.write_text(textwrap.dedent("""\
            #!/usr/bin/env python3
            import os
            from pathlib import Path
            import sys

            Path(os.environ["F45_TEST_COLLISION"]).write_bytes(b"other writer")
            if "--decompress" in sys.argv:
                sys.stdout.buffer.write(Path(os.environ["F45_TEST_RAW"]).read_bytes())
            """))
        decoder.chmod(0o755)
        result = self.run_helper(
            "extract-riscv-zboot.sh", source, output,
            extra_env={"F45_TEST_COLLISION": str(output), "F45_TEST_RAW": str(raw)},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), b"other writer")
        self.assertFalse(Path(str(output) + ".partial").exists())
        self.assertFalse(Path(str(output) + ".payload.partial").exists())

    def test_extractor_is_standalone_after_relocation(self):
        standalone = self.work / "standalone"
        standalone.mkdir()
        script = standalone / "extract-riscv-zboot.sh"
        shutil.copy2(self.support / "scripts" / script.name, script)
        source = self.work / "valid.zboot"
        source.write_bytes(self.zboot())
        output = self.work / "Image"
        result = subprocess.run(
            [str(script), str(source), str(output)], cwd=self.other_cwd,
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_bytes(), self.raw_image())

    def test_extractor_ignores_modules_in_the_callers_directory(self):
        source = self.work / "valid.zboot"
        source.write_bytes(self.zboot())
        output = self.work / "Image"
        marker = self.work / "untrusted import"
        (self.other_cwd / "gzip.py").write_text(
            f"open({str(marker)!r}, 'w').write('loaded')\n"
            "raise SystemExit('untrusted current-directory module')\n"
        )
        result = self.run_helper(
            "extract-riscv-zboot.sh", source, output,
            extra_env={"PYTHONPATH": str(self.other_cwd)},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_bytes(), self.raw_image())
        self.assertFalse(marker.exists())

    # populate-f45-volumes.sh: refusals must precede every device/format command.
    DESTRUCTIVE = {"mkfs.ext4", "mkfs.btrfs", "mount", "losetup", "blkid", "lsblk",
                   "systemctl", "wipefs"}
    DISK = "/dev/disk/by-id/fixture-disk"

    @staticmethod
    def fixture_uuid(digit):
        return "-".join(digit * width for width in (8, 4, 4, 4, 12))

    def populate(self, *args, **overrides):
        env = {
            "K3_NVME_EXPECTED_MODEL": "Fixture Disk",
            "K3_NVME_EXPECTED_SERIAL": "FIXTURE1",
            "K3_NVME_EXPECTED_SIZE_BYTES": "500107862016",
            "K3_F45_EXPECTED_BOOT": self.fixture_uuid("1"),
            "K3_F45_EXPECTED_ROOT": "empty",
            "K3_F45_FWUPD": "mask",
            "K3_F45_ACK_FORMAT": "YES-FORMAT-F45-VOLUMES",
        }
        env.update(overrides)
        base = dict(self.env)
        for key in env:
            base.pop(key, None)
        base.update({key: value for key, value in env.items() if value is not None})
        if not args:
            args = (self.work / "image.raw.xz", self.DISK,
                    self.DISK + "-part4", self.DISK + "-part5")
        command = [str(self.support / "scripts" / "populate-f45-volumes.sh"),
                   *map(str, args)]
        return subprocess.run(
            command, cwd=self.other_cwd, env=base, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, timeout=30,
        )

    def assert_populate_refusal(self, result, diagnostic):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(diagnostic, result.stderr)
        self.assertFalse(self.DESTRUCTIVE.intersection(
            c["command"] for c in self.commands()))

    def test_populate_refuses_non_stable_or_partition_disk_paths(self):
        image = self.work / "image.raw.xz"
        cases = (
            (("/dev/nvme0n1", "/dev/nvme0n1p4", "/dev/nvme0n1p5"), "by-id/ path"),
            ((self.DISK + "-part1", self.DISK + "-part1-part4",
              self.DISK + "-part1-part5"), "whole disk, not a partition"),
            ((self.DISK, "/dev/disk/by-id/other-disk-part4", self.DISK + "-part5"),
             "WHOLE_DISK-partN"),
            ((self.DISK, self.DISK + "-part4x", self.DISK + "-part5"),
             "WHOLE_DISK-partN"),
            ((self.DISK, self.DISK + "-part5", self.DISK + "-part5"), "must differ"),
        )
        for paths, diagnostic in cases:
            with self.subTest(paths=paths):
                self.assert_populate_refusal(self.populate(image, *paths), diagnostic)

    def test_populate_requires_explicit_format_acknowledgment(self):
        for value in (None, "yes", "YES-FORMAT-F45-PARTITIONS"):
            with self.subTest(value=value):
                self.assert_populate_refusal(
                    self.populate(K3_F45_ACK_FORMAT=value), "Formatting requires")

    def test_populate_requires_explicit_fwupd_choice(self):
        self.assert_populate_refusal(self.populate(K3_F45_FWUPD=None), "K3_F45_FWUPD")
        self.assert_populate_refusal(
            self.populate(K3_F45_FWUPD="disable"), "must be mask or keep")

    def test_populate_requires_exact_current_target_content(self):
        for value in (None, "", "UUID=" + self.fixture_uuid("1"),
                      self.fixture_uuid("A"), "any"):
            with self.subTest(value=value):
                result = self.populate(K3_F45_EXPECTED_ROOT=value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("K3_F45_EXPECTED_ROOT" if not value else
                              "empty or a lowercase filesystem UUID", result.stderr)
                self.assertFalse(self.DESTRUCTIVE.intersection(
                    c["command"] for c in self.commands()))

    def test_populate_requires_whole_disk_identity(self):
        for name in ("K3_NVME_EXPECTED_MODEL", "K3_NVME_EXPECTED_SERIAL",
                     "K3_NVME_EXPECTED_SIZE_BYTES"):
            with self.subTest(name=name):
                self.assert_populate_refusal(self.populate(**{name: None}), name)
        self.assert_populate_refusal(
            self.populate(K3_NVME_EXPECTED_SIZE_BYTES="500G"), "decimal byte count")

    @unittest.skipIf(os.geteuid() == 0, "root reaches device resolution instead")
    def test_populate_check_needs_root_but_no_acknowledgment(self):
        image = self.work / "image.raw.xz"
        result = self.populate("--check", image, self.DISK, self.DISK + "-part4",
                               self.DISK + "-part5", K3_F45_ACK_FORMAT=None)
        self.assert_populate_refusal(result, "Run as root")

    # make-bootstrap-dtb.sh, with the real dtc tools on a synthetic DTB.
    FIXTURE_DTS = """/dts-v1/;
/ {
	model = "Fixture board";
	soc {
		pmic {
			regulators {
				dldo4 {
					regulator-name = "dldo4";
					regulator-boot-on;
				};%s
			};
		};
	};%s
};
"""
    HUB = """
	hub-reset {
		compatible = "regulator-fixed";
		regulator-name = "hub-reset";%s
	};"""

    def fixture_dtb(self, name, *, hub=True, duplicate=False, hub_property=""):
        if shutil.which("dtc") is None:
            self.skipTest("dtc is not installed")
        extra = "\n\t\t\t\tother {\n\t\t\t\t\tdldo4 {\n\t\t\t\t\t};\n\t\t\t\t};" \
            if duplicate else ""
        text = self.FIXTURE_DTS % (extra, self.HUB % hub_property if hub else "")
        source = self.work / (name + ".dts")
        source.write_text(text)
        output = self.work / (name + ".dtb")
        subprocess.run(["dtc", "-q", "-I", "dts", "-O", "dtb", "-o", str(output),
                        str(source)], check=True, env=self.env)
        return output

    def make_dtb(self, packaged, output):
        for tool in ("fdtget", "fdtput"):
            if shutil.which(tool) is None:
                self.skipTest(tool + " is not installed")
        return self.run_helper("make-bootstrap-dtb.sh", packaged, output)

    def decompile(self, dtb):
        return subprocess.run(["dtc", "-q", "-I", "dtb", "-O", "dts", str(dtb)],
                              check=True, stdout=subprocess.PIPE, text=True,
                              env=self.env).stdout.splitlines()

    def test_bootstrap_dtb_adds_exactly_two_empty_properties(self):
        packaged = self.fixture_dtb("packaged")
        original = packaged.read_bytes()
        output = self.work / "bootstrap.dtb"
        result = self.make_dtb(packaged, output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(packaged.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o644)
        self.assertFalse(Path(str(output) + ".partial").exists())
        before, after = self.decompile(packaged), self.decompile(output)
        added = [line.strip() for line in after if line not in before]
        self.assertEqual(added, ["regulator-always-on;"] * 2)
        self.assertTrue(set(before) <= set(after))
        for node in ("/soc/pmic/regulators/dldo4", "/hub-reset"):
            properties = subprocess.run(
                ["fdtget", "-p", str(output), node], check=True,
                stdout=subprocess.PIPE, text=True, env=self.env).stdout.split()
            self.assertIn("regulator-always-on", properties)

    def test_bootstrap_dtb_refuses_unexpected_inputs(self):
        cases = (
            (self.fixture_dtb("nohub", hub=False), "/hub-reset node is missing"),
            (self.fixture_dtb("twice", duplicate=True), "exactly one node named dldo4"),
            (self.fixture_dtb("already", hub_property="\n\t\tregulator-always-on;"),
             "already has regulator-always-on"),
        )
        for packaged, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic):
                output = self.work / (packaged.stem + "-out.dtb")
                result = self.make_dtb(packaged, output)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)
                self.assertFalse(output.exists())
                self.assertFalse(Path(str(output) + ".partial").exists())

    def test_bootstrap_dtb_never_replaces_output_or_follows_input_symlink(self):
        packaged = self.fixture_dtb("packaged")
        output = self.work / "existing.dtb"
        output.write_bytes(b"keep")
        result = self.make_dtb(packaged, output)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), b"keep")
        alias = self.work / "packaged-alias.dtb"
        alias.symlink_to(packaged)
        fresh = self.work / "fresh.dtb"
        result = self.make_dtb(alias, fresh)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(fresh.exists())


if __name__ == "__main__":
    unittest.main()
