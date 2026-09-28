#!/usr/bin/env python3
"""`pb update` — what it tells you when a flash does not take.

`installFirmwareFile` already works out why; the CLI's job is not to throw that
away. It did, and the cost was real: a refused image and a truncated upload both
came out as the same sentence, and they want opposite next moves.
"""

import contextlib
import io
from pathlib import Path

from click.testing import CliRunner

from pixelblaze.cli import cli as cli_mod
from pixelblaze.cli.cli import pixelblaze


class FakePB:
    """Stands in for a device: emits the events installFirmwareFile would."""

    ok = False
    reason = None
    version = "3.51"

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def getVersion(self):
        return self.version

    def installFirmwareFile(self, path, *, monitor=True, callback=None, **kw):
        if monitor and callback:
            callback({'type': 'start', 'total': 1024})
            callback({'type': 'chunk', 'sent': 1024, 'total': 1024})
            callback({'type': 'result', 'ok': type(self).ok, 'reason': type(self).reason})
        return type(self).ok


def _run(tmp, monkeypatch, *, ok, reason, extra=()):
    monkeypatch.setattr(cli_mod, 'Pixelblaze', FakePB)
    FakePB.ok, FakePB.reason = ok, reason
    fw = Path(tmp) / "v3.70.pb32.stfu"
    fw.write_bytes(b"STFU" + b"\0" * 64)
    runner = CliRunner()
    return runner.invoke(pixelblaze, ['--ip', '10.0.0.5', 'update', str(fw), *extra])


def test_a_failed_flash_reports_the_device_s_own_reason(tmp_path, monkeypatch):
    """The whole point: say which failure it was."""
    reason = ("device reported upgradeState.updateError; HTTP 200 "
              "body='Update Success! Rebooting...'")
    result = _run(tmp_path, monkeypatch, ok=False, reason=reason)

    assert result.exit_code != 0
    out = result.output
    assert "updateError" in out, out
    # and it must not fall back to the old guess-list
    assert "wrong variant, corrupted file, or flash error" not in out, out
    print("✓ a failed flash reports the device's own reason")


def test_the_http_lies_contradiction_is_called_out(tmp_path, monkeypatch):
    """HTTP 200 'Update Success!' alongside updateError is the confusing case.

    Anything trusting the HTTP response reports a flash that never happened, so
    the contradiction is worth saying out loud rather than leaving to be noticed.
    """
    reason = ("device reported upgradeState.updateError; HTTP 200 "
              "body='Update Success! Rebooting...'")
    out = _run(tmp_path, monkeypatch, ok=False, reason=reason).output
    assert "not trustworthy" in out, out
    assert "the file the device objects to, not the transfer" in out, out
    print("✓ the HTTP-said-success contradiction is called out")


def test_a_truncated_upload_is_not_dressed_up_as_a_rejection(tmp_path, monkeypatch):
    """A short upload is a transport problem and reads as one."""
    reason = "only sent 700000/1505737 bytes before upload returned; HTTP 200"
    out = _run(tmp_path, monkeypatch, ok=False, reason=reason).output
    assert "only sent 700000/1505737 bytes" in out, out
    assert "not trustworthy" not in out, out        # no HTTP-lies hint here
    print("✓ a truncated upload is reported as itself")


def test_no_monitor_says_why_it_has_no_reason(tmp_path, monkeypatch):
    """--no-monitor judges on the HTTP response alone, so there is nothing to
    report — say that, rather than printing an empty reason."""
    out = _run(tmp_path, monkeypatch, ok=False, reason=None, extra=('--no-monitor',)).output
    assert "no reason available" in out, out
    assert "--no-monitor" in out, out
    print("✓ --no-monitor explains why it has no reason")


def test_success_still_says_so(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, ok=True, reason="device reported updateComplete")
    assert result.exit_code == 0, result.output
    assert "Firmware accepted" in result.output, result.output
    print("✓ a good flash still reports success")
