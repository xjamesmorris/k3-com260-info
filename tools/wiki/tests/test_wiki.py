# SPDX-License-Identifier: GPL-2.0-only
"""Offline fixtures only. No board commands, external requests, or public pushes."""

from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
import gzip
import io
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
TOOL_ROOT = TOOLS.parents[1]
ROOT = Path(os.environ.get("WIKI_TEST_REPOSITORY", TOOL_ROOT))
sys.dont_write_bytecode = True
sys.path.insert(0, str(TOOLS))

import content as c
import checks as ck
import httpcheck as h
import manage
import publication as p
import storage as s

DAY = date(2026, 9, 27)


def fixture_manifest():
    trusted_ref = os.environ.get("WIKI_TEST_SOURCE_REF")
    data = c.Snapshot(ROOT, trusted_ref).read(c.MANIFEST) if trusted_ref else c.regular_read(ROOT, c.MANIFEST)
    return c.load_json(data, "fixture manifest")


def fixture_output():
    base = ROOT / s.BUILD / "tests"
    output = Path(os.environ.get("WIKI_TEST_OUTPUT", base))
    c.require(output.is_absolute() and output.is_relative_to(base) and ".." not in output.parts,
              "fixture output must remain inside the repository's ignored test area")
    with s.directory(ROOT, output.relative_to(ROOT).as_posix(), create=True):
        pass
    return output


def page_bytes(title="Fixture", extra=""):
    return (
        f"# {title}\n\n"
        "**Applies to:** Reference-only fixture; no hardware procedure.\n\n"
        "**Evidence:** Recorded fixture/reference shape only, not a hardware result.\n\n"
        "**Source review:** 2026-09-25.\n\n"
        "**Hardware observation:** Not performed.\n\n"
        "**Destructive operations:** None on this fixture page.\n\n"
        f"[Home]({c.WIKI_URL}/Home)\n\n" + extra
    ).encode()


def manifest_page_bytes(page):
    extra = "## Fixture\n"
    if page["target"] == "Console-and-Recovery.md":
        extra += "\n## Factory recovery, only when needed\n"
    return page_bytes(page["title"], extra)


class MemorySnapshot:
    def __init__(self, manifest, recipe):
        self.commit = c.BASELINE
        self.worktree = False
        self.root = ROOT
        self.base = c.Snapshot(ROOT, c.BASELINE)
        self.git = self.base.git
        self.entries = self.base.entries
        self.files = {
            c.MANIFEST: c.canonical(manifest),
            c.EXCEPTIONS: b'{"schema":1,"exceptions":[]}\n',
            c.RECIPE_PATH: recipe,
            **{page["source"]: manifest_page_bytes(page) for page in manifest["pages"]},
        }

    def read(self, path, *, page=False):
        return self.files[path] if path in self.files else self.base.read(path, page=page)

    def inventory(self, prefix):
        return {p for p in self.files if p.startswith(prefix + "/")}

    def protected(self):
        return None


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = c.Snapshot(ROOT, c.BASELINE)
        cls.data = cls.snapshot.read(c.RECIPE_PATH)
        cls.manifest = fixture_manifest()

    def test_public_protected_blob(self):
        self.snapshot.protected()
        self.assertEqual(c.blob_id(self.data), c.RECIPE_BLOB)
        self.assertEqual(c.sha256(self.data), c.RECIPE_SHA256)

    def test_exact_fidelity(self):
        recipe = self.manifest["recipe"]
        expected = self.data
        for rule in recipe["links"]:
            old = ("](" + rule["old"] + ")").encode()
            new = ("](" + rule["new"] + ")").encode()
            self.assertEqual(expected.count(old), rule["count"])
            expected = expected.replace(old, new)
        checkout = recipe["checkout"]
        expected = expected.replace(checkout["old"].encode(), checkout["new"].encode())
        self.assertEqual(c.recipe_body(self.data, recipe), expected)
        original_fences = [t.content for t in c.parser().parse(self.data.decode()) if t.type == "fence"]
        result_fences = [t.content for t in c.parser().parse(expected.decode()) if t.type == "fence"]
        self.assertEqual(
            [x.replace(checkout["old"], checkout["new"]) for x in original_fences], result_fences,
        )

    def test_unexpected_blob_fails(self):
        with self.assertRaises(c.Invalid):
            c.recipe_body(self.data + b"\n", self.manifest["recipe"])

    def test_transforms_only_destinations(self):
        source = "[old](old) `old` ![old](image)\n\n```sh\n[old](old)\n```\n"
        expected = "[old](https://example.org/new) `old` ![old](image)\n\n```sh\n[old](old)\n```\n"
        self.assertEqual(c.relocate_links(source, [{"old": "old", "new": "https://example.org/new", "count": 1}]), expected)

    def test_reference_link_transformation(self):
        source = "[first][ref] and [second][ref].\n\n[ref]: old \"Title\"\n"
        expected = source.replace('[ref]: old', '[ref]: https://example.org/new')
        self.assertEqual(c.relocate_links(source, [{"old": "old", "new": "https://example.org/new", "count": 2}]), expected)

    def test_duplicate_parsed_link_fails(self):
        with self.assertRaises(c.Invalid):
            c.relocate_links("[a](old) [b](old)", [{"old": "old", "new": "new", "count": 1}])

    def test_unmatched_rule_fails(self):
        with self.assertRaises(c.Invalid):
            c.relocate_links("`[a](old)`", [{"old": "old", "new": "new", "count": 1}])

    def test_unexpected_encoding_fails_closed(self):
        with self.assertRaises(c.Invalid):
            c.relocate_links("[a](old&#46;md)", [{"old": "old.md", "new": "new", "count": 1}])

    def test_checkout_duplicate_fails_even_with_fixture_hash(self):
        recipe = copy.deepcopy(self.manifest["recipe"])
        data = self.data + recipe["checkout"]["old"].encode() + b"\n"
        recipe["blob"], recipe["sha256"] = c.blob_id(data), c.sha256(data)
        with self.assertRaises(c.Invalid):
            c.recipe_body(data, recipe)

    def test_crlf_source_is_not_normalized(self):
        recipe = copy.deepcopy(self.manifest["recipe"])
        data = self.data.replace(b"\n", b"\r\n")
        recipe["blob"], recipe["sha256"] = c.blob_id(data), c.sha256(data)
        body = c.recipe_body(data, recipe)
        self.assertEqual(body.count(b"\r\n"), data.count(b"\r\n"))
        self.assertNotIn(b"\n", body.replace(b"\r\n", b""))

    def test_unsafe_paths(self):
        for path in ("../Home.md", "/Home.md", "wiki//Home.md", "wiki/./Home.md", "wiki\\Home.md", ".git/config"):
            with self.subTest(path=path), self.assertRaises(c.Invalid):
                c.safe_path(path)

    def test_duplicate_json_key_fails(self):
        with self.assertRaises(c.Invalid):
            c.load_json(b'{"schema":1,"schema":2}', "fixture")

    def test_bootstrap_home_requires_small_lf_terminated_utf8_text(self):
        invalid = ("", "Missing final newline", "CRLF\r\n", "NUL\0\n",
                   "\ud800\n", "x" * 4095 + "\n")
        for value in invalid:
            manifest = copy.deepcopy(self.manifest)
            manifest["bootstrap_home"] = value
            with self.subTest(value=repr(value)), self.assertRaises(c.Invalid):
                c.manifest(MemorySnapshot(manifest, self.data))

    def test_complete_deterministic_projection(self):
        fixture = MemorySnapshot(self.manifest, self.data)
        m, first = c.render(fixture)
        self.assertEqual(first, c.render(fixture)[1])
        self.assertEqual(set(first), {p["target"] for p in m["pages"]}
                         | {"Fedora-Recipe.md", "_Sidebar.md", "_Footer.md"})
        self.assertTrue(first["Fedora-Recipe.md"].endswith(c.recipe_body(self.data, m["recipe"])))
        for page in m["pages"]:
            self.assertEqual(first[page["target"]], fixture.files[page["source"]])
            self.assertIn((c.WIKI_URL + "/" + page["target"][:-3]).encode(), first["_Sidebar.md"])
        self.assertIn(c.BASELINE.encode(), first["_Footer.md"])
        self.assertIn(m["recipe"]["navigation"]["recovery"].encode(), first["Fedora-Recipe.md"])

    def test_worktree_preview_is_visibly_not_publishable(self):
        fixture = MemorySnapshot(self.manifest, self.data)
        fixture.worktree = True
        output = c.render(fixture)[1]
        self.assertIn(b"WORKTREE PREVIEW - NOT FOR PUBLICATION", output["Fedora-Recipe.md"])
        self.assertIn(b"WORKTREE PREVIEW - NOT FOR PUBLICATION", output["_Footer.md"])

    def test_extra_input_fails(self):
        fixture = MemorySnapshot(self.manifest, self.data)
        fixture.files["wiki/stale-mirror.md"] = b"# Not published\n"
        with self.assertRaises(c.Invalid):
            c.render(fixture)

    def test_duplicate_case_slug_fails(self):
        m = copy.deepcopy(self.manifest)
        duplicate = dict(m["pages"][0], source="wiki/home.md", target="home.md")
        m["pages"].append(duplicate)
        with self.assertRaises(c.Invalid):
            c.render(MemorySnapshot(m, self.data))

    def test_arbitrary_include_fails(self):
        m = copy.deepcopy(self.manifest)
        m["pages"][0]["source"] = "README.md"
        with self.assertRaises(c.Invalid):
            c.render(MemorySnapshot(m, self.data))


