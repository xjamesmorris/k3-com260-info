# SPDX-License-Identifier: GPL-2.0-only
"""Bounded public HTTPS checks with DNS-to-socket pinning, never proxy requests."""

from __future__ import annotations

from dataclasses import dataclass
import http.client
import io
import ipaddress
import json
import re
import socket
import ssl
import subprocess
import sys
import time
from urllib.parse import urljoin, urlsplit, urlunsplit
import zlib

import checks
import content as c

TIMEOUT = 8.0
DNS_TIMEOUT = 5.0
MAX_BODY = 128 * 1024
MAX_CHECKSUM = 4 * 1024
MAX_HEADERS = 32 * 1024
MAX_REDIRECTS = 3
RETRIES = 3
RESERVED = ("example.com", "example.org", "example.net")


class Unavailable(c.Invalid):
    """Availability failure, distinct from an unsafe URL or response."""


def example_host(host: str) -> bool:
    return (host in RESERVED or any(host.endswith("." + domain) for domain in RESERVED)
            or host.endswith((".example", ".invalid", ".test")))


def public_addresses(host: str, resolver) -> list[str]:
    host = host.lower().rstrip(".")
    c.require("." in host or ":" in host, "network target is not a public hostname")
    c.require(not host.endswith((".localhost", ".local", ".lan", ".internal", ".onion"))
              and host != "localhost", "local/private network target refused")
    try:
        addresses = resolver(host)
    except (OSError, subprocess.TimeoutExpired):
        raise Unavailable("DNS resolution unavailable or timed out") from None
    c.require(addresses and len(addresses) <= 32, "empty or oversized DNS answer")
    families = {4: set(), 6: set()}
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise c.Invalid("invalid DNS address") from None
        c.require(ip.is_global and not ip.is_multicast and not ip.is_reserved
                  and not ip.is_loopback and not ip.is_link_local
                  and not (isinstance(ip, ipaddress.IPv6Address) and
                           (ip.ipv4_mapped or ip.sixtofour or ip.teredo)),
                  "DNS resolved to a non-public or transition address; request refused")
        families[ip.version].add(ip)
    ordered = []
    ipv4 = sorted(families[4], key=int)
    ipv6 = sorted(families[6], key=int)
    for index in range(max(len(ipv4), len(ipv6))):
        if index < len(ipv4):
            ordered.append(str(ipv4[index]))
        if index < len(ipv6):
            ordered.append(str(ipv6[index]))
    return ordered


def resolve(host: str) -> list[str]:
    # getaddrinfo has no portable deadline. A bounded child avoids stuck resolver threads.
    code = ("import json,socket,sys;"
            "print(json.dumps(sorted({x[4][0] for x in "
            "socket.getaddrinfo(sys.argv[1],443,type=socket.SOCK_STREAM)})))")
    result = subprocess.run([sys.executable, "-I", "-S", "-c", code, host], timeout=DNS_TIMEOUT,
                            capture_output=True, check=False, env=c.subprocess_env())
    if result.returncode:
        raise Unavailable("DNS resolution failed")
    c.require(len(result.stdout) < 8192, "oversized resolver output")
    try:
        addresses = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise c.Invalid("invalid resolver output") from None
    c.require(isinstance(addresses, list) and all(isinstance(x, str) for x in addresses),
              "invalid resolver address list")
    return addresses


class DeadlineReader(io.RawIOBase):
    def __init__(self, sock, deadline: float):
        self.sock, self.deadline = sock, deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTPS deadline")
        self.sock.settimeout(remaining)
        return self.sock.recv_into(buffer)


class DeadlineSocket:
    def __init__(self, sock, deadline: float):
        self.sock, self.deadline = sock, deadline

    def makefile(self, mode, buffering=None):
        c.require(mode == "rb", "unsupported HTTP stream mode")
        return io.BufferedReader(DeadlineReader(self.sock, self.deadline), buffer_size=8192)

    def sendall(self, data):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("HTTPS deadline")
        self.sock.settimeout(remaining)
        self.sock.sendall(data)

    def close(self):
        self.sock.close()


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, deadline: float):
        super().__init__(host, timeout=TIMEOUT, context=ssl.create_default_context())
        self.address, self.deadline = address, deadline

    def connect(self):
        family = socket.AF_INET6 if ":" in self.address else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.settimeout(max(0.001, self.deadline - time.monotonic()))
            sock.connect((self.address, 443))
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("HTTPS connection deadline")
            sock.settimeout(remaining)
            wrapped = self._context.wrap_socket(sock, server_hostname=self.host)
            self.sock = DeadlineSocket(wrapped, self.deadline)
        except BaseException:
            sock.close()
            raise


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes = b""


