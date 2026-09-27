<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Agent-assisted contributions

This is the entry point for external agents assisting a human contributor,
regardless of the tool or provider. Before working, read the
[project overview](README.md), [LLM policy](LLM-POLICY.md), and
[shared project and flashing guidance](.github/copilot-instructions.md).

## Human ownership

An LLM is a tool, not an autonomous contributor or maintainer. The human is
the author responsible for reviewing, understanding, and publishing the
assisted material. Prepare work for that review; generated code or another
agent's approval does not replace it. Follow the LLM policy's disclosure,
sign-off, and publication requirements.

## Working in this repository

- Keep changes proportionate to this informal collection of K3-CoM260 notes,
  hardware findings, how-tos, scripts, and patches. Flashing is one component,
  not the project's entire purpose.
- Check the branch and worktree before editing. Preserve unrelated changes,
  and stay within the human contributor's requested scope.
- Establish whether documentation belongs in repository files or the public
  wiki. Keep overlapping instructions consistent, and use public sources
  rather than depending on unpublished files on an operator's machine.
- Preserve recorded bring-up observations. Do not rewrite tested procedures,
  workarounds, release pins, or hardware results based on speculation.
  Distinguish observations, vendor guidance, and untested ideas.
- Identify the module, carrier, firmware or image version, and what was
  actually tried. Firefly carrier wiring and results must not be generalized
  to other carriers without evidence.
- Preserve imported patch authorship, licenses, trailers, and provenance.
  Identify the target project and revision; do not alter pinned patch bytes
  merely to satisfy formatting checks.

## Validation and safety

Use the relevant existing checks and report their limits. For modified Bash
scripts, run `bash -n` and `shellcheck`; consult [tools/README.md](tools/README.md)
for flashing-tool requirements. Do not equate syntax checks, hashes, or patch
replay with successful hardware operation.

Never flash a board, overwrite a disk, change its boot environment, or reboot
it as an automated contribution check. Such work needs the human operator's
explicit approval and supervision. The flashing tool's `--check` can download
and extract large images; it is not a side-effect-free command preview.

## Handoff

Give the human author the changed paths, a reviewable diff, the checks
actually performed, and any unresolved questions or untested behavior.
Never invent observations, test results, citations, or human endorsements.
Leave publication to the human author as required by the LLM policy.

## Fedora developer wiki

Canonical public pages live in `wiki/`. Read the
[wiki maintenance contract](tools/wiki/README.md) before editing them.
The historical `k3-com260-fedora-howto/` is protected; its wiki reference is
generated, not a second hand-maintained installation recipe.

Document only the Linux-workstation procedures actually performed. Keep
bootstrap, source-built host, and persistent guest results separate. Other
platforms, newer images and unperformed experiments may be linked as
resources, not presented as tested walkthroughs.

Validate the exact proposed snapshot before a push. Content-repository and
wiki pushes are separate human-authorized actions; never enable the wiki,
alter its permissions or publish as a side effect of writing documentation.
Private source notes and session reports are not publication inputs.

The `wiki-curator` and `wiki-reviewer` profiles are read-only. They propose
and evaluate changes; they do not edit, schedule work or publish autonomously.
