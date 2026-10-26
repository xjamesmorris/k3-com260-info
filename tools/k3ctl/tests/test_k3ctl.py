#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""End-to-end test of the k3ctl client against a fake dongle on a pty.

The fake speaks the firmware protocol (see firmware/k3ctl/k3ctl.ino), including
the awkward bits the client must survive: a ROM boot banner before the first
reply, a reboot-shaped silence on the first ping, and CRLF line endings.

Run:  python3 tests/test_k3ctl.py
"""
from __future__ import annotations

import os
import pty
import select
import subprocess
import sys
import threading
import tty
import unittest
from pathlib import Path

CLIENT = Path(__file__).resolve().parent.parent / "k3ctl"


class FakeDongle(threading.Thread):
    """Minimal protocol server on the master side of a pty."""

    def __init__(self, drop_first_ping: bool = False, banner: bool = True) -> None:
        super().__init__(daemon=True)
        self.master, self.slave = pty.openpty()
        tty.setraw(self.slave)   # no line-discipline echo of our own output
        self.path = os.ttyname(self.slave)
        self.drop_first_ping = drop_first_ping
        self.banner = banner
        self.received: list[str] = []
        self._quit = False

    def reply(self, line: str) -> str | None:
        parts = line.split()
        cmd = parts[0] if parts else ""
        if cmd == "ping":
            if self.drop_first_ping:
                self.drop_first_ping = False
                return None                      # simulate reboot-on-open
            return "OK pong k3ctl test"
        if cmd == "reset":
            return "OK reset"
        if cmd == "recovery":
            return "OK recovery"
        if cmd == "status":
            return "OK status rst=0 fcrec=0 pwr=0 k3=n/a up=1 ver=test"
        if cmd == "press" and len(parts) == 3:
            return f"OK press {parts[1]} {parts[2]}"
        return "ERR unknown command (try help)"

    def run(self) -> None:
        buf = b""
        if self.banner:
            os.write(self.master, b"ESP-ROM:esp32c3-api1-20210207\r\nBuild:Feb  7 2021\r\n")
        while not self._quit:
            r, _, _ = select.select([self.master], [], [], 0.1)
            if not r:
                continue
            try:
                data = os.read(self.master, 256)
            except OSError:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                text = line.decode().strip()
                self.received.append(text)
                rep = self.reply(text)
                if rep is not None:
                    os.write(self.master, (rep + "\r\n").encode())

    def stop(self) -> None:
        self._quit = True
        self.join(timeout=2)
        for fd in (self.master, self.slave):
            try:
                os.close(fd)
            except OSError:
                pass


def run_client(dev: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(CLIENT), "-d", dev, "-t", "2", *args],
                          capture_output=True, text=True, timeout=20)


class ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dongle = FakeDongle()
        self.dongle.start()

    def tearDown(self) -> None:
        self.dongle.stop()

    def test_reset_ok(self) -> None:
        r = run_client(self.dongle.path, "reset")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "OK reset")
        self.assertEqual(self.dongle.received, ["ping", "reset"])

    def test_recovery_ok_quiet(self) -> None:
        r = run_client(self.dongle.path, "-q", "recovery")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_err_reply_exit_1(self) -> None:
        r = run_client(self.dongle.path, "raw", "bogus")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ERR unknown command", r.stderr)

    def test_press_with_duration(self) -> None:
        r = run_client(self.dongle.path, "press", "fcrec", "1500")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "OK press fcrec 1500")

    def test_bad_duration_rejected_locally(self) -> None:
        r = run_client(self.dongle.path, "press", "rst", "99999")
        self.assertEqual(r.returncode, 2)          # argparse/SystemExit path
        self.assertEqual(self.dongle.received, [])  # never touched the device

    def test_arity_checked_locally(self) -> None:
        r = run_client(self.dongle.path, "reset", "now")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.dongle.received, [])


class RebootOnOpenTest(unittest.TestCase):
    def test_first_ping_swallowed(self) -> None:
        dongle = FakeDongle(drop_first_ping=True)
        dongle.start()
        try:
            r = run_client(dongle.path, "status")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(r.stdout.startswith("OK status"))
            self.assertGreaterEqual(dongle.received.count("ping"), 2)
        finally:
            dongle.stop()


class NoDeviceTest(unittest.TestCase):
    def test_missing_device_exit_2(self) -> None:
        r = run_client("/dev/does-not-exist-k3ctl", "ping")
        self.assertEqual(r.returncode, 2)
        self.assertIn("cannot open", r.stderr)

    def test_silent_device_exit_2(self) -> None:
        dongle = FakeDongle(banner=False)
        dongle.reply = lambda line: None      # type: ignore[method-assign]
        dongle.start()
        try:
            r = run_client(dongle.path, "ping")
            self.assertEqual(r.returncode, 2)
            self.assertIn("did not answer", r.stderr)
        finally:
            dongle.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