def decode_body(data: bytes, encoding: str, limit: int = MAX_BODY) -> bytes:
    c.require(len(data) <= limit, "encoded text response exceeds size limit")
    if not encoding or encoding == "identity":
        return data
    c.require(encoding == "gzip", "unsupported content encoding")
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        result = decoder.decompress(data, limit + 1)
        c.require(len(result) <= limit and not decoder.unconsumed_tail,
                  "decompressed text response exceeds size limit")
        c.require(decoder.eof and not decoder.unused_data, "incomplete or concatenated compressed response")
        return result
    except zlib.error:
        raise c.Invalid("invalid compressed text response") from None


def transport(method: str, url: str, address: str, deadline: float) -> Response:
    parts = urlsplit(url)
    c.require(method in ("HEAD", "GET", "CHECKSUM"), "unsupported request method")
    checksum = method == "CHECKSUM"
    if checksum:
        c.require(parts.path.endswith(".sha256") and not parts.query and not parts.fragment,
                  "checksum GET must target an explicit sidecar, never an image")
    host = parts.hostname.encode("idna").decode("ascii")
    connection = PinnedHTTPS(host, address, deadline)
    try:
        target = urlunsplit(("", "", parts.path or "/", parts.query, ""))
        connection.request("GET" if checksum else method, target, headers={
            "User-Agent": "k3-com260-info-wiki-link-check/1",
            "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
            "Accept-Encoding": "identity",
            "Connection": "close",
        })
        reply = connection.getresponse()
        raw_headers = reply.getheaders()
        c.require(sum(len(k) + len(v) + 4 for k, v in raw_headers) <= MAX_HEADERS,
                  "response headers exceed size limit")
        headers = {}
        for key, value in raw_headers:
            key = key.lower()
            c.require(key not in headers or key not in ("location", "content-length", "content-encoding"),
                      "ambiguous HTTP response headers")
            headers[key] = value
        data = b""
        if method in ("GET", "CHECKSUM") and 200 <= reply.status < 300:
            limit = MAX_CHECKSUM if checksum else MAX_BODY
            if not checksum:
                mime = headers.get("content-type", "").split(";", 1)[0].strip().lower()
                c.require(mime in ("text/html", "text/plain"), "GET refused a non-text or untyped response")
            if "content-length" in headers:
                length = headers["content-length"]
                c.require(re.fullmatch(r"\d{1,12}", length) and int(length) <= limit,
                          "declared response size exceeds the bounded text/metadata limit")
            data = decode_body(reply.read(limit + 1), headers.get("content-encoding", "").lower(), limit)
        return Response(reply.status, headers, data)
    except ssl.SSLCertVerificationError:
        raise c.Invalid("TLS certificate verification failed; no insecure retry is permitted") from None
    except (OSError, http.client.HTTPException):
        raise Unavailable("HTTPS request failed or timed out") from None
    finally:
        connection.close()


