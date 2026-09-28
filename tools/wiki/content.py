# SPDX-License-Identifier: GPL-2.0-only
"""Exact Git inputs and lossless, enumerated wiki projection."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from typing import Any
from urllib.parse import urlsplit

SOURCE_URL = "https://github.com/xjamesmorris/k3-com260-info.git"
SOURCE_BRANCH = "refs/heads/main"
WIKI_REPO = "https://github.com/xjamesmorris/k3-com260-info.wiki.git"
WIKI_URL = "https://github.com/xjamesmorris/k3-com260-info/wiki"
REPO_WEB = SOURCE_URL.removesuffix(".git")
BASELINE = "57400da095e944c75e63154b1c187e18a3ac3359"
PROTECTED_PATH = "k3-com260-fedora-howto"
PROTECTED_TREE = "db99cfb1555592c097e4c283b488149067ebea7b"
RECIPE_PATH = PROTECTED_PATH + "/README.md"
RECIPE_BLOB = "de8a7c54d1b46a69e259e470cfead00b724197bc"
RECIPE_SHA256 = "d50d5b3f0b8098a79505ea3ca4b0db38aafa53c62bf08496ef3aa425cee69f35"
CRITICAL_SOURCES = {
    "omni-bootstrap": (RECIPE_PATH, RECIPE_BLOB, ".raw.xz", 2),
    "fedora-guest": (PROTECTED_PATH + "/scripts/prepare-riscv-fedora-guest.sh",
                     "412f9036aced7348dc70a4e86727f7d8a57cfe83", ".qcow2", 1),
}
MANIFEST = "tools/wiki/manifest.json"
EXCEPTIONS = "tools/wiki/link-exceptions.json"
LOCK = "tools/wiki/requirements.txt"
PARSER_VERSIONS = {"markdown-it-py": "4.2.0", "mdurl": "0.1.2"}
MAX_INPUT = 2 * 1024 * 1024
OID_RE = re.compile(r"[0-9a-f]{40}\Z")
SLUG_RE = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\.md\Z")
SYSTEM_EXECUTABLE_CANDIDATES = {
    "git": (Path("/usr/bin/git"),),
    "gh": (Path("/usr/bin/gh"),),
}
SYSTEM_PATH = "/usr/bin"
_EXECUTABLE_BINDINGS: dict[str, tuple[dict[str, Any], tuple[Any, ...]]] = {}


class Invalid(ValueError):
    """A public-safe diagnostic; never include untrusted content in messages."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise Invalid(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode()


def load_json(data: bytes, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            require(key not in result, f"{label}: duplicate JSON key")
            result[key] = value
        return result

    try:
        return json.loads(data, object_pairs_hook=pairs)
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, Invalid):
            raise
        raise Invalid(f"{label}: invalid UTF-8 JSON") from None


def text(data: bytes, label: str = "input") -> str:
    require(len(data) <= MAX_INPUT and b"\0" not in data, f"{label}: binary or oversized input")
    try:
        return data.decode("utf-8")
    except UnicodeError:
        raise Invalid(f"{label}: input must be UTF-8 text") from None


def safe_path(value: Any) -> str:
    require(isinstance(value, str) and bool(value), "invalid relative path")
    p = PurePosixPath(value)
    require(
        not p.is_absolute()
        and value == p.as_posix()
        and all(part not in (".", "..", ".git") for part in p.parts)
        and re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", value),
        "unsafe relative path",
    )
    return value


def open_directory(root: Path) -> int:
    require(root.is_absolute() and ".." not in root.parts, "directory root must be an absolute lexical path")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except OSError:
        os.close(fd)
        raise Invalid("missing or symlinked directory ancestor") from None


def regular_read(root: Path, relative: str, limit: int = MAX_INPUT) -> bytes:
    """Read without following any input symlink, including parent directories."""
    parts = PurePosixPath(safe_path(relative)).parts
    fd = open_directory(root)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            mode = os.fstat(child)
            require(stat.S_ISREG(mode.st_mode), "input is not a regular file")
            require(mode.st_size <= limit, "input is oversized")
            with os.fdopen(child, "rb", closefd=False) as stream:
                data = stream.read(limit + 1)
            require(len(data) <= limit, "input is oversized")
            return data
        finally:
            os.close(child)
    except OSError:
        raise Invalid("missing, unreadable, or symlinked input; inspect the listed source paths") from None
    finally:
        os.close(fd)