class ContentChecks(unittest.TestCase):
    def setUp(self):
        self.manifest = fixture_manifest()
        self.manifest["pages"] = [
            page for page in self.manifest["pages"]
            if page["target"] in ("Home.md", "Console-and-Recovery.md", "Install-Fedora.md")
        ]
        self.fixture = MemorySnapshot(self.manifest, c.Snapshot(ROOT, c.BASELINE).read(c.RECIPE_PATH))

    def test_metadata_all_fields(self):
        fields = ck.metadata(page_bytes(), "reference", DAY)
        self.assertEqual(set(fields), set(ck.FIELDS))

    def test_missing_or_wrong_parser_has_setup_diagnostic(self):
        with mock.patch.object(c.importlib.metadata, "version", side_effect=c.importlib.metadata.PackageNotFoundError):
            with self.assertRaisesRegex(c.Invalid, "parser missing"):
                c.parser()
        with mock.patch.object(c.importlib.metadata, "version", return_value="0.0.0"):
            with self.assertRaisesRegex(c.Invalid, "wrong parser version"):
                c.parser()

    def test_missing_metadata(self):
        for field in ck.FIELDS:
            lines = [line for line in page_bytes().decode().splitlines() if not line.startswith("**" + field + ":")]
            with self.subTest(field=field), self.assertRaises(c.Invalid):
                ck.metadata("\n".join(lines).encode(), "procedure", DAY)

    def test_metadata_in_fence_does_not_count(self):
        with self.assertRaises(c.Invalid):
            ck.metadata(b"# Test\n\n```text\n" + page_bytes() + b"\n```\n", "reference", DAY)

    def test_missing_declared_basis(self):
        data = page_bytes().replace(b"Recorded fixture/reference shape only, not a hardware result.", b"Unknown.")
        with self.assertRaises(c.Invalid):
            ck.metadata(data, "reference", DAY)

    def test_future_dates(self):
        with self.assertRaises(c.Invalid):
            ck.metadata(page_bytes().replace(b"2026-09-25", b"2099-01-01"), "reference", DAY)

    def test_duplicate_headings_github_style(self):
        data = b"# One `code` & two!\n\n## Repeat\n## Repeat\n## Repeat-1\n## Repeat\n"
        self.assertEqual(ck.headings(data), {"one-code--two", "repeat", "repeat-1", "repeat-1-1", "repeat-2"})

    def test_draft_links_resolve_locally(self):
        self.fixture.files["wiki/Home.md"] = page_bytes(extra=f"[New draft]({c.WIKI_URL}/Install-Fedora#fixture)\n")
        self.assertTrue(ck.validate(self.fixture, today=DAY).output)

    def test_missing_wiki_page_and_anchor(self):
        for url in (c.WIKI_URL + "/Missing", c.WIKI_URL + "/Install-Fedora#missing"):
            with self.subTest(url=url):
                self.fixture.files["wiki/Home.md"] = page_bytes(extra=f"[Bad]({url})\n")
                with self.assertRaises(c.Invalid):
                    ck.validate(self.fixture, today=DAY)

    def test_relative_page_link_rejected(self):
        self.fixture.files["wiki/Home.md"] = page_bytes(extra="[Bad](Install-Fedora.md)\n")
        with self.assertRaises(c.Invalid):
            ck.validate(self.fixture, today=DAY)

    def test_noncanonical_wiki_links_do_not_fall_back_to_web(self):
        for url in (c.WIKI_URL.replace("github.com", "GITHUB.COM") + "/Missing",
                    c.WIKI_URL + "%2FMissing", c.WIKI_URL.replace("/wiki", "/Wiki") + "/Missing"):
            self.fixture.files["wiki/Home.md"] = page_bytes(extra=f"[Bad]({url})\n")
            with self.subTest(url=url), self.assertRaises(c.Invalid):
                ck.validate(self.fixture, today=DAY)

    def test_missing_navigation_rejected(self):
        self.fixture.files["wiki/Home.md"] = page_bytes().replace(f"[Home]({c.WIKI_URL}/Home)".encode(), b"No navigation")
        with self.assertRaises(c.Invalid):
            ck.validate(self.fixture, today=DAY)

    def test_bare_wiki_urls_are_checked_locally(self):
        self.fixture.files["wiki/Home.md"] = page_bytes(extra=c.WIKI_URL + "/Missing\n")
        with self.assertRaises(c.Invalid):
            ck.validate(self.fixture, today=DAY)

    def test_critical_images_are_not_discovered_from_hyperlinks(self):
        checked = ck.validate(self.fixture, today=DAY)
        hrefs = {url for data in checked.output.values() for url in c.link_values(c.parser().parse(data.decode()))}
        for artifact in self.manifest["critical_artifacts"]:
            self.assertNotIn(artifact["url"], hrefs)
            self.assertIn(ck.Link("Fedora-Recipe.md", artifact["url"], "critical-artifact",
                                 artifact["sha256"], artifact["url"].rsplit("/", 1)[1]), checked.links)
            self.assertIn(ck.Link("Fedora-Recipe.md", artifact["checksum_url"], "critical-checksum",
                                 artifact["sha256"], artifact["url"].rsplit("/", 1)[1]), checked.links)

    def test_arbitrary_code_urls_are_not_network_inputs(self):
        url = "https://unreviewed.fixture.test/not-an-input"
        self.fixture.files["wiki/Home.md"] = page_bytes(extra=f"`{url}`\n\n```sh\ncurl {url}\n```\n")
        checked = ck.validate(self.fixture, today=DAY)
        self.assertNotIn(url, {link.url for link in checked.links})

    def test_critical_inventory_cannot_be_omitted_or_duplicated(self):
        for entries in ([], self.manifest["critical_artifacts"][:1],
                        [self.manifest["critical_artifacts"][0]] * 2):
            altered = copy.deepcopy(self.manifest)
            altered["critical_artifacts"] = entries
            self.fixture.files[c.MANIFEST] = c.canonical(altered)
            with self.assertRaises(c.Invalid):
                ck.validate(self.fixture, today=DAY)

    def test_critical_pins_are_bound_to_exact_public_sources(self):
        alterations = {
            "url": "https://dl.fedoraproject.org/unreviewed-fixture.raw.xz",
            "sha256": "0" * 64,
            "checksum_url": "https://checksum.fixture.test/unreviewed.sha256",
            "source": {"path": "Unlisted-fixture.txt", "blob": "0" * 40},
        }
        for field, value in alterations.items():
            altered = copy.deepcopy(self.manifest)
            altered["critical_artifacts"][0][field] = value
            self.fixture.files[c.MANIFEST] = c.canonical(altered)
            with self.subTest(field=field), self.assertRaises(c.Invalid):
                ck.validate(self.fixture, today=DAY)

    def test_resource_exception_cannot_waive_critical_image_or_metadata(self):
        checked = ck.validate(self.fixture, today=DAY)
        for link in [item for item in checked.links if item.role.startswith("critical-")]:
            entry = {"kind": "resource", "page": "Resources.md", "url": link.url, "reason": "Fixture only",
                     "reviewer": "Fixture Human", "reviewed": "2026-09-26", "expires": "2026-09-28"}
            external = checked.links + [ck.Link("Resources.md", link.url, "resource")]
            with self.subTest(role=link.role), self.assertRaises(c.Invalid):
                ck.resource_exceptions(c.canonical({"schema": 1, "exceptions": [entry]}),
                                       self.manifest, external, DAY)

    def test_reference_style_wiki_link(self):
        self.fixture.files["wiki/Home.md"] = page_bytes(extra=f"[Next][target]\n\n[target]: {c.WIKI_URL}/Install-Fedora\n")
        ck.validate(self.fixture, today=DAY)

    def test_link_shaped_code_is_not_a_page_link(self):
        self.fixture.files["wiki/Home.md"] = page_bytes(extra="```\n[not a link](Missing.md)\n```\n")
        ck.validate(self.fixture, today=DAY)

    def test_repository_link_uses_exact_baseline(self):
        self.assertTrue(ck.repo_link(self.fixture, c.REPO_WEB + "/blob/" + c.BASELINE + "/README.md#license"))
        with self.assertRaises(c.Invalid):
            ck.repo_link(self.fixture, c.REPO_WEB + "/blob/" + c.BASELINE + "/No-such-file.md")

    def test_repository_lines_checked_without_network(self):
        url = c.REPO_WEB + "/blob/" + c.BASELINE + "/README.md"
        self.assertTrue(ck.repo_link(self.fixture, url + "#L1-L2"))
        with self.assertRaises(c.Invalid):
            ck.repo_link(self.fixture, url + "#L999999")

    def test_raw_html_and_binaries_rejected(self):
        for extra in ('<script>not executed</script>\n', "![image](https://example.org/image.png)\n"):
            self.fixture.files["wiki/Home.md"] = page_bytes(extra=extra)
            with self.assertRaises(c.Invalid):
                ck.validate(self.fixture, today=DAY)

    def test_public_recipe_generic_examples_are_safe(self):
        ck.require_private_safe(self.fixture.read(c.RECIPE_PATH), c.RECIPE_PATH, approved_blob=c.RECIPE_BLOB)
        ck.require_private_safe(b"ssh fedora@127.0.0.1\nPublic hash " + b"a" * 64, "fixture")

    def test_sensitive_fixture_is_not_echoed(self):
        token = "ghp_" + "A" * 36
        with self.assertRaises(c.Invalid) as raised:
            ck.require_private_safe(page_bytes(extra=token), "wiki/Home.md")
        self.assertNotIn(token, str(raised.exception))
        self.assertIn("access-token", str(raised.exception))

    def test_source_bound_exception_and_changed_blob(self):
        data = page_bytes(extra="/home/" + "fixture-placeholder\n")
        finding = ck.privacy(data, "wiki/Home.md")[0]
        entry = {**finding, "reason": "Reserved fixture example, test only",
                 "reviewer": "Fixture Human (test only)", "reviewed": "2026-09-26"}
        self.fixture.files["wiki/Home.md"] = data
        self.manifest["validation_exceptions"] = [entry]
        self.fixture.files[c.MANIFEST] = c.canonical(self.manifest)
        ck.validate(self.fixture, today=DAY)
        self.fixture.files["wiki/Home.md"] += b"\nChanged\n"
        with self.assertRaises(c.Invalid):
            ck.validate(self.fixture, today=DAY)

    def test_exception_does_not_waive_other_occurrence(self):
        data = ("/home/" + "fixture-placeholder\n").encode()
        finding = ck.privacy(data, "wiki/Home.md")[0]
        entry = {**finding, "reason": "Test only", "reviewer": "Fixture Human", "reviewed": "2026-09-26"}
        self.assertTrue(ck.privacy(data * 2, "wiki/Home.md", [entry]))
        self.assertTrue(ck.privacy(data, "wiki/Install-Fedora.md", [entry]))

    def test_malformed_validation_exception(self):
        for entry in ({"rule": "all", "reason": "ignore"}, {"rule": "access-token"}):
            self.manifest["validation_exceptions"] = [entry]
            with self.assertRaises(c.Invalid):
                ck.validation_exceptions(self.manifest, self.fixture, DAY)

    def test_resource_exception_exact_scope(self):
        url = "https://resource.example.test/project"
        entry = {"kind": "resource", "page": "Resources.md", "url": url, "reason": "Fixture outage only",
                 "reviewer": "Fixture Human (test only)", "reviewed": "2026-09-26", "expires": "2026-09-28"}
        data = c.canonical({"schema": 1, "exceptions": [entry]})
        links = [ck.Link("Resources.md", url, "resource")]
        self.assertEqual(ck.resource_exceptions(data, self.manifest, links, DAY), [entry])
        for changed in (links + [ck.Link("Home.md", url, "source")],
                        [ck.Link("Elsewhere.md", url, "resource")]):
            with self.assertRaises(c.Invalid):
                ck.resource_exceptions(data, self.manifest, changed, DAY)
        with self.assertRaises(c.Invalid):
            ck.resource_exceptions(data, self.manifest, links, date(2026, 9, 29))

    def test_explicit_kvm_matrix_and_changed_flags(self):
        headers = "| Result | Host kernel | QEMU | Guest | CPU | PLIC/AIA | vCPUs | Storage | Network | Source | Nonclaims |\n"
        separator = "| " + " | ".join(["---"] * 11) + " |\n"
        cells = ["Fedora", "`7.3.0-rc4-k3-kvm-host-a1`", "10.2.2", "Fedora 44",
                 "`host,svpbmt=false,zicbom=false,zicbop=false,zicboz=false`",
                 "PLIC", "4", "not recorded", "not recorded", "public record", "not recorded"]
        row = "| " + " | ".join(cells) + " |\n"
        data = (headers + separator + row * 2).encode()
        ck.evidence_shape("KVM-and-QEMU.md", data)
        with self.assertRaises(c.Invalid):
            ck.evidence_shape("KVM-and-QEMU.md", data.replace(b"svpbmt=false", b"svpbmt=true"))
        with self.assertRaises(c.Invalid):
            ck.evidence_shape("KVM-and-QEMU.md", b"# No matrix\n")

    def test_missing_performed_contribution_examples(self):
        with self.assertRaises(c.Invalid):
            ck.evidence_shape("Contributing-Upstream.md", b"# Only generic contribution links\n")