class Checker:
    """Injection is a Python test seam only; the CLI exposes no network overrides."""

    def __init__(self, resolver=resolve, request=transport):
        self.resolver, self.request = resolver, request

    def one(self, url: str, role: str, *, expected_sha256: str | None = None,
            filename: str | None = None) -> str:
        checksum = role == "critical-checksum"
        if checksum:
            c.require(isinstance(expected_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
                      and isinstance(filename, str) and "/" not in c.safe_path(filename),
                      "checksum check requires its bound image filename and SHA256")
        current, method = url, "CHECKSUM" if checksum else "HEAD"
        redirects = 0
        tried_get = False
        seen = set()
        while True:
            checks.url_shape(current)
            parts = urlsplit(current)
            if checksum:
                c.require(parts.path.rsplit("/", 1)[-1] == filename + ".sha256"
                          and not parts.query and not parts.fragment,
                          "checksum redirect does not name the bound metadata sidecar")
            host = parts.hostname.lower().rstrip(".")
            if example_host(host):
                c.require(current == url, "redirect to an example endpoint refused")
                c.require(not role.startswith("critical-"), "critical installation input cannot be an example URL")
                return "example-not-requested"
            addresses = public_addresses(host, self.resolver)
            key = (current, method)
            c.require(key not in seen, "redirect loop")
            seen.add(key)
            response = None
            for attempt in range(RETRIES + 1):
                try:
                    response = self.request(method, current, addresses[attempt % len(addresses)],
                                            time.monotonic() + TIMEOUT)
                except Unavailable:
                    if attempt == RETRIES:
                        raise
                    continue
                if response.status not in (429, 502, 503, 504) or attempt == RETRIES:
                    break
            c.require(response is not None, "missing HTTP response")
            c.require(len(response.body) <= MAX_BODY, "text response exceeds size limit")
            if 200 <= response.status < 300:
                if checksum:
                    c.require(response.status == 200, "critical checksum response is not a complete record")
                    verify_checksum(response.body, filename, expected_sha256)
                    return "checksum-matches"
                if role == "critical-artifact":
                    mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    length = response.headers.get("content-length")
                    c.require(response.status == 200 and not mime.startswith("text/")
                              and mime not in ("application/json", "application/xml"),
                              "critical image HEAD returned no image entity")
                    c.require(length is None or (re.fullmatch(r"\d{1,20}", length) and int(length) > 0),
                              "critical image HEAD returned an empty or invalid size")
                if method == "GET":
                    mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    c.require(mime in ("text/html", "text/plain"), "GET refused a non-text or untyped response")
                return "available-" + method.lower()
            if response.status in (301, 302, 303, 307, 308):
                c.require("location" in response.headers and redirects < MAX_REDIRECTS,
                          "missing redirect location or redirect limit exceeded")
                redirected = urljoin(current, response.headers["location"])
                checks.url_shape(redirected)
                c.require(not checks.ARTIFACT.search(urlsplit(redirected).path) or method == "HEAD",
                          "GET redirect to a binary artifact refused")
                redirects += 1
                current = redirected
                continue
            suffix = parts.path.rsplit("/", 1)[-1]
            text_path = "." not in suffix or suffix.lower().endswith((".html", ".htm"))
            if (response.status in (405, 501) and method == "HEAD" and not tried_get
                    and role not in ("artifact", "critical-artifact", "critical-checksum")
                    and text_path and not checks.ARTIFACT.search(parts.path)):
                method, tried_get = "GET", True
                continue
            raise Unavailable(f"HTTP {response.status}; availability not established")

    def all(self, links: list[checks.Link], exceptions: list[dict]) -> list[dict]:
        report = []
        cache = {}
        for link in links:
            key = (link.url, link.role, link.expected_sha256, link.filename)
            if key not in cache:
                try:
                    cache[key] = self.one(link.url, link.role, expected_sha256=link.expected_sha256, filename=link.filename)
                except Unavailable as exc:
                    cache[key] = exc
            result = cache[key]
            row = {"page": link.page, "url": link.url, "role": link.role}
            if link.expected_sha256:
                row.update(expected_sha256=link.expected_sha256, filename=link.filename)
            if isinstance(result, Unavailable):
                exception = next((entry for entry in exceptions
                                  if entry["page"] == link.page and entry["url"] == link.url), None)
                c.require(exception is not None and link.role == "resource",
                          f"public link unavailable ({link.page}, URL SHA256 "
                          f"{c.sha256(link.url.encode())[:16]}): {result}")
                row.update(status="reviewed-resource-exception", exception=exception)
            else:
                row["status"] = result
            report.append(row)
        return report


def verify_checksum(data: bytes, filename: str, expected_sha256: str) -> None:
    c.require(0 < len(data) <= MAX_CHECKSUM, "critical checksum metadata exceeds its size limit or is empty")
    try:
        value = data.decode("ascii")
    except UnicodeError:
        raise c.Invalid("critical checksum metadata is not an ASCII checksum record") from None
    match = re.fullmatch(r"([0-9a-f]{64}) [ *]" + re.escape(filename) + r"(?:\r?\n)?", value)
    c.require(match is not None, "critical checksum metadata has a missing, wrong, duplicate or malformed filename record")
    c.require(match[1] == expected_sha256, "critical checksum metadata disagrees with the protected public image pin")