def _safe_system_node(info: os.stat_result, *, directory: bool) -> bool:
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    return (
        kind
        and info.st_uid == 0
        and not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        and (directory or (
            info.st_nlink == 1
            and bool(info.st_mode & stat.S_IXUSR)
            and not info.st_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX)
        ))
    )


def _system_executable_metadata(path: Path, name: str) -> tuple[int, dict[str, Any], tuple[Any, ...]]:
    message = (
        f"trusted system {name} executable is unavailable or unsafe; "
        f"require a root-owned, non-writable /usr/bin/{name}"
    )
    require(name in SYSTEM_EXECUTABLE_CANDIDATES and path.is_absolute()
            and path.name == name and ".." not in path.parts, message)
    fd = -1
    executable = -1
    current = Path("/")
    ancestors = []
    token = []
    try:
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        info = os.fstat(fd)
        require(_safe_system_node(info, directory=True), message)
        ancestors.append({"path": "/", "uid": info.st_uid, "gid": info.st_gid,
                          "mode": f"{stat.S_IMODE(info.st_mode):04o}"})
        token.append((info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                      info.st_mtime_ns, info.st_ctime_ns))
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=fd)
            os.close(fd)
            fd = child
            current /= part
            info = os.fstat(fd)
            require(_safe_system_node(info, directory=True), message)
            ancestors.append({"path": str(current), "uid": info.st_uid, "gid": info.st_gid,
                              "mode": f"{stat.S_IMODE(info.st_mode):04o}"})
            token.append((info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                          info.st_mtime_ns, info.st_ctime_ns))
        executable = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
        info = os.fstat(executable)
        require(_safe_system_node(info, directory=False), message)
        identity = {
            "path": str(path),
            "size": info.st_size,
            "uid": info.st_uid,
            "gid": info.st_gid,
            "mode": f"{stat.S_IMODE(info.st_mode):04o}",
            "ancestors": ancestors,
        }
        token.append((info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                      info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns))
        result = executable
        executable = -1
        return result, identity, tuple(token)
    except (OSError, Invalid):
        raise Invalid(message) from None
    finally:
        if executable >= 0:
            os.close(executable)
        if fd >= 0:
            os.close(fd)


