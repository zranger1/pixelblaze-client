#!/usr/bin/env python3
"""Unit tests for `pb off` / `pb on` (pause, --deep). No Pixelblaze hardware needed."""

import json

import pytest
from click.testing import CliRunner

from pixelblaze.cli import cli as cli_mod
from pixelblaze.cli import cli_utils
from pixelblaze.cli.cli import pixelblaze, OFF_MARKER
from pixelblaze.pixelblaze import Pixelblaze


class FakePixelblaze:
    """Records every call, in order, as (method, *args)."""
    cpuSpeeds = Pixelblaze.cpuSpeeds
    ipAddress = '192.168.1.12'

    def __init__(self, cpu_speed=240, marker=None, ver='3.51'):
        self.calls = []
        self.files = {} if marker is None else {OFF_MARKER: json.dumps(marker).encode()}
        self.settings = {'ver': ver, 'cpuSpeed': cpu_speed}
        self.connected = True

    def __enter__(self): return self
    def __exit__(self, *exc): pass
    def _record(self, *call): self.calls.append(call)

    def getConfigSettings(self): return dict(self.settings)
    def getCpuSpeed(self, configSettings=None):  # the real one, to exercise its int/str handling
        return Pixelblaze.getCpuSpeed(self, configSettings or self.getConfigSettings())
    def getFile(self, name): return self.files.get(name)
    def putFile(self, name, data): self._record('putFile', name, json.loads(data)); self.files[name] = data
    def deleteFile(self, name): self._record('deleteFile', name); self.files.pop(name, None)
    def setBrightnessSlider(self, b, saveToFlash=False): self._record('brightness', b, saveToFlash)
    def pauseSequencer(self, saveToFlash=False): self._record('pauseSequencer', saveToFlash)
    def playSequencer(self, saveToFlash=False): self._record('playSequencer', saveToFlash)
    def pauseRenderer(self, doPause): self._record('pauseRenderer', doPause)
    def setCpuSpeed(self, speed): self._record('setCpuSpeed', speed.value); self.pending_cpu = int(speed.value)
    def compilePattern(self, code, allow_cache=False): return b'bytecode:' + code.encode()
    def sendPatternToRenderer(self, bytecode): self._record('sendPattern', bytecode)

    def reboot(self):
        self._record('reboot')
        self.settings['cpuSpeed'] = getattr(self, 'pending_cpu', self.settings['cpuSpeed'])
    def _close(self): self.connected = False
    def _open(self): self._record('reconnect'); self.connected = True


@pytest.fixture
def run(monkeypatch):
    """Invoke `pb ...` against a FakePixelblaze whose websocket port goes down, then up."""
    def _run(fake, *args, port_states=(True, False, True)):
        states = iter(port_states)
        monkeypatch.setattr(cli_utils, 'get_pixelblaze', lambda ctx: fake)
        monkeypatch.setattr(cli_utils, 'maybe_refresh_cache', lambda *a, **k: False)
        monkeypatch.setattr(cli_mod, '_tcp_ports_open', lambda ip, ports: {ports[0]: next(states, True)})
        monkeypatch.setattr(cli_mod.time, 'sleep', lambda s: None)
        return CliRunner().invoke(pixelblaze, ['--ip', fake.ipAddress, '--retries', '0', *args])
    return _run


def names(fake):
    return [c[0] for c in fake.calls]


def test_off_blanks_then_pauses_renderer(run):
    fake = FakePixelblaze()
    result = run(fake, 'off')
    assert result.exit_code == 0, result.output
    assert fake.calls == [('brightness', 0.0, True), ('pauseRenderer', True)]


def test_on_without_marker_resumes_renderer_before_brightness(run):
    fake = FakePixelblaze()
    result = run(fake, 'on', '0.4')
    assert result.exit_code == 0, result.output
    assert fake.calls == [('pauseRenderer', False), ('brightness', 0.4, True)]


def test_off_deep_records_before_changing_then_parks_after_reboot(run):
    fake = FakePixelblaze(cpu_speed=240)
    result = run(fake, 'off', '--deep')
    assert result.exit_code == 0, result.output
    assert fake.calls == [
        ('brightness', 0.0, True),
        ('putFile', OFF_MARKER, {'cpuSpeed': '240'}),
        ('setCpuSpeed', '80'),
        ('reboot',),
        ('reconnect',),
        ('pauseSequencer', False),
        ('sendPattern', b'bytecode:' + cli_mod.NOOP_PATTERN.encode()),
        ('pauseRenderer', True),
    ]


def test_off_deep_keeps_an_existing_marker_and_skips_unneeded_cpu_change(run):
    fake = FakePixelblaze(cpu_speed=80, marker={'cpuSpeed': '160'})
    result = run(fake, 'off', '--deep')
    assert result.exit_code == 0, result.output
    assert 'putFile' not in names(fake) and 'setCpuSpeed' not in names(fake)
    assert json.loads(fake.files[OFF_MARKER]) == {'cpuSpeed': '160'}


def test_on_after_deep_restores_cpu_and_removes_marker_only_after_reboot(run):
    fake = FakePixelblaze(cpu_speed=80, marker={'cpuSpeed': '240'})
    result = run(fake, 'on', '0.4')
    assert result.exit_code == 0, result.output
    assert fake.calls == [
        ('setCpuSpeed', '240'),
        ('reboot',),
        ('reconnect',),
        ('deleteFile', OFF_MARKER),
        ('brightness', 0.4, True),
    ]
    assert fake.settings['cpuSpeed'] == 240


def test_off_deep_fails_loudly_when_cpu_speed_does_not_stick(run):
    fake = FakePixelblaze(cpu_speed=240)
    fake.setCpuSpeed = lambda speed: fake._record('setCpuSpeed', speed.value)  # device ignores it
    result = run(fake, 'off', '--deep')
    assert result.exit_code != 0
    assert 'not 80MHz' in result.output
    assert names(fake)[-1] == 'pauseRenderer'  # still parked dark before failing


def test_off_deep_fails_loudly_when_device_never_goes_down(run, monkeypatch):
    fake = FakePixelblaze()
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(cli_mod.time, 'monotonic', lambda: next(clock))
    result = run(fake, 'off', '--deep', port_states=[True] * 100)
    assert result.exit_code != 0
    assert 'did not go down' in result.output
    assert 'pauseRenderer' not in names(fake)


def test_off_deep_rejects_no_save(run):
    fake = FakePixelblaze()
    result = run(fake, 'off', '--deep', '--no-save')
    assert result.exit_code != 0
    assert fake.calls == []


def test_off_deep_rejects_v2(run):
    fake = FakePixelblaze(ver='2.29')
    result = run(fake, 'off', '--deep')
    assert result.exit_code != 0
    assert 'v3' in result.output


def test_get_cpu_speed_accepts_the_int_firmware_reports():
    assert FakePixelblaze().getCpuSpeed({'cpuSpeed': 240}) == Pixelblaze.cpuSpeeds.high
    assert FakePixelblaze().getCpuSpeed({'cpuSpeed': '80'}) == Pixelblaze.cpuSpeeds.low