class NetworkChecks(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.resolutions = []
        self.responses = [h.Response(200, {})]
        self.special = mock.patch.object(h, "example_host", return_value=False)
        self.special.start()
        self.addCleanup(self.special.stop)
        self.checker = h.Checker(self.resolver, self.request)
        self.url = "https://public.fixture.test/page"

    def resolver(self, host):
        self.resolutions.append(host)
        return ["93.184.216.34"]

    def request(self, method, url, address, deadline):
        self.requests.append((method, url, address))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def test_head_only_success_and_ip_binding(self):
        self.assertEqual(self.checker.one(self.url, "source"), "available-head")
        self.assertEqual(self.requests, [("HEAD", self.url, "93.184.216.34")])
        self.assertEqual(len(self.resolutions), 1)

    def test_redirect_rechecked(self):
        self.responses = [h.Response(302, {"location": "/next"}), h.Response(200, {})]
        self.checker.one(self.url, "source")
        self.assertEqual(len(self.resolutions), 2)
        self.assertEqual(self.requests[-1][1], "https://public.fixture.test/next")

    def test_private_redirect_never_requested(self):
        self.responses = [h.Response(302, {"location": "https://127.0.0.1/private"})]
        self.checker.resolver = lambda host: ["127.0.0.1"] if host == "127.0.0.1" else ["93.184.216.34"]
        with self.assertRaises(c.Invalid):
            self.checker.one(self.url, "source")
        self.assertEqual(len(self.requests), 1)

    def test_mixed_private_and_public_dns_rejected(self):
        self.checker.resolver = lambda host: ["93.184.216.34", ".".join(map(str, (10, 0, 0, 1)))]
        with self.assertRaises(c.Invalid):
            self.checker.one(self.url, "source")
        self.assertFalse(self.requests)

    def test_dual_stack_attempts_cover_both_address_families(self):
        self.checker.resolver = lambda host: [
            "2001:4860:4860::8888", "93.184.216.35",
            "2001:4860:4860::8844", "93.184.216.34",
        ]
        self.responses = [
            h.Unavailable("fixture first IPv4 unavailable"),
            h.Unavailable("fixture IPv6 unavailable"),
            h.Response(200, {}),
        ]
        self.assertEqual(self.checker.one(self.url, "source"), "available-head")
        self.assertEqual([item[2] for item in self.requests],
                         ["93.184.216.34", "2001:4860:4860::8844", "93.184.216.35"])

    def test_rebinding_cannot_change_socket_target(self):
        connection = h.PinnedHTTPS("public.fixture.test", "93.184.216.34", 1000)
        raw = mock.Mock()
        context = mock.Mock()
        connection._context = context
        with mock.patch.object(h.socket, "socket", return_value=raw), mock.patch.object(h.time, "monotonic", return_value=1):
            connection.connect()
        raw.connect.assert_called_once_with(("93.184.216.34", 443))
        context.wrap_socket.assert_called_once_with(raw, server_hostname="public.fixture.test")

    def test_example_endpoints_never_resolved(self):
        self.special.stop()
        self.assertEqual(self.checker.one("https://example.org/doc", "resource"), "example-not-requested")
        self.assertFalse(self.resolutions)
        self.assertFalse(self.requests)

    def test_local_names_never_resolved(self):
        for url in ("https://localhost/x", "https://host.local/x", "https://host.internal/x"):
            with self.subTest(url=url), self.assertRaises(c.Invalid):
                self.checker.one(url, "source")
        self.assertFalse(self.resolutions)

    def test_bounded_timeout_and_rate_limit_retry(self):
        attempts = h.RETRIES + 1
        for responses in ([h.Unavailable("fixture timeout")] * attempts,
                          [h.Response(429, {})] * attempts):
            self.responses = list(responses)
            self.requests.clear()
            with self.assertRaises(h.Unavailable):
                self.checker.one(self.url, "source")
            self.assertEqual(len(self.requests), attempts)

    def test_text_only_get_fallback(self):
        self.responses = [h.Response(405, {}), h.Response(200, {"content-type": "text/html"}, b"ok")]
        self.assertEqual(self.checker.one(self.url, "source"), "available-get")
        self.assertEqual([x[0] for x in self.requests], ["HEAD", "GET"])

    def test_binary_or_untyped_get_response_refused(self):
        for mime in ("application/octet-stream", ""):
            self.responses = [h.Response(405, {}), h.Response(200, {"content-type": mime}, b"fixture")]
            with self.assertRaises(c.Invalid):
                self.checker.one(self.url, "source")

    def test_dns_timeout_has_bounded_failure(self):
        self.checker.resolver = mock.Mock(side_effect=subprocess.TimeoutExpired("fixture resolver", h.DNS_TIMEOUT))
        with self.assertRaises(h.Unavailable):
            self.checker.one(self.url, "source")
        self.assertFalse(self.requests)

    def test_archive_never_gets_downloaded(self):
        self.responses = [h.Response(405, {})]
        with self.assertRaises(h.Unavailable):
            self.checker.one("https://public.fixture.test/image.raw.xz", "artifact")
        self.assertEqual([x[0] for x in self.requests], ["HEAD"])

    def test_critical_image_has_no_get_even_after_extensionless_redirect(self):
        self.responses = [h.Response(302, {"location": "/download"}), h.Response(405, {})]
        with self.assertRaises(h.Unavailable):
            self.checker.one(self.url, "critical-artifact")
        self.assertEqual([x[0] for x in self.requests], ["HEAD", "HEAD"])

    def test_critical_image_transport_never_reads_binary_body(self):
        reply = mock.Mock(status=200)
        reply.getheaders.return_value = [("Content-Type", "application/x-xz"), ("Content-Length", "4096000000")]
        connection = mock.Mock()
        connection.getresponse.return_value = reply
        with mock.patch.object(h, "PinnedHTTPS", return_value=connection):
            response = h.transport("HEAD", "https://public.fixture.test/fixture.raw.xz", "93.184.216.34", 1000)
        self.assertEqual(response.body, b"")
        connection.request.assert_called_once_with("HEAD", "/fixture.raw.xz", headers=mock.ANY)
        reply.read.assert_not_called()

    def test_critical_image_requires_a_nonempty_image_entity(self):
        for response in (h.Response(204, {}), h.Response(200, {"content-length": "0"}),
                         h.Response(200, {"content-type": "text/html"})):
            self.responses = [response]
            with self.assertRaises(c.Invalid):
                self.checker.one(self.url, "critical-artifact")

    def test_critical_checksum_accepts_only_the_exact_record(self):
        filename, digest = "fixture.qcow2", "a" * 64
        url = "https://public.fixture.test/" + filename + ".sha256"
        data = (digest + "  " + filename + "\n").encode()
        self.responses = [h.Response(200, {"content-type": "application/octet-stream"}, data)]
        self.assertEqual(self.checker.one(url, "critical-checksum", filename=filename, expected_sha256=digest),
                         "checksum-matches")
        self.assertEqual(self.requests, [("CHECKSUM", url, "93.184.216.34")])
        for bad in (data.replace(b"a", b"b", 1), data * 2, data.replace(b"fixture.qcow2", b"other.qcow2"),
                    b"<html>Fixture error</html>", b"", b"\xff"):
            with self.subTest(data_kind=len(bad)), self.assertRaises(c.Invalid):
                h.verify_checksum(bad, filename, digest)

    def test_critical_checksum_has_smaller_encoded_and_decoded_bounds(self):
        for data, encoding in ((b"x" * (h.MAX_CHECKSUM + 1), "identity"),
                               (gzip.compress(b"x" * (h.MAX_CHECKSUM + 1)), "gzip")):
            with self.assertRaises(c.Invalid):
                h.decode_body(data, encoding, h.MAX_CHECKSUM)
        with self.assertRaises(c.Invalid):
            h.verify_checksum(b"x" * (h.MAX_CHECKSUM + 1), "fixture.qcow2", "a" * 64)

    def test_checksum_transport_uses_bounded_get_despite_server_mime(self):
        filename, digest = "fixture.raw.xz", "a" * 64
        data = (digest + "  " + filename + "\n").encode()
        reply = mock.Mock(status=200)
        reply.getheaders.return_value = [("Content-Type", "application/x-xz"), ("Content-Length", str(len(data)))]
        reply.read.return_value = data
        connection = mock.Mock()
        connection.getresponse.return_value = reply
        with mock.patch.object(h, "PinnedHTTPS", return_value=connection):
            response = h.transport("CHECKSUM", "https://public.fixture.test/" + filename + ".sha256",
                                   "93.184.216.34", 1000)
        self.assertEqual(response.body, data)
        connection.request.assert_called_once_with("GET", "/" + filename + ".sha256", headers=mock.ANY)
        reply.read.assert_called_once_with(h.MAX_CHECKSUM + 1)

    def test_checksum_transport_refuses_large_body_before_reading(self):
        reply = mock.Mock(status=200)
        reply.getheaders.return_value = [("Content-Type", "application/octet-stream"),
                                         ("Content-Length", str(h.MAX_CHECKSUM + 1))]
        connection = mock.Mock()
        connection.getresponse.return_value = reply
        with mock.patch.object(h, "PinnedHTTPS", return_value=connection), self.assertRaises(c.Invalid):
            h.transport("CHECKSUM", "https://public.fixture.test/fixture.qcow2.sha256", "93.184.216.34", 1000)
        reply.read.assert_not_called()

    def test_checksum_redirect_cannot_fetch_image_or_private_endpoint(self):
        filename, digest = "fixture.qcow2", "a" * 64
        url = "https://public.fixture.test/" + filename + ".sha256"
        for location in ("/" + filename, "https://127.0.0.1/" + filename + ".sha256"):
            self.responses = [h.Response(302, {"location": location})]
            self.requests.clear()
            self.checker.resolver = lambda host: ["127.0.0.1"] if host == "127.0.0.1" else ["93.184.216.34"]
            with self.assertRaises(c.Invalid):
                self.checker.one(url, "critical-checksum", filename=filename, expected_sha256=digest)
            self.assertEqual(len(self.requests), 1)

    def test_critical_checksum_public_redirect_preserves_binding(self):
        filename, digest = "fixture.qcow2", "a" * 64
        url = "https://public.fixture.test/" + filename + ".sha256"
        target = "https://mirror.fixture.test/checksums/" + filename + ".sha256"
        self.responses = [h.Response(302, {"location": target}),
                          h.Response(200, {}, (digest + "  " + filename + "\n").encode())]
        self.assertEqual(self.checker.one(url, "critical-checksum", filename=filename, expected_sha256=digest),
                         "checksum-matches")
        self.assertEqual([item[0] for item in self.requests], ["CHECKSUM", "CHECKSUM"])
        self.assertEqual(len(self.resolutions), 2)

    def test_resource_exception_never_waives_critical_network_failure(self):
        for role in ("critical-artifact", "critical-checksum"):
            url = "https://public.fixture.test/fixture.qcow2" + (".sha256" if role == "critical-checksum" else "")
            self.responses = [h.Response(404, {})]
            link = ck.Link("Resources.md", url, role, "a" * 64, "fixture.qcow2")
            exception = {"page": "Resources.md", "url": url, "reason": "Fixture only"}
            with self.subTest(role=role), self.assertRaises(c.Invalid):
                self.checker.all([link], [exception])

    def test_binary_get_redirect_refused(self):
        self.responses = [h.Response(405, {}), h.Response(302, {"location": "/model.gguf"})]
        with self.assertRaises(c.Invalid):
            self.checker.one(self.url, "source")
        self.assertEqual(len(self.requests), 2)

    def test_redirect_limit(self):
        self.responses = [h.Response(302, {"location": "/redirect" + str(i)}) for i in range(5)]
        with self.assertRaises(c.Invalid):
            self.checker.one(self.url, "source")
        self.assertEqual(len(self.requests), h.MAX_REDIRECTS + 1)

    def test_secret_query_never_requested_or_echoed(self):
        url = self.url + "?token=" + "fixture-value"
        with self.assertRaises(c.Invalid) as raised:
            self.checker.one(url, "source")
        self.assertNotIn(url, str(raised.exception))
        self.assertFalse(self.requests)

    def test_encoded_query_and_credentials_refused(self):
        for url in (self.url + "?%74oken=fixture", "https://" + "user:fixture@" + "public.fixture.test/page",
                    "http://public.fixture.test/page", "https://public.fixture.test:8443/page"):
            with self.subTest(url=url), self.assertRaises(c.Invalid):
                self.checker.one(url, "source")
        self.assertFalse(self.requests)

    def test_oversized_decoded_and_encoded_responses(self):
        for data, encoding in ((b"x" * (h.MAX_BODY + 1), "identity"),
                               (gzip.compress(b"x" * (h.MAX_BODY + 1)), "gzip")):
            with self.assertRaises(c.Invalid):
                h.decode_body(data, encoding)
        self.assertEqual(h.decode_body(gzip.compress(b"small text"), "gzip"), b"small text")

    def test_slow_stream_has_total_deadline(self):
        sock = mock.Mock()
        sock.recv_into.return_value = 1
        reader = h.DeadlineReader(sock, 10)
        with mock.patch.object(h.time, "monotonic", side_effect=[9, 11]):
            self.assertEqual(reader.readinto(bytearray(1)), 1)
            with self.assertRaises(TimeoutError):
                reader.readinto(bytearray(1))
        sock.settimeout.assert_called_once_with(1)

    def test_unavailable_is_not_reported_as_success(self):
        self.responses = [h.Response(403, {})]
        with self.assertRaises(c.Invalid):
            self.checker.all([ck.Link("Home.md", self.url, "source")], [])

    def test_resource_only_exception_reporting(self):
        self.responses = [h.Response(404, {})]
        exception = {"page": "Resources.md", "url": self.url, "reason": "Fixture only",
                     "reviewer": "Fixture Human", "reviewed": "2026-09-26", "expires": "2026-09-28"}
        report = self.checker.all([ck.Link("Resources.md", self.url, "resource")], [exception])
        self.assertEqual(report[0]["status"], "reviewed-resource-exception")
        self.responses = [h.Response(404, {})]
        with self.assertRaises(c.Invalid):
            self.checker.all([ck.Link("Resources.md", self.url, "artifact")], [exception])


class LocalRemotes(p.PublicRemotes):
    def __init__(self, source, wiki):
        self.paths = {c.SOURCE_URL: source, c.WIKI_REPO: wiki}
        self.pushes = []
        self.before_push = None
        self.fail_push = False

    def network_git(self, git, *args, hooks=False, wiki_credentials=False):
        if wiki_credentials != (args[0] == "push"):
            raise AssertionError("fixture credential scope differs from production")
        actual = [str(self.paths.get(arg, arg)) for arg in args]
        self.assert_local(actual)
        if args[0] == "push":
            self.pushes.append(args)
            if self.before_push:
                self.before_push()
            if self.fail_push:
                raise c.Invalid("fixture interrupted push")
        return git.run(*actual)

    def assert_local(self, args):
        if any(arg in (c.SOURCE_URL, c.WIKI_REPO) or arg.startswith(("https://", "ssh://", "git@")) for arg in args):
            raise AssertionError("fixture attempted a nonlocal Git operation")


class SystemExecutableTests(unittest.TestCase):
    def test_interpreter_path_prefers_repository_venv_launcher(self):
        with tempfile.TemporaryDirectory(prefix="wiki-python-", dir=fixture_output()) as temporary:
            root = Path(temporary)
            (root / ".wiki-venv/bin").mkdir(parents=True)
            launcher = root / ".wiki-venv/bin/python"
            executable = Path(sys.executable).resolve()
            launcher.symlink_to(executable)
            with mock.patch.object(p.sys, "executable", str(executable)):
                self.assertEqual(p.interpreter_path(root), str(launcher))

    def test_interpreter_path_rejects_unrelated_or_symlinked_repository_venv(self):
        with tempfile.TemporaryDirectory(prefix="wiki-python-", dir=fixture_output()) as temporary:
            root = Path(temporary)
            (root / ".wiki-venv/bin").mkdir(parents=True)
            launcher = root / ".wiki-venv/bin/python"
            launcher.write_text("#!/bin/sh\nexit 0\n")
            launcher.chmod(0o755)
            with self.assertRaisesRegex(c.Invalid, "run the wiki tool"):
                p.interpreter_path(root)
            moved = root / "moved-venv"
            (root / ".wiki-venv").rename(moved)
            (root / ".wiki-venv").symlink_to(moved, target_is_directory=True)
            with self.assertRaisesRegex(c.Invalid, "missing or symlinked"):
                p.interpreter_path(root)

    def test_system_tool_identities_are_root_owned_absolute_and_hashed(self):
        identities = c.system_executable_identities()
        self.assertEqual(set(identities), {"git", "gh"})
        for name, identity in identities.items():
            with self.subTest(name=name):
                self.assertEqual(identity["path"], "/usr/bin/" + name)
                self.assertEqual(identity["uid"], 0)
                self.assertRegex(identity["sha256"], r"^[0-9a-f]{64}$")
                self.assertFalse(int(identity["mode"], 8) & 0o022)
                self.assertEqual([entry["path"] for entry in identity["ancestors"]],
                                 ["/", "/usr", "/usr/bin"])
                self.assertTrue(all(entry["uid"] == 0 and not int(entry["mode"], 8) & 0o022
                                    for entry in identity["ancestors"]))

    def test_user_owned_and_symlinked_executable_candidates_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="unsafe-tools-", dir=fixture_output()) as temporary:
            directory = Path(temporary)
            executable = directory / "git"
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
            with self.assertRaisesRegex(c.Invalid, "root-owned"):
                c.inspect_system_executable(executable, "git")
            executable.unlink()
            executable.symlink_to("/usr/bin/git")
            original = c._safe_system_node

            def allow_fixture_ancestors(info, *, directory):
                return True if directory else original(info, directory=directory)

            with mock.patch.object(c, "_safe_system_node", side_effect=allow_fixture_ancestors), \
                    self.assertRaisesRegex(c.Invalid, "root-owned"):
                c.inspect_system_executable(executable, "git")

    def test_git_ignores_hostile_path_and_executes_verified_absolute_binary(self):
        with tempfile.TemporaryDirectory(prefix="hostile-path-", dir=fixture_output()) as temporary:
            directory = Path(temporary)
            marker = directory / "PATH-GIT-RAN"
            fake = directory / "git"
            fake.write_text("#!/bin/sh\n: > " + shlex.quote(str(marker)) + "\nexit 99\n")
            fake.chmod(0o755)
            environment = {
                "PATH": str(directory),
                "GH_TOKEN": "fixture-token-must-not-cross-the-git-boundary",
                "HTTPS_PROXY": "http://proxy.fixture.invalid",
            }
            with mock.patch.dict(os.environ, environment, clear=True):
                top = c.Git(ROOT).run("rev-parse", "--show-toplevel").decode().strip()
            self.assertEqual(top, str(ROOT))
            self.assertFalse(marker.exists())


