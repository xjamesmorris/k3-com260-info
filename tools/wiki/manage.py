#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Local authoring checks and explicitly human-invoked wiki publication."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).absolute().parent))

import content as c
import checks
import publication as p
import storage as s


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "render"):
        command = commands.add_parser(name)
        choice = command.add_mutually_exclusive_group(required=True)
        choice.add_argument("--worktree", action="store_true")
        choice.add_argument("--ref")
        if name == "validate":
            command.add_argument("--offline", action="store_true", required=True)
        else:
            command.add_argument("--output", required=True, choices=[s.BUILD])
    command = commands.add_parser("check-links")
    command.add_argument("--ref", required=True)
    command = commands.add_parser("prepare")
    command.add_argument("--source", required=True)
    prior = command.add_mutually_exclusive_group()
    prior.add_argument("--adopt-bootstrap")
    prior.add_argument("--reconcile-web-tip")
    command = commands.add_parser("publish")
    command.add_argument("--receipt", required=True, type=Path)
    command.add_argument("--expect-receipt", required=True)
    command = commands.add_parser("install-hook")
    command.add_argument("--ref", required=True)
    command = commands.add_parser("content-pre-push")
    command.add_argument("--trust-ref", required=True)
    command.add_argument("--remote-name", required=True)
    command.add_argument("--remote-url", required=True)
    command = commands.add_parser("hook")
    command.add_argument("--bundle", type=Path, required=True)
    command.add_argument("remote_name")
    command.add_argument("remote_url")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        c.parser()
        root = Path(c.Git(Path.cwd()).run("rev-parse", "--show-toplevel").decode().strip())
        if args.command in ("validate", "render"):
            snapshot = c.Snapshot(root, args.ref or "HEAD", worktree=args.worktree)
            p.tool_identity(snapshot)
            checked = checks.validate(snapshot, today=p.utc_day())
            if args.command == "render":
                s.preview(root, checked.output, args.output)
                print("Rendered exact managed preview in .wiki-build; this is not publication approval.")
            else:
                mode = "worktree (not publishable)" if args.worktree else snapshot.commit
                print(f"Offline validation passed: {mode}; {len(checked.output)} output pages.")
        elif args.command == "check-links":
            print(c.canonical(p.check_links(root, args.ref)).decode(), end="")
        elif args.command == "prepare":
            path, digest = p.prepare(root, args.source, args.adopt_bootstrap, args.reconcile_web_tip)
            print(f"Prepared receipt SHA256: {digest}\nReview: {path.relative_to(root).as_posix()}")
        elif args.command == "publish":
            result = p.publish(root, args.receipt, args.expect_receipt)
            print("Wiki " + result + "; inspect GitHub Wiki rendering as the human follow-up.")
        elif args.command == "install-hook":
            p.install_hook(root, args.ref)
            print("Installed repository-local immutable validator hook; no push was performed.")
        elif args.command == "content-pre-push":
            snapshot = c.Snapshot(root, args.trust_ref)
            trust = {
                "source": snapshot.commit,
                "identities": p.bind_running_tool(snapshot),
                "runtime": p.runtime_identity(),
            }
            p.content_pre_push(root, sys.stdin.buffer.read(65537), args.remote_name, args.remote_url, trust)
            print("Proposed content refs and newly reachable history passed the local gate.")
        elif args.command == "hook":
            trust = p.read_bundle(args.bundle)
            c.require(Path(__file__).absolute().parents[2] == args.bundle, "hook did not execute its bound tool bundle")
            if args.remote_url == c.WIKI_REPO:
                p.wiki_pre_push(root, sys.stdin.buffer.read(65537), args.remote_name, args.remote_url)
            else:
                p.content_pre_push(root, sys.stdin.buffer.read(65537), args.remote_name, args.remote_url, trust)
        return 0
    except c.Invalid as exc:
        print("wiki: " + str(exc), file=sys.stderr)
        return 1
    except (OSError, UnicodeError, KeyError, TypeError, ValueError):
        print("wiki: malformed input or unavailable local resource; inspect the documented schema/setup "
              "(untrusted data suppressed).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
