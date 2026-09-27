# SPDX-License-Identifier: GPL-2.0-only
"""Human-selected receipts and normal fast-forward publication of exact bytes."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import difflib
import fcntl
import importlib.metadata
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import uuid

import checks
import content as c
import httpcheck
import storage as s

TOOL_PATHS = (
    ".githooks/pre-push", "tools/wiki/README.md", "tools/wiki/checks.py",
    "tools/wiki/content.py", "tools/wiki/httpcheck.py", "tools/wiki/manage.py",
    "tools/wiki/publication.py", "tools/wiki/requirements.txt", "tools/wiki/storage.py",
    "tools/wiki/tests/test_wiki.py",
)
BUNDLE_MODES = {
    **{path: 0o555 if path == ".githooks/pre-push" else 0o444 for path in TOOL_PATHS},
    "hooks/pre-push": 0o555, "interpreter": 0o444, "bundle.json": 0o444,
}
PROVENANCE = "K3-Wiki-Provenance: "
ZERO = "0" * 40
GITHUB_TOKEN_ENV = {
    "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN",
}


def utc_day():
    return datetime.now(timezone.utc).date()


def tool_identity(snapshot: c.Snapshot) -> dict:
    expected = {p for p in TOOL_PATHS if p.startswith("tools/wiki/")} | {c.MANIFEST, c.EXCEPTIONS}
    c.require(snapshot.inventory("tools/wiki") == expected, "tool inventory differs from the supported, reviewed tool set")
    result = {}
    for path in TOOL_PATHS:
        data = snapshot.read(path)
        checks.require_private_safe(data, path)
        mode = "100755" if path == ".githooks/pre-push" else "100644"
        if snapshot.worktree:
            actual = "100755" if (snapshot.root / path).lstat().st_mode & 0o111 else "100644"
        else:
            actual = snapshot.entries[path][0]
        c.require(actual == mode, "validator tool mode changed or is not installed as documented")
        result[path] = {"blob": c.blob_id(data), "sha256": c.sha256(data), "mode": mode}
    return result


def runtime_identity() -> dict:
    c.parser()
    packages = {}
    for name, version in c.PARSER_VERSIONS.items():
        distribution = importlib.metadata.distribution(name)
        files = {}
        for entry in distribution.files or ():
            path = str(entry)
            if not path.endswith(".py") or ".." in Path(path).parts:
                continue
            actual = Path(distribution.locate_file(entry))
            c.require(actual.is_file() and not actual.is_symlink(), "parser has a missing or linked module")
            data = actual.read_bytes()
            digest = base64.urlsafe_b64encode(__import__("hashlib").sha256(data).digest()).decode().rstrip("=")
            c.require(entry.hash and entry.hash.mode == "sha256" and entry.hash.value == digest,
                      "installed parser bytes differ from wheel RECORD; reinstall the hash-locked environment")
            files[path] = c.sha256(data)
        c.require(files, "installed parser has no verifiable Python files")
        packages[name] = {"version": version, "files_sha256": c.sha256(c.canonical(files))}
    return {
        "python": list(sys.version_info[:3]),
        "implementation": sys.implementation.name,
        "packages": packages,
        "executables": c.system_executable_identities(),
    }


def identities(snapshot: c.Snapshot) -> dict:
    tools = tool_identity(snapshot)
    m = c.manifest(snapshot)
    return {
        "manifest_blob": c.blob_id(snapshot.read(c.MANIFEST)),
        "tool_files": tools,
        "tool_sha256": c.sha256(c.canonical(tools)),
        "lock_blob": c.blob_id(snapshot.read(c.LOCK)),
        "link_exceptions_blob": c.blob_id(snapshot.read(c.EXCEPTIONS)),
        "validation_exceptions_sha256": c.sha256(c.canonical(m["validation_exceptions"])),
    }


def bind_running_tool(snapshot: c.Snapshot) -> dict:
    identity = identities(snapshot)
    running_root = Path(__file__).absolute().parents[2]
    for path in TOOL_PATHS:
        c.require(c.sha256(c.regular_read(running_root, path)) == identity["tool_files"][path]["sha256"],
                  "running validator differs from the selected source; explicitly review/install the matching tool version")
    return identity


def online_approval(results: list[dict]) -> list[dict]:
    """Bind outcomes and used reviews, not request methods, timings, or DNS choices."""
    c.require(isinstance(results, list), "invalid online approval results")
    statuses = {
        "available-head": "available", "available-get": "available", "available": "available",
        "example-not-requested": "example-not-requested", "checksum-matches": "checksum-matches",
        "reviewed-resource-exception": "reviewed-resource-exception",
    }
    approved = {}
    for result in results:
        c.require(isinstance(result, dict) and {"page", "url", "role", "status"} <= result.keys(),
                  "incomplete online approval result")
        page, url, role = result["page"], result["url"], result["role"]
        c.require("/" not in c.safe_path(page), "invalid online approval page")
        checks.url_shape(url)
        c.require(role in ("source", "resource", "artifact", "critical-artifact", "critical-checksum")
                  and isinstance(result["status"], str) and result["status"] in statuses,
                  "unsupported online approval verdict")
        row = {"page": page, "url": url, "role": role, "status": statuses[result["status"]]}
        if role.startswith("critical-"):
            expected = result.get("expected_sha256")
            filename = result.get("filename")
            c.require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected)
                      and isinstance(filename, str) and "/" not in c.safe_path(filename),
                      "critical online result lacks its bound image identity")
            c.require(row["status"] == ("checksum-matches" if role == "critical-checksum" else "available"),
                      "critical artifacts and checksums cannot use exceptions or example verdicts")
            row.update(expected_sha256=expected, filename=filename)
        if row["status"] == "reviewed-resource-exception":
            c.require(role == "resource" and isinstance(result.get("exception"), dict),
                      "online availability exception is not resource-scoped")
            exception = result["exception"]
            c.object_keys(exception, {"kind", "page", "url", "reason", "reviewer", "reviewed", "expires"})
            c.require(exception["kind"] == "resource" and exception["page"] == page and exception["url"] == url,
                      "online result exception does not match its exact resource")
            row["exception"] = exception
        else:
            c.require("exception" not in result, "available online result unexpectedly uses an exception")
        key = (page, url, role)
        c.require(key not in approved, "duplicate online approval result")
        approved[key] = row
    return [approved[key] for key in sorted(approved)]


def check_links(root: Path, ref: str, *, checker: httpcheck.Checker | None = None) -> dict:
    c.require(isinstance(ref, str) and c.OID_RE.fullmatch(ref),
              "check-links --ref requires a full reviewed commit OID, not a branch or abbreviated ref")
    source = c.Snapshot(root, ref)
    c.require(source.commit == ref, "check-links --ref must identify a commit, not a tag object")
    bound, runtime = bind_running_tool(source), runtime_identity()
    checked = checks.validate(source, today=utc_day())
    results = online_approval((checker or httpcheck.Checker()).all(checked.links, checked.exceptions))
    c.require(bind_running_tool(source) == bound and runtime_identity() == runtime,
              "running tool or interpreter/parser changed during the report-only check")
    report = {"schema": 1, "mode": "report-only", "source": {"commit": source.commit, "tree": source.tree},
              "identities": bound, "runtime": runtime, "links": results,
              "public_reachability_checked": False, "publication_authorized": False}
    checks.require_private_safe(c.canonical(report), "link-check-report")
    return report


def clean(git: c.Git) -> None:
    c.require(not git.run("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none"),
              "publication input/clone is dirty or has untracked files; preserve and reconcile it before preparing")


def real_history(git: c.Git) -> None:
    grafts = Path(git.run("rev-parse", "--git-path", "info/grafts").decode().strip())
    if not grafts.is_absolute():
        grafts = git.root / grafts
    c.require(not grafts.exists() and not grafts.is_symlink(), "Git grafts are unsupported; ancestry must be the real public history")
    c.require(git.run("rev-parse", "--is-shallow-repository").strip() == b"false",
              "shallow history cannot establish the required public reachability")


def ordinary_wiki(root: Path) -> None:
    with s.directory(root / s.PUBLISH / ".git"):
        pass
    gitdir = root / s.PUBLISH / ".git"
    c.require(not (gitdir / "commondir").exists() and not (gitdir / "objects/info/alternates").exists(),
              "publication requires an ordinary independent clone, not shared Git storage")
    for base, dirs, files in os.walk(gitdir, followlinks=False):
        c.require(not any((Path(base) / name).is_symlink() for name in dirs + files),
                  "publication Git metadata contains a symlink; preserve it and use a verified ordinary clone")
    git = c.Git(root / s.PUBLISH)
    c.require(not git.run("config", "--local", "--get", "core.worktree", ok=(0, 1)).strip()
              and git.run("rev-parse", "--show-toplevel").decode().strip() == str(git.root),
              "publication Git worktree is redirected outside the named clone")


def branch(value: str) -> str:
    c.require(isinstance(value, str) and re.fullmatch(r"refs/heads/[A-Za-z0-9][A-Za-z0-9._/-]*", value)
              and ".." not in value and "//" not in value and "@{" not in value
              and not value.endswith(("/", ".", ".lock")) and "/." not in value,
              "unsupported remote branch name")
    return value


class PublicRemotes:
    """The production endpoints are constants. Local transport exists only in fixture subclasses."""

    @staticmethod
    def github_credential_helper() -> str:
        try:
            executable = c.system_executable_path("gh")
        except c.Invalid:
            raise c.Invalid(
                "trusted system GitHub CLI credential helper is required at /usr/bin/gh; "
                "install it and authenticate with `/usr/bin/gh auth login --hostname github.com`"
            ) from None
        return "!" + shlex.quote(executable) + " auth git-credential"

    def network_git(self, git: c.Git, *args: str, hooks: bool = False,
                    wiki_credentials: bool = False) -> bytes:
        # Refuse repository-config URL rewrites, proxies and executable transport helpers.
        config = git.run("config", "--local", "--list", "--name-only").decode().splitlines()
        forbidden = ("url.", "http.", "https.", "credential.", "include.", "includeif.")
        c.require(not any(key.lower().startswith(forbidden) or key.lower() in
                          ("core.sshcommand", "core.gitproxy") for key in config),
                  "repository Git transport overrides are unsupported; use the exact public HTTPS origins")
        if hooks or wiki_credentials:
            c.require(hooks and wiki_credentials and len(args) == 5
                      and args[:4] == ("push", "--porcelain", "--", c.WIKI_REPO),
                      "GitHub credentials and hooks are restricted to the exact approved wiki push")
            oid, separator, ref = args[4].partition(":")
            c.require(separator == ":" and c.OID_RE.fullmatch(oid) and branch(ref) == ref,
                      "GitHub credentials require one exact reviewed wiki branch update")
        env = c.git_env(credentials=wiki_credentials)
        options = ["-c", "protocol.allow=never", "-c", "protocol.https.allow=always",
                   "-c", "http.sslVerify=true", "-c", "credential.helper=",
                   "-c", "http.followRedirects=false", "-c", "http.lowSpeedLimit=1",
                   "-c", "http.lowSpeedTime=20", "-c", "core.fsmonitor=false"]
        if wiki_credentials:
            options += [
                "-c",
                "credential.https://github.com.helper=" + self.github_credential_helper(),
            ]
        if not hooks:
            options += ["-c", "core.hooksPath=/dev/null"]
        try:
            result = subprocess.run([c.system_executable_path("git"), "--no-pager",
                                     "--no-replace-objects", "-C", str(git.root),
                                     *options, *args], env=env, capture_output=True, timeout=90, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise c.Invalid("public Git operation unavailable or timed out; no fallback remote is permitted") from None
        c.require(result.returncode == 0, f"public Git {args[0]} failed; remote details suppressed")
        return result.stdout

    def origin(self, git: c.Git, expected: str) -> None:
        urls = git.run("config", "--get-all", "remote.origin.url", ok=(0, 1)).decode().splitlines()
        pushes = git.run("config", "--get-all", "remote.origin.pushurl", ok=(0, 1)).decode().splitlines()
        c.require(urls == [expected] and (not pushes or pushes == [expected]),
                  "origin/pushurl must be the single exact approved public HTTPS repository")

    def advertised(self, git: c.Git, url: str) -> tuple[str | None, dict[str, str]]:
        c.require(url in (c.SOURCE_URL, c.WIKI_REPO), "remote URL is outside the immutable publication allowlist")
        raw = self.network_git(git, "ls-remote", "--symref", "--", url)
        default = None
        head = None
        refs = {}
        for line in raw.decode("ascii").splitlines():
            fields = line.split("\t")
            c.require(len(fields) == 2, "malformed public ref advertisement")
            value, ref = fields
            if value.startswith("ref: "):
                c.require(ref == "HEAD" and default is None, "ambiguous remote default branch")
                default = branch(value[5:])
            elif ref == "HEAD":
                c.require(c.OID_RE.fullmatch(value) and head is None, "invalid remote HEAD advertisement")
                head = value
            elif ref.startswith(("refs/heads/", "refs/tags/")) and not ref.endswith("^{}"):
                branch("refs/heads/" + ref.split("/", 2)[2])
                c.require(c.OID_RE.fullmatch(value) and ref not in refs, "invalid or duplicate public ref")
                refs[ref] = value
        c.require(any(ref.startswith("refs/heads/") for ref in refs),
                  "remote has no branch; the human must create the initial wiki Home in the browser")
        if default is not None:
            c.require(default in refs and head == refs[default], "remote default branch is absent or disagrees with HEAD")
        return default, refs

    def fetch(self, git: c.Git, url: str, refs: dict[str, str]) -> None:
        c.require(url in (c.SOURCE_URL, c.WIKI_REPO), "unapproved fetch remote")
        self.network_git(git, "fetch", "--no-tags", "--no-recurse-submodules", "--no-write-fetch-head",
                         "--", url, *sorted(refs))
        for ref, oid in refs.items():
            commit = git.run("rev-parse", oid + "^{}").decode().strip()
            c.require(git.run("cat-file", "-t", commit).strip() == b"commit",
                      "remote advertisement contains a non-commit tag/object; its history cannot be bounded here")
            c.require(not ref.startswith("refs/heads/") or commit == oid,
                      "advertised branch is not a commit after fetch")

    def push(self, git: c.Git, oid: str, ref: str) -> None:
        c.require(c.OID_RE.fullmatch(oid), "invalid candidate commit")
        self.origin(git, c.WIKI_REPO)
        self.network_git(git, "push", "--porcelain", "--", c.WIKI_REPO, oid + ":" + branch(ref),
                         hooks=True, wiki_credentials=True)

    def source(self, git: c.Git, source: str) -> str:
        real_history(git)
        self.origin(git, c.SOURCE_URL)
        _, advertised = self.advertised(git, c.SOURCE_URL)
        c.require(c.SOURCE_BRANCH in advertised, "approved public source branch is absent")
        wanted = {c.SOURCE_BRANCH: advertised[c.SOURCE_BRANCH]}
        self.fetch(git, c.SOURCE_URL, wanted)
        _, after = self.advertised(git, c.SOURCE_URL)
        c.require(after.get(c.SOURCE_BRANCH) == wanted[c.SOURCE_BRANCH],
                  "source branch moved during fetch; retry preparation rather than guessing")
        c.require(git.ancestor(source, wanted[c.SOURCE_BRANCH]),
                  "selected source is not reachable from the freshly fetched public main branch")
        return wanted[c.SOURCE_BRANCH]

    def wiki(self, git: c.Git) -> tuple[str, str]:
        real_history(git)
        self.origin(git, c.WIKI_REPO)
        default, refs = self.advertised(git, c.WIKI_REPO)
        c.require(default is not None, "wiki default branch was not advertised; do not assume main/master")
        wanted = {default: refs[default]}
        self.fetch(git, c.WIKI_REPO, wanted)
        next_default, after = self.advertised(git, c.WIKI_REPO)
        c.require(next_default == default and after.get(default) == wanted[default],
                  "wiki moved during fetch; retry after reviewing the remote change")
        return default, wanted[default]


def wiki_tree(git: c.Git, oid: str) -> dict[str, bytes]:
    entries = git.entries(oid)
    output = {}
    for path, (mode, kind, blob) in entries.items():
        c.require("/" not in path and (c.SLUG_RE.fullmatch(path) or path in ("_Sidebar.md", "_Footer.md"))
                  and kind == "blob" and mode == "100644", "unexpected wiki path, mode, or object")
        output[path] = git.blob(blob)
    c.require(len({p.casefold() for p in output}) == len(output), "case-colliding wiki pages")
    return output


def provenance_message(receipt: dict) -> bytes:
    provenance = {
        "schema": 1,
        "source": receipt["source"]["commit"],
        "source_tree": receipt["source"]["tree"],
        "identities": receipt["identities"],
        "output": receipt["output"],
        "wiki_branch": receipt["wiki"]["branch"],
        "parent": receipt["wiki"]["expected_oid"],
    }
    return (
        f"Publish curated wiki from {provenance['source']}\n\n"
        + PROVENANCE + c.canonical(provenance).decode().strip()
        + "\n\nAssisted-by: LLM\n"
        + "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>\n"
    ).encode()


def read_provenance(git: c.Git, oid: str) -> dict:
    message = git.run("show", "-s", "--format=%B", oid).decode("utf-8")
    values = [line[len(PROVENANCE):] for line in message.splitlines() if line.startswith(PROVENANCE)]
    c.require(len(values) == 1, "wiki tip is not a recognized publisher commit; reconcile web edits first")
    value = c.load_json(values[0].encode(), "public provenance")
    c.object_keys(value, {"schema", "source", "source_tree", "identities", "output", "wiki_branch", "parent"})
    c.require(value["schema"] == 1 and c.OID_RE.fullmatch(value["source"]), "unsupported public provenance")
    parents = git.run("rev-list", "--parents", "-n", "1", oid).decode().split()
    c.require(parents == [oid, value["parent"]], "unexpected wiki merge or parent; reconcile history")
    return value


def remote_state(source: c.Snapshot, wiki: c.Git, wiki_ref: str, tip: str,
                 source_tip: str, adoption: str | None) -> dict:
    output = wiki_tree(wiki, tip)
    if adoption is not None:
        c.require(adoption == tip, "bootstrap adoption OID differs from the freshly advertised wiki tip")
        c.require(wiki.run("rev-list", "--parents", "-n", "1", tip).decode().split() == [tip],
                  "bootstrap adoption is one-time and requires the initial root Home commit")
        expected = {"Home.md": c.manifest(source)["bootstrap_home"].encode()}
        c.require(output == expected, "bootstrap must contain exactly the documented regular Home.md bytes")
        return {"kind": "bootstrap", "home_blob": c.blob_id(expected["Home.md"])}
    prior = read_provenance(wiki, tip)
    c.require(prior["wiki_branch"] == wiki_ref, "wiki provenance branch changed")
    previous = c.Snapshot(source.root, prior["source"])
    c.require(source.git.ancestor(previous.commit, source_tip), "previous wiki source is no longer public on main")
    c.require(previous.tree == prior["source_tree"] and identities(previous) == prior["identities"],
              "previous wiki source/tool identity does not match public provenance")
    # Reconstruct without executing the previous commit's scripts or applying expired old exceptions.
    expected = c.render(previous)[1]
    c.require(s.tree_record(expected) == prior["output"] and output == expected,
              "wiki has unrecognized edits or extra files; reconcile into canonical source first")
    return {"kind": "managed", "previous_source": previous.commit, "previous_tree": prior["output"]["git_tree"]}


def bundle_directories() -> list[str]:
    directories = {parent.as_posix() for path in BUNDLE_MODES
                   for parent in Path(path).parents if parent != Path(".")}
    return sorted(directories | {""}, key=lambda path: (path.count("/"), path))


def bundle_inventory(bundle: Path, *, sealed: bool) -> None:
    directories = set(bundle_directories())
    for relative in sorted(directories):
        prefix = relative + "/" if relative else ""
        expected = {path[len(prefix):].split("/", 1)[0] for path in BUNDLE_MODES if path.startswith(prefix)}
        with s.directory(bundle, relative) as fd:
            c.require(stat.S_IMODE(os.fstat(fd).st_mode) == (0o555 if sealed else 0o700),
                      "trusted bundle directory mode changed")
            c.require(set(os.listdir(fd)) == expected,
                      "trusted bundle inventory changed; extra files, directories and bytecode caches are forbidden")
            for name in expected:
                path = prefix + name
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if path in directories:
                    c.require(stat.S_ISDIR(info.st_mode), "trusted bundle contains a symlinked or invalid directory")
                else:
                    c.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                              and stat.S_IMODE(info.st_mode) == BUNDLE_MODES[path],
                              "trusted bundle file mode changed, file is linked, or required hook is not executable")


def read_bundle(bundle: Path, *, sealed: bool = True, check_runtime: bool = True) -> dict:
    bundle_inventory(bundle, sealed=sealed)
    data = c.regular_read(bundle, "bundle.json")
    metadata = c.load_json(data, "trusted validator bundle")
    c.object_keys(metadata, {"schema", "source", "identities", "runtime", "interpreter"})
    c.require(metadata["schema"] == 1 and c.OID_RE.fullmatch(metadata["source"]), "invalid validator bundle")
    c.require(data == c.canonical(metadata), "trusted bundle metadata is not canonical JSON")
    if sealed:
        c.require(bundle.name == c.sha256(data), "trusted bundle directory does not match its metadata digest")
    c.require(set(metadata["identities"]["tool_files"]) == set(TOOL_PATHS), "trusted bundle tool identity set changed")
    for path in TOOL_PATHS:
        payload = c.regular_read(bundle, path)
        expected = {"blob": c.blob_id(payload), "sha256": c.sha256(payload),
                    "mode": "100755" if path == ".githooks/pre-push" else "100644"}
        c.require(expected == metadata["identities"]["tool_files"][path],
                  "trusted validator bundle was modified; explicitly reinstall the reviewed version")
    c.require(c.regular_read(bundle, "hooks/pre-push") == c.regular_read(bundle, ".githooks/pre-push")
              and (bundle / "hooks/pre-push").lstat().st_mode & stat.S_IXUSR,
              "trusted hook dispatcher changed or is not executable")
    c.require(c.regular_read(bundle, "interpreter").decode().strip() == metadata["interpreter"],
              "trusted interpreter binding changed")
    if check_runtime:
        c.require(runtime_identity() == metadata["runtime"],
                  "pinned interpreter/parser/system executables changed; reinstall the reviewed hook")
    return metadata


def seal_bundle(bundle: Path) -> None:
    bundle_inventory(bundle, sealed=False)
    for path in BUNDLE_MODES:
        relative = Path(path)
        with s.directory(bundle, "" if relative.parent == Path(".") else relative.parent.as_posix()) as parent:
            fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    for path in reversed(bundle_directories()):
        with s.directory(bundle, path) as fd:
            os.fchmod(fd, 0o555)
            os.fsync(fd)


def installed_bundle(source: c.Git) -> Path:
    configured = source.run("config", "--local", "--get", "wiki.trustBundle", ok=(0, 1)).decode().strip()
    c.require(bool(configured), "install the reviewed canonical hook before preparing a publication")
    bundle = Path(configured)
    c.require(bundle.is_absolute(), "trusted validator bundle path must be absolute")
    read_bundle(bundle)
    hooks = source.run("config", "--local", "--get", "core.hooksPath", ok=(0, 1)).decode().strip()
    c.require(hooks == str(bundle / "hooks"), "canonical hook is not installed at its bound path")
    return bundle


def external_git_config_paths() -> tuple[Path, ...]:
    home_value = os.environ.get("HOME")
    try:
        home = Path(home_value) if home_value else Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, RuntimeError):
        raise c.Invalid("cannot determine the operator Git configuration boundary") from None
    c.require(home.is_absolute() and ".." not in home.parts,
              "operator home for Git configuration inspection is unsafe")
    xdg_value = os.environ.get("XDG_CONFIG_HOME")
    xdg = Path(xdg_value) if xdg_value else home / ".config"
    c.require(xdg.is_absolute() and ".." not in xdg.parts,
              "operator XDG Git configuration path is unsafe")
    return (Path("/etc/gitconfig"), home / ".gitconfig", xdg / "git/config")


def config_may_define_hooks(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_size > c.MAX_INPUT):
        return True
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            data = os.read(fd, c.MAX_INPUT + 1)
            current = os.fstat(fd)
        finally:
            os.close(fd)
    except OSError:
        return True
    if (len(data) > c.MAX_INPUT or current.st_size != len(data)
            or (current.st_dev, current.st_ino, current.st_mode, current.st_uid, current.st_gid,
                current.st_size, current.st_mtime_ns, current.st_ctime_ns)
            != (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns)):
        return True
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeError:
        return True
    active = "\n".join(line for line in lines if not line.lstrip().startswith(("#", ";")))
    return bool(re.search(r"(?im)\bhookspath\b|^\s*\[\s*include(?:if)?\b", active))


def effective_hooks(git: c.Git) -> str:
    # Operational Git ignores external configuration. Detect possible external hooks as inert text.
    try:
        result = subprocess.run(
            [c.system_executable_path("git"), "--no-pager", "--no-replace-objects",
             "-C", str(git.root), "config", "--local", "--get", "core.hooksPath"],
            env=c.git_env(), capture_output=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise c.Invalid("cannot inspect the existing local hook configuration") from None
    c.require(result.returncode in (0, 1), "cannot inspect the existing local hook configuration")
    local = result.stdout.decode().strip()
    c.require("\n" not in local, "ambiguous local hook configuration")
    if local:
        return local
    if any(config_may_define_hooks(path) for path in external_git_config_paths()):
        return "<global or system Git configuration requires explicit hook integration>"
    return ""


def ensure_hooks_available(git: c.Git, desired: Path) -> None:
    configured = effective_hooks(git)
    previous = git.run("config", "--local", "--get", "wiki.trustBundle", ok=(0, 1)).decode().strip()
    if configured and previous and configured == str(Path(previous) / "hooks"):
        read_bundle(Path(previous), check_runtime=False)
        current = Path(configured)
    elif configured:
        raise c.Invalid("existing core.hooksPath must be explicitly integrated by the human; nothing was replaced")
    else:
        current = Path(git.run("rev-parse", "--absolute-git-dir").decode().strip()) / "hooks"
    if current.exists():
        c.require(current.is_dir() and not current.is_symlink(), "existing hook directory is unsafe")
        for entry in current.iterdir():
            if entry.name.endswith(".sample"):
                continue
            if configured and previous and entry.name == "pre-push":
                c.require(c.regular_read(current, "pre-push") ==
                          c.regular_read(Path(previous), ".githooks/pre-push"), "existing hook was modified")
                continue
            raise c.Invalid("existing hooks must be explicitly integrated; no hook was overwritten or disabled")


def configure_wiki_hook(git: c.Git, source: c.Git) -> Path:
    bundle = installed_bundle(source)
    ensure_hooks_available(git, bundle)
    git.run("config", "--local", "wiki.trustBundle", str(bundle))
    git.run("config", "--local", "wiki.sourceRoot", str(source.root))
    git.run("config", "--local", "core.hooksPath", str(bundle / "hooks"))
    return bundle


def ensure_wiki(root: Path, remote: PublicRemotes) -> c.Git:
    source = c.Git(root)
    installed_bundle(source)
    with s.directory(root, s.PUBLISH, create=True):
        pass
    wiki = c.Git(root / s.PUBLISH)
    if not (wiki.root / ".git").exists():
        c.require(not os.listdir(wiki.root), "publication directory is not an empty managed clone")
        wiki.run("init", "-q")
        wiki.run("config", "--local", "remote.origin.url", c.WIKI_REPO)
    c.require((wiki.root / ".git").is_dir() and not (wiki.root / ".git").is_symlink(),
              "publication .git must be a real directory")
    ordinary_wiki(root)
    remote.origin(wiki, c.WIKI_REPO)
    configure_wiki_hook(wiki, source)
    return wiki


def checkout_initial(wiki: c.Git, ref: str, oid: str, output: dict[str, bytes]) -> None:
    existing = wiki.run("rev-parse", "--verify", "HEAD", ok=(0, 128)).decode().strip()
    if existing:
        clean(wiki)
        c.require(existing == oid and wiki.run("symbolic-ref", "-q", "HEAD").decode().strip() == ref,
                  "publication clone is not at the verified remote tip; preserve/reconcile it")
        check_clone_files(wiki, output)
        return
    c.require(set(os.listdir(wiki.root)) == {".git"}, "uninitialized publication clone has unexpected files")
    wiki.run("symbolic-ref", "HEAD", ref)
    for name, data in output.items():
        s.write(wiki.root, name, data)
    wiki.run("read-tree", oid)
    wiki.run("update-ref", ref, oid, ZERO)
    clean(wiki)


def check_clone_files(wiki: c.Git, expected: dict[str, bytes]) -> None:
    c.require(set(os.listdir(wiki.root)) == set(expected) | {".git"},
              "publication clone has missing or extra files, including ignored files")
    for name, data in expected.items():
        c.require(c.regular_read(wiki.root, name) == data
                  and not (wiki.root / name).lstat().st_mode & 0o111,
                  "publication worktree bytes/modes differ from the verified Git tree")


def report_bytes(receipt: dict, online: list[dict], old: dict[str, bytes], new: dict[str, bytes]) -> bytes:
    lines = [
        "# Prepared wiki publication\n\n",
        "This is a review artifact, not permission to publish. Human semantic, privacy, licensing, "
        "authorship and destination-policy review is still required. No hardware was exercised.\n\n",
        f"- Public source: `{receipt['source']['commit']}`\n",
        f"- Public branch observed: `{receipt['source']['advertised_tip']}`\n",
        f"- Expected wiki head: `{receipt['wiki']['expected_oid']}`\n",
        f"- Wiki branch: `{receipt['wiki']['branch']}`\n",
        f"- Rendered tree: `{receipt['output']['git_tree']}`\n",
        f"- Adoption: `{receipt['wiki']['state']['kind']}`\n\n",
        "## Exact output\n\n",
    ]
    lines.extend(f"- `{name}`: SHA256 `{entry['sha256']}`, {entry['size']} bytes\n"
                 for name, entry in receipt["output"]["files"].items())
    lines.append("\n## Bounded public link checks\n\n")
    for entry in online:
        lines.append(f"- `{entry['page']}`: {entry['url']} -- {entry['status']}\n")
        if "expected_sha256" in entry:
            lines.append(f"  Required image `{entry['filename']}`; expected SHA256 `{entry['expected_sha256']}`. "
                         "Image bytes are not downloaded by this gate.\n")
        if "exception" in entry:
            ex = entry["exception"]
            lines.append(f"  Human review: {ex['reviewer']}; {ex['reviewed']}; expires {ex['expires']}. "
                         f"Reason: {ex['reason']}\n")
    lines.append("\nAvailability is not source correctness. Local Markdown checks are not proof of GitHub "
                 "Wiki rendering parity. Review every output file and the managed diff before choosing the receipt hash.\n")
    result = "".join(lines).encode()
    checks.require_private_safe(result, "publication-report")
    diff = []
    for name in sorted(set(old) | set(new)):
        diff.extend(difflib.unified_diff(c.text(old.get(name, b"")).splitlines(keepends=True),
                                        c.text(new.get(name, b"")).splitlines(keepends=True),
                                        fromfile="previous/" + name, tofile="prepared/" + name))
    # Diff bytes are derived only from the validated public source and verified public wiki.
    return result + b"\n## Managed diff\n\n~~~~diff\n" + "".join(diff).encode() + b"~~~~\n"


def publisher_identity(source: c.Snapshot) -> dict:
    author = {}
    for key in ("name", "email"):
        author[key] = source.git.run("config", "--local", "--get", "user." + key, ok=(0, 1)).decode().strip()
        c.require(author[key] and len(author[key]) <= 200 and not re.search(r"[\x00-\x1f<>]", author[key]),
                  "set a reviewed repository-local user.name and user.email before preparing the wiki commit")
    c.require(re.fullmatch(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", author["email"]),
              "publisher email must be a public reviewable address")
    author["timestamp"] = int(source.git.run("show", "-s", "--format=%ct", source.commit))
    checks.require_private_safe(c.canonical(author), "publisher-identity")
    return author


def prepare(root: Path, source_ref: str, adoption: str | None = None, *,
            remote: PublicRemotes | None = None, checker: httpcheck.Checker | None = None) -> tuple[Path, str]:
    remote, checker = remote or PublicRemotes(), checker or httpcheck.Checker()
    source = c.Snapshot(root, source_ref)
    c.require(source_ref == source.commit, "prepare --source requires the full reviewed commit OID")
    if adoption is not None:
        c.require(c.OID_RE.fullmatch(adoption), "bootstrap adoption requires a full reviewed commit OID")
    clean(source.git)
    bound = bind_running_tool(source)
    c.require(read_bundle(installed_bundle(source.git))["identities"]["tool_files"] == bound["tool_files"],
              "installed hook does not trust this tool version; explicitly install the reviewed source first")
    source_tip = remote.source(source.git, source.commit)
    checked = checks.validate(source, today=utc_day())
    online = checker.all(checked.links, checked.exceptions)
    wiki = ensure_wiki(root, remote)
    wiki_ref, tip = remote.wiki(wiki)
    state = remote_state(source, wiki, wiki_ref, tip, source_tip, adoption)
    checkout_initial(wiki, wiki_ref, tip, wiki_tree(wiki, tip))
    receipt = {
        "schema": 1,
        "source": {"url": c.SOURCE_URL, "branch": c.SOURCE_BRANCH, "commit": source.commit,
                   "tree": source.tree, "advertised_tip": source_tip},
        "identities": bound,
        "runtime": runtime_identity(),
        "author": publisher_identity(source),
        "output": s.tree_record(checked.output),
        "online_approval": online_approval(online),
        "wiki": {"url": c.WIKI_REPO, "branch": wiki_ref, "expected_oid": tip, "state": state},
        "checked_day": utc_day().isoformat(),
    }
    report = report_bytes(receipt, online, wiki_tree(wiki, tip), checked.output)
    c.require(len(report) <= c.MAX_INPUT, "prepared report exceeds the bounded text-input limit")
    receipt["report_sha256"] = c.sha256(report)
    data = c.canonical(receipt)
    digest = c.sha256(data)
    with s.directory(root, s.BUILD + "/prepared", create=True):
        pass
    parent = root / s.BUILD / "prepared"
    target = parent / digest
    if target.exists() or target.is_symlink():
        read_receipt(root, target / "receipt.json", digest)
        c.require(c.regular_read(target, "receipt.json") == data, "receipt-address collision")
        return target / "receipt.json", digest
    temporary = ".partial-" + uuid.uuid4().hex
    with s.directory(parent, temporary + "/tree", create=True):
        pass
    stage = parent / temporary
    try:
        for name, payload in checked.output.items():
            s.write(stage / "tree", name, payload, mode=0o444)
        s.write(stage, "report.md", report, mode=0o444)
        s.write(stage, "receipt.json", data, mode=0o444)
        with s.directory(stage, "tree") as fd:
            os.fchmod(fd, 0o555)
            os.fsync(fd)
        with s.directory(stage) as fd:
            os.fchmod(fd, 0o555)
            os.fsync(fd)
        with s.directory(parent) as fd:
            c.require(digest not in os.listdir(fd), "preparation appeared concurrently; retry without overwriting it")
            os.rename(temporary, digest, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
    except BaseException:
        # Leave a named partial artifact for inspection, never recursively erase an uncertain tree.
        raise
    return target / "receipt.json", digest


def read_receipt(root: Path, path: Path, digest: str) -> tuple[dict, dict[str, bytes]]:
    c.require(re.fullmatch(r"[0-9a-f]{64}", digest), "--expect-receipt must be the human-selected SHA256")
    if not path.is_absolute():
        path = root / path
    expected = root / s.BUILD / "prepared" / digest / "receipt.json"
    c.require(path == expected, "receipt must be the named SHA256-addressed preparation, not an arbitrary file")
    with s.directory(root, s.BUILD + "/prepared/" + digest) as fd:
        c.require(set(os.listdir(fd)) == {"receipt.json", "report.md", "tree"}, "extra preparation files")
    data = c.regular_read(root, s.BUILD + "/prepared/" + digest + "/receipt.json")
    c.require(c.sha256(data) == digest, "reviewed receipt bytes changed; prepare and review a new receipt")
    receipt = c.load_json(data, "receipt")
    c.require(data == c.canonical(receipt), "receipt is not canonical JSON")
    c.object_keys(receipt, {"schema", "source", "identities", "runtime", "author", "output", "online_approval", "wiki",
                            "checked_day", "report_sha256"})
    c.require(receipt["schema"] == 1, "unsupported receipt schema")
    c.object_keys(receipt["source"], {"url", "branch", "commit", "tree", "advertised_tip"})
    c.object_keys(receipt["wiki"], {"url", "branch", "expected_oid", "state"})
    c.require(receipt["source"]["url"] == c.SOURCE_URL and receipt["source"]["branch"] == c.SOURCE_BRANCH
              and receipt["wiki"]["url"] == c.WIKI_REPO, "receipt remote identity changed")
    for oid in (receipt["source"]["commit"], receipt["source"]["tree"], receipt["source"]["advertised_tip"],
                receipt["wiki"]["expected_oid"]):
        c.require(isinstance(oid, str) and c.OID_RE.fullmatch(oid), "invalid receipt object identity")
    branch(receipt["wiki"]["branch"])
    checks.iso_day(receipt["checked_day"], "receipt check date")
    c.require(online_approval(receipt["online_approval"]) == receipt["online_approval"],
              "receipt online approval results are not in canonical form")
    report = c.regular_read(path.parent, "report.md")
    c.require(c.sha256(report) == receipt["report_sha256"], "reviewed report bytes changed")
    c.require(all((path.parent / name).lstat().st_mode & 0o777 == 0o444
                  and (path.parent / name).lstat().st_nlink == 1 for name in ("receipt.json", "report.md")),
              "prepared receipt/report must remain read-only unlinked regular files")
    c.require(path.parent.lstat().st_mode & 0o777 == 0o555
              and (path.parent / "tree").lstat().st_mode & 0o777 == 0o555,
              "prepared directories must remain read-only")
    return receipt, s.read_tree(path.parent / "tree", receipt["output"])


def verify_receipt(root: Path, path: Path, digest: str, remote: PublicRemotes,
                   checker: httpcheck.Checker) -> tuple[dict, dict[str, bytes], c.Git, str]:
    receipt, output = read_receipt(root, path, digest)
    source = c.Snapshot(root, receipt["source"]["commit"])
    clean(source.git)
    c.require(source.tree == receipt["source"]["tree"] and bind_running_tool(source) == receipt["identities"],
              "receipt source/tool/manifest/dependency/exception identity changed")
    c.require(runtime_identity() == receipt["runtime"] and publisher_identity(source) == receipt["author"],
              "receipt interpreter/parser or public publisher identity changed")
    c.require(read_bundle(installed_bundle(source.git))["identities"]["tool_files"]
              == receipt["identities"]["tool_files"], "installed hook tool identity differs from the reviewed receipt")
    checked = checks.validate(source, today=utc_day())
    c.require(checked.output == output, "prepared bytes differ from the bound projection; no regeneration is allowed")
    online = checker.all(checked.links, checked.exceptions)
    c.require(online_approval(online) == receipt["online_approval"],
              "online availability or exception use changed since review; prepare and review a new receipt")
    source_tip = remote.source(source.git, source.commit)
    ordinary_wiki(root)
    wiki = c.Git(root / s.PUBLISH)
    configure_wiki_hook(wiki, source.git)
    ref, tip = remote.wiki(wiki)
    c.require(ref == receipt["wiki"]["branch"], "wiki default branch changed since review")
    if tip != receipt["wiki"]["expected_oid"]:
        c.require(wiki_tree(wiki, tip) == output
                  and wiki.run("show", "-s", "--format=%B", tip).strip() == provenance_message(receipt).strip(),
                  "wiki advanced after receipt review; preserve the remote and prepare a new receipt")
        prior = read_provenance(wiki, tip)
        c.require(prior["parent"] == receipt["wiki"]["expected_oid"], "unexpected publication parent")
    else:
        state = receipt["wiki"]["state"]
        c.require(isinstance(state, dict) and state.get("kind") in ("bootstrap", "managed"),
                  "invalid adoption state")
        actual = remote_state(source, wiki, ref, tip, source_tip,
                              tip if state["kind"] == "bootstrap" else None)
        c.require(actual == state, "prepared bootstrap/publication state changed")
    refreshed = {"checked_day": utc_day().isoformat(), "source_tip": source_tip, "wiki_tip": tip,
                 "receipt_sha256": digest, "links": online}
    # This sidecar is outside the immutable preparation; it never changes reviewed bytes.
    with s.directory(root, s.BUILD + "/prepared", create=True):
        pass
    latest = root / s.BUILD / "prepared"
    name = ".last-check.json"
    s.write(latest, name, c.canonical(refreshed), replace=name in os.listdir(latest), mode=0o600)
    return receipt, output, wiki, tip


def transaction_path(wiki: c.Git) -> Path:
    return Path(wiki.run("rev-parse", "--absolute-git-dir").decode().strip())


def update_checkout(wiki: c.Git, old: dict[str, bytes], new: dict[str, bytes]) -> str:
    allowed = set(old) | set(new) | {".git"}
    c.require(set(os.listdir(wiki.root)) <= allowed, "unrelated publication file; refusing to stage or delete it")
    indexed = set()
    for row in wiki.run("ls-files", "--stage", "-z").split(b"\0"):
        if not row:
            continue
        header, raw_name = row.split(b"\t", 1)
        mode, oid, stage = header.decode("ascii").split()
        name = raw_name.decode("utf-8")
        c.require(name in old or name in new, "publication index contains an unrelated path")
        permitted = {c.blob_id(data) for data in (old.get(name), new.get(name)) if data is not None}
        c.require(mode == "100644" and stage == "0" and oid in permitted and name not in indexed,
                  "publication index has an unreviewed edit, mode or merge conflict")
        indexed.add(name)
    c.require(set(old) & set(new) <= indexed, "publication index has an unexpected managed deletion")
    for name in set(old) | set(new):
        path = wiki.root / name
        if path.exists() or path.is_symlink():
            value = c.regular_read(wiki.root, name)
            c.require(not path.lstat().st_mode & 0o111
                      and value in (old.get(name), new.get(name)), "publication worktree contains an unreviewed edit")
        elif name in old and name in new:
            raise c.Invalid("publication worktree has an unexpected missing page")
    for name, data in sorted(new.items()):
        s.write(wiki.root, name, data, replace=(wiki.root / name).exists())
        oid = wiki.run("hash-object", "-w", "--stdin", input=data).decode().strip()
        c.require(oid == c.blob_id(data), "Git wrote an unexpected output blob")
        wiki.run("update-index", "--add", "--cacheinfo", "100644," + oid + "," + name)
    for name in sorted(set(old) - set(new)):
        if (wiki.root / name).exists():
            s.unlink_verified(wiki.root, name, c.sha256(old[name]))
        wiki.run("update-index", "--force-remove", "--", name)
    tree = wiki.run("write-tree").decode().strip()
    c.require(tree == s.tree_record(new)["git_tree"], "publication index has unexpected entries")
    return tree


def candidate_commit(wiki: c.Git, receipt: dict, tree: str) -> str:
    author = receipt["author"]
    env = {}
    for role in ("AUTHOR", "COMMITTER"):
        env["GIT_" + role + "_NAME"] = author["name"]
        env["GIT_" + role + "_EMAIL"] = author["email"]
        env["GIT_" + role + "_DATE"] = str(author["timestamp"]) + " +0000"
    message = provenance_message(receipt)
    checks.require_private_safe(message, "wiki-commit-message")
    return wiki.run("commit-tree", tree, "-p", receipt["wiki"]["expected_oid"],
                    input=message, env_extra=env).decode().strip()


def publish(root: Path, path: Path, digest: str, *, remote: PublicRemotes | None = None,
            checker: httpcheck.Checker | None = None) -> str:
    remote, checker = remote or PublicRemotes(), checker or httpcheck.Checker()
    receipt, output, wiki, remote_tip = verify_receipt(root, path, digest, remote, checker)
    expected, ref = receipt["wiki"]["expected_oid"], receipt["wiki"]["branch"]
    current = wiki.commit("HEAD")
    marker_root, marker_name = transaction_path(wiki), "wiki-transaction.json"
    marker = {"receipt_sha256": digest, "expected": expected, "tree": receipt["output"]["git_tree"]}
    marker_data = c.canonical(marker)
    marker_exists = marker_name in os.listdir(marker_root)
    if marker_exists:
        c.require(c.regular_read(marker_root, marker_name) == marker_data,
                  "a different interrupted publication needs explicit reconciliation")
    else:
        clean(wiki)
    c.require(wiki.run("symbolic-ref", "-q", "HEAD").decode().strip() == ref, "publication branch changed")
    if wiki_tree(wiki, remote_tip) == output:
        c.require(current == remote_tip, "remote already has the reviewed output but this clone needs deliberate fast-forward reconciliation")
        clean(wiki)
        check_clone_files(wiki, output)
        if marker_exists:
            s.unlink_verified(marker_root, marker_name, c.sha256(marker_data))
        return "already-published"
    c.require(remote_tip == expected, "wiki remote drifted")
    if not marker_exists:
        c.require(current == expected, "publication clone advanced outside this receipt")
        s.write(marker_root, marker_name, marker_data, mode=0o600)
    old = wiki_tree(wiki, expected)
    tree = update_checkout(wiki, old, output)
    candidate = candidate_commit(wiki, receipt, tree)
    c.require(current in (expected, candidate), "unexpected local publication commit")
    if current == expected:
        wiki.run("update-ref", ref, candidate, expected)
    clean(wiki)
    # Bind the wiki hook to exactly this invocation; the publisher still checks directly.
    wiki.run("config", "--local", "wiki.receipt", str(path if path.is_absolute() else root / path))
    wiki.run("config", "--local", "wiki.expectReceipt", digest)
    latest_ref, latest = remote.wiki(wiki)
    c.require(latest_ref == ref and latest == expected, "wiki moved immediately before push; no force retry")
    remote.push(wiki, candidate, ref)
    verified_ref, verified = remote.wiki(wiki)
    c.require(verified_ref == ref and verified == candidate and wiki_tree(wiki, verified) == output,
              "push read-back did not match the prepared commit/tree; inspect the remote before retrying")
    s.unlink_verified(marker_root, marker_name, c.sha256(marker_data))
    return "published"


def run_tests(tool_root: Path, repository: Path, trusted_ref: str) -> None:
    env = c.git_env()
    env["WIKI_TEST_REPOSITORY"] = str(repository)
    env["WIKI_TEST_SOURCE_REF"] = trusted_ref
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with s.directory(repository, s.BUILD + "/tests", create=True):
        pass
    with tempfile.TemporaryDirectory(prefix="suite-", dir=repository / s.BUILD / "tests") as temporary:
        output = Path(temporary)
        with s.directory(output, "fixtures", create=True):
            pass
        with s.directory(output, "bytecode", create=True):
            pass
        env["WIKI_TEST_OUTPUT"] = str(output / "fixtures")
        env.update(TMPDIR=temporary, TMP=temporary, TEMP=temporary)
        try:
            result = subprocess.run([sys.executable, "-I", "-B", "-X", "pycache_prefix=" + str(output / "bytecode"),
                                     "-m", "unittest", "discover",
                                     "-s", str(tool_root / "tools/wiki/tests"), "-p", "test_wiki.py"],
                                    cwd=output, env=env, capture_output=True, timeout=300, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise c.Invalid("trusted tooling fixtures could not finish; run the documented unittest command") from None
        c.require(result.returncode == 0, "trusted tooling fixtures failed; run the documented unittest command (push blocked)")


def install_hook(root: Path, ref: str) -> Path:
    source = c.Snapshot(root, ref)
    c.require(not source.worktree, "hook installation requires committed trusted tooling")
    identity = bind_running_tool(source)
    gitdir = Path(source.git.run("rev-parse", "--absolute-git-dir").decode().strip())
    interpreter = sys.executable
    c.require(Path(interpreter).is_absolute() and "\n" not in interpreter, "invalid pinned interpreter")
    metadata = {"schema": 1, "source": source.commit, "identities": identity,
                "runtime": runtime_identity(), "interpreter": interpreter}
    digest = c.sha256(c.canonical(metadata))
    parent = gitdir / "wiki-validator"
    bundle = gitdir / "wiki-validator" / digest
    ensure_hooks_available(source.git, bundle)
    with s.directory(gitdir, "wiki-validator", create=True) as parent_fd:
        fcntl.flock(parent_fd, fcntl.LOCK_EX)
        if digest in os.listdir(parent_fd):
            c.require(read_bundle(bundle) == metadata, "existing hook bundle identity differs")
            run_tests(bundle, root, source.commit)
        else:
            temporary = ".partial-" + uuid.uuid4().hex
            os.mkdir(temporary, 0o700, dir_fd=parent_fd)
            stage = parent / temporary
            for directory in bundle_directories():
                with s.directory(stage, directory, create=True):
                    pass
            for path in TOOL_PATHS:
                relative = Path(path)
                s.write(stage / relative.parent, relative.name, source.read(path), mode=BUNDLE_MODES[path])
            s.write(stage / "hooks", "pre-push", source.read(".githooks/pre-push"), mode=0o555)
            s.write(stage, "interpreter", (interpreter + "\n").encode(), mode=0o444)
            s.write(stage, "bundle.json", c.canonical(metadata), mode=0o444)
            c.require(read_bundle(stage, sealed=False) == metadata, "staged hook bundle identity differs")
            run_tests(stage, root, source.commit)
            c.require(read_bundle(stage, sealed=False) == metadata, "staged hook bundle changed during its tests")
            seal_bundle(stage)
            c.require(digest not in os.listdir(parent_fd), "hook bundle appeared concurrently; retry without overwriting it")
            os.rename(temporary, digest, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
        c.require(read_bundle(bundle) == metadata, "final hook bundle identity differs; configuration was not installed")
        ensure_hooks_available(source.git, bundle)
        source.git.run("config", "--local", "wiki.trustBundle", str(bundle))
        source.git.run("config", "--local", "core.hooksPath", str(bundle / "hooks"))
    return bundle


def parse_updates(data: bytes) -> list[tuple[str, str, str, str]]:
    c.require(len(data) <= 64 * 1024, "oversized pre-push update list")
    updates = []
    seen = set()
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeError:
        raise c.Invalid("non-ASCII pre-push update list") from None
    for line in lines:
        fields = line.split()
        c.require(len(fields) == 4, "malformed pre-push update")
        local, new, target, old = fields
        branch(target)
        c.require(local in ("HEAD", new) or local.startswith("refs/heads/"), "unsupported local ref/object")
        if local not in ("HEAD", new):
            branch(local)
        c.require(c.OID_RE.fullmatch(new) and new != ZERO and c.OID_RE.fullmatch(old),
                  "branch deletions and non-commit update OIDs are unsupported")
        c.require(target not in seen, "duplicate proposed remote ref")
        seen.add(target)
        updates.append((local, new, target, old))
    c.require(updates, "empty pre-push update list; nothing was validated")
    return updates


def content_pre_push(root: Path, data: bytes, remote_name: str, remote_url: str,
                     trust: dict, *, remote: PublicRemotes | None = None, test_runner=None) -> None:
    c.require(remote_name in ("origin", c.SOURCE_URL) and remote_url == c.SOURCE_URL,
              "content hook only supports the exact public source origin")
    c.require(trust.get("runtime") == runtime_identity(),
              "trusted runtime or system executable identity changed; reinstall or reselect the reviewed tool")
    remote = remote or PublicRemotes()
    git = c.Git(root)
    real_history(git)
    remote.origin(git, c.SOURCE_URL)
    updates = parse_updates(data)
    _, refs = remote.advertised(git, c.SOURCE_URL)
    remote.fetch(git, c.SOURCE_URL, refs)
    _, after = remote.advertised(git, c.SOURCE_URL)
    c.require(after == refs, "advertised public refs moved during hook validation; retry")
    for _, new, ref, old in updates:
        c.require(git.run("cat-file", "-t", new).strip() == b"commit",
                  "proposed branch tip must be a commit, not a tag/tree/blob")
        c.require(git.commit(new) == new, "proposed tip is not a commit")
        c.require(refs.get(ref, ZERO) == old, "pre-push old OID differs from the live advertisement")
        if old != ZERO:
            c.require(git.ancestor(old, new), "non-fast-forward source update refused")
        snapshot = c.Snapshot(root, new)
        c.require(identities(snapshot)["tool_files"] == trust["identities"]["tool_files"],
                  "proposed validator differs from explicitly trusted tooling; review and install that tool version first")
        checks.validate(snapshot, today=utc_day())
    tips = sorted({new for _, new, _, _ in updates})
    excluded = sorted({git.commit(oid) for oid in refs.values()})
    commits = git.run("rev-list", "--topo-order", *tips, "--not", *excluded).decode().splitlines()
    c.require(len(commits) <= 10000, "too many new commits for the local review gate; split and review deliberately")
    object_ids = set(git.run("rev-list", "--objects", "--no-object-names", *tips,
                             "--not", *excluded).decode().splitlines())
    c.require(len(object_ids) <= 50000, "too many new objects for the bounded local review gate")
    scanned = set()
    for commit in commits:
        snapshot = c.Snapshot(root, commit)
        snapshot.protected()
        checks.require_private_safe(git.run("cat-file", "commit", commit), "commit-message")
        parents = git.run("rev-list", "--parents", "-n", "1", commit).decode().split()[1:]
        parent_entries = [git.entries(parent) for parent in parents]
        previous = parent_entries[0] if parent_entries else {}
        allowances = []
        # Every parent matters: a commit may remove all tooling, including its manifest.
        if any(path == ".githooks/pre-push" or path == "tools/wiki" or path.startswith("tools/wiki/")
               for entries in (snapshot.entries, *parent_entries) for path in entries):
            c.require(c.MANIFEST in snapshot.entries,
                      "new history omits the wiki manifest while validator files are present or removed; "
                      "review and repair that history before pushing")
            c.require(tool_identity(snapshot) == trust["identities"]["tool_files"],
                      "new history includes an untrusted intermediate validator version; review it before pushing")
            m = c.manifest(snapshot)
            allowances = checks.validation_exceptions(m, snapshot, utc_day())
        for path, (mode, kind, oid) in snapshot.entries.items():
            if previous.get(path) != (mode, kind, oid):
                c.safe_path(path)
                checks.require_private_safe(path.encode(), "new-path")
                c.require(kind == "blob" and mode in ("100644", "100755"), "new symlink, submodule, or unsupported object")
                if path.startswith("wiki/"):
                    c.require(mode == "100644", "new executable wiki page in pushed history")
            if oid not in object_ids or (path, oid) in scanned:
                continue
            scanned.add((path, oid))
            checks.require_private_safe(git.blob(oid), path, allowances,
                                        approved_blob=c.RECIPE_BLOB if path == c.RECIPE_PATH else None)
    if test_runner:
        test_runner()
    else:
        run_tests(Path(__file__).absolute().parents[2], root, trust["source"])
    c.require(trust["runtime"] == runtime_identity(),
              "trusted runtime or system executable identity changed during push validation")


def wiki_pre_push(root: Path, data: bytes, remote_name: str, remote_url: str, *,
                  remote: PublicRemotes | None = None, checker: httpcheck.Checker | None = None) -> None:
    c.require(remote_name in ("origin", c.WIKI_REPO) and remote_url == c.WIKI_REPO, "unapproved wiki push destination")
    updates = parse_updates(data)
    c.require(len(updates) == 1, "wiki publication permits exactly one branch update")
    wiki = c.Git(root)
    source_root = Path(wiki.run("config", "--local", "--get", "wiki.sourceRoot").decode().strip())
    c.require(root == source_root / s.PUBLISH, "wiki hook must run in the named publication clone")
    path = Path(wiki.run("config", "--local", "--get", "wiki.receipt").decode().strip())
    digest = wiki.run("config", "--local", "--get", "wiki.expectReceipt").decode().strip()
    receipt, output, _, tip = verify_receipt(source_root, path, digest,
                                            remote or PublicRemotes(), checker or httpcheck.Checker())
    _, new, ref, old = updates[0]
    c.require(ref == receipt["wiki"]["branch"] and old == receipt["wiki"]["expected_oid"] == tip,
              "wiki hook update is not the reviewed receipt target")
    c.require(wiki_tree(wiki, new) == output and wiki.ancestor(old, new), "wiki push tree/history differs from receipt")
    c.require(wiki.run("show", "-s", "--format=%B", new).strip() == provenance_message(receipt).strip(),
              "wiki commit provenance differs from receipt")
    c.require(wiki.run("rev-list", "--parents", "-n", "1", new).decode().split() == [new, old],
              "wiki publication must be a single forward commit")
    checks.require_private_safe(wiki.run("cat-file", "commit", new), "wiki-commit")
    clean(wiki)