class PublicRemoteCommandTests(unittest.TestCase):
    SECRET = "fixture-token-must-not-cross-the-git-boundary"

    @staticmethod
    def git():
        git = mock.Mock()
        git.root = Path("/fixture/wiki-publication")

        def run(*args, **_kwargs):
            if args == ("config", "--local", "--list", "--name-only"):
                return b""
            if args == ("config", "--get-all", "remote.origin.url"):
                return (c.WIKI_REPO + "\n").encode()
            if args == ("config", "--get-all", "remote.origin.pushurl"):
                return b""
            raise AssertionError(f"unexpected fixture Git command: {args!r}")

        git.run.side_effect = run
        return git

    @classmethod
    def environment(cls):
        return {
            "PATH": "/fixture/bin",
            "HOME": "/fixture/home",
            "HTTPS_PROXY": "http://proxy.fixture.invalid",
            "no_proxy": "fixture.invalid",
            "GIT_ASKPASS": "/fixture/askpass",
            "SSH_ASKPASS": "/fixture/ssh-askpass",
            "GH_TOKEN": cls.SECRET,
            "GITHUB_TOKEN": cls.SECRET,
            "GH_ENTERPRISE_TOKEN": cls.SECRET,
            "GITHUB_ENTERPRISE_TOKEN": cls.SECRET,
        }

    def assert_sanitized_environment(self, env, *, credentials=False):
        self.assertEqual(env["PATH"], c.SYSTEM_PATH)
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertFalse(any(key.lower().endswith("_proxy") for key in env))
        self.assertFalse({"GIT_ASKPASS", "SSH_ASKPASS"} & set(env))
        self.assertFalse(p.GITHUB_TOKEN_ENV & {key.upper() for key in env})
        self.assertNotIn(self.SECRET, "\0".join(env.values()))
        self.assertEqual(env.get("HOME"), "/fixture/home" if credentials else None)

    def assert_network_guardrails(self, command):
        for option in (
            "protocol.allow=never",
            "protocol.https.allow=always",
            "http.sslVerify=true",
            "http.followRedirects=false",
            "credential.helper=",
        ):
            self.assertIn(option, command)

    def test_read_operations_reset_credentials_without_invoking_gh(self):
        completed = subprocess.CompletedProcess([], 0, stdout=b"fixture refs\n", stderr=b"")
        operations = (
            ("ls-remote", "--symref", "--", c.WIKI_REPO),
            ("fetch", "--no-tags", "--", c.SOURCE_URL, c.SOURCE_BRANCH),
        )
        with mock.patch.dict(os.environ, self.environment(), clear=True), \
                mock.patch.object(c, "system_executable_path", wraps=c.system_executable_path) as executable, \
                mock.patch.object(p.subprocess, "run", return_value=completed) as run:
            output = [
                p.PublicRemotes().network_git(self.git(), *operation)
                for operation in operations
            ]
        self.assertEqual(output, [completed.stdout, completed.stdout])
        self.assertNotIn("gh", [call.args[0] for call in executable.call_args_list])
        self.assertEqual(run.call_count, len(operations))
        for operation, call in zip(operations, run.call_args_list):
            command = call.args[0]
            env = call.kwargs["env"]
            self.assertEqual(command[0], "/usr/bin/git")
            self.assertEqual(command[-len(operation):], list(operation))
            self.assert_network_guardrails(command)
            self.assertFalse(any(arg.startswith("credential.https://github.com.helper=") for arg in command))
            self.assertIn("core.hooksPath=/dev/null", command)
            self.assertNotIn(self.SECRET, "\0".join(command))
            self.assertEqual(call.kwargs["timeout"], p.GIT_READ_TIMEOUT)
            self.assert_sanitized_environment(env)

    def test_push_adds_only_verified_github_helper_and_keeps_hooks(self):
        with tempfile.TemporaryDirectory(prefix="hostile-helper-path-", dir=fixture_output()) as temporary:
            directory = Path(temporary)
            for name in ("git", "gh"):
                fake = directory / name
                fake.write_text("#!/bin/sh\nexit 99\n")
                fake.chmod(0o755)
            completed = subprocess.CompletedProcess([], 0, stdout=b"ok\n", stderr=b"")
            environment = {**self.environment(), "PATH": str(directory)}
            with mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch.object(p.subprocess, "run", return_value=completed) as run:
                p.PublicRemotes().push(self.git(), "a" * 40, "refs/heads/master")
        command = run.call_args.args[0]
        env = run.call_args.kwargs["env"]
        reset = command.index("credential.helper=")
        helper = "credential.https://github.com.helper=!" + shlex.quote(
            c.system_executable_path("gh")
        ) + " auth git-credential"
        self.assert_network_guardrails(command)
        self.assertEqual(command[0], "/usr/bin/git")
        self.assertEqual(command.count(helper), 1)
        self.assertLess(reset, command.index(helper))
        self.assertNotIn("core.hooksPath=/dev/null", command)
        self.assertEqual(command[-5:], [
            "push", "--porcelain", "--", c.WIKI_REPO,
            "a" * 40 + ":refs/heads/master",
        ])
        self.assertFalse(any("extraHeader" in arg or "Authorization" in arg for arg in command))
        self.assertNotIn(self.SECRET, "\0".join(command))
        self.assertEqual(run.call_args.kwargs["timeout"], p.GIT_PUSH_TIMEOUT)
        self.assertGreater(p.GIT_PUSH_TIMEOUT, p.GIT_READ_TIMEOUT)
        self.assert_sanitized_environment(env, credentials=True)

    def test_push_requires_trusted_gh_without_exposing_environment(self):
        git_path = c.system_executable_path("git")

        def unavailable(name):
            if name == "gh":
                raise c.Invalid("fixture unsafe GitHub CLI")
            return git_path

        with mock.patch.dict(os.environ, self.environment(), clear=True), \
                mock.patch.object(c, "system_executable_path", side_effect=unavailable), \
                mock.patch.object(p.subprocess, "run") as run:
            with self.assertRaisesRegex(c.Invalid, "trusted system GitHub CLI") as raised:
                p.PublicRemotes().push(self.git(), "a" * 40, "refs/heads/master")
            self.assertNotIn(self.SECRET, str(raised.exception))
            run.assert_not_called()

    def test_push_failure_suppresses_remote_and_helper_output(self):
        failed = subprocess.CompletedProcess(
            [], 1, stdout=self.SECRET.encode(), stderr=self.SECRET.encode(),
        )
        with mock.patch.dict(os.environ, self.environment(), clear=True), \
                mock.patch.object(p.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(c.Invalid, "public Git push failed") as raised:
                p.PublicRemotes().push(self.git(), "a" * 40, "refs/heads/master")
        self.assertNotIn(self.SECRET, str(raised.exception))

    def test_credentials_and_hooks_are_restricted_to_exact_wiki_push(self):
        attempts = (
            (("ls-remote", "--", c.WIKI_REPO), True, True),
            (("push", "--porcelain", "--", c.WIKI_REPO, "a" * 40 + ":refs/heads/master"), False, True),
            (("push", "--porcelain", "--", c.SOURCE_URL, "a" * 40 + ":refs/heads/main"), True, True),
            (("push", "--porcelain", "--", c.WIKI_REPO, "+a" * 40 + ":refs/heads/master"), True, True),
        )
        for args, hooks, credentials in attempts:
            with self.subTest(args=args), mock.patch.object(p.subprocess, "run") as run, \
                    self.assertRaisesRegex(c.Invalid, "exact approved wiki push|one exact reviewed"):
                p.PublicRemotes().network_git(
                    self.git(), *args, hooks=hooks, wiki_credentials=credentials,
                )
            run.assert_not_called()

    def test_repository_transport_credentials_are_rejected_before_network(self):
        git = self.git()
        git.run.side_effect = lambda *args, **_kwargs: (
            b"credential.helper\n"
            if args == ("config", "--local", "--list", "--name-only")
            else b""
        )
        with mock.patch.object(p.subprocess, "run") as run, \
                self.assertRaisesRegex(c.Invalid, "transport overrides"):
            p.PublicRemotes().network_git(git, "ls-remote", "--", c.WIKI_REPO)
        run.assert_not_called()


class FixtureOnline(h.Checker):
    def __init__(self):
        self.requests = []
        self.unavailable = set()
        self.bad_checksums = set()
        self.artifacts = {item["checksum_url"]: item for item in fixture_manifest()["critical_artifacts"]}
        super().__init__(resolver=lambda host: ["93.184.216.34"], request=self.request)

    def request(self, method, url, address, deadline):
        self.requests.append((method, url))
        if url in self.unavailable:
            return h.Response(404, {})
        if method == "CHECKSUM":
            item = self.artifacts[url]
            digest = "0" * 64 if url in self.bad_checksums else item["sha256"]
            data = (digest + "  " + item["url"].rsplit("/", 1)[1] + "\n").encode()
            return h.Response(200, {"content-type": "application/octet-stream",
                                    "content-length": str(len(data))}, data)
        return h.Response(200, {"content-type": "application/octet-stream", "content-length": "4096000000"})


class GitFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wiki-case-", dir=fixture_output())
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "source"
        self.root.mkdir()
        self.git = c.Git(self.root)
        self.git.run("init", "-q")
        self.git.run("config", "user.name", "Fixture Human")
        self.git.run("config", "user.email", "fixture@example.invalid")
        self.git.run("fetch", "-q", "--no-tags", "--", str(ROOT), c.BASELINE)
        self.git.run("checkout", "-q", "-b", "main", c.BASELINE)
        for path in p.TOOL_PATHS:
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(c.regular_read(TOOL_ROOT, path))
            dest.chmod(0o755 if path == ".githooks/pre-push" else 0o644)
        self.manifest = fixture_manifest()
        self.manifest["pages"] = [page for page in self.manifest["pages"]
                                  if page["target"] in
                                  ("Home.md", "Console-and-Recovery.md", "Install-Fedora.md")]
        self.manifest["pages"].append({"source": "wiki/Extra.md", "target": "Extra.md", "title": "Extra",
                                      "section": "Resources", "kind": "resources"})
        (self.root / "wiki").mkdir()
        for page in self.manifest["pages"]:
            (self.root / page["source"]).write_bytes(manifest_page_bytes(page))
        (self.root / c.MANIFEST).write_bytes(c.canonical(self.manifest))
        (self.root / c.EXCEPTIONS).write_bytes(b'{"schema":1,"exceptions":[]}\n')
        with (self.root / ".gitignore").open("a") as stream:
            stream.write("\n/.wiki-build/\n/.wiki-publish/\n/.wiki-venv/\n")
        self.initial = self.commit("Fixture canonical source")
        self.source_remote = self.base / "source.git"
        self.source_remote.mkdir()
        c.Git(self.source_remote).run("init", "--bare", "-q")
        c.Git(self.source_remote).run("symbolic-ref", "HEAD", "refs/heads/main")
        self.git.run("push", "-q", "--", str(self.source_remote), "main")
        self.git.run("config", "remote.origin.url", c.SOURCE_URL)
        self.wiki_remote = self.base / "wiki.git"
        self.wiki_remote.mkdir()
        c.Git(self.wiki_remote).run("init", "--bare", "-q")
        c.Git(self.wiki_remote).run("symbolic-ref", "HEAD", "refs/heads/master")
        seed = self.base / "wiki-seed"
        seed.mkdir()
        self.seed = c.Git(seed)
        self.seed.run("init", "-q", "-b", "master")
        self.seed.run("config", "user.name", "Fixture Human")
        self.seed.run("config", "user.email", "fixture@example.invalid")
        (seed / "Home.md").write_text(self.manifest["bootstrap_home"])
        self.seed.run("add", "--", "Home.md")
        self.seed.run("commit", "-q", "-m", "Fixture bootstrap")
        self.bootstrap = self.seed.commit("HEAD")
        self.seed.run("push", "-q", "--", str(self.wiki_remote), "master")
        self.remote = LocalRemotes(self.source_remote, self.wiki_remote)
        self.online = FixtureOnline()
        self.external_configs = mock.patch.object(p, "external_git_config_paths", return_value=())
        self.external_configs.start()
        self.addCleanup(self.external_configs.stop)
        self.day = mock.patch.object(p, "utc_day", return_value=DAY)
        self.day.start()
        self.addCleanup(self.day.stop)
        with mock.patch.object(p, "run_tests"), mock.patch.object(p, "effective_hooks", return_value=""):
            self.bundle = p.install_hook(self.root, self.initial)
        self.trust = p.read_bundle(self.bundle)

    def commit(self, message="Fixture change"):
        self.git.run("add", "-A")
        self.git.run("commit", "-q", "--allow-empty", "-m", message)
        return self.git.commit("HEAD")

    def public_source(self, oid=None):
        self.git.run("push", "-q", "--", str(self.source_remote), (oid or self.git.commit("HEAD")) + ":refs/heads/main")

    def prepare(self, source=None, adopt=True):
        return p.prepare(self.root, source or self.git.commit("HEAD"), self.bootstrap if adopt else None,
                         remote=self.remote, checker=self.online)

    def publish(self, prepared):
        return p.publish(self.root, prepared[0], prepared[1], remote=self.remote, checker=self.online)

    def updates(self, new, ref="refs/heads/topic", old=p.ZERO):
        return f"{ref} {new} {ref} {old}\n".encode()

    def gate(self, data, trust=None):
        p.content_pre_push(self.root, data, "origin", c.SOURCE_URL, trust or self.trust,
                           remote=self.remote, test_runner=lambda: None)

    def wiki_edit(self, name="Web-edit.md", data=b"# Fixture web edit\n", root=False, mode="100644"):
        tip = c.Git(self.wiki_remote).commit("HEAD")
        self.seed.run("fetch", "-q", "--", str(self.wiki_remote), "refs/heads/master")
        self.seed.run("read-tree", tip)
        oid = self.seed.run("hash-object", "-w", "--stdin", input=data).decode().strip()
        self.seed.run("update-index", "--add", "--cacheinfo", mode + "," + oid + "," + name)
        tree = self.seed.run("write-tree").decode().strip()
        args = ["commit-tree", tree]
        if not root:
            args += ["-p", tip]
        commit = self.seed.run(*args, input=b"Fixture web edit\n").decode().strip()
        self.seed.run("push", "-q", "--", str(self.wiki_remote), commit + ":refs/heads/web-fixture")
        c.Git(self.wiki_remote).run("update-ref", "refs/heads/master", commit, tip)
        return commit


class SnapshotFixtures(GitFixture):
    def test_exact_committed_snapshot_and_worktree(self):
        checked = ck.validate(c.Snapshot(self.root, self.initial), today=DAY)
        self.assertEqual(len(checked.output), 7)
        ck.validate(c.Snapshot(self.root, worktree=True), today=DAY)

    def test_uncommitted_authoring_is_not_committed_input(self):
        (self.root / "wiki/Home.md").write_bytes(b"# Incomplete worktree\n")
        ck.validate(c.Snapshot(self.root, self.initial), today=DAY)
        with self.assertRaises(c.Invalid):
            ck.validate(c.Snapshot(self.root, worktree=True), today=DAY)

    def test_pinned_repository_link_never_uses_worktree_bytes(self):
        readme = self.root / "README.md"
        readme.write_bytes(readme.read_bytes() + b"\n## Worktree only\n\nFixture.\n")
        snapshot = c.Snapshot(self.root, worktree=True)
        with self.assertRaises(c.Invalid):
            ck.repo_link(snapshot, c.REPO_WEB + "/blob/" + self.initial + "/README.md#worktree-only")
        self.assertTrue(ck.repo_link(snapshot, c.REPO_WEB + "/blob/main/README.md#worktree-only"))

    def test_page_symlink(self):
        home = self.root / "wiki/Home.md"
        home.unlink()
        home.symlink_to(self.root / "README.md")
        for snapshot in (c.Snapshot(self.root, worktree=True),):
            with self.assertRaises(c.Invalid):
                ck.validate(snapshot, today=DAY)
        tip = self.commit()
        with self.assertRaises(c.Invalid):
            ck.validate(c.Snapshot(self.root, tip), today=DAY)

    def test_executable_and_extra_pages(self):
        home = self.root / "wiki/Home.md"
        home.chmod(0o755)
        with self.assertRaises(c.Invalid):
            ck.validate(c.Snapshot(self.root, self.commit()), today=DAY)
        home.chmod(0o644)
        (self.root / "wiki/Not-listed.md").write_bytes(b"# Extra\n")
        with self.assertRaises(c.Invalid):
            ck.validate(c.Snapshot(self.root, self.commit()), today=DAY)

    def test_protected_tree_changed(self):
        (self.root / c.RECIPE_PATH).write_bytes(b"# Changed recipe\n")
        with self.assertRaises(c.Invalid):
            ck.validate(c.Snapshot(self.root, self.commit()), today=DAY)

    def test_preview_deterministic_and_dirty_target_refusal(self):
        output = ck.validate(c.Snapshot(self.root), today=DAY).output
        s.preview(self.root, output, ".wiki-build")
        s.preview(self.root, output, ".wiki-build")
        target = self.root / ".wiki-build/Home.md"
        target.write_bytes(b"Unreviewed edit")
        with self.assertRaises(c.Invalid):
            s.preview(self.root, output, ".wiki-build")
        self.assertEqual(target.read_bytes(), b"Unreviewed edit")

    def test_preview_symlink_parent_and_arbitrary_destination(self):
        outside = self.base / "outside"
        outside.mkdir()
        (self.root / ".wiki-build").symlink_to(outside, target_is_directory=True)
        output = ck.validate(c.Snapshot(self.root), today=DAY).output
        for target in (".wiki-build", "k3-com260-fedora-howto", "../escape"):
            with self.assertRaises(c.Invalid):
                s.preview(self.root, output, target)
        self.assertFalse(list(outside.iterdir()))

    def test_preview_preserves_unrelated_files(self):
        build = self.root / ".wiki-build"
        build.mkdir()
        (build / "Unrelated.txt").write_text("Fixture user data")
        with self.assertRaises(c.Invalid):
            s.preview(self.root, ck.validate(c.Snapshot(self.root), today=DAY).output, ".wiki-build")
        self.assertEqual((build / "Unrelated.txt").read_text(), "Fixture user data")


class HookFixtures(GitFixture):
    def manifest_gap_tip(self, tool_path):
        manifest = self.root / c.MANIFEST
        tool = self.root / tool_path
        original_manifest, original_tool = manifest.read_bytes(), tool.read_bytes()
        manifest.unlink()
        self.commit("Fixture A removes manifest")
        tool.write_bytes(b"# Fixture B untrusted validator bytes; never execute\n")
        self.commit("Fixture B changes validator without manifest")
        manifest.write_bytes(original_manifest)
        tool.write_bytes(original_tool)
        tip = self.commit("Fixture C restores original manifest and validator")
        self.assertEqual(self.git.run("rev-list", "--count", self.initial + ".." + tip).strip(), b"3")
        self.assertEqual(p.identities(c.Snapshot(self.root, tip)), p.identities(c.Snapshot(self.root, self.initial)))
        return tip

    def test_non_checked_out_new_branch_and_zero_old(self):
        self.git.run("checkout", "-q", "-b", "topic")
        (self.root / "wiki/Home.md").write_bytes(page_bytes(extra="New public draft\n"))
        tip = self.commit()
        self.git.run("checkout", "-q", "main")
        self.gate(self.updates(tip))

    def test_multiple_proposed_refs(self):
        first = self.commit("Fixture first branch")
        second = self.commit("Fixture second branch")
        self.gate(self.updates(first, "refs/heads/one") + self.updates(second, "refs/heads/two"))

    def test_tip_is_validated_not_worktree_head(self):
        self.git.run("checkout", "-q", "-b", "bad")
        (self.root / "wiki/Home.md").write_bytes(b"# Missing metadata\n")
        tip = self.commit()
        self.git.run("checkout", "-q", "main")
        with self.assertRaises(c.Invalid):
            self.gate(self.updates(tip, "refs/heads/bad"))

    def test_introduced_then_deleted_blob_is_checked(self):
        token = ("ghp_" + "A" * 36).encode()
        path = self.root / "Temporary.txt"
        path.write_bytes(token)
        self.commit("Fixture introduction")
        path.unlink()
        tip = self.commit("Fixture deletion")
        with self.assertRaises(c.Invalid) as raised:
            self.gate(self.updates(tip))
        self.assertNotIn(token.decode(), str(raised.exception))

    def test_new_commit_message_is_checked(self):
        token = "ghp_" + "B" * 36
        tip = self.commit("Fixture " + token)
        with self.assertRaises(c.Invalid):
            self.gate(self.updates(tip))

    def test_merge_side_history_is_checked(self):
        self.git.run("checkout", "-q", "-b", "side")
        path = self.root / "Temporary.txt"
        path.write_bytes(("ghp_" + "C" * 36).encode())
        self.commit("Fixture side introduction")
        path.unlink()
        side = self.commit("Fixture side deletion")
        self.git.run("checkout", "-q", "main")
        main = self.commit("Fixture main work")
        tree = self.git.run("rev-parse", main + "^{tree}").decode().strip()
        merged = self.git.run("commit-tree", tree, "-p", main, "-p", side, input=b"Fixture merge\n").decode().strip()
        with self.assertRaises(c.Invalid):
            self.gate(self.updates(merged))

    def test_protected_introduce_then_restore_is_checked(self):
        original = (self.root / c.RECIPE_PATH).read_bytes()
        (self.root / c.RECIPE_PATH).write_bytes(original + b"\nUnreviewed\n")
        self.commit()
        (self.root / c.RECIPE_PATH).write_bytes(original)
        tip = self.commit()
        with self.assertRaises(c.Invalid):
            self.gate(self.updates(tip))

    def test_existing_public_unrelated_blob_not_rescanned(self):
        (self.root / "Old-fixture.txt").write_bytes(("/home/" + "fixture-placeholder").encode())
        self.commit("Fixture already public baseline")
        self.public_source()
        tip = self.commit("Fixture new safe commit")
        self.gate(self.updates(tip))

    def test_tag_only_public_history_not_rescanned(self):
        (self.root / "Old-tag-fixture.txt").write_bytes(("/home/" + "fixture-placeholder").encode())
        self.commit("Fixture tagged public history")
        self.git.run("tag", "-a", "fixture-public", "-m", "Fixture public tag")
        self.git.run("push", "-q", "--", str(self.source_remote), "refs/tags/fixture-public")
        tip = self.commit("Fixture new descendant")
        self.gate(self.updates(tip))

    def test_direct_commit_oid_update_is_supported(self):
        tip = self.commit()
        data = f"{tip} {tip} refs/heads/topic {p.ZERO}\n".encode()
        self.gate(data)

    def test_grafts_rejected_before_ancestry_checks(self):
        tip = self.commit()
        grafts = self.root / ".git/info/grafts"
        grafts.write_text(tip + "\n")
        with self.assertRaises(c.Invalid):
            self.gate(self.updates(tip))

    def test_nonfastforward_and_stale_old_rejected(self):
        for new, old in ((c.BASELINE, self.initial), (self.initial, c.BASELINE)):
            with self.assertRaises(c.Invalid):
                self.gate(self.updates(new, "refs/heads/main", old))

    def test_unsupported_refs_and_deletion_rejected(self):
        for data in (
            f"refs/tags/test {self.initial} refs/tags/test {p.ZERO}\n",
            f"(delete) {p.ZERO} refs/heads/main {self.initial}\n",
            f"refs/heads/main {self.initial} refs/heads/main {p.ZERO}\n",
        ):
            with self.assertRaises(c.Invalid):
                self.gate(data.encode())

    def test_tag_object_is_not_accepted_as_branch_tip(self):
        self.git.run("tag", "-a", "fixture-tag-object", "-m", "Fixture annotated tag")
        oid = self.git.run("rev-parse", "refs/tags/fixture-tag-object").decode().strip()
        with self.assertRaisesRegex(c.Invalid, "must be a commit"):
            self.gate(self.updates(oid))

    def test_reused_public_blob_cannot_hide_new_symlink_mode(self):
        (self.root / "Known-public.txt").write_text("fixture-target")
        self.commit()
        self.public_source()
        (self.root / "New-link").symlink_to("fixture-target")
        tip = self.commit()
        with self.assertRaisesRegex(c.Invalid, "symlink"):
            self.gate(self.updates(tip))

    def test_new_validator_never_executed(self):
        marker = self.root / "SHOULD-NOT-EXIST"
        (self.root / "tools/wiki/manage.py").write_text("raise RuntimeError('untrusted fixture tool')\n")
        tip = self.commit()
        with self.assertRaises(c.Invalid):
            self.gate(self.updates(tip))
        self.assertFalse(marker.exists())

    def test_untrusted_intermediate_tool_version_rejected(self):
        path = self.root / "tools/wiki/manage.py"
        original = path.read_bytes()
        path.write_bytes(b"raise RuntimeError('fixture unreviewed tool')\n")
        self.commit()
        path.write_bytes(original)
        tip = self.commit()
        with self.assertRaises(c.Invalid):
            self.gate(self.updates(tip))

    def test_manifest_gap_intermediate_validator_rejected(self):
        tip = self.manifest_gap_tip("tools/wiki/manage.py")
        with self.assertRaisesRegex(c.Invalid, "manifest|intermediate validator"):
            self.gate(self.updates(tip))

    def test_manifest_gap_intermediate_hook_rejected(self):
        tip = self.manifest_gap_tip(".githooks/pre-push")
        with self.assertRaisesRegex(c.Invalid, "manifest|intermediate validator"):
            self.gate(self.updates(tip))

    def test_manifest_gap_on_merge_side_rejected(self):
        self.git.run("checkout", "-q", "-b", "manifest-gap-side")
        side = self.manifest_gap_tip("tools/wiki/manage.py")
        self.git.run("checkout", "-q", "main")
        main = self.commit("Fixture independent main work")
        tree = self.git.run("rev-parse", main + "^{tree}").decode().strip()
        merged = self.git.run("commit-tree", tree, "-p", main, "-p", side,
                              input=b"Fixture merge restores trusted final tree\n").decode().strip()
        with self.assertRaisesRegex(c.Invalid, "manifest|intermediate validator"):
            self.gate(self.updates(merged))

    def test_manifest_deletion_and_restoration_rejected(self):
        path = self.root / c.MANIFEST
        original = path.read_bytes()
        path.unlink()
        self.commit("Fixture removes only manifest")
        path.write_bytes(original)
        tip = self.commit("Fixture restores only manifest")
        with self.assertRaisesRegex(c.Invalid, "manifest"):
            self.gate(self.updates(tip))

    def test_whole_tool_deletion_and_restoration_rejected(self):
        paths = (*p.TOOL_PATHS, c.MANIFEST, c.EXCEPTIONS)
        saved = {path: ((self.root / path).read_bytes(), (self.root / path).stat().st_mode & 0o777)
                 for path in paths}
        for path in paths:
            (self.root / path).unlink()
        removed = self.commit("Fixture removes complete validator including manifest and hook")
        self.assertFalse(any(path in self.git.entries(removed) for path in paths))
        for path, (data, mode) in saved.items():
            (self.root / path).write_bytes(data)
            (self.root / path).chmod(mode)
        tip = self.commit("Fixture restores complete trusted validator")
        with self.assertRaisesRegex(c.Invalid, "manifest"):
            self.gate(self.updates(tip))

    def test_whole_tool_deletion_in_merge_checks_all_parents(self):
        prewiki_tree = self.git.run("rev-parse", c.BASELINE + "^{tree}").decode().strip()
        removed = self.git.run("commit-tree", prewiki_tree, "-p", c.BASELINE, "-p", self.initial,
                               input=b"Fixture merge removes tooling from its second parent\n").decode().strip()
        trusted_tree = self.git.run("rev-parse", self.initial + "^{tree}").decode().strip()
        tip = self.git.run("commit-tree", trusted_tree, "-p", removed,
                           input=b"Fixture restores trusted tooling after merge\n").decode().strip()
        with self.assertRaisesRegex(c.Invalid, "manifest"):
            self.gate(self.updates(tip, "refs/heads/main", self.initial))

    def test_docs_only_commit_with_trusted_tooling_allowed(self):
        path = self.root / "README.md"
        path.write_bytes(path.read_bytes() + b"\nPublic fixture documentation correction.\n")
        tip = self.commit("Fixture documentation-only change")
        self.gate(self.updates(tip, "refs/heads/main", self.initial))

    def test_prewiki_docs_only_ancestry_allowed(self):
        self.assertNotIn(c.MANIFEST, self.git.entries(c.BASELINE))
        self.git.run("checkout", "-q", "-b", "prewiki-docs", c.BASELINE)
        path = self.root / "README.md"
        path.write_bytes(path.read_bytes() + b"\nPublic pre-wiki fixture documentation correction.\n")
        docs = self.commit("Fixture pre-wiki documentation-only change")
        tree = self.git.run("rev-parse", self.initial + "^{tree}").decode().strip()
        tip = self.git.run("commit-tree", tree, "-p", docs,
                           input=b"Fixture introduces complete reviewed wiki tooling\n").decode().strip()
        self.gate(self.updates(tip))

    def test_trusted_fixture_failure_blocks_push(self):
        tip = self.commit()
        with self.assertRaises(c.Invalid):
            p.content_pre_push(self.root, self.updates(tip), "origin", c.SOURCE_URL, self.trust,
                               remote=self.remote, test_runner=lambda: c.require(False, "Fixture tests failed"))

    def test_trusted_runtime_identity_drift_blocks_push(self):
        tip = self.commit()
        altered = copy.deepcopy(self.trust)
        altered["runtime"]["executables"]["git"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(c.Invalid, "system executable identity changed"):
            self.gate(self.updates(tip), trust=altered)
        self.assertFalse(self.remote.pushes)

    def test_trusted_fixture_input_is_bound_not_worktree(self):
        (self.root / c.MANIFEST).write_text("Unreviewed worktree fixture input")
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")
        with mock.patch.object(p.subprocess, "run", return_value=completed) as run:
            p.run_tests(self.bundle, self.root, self.initial)
        self.assertEqual(run.call_args.kwargs["env"]["WIKI_TEST_SOURCE_REF"], self.initial)
        self.assertEqual(run.call_args.kwargs["env"]["WIKI_TEST_REPOSITORY"], str(self.root))
        self.assertIn(str(self.bundle / "tools/wiki/tests"), run.call_args.args[0])
        isolated = Path(run.call_args.kwargs["cwd"])
        self.assertTrue(isolated.is_relative_to(self.root / s.BUILD / "tests"))
        self.assertEqual(run.call_args.kwargs["env"]["WIKI_TEST_OUTPUT"], str(isolated / "fixtures"))
        self.assertIn("-B", run.call_args.args[0])
        self.assertIn("pycache_prefix=" + str(isolated / "bytecode"), run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["env"]["PATH"], c.SYSTEM_PATH)
        self.assertFalse(isolated.exists())

    def test_existing_hook_configuration_preserved(self):
        self.git.run("config", "core.hooksPath", "custom-hooks")
        with mock.patch.object(p, "run_tests"), self.assertRaises(c.Invalid):
            p.install_hook(self.root, self.initial)
        self.assertEqual(self.git.run("config", "--local", "core.hooksPath").strip(), b"custom-hooks")

    def test_effective_global_hook_configuration_preserved(self):
        before = self.git.run("config", "--local", "core.hooksPath")
        with mock.patch.object(p, "run_tests"), mock.patch.object(p, "effective_hooks", return_value="/fixture-global-hooks"):
            with self.assertRaises(c.Invalid):
                p.install_hook(self.root, self.initial)
        self.assertEqual(self.git.run("config", "--local", "core.hooksPath"), before)

    def test_external_hook_configuration_is_detected_as_inert_input(self):
        config = self.base / "fixture-gitconfig"
        config.write_text("[user]\n\tname = Fixture Human\n")
        self.assertFalse(p.config_may_define_hooks(config))
        config.write_text("[core]\n\thooksPath = fixture-hooks\n")
        self.assertTrue(p.config_may_define_hooks(config))
        config.write_text("[includeIf \"gitdir:~/src/\"]\n\tpath = fixture.inc\n")
        self.assertTrue(p.config_may_define_hooks(config))
        config.unlink()
        config.symlink_to(self.root / ".git/config")
        self.assertTrue(p.config_may_define_hooks(config))

    def test_effective_hook_detection_does_not_load_external_git_config(self):
        config = self.base / "fixture-gitconfig"
        config.write_text("[core]\n\thooksPath = fixture-hooks\n")
        git = mock.Mock()
        git.root = self.root
        completed = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"")
        with mock.patch.dict(os.environ, {"HOME": str(self.base)}, clear=True), \
                mock.patch.object(p, "external_git_config_paths", return_value=(config,)), \
                mock.patch.object(p.subprocess, "run", return_value=completed) as run:
            self.assertTrue(p.effective_hooks(git))
        command = run.call_args.args[0]
        env = run.call_args.kwargs["env"]
        self.assertEqual(command[0], "/usr/bin/git")
        self.assertEqual(command[-4:], ["config", "--local", "--get", "core.hooksPath"])
        self.assertEqual(env["PATH"], c.SYSTEM_PATH)
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")

    def test_dispatcher_fails_without_interpreter_before_any_network(self):
        interpreter = self.bundle / "interpreter"
        interpreter.chmod(0o644)
        interpreter.write_text("/nonexistent/fixture-python\n")
        result = subprocess.run(["sh", str(self.bundle / "hooks/pre-push"), "origin", c.SOURCE_URL],
                                input=self.updates(self.initial), capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"pinned interpreter missing", result.stderr)

    def test_disabled_installed_dispatcher_is_rejected(self):
        (self.bundle / "hooks/pre-push").chmod(0o444)
        with self.assertRaisesRegex(c.Invalid, "not executable"):
            p.read_bundle(self.bundle)


class BundleFixtures(GitFixture):
    def test_install_tests_exact_staged_bundle_after_live_source_edit(self):
        source = self.commit("Fixture reviewed installation source")
        before_config = (self.root / ".git/config").read_bytes()
        run_tests, run_process = p.run_tests, subprocess.run
        calls = []

        def reference_tests_only(command, **kwargs):
            if "-m" in command and "unittest" in command:
                self.assertTrue(Path(kwargs["env"]["WIKI_TEST_OUTPUT"]).is_relative_to(self.root / s.BUILD / "tests"))
                self.assertEqual(command[0], p.interpreter_path(self.root))
                self.assertEqual(kwargs["timeout"], p.TRUSTED_SUITE_TIMEOUT)
                command = [*command, "-k", "ReferenceTests"]
                result = run_process(command, **kwargs)
                self.assertIn(b"Ran 18 tests", result.stderr)
                return result
            return run_process(command, **kwargs)

        def staged_tests(stage, repository, trusted_ref):
            calls.append(stage)
            self.assertEqual(stage.parent, self.bundle.parent)
            self.assertTrue(stage.name.startswith(".partial-"))
            self.assertEqual(repository, self.root)
            self.assertEqual(trusted_ref, source)
            self.assertEqual((self.root / ".git/config").read_bytes(), before_config)
            selected = c.Snapshot(self.root, source)
            for path in ("tools/wiki/manage.py", "tools/wiki/tests/test_wiki.py", c.MANIFEST):
                (self.root / path).write_bytes(b"Fixture concurrent unreviewed worktree edit\n")
            self.assertEqual(c.regular_read(stage, "tools/wiki/manage.py"), selected.read("tools/wiki/manage.py"))
            self.assertEqual(c.regular_read(stage, "tools/wiki/tests/test_wiki.py"),
                             selected.read("tools/wiki/tests/test_wiki.py"))
            with mock.patch.object(subprocess, "run", side_effect=reference_tests_only):
                run_tests(stage, repository, trusted_ref)

        with mock.patch.object(p, "run_tests", side_effect=staged_tests):
            installed = p.install_hook(self.root, source)
        self.assertEqual(len(calls), 1)
        self.assertFalse(calls[0].exists())
        metadata = p.read_bundle(installed)
        self.assertEqual(metadata["source"], source)
        self.assertEqual(metadata["interpreter"], p.interpreter_path(self.root))
        self.assertEqual(installed.name, c.sha256(c.regular_read(installed, "bundle.json")))

    def test_install_interruption_never_creates_incomplete_final_bundle(self):
        source = self.commit("Fixture interrupted installation source")
        before_config = (self.root / ".git/config").read_bytes()
        original = s.write

        def interrupted(root, name, data, **kwargs):
            if name == "bundle.json":
                raise OSError("Fixture interrupted staged bundle write")
            return original(root, name, data, **kwargs)

        with mock.patch.object(s, "write", side_effect=interrupted), mock.patch.object(p, "run_tests") as tests:
            with self.assertRaises(c.Invalid):
                p.install_hook(self.root, source)
        tests.assert_not_called()
        self.assertEqual((self.root / ".git/config").read_bytes(), before_config)
        parent = self.bundle.parent
        partials = {path.name for path in parent.iterdir() if path.name.startswith(".partial-")}
        self.assertEqual(len(partials), 1)
        self.assertEqual({path.name for path in parent.iterdir() if not path.name.startswith(".partial-")},
                         {self.bundle.name})
        with mock.patch.object(p, "run_tests"):
            installed = p.install_hook(self.root, source)
        self.assertNotEqual(installed, self.bundle)
        self.assertEqual(p.read_bundle(installed)["source"], source)
        self.assertTrue(partials <= {path.name for path in parent.iterdir()})

    def test_install_interrupted_atomic_rename_is_retryable(self):
        source = self.commit("Fixture interrupted rename source")
        before_config = (self.root / ".git/config").read_bytes()
        with mock.patch.object(p, "run_tests"), mock.patch.object(p.os, "rename", side_effect=OSError("Fixture rename interruption")):
            with self.assertRaises(c.Invalid):
                p.install_hook(self.root, source)
        self.assertEqual((self.root / ".git/config").read_bytes(), before_config)
        self.assertEqual({path.name for path in self.bundle.parent.iterdir() if not path.name.startswith(".partial-")},
                         {self.bundle.name})
        with mock.patch.object(p, "run_tests"):
            installed = p.install_hook(self.root, source)
        self.assertEqual(p.read_bundle(installed)["source"], source)

    def test_install_failed_staged_suite_preserves_previous_hook_and_retries(self):
        source = self.commit("Fixture failed installation suite source")
        before_config = (self.root / ".git/config").read_bytes()
        with mock.patch.object(p, "run_tests", side_effect=c.Invalid("Fixture staged suite failed")):
            with self.assertRaisesRegex(c.Invalid, "staged suite failed"):
                p.install_hook(self.root, source)
        self.assertEqual((self.root / ".git/config").read_bytes(), before_config)
        self.assertEqual({path.name for path in self.bundle.parent.iterdir() if not path.name.startswith(".partial-")},
                         {self.bundle.name})
        with mock.patch.object(p, "run_tests"):
            installed = p.install_hook(self.root, source)
        self.assertEqual(p.read_bundle(installed)["source"], source)

    def test_install_rejects_extra_staged_file_before_configuration(self):
        source = self.commit("Fixture staged inventory source")
        before_config = (self.root / ".git/config").read_bytes()

        def inject(stage, repository, trusted_ref):
            (stage / "Unexpected.py").write_bytes(b"# Fixture extra code; never execute\n")

        with mock.patch.object(p, "run_tests", side_effect=inject), self.assertRaisesRegex(c.Invalid, "inventory"):
            p.install_hook(self.root, source)
        self.assertEqual((self.root / ".git/config").read_bytes(), before_config)
        self.assertEqual({path.name for path in self.bundle.parent.iterdir() if not path.name.startswith(".partial-")},
                         {self.bundle.name})

    def test_install_final_verification_precedes_configuration(self):
        source = self.commit("Fixture final verification source")
        before_config = (self.root / ".git/config").read_bytes()
        read_bundle = p.read_bundle

        def verify(bundle, *, sealed=True, check_runtime=True):
            value = read_bundle(bundle, sealed=sealed, check_runtime=check_runtime)
            if sealed and check_runtime and value["source"] == source:
                raise c.Invalid("Fixture final verification refusal")
            return value

        with mock.patch.object(p, "run_tests"), mock.patch.object(p, "read_bundle", side_effect=verify):
            with self.assertRaisesRegex(c.Invalid, "final verification"):
                p.install_hook(self.root, source)
        self.assertEqual((self.root / ".git/config").read_bytes(), before_config)
        with mock.patch.object(p, "run_tests"):
            installed = p.install_hook(self.root, source)
        self.assertEqual(p.read_bundle(installed)["source"], source)

    def test_install_preserves_hook_added_while_tests_run(self):
        source = self.commit("Fixture concurrent hook integration source")
        hooks_path = "fixture-human-hooks"

        def add_hook(stage, repository, trusted_ref):
            self.git.run("config", "--local", "core.hooksPath", hooks_path)

        with mock.patch.object(p, "run_tests", side_effect=add_hook), self.assertRaisesRegex(c.Invalid, "existing core.hooksPath"):
            p.install_hook(self.root, source)
        self.assertEqual(self.git.run("config", "--local", "--get", "core.hooksPath").strip(), hooks_path.encode())
        self.assertEqual(self.git.run("config", "--local", "--get", "wiki.trustBundle").strip(), str(self.bundle).encode())

    def test_bundle_inventory_rejects_extra_file(self):
        self.bundle.chmod(0o700)
        (self.bundle / "Unexpected.py").write_bytes(b"# Fixture extra\n")
        self.bundle.chmod(0o555)
        with self.assertRaisesRegex(c.Invalid, "inventory"):
            p.read_bundle(self.bundle)

    def test_bundle_inventory_rejects_bytecode_cache(self):
        directory = self.bundle / "tools/wiki"
        directory.chmod(0o700)
        (directory / "__pycache__").mkdir()
        (directory / "__pycache__/fixture.pyc").write_bytes(b"Fixture not bytecode")
        directory.chmod(0o555)
        with self.assertRaisesRegex(c.Invalid, "inventory"):
            p.read_bundle(self.bundle)

    def test_bundle_inventory_rejects_empty_extra_directory(self):
        self.bundle.chmod(0o700)
        (self.bundle / "extra-empty").mkdir()
        self.bundle.chmod(0o555)
        with self.assertRaisesRegex(c.Invalid, "inventory"):
            p.read_bundle(self.bundle)

    def test_bundle_inventory_rejects_symlink(self):
        directory = self.bundle / "tools/wiki"
        directory.chmod(0o700)
        (directory / "manage.py").unlink()
        (directory / "manage.py").symlink_to(self.root / "tools/wiki/manage.py")
        directory.chmod(0o555)
        with self.assertRaises(c.Invalid):
            p.read_bundle(self.bundle)

    def test_bundle_inventory_rejects_file_and_directory_modes(self):
        for relative in ("tools/wiki/manage.py", "tools/wiki"):
            path = self.bundle / relative
            original = path.stat().st_mode & 0o777
            path.chmod(0o755)
            with self.subTest(path=relative), self.assertRaisesRegex(c.Invalid, "mode"):
                p.read_bundle(self.bundle)
            path.chmod(original)

    def test_bundle_inventory_rejects_hardlinked_file(self):
        directory = self.bundle / "tools/wiki"
        directory.chmod(0o700)
        os.link(directory / "manage.py", self.base / "fixture-hardlink")
        directory.chmod(0o555)
        with self.assertRaisesRegex(c.Invalid, "linked"):
            p.read_bundle(self.bundle)

    def test_bundle_rejects_system_executable_identity_drift(self):
        altered = copy.deepcopy(p.runtime_identity())
        altered["executables"]["git"]["sha256"] = "0" * 64
        with mock.patch.object(p, "runtime_identity", return_value=altered), \
                self.assertRaisesRegex(c.Invalid, "system executables changed"):
            p.read_bundle(self.bundle)

    def test_stale_runtime_bundle_can_be_deliberately_reinstalled(self):
        source = self.commit("Fixture executable identity reinstall source")
        altered = copy.deepcopy(p.runtime_identity())
        altered["executables"]["git"]["sha256"] = "0" * 64
        with mock.patch.object(p, "runtime_identity", return_value=altered), \
                mock.patch.object(p, "run_tests"):
            installed = p.install_hook(self.root, source)
        self.assertNotEqual(installed, self.bundle)
        self.assertEqual(p.read_bundle(installed, check_runtime=False)["runtime"], altered)

    def test_fixture_output_cannot_escape_ignored_area(self):
        with mock.patch.dict(os.environ, {"WIKI_TEST_OUTPUT": str(ROOT / "tools/wiki")}), self.assertRaises(c.Invalid):
            fixture_output()


class CheckLinksFixtures(GitFixture):
    def invoke(self, ref):
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(Path, "cwd", return_value=self.root), \
                mock.patch.object(sys, "argv", ["manage.py", "check-links", "--ref", ref]), \
                mock.patch.object(h, "Checker", return_value=self.online), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            result = manage.main()
        return result, stdout.getvalue(), stderr.getvalue()

    def test_check_links_cli_is_report_only_without_installed_hooks(self):
        self.git.run("config", "--local", "--unset", "core.hooksPath")
        self.git.run("config", "--local", "--unset", "wiki.trustBundle")
        config = (self.root / ".git/config").read_bytes()
        before = self.git.run("status", "--porcelain=v1", "--untracked-files=all")
        run = c.Git.run

        def read_only(git, *args, **kwargs):
            self.assertIn(args[0], ("rev-parse", "ls-tree", "cat-file"))
            return run(git, *args, **kwargs)

        with mock.patch.object(c.Git, "run", new=read_only), \
                mock.patch.object(s, "write", side_effect=AssertionError("Fixture unexpected file write")), \
                mock.patch.object(p, "PublicRemotes", side_effect=AssertionError("Fixture unexpected Git transport")):
            code, stdout, stderr = self.invoke(self.initial)
        self.assertEqual((code, stderr), (0, ""))
        report = c.load_json(stdout.encode(), "fixture link report")
        self.assertEqual(report["mode"], "report-only")
        self.assertFalse(report["public_reachability_checked"])
        self.assertFalse(report["publication_authorized"])
        self.assertEqual(report["source"]["commit"], self.initial)
        self.assertEqual(report["runtime"], p.runtime_identity())
        self.assertEqual(report["identities"], p.identities(c.Snapshot(self.root, self.initial)))
        self.assertEqual((self.root / ".git/config").read_bytes(), config)
        self.assertEqual(self.git.run("status", "--porcelain=v1", "--untracked-files=all"), before)
        self.assertFalse((self.root / s.BUILD).exists())
        self.assertFalse((self.root / s.PUBLISH).exists())
        self.assertEqual(sum(item["role"].startswith("critical-") for item in report["links"]), 4)

    def test_check_links_rejects_nonfull_refs_without_echoing_input(self):
        for ref in ("HEAD", self.initial[:12], "not-a-ref", "ghp_" + "A" * 36):
            code, stdout, stderr = self.invoke(ref)
            with self.subTest(length=len(ref)):
                self.assertEqual(code, 1)
                self.assertEqual(stdout, "")
                self.assertIn("wiki: check-links --ref requires a full", stderr)
                self.assertNotIn(ref, stderr)
        self.assertFalse(self.online.requests)

    def test_check_links_rejects_tag_object(self):
        self.git.run("tag", "-a", "fixture-report-tag", "-m", "Fixture report tag")
        tag = self.git.run("rev-parse", "refs/tags/fixture-report-tag").decode().strip()
        code, stdout, stderr = self.invoke(tag)
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("not a tag object", stderr)

    def test_check_links_runtime_failure_has_normal_sanitized_error(self):
        with mock.patch.object(p, "runtime_identity", side_effect=c.Invalid("Fixture pinned runtime unavailable")):
            code, stdout, stderr = self.invoke(self.initial)
        self.assertEqual((code, stdout), (1, ""))
        self.assertEqual(stderr, "wiki: Fixture pinned runtime unavailable\n")
        self.assertFalse(self.online.requests)

    def test_check_links_offline_failure_has_no_report_or_network(self):
        (self.root / "wiki/Home.md").write_bytes(b"# Fixture missing metadata\n")
        tip = self.commit()
        code, stdout, stderr = self.invoke(tip)
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("wiki: missing visible context fields", stderr)
        self.assertFalse(self.online.requests)

    def test_check_links_detects_runtime_change_during_check(self):
        runtime = p.runtime_identity()
        with mock.patch.object(p, "runtime_identity", side_effect=[runtime, {**runtime, "python": [99, 0, 0]}]):
            code, stdout, stderr = self.invoke(self.initial)
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("changed during the report-only check", stderr)

    def test_check_links_binds_running_tool_bytes(self):
        (self.root / "tools/wiki/manage.py").write_bytes(b"# Fixture unreviewed tool\n")
        tip = self.commit()
        code, stdout, stderr = self.invoke(tip)
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("running validator differs", stderr)
        self.assertFalse(self.online.requests)

    def test_check_links_unavailable_critical_input_is_not_a_publication_success(self):
        self.online.unavailable.add(self.manifest["critical_artifacts"][0]["url"])
        code, stdout, stderr = self.invoke(self.initial)
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("wiki: public link unavailable", stderr)
        self.assertFalse(self.remote.pushes)

    def test_check_links_local_commit_does_not_claim_public_reachability(self):
        path = self.root / "README.md"
        path.write_bytes(path.read_bytes() + b"\nUnpublished fixture documentation correction.\n")
        tip = self.commit()
        self.assertNotEqual(tip, c.Git(self.source_remote).commit("HEAD"))
        code, stdout, stderr = self.invoke(tip)
        self.assertEqual((code, stderr), (0, ""))
        report = c.load_json(stdout.encode(), "fixture link report")
        self.assertFalse(report["public_reachability_checked"])
        self.assertFalse(report["publication_authorized"])


class PublicationFixtures(GitFixture):
    def resource_review(self):
        url = "https://resource.fixture.test/reviewed-resource"
        entry = {"kind": "resource", "page": "Extra.md", "url": url, "reason": "Test-only resource outage review",
                 "reviewer": "Fixture Human (test only)", "reviewed": "2026-09-26", "expires": "2026-09-28"}
        (self.root / "wiki/Extra.md").write_bytes(page_bytes(extra=f"[Resource]({url})\n"))
        (self.root / c.EXCEPTIONS).write_bytes(c.canonical({"schema": 1, "exceptions": [entry]}))
        self.commit("Fixture reviewed resource policy")
        self.public_source()
        return url, entry

    def test_new_exception_use_requires_new_receipt_before_writes(self):
        url, entry = self.resource_review()
        with mock.patch.object(h, "example_host", return_value=False):
            prepared = self.prepare()
            receipt, _ = p.read_receipt(self.root, *prepared)
            reviewed = next(row for row in receipt["online_approval"] if row["url"] == url)
            self.assertEqual(reviewed["status"], "available")
            self.assertNotIn("exception", reviewed)
            self.assertNotIn(entry["reason"].encode(), (prepared[0].parent / "report.md").read_bytes())
            wiki = self.root / s.PUBLISH
            config, index = (wiki / ".git/config").read_bytes(), (wiki / ".git/index").read_bytes()
            self.online.unavailable.add(url)
            with mock.patch.object(self.remote, "source", wraps=self.remote.source) as fetch_source, \
                    mock.patch.object(s, "write", side_effect=AssertionError("Fixture unexpected publication write")):
                with self.assertRaisesRegex(c.Invalid, "availability or exception use changed"):
                    self.publish(prepared)
            fetch_source.assert_not_called()
        self.assertFalse(self.remote.pushes)
        self.assertEqual(c.Git(wiki).commit("HEAD"), self.bootstrap)
        self.assertEqual((wiki / ".git/config").read_bytes(), config)
        self.assertEqual((wiki / ".git/index").read_bytes(), index)
        self.assertFalse((wiki / ".git/wiki-transaction.json").exists())
        self.assertFalse((self.root / s.BUILD / "prepared/.last-check.json").exists())

    def test_exception_recovery_also_requires_new_receipt(self):
        url, _ = self.resource_review()
        self.online.unavailable.add(url)
        with mock.patch.object(h, "example_host", return_value=False):
            prepared = self.prepare()
            self.online.unavailable.clear()
            with self.assertRaisesRegex(c.Invalid, "availability or exception use changed"):
                self.publish(prepared)
        self.assertFalse(self.remote.pushes)

    def test_reviewed_active_exception_remains_publishable(self):
        url, entry = self.resource_review()
        self.online.unavailable.add(url)
        with mock.patch.object(h, "example_host", return_value=False):
            prepared = self.prepare()
            receipt, _ = p.read_receipt(self.root, *prepared)
            reviewed = next(row for row in receipt["online_approval"] if row["url"] == url)
            self.assertEqual(reviewed["exception"], entry)
            self.assertIn(entry["reason"].encode(), (prepared[0].parent / "report.md").read_bytes())
            self.assertEqual(self.publish(prepared), "published")

    def test_online_approval_ignores_method_timing_and_dns_noise(self):
        prepared = self.prepare()
        all_links = self.online.all

        def reordered(links, exceptions):
            result = all_links(links, exceptions)
            for row in result:
                row.update(elapsed_seconds=123.0, resolved_addresses=["93.184.216.35"])
                if row["status"] == "available-head":
                    row["status"] = "available-get"
            return list(reversed(result))

        with mock.patch.object(self.online, "all", side_effect=reordered):
            self.assertEqual(self.publish(prepared), "published")

    def test_publication_gate_checks_both_images_and_checksum_records(self):
        prepared = self.prepare()
        for item in self.manifest["critical_artifacts"]:
            self.assertIn(("HEAD", item["url"]), self.online.requests)
            self.assertIn(("CHECKSUM", item["checksum_url"]), self.online.requests)
            self.assertNotIn(("GET", item["url"]), self.online.requests)
            self.assertIn(item["sha256"].encode(), (prepared[0].parent / "report.md").read_bytes())
        self.assertEqual((prepared[0].parent / "report.md").read_bytes().count(b"checksum-matches"), 2)

    def test_missing_either_critical_image_or_metadata_blocks_prepare(self):
        for item in self.manifest["critical_artifacts"]:
            for field in ("url", "checksum_url"):
                self.online.unavailable = {item[field]}
                with self.subTest(artifact=item["id"], field=field), self.assertRaises(c.Invalid):
                    self.prepare()
        self.assertFalse(self.remote.pushes)

    def test_changed_checksum_metadata_invalidates_reviewed_publication(self):
        prepared = self.prepare()
        for item in self.manifest["critical_artifacts"]:
            self.online.bad_checksums = {item["checksum_url"]}
            with self.subTest(artifact=item["id"]), self.assertRaises(c.Invalid):
                self.publish(prepared)
        self.assertFalse(self.remote.pushes)

    def test_prepare_is_sha_addressed_and_idempotent(self):
        first = self.prepare()
        second = self.prepare()
        self.assertEqual(first, second)
        receipt, output = p.read_receipt(self.root, *first)
        self.assertEqual(c.sha256(first[0].read_bytes()), first[1])
        self.assertEqual(s.tree_record(output), receipt["output"])
        self.assertFalse(self.remote.pushes)

    def test_bootstrap_publish_is_forward_and_idempotent(self):
        prepared = self.prepare()
        self.assertEqual(self.publish(prepared), "published")
        tip = c.Git(self.wiki_remote).commit("HEAD")
        self.assertEqual(c.Git(self.wiki_remote).run("rev-list", "--parents", "-n", "1", tip).decode().split(),
                         [tip, self.bootstrap])
        self.assertEqual(self.publish(prepared), "already-published")
        self.assertEqual(len(self.remote.pushes), 1)
        args = self.remote.pushes[0]
        self.assertFalse(any("force" in arg or arg in ("--mirror", "--prune") for arg in args))

    def test_main_default_branch_is_discovered(self):
        bare = c.Git(self.wiki_remote)
        bare.run("update-ref", "refs/heads/main", self.bootstrap)
        bare.run("symbolic-ref", "HEAD", "refs/heads/main")
        prepared = self.prepare()
        self.assertEqual(p.read_receipt(self.root, *prepared)[0]["wiki"]["branch"], "refs/heads/main")
        self.assertEqual(self.publish(prepared), "published")

    def test_bootstrap_requires_explicit_adoption(self):
        with self.assertRaises(c.Invalid):
            self.prepare(adopt=False)

    def test_wrong_bootstrap_oid_rejected(self):
        self.bootstrap = self.initial
        with self.assertRaises(c.Invalid):
            self.prepare()

    def test_bootstrap_extra_sidebar_rejected(self):
        self.bootstrap = self.wiki_edit("_Sidebar.md", b"Fixture unexpected sidebar\n", root=True)
        with self.assertRaises(c.Invalid):
            self.prepare()

    def test_bootstrap_changed_home_rejected(self):
        self.bootstrap = self.wiki_edit("Home.md", b"# Different fixture Home\n", root=True)
        with self.assertRaises(c.Invalid):
            self.prepare()

    def test_bootstrap_bad_mode_rejected(self):
        self.bootstrap = self.wiki_edit("Home.md", self.manifest["bootstrap_home"].encode(), root=True, mode="100755")
        with self.assertRaises(c.Invalid):
            self.prepare()

    def test_bootstrap_cannot_be_repeated(self):
        self.publish(self.prepare())
        self.bootstrap = c.Git(self.wiki_remote).commit("HEAD")
        with self.assertRaises(c.Invalid):
            self.prepare()

    def test_dirty_source_rejected(self):
        (self.root / "Unreviewed.txt").write_text("Fixture untracked content")
        with self.assertRaises(c.Invalid):
            self.prepare()
        self.assertTrue((self.root / "Unreviewed.txt").exists())

    def test_unreachable_source_and_stale_tracking_ref(self):
        private = self.commit("Fixture not public")
        self.git.run("update-ref", "refs/remotes/origin/main", private)
        with self.assertRaises(c.Invalid):
            self.prepare(private)

    def test_wrong_origin_rejected(self):
        self.git.run("config", "remote.origin.url", "https://example.invalid/wrong.git")
        with self.assertRaises(c.Invalid):
            self.prepare()

    def test_source_advance_same_approved_source_allowed(self):
        prepared = self.prepare()
        (self.root / "wiki/Home.md").write_bytes(page_bytes(extra="Later public source, not this receipt.\n"))
        self.commit()
        self.public_source()
        self.assertEqual(self.publish(prepared), "published")

    def test_receipt_byte_tampering_rejected(self):
        prepared = self.prepare()
        prepared[0].chmod(0o644)
        prepared[0].write_bytes(prepared[0].read_bytes() + b" ")
        with self.assertRaises(c.Invalid):
            self.publish(prepared)
        self.assertFalse(self.remote.pushes)

    def test_report_tampering_rejected(self):
        prepared = self.prepare()
        report = prepared[0].parent / "report.md"
        report.chmod(0o644)
        report.write_bytes(b"Altered fixture report")
        with self.assertRaises(c.Invalid):
            self.publish(prepared)

    def test_output_tampering_and_extra_file_rejected(self):
        prepared = self.prepare()
        page = prepared[0].parent / "tree/Home.md"
        page.chmod(0o644)
        page.write_bytes(b"Changed output")
        with self.assertRaises(c.Invalid):
            self.publish(prepared)

    def test_extra_prepared_artifact_rejected(self):
        prepared = self.prepare()
        directory = prepared[0].parent
        directory.chmod(0o755)
        (directory / "Unreviewed.txt").write_text("Fixture extra")
        with self.assertRaises(c.Invalid):
            self.publish(prepared)

    def test_symlinked_preparation_ancestor_rejected(self):
        prepared = self.prepare()
        directory = prepared[0].parent
        moved = directory.with_name("moved-fixture")
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(c.Invalid):
            self.publish(prepared)

    def test_symlinked_publication_clone_cannot_redirect_writes(self):
        prepared = self.prepare()
        original = self.root / s.PUBLISH
        moved = self.base / "moved-wiki"
        original.rename(moved)
        original.symlink_to(moved, target_is_directory=True)
        before = (moved / ".git/config").read_bytes()
        with self.assertRaises(c.Invalid):
            self.publish(prepared)
        self.assertEqual((moved / ".git/config").read_bytes(), before)

    def test_symlinked_git_metadata_refused(self):
        prepared = self.prepare()
        directory = self.root / s.PUBLISH / ".git"
        moved = self.base / "moved-git"
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(c.Invalid):
            self.publish(prepared)

    def test_changed_bound_inputs_require_new_review(self):
        prepared = self.prepare()
        for path in (c.MANIFEST, c.EXCEPTIONS, c.LOCK, "tools/wiki/manage.py"):
            target = self.root / path
            data = target.read_bytes()
            target.write_bytes(data + b"\n")
            with self.subTest(path=path), self.assertRaises(c.Invalid):
                self.publish(prepared)
            target.write_bytes(data)

    def test_changed_runtime_invalidates_receipt(self):
        prepared = self.prepare()
        original = p.runtime_identity()
        altered = {**original, "python": [99, 0, 0]}
        with mock.patch.object(p, "runtime_identity", return_value=altered), self.assertRaises(c.Invalid):
            self.publish(prepared)

    def test_changed_system_executable_invalidates_receipt(self):
        prepared = self.prepare()
        altered = copy.deepcopy(p.runtime_identity())
        altered["executables"]["gh"]["path"] = "/usr/bin/gh-changed"
        with mock.patch.object(p, "runtime_identity", return_value=altered), self.assertRaises(c.Invalid):
            self.publish(prepared)

    def test_expiring_resource_exception_invalidates_receipt(self):
        url = "https://resource.example.test/fixture"
        (self.root / "wiki/Extra.md").write_bytes(page_bytes(extra=f"[Resource]({url})\n"))
        entry = {"kind": "resource", "page": "Extra.md", "url": url, "reason": "Test-only reviewed fixture outage",
                 "reviewer": "Fixture Human (test only)", "reviewed": "2026-09-26", "expires": "2026-09-28"}
        (self.root / c.EXCEPTIONS).write_bytes(c.canonical({"schema": 1, "exceptions": [entry]}))
        self.commit()
        self.public_source()
        prepared = self.prepare()
        with mock.patch.object(p, "utc_day", return_value=date(2026, 9, 29)), self.assertRaises(c.Invalid):
            self.publish(prepared)

    def test_altered_publisher_identity_invalidates_receipt(self):
        prepared = self.prepare()
        self.git.run("config", "user.name", "Different Fixture Human")
        with self.assertRaises(c.Invalid):
            self.publish(prepared)

    def test_preparation_refuses_drift_after_managed_publish(self):
        self.publish(self.prepare())
        self.wiki_edit()
        with self.assertRaises(c.Invalid):
            self.prepare(adopt=False)

    def test_remote_web_edit_stops_publication(self):
        prepared = self.prepare()
        self.wiki_edit()
        with self.assertRaises(c.Invalid):
            self.publish(prepared)
        self.assertFalse(self.remote.pushes)

    def test_race_at_push_is_not_force_overwritten(self):
        prepared = self.prepare()
        self.remote.before_push = lambda: self.wiki_edit()
        with self.assertRaises(c.Invalid):
            self.publish(prepared)
        self.assertIn("Web-edit.md", c.Git(self.wiki_remote).entries("HEAD"))
        self.assertEqual(len(self.remote.pushes), 1)

    def test_interrupted_push_resumes_same_forward_commit(self):
        prepared = self.prepare()
        self.remote.fail_push = True
        with self.assertRaises(c.Invalid):
            self.publish(prepared)
        candidate = c.Git(self.root / s.PUBLISH).commit("HEAD")
        self.remote.fail_push = False
        self.assertEqual(self.publish(prepared), "published")
        self.assertEqual(c.Git(self.wiki_remote).commit("HEAD"), candidate)

    def test_interrupted_publication_preserves_unreviewed_index_edit(self):
        prepared = self.prepare()
        self.remote.fail_push = True
        with self.assertRaises(c.Invalid):
            self.publish(prepared)
        wiki = c.Git(self.root / s.PUBLISH)
        oid = wiki.run("hash-object", "-w", "--stdin", input=b"Fixture user-staged edit\n").decode().strip()
        wiki.run("update-index", "--cacheinfo", "100644," + oid + ",Home.md")
        with self.assertRaisesRegex(c.Invalid, "index"):
            self.publish(prepared)
        self.assertIn(oid.encode(), wiki.run("ls-files", "--stage", "--", "Home.md"))

    def test_dirty_publication_clone_preserves_unrelated_file(self):
        prepared = self.prepare()
        unrelated = self.root / s.PUBLISH / "Unrelated.txt"
        unrelated.write_text("Fixture user data")
        with self.assertRaises(c.Invalid):
            self.publish(prepared)
        self.assertEqual(unrelated.read_text(), "Fixture user data")

    def test_ignored_extra_file_blocks_subsequent_preparation(self):
        self.publish(self.prepare())
        wiki = self.root / s.PUBLISH
        (wiki / ".git/info/exclude").write_text("Hidden-fixture.txt\n")
        (wiki / "Hidden-fixture.txt").write_text("Fixture user data")
        with self.assertRaises(c.Invalid):
            self.prepare(adopt=False)
        self.assertEqual((wiki / "Hidden-fixture.txt").read_text(), "Fixture user data")

    def test_redirected_git_worktree_is_rejected(self):
        prepared = self.prepare()
        wiki = c.Git(self.root / s.PUBLISH)
        outside = self.base / "outside-worktree"
        outside.mkdir()
        wiki.run("config", "core.worktree", str(outside))
        with self.assertRaises(c.Invalid):
            self.publish(prepared)
        self.assertFalse(list(outside.iterdir()))

    def test_managed_deletion_and_subsequent_no_change(self):
        self.publish(self.prepare())
        (self.root / "wiki/Extra.md").unlink()
        self.manifest["pages"] = [page for page in self.manifest["pages"] if page["target"] != "Extra.md"]
        (self.root / c.MANIFEST).write_bytes(c.canonical(self.manifest))
        self.commit()
        self.public_source()
        self.publish(self.prepare(adopt=False))
        self.assertNotIn("Extra.md", c.Git(self.wiki_remote).entries("HEAD"))
        count = len(self.remote.pushes)
        self.assertEqual(self.publish(self.prepare(adopt=False)), "already-published")
        self.assertEqual(len(self.remote.pushes), count)

    def test_forward_content_rollback(self):
        self.publish(self.prepare())
        (self.root / "wiki/Home.md").write_bytes(page_bytes(extra="A later published fixture\n"))
        self.commit()
        self.public_source()
        self.publish(self.prepare(adopt=False))
        middle = c.Git(self.wiki_remote).commit("HEAD")
        self.publish(self.prepare(self.initial, adopt=False))
        final = c.Git(self.wiki_remote).commit("HEAD")
        self.assertTrue(c.Git(self.wiki_remote).ancestor(middle, final))
        self.assertEqual(p.read_provenance(c.Git(self.wiki_remote), final)["source"], self.initial)

    def test_interrupted_prepare_retry_preserves_partial_artifact(self):
        original = s.write
        def interrupted(root, name, data, **kwargs):
            if name == "report.md":
                raise OSError("fixture interruption")
            return original(root, name, data, **kwargs)
        with mock.patch.object(s, "write", side_effect=interrupted), self.assertRaises(OSError):
            self.prepare()
        parent = self.root / s.BUILD / "prepared"
        partials = {name for name in os.listdir(parent) if name.startswith(".partial-")}
        self.assertEqual(len(partials), 1)
        self.prepare()
        self.assertTrue(partials <= set(os.listdir(parent)))

    def test_wiki_hook_rechecks_reviewed_candidate(self):
        prepared = self.prepare()
        self.remote.fail_push = True
        with self.assertRaises(c.Invalid):
            self.publish(prepared)
        wiki = c.Git(self.root / s.PUBLISH)
        candidate = wiki.commit("HEAD")
        data = f"{candidate} {candidate} refs/heads/master {self.bootstrap}\n".encode()
        p.wiki_pre_push(wiki.root, data, "origin", c.WIKI_REPO, remote=self.remote, checker=self.online)
        with self.assertRaises(c.Invalid):
            p.wiki_pre_push(wiki.root, data + data, "origin", c.WIKI_REPO, remote=self.remote, checker=self.online)


if __name__ == "__main__":
    unittest.main()
