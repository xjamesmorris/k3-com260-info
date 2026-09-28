<!-- SPDX-License-Identifier: GPL-2.0-only -->

# Maintaining the Fedora developer wiki

`wiki/` is the curated public source. GitHub Wiki is a separately published
projection, not another editing workspace. These tools prepare work for the
human author under [LLM-POLICY.md](../../LLM-POLICY.md); passing checks does
not authorize a push or certify a hardware result.

The recorded hardware is the Firefly-carrier K3-CoM260. The protected
September 25, 2026 Fedora/KVM how-to remains the command authority. Nothing
here executes its Markdown, shell, U-Boot, disk-writing, or guest commands.

## Local setup

Use Linux, system-installed Git and GitHub CLI at `/usr/bin/git` and
`/usr/bin/gh`, and Python 3.10 or newer. `glow` is optional for rendered
Markdown review; `cat` is the no-`glow` fallback. The implementation needs
POSIX no-follow directory/file operations and an ordinary full-history source
checkout, not a shallow clone. There is no site generator or test framework.
Run all commands below from the repository root.

```sh
/usr/bin/git --version
/usr/bin/gh --version
/usr/bin/env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN \
  -u GITHUB_ENTERPRISE_TOKEN /usr/bin/gh auth status --hostname github.com

# If no suitable github.com login is present, authenticate interactively.
/usr/bin/env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN \
  -u GITHUB_ENTERPRISE_TOKEN \
  /usr/bin/gh auth login --hostname github.com --git-protocol https --web

python3 -m venv .wiki-venv
.wiki-venv/bin/python -m pip install --only-binary=:all: --require-hashes \
  -r tools/wiki/requirements.txt
.wiki-venv/bin/python -B -m unittest discover -s tools/wiki/tests -p test_wiki.py -v
.wiki-venv/bin/python -B tools/wiki/manage.py validate --worktree --offline
```

