<!-- SPDX-License-Identifier: GPL-2.0-only -->

# LLM contribution policy

This project conforms to the Linux kernel's LLM policy, and all contributions
must conform to it. This includes code, scripts, patches, documentation, wiki
content, reviews, and contribution messages.

The authoritative upstream guidance is:

- [AI Coding Assistants](https://docs.kernel.org/process/coding-assistants.html)
- [Kernel Guidelines for Tool-Generated Content](https://docs.kernel.org/process/generated-content.html)

These documents were consulted on September 26, 2026. Follow their current
requirements; the project guidance below supplements, rather than replaces
or relaxes, them.

## The human is the author

In this project, an LLM is simply a tool utilized by a human. The human is
ultimately the author and is responsible for reviewing, understanding, and
publishing all LLM-assisted material.

The author must understand the entire contribution, check its correctness
and provenance, validate it appropriately, and be able to explain it and
respond to review. Do not submit material you cannot understand or defend.
An LLM's output, confidence, or review is not a substitute for human judgment.
Attributing assistance to a tool does not transfer authorship or responsibility
to that tool.

## Disclosure and provenance

Disclose meaningful LLM assistance in the contribution description or
changelog: which tools were used, what they assisted with, and how the result
was checked. Include relevant short prompts or a summary of a longer session
when useful to review, without exposing private information.

For substantive LLM-assisted commits or patches, include the upstream
attribution trailer:

```text
Assisted-by: LLM
```

The upstream format permits additional specialized analysis tools on that
line. Ordinary build tools and editors do not belong there. The upstream
guidelines exclude trivial mechanical assistance such as spelling fixes and
formatting; when uncertain, disclose the assistance.

Respect the repository's licensing requirements and preserve source
attribution, licenses, and existing patch provenance. LLM use does not waive
these obligations or establish permission to copy material.

## Human sign-off and publication

Only a human can certify the Developer Certificate of Origin through a
`Signed-off-by` trailer. Agents must not add one, including on a human's behalf.
The human submitter supplies their own sign-off after review and only when
they can make that certification. Preserve existing genuine sign-offs in
imported material.

Agents prepare drafts for the human author; they must not independently
publish contributions, submit patches or reports, send email, or post review
comments. The human author reviews the final material and controls its
publication. In particular, upstream kernel reports and submissions must be
sent by the human, not by the assistant.

Be explicit about untested behavior, failed checks, and missing evidence.
Hardware observations must identify the relevant board and software; never
present an inference or an agent-generated claim as a measured result.
