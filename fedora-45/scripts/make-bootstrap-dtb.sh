#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -Eeuo pipefail
set -x

usage()
{
	cat <<'EOF'
Usage: make-bootstrap-dtb.sh PACKAGED_DTB OUTPUT_DTB

Create the separately named K3-CoM260 bootstrap DTB used by the Fedora 45
route. The helper copies PACKAGED_DTB and adds an empty regulator-always-on
property to the unique dldo4 node and to the root-level /hub-reset node.
PACKAGED_DTB is never modified.

OUTPUT_DTB is published only if decompiling the copy before and after the
edit shows exactly those two added lines, with nothing removed or changed.
OUTPUT_DTB and OUTPUT_DTB.partial must not exist, and OUTPUT_DTB's parent
must exist. A packaged DTB that already has either property, lacks either
node, or has more than one dldo4 node is refused. Cooling-fan I2C changes
are deliberately not made.

Requires Python 3, dtc, fdtget and fdtput. No disk, package or boot state is
changed.
EOF
}

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
	usage
	exit 0
fi
[[ $# -eq 2 ]] || { usage >&2; exit 2; }
for tool in python3 dtc fdtget fdtput; do
	command -v "$tool" >/dev/null || {
		printf 'error: Required command not found: %s\n' "$tool" >&2
		exit 1
	}
done

python3 -I -B - "$@" <<'PY'
import difflib
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys

PROPERTY = "regulator-always-on"


class Error(Exception):
    pass


def run(*args):
    result = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if result.returncode:
        raise Error(f"{args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def children(dtb, node):
    return run("fdtget", "-l", dtb, node).splitlines()


def properties(dtb, node):
    return run("fdtget", "-p", dtb, node).splitlines()


def find_dldo4(dtb):
    pending, found = ["/"], []
    while pending:
        node = pending.pop()
        if node.rsplit("/", 1)[-1] == "dldo4":
            found.append(node)
        pending.extend(
            node.rstrip("/") + "/" + child for child in children(dtb, node)
        )
    if len(found) != 1:
        raise Error("expected exactly one node named dldo4")
    return found[0]


def decompile(dtb):
    return run("dtc", "-q", "-I", "dtb", "-O", "dts", dtb).splitlines()


def changed_lines(before, after):
    added, removed = [], []
    for line in difflib.unified_diff(before, after, lineterm="", n=0):
        if line.startswith(("---", "+++", "@@")):
            continue
        if line.startswith("+"):
            added.append(line[1:].strip())
        elif line.startswith("-"):
            removed.append(line[1:])
    return added, removed


def main(input_arg, output_arg):
    output_arg = Path(output_arg)
    parent = output_arg.parent.resolve(strict=True)
    output = parent / output_arg.name
    partial = Path(str(output) + ".partial")
    for path in (output, partial):
        if os.path.lexists(path):
            raise Error("output or partial file already exists")

    fd = os.open(input_arg, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise Error("PACKAGED_DTB must be a regular non-symlink file")
        data = stream.read()

    owned = False
    try:
        out_fd = os.open(
            partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        owned = True
        with os.fdopen(out_fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        work = str(partial)
        dldo4 = find_dldo4(work)
        if "hub-reset" not in children(work, "/"):
            raise Error("root-level /hub-reset node is missing")
        nodes = (dldo4, "/hub-reset")
        for node in nodes:
            if PROPERTY in properties(work, node):
                raise Error(f"{node} already has {PROPERTY}; unexpected input")
        before = decompile(work)
        for node in nodes:
            run("fdtput", work, node, PROPERTY)
        for node in nodes:
            if (
                PROPERTY not in properties(work, node)
                or run("fdtget", work, node, PROPERTY).strip()
            ):
                raise Error(f"{PROPERTY} is not an empty property of {node}")
        added, removed = changed_lines(before, decompile(work))
        if removed or added != [PROPERTY + ";", PROPERTY + ";"]:
            raise Error(
                "the edited DTB differs by more than the two expected properties"
            )
        os.chmod(partial, 0o644)
        with open(partial, "rb") as stream:
            result = stream.read()
            os.fsync(stream.fileno())
        # link() publishes without replacing an output created meanwhile.
        os.link(partial, output, follow_symlinks=False)
    finally:
        if owned:
            partial.unlink(missing_ok=True)

    print("dldo4 node:         ", dldo4)
    print("Packaged SHA-256:   ", hashlib.sha256(data).hexdigest(),
          f"({len(data)} bytes)")
    print("Bootstrap SHA-256:  ", hashlib.sha256(result).hexdigest(),
          f"({len(result)} bytes)")


try:
    main(*sys.argv[1:])
except (Error, OSError, UnicodeError) as exc:
    print(f"error: {exc}", file=sys.stderr)
    sys.exit(1)
PY