def inspect_system_executable(path: Path, name: str) -> tuple[dict[str, Any], tuple[Any, ...]]:
    executable, identity, token = _system_executable_metadata(path, name)
    digest = hashlib.sha256()
    try:
        while True:
            chunk = os.read(executable, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        info = os.fstat(executable)
        current = (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                   info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        require(token[-1] == current, f"trusted system {name} executable changed while it was read")
    finally:
        os.close(executable)
    identity["sha256"] = digest.hexdigest()
    return identity, token


def _copy_executable_identity(identity: dict[str, Any]) -> dict[str, Any]:
    return {**identity, "ancestors": [dict(entry) for entry in identity["ancestors"]]}


def system_executable_identity(name: str) -> dict[str, Any]:
    require(name in SYSTEM_EXECUTABLE_CANDIDATES, "unsupported system executable")
    if name not in _EXECUTABLE_BINDINGS:
        for candidate in SYSTEM_EXECUTABLE_CANDIDATES[name]:
            try:
                _EXECUTABLE_BINDINGS[name] = inspect_system_executable(candidate, name)
                break
            except Invalid:
                continue
        require(name in _EXECUTABLE_BINDINGS,
                f"trusted system {name} executable is unavailable or unsafe; "
                f"require a root-owned, non-writable /usr/bin/{name}")
    identity, expected_token = _EXECUTABLE_BINDINGS[name]
    executable, current, current_token = _system_executable_metadata(Path(identity["path"]), name)
    os.close(executable)
    require(current == {key: value for key, value in identity.items() if key != "sha256"}
            and current_token == expected_token,
            f"trusted system {name} executable identity changed during execution; restart and revalidate")
    return _copy_executable_identity(identity)


def system_executable_path(name: str) -> str:
    return system_executable_identity(name)["path"]


def system_executable_identities() -> dict[str, dict[str, Any]]:
    return {name: system_executable_identity(name) for name in sorted(SYSTEM_EXECUTABLE_CANDIDATES)}


def subprocess_env(*, credentials: bool = False) -> dict[str, str]:
    env = {"PATH": SYSTEM_PATH, "LC_ALL": "C", "LANG": "C"}
    if credentials:
        for key in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR",
                    "DBUS_SESSION_BUS_ADDRESS"):
            value = os.environ.get(key)
            if value and not re.search(r"[\x00\r\n]", value):
                env[key] = value
    return env


def git_env(*, credentials: bool = False) -> dict[str, str]:
    env = subprocess_env(credentials=credentials)
    env.update(
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT="0",
        GIT_NO_REPLACE_OBJECTS="1",
        LC_ALL="C",
    )
    return env


class Git:
    def __init__(self, root: Path):
        self.root = root

    def run(self, *args: str, input: bytes | None = None, ok: tuple[int, ...] = (0,),
            env_extra: dict[str, str] | None = None) -> bytes:
        env = git_env()
        if env_extra:
            require(all(isinstance(value, str)
                        and re.fullmatch(r"GIT_(?:AUTHOR|COMMITTER)_(?:NAME|EMAIL|DATE)", key)
                        and not re.search(r"[\x00\r\n]", value)
                        for key, value in env_extra.items()),
                    "unsupported Git subprocess environment")
            env.update(env_extra)
        try:
            proc = subprocess.run(
                [system_executable_path("git"), "--no-pager", "--no-replace-objects",
                 "-c", "core.fsmonitor=false",
                 "-c", "core.hooksPath=/dev/null", "-C", str(self.root), *args],
                input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=env, timeout=90, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise Invalid("Git unavailable or timed out; no publication was authorized") from None
        require(proc.returncode in ok, f"Git {args[0]} failed (details suppressed to protect input data)")
        return proc.stdout

    def commit(self, ref: str) -> str:
        require(bool(ref) and not ref.startswith("-") and "\0" not in ref, "invalid Git ref")
        oid = self.run("rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
        require(OID_RE.fullmatch(oid), "only full SHA-1 commit objects are supported")
        return oid

    def entries(self, ref: str) -> dict[str, tuple[str, str, str]]:
        entries = {}
        for row in self.run("ls-tree", "-rz", "--full-tree", ref).split(b"\0"):
            if not row:
                continue
            header, raw_path = row.split(b"\t", 1)
            try:
                path = raw_path.decode("utf-8")
            except UnicodeError:
                raise Invalid("non-UTF-8 Git path") from None
            mode, kind, oid = header.decode("ascii").split()
            require(path not in entries, "duplicate Git tree path")
            entries[path] = (mode, kind, oid)
        return entries

    def blob(self, oid: str) -> bytes:
        require(OID_RE.fullmatch(oid), "invalid blob identity")
        size = int(self.run("cat-file", "-s", oid))
        require(size <= MAX_INPUT, "oversized Git input; binaries are not supported in this version")
        return self.run("cat-file", "blob", oid)

    def ancestor(self, old: str, new: str) -> bool:
        return self.run("merge-base", old, new, ok=(0, 1)).decode().strip() == old


class Snapshot:
    def __init__(self, root: Path, ref: str = "HEAD", *, worktree: bool = False):
        self.root = root
        self.git = Git(root)
        self.commit = self.git.commit(ref)
        self.worktree = worktree
        self.entries = self.git.entries(self.commit)
        self.tree = self.git.run("rev-parse", self.commit + "^{tree}").decode().strip()

    def read(self, path: str, *, page: bool = False) -> bytes:
        safe_path(path)
        if self.worktree:
            data = regular_read(self.root, path)
            if page:
                require(not (self.root / path).lstat().st_mode & 0o111, "executable page input")
            return data
        require(path in self.entries, "missing committed input; commit all manifest-listed files")
        mode, kind, oid = self.entries[path]
        require(kind == "blob" and mode in (("100644",) if page else ("100644", "100755")),
                "input has an unsupported mode or is a symlink")
        return self.git.blob(oid)

    def inventory(self, prefix: str) -> set[str]:
        if not self.worktree:
            return {p for p in self.entries if p.startswith(prefix + "/")}
        directory = self.root / safe_path(prefix)
        require(directory.is_dir() and not directory.is_symlink(), "missing or symlinked input directory")
        paths = set()
        for base, dirs, files in os.walk(directory, followlinks=False):
            require(not any((Path(base) / d).is_symlink() for d in dirs), "symlinked input directory")
            for filename in files:
                paths.add((Path(base) / filename).relative_to(self.root).as_posix())
        return paths

    def protected(self) -> None:
        tree = self.git.run("rev-parse", self.commit + ":" + PROTECTED_PATH).decode().strip()
        require(tree == PROTECTED_TREE, "protected historical how-to tree changed")
        if self.worktree:
            expected = {p for p in self.entries if p.startswith(PROTECTED_PATH + "/")}
            require(self.inventory(PROTECTED_PATH) == expected, "protected historical inventory changed")
            for path in sorted(expected):
                mode, kind, oid = self.entries[path]
                data = self.read(path)
                actual_mode = "100755" if (self.root / path).lstat().st_mode & 0o111 else "100644"
                require(kind == "blob" and mode == actual_mode and blob_id(data) == oid,
                        "protected historical bytes or mode changed")


def parser():
    try:
        for name, version in PARSER_VERSIONS.items():
            require(importlib.metadata.version(name) == version,
                    "wrong parser version; use .wiki-venv with hash-locked requirements.txt")
        from markdown_it import MarkdownIt
    except (ImportError, importlib.metadata.PackageNotFoundError):
        raise Invalid("parser missing; create .wiki-venv and install --require-hashes -r tools/wiki/requirements.txt") from None
    return MarkdownIt("commonmark").enable(["table", "strikethrough"])


def nodes(tokens):
    for token in tokens:
        yield token
        if token.children:
            yield from nodes(token.children)


def link_values(tokens) -> list[str]:
    return [t.attrGet("href") for t in nodes(tokens) if t.type == "link_open"]


def ast_signature(tokens, replace: tuple[str, str] | None = None):
    signature = []
    for t in nodes(tokens):
        attrs = dict(t.attrs)
        if replace and attrs.get("href") == replace[0]:
            attrs["href"] = replace[1]
        signature.append((t.type, t.tag, t.nesting, tuple(sorted(attrs.items())),
                          "" if t.children else t.content, t.markup, t.info))
    return signature


def relocate_links(source: str, rules: list[dict[str, Any]]) -> str:
    """Locate destinations by reparsing candidates, never by rewriting Markdown."""
    md = parser()
    original = md.parse(source)
    hrefs = link_values(original)
    signature = ast_signature(original)
    edits: list[tuple[int, int, str]] = []
    for rule in rules:
        old, new, count = rule["old"], rule["new"], rule["count"]
        normalized = md.normalizeLink(old)
        expected = {i for i, value in enumerate(hrefs) if value == normalized}
        require(len(expected) == count, "recipe link transform count changed")
        covered: set[int] = set()
        occurrences = list(re.finditer(re.escape(old), source))
        require(len(occurrences) <= 128, "recipe transform has too many ambiguous candidates")
        for occurrence in occurrences:
            marker = "https://example.invalid/wiki-transform-destination"
            require(marker not in source, "reserved transform marker in source")
            candidate = source[:occurrence.start()] + marker + source[occurrence.end():]
            parsed = md.parse(candidate)
            changed = link_values(parsed)
            if len(changed) != len(hrefs):
                continue
            affected = {i for i, value in enumerate(changed) if value == marker}
            if not affected or not affected <= expected:
                continue
            if ast_signature(parsed, (marker, normalized)) != signature:
                continue
            require(not covered & affected, "ambiguous recipe link destination")
            covered |= affected
            edits.append((occurrence.start(), occurrence.end(), new))
        require(covered == expected, "recipe link destination is not an exact supported source match")
    edits.sort()
    require(all(a[1] <= b[0] for a, b in zip(edits, edits[1:])), "overlapping recipe transforms")
    for start, end, replacement in reversed(edits):
        source = source[:start] + replacement + source[end:]
    return source


def object_keys(value: Any, required: set[str], optional: set[str] = frozenset()) -> None:
    require(isinstance(value, dict) and required <= value.keys()
            and value.keys() <= required | optional, "JSON object has missing or unsupported fields")


def critical_artifacts(snapshot: Snapshot, entries: Any) -> None:
    require(isinstance(entries, list) and len(entries) == len(CRITICAL_SOURCES),
            "manifest must enumerate both critical installation images")
    seen = set()
    for entry in entries:
        object_keys(entry, {"id", "url", "sha256", "checksum_url", "source"})
        identifier = entry["id"]
        require(isinstance(identifier, str) and identifier in CRITICAL_SOURCES
                and identifier not in seen, "missing, duplicate or unknown critical artifact")
        seen.add(identifier)
        path, blob, suffix, hash_count = CRITICAL_SOURCES[identifier]
        require(entry["source"] == {"path": path, "blob": blob},
                "critical artifact source must be its exact protected public blob")
        url = entry["url"]
        require(isinstance(url, str) and len(url) <= 4096
                and url.startswith("https://dl.fedoraproject.org/"), "invalid critical image URL")
        parts = urlsplit(url)
        require(parts.netloc == "dl.fedoraproject.org" and not parts.query and not parts.fragment
                and parts.path.endswith(suffix), "critical image URL has an unexpected origin or format")
        safe_path(parts.path.rsplit("/", 1)[-1])
        require(entry["checksum_url"] == url + ".sha256", "critical checksum URL must name the explicit image sidecar")
        digest = entry["sha256"]
        require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest),
                "invalid critical image SHA256")
        data = snapshot.read(path)
        require(blob_id(data) == blob, "critical image pin source blob changed")
        source = text(data)
        require(len(re.findall(re.escape(url) + r"(?=$|[\s<>\"'`])", source)) == 1
                and source.count(digest) == hash_count,
                "critical image URL/hash does not match the protected public pin")
        if identifier == "fedora-guest":
            require(source.count(entry["checksum_url"]) == 1, "guest checksum metadata source changed")


def manifest(snapshot: Snapshot) -> dict[str, Any]:
    value = load_json(snapshot.read(MANIFEST, page=True), "manifest")
    object_keys(value, {"schema", "repository", "source_branch", "wiki_repository", "wiki_url",
                        "baseline_commit", "protected", "pages", "recipe", "bootstrap_home",
                        "validation_exceptions", "critical_artifacts"})
    require(value["schema"] == 1, "unsupported manifest schema")
    for key, expected in (("repository", SOURCE_URL), ("source_branch", SOURCE_BRANCH),
                          ("wiki_repository", WIKI_REPO), ("wiki_url", WIKI_URL),
                          ("baseline_commit", BASELINE)):
        require(value[key] == expected, f"manifest {key} is not the approved public identity")
    require(value["protected"] == {"path": PROTECTED_PATH, "tree": PROTECTED_TREE},
            "manifest protected baseline changed; separate review is required")
    require(isinstance(value["pages"], list) and value["pages"], "empty page inventory")
    seen: set[str] = set()
    for page in value["pages"]:
        object_keys(page, {"source", "target", "title", "section", "kind"})
        target = page["target"]
        require(isinstance(target, str) and SLUG_RE.fullmatch(target), "invalid page slug")
        require(page["source"] == "wiki/" + target, "page source-to-target mapping must be exact")
        require(target.casefold() not in seen and target != "Fedora-Recipe.md", "duplicate page slug")
        seen.add(target.casefold())
        require(page["section"] in ("Start", "Operate", "Develop", "Resources"), "invalid navigation group")
        require(page["kind"] in ("landing", "procedure", "reference", "resources"), "invalid page kind")
        require(isinstance(page["title"], str) and re.fullmatch(r"[A-Za-z0-9 ,()/-]+", page["title"]),
                "invalid navigation title")
    require("home.md" in seen, "manifest must include Home.md")
    recipe = value["recipe"]
    object_keys(recipe, {"source", "target", "blob", "sha256", "title", "section",
                         "links", "checkout", "navigation"})
    require((recipe["source"], recipe["target"], recipe["blob"], recipe["sha256"], recipe["section"])
            == (RECIPE_PATH, "Fedora-Recipe.md", RECIPE_BLOB, RECIPE_SHA256, "Start"),
            "generated recipe source, destination or identity changed")
    require(isinstance(recipe["title"], str) and re.fullmatch(r"[A-Za-z0-9 ,()/-]+", recipe["title"]),
            "invalid recipe navigation title")
    require(isinstance(recipe["links"], list), "invalid recipe link rules")
    old_values = set()
    for rule in recipe["links"]:
        object_keys(rule, {"old", "new", "count"})
        require(isinstance(rule["old"], str) and rule["old"]
                and rule["old"] not in old_values, "invalid or duplicate recipe link rule")
        old_values.add(rule["old"])
        require(isinstance(rule["new"], str) and rule["new"].startswith(REPO_WEB + "/blob/" + BASELINE + "/"),
                "recipe links must refer to the approved public baseline")
        require(type(rule["count"]) is int and 0 < rule["count"] <= 32, "invalid recipe match count")
    require(recipe["checkout"] == {
        "old": 'export HOWTO="$WORK/k3-com260-info/docs/k3-fedora-howto"',
        "new": 'export HOWTO="$WORK/k3-com260-info/k3-com260-fedora-howto"',
        "count": 1,
    }, "checkout transform must be the single approved root-README correction")
    require(recipe["navigation"] == {
        "installation": WIKI_URL + "/Install-Fedora",
        "recovery": WIKI_URL + "/Console-and-Recovery#factory-recovery-only-when-needed",
        "home": WIKI_URL + "/Home",
    }, "generated recipe navigation must use the maintained wiki authorities")
    bootstrap = value["bootstrap_home"]
    try:
        bootstrap_bytes = bootstrap.encode("utf-8") if isinstance(bootstrap, str) else None
    except UnicodeError:
        bootstrap_bytes = None
    require(isinstance(bootstrap, str) and bool(bootstrap.strip()) and bootstrap.endswith("\n")
            and "\r" not in bootstrap and "\0" not in bootstrap
            and bootstrap_bytes is not None and len(bootstrap_bytes) < 4096,
            "invalid bootstrap Home bytes")
    require(isinstance(value["validation_exceptions"], list), "invalid validation exceptions")
    critical_artifacts(snapshot, value["critical_artifacts"])
    return value


def recipe_body(data: bytes, recipe: dict[str, Any]) -> bytes:
    require(blob_id(data) == recipe["blob"] and sha256(data) == recipe["sha256"],
            "recipe does not match its protected blob and SHA-256")
    original = text(data, "recipe")
    result = relocate_links(original, recipe["links"])
    old, new = recipe["checkout"]["old"], recipe["checkout"]["new"]
    lines = result.splitlines(keepends=True)
    matches = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == old]
    require(len(matches) == 1 and original.count(old) == 1, "checkout correction requires exactly one source line")
    fences = [t for t in parser().parse(result) if t.type == "fence" and t.info in ("sh", "bash")]
    require(any(t.map[0] < matches[0] < t.map[1] - 1 for t in fences),
            "checkout correction must be in the recorded shell fence")
    lines[matches[0]] = lines[matches[0]].replace(old, new, 1)
    return "".join(lines).encode("utf-8")