`requirements.txt` pins `markdown-it-py==4.2.0` and its only required
dependency, `mdurl==0.1.2`, to the pure-Python wheel SHA256 values reported by
official PyPI on September 27, 2026. Only those wheels are accepted. Review
the [parser release metadata](https://pypi.org/pypi/markdown-it-py/4.2.0/json)
and [dependency metadata](https://pypi.org/pypi/mdurl/0.1.2/json) when updating
the lock; also update the expected versions in `content.py`, run the
fixtures, and obtain a new tool review. Do not install packages globally.

The hook never installs dependencies. A missing/wrong parser or changed
installed parser bytes blocks it with a setup diagnostic. Receipts and hook
bundles also bind the Python version and verified installed Python-module
hashes against wheel `RECORD` entries. They additionally bind `/usr/bin/git`
and `/usr/bin/gh` by absolute path, streamed SHA256, size, ownership, mode,
and root-owned non-writable ancestor identity. The tools never select either
executable from ambient `PATH`; a package, path, owner, mode, or ancestor
change requires a fresh validation, hook installation, and preparation. Hook
installation records the active Python prefix's `bin/python` launcher when it
resolves to the running interpreter, preserving the hash-locked virtual
environment path even if Python reports its base executable. The local
interpreter/environment remains part of the human's trust boundary, not a
remotely attested runtime. Use `-B` to avoid untracked `__pycache__` files in
the tool inventory.

`gh auth status` checks the GitHub CLI's stored login; it does not verify the
credential mechanism that the human will use for the separate canonical
source push. `gh auth login` opens the selected login flow, records the
GitHub-host/protocol choice, and stores the token in the system credential
store when available, with a documented plain-text fallback if secure storage
is unavailable. Inspect the location reported by `gh auth status`. Neither
command pushes or approves anything. If the human deliberately wants GitHub
CLI to configure Git credentials for the manual canonical source push, run
`/usr/bin/gh auth setup-git --hostname github.com` and review that separate
Git-configuration side effect.

The publisher does not use `gh auth token`, place a token in Git arguments or
environment variables, or fall back to ambient/system/global Git credential
configuration. Public source/wiki `ls-remote` and fetch operations remain
anonymous. Only the final approved wiki push receives an in-memory,
`https://github.com`-scoped helper command built from the verified executable:
`!/usr/bin/gh auth git-credential`. The empty `credential.helper` reset still
precedes it, and the push continues to run the installed hook. This helper is
never supplied to the canonical source push or to anonymous reads. Check
authentication with the token-unset command above before preparing and again
before an approved publication if authentication may have changed.

Only `.wiki-venv/`, `.wiki-build/`, and `.wiki-publish/` are generated
top-level locations. Tests create and clean individually named temporary
fixtures inside `.wiki-build/tests/`. They use reserved example identities,
mock HTTPS/DNS, and local bare Git remotes; they never contact or push GitHub.

## Publication quick path

1. Edit the canonical `wiki/`, manifest, validator, tests, profiles, and
   documentation; run the offline validation and render review below.
2. Human-review the complete result and commit the full wiki/tool snapshot
   atomically as one local commit. Do not create an intermediate public commit
   with only part of the validator or content.
3. Install the immutable hook from that reviewed commit, then obtain separate
   approval and push that exact canonical source commit.
4. For first publication, verify collaborator-only editing and the existing
   exact root Home bootstrap; never web-edit it again.
5. Prepare from the public source commit, review the receipt/report/tree, then
   obtain separate approval for the exact receipt and publish it.
6. Let the publisher complete its mandatory remote read-back, then inspect the
   rendered GitHub Wiki in the browser.

The sections below are authoritative for commands, stop conditions, and
recovery; this list does not replace them.

## Authoring and exact snapshots

```sh
# New/untracked manifest-listed pages are permitted for authoring only.
.wiki-venv/bin/python -B tools/wiki/manage.py validate --worktree --offline
.wiki-venv/bin/python -B tools/wiki/manage.py render --worktree --output .wiki-build

# After the human has reviewed and committed the canonical changes:
.wiki-venv/bin/python -B tools/wiki/manage.py validate --ref HEAD --offline
.wiki-venv/bin/python -B tools/wiki/manage.py render --ref HEAD --output .wiki-build
glow -p .wiki-build/Home.md
glow -p .wiki-build/Fedora-Recipe.md
```

`glow` is only a convenience. If it is not installed, review the same exact
files with `cat .wiki-build/Home.md` and
`cat .wiki-build/Fedora-Recipe.md`.

Committed mode reads exact Git objects at the resolved commit, not the
index, current `HEAD` content, or an unrelated working file. Worktree mode
has an explicit nonpublication banner and is never accepted by the publisher.
Both modes check the whole protected how-to tree, exact page/tool inventories
and modes, parsed links, local anchors, context fields, exception schemas,
and suspected private data. Neither offline mode establishes external
availability or supplies the required human semantic/privacy/licensing review.

`render --output` accepts **only `.wiki-build`**. The preview owns its
manifest-listed Markdown and `.preview.json`; `prepared/` and `tests/` are
separate named subdirectories. It refuses symlinks, unrelated entries,
executable pages, and edited previews. A retry can recognize its own old or
desired bytes after an interrupted render. It does not delete dropped
preview pages: inspect and remove that exact obsolete preview file yourself.
It never writes into the protected how-to or arbitrary output directories.

## Manifest and content schema

`manifest.json` is schema 1. The executable contract rejects unknown keys,
duplicate JSON keys, duplicate/case-colliding pages, path traversal, symlinks,
executable Markdown, missing files and unlisted publication files.
There are no copied binary assets in this version.

| Field | Contract |
| --- | --- |
| `repository`, `source_branch` | Exact `https://github.com/xjamesmorris/k3-com260-info.git`, `refs/heads/main`. |
| `wiki_repository`, `wiki_url` | Exact `.wiki.git` HTTPS origin and canonical GitHub Wiki page base. |
| `baseline_commit`, `protected` | Approved public baseline commit and complete historical how-to tree; also pinned in the validator. |
| `pages[]` | `source`, `target`, `title`, `section`, `kind`; source must be exactly `wiki/TARGET.md`. ASCII hyphenated slugs are case-sensitive. |
| `section` | `Start`, `Operate`, `Develop`, or `Resources`; sidebar order follows the manifest. |
| `kind` | `landing`, `procedure`, `reference`, or `resources`. Only the last can receive resource-link availability exceptions. |
| `recipe` | The single protected input, its Git blob/SHA256, destination, title/group, enumerated link transforms, checkout-line transform, and exact generated navigation to installation, maintained recovery, and Home. |
| `critical_artifacts` | Exactly the `omni-bootstrap` and `fedora-guest` records: `id`, `url`, `sha256`, `checksum_url`, and `source` with exact protected `path`/`blob`. Both images and sidecars are mandatory publication checks. |
| `bootstrap_home` | Exact reviewed UTF-8 initial Home bytes: nonempty, LF-terminated, without CR/NUL, and under 4 KiB; approved for one-time adoption. |
| `validation_exceptions` | Exact source-bound review allowances described below; empty by default. |

The output is precisely the authored targets, `Fedora-Recipe.md`,
`_Sidebar.md`, and `_Footer.md`. Patch files stay in the content repository.
No private intake directory, arbitrary include or recursive mirror is a
publisher input. Source scripts are never executed or copied into the wiki;
the guest preparer's explicitly pinned public blob is read only to verify
its declared default image/checksum constants.

Each authored page begins with an H1 and these visible, non-code fields:

```text
**Applies to:** Relevant module/carrier and stack, or reference-only scope.
**Evidence:** Recorded public result, upstream/vendor reference, or untested idea.
**Source review:** YYYY-MM-DD.
**Hardware observation:** Date and scope, or not performed / not applicable / unknown.
**Destructive operations:** Affected storage/actions, or none on this page.
```

Dates must be real and not in the future on the UTC check date. Procedure
pages need meaningful applicable hardware/stack and destructive scope.
Resource pages can say `not applicable`; do not invent a hardware date.
The generated recipe retains its historical banner and snapshot table rather
than imposing new fields on the protected source.

All authored pages need canonical wiki navigation. Use full
`https://github.com/xjamesmorris/k3-com260-info/wiki/Slug#heading` links:
the manifest and parsed headings resolve them locally, even before the page
exists online. Duplicate headings receive GitHub-style numeric suffixes.
Use ordinary Markdown, including reference-style links, not raw HTML or
images. Only HTML comments are accepted.

This repository's code/patch links must use public `blob/main/PATH`,
`tree/main/PATH`, or exact commit URLs. `main` resolves against the selected
snapshot; a pinned link resolves against its specified local Git commit.
Markdown fragments and source line ranges are checked there, not by a blind
request to whichever `HEAD` a website currently serves. Other public HTTPS
links are availability inputs at publication. Missing local pinned objects
need deliberate read-only retrieval/review, not a fallback to working `HEAD`.

The KVM page must keep the per-result table columns: result, host kernel,
QEMU, guest, CPU filter, PLIC/AIA, vCPUs, storage/persistence, network, public
source, and nonclaims. Recorded Fedora 44 rows on the pinned host retain
the four-vCPU CPU-filter settings. The contribution page must retain the
worked dldo4 RFC and Fedora guest report headings and artifact checklists.
These are structural guards, **not proof of the claims in the cells**.
The three evidence stages, missing per-mode checks, observed versus
reference-only results, and destination submission policies still need
human review.

## Generated recipe: exact permitted changes

The protected source is
`k3-com260-fedora-howto/README.md`, at public baseline
`57400da095e944c75e63154b1c187e18a3ac3359`. Its full directory must keep tree
`db99cfb1555592c097e4c283b488149067ebea7b`; the manifest also records the
recipe's blob and SHA256.

Only these adaptations are allowed:

1. Prepend the fixed historical/reference and source-commit banner, including
   the manifest-bound link to the maintained Console-and-Recovery authority.
   Generate sidebar/footer from the manifest and bound source commit. The
   protected body's pinned flashing-document link remains historical
   provenance, not the current recovery command authority.
2. Relocate the two manifest-enumerated Markdown destinations to exact
   baseline repository URLs, with the required parsed-link counts.
3. Change the one exact shell line
   `export HOWTO="$WORK/k3-com260-info/docs/k3-fedora-howto"` to
   `export HOWTO="$WORK/k3-com260-info/k3-com260-fedora-howto"`.
   This is the correction already documented in the root README.

The parser locates destination edits by checking the parsed structure before
and after each candidate substitution, including reference definitions.
It does not serialize or reflow Markdown. Link-shaped code stays untouched;
an extra parsed match, ambiguous/encoded destination, or missing match
blocks rendering. The checkout correction must be the single complete
expected line inside the recorded shell fence; another occurrence fails.
All remaining bytes, line endings, code fences, command text and limitations
are preserved. The fidelity tests compare the complete body and every fence.
A baseline refresh is a separate reviewed tool/manifest decision.

## Critical installation images and checksum metadata

The manifest explicitly enumerates both recorded install images, independently
of Markdown hyperlinks or the generated page's code blocks:

| Critical input | Protected public pin source |
| --- | --- |
| Fedora 44 Omni `Fedora-Server-Host-Omni-44-20260731.0.riscv64.raw.xz` | The original recipe blob, including its repeated SHA256 checks. |
| Full Fedora guest `Fedora-Cloud-Base-Generic-44-20260604.0.riscv64.qcow2` | The exact protected `scripts/prepare-riscv-fedora-guest.sh` blob and its default image, SHA256 and checksum-URL constants. |

Each record must retain its exact protected source path/blob; the URL/hash
must match that source and the checksum URL must be the named image's
`.sha256` sidecar. Missing/duplicate records, changed pins, arbitrary source
paths or substituted metadata URLs fail offline validation. The guest helper
is a validation-only source, not an additional generated-reference include.

Preparation, publication rechecks, and the manual report-only checker always
include these four critical requests. Image availability uses HEAD only,
including after redirects; it never falls back to GET. Each explicit sidecar
gets a bounded GET and must contain exactly one GNU-style SHA256 record for
the expected image basename, with the hash matching the protected pin.
The cap is **4 KiB encoded and decompressed**. Missing, malformed, duplicate,
wrong-filename or mismatched checksum records block the gate.

The official sidecars can advertise `application/octet-stream` or
`application/x-xz` despite containing short ASCII checksum records. Only
this explicit sidecar operation permits those MIME types: it still enforces
the small bound, exact `.sha256` filename, redirect/DNS/TLS checks and strict
record parser. It cannot follow a metadata redirect to an image/model URL.
There is no generic binary-body GET exception.

Neither a RESOURCE availability exception nor a duplicate link on a resource
page can waive a critical image or its checksum metadata. Reports identify
the required filename, expected image SHA256 and checksum-match result.
These are source pins and online metadata comparisons, **not newly computed
image hashes or hardware results**. The publisher does not download/re-hash
the multi-GB images or verify detached signatures; the installation recipe
and guest preparer still verify the actual downloaded bytes against their
pinned SHA256 values before use.

## Privacy and reviewed exceptions

The scanner flags credential-shaped values, private-key headers, credential
URLs/query parameters, operator home paths, private-source locators, private
IPv4 examples, and UUID-shaped identifiers for review. Findings report only
rule, blob identity and line, never the matched data. Public hashes and
upstream author addresses are not indiscriminately rejected. The complete
approved recipe blob admits its recorded generic Fedora image-account paths;
loopback guest SSH is not treated as a private machine identifier.

These are conservative review aids, not a secret detector or a substitute
for reading every new commit, message, fixture and public output. They cannot
prove human approval, licensing, tested hardware compatibility, or correctness
of a prose claim. Do not place a private identifier list in the public tool.

A stable known-safe occurrence can have a manifest validation exception with
exactly:

```json
{
  "rule": "operator-home",
  "path": "wiki/EXACT-PAGE.md",
  "blob": "EXACT_PUBLIC_SOURCE_GIT_BLOB_OID",
  "match_sha256": "SHA256_OF_THE_EXACT_MATCH_BYTES",
  "line": 1,
  "reason": "HUMAN_REVIEWED_PUBLIC_RATIONALE",
  "reviewer": "ACTUAL_HUMAN_REVIEWER",
  "reviewed": "YYYY-MM-DD",
  "expires": "YYYY-MM-DD"
}
```

This is a **schema illustration, not an approved entry**. The path must be a
public wiki input, the recipe, or a policy JSON input. The rule must be an
implemented privacy rule. Blob, match digest and 1-based line must all match;
an unused, duplicate, moved or stale exception fails. Expiry is optional only
for stable content allowances; add it for volatile allowances. Agents can
propose a need for review, never fill in a fabricated human endorsement.
No exception can waive unsafe paths, recipe integrity, source/tool identity,
remote drift, missing metadata, or incompatible output.

`link-exceptions.json` is a **separate** schema:

```json
{"schema": 1, "exceptions": []}
```

Each real availability entry has exactly `kind` (`resource`), `page`
(manifest destination including `.md`), `url` (the exact HTTPS URL), `reason`,
`reviewer`, `reviewed`, and mandatory `expires`. Dates are `YYYY-MM-DD`;
expiry is inclusive through that UTC date. It must name a currently used
link on a `kind: resources` page. A URL also used as a source or artifact
elsewhere cannot be waived. Missing installation artifacts, Git repositories,
unsafe redirects, private addresses and invalid TLS are not resource outages.
Expired, stale, duplicate or overbroad entries block publication. The report
displays any availability allowance actually used. Both files start empty;
an outage does not authorize an agent to invent a review.

## Bounded external checks

Publication validates parsed Markdown links and bare URL text in prose.
It does not mine inline code, fenced blocks or indented code for network
targets, and never executes examples. The code-only installation images
above enter the gate through the explicit source-bound manifest inventory,
not an arbitrary fence-URL scan. HTTPS is mandatory, with no URL credentials, secret
query fields, custom ports, insecure skip flags, or network overrides.
Reserved example domains are recorded as examples and never requested.
Local/private/loopback, mixed public/private DNS and IPv6 transition
addresses are rejected before connecting. Every redirect is checked again.

DNS runs in a bounded subprocess (5 seconds). A socket connects to the
already validated public numeric IP, while TLS certificate verification and
SNI use the original hostname; a second name lookup cannot rebind the
connection. Requests ignore proxy environment variables. Each request has
an 8-second total socket deadline, at most one retry, three redirects, and
32 KiB accepted headers. There is no unbounded resolver thread.

Ordinary link-availability checks use HEAD. Only a 405/501 on a plausible
text-page path can trigger their GET fallback; its response must be HTML/plain text. Archive, image, disk, repository,
model, PDF, package and similar links never receive that fallback. Text
responses are limited to 128 KiB encoded **and** decompressed; the explicitly
declared checksum-sidecar reader has the stricter 4 KiB limit above. Unsupported
encoding, concatenated gzip streams, excessive bodies and binary responses
fail. No linked binary is downloaded or written to disk.

A server can deny HEAD (including an official source), rate-limit, or return
an inconclusive response. That is reported as **unavailable**, not success.
Availability does not verify artifact checksums, contents, or historical
claims. Production Git operations separately allow only the two literal
public HTTPS repository URLs, enforce TLS/no redirects and bounded Git
timeouts, and reject repository transport rewrites/proxies/helpers. Anonymous
advertisement/fetch operations retain a 90-second bound. The single exact
credentialed wiki push has a ten-minute outer bound because its installed
pre-push hook repeats the receipt's online and remote checks before Git can
send the update; the hook and each underlying operation remain independently
bounded.
Local transports and fake resolvers are Python fixture seams only, not CLI
options.

## Install the reviewed local hook before a content push

Hook installation is a human-approved integration step, not part of authoring
or an implicit effect of `validate`. Run the fixtures and commit the complete
reviewed snapshot locally first: canonical `wiki/`, `tools/wiki/`, the hook,
profiles, and directly related policy/navigation documentation must be one
atomic commit. Do not split that snapshot across intermediate commits, and do
not push it yet.

```sh
.wiki-venv/bin/python -B tools/wiki/manage.py install-hook --ref REVIEWED_TOOL_COMMIT
/usr/bin/git config --local --get core.hooksPath
```

The installer verifies the selected commit against the running tool bytes,
then copies only the explicit tool files **from those Git objects** into
`.git/wiki-validator/.partial-NONCE/`. It verifies the exact recursive
inventory, bytes and modes before and after running the trusted suite from
that staged bundle, never from mutable worktree code. Extra files, empty
directories, bytecode caches, symlinks, hardlinks and incorrect modes fail.
Fixture metadata comes from the selected Git commit. Test output and any
bytecode cache are isolated in an individually cleaned temporary directory
under `.wiki-build/tests/`; the runner uses `-I -B` and an isolated cache
prefix, with a ten-minute suite timeout.

The completed files are read-only (`0444`, or `0555` for hook dispatchers);
directories are sealed to `0555` and fsynced before an atomic rename to
`.git/wiki-validator/HASH/`. The hash binds canonical `bundle.json`, including
the public source/tool identities and local interpreter/runtime binding.
An advisory lock on the bundle-parent directory serializes installers and
is released automatically on exit. Existing final bundles must pass the same
exact verification and trusted tests before reuse. Git configuration changes
only after final verification and another check for existing hooks.

`core.hooksPath` points to the verified bundle's `hooks/`, **not** the branch's
`.githooks/`. Repository-local hook configuration is queried through isolated
Git. Standard system/global config files are inspected only as bounded inert
text for `hooksPath` or include markers; they are never loaded into Git
execution. A possible external hook, an ambiguous config file, and unrelated
active hook files all require explicit human integration and are never
silently overwritten or disabled. An interrupted install leaves at most an
uninstalled `.partial-*` candidate or a complete final bundle, never an
incomplete final-name bundle; retry needs no broad cleanup.

The dispatcher consumes Git's stdin updates and remote name/URL. It validates
the actual proposed commit tips, not checked-out `HEAD`, then walks all newly
reachable commits, messages, modes and blobs relative to freshly advertised
and fetched public heads/tags. It covers multiple branches, zero old OIDs,
non-checked-out tips, merge parents and introduce-then-delete history.
Already public unrelated history is not rescanned. Tag/deletion pushes,
non-fast-forwards, unsupported objects, grafts/shallow history and stale
old-OID advertisements fail explicitly.

The gate executes only the installed trusted test/tool bundle. It never
executes a newly proposed source script or test. Fixture metadata comes from
the trusted tool commit's Git objects, not whichever branch is checked out.
A new validator version,
including an intermediate newly reachable version, must be separately
reviewed and explicitly installed before that content push. Do not use an
unreviewed branch as the hook's executable location.

The trust check also applies when the manifest is absent: a newly reachable
commit containing `.githooks/pre-push` or anything at `tools/wiki`, or removing
those paths from any parent, must retain the manifest and complete trusted
tooling. Temporarily deleting the manifest or all tools and restoring them
at the final tip does not bypass the check, including through merge parents.
Already-public pre-wiki history remains excluded; documentation-only ancestry
with no tooling in the commit or any parent does not require a wiki manifest.

If a separately authorized preinstallation push is necessary, the equivalent
explicit interface is:

```sh
# Feed the same four-field updates Git supplies to pre-push.
.wiki-venv/bin/python -B tools/wiki/manage.py content-pre-push \
  --trust-ref REVIEWED_TOOL_COMMIT --remote-name origin \
  --remote-url https://github.com/xjamesmorris/k3-com260-info.git < REVIEWED_UPDATES
```

Each line is `LOCAL_REF LOCAL_OID REMOTE_REF EXPECTED_REMOTE_OID`. A direct
full commit OID is accepted as `LOCAL_REF` only when it equals `LOCAL_OID`.
The trusted tool selection is a separate human decision, not whichever new
tip happens to be in that stream. The hook's content checks are offline;
its live ref advertisement/fetch is necessary to establish the history
boundary. It never publishes the wiki.

Hooks are bypassable clone-local safeguards, not server enforcement. The
publisher repeats the gates directly. Other clones/operators can bypass
local hooks; the workflow makes no stronger guarantee.

## Human bootstrap

After implementation, source/privacy/licensing review, and separate approval
for the canonical content push, publish the canonical source **first** with
the installed hook. The publisher never pushes that source for you. Its
`origin` and any `pushurl` must be the single exact approved HTTPS source URL.
It requires an already public source commit reachable from freshly fetched
`refs/heads/main`, not merely an existing GitHub object or stale tracking ref.

Replace the two placeholders below with the human author's reviewed public
identity. These repository-local values are used for the canonical commit and
the later deterministic wiki commit; they are not a DCO sign-off.

```sh
/usr/bin/git config --local user.name '<reviewed public name>'
/usr/bin/git config --local user.email '<reviewed public email>'
/usr/bin/git config --local --get user.name
/usr/bin/git config --local --get user.email
```

After the canonical changes and reviewed tool are committed and the hook is
installed, the **separate content-publication approval gate** is:

The `/usr/bin/git push` below uses the human's independently selected
credential setup for the canonical repository and executes the installed
pre-push hook. It does not receive the wiki publisher's inline, push-only
`/usr/bin/gh` helper. The following `ls-remote` read-back is anonymous: it
runs outside any repository, disables system/global Git configuration and
credential helpers, rejects transport rewrites by allowing only HTTPS, and
ignores proxy/askpass/token environment variables.

```sh
FULL_PUBLIC_SOURCE_COMMIT="$(/usr/bin/git rev-parse HEAD)"
printf '%s\n' "$FULL_PUBLIC_SOURCE_COMMIT" | /usr/bin/grep -Eq '^[0-9a-f]{40}$'
/usr/bin/git push origin "${FULL_PUBLIC_SOURCE_COMMIT}:refs/heads/main"

PUBLIC_MAIN_COMMIT="$(
  /usr/bin/env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN -u GIT_ASKPASS -u SSH_ASKPASS \
    -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u ALL_PROXY -u all_proxy PATH=/usr/bin GIT_CONFIG_NOSYSTEM=1 \
    GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git --no-pager --no-replace-objects \
    -C / \
    -c protocol.allow=never -c protocol.https.allow=always \
    -c credential.helper= -c http.sslVerify=true \
    -c http.followRedirects=false ls-remote --exit-code --heads -- \
    https://github.com/xjamesmorris/k3-com260-info.git refs/heads/main |
  /usr/bin/awk '{print $1}'
)"
test "$PUBLIC_MAIN_COMMIT" = "$FULL_PUBLIC_SOURCE_COMMIT"
```

Do not run that push merely because validation passed. The human must approve
that exact canonical commit for `main`; the later wiki receipt approval is a
different decision.

Wiki enablement and first-page creation were separate human actions. The
one-time browser bootstrap was completed on September 27, 2026. The advertised
wiki tip is root commit `58ad759c03d924a051a26b6150af7d278119f026`;
it contains only regular `Home.md`, with precisely these bytes and a final
newline:

```text
Welcome to the k3-com260-info wiki!
```

The manifest binds those public bytes for one-time adoption. In the repository
UI, confirm **Settings -> General -> Features -> Wikis -> Restrict editing to
collaborators only** remains checked. Never make another browser save, even to
adjust whitespace or replace the default text: it creates a child commit, so
the advertised tip is no longer the required root commit and
`--adopt-bootstrap` refuses it. Do not add a sidebar or other page. If the
remote bytes, tree, or ancestry differ, do not edit again and do not force-push.
Go directly to the
[reviewed bootstrap recovery procedure](#recovery-and-useful-failures).
The tool discovers the wiki's default branch through an isolated
`/usr/bin/git ls-remote --symref`;
it does not assume `main` or `master`. GitHub's browser bootstrap is the
documented exception to the CLI workflow: no invented `gh wiki` subcommand,
REST wiki endpoint, or undocumented upload API is used.

Derive the freshly advertised bootstrap commit without supplying credentials
to the read:

```sh
INITIAL_HOME_COMMIT="$(
  /usr/bin/env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN \
    -u GITHUB_ENTERPRISE_TOKEN -u GIT_ASKPASS -u SSH_ASKPASS \
    -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    -u ALL_PROXY -u all_proxy PATH=/usr/bin GIT_CONFIG_NOSYSTEM=1 \
    GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git --no-pager --no-replace-objects \
    -C / \
    -c protocol.allow=never -c protocol.https.allow=always \
    -c credential.helper= -c http.sslVerify=true \
    -c http.followRedirects=false ls-remote -- \
    https://github.com/xjamesmorris/k3-com260-info.wiki.git HEAD |
  /usr/bin/awk '$2 == "HEAD" {print $1}'
)"
printf '%s\n' "$INITIAL_HOME_COMMIT" | /usr/bin/grep -Eq '^[0-9a-f]{40}$'
printf 'Initial wiki Home commit: %s\n' "$INITIAL_HOME_COMMIT"
```

Preparation initializes/fetches an ordinary independent `.wiki-publish/`
clone and configures its trusted hook before any publication push. It will
not repurpose another working tree, follow symlinked Git metadata, or
overwrite an existing unrelated directory.

## Prepare, review, then explicitly publish

Recheck the public repository-local `user.name` and `user.email`, the
published source OID, and GitHub CLI authentication. The identity becomes the
wiki publisher identity in the receipt; the tool does not invent an author or
certify a DCO sign-off.

```sh
/usr/bin/git config --local --get user.name
/usr/bin/git config --local --get user.email
/usr/bin/env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN \
  -u GITHUB_ENTERPRISE_TOKEN /usr/bin/gh auth status --hostname github.com

# First publication only: explicitly adopt the reviewed initial Home commit.
.wiki-venv/bin/python -B tools/wiki/manage.py prepare \
  --source "$FULL_PUBLIC_SOURCE_COMMIT" --adopt-bootstrap "$INITIAL_HOME_COMMIT"

# Later publications omit adoption.
.wiki-venv/bin/python -B tools/wiki/manage.py prepare \
  --source "$FULL_PUBLIC_SOURCE_COMMIT"

glow -p .wiki-build/prepared/RECEIPT_SHA256/report.md
glow -p .wiki-build/prepared/RECEIPT_SHA256/tree/Home.md
glow -p .wiki-build/prepared/RECEIPT_SHA256/tree/Fedora-Recipe.md

# Only after explicit human approval of these exact receipt bytes:
.wiki-venv/bin/python -B tools/wiki/manage.py publish \
  --receipt .wiki-build/prepared/RECEIPT_SHA256/receipt.json \
  --expect-receipt RECEIPT_SHA256
```

Without `glow`, use `cat` on those same three files. Do not regenerate or edit
the prepared tree while reviewing it.

Preparation does not push or make a wiki commit. It requires clean source
and publication checkouts, verifies public source reachability and wiki
identity, runs offline/online gates, and creates a read-only preparation
directory by atomic rename. The report includes public source/target
identities, exact file hashes, bounded link results/used exceptions and the
complete managed diff. No ambient login names, local paths or private intake
identities from the build machine appear in its provenance. The deliberately
reviewed public publisher identity is bound separately.

The publish command is the **separate receipt-bound wiki approval gate**. Its
pre-push/read-back fetches remain anonymous. Only its single normal
fast-forward wiki push receives the resolved GitHub CLI credential helper;
the helper returns credentials directly to Git over the credential protocol.
No token is copied into the command line, environment, receipt, report,
transaction marker, or repository configuration.

### Receipt schema 1

`receipt.json` is UTF-8 canonical JSON: recursively sorted keys, compact
separators, ASCII escapes, one terminal newline. Its SHA256 is both the
directory name and the separate human-selected `--expect-receipt` value.

| Field | Binding |
| --- | --- |
| `source` | Exact source URL/branch, commit, tree and freshly observed public branch tip. |
| `identities` | Manifest blob, explicit tool-file modes/blobs/SHA256 and aggregate tool SHA256, dependency-lock blob, link-exception blob, validation-exception policy SHA256. |
| `runtime` | Python implementation/version, pinned parser/dependency module fingerprints, and verified system `git`/`gh` path, SHA256, ownership, mode, size, and ancestor identity. |
| `author` | Reviewed public publisher name/email and selected source commit timestamp, producing retry-stable wiki commits. |
| `output` | Exact Git tree plus every file's name, `100644` mode, blob, SHA256 and size. |
| `online_approval` | Canonically ordered per-page/URL/role availability verdicts, required image/checksum identities, and the complete records of exceptions actually used during preparation. |
| `wiki` | Exact wiki URL, discovered branch, expected remote OID, and bootstrap or prior-managed state. Bootstrap binds the exact Home blob; managed state binds previous source/tree. |
| `checked_day` | UTC date of preparation checks, not a hardware observation date. |
| `report_sha256` | The exact report/diff the human reviews. |

Publication consumes the reviewed files. It may render/check in memory to
compare them, but never replaces a changed prepared tree by silently
regenerating it. A changed receipt/report/output, tool/lock/runtime, policy,
author, target branch/OID, expired exception or unavailable critical link
requires new preparation and review. A changed availability verdict or
exception-use set also requires a new receipt, even when an exception was
already present and still valid in the bound policy. This comparison happens
before any publication writes or ref fetches. An available resource becoming
excepted, or an excepted resource recovering, cannot silently change the
human-reviewed state. HEAD/GET success is one stable `available` verdict;
response ordering, timing and DNS/load-balanced-address noise are not approval
inputs. Critical images and checksum records remain non-waivable.

Both preparation and publication live-fetch the exact public source branch
and verify its advertisement and ancestry. A later source tip is acceptable
only if the same reviewed source is still reachable and all bound inputs
and output remain unchanged. A separate local
`.wiki-build/prepared/.last-check.json` records the refreshed checks; it
does not alter the reviewed receipt.

Before writing the clone, publication checks that its old tree is either
the exact initial Home or can be reconstructed from the last publisher's
public `K3-Wiki-Provenance` commit record and its public source snapshot.
Unexpected web edits, extra files, altered modes, merges, missing provenance
or changed bootstrap Home stop it. Adoption cannot be reused after that
initial root commit. A renderer upgrade must retain the ability to recognize
the last published projection; if reconstruction fails, reconcile explicitly.

Only named managed files are written/staged; deletions must come from the
verified prior managed tree. Publication creates one normal child commit
with public provenance, checks its exact tree, rechecks the remote OID
immediately before pushing, and performs a **normal fast-forward push only**.
The wiki clone hook repeats the receipt gate for the actual proposed commit.
There is no force/lease/mirror/prune path or implicit second push. Remote
commit/tree read-back is mandatory.

After a separately approved successful push, use `gh browse --wiki` to
inspect Home, navigation, reference anchors, tables and code rendering.
Glow and these fixtures are not proof of GitHub Wiki rendering parity.

## Recovery and useful failures

| Diagnostic or state | Safe response |
| --- | --- |
| Missing/mismatched parser | Restore the reviewed hash-locked venv. The hook does not install on push. |
| Missing, moved, or unsafe `git`/`gh` | Install the distribution packages so root-owned, non-writable regular executables exist at `/usr/bin/git` and `/usr/bin/gh`. Symlinks, unsafe ancestors, user/group/other-writable tools, or identity drift are refused. Rerun validation, reinstall the hook, and prepare a new receipt after a deliberate package change. |
| GitHub authentication rejected | Run the token-unset `/usr/bin/gh auth status` command above; if necessary, use `/usr/bin/env -u GH_TOKEN -u GITHUB_TOKEN -u GH_ENTERPRISE_TOKEN -u GITHUB_ENTERPRISE_TOKEN /usr/bin/gh auth login --hostname github.com --git-protocol https --web`. Review where `gh` stored the credential. Do not pass an environment token, HTTP authorization header, or credential URL to the publisher. Retry the same receipt only if the wiki tip and bound runtime did not move. |
| Missing visible context or anchor | Correct the canonical page; do not accept an unrelated live wiki page as proof. |
| Privacy finding | Inspect the identified blob/line locally; sanitize or obtain a genuinely human-reviewed exact allowance. Do not paste the matched data into a public issue/report. |
| Different tool or intermediate validator | Review it and run the fixtures, then explicitly install that reviewed committed tool. Never execute untrusted push inputs to make the gate pass. |
| `.git/wiki-validator/.partial-*` candidate | An interrupted/failed install did not configure this candidate. Retry the same reviewed commit; the installer builds a fresh stage or verifies a completed final bundle. Preserve partials for inspection and remove only individually verified owned artifacts, not the bundle parent. |
| Hook bundle inventory/mode mismatch | Extra files/caches, symlinks, hardlinks or changed permissions invalidate the bundle. Nothing is automatically overwritten; preserve the evidence and deliberately reconcile/reinstall the reviewed tool. |
| Online availability or used exception changed | Prepare and review a new receipt showing the new verdict/exception-use set. A valid but previously unused exception does not authorize a silent publication-state change. |
| Source not public on main | Obtain permission for the canonical content push first; neither helper performs it. |
| Initial Home bytes differ from `bootstrap_home`, or Home was saved more than once | Do not make another browser edit, amend, or force-push wiki history. Inspect `/usr/bin/git -C .wiki-publish rev-list --parents -n 1 "$INITIAL_HOME_COMMIT"` and `/usr/bin/git -C .wiki-publish show "${INITIAL_HOME_COMMIT}:Home.md"`. If the advertised commit is the acceptable reviewed **root** bootstrap, update `bootstrap_home` to those exact public bytes through a separately reviewed canonical tool/manifest commit, reinstall that reviewed hook, obtain a new content-push approval, and prepare again. A second browser save produces a non-root tip and therefore requires explicit reconciliation rather than another edit. |
| Wiki web edit/extra file or default-branch change | Preserve it, reconcile it into canonical source deliberately, and prepare a new receipt. Do not force-push over it. |
| Dirty source/clone or preview | Preserve unrelated edits. Inspect the exact files rather than broadly cleaning/resetting directories. |
| `.partial-*` preparation | An interrupted preparation is not a receipt. Retry creates a fresh named staging directory; old partials remain for inspection. Remove only individually verified owned artifacts. |
| `.git/wiki-transaction.json` in the publication clone | A write/push was interrupted. Retry the **same** receipt; it recognizes only that bound transaction, old/prepared file bytes and deterministic candidate commit. A different receipt or unrelated edit is refused. |
| Push failed/raced | Do not force-retry. If the target did not move, retry the same receipt; otherwise preserve/reconcile the changed remote and obtain fresh review. |
| Already-published/no-change result | Gates still ran; no redundant push is made. |

To roll back wiki content, prepare a reviewed earlier **public** source and
publish it as a new forward commit, with fresh checks and human receipt
approval. Do not reset/rewrite wiki history. If its tool version is no longer
trusted or an exception expired, create a newly reviewed canonical commit
containing the older content with current tooling/policy instead.

The focused acceptance suite covers projection fidelity, metadata/anchors,
paths/modes, privacy and source-bound exceptions, HTTP/DNS bounds, actual-ref
and historical-content gates, bootstrap/default branches, receipts,
managed deletion, drift/races, interrupted work, forward rollback, and both
mandatory code-only install images/checksum records without binary GETs.
Run it after tooling changes, plus `bash -n .githooks/pre-push` and
`shellcheck .githooks/pre-push`. Initial integration still requires the scoped
publisher security review, reader-journey review and human acceptance.

## Manual-first maintenance

Start with manual invocations of the read-only
[wiki-curator](../../.github/agents/wiki-curator.agent.md) and
[wiki-reviewer](../../.github/agents/wiki-reviewer.agent.md) profiles. Give
each one human-selected topic, the exact public source commit/pages, and a
bounded primary-source list. The curator returns dated proposals; the
reviewer evaluates the proposed changes and supplied check results. Neither
profile runs commands, edits files, changes review dates/pins/exceptions, or
publishes. The human remains the author and may direct the main session to
apply accepted changes.

| When manually invoked | Bounded work and expected output |
| --- | --- |
| Weekly | Human-run link/anchor/exception-expiry checks, followed by one Fedora/Omni or kernel/KVM/QEMU source delta. Produce one dated review queue, including unknown/unavailable sources, not rewritten pages. |
| Relevant Fedora/vendor milestone | Review image availability, board advisories or upstream status; propose corrections without automatically advancing tested pins or removing workarounds. |
| Monthly | Review resource relevance, original Chinese-language versus translated sources, toolchain/llama opportunities and contribution-policy changes. Return scoped resource/page proposals. |
| After an approved hardware result | Propose an evidence update tied to the exact stack, observations, public-safe record and explicit limits. A source-review date never becomes a hardware-test date. |

For the weekly deterministic check, use the supported report-only command
with a full reviewed **commit OID**, not `HEAD`, a branch, tag object or
abbreviated ref:

```sh
.wiki-venv/bin/python -B tools/wiki/manage.py check-links \
  --ref REVIEWED_FULL_SOURCE_COMMIT
```

`check-links` binds the matching running tool and pinned runtime before and
after offline and bounded online checks, including the two mandatory image
HEADs/checksum records. It prints canonical public-safe JSON to stdout and
uses the normal sanitized CLI error path. The report includes source
commit/tree, tool/runtime identities, stable link verdicts and any used
exceptions; it explicitly sets `public_reachability_checked` and
`publication_authorized` to `false`. It needs no installed hook and performs
no Git fetch/push, receipt creation, wiki-clone setup, hook/configuration
changes or source edits. There are no additional network override/skip flags.

An unavailable required link fails rather than producing a clean bill of
health. Supply only public-safe results to the profiles; their interpretation
does not replace deterministic checks or human privacy/licensing review.
This maintenance report does not establish publication reachability or
authorize publishing: every publication still requires its complete gate and
human-selected receipt. Publisher/security-sensitive changes need the separately scoped Codex 5.3
review, followed by Opus 5.5 review/evaluation and human review.

No timer or schedule is installed or enabled. Any later external scheduler
requires separate human opt-in, a selected model/cost ceiling, bounded
report-only jobs and no overlapping runs. Do not enable autonomous edits,
publication, hardware experiments or a recurring vulnerability hunt.
