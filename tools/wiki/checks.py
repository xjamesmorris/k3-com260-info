# SPDX-License-Identifier: GPL-2.0-only
"""Offline checks and public-safe findings. These do not certify human claims."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import re
import unicodedata
from urllib.parse import unquote, urlsplit

import content as c

FIELDS = ("Applies to", "Evidence", "Source review", "Hardware observation", "Destructive operations")
NAVIGATION_LABELS = ("Previous:", "Next:", "Start again:")
ARTIFACT = re.compile(
    r"\.(?:xz|gz|bz2|zip|zst|zstd|tar|img|raw|qcow2|iso|bin|dtb|gguf|onnx|safetensors|"
    r"png|jpe?g|gif|svg|webp|mp4|pdf|deb|rpm|whl|git)(?:$|/)", re.I,
)
SECRET_QUERY = re.compile(r"(?:^|[?&;])(?:access[_-]?token|token|api[_-]?key|password|secret|"
                          r"signature|credential|auth|key)=", re.I)
PRIVACY_RULES = {
    "private-key": re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"),
    "access-token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
                               r"AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{32,})"),
    "credential-url": re.compile(r"https?://[^/\s<>]+:[^/\s<>]+@[^/\s<>]+", re.I),
    "secret-query": re.compile(r"https?://[^\s<>\"']*[?&](?:access[_-]?token|token|api[_-]?key|"
                               r"password|secret|signature|credential|auth|key)=[^\s<>\"']+", re.I),
    "private-locator": re.compile(r"(?:\.copilot/session-state/[A-Za-z0-9_-]+|file://(?:/|[A-Za-z0-9])[^\s<>\"']+|(?<![A-Za-z0-9])/(?:private|mirror)/"
                                 r"[A-Za-z0-9_.-]+|[A-Za-z]:\\Users\\[A-Za-z0-9_.-]+)"),
    "operator-home": re.compile(r"/(?:home|Users)/[A-Za-z0-9_.-]+"),
    "private-ip": re.compile(r"(?<![\d.])(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
                            r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?![\d.])"),
    "personal-uuid": re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                               r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
}


def iso_day(value, label: str) -> date:
    c.require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
              f"{label}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise c.Invalid(f"{label}: invalid calendar date") from None


def review_fields(entry: dict, today: date, *, expiry: bool) -> None:
    for key in ("reason", "reviewer"):
        c.require(isinstance(entry[key], str) and 3 <= len(entry[key].strip()) <= 1000,
                  "exception needs a meaningful rationale and human reviewer")
        c.require(not any(ch in entry[key] for ch in "\x00\r\n"), "multiline exception review field")
    c.require(not re.search(r"\b(?:copilot|chatgpt|claude|gemini|agent|llm|todo|tbd|unknown)\b",
                            entry["reviewer"], re.I), "exception requires a real human reviewer")
    reviewed = iso_day(entry["reviewed"], "exception reviewed")
    c.require(reviewed <= today, "exception review date is in the future")
    if expiry or "expires" in entry:
        expires = iso_day(entry["expires"], "exception expires")
        c.require(reviewed <= expires and today <= expires, "exception expired or has inconsistent dates")


def validation_exceptions(m: dict, snapshot, today: date) -> list[dict]:
    entries = m["validation_exceptions"]
    seen = set()
    for entry in entries:
        c.object_keys(entry, {"rule", "path", "blob", "match_sha256", "line",
                              "reason", "reviewer", "reviewed"}, {"expires"})
        c.require(entry["rule"] in PRIVACY_RULES, "unknown validation exception rule")
        path = c.safe_path(entry["path"])
        c.require(path.startswith("wiki/") or path in (c.MANIFEST, c.EXCEPTIONS, c.RECIPE_PATH),
                  "validation exception is not scoped to a public content input")
        c.require(isinstance(entry["blob"], str) and c.OID_RE.fullmatch(entry["blob"]),
                  "invalid exception source blob")
        c.require(isinstance(entry["match_sha256"], str)
                  and re.fullmatch(r"[0-9a-f]{64}", entry["match_sha256"]), "invalid match digest")
        c.require(type(entry["line"]) is int and entry["line"] > 0, "exception needs a precise source line")
        c.require(c.blob_id(snapshot.read(path)) == entry["blob"], "stale exception: source blob changed")
        identity = tuple(entry[key] for key in ("rule", "path", "blob", "match_sha256", "line"))
        c.require(identity not in seen, "duplicate validation exception")
        seen.add(identity)
        review_fields(entry, today, expiry=False)
    return entries


def privacy(data: bytes, path: str, allowances: list[dict] = (), *, approved_blob: str | None = None) -> list[dict]:
    value = c.text(data, "privacy input")
    oid = c.blob_id(data)
    findings = []
    for rule, pattern in PRIVACY_RULES.items():
        for match in pattern.finditer(value):
            # The complete protected public blob, not a string-wide ignore, admits its image account.
            if (rule == "operator-home" and match.group() == "/home/" + "fedora"
                    and oid == approved_blob == c.RECIPE_BLOB):
                continue
            line = value.count("\n", 0, match.start()) + 1
            finding = {"rule": rule, "path": path, "blob": oid,
                       "match_sha256": c.sha256(match.group().encode()), "line": line}
            if not any(all(entry[k] == v for k, v in finding.items()) for entry in allowances):
                findings.append(finding)
    return findings


def require_private_safe(data: bytes, path: str, allowances: list[dict] = (), *,
                         approved_blob: str | None = None) -> None:
    findings = privacy(data, path, allowances, approved_blob=approved_blob)
    if findings:
        f = findings[0]
        raise c.Invalid(f"privacy review required: {f['rule']}, blob {f['blob']}, line {f['line']}; "
                        "no matching data is printed; sanitize or obtain a source-bound human review")


def headings(data: bytes) -> set[str]:
    tokens = c.parser().parse(c.text(data))
    used = set()
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        inline = tokens[index + 1]
        visible = "".join(child.content for child in (inline.children or [])
                          if child.type in ("text", "code_inline", "html_inline"))
        base = "".join(ch for ch in visible.lower() if ch in "-_ "
                       or unicodedata.category(ch)[0] in ("L", "N")).replace(" ", "-")
        slug, suffix = base, 0
        while slug in used:
            suffix += 1
            slug = f"{base}-{suffix}"
        used.add(slug)
    return used


def heading_text(tokens, index: int) -> str:
    inline = tokens[index + 1]
    return "".join(child.content for child in (inline.children or [])
                   if child.type in ("text", "code_inline", "html_inline")).strip()


def field_labels(token) -> list[str]:
    labels = []
    strong = None
    for child in token.children or []:
        if child.type == "strong_open":
            strong = []
        elif child.type == "strong_close" and strong is not None:
            label = re.sub(r"\s+", " ", "".join(strong)).strip()
            label = label.removesuffix(":").strip().casefold()
            labels.extend(field for field in FIELDS if field.casefold() == label)
            strong = None
        elif strong is not None and child.type in ("text", "code_inline"):
            strong.append(child.content)
        elif strong is not None and child.type in ("softbreak", "hardbreak"):
            strong.append(" ")
    return labels


def navigation(token) -> None:
    labels = []
    links = 0
    strong = None
    in_link = False
    pending_label = False
    labeled_links = 0
    for child in token.children or []:
        if child.type == "text":
            if strong is not None:
                strong.append(child.content)
            elif in_link:
                continue
            else:
                permitted = r"\s*" if pending_label else r"[\s.|]*"
                c.require(re.fullmatch(permitted, child.content),
                          "Technical notes navigation has unsupported text")
        elif child.type == "softbreak":
            c.require(strong is None and not in_link, "malformed Technical notes navigation")
        elif child.type == "strong_open":
            c.require(strong is None and not in_link and not pending_label and child.markup == "**",
                      "malformed Technical notes navigation label")
            strong = []
        elif child.type == "strong_close":
            c.require(strong is not None and child.markup == "**",
                      "malformed Technical notes navigation label")
            label = "".join(strong).strip()
            c.require(label in NAVIGATION_LABELS, "unsupported Technical notes navigation label")
            labels.append(label)
            pending_label = True
            strong = None
        elif child.type == "link_open":
            href = child.attrGet("href")
            c.require(strong is None and not in_link and isinstance(href, str)
                      and (href == c.WIKI_URL or href.startswith(c.WIKI_URL + "/")),
                      "Technical notes navigation must use canonical wiki links")
            if pending_label:
                labeled_links += 1
            else:
                c.require(labeled_links and href in (c.WIKI_URL, c.WIKI_URL + "/Home"),
                          "unlabeled Technical notes navigation is limited to Home after a labeled link")
            in_link = True
            links += 1
            pending_label = False
        elif child.type == "link_close":
            c.require(in_link, "malformed Technical notes navigation link")
            in_link = False
        elif child.type == "code_inline" and in_link:
            continue
        else:
            raise c.Invalid("unsupported Technical notes navigation markup")
    c.require(strong is None and not in_link and not pending_label and labels and links,
              "authored page is missing canonical wiki navigation")


def metadata(data: bytes, kind: str, today: date) -> dict[str, str]:
    tokens = c.parser().parse(c.text(data))
    first = 0
    while (first < len(tokens) and tokens[first].type == "html_block"
           and tokens[first].content.lstrip().startswith("<!--")):
        first += 1
    c.require(first < len(tokens) and tokens[first].type == "heading_open" and tokens[first].tag == "h1",
              "authored page must begin with an H1 title")
    c.require(sum(token.type == "heading_open" and token.tag == "h1" for token in tokens) == 1,
              "authored page must contain exactly one H1 title")

    technical = [index for index, token in enumerate(tokens)
                 if token.type == "heading_open"
                 and heading_text(tokens, index).casefold() == "technical notes"]
    c.require(technical, "missing visible context fields; see tools/wiki/README.md")
    c.require(len(technical) == 1, "duplicate Technical notes section")
    section = technical[0]
    c.require(tokens[section].tag == "h2" and heading_text(tokens, section) == "Technical notes"
              and tokens[section + 1].content == "Technical notes",
              "authored page needs an exact H2 Technical notes section")
    heading_indices = [index for index, token in enumerate(tokens) if token.type == "heading_open"]
    c.require(section == heading_indices[-1], "Technical notes must be the final heading")

    tail = tokens[section + 3:]
    c.require(len(tail) >= 18, "missing visible context fields; see tools/wiki/README.md")
    blocks = []
    for offset in range(0, 18, 3):
        opened, inline, closed = tail[offset:offset + 3]
        c.require(opened.type == "paragraph_open" and opened.level == 0
                  and inline.type == "inline" and closed.type == "paragraph_close",
                  "Technical notes must contain top-level field and navigation paragraphs only")
        blocks.append((section + 4 + offset, inline))
    c.require(len(tail) == 18,
              "Technical notes may contain only the five fields and final navigation; "
              "no content may follow navigation")

    fields = {}
    expected_labels = []
    for (index, token), field in zip(blocks[:5], FIELDS):
        match = re.fullmatch(r"\*\*" + re.escape(field) + r":\*\*[ \t]+([^\n]+)", token.content)
        c.require(match is not None, "context fields must use the documented labels and order")
        fields[field] = match.group(1).strip()
        expected_labels.append((index, field))
    navigation(blocks[5][1])

    actual_labels = [(index, field) for index, token in enumerate(tokens) if token.type == "inline"
                     for field in field_labels(token)]
    c.require(actual_labels == expected_labels, "duplicate or misplaced visible context field")

    opener = first + 3
    c.require(opener + 2 < len(tokens)
              and tokens[opener].type == "paragraph_open" and tokens[opener].level == 0
              and tokens[opener + 1].type == "inline" and tokens[opener + 1].content.strip()
              and tokens[opener + 2].type == "paragraph_close",
              "authored page needs an opening paragraph after its H1")

    reviewed = re.match(r"(\d{4}-\d{2}-\d{2})(?:\b|$)", fields["Source review"])
    c.require(reviewed and iso_day(reviewed.group(1), "source review") <= today,
              "missing or future source-review date")
    c.require(re.search(r"\b(?:record(?:ed)?|snapshot|recipe|provenance|official|upstream|vendor|references?|untested)\b",
                        fields["Evidence"], re.I),
              "Evidence must declare recorded, reference, or untested basis")
    observed = fields["Hardware observation"]
    c.require(re.search(r"\b(?:not performed|not applicable|unknown|not recorded|\d{4}-\d{2}-\d{2})\b",
                        observed, re.I), "Hardware observation needs a date/scope or an explicit unknown")
    for observed_day in re.findall(r"\d{4}-\d{2}-\d{2}", observed):
        c.require(iso_day(observed_day, "hardware observation") <= today, "future hardware observation")
    if kind == "procedure":
        c.require(len(fields["Applies to"]) >= 15 and len(fields["Destructive operations"]) >= 4,
                  "procedure needs applicable hardware/stack and destructive scope")
    return fields


def table_rows(data: bytes) -> list[list[list[str]]]:
    tables, rows, row = [], [], []
    in_table = False
    for token in c.parser().parse(c.text(data)):
        if token.type == "table_open":
            in_table, rows = True, []
        elif token.type == "tr_open" and in_table:
            row = []
        elif token.type == "inline" and in_table:
            row.append(token.content)
        elif token.type == "tr_close" and in_table:
            rows.append(row)
        elif token.type == "table_close":
            tables.append(rows)
            in_table = False
    return tables


def evidence_shape(page: str, data: bytes) -> None:
    if page == "KVM-and-QEMU.md":
        required = ("result", "host", "qemu", "guest", "cpu", "plic", "vcpu",
                    "storage", "network", "source", "nonclaim")
        tables = table_rows(data)
        matrix = next((table for table in tables if table and len(table[0]) == len(required)
                       and all(word in cell.lower() for word, cell in zip(required, table[0]))), None)
        c.require(matrix and len(matrix) >= 3 and all(len(row) == len(required)
                  and all(cell.strip() for cell in row) for row in matrix),
                  "KVM page needs the explicit per-result host/QEMU/guest/CPU/PLIC/vCPU/storage/network/source/nonclaims matrix")
        for row in matrix[1:]:
            if "7.3.0-rc4-k3-kvm-host-a1" in row[1] and "Fedora 44" in row[3]:
                c.require(row[4] == "`host,svpbmt=false,zicbom=false,zicbop=false,zicboz=false`"
                          and re.match(r"4\b", row[6].lstrip("`")),
                          "recorded Fedora guest compatibility flags/vCPU count changed; review the public evidence")
    elif page == "Contributing-Upstream.md":
        anchors = headings(data)
        c.require({"worked-preparation-dldo4-rfc", "worked-preparation-fedora-guest-report"} <= anchors
                  and sum(len(table) >= 5 for table in table_rows(data)) >= 2,
                  "contribution page needs both performed-work examples and their artifact checklists")


@dataclass(frozen=True)
class Link:
    page: str
    url: str
    role: str
    expected_sha256: str | None = None
    filename: str | None = None


def url_shape(url: str) -> None:
    c.require(isinstance(url, str) and len(url) <= 4096
              and not re.search(r"[\x00-\x20\x7f\\]", url), "malformed or unsafe URL")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise c.Invalid("malformed URL authority") from None
    c.require(parts.scheme == "https" and bool(parts.hostname) and not parts.username
              and not parts.password and port in (None, 443), "only public HTTPS URLs on port 443 are allowed")
    c.require(not SECRET_QUERY.search(unquote(url)), "URL may contain a credential; URL suppressed")


def repo_link(snapshot, url: str) -> bool:
    """Check our public repo links against their actual local objects, not local HEAD."""
    if url in (c.REPO_WEB, c.SOURCE_URL):
        return True
    parts = urlsplit(url)
    prefix = urlsplit(c.REPO_WEB).path + "/"
    if parts.hostname != "github.com" or not unquote(parts.path).casefold().startswith(prefix.casefold()):
        return False
    c.require(parts.netloc == "github.com" and parts.path.startswith(prefix)
              and unquote(parts.path) == parts.path, "use canonical unencoded links to this public repository")
    rest = parts.path[len(prefix):].split("/")
    if rest[0] == "commit" and len(rest) == 2 and c.OID_RE.fullmatch(rest[1]):
        snapshot.git.commit(rest[1])
        return True
    if rest[0] not in ("blob", "tree") or len(rest) < 3:
        return False
    ref, path = rest[1], unquote("/".join(rest[2:]))
    c.safe_path(path)
    # A symbolic main link is the proposed snapshot; a pinned link is that exact commit.
    c.require(ref == "main" or c.OID_RE.fullmatch(ref),
              "this repository's links must use main or an exact public commit")
    target = (snapshot if ref == "main" or (ref == snapshot.commit and not snapshot.worktree)
              else c.Snapshot(snapshot.root, ref))
    if rest[0] == "tree":
        c.require(any(p.startswith(path + "/") for p in target.entries), "repository tree link is absent")
        if parts.fragment:
            path += "/README.md"
        else:
            return True
    if target.worktree and ref == "main":
        data = target.read(path)
    else:
        c.require(path in target.entries, "repository blob link is absent at its specified commit")
        data = target.read(path)
    fragment = unquote(parts.fragment)
    if fragment:
        lines = re.fullmatch(r"L(\d+)(?:-L(\d+))?", fragment)
        if lines:
            first, last = int(lines[1]), int(lines[2] or lines[1])
            c.require(1 <= first <= last <= len(data.splitlines()), "repository line link is out of range")
        else:
            c.require(path.endswith(".md") and fragment in headings(data), "repository heading anchor is absent")
    return True


def links(snapshot, m: dict, output: dict[str, bytes]) -> list[Link]:
    anchors = {name: headings(data) for name, data in output.items()}
    kinds = {p["target"]: p["kind"] for p in m["pages"]}
    external: set[Link] = set()
    for page, data in output.items():
        tokens = c.parser().parse(c.text(data))
        values = []
        for token in c.nodes(tokens):
            c.require(token.type != "image", "binary/image inputs are not supported by this initial wiki publisher")
            if token.type in ("html_block", "html_inline"):
                c.require(re.fullmatch(r"\s*<!--(?:(?!-->).)*-->\s*", token.content, re.S),
                          "raw HTML is unsupported; use ordinary Markdown")
            if token.type == "link_open":
                values.append((token.attrGet("href"), False))
            if token.type == "text":
                for url in re.findall(r"https?://[^\s<>\"'`]+", token.content):
                    values.append((url.rstrip(".,);"), False))
        navigation = False
        for url, in_code in values:
            if url.startswith("#"):
                c.require(unquote(url[1:]) in anchors[page], "same-page heading anchor is absent")
                continue
            if url.startswith("mailto:"):
                c.require(re.fullmatch(r"mailto:[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", url),
                          "invalid public mailto link")
                continue
            url_shape(url)
            parsed = urlsplit(url)
            wiki_path = urlsplit(c.WIKI_URL).path
            if (parsed.hostname == "github.com"
                    and (unquote(parsed.path).casefold() == wiki_path.casefold()
                         or unquote(parsed.path).casefold().startswith(wiki_path.casefold() + "/"))):
                c.require(url.startswith(c.WIKI_URL) and parsed.netloc == "github.com"
                          and unquote(parsed.path) == parsed.path, "use full canonical unencoded wiki URLs")
                tail = unquote(parsed.path.removeprefix(urlsplit(c.WIKI_URL).path)).lstrip("/")
                target = (tail or "Home") + ".md"
                c.require(not parsed.query and target in output, "wiki page link is not in the manifest")
                if parsed.fragment:
                    c.require(unquote(parsed.fragment) in anchors[target], "wiki heading anchor is absent")
                if not in_code:
                    navigation = True
                continue
            if repo_link(snapshot, url):
                continue
            role = "resource" if kinds.get(page) == "resources" and not in_code else "source"
            if ARTIFACT.search(parsed.path):
                role = "artifact"
            external.add(Link(page, url, role))
        if page in kinds:
            c.require(navigation, "authored page is missing canonical wiki navigation")
    for artifact in m["critical_artifacts"]:
        filename = urlsplit(artifact["url"]).path.rsplit("/", 1)[-1]
        for field, role in (("url", "critical-artifact"), ("checksum_url", "critical-checksum")):
            external.add(Link("Fedora-Recipe.md", artifact[field], role, artifact["sha256"], filename))
    return sorted(external, key=lambda link: (not link.role.startswith("critical-"), link.page, link.url, link.role))


def resource_exceptions(data: bytes, m: dict, external: list[Link], today: date) -> list[dict]:
    value = c.load_json(data, "link exceptions")
    c.object_keys(value, {"schema", "exceptions"})
    c.require(value["schema"] == 1 and isinstance(value["exceptions"], list), "invalid link exception schema")
    allowed = {(link.page, link.url) for link in external if link.role == "resource"}
    critical = {link.url for link in external if link.role != "resource"}
    seen = set()
    for entry in value["exceptions"]:
        c.object_keys(entry, {"kind", "page", "url", "reason", "reviewer", "reviewed", "expires"})
        c.require(entry["kind"] == "resource", "only resource availability can receive a link exception")
        url_shape(entry["url"])
        identity = (entry["page"], entry["url"])
        c.require(identity in allowed and entry["url"] not in critical,
                  "link exception is stale, not resource-scoped, or covers a critical source/artifact")
        c.require(identity not in seen, "duplicate link exception")
        seen.add(identity)
        review_fields(entry, today, expiry=True)
        require_private_safe(c.canonical(entry), c.EXCEPTIONS)
    return value["exceptions"]


@dataclass
class Checked:
    manifest: dict
    output: dict[str, bytes]
    links: list[Link]
    exceptions: list[dict]


def validate(snapshot, *, today: date | None = None) -> Checked:
    today = today or datetime.now(timezone.utc).date()
    m, output = c.render(snapshot)
    allowances = validation_exceptions(m, snapshot, today)
    for path in (c.MANIFEST, c.EXCEPTIONS, c.RECIPE_PATH):
        require_private_safe(snapshot.read(path), path, allowances, approved_blob=c.RECIPE_BLOB)
    for page in m["pages"]:
        data = snapshot.read(page["source"], page=True)
        require_private_safe(data, page["source"], allowances)
        metadata(data, page["kind"], today)
        evidence_shape(page["target"], data)
    # Every allowance must still identify an actual finding, even if the entire blob is unchanged.
    for entry in allowances:
        findings = privacy(snapshot.read(entry["path"]), entry["path"])
        c.require(any(all(entry[k] == finding[k] for k in
                          ("rule", "path", "blob", "match_sha256", "line")) for finding in findings),
                  "validation exception no longer matches its exact occurrence")
    external = links(snapshot, m, output)
    exceptions = resource_exceptions(snapshot.read(c.EXCEPTIONS, page=True), m, external, today)
    return Checked(m, output, external, exceptions)