def render(snapshot: Snapshot) -> tuple[dict[str, Any], dict[str, bytes]]:
    m = manifest(snapshot)
    snapshot.protected()
    expected = {p["source"] for p in m["pages"]}
    require(snapshot.inventory("wiki") == expected, "wiki inventory differs from manifest (missing or extra files)")
    output = {p["target"]: snapshot.read(p["source"], page=True) for p in m["pages"]}
    for data in output.values():
        text(data, "page")
    mode = "WORKTREE PREVIEW - NOT FOR PUBLICATION. " if snapshot.worktree else ""
    source_link = f"{REPO_WEB}/blob/{snapshot.commit}/{RECIPE_PATH}"
    banner = (
        "<!-- Generated; do not edit. SPDX-License-Identifier: GPL-2.0-only -->\n\n"
        "> **Historical reference.** " + mode
        + "This is the retained September 25, 2026 bring-up record, not a new hardware result.\n"
        f"> [Canonical source at {snapshot.commit}]({source_link}). "
        "The original snapshot table below supplies this reference's hardware and stack metadata.\n"
        "> Only the manifest-enumerated Markdown links and the single `HOWTO` checkout path "
        "(the correction already documented in the repository README) are adapted. "
        "All other source bytes, including commands and limitations, are retained.\n"
        f"> [Installation orientation]({m['recipe']['navigation']['installation']})"
        f" | [Current recovery authority]({m['recipe']['navigation']['recovery']})"
        f" | [Home]({m['recipe']['navigation']['home']})\n\n"
    )
    output["Fedora-Recipe.md"] = banner.encode() + recipe_body(snapshot.read(RECIPE_PATH), m["recipe"])
    navigation = []
    for group in ("Start", "Operate", "Develop", "Resources"):
        navigation.append(f"### {group}\n")
        pages = [p for p in m["pages"] if p["section"] == group]
        if group == "Start":
            pages.append(m["recipe"])
        navigation.extend(f"- [{p['title']}]({WIKI_URL}/{p['target'][:-3]})\n" for p in pages)
        navigation.append("\n")
    output["_Sidebar.md"] = "".join(navigation).encode()
    output["_Footer.md"] = (
        f"{mode}[Source commit {snapshot.commit}]({REPO_WEB}/commit/{snapshot.commit})"
        f" | [Repository]({REPO_WEB})"
        f" | [Human authorship and LLM policy]({REPO_WEB}/blob/{snapshot.commit}/LLM-POLICY.md)\n"
    ).encode()
    return m, output
