# SPDX-License-Identifier: GPL-2.0-only
"""Small no-follow filesystem operations for the two named generated locations."""

from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import stat
import uuid

import content as c

BUILD = ".wiki-build"
PUBLISH = ".wiki-publish"


@contextmanager
def directory(root: Path, relative: str = "", *, create: bool = False):
    parts = c.safe_path(relative).split("/") if relative else []
    fd = c.open_directory(root)
    try:
        for part in parts:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        yield fd
    except OSError:
        raise c.Invalid("unsafe, missing, or inaccessible output directory; inspect named generated locations") from None
    finally:
        os.close(fd)


def regular_names(root: Path) -> set[str]:
    with directory(root) as fd:
        names = set(os.listdir(fd))
        for name in names:
            mode = os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode
            c.require(stat.S_ISREG(mode), "output contains a directory, symlink, or special file")
            c.safe_path(name)
        return names


def write(root: Path, name: str, data: bytes, *, replace: bool = False, mode: int = 0o644) -> None:
    c.require("/" not in c.safe_path(name), "write requires an explicit direct child")
    temporary = ".partial-" + uuid.uuid4().hex
    with directory(root) as fd:
        if name in os.listdir(fd):
            entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
            c.require(replace and stat.S_ISREG(entry.st_mode) and entry.st_nlink == 1,
                      "refusing an existing, linked, or non-regular output")
        child = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=fd)
        try:
            with os.fdopen(child, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
            os.fsync(child)
            os.fchmod(child, mode)
            if replace:
                os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
            else:
                # link+unlink provides no-clobber publication of the completed regular file.
                os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
                os.unlink(temporary, dir_fd=fd)
            os.fsync(fd)
        except FileExistsError:
            raise c.Invalid("output appeared concurrently; refusing to overwrite it") from None
        finally:
            os.close(child)
            if temporary in os.listdir(fd):
                os.unlink(temporary, dir_fd=fd)


def unlink_verified(root: Path, name: str, expected_sha: str) -> None:
    c.require("/" not in c.safe_path(name), "deletion requires a named direct child")
    c.require(c.sha256(c.regular_read(root, name)) == expected_sha,
              "managed deletion target was edited; refusing to remove it")
    with directory(root) as fd:
        info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        c.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "managed deletion target is linked")
        os.unlink(name, dir_fd=fd)
        os.fsync(fd)


def tree_record(output: dict[str, bytes]) -> dict:
    entries = {}
    raw = bytearray()
    for name, data in sorted(output.items()):
        c.require(c.SLUG_RE.fullmatch(name) or name in ("_Sidebar.md", "_Footer.md"), "invalid output name")
        oid = c.blob_id(data)
        entries[name] = {"mode": "100644", "blob": oid, "sha256": c.sha256(data), "size": len(data)}
        raw.extend(b"100644 " + name.encode("ascii") + b"\0" + bytes.fromhex(oid))
    import hashlib
    tree = hashlib.sha1(b"tree " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    return {"git_tree": tree, "files": entries}


def read_tree(root: Path, record: dict) -> dict[str, bytes]:
    c.object_keys(record, {"git_tree", "files"})
    c.require(isinstance(record["files"], dict), "invalid output inventory")
    c.require(regular_names(root) == set(record["files"]), "prepared output inventory changed")
    result = {}
    for name, expected in record["files"].items():
        c.object_keys(expected, {"mode", "blob", "sha256", "size"})
        data = c.regular_read(root, name)
        c.require((root / name).lstat().st_mode & 0o777 == 0o444, "prepared pages must remain read-only regular files")
        result[name] = data
    c.require(tree_record(result) == record, "prepared output bytes or tree identity changed")
    return result


def preview(root: Path, output: dict[str, bytes], destination: str) -> None:
    c.require(destination == BUILD, "render --output must be exactly .wiki-build")
    with directory(root, BUILD, create=True):
        pass
    build = root / BUILD
    state_name = ".preview.json"
    old = {"files": {}}
    if state_name in os.listdir(build):
        old = c.load_json(c.regular_read(build, state_name), "preview state")
        c.object_keys(old, {"git_tree", "files"})
    new = tree_record(output)
    allowed = set(old["files"]) | set(output) | {state_name, "prepared", "tests"}
    c.require(set(os.listdir(build)) <= allowed, "unmanaged .wiki-build entry; preserve it and reconcile explicitly")
    for name in set(old["files"]) | set(output):
        path = build / name
        if path.exists() or path.is_symlink():
            data = c.regular_read(build, name)
            c.require(not path.lstat().st_mode & 0o111, "executable preview page")
            permitted = {entry["sha256"] for entry in (old["files"].get(name), new["files"].get(name)) if entry}
            c.require(c.sha256(data) in permitted, "preview output was edited; refusing to overwrite it")
            # An interrupted previous render can contain either the old or the desired bytes.
            if data == output.get(name):
                continue
            if name not in old["files"]:
                raise c.Invalid("unmanaged preview collision")
        if name in output:
            write(build, name, output[name], replace=path.exists())
        else:
            c.require(not path.exists(), "preview has a removed managed page; inspect and remove that named preview file explicitly")
    write(build, state_name, c.canonical(new), replace=state_name in os.listdir(build), mode=0o600)
