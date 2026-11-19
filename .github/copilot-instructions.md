# Agent-assisted contribution policy

Read [AGENTS.md](../AGENTS.md) and the [LLM policy](../LLM-POLICY.md) before
working on contributions. They provide the tool-independent requirements for
human authorship, review, attribution, sign-off, and publication.

# Repository purpose

This repository is a lightweight public collection of what the maintainer
learns and does with the **SpacemiT K3-CoM260**. It shares and maintains
practical notes, hardware findings, firmware and OS bring-up work, recovery
procedures, scripts, and patches. Keep organization and workflows
proportionate to this informal, evolving collection.
The root `README.md` introduces the resource and links to its documentation
and tools.

Give shared scripts and patches enough board-specific context to be reusable:
their purpose, applicable hardware/software versions, usage or application
steps, and what was actually tried. For patches, identify the target project
and revision when known.

The project will also have a GitHub wiki, which the maintainer will frequently
maintain via `gh`. Treat the wiki as part of the public documentation, not just
the files in this checkout. For documentation tasks, establish whether the
target is the wiki or repository files, and keep overlapping facts and
procedures consistent. Prefer the maintainer's `gh`-based workflow for wiki
work; inspect available commands and extensions before assuming a
wiki-specific command exists.

Keep module-level facts separate from carrier-specific details: the existing
recovery-header pin assignments and procedures describe the Firefly carrier.
Do not generalize results to other K3 modules or carriers without evidence.
Hardware findings should identify the relevant carrier and firmware/image
version and distinguish observed results, vendor guidance, and untested ideas.
Public instructions must not depend on unpublished notes or files elsewhere
on the maintainer's machine.

# Fedora developer wiki

`wiki/` is the canonical public wiki source; `tools/wiki/README.md` documents
its manifest, generated historical recipe, validation and publication
workflow. Preserve `k3-com260-fedora-howto/` unchanged. The GitHub Wiki is a
separate checked projection, not an independently edited source of truth.
`wiki/Fedora-45-Recipe.md` is the maintained F45 command source, backed by
`fedora-45/` helpers, pins, and results. Keep the retained F44 recipe and guest
results explicitly archived; they are not F45 guest evidence or prerequisites.
The two-partition volume installation was recorded end to end on 2026-10-20;
other fresh-install adaptations (partition creation, other maintenance hosts,
whole-disk imaging) stay visibly unverified until an attended result
establishes them. Fan control is covered only by the pinned 7.3.0 upgrade
(COPR build 11177969) and its recorded single-boot result.
Run the local validation gate before the relevant content or wiki push, and
require explicit human publication approval. Neither a source commit nor a
successful check authorizes a wiki push or new hardware result.

# Board tools in k3-tools

The Bianbu factory-flashing script and k3ctl moved to the public
`xjamesmorris/k3-tools` repository, with their history, on 2026-11-19. Its
own agent instructions carry the flashing tool's architecture, commands and
invariants; make tool changes there. `tools/README.md` and
`tools/k3ctl/README.md` here are only pointers, kept because published pages
and other projects link to them, and `tools/k3ctl/.gitignore` keeps existing
checkouts' build and cache files ignored. `tools/wiki/` stays: it validates
and publishes this repository's wiki.

Wiki pages and the README link to the k3-tools documentation with full
`https://github.com/xjamesmorris/k3-tools/...` URLs. The wiki gate checks
those only for availability, not their anchors or content, so keep facts
that appear in both repositories consistent by review. Factory flashing
erases NOR firmware and all UFS contents; never use it, or any other board
action, as an automated check.
