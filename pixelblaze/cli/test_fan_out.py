#!/usr/bin/env python3
"""Unit tests for `--ip` naming several devices. No hardware, no network.

    python3 -m pytest pixelblaze/cli/test_fan_out.py
"""

import io
import sys
import threading
import time

import click
import pytest
from click.testing import CliRunner

from pixelblaze.cli import cli_utils
from pixelblaze.cli.cli_utils import fan_out, resolve_ip_specs, run_per_address

FAKE_CACHE = {
    'lastIp': None,
    'devices': {
        '192.168.1.230': {'ip': '192.168.1.230', 'name': 'Kitchen Strip',
                          'lastSeenAt': '2026-09-01T00:00:00+00:00'},
        '192.168.1.240': {'ip': '192.168.1.240', 'name': 'Porch',
                          'lastSeenAt': '2026-09-02T00:00:00+00:00'},
        '10.0.0.5': {'ip': '10.0.0.5', 'name': 'Garage',
                     'lastSeenAt': '2026-09-03T00:00:00+00:00'},
    },
}


@pytest.fixture
def cache(monkeypatch):
    monkeypatch.setattr(cli_utils, 'cached_by_ip', lambda: FAKE_CACHE['devices'])
    monkeypatch.setattr(cli_utils, '_read_cache', lambda: FAKE_CACHE)
    monkeypatch.setattr(cli_utils, 'get_host_ip', lambda: '192.168.1.55')


# ── what a --ip value can name ─────────────────────────────────────────────

@pytest.mark.parametrize("spec, expected", [
    (None, []),
    ('', []),
    ('auto', []),
    ('  ,  ,', []),
    ('192.168.1.230', ['192.168.1.230']),
    # Every form mixes freely inside one list.
    ('192.168.1.230,porch,240,http://10.0.0.5/',
     ['192.168.1.230', '192.168.1.240', '192.168.1.240', '10.0.0.5']),
    (' 10.0.0.5 , 10.0.0.6 ', ['10.0.0.5', '10.0.0.6']),
])
def test_a_list_resolves_each_part_the_way_one_value_would(cache, spec, expected):
    # '240' and 'porch' are the same device: duplicates collapse, order kept.
    assert resolve_ip_specs(spec) == list(dict.fromkeys(expected))


def test_all_means_every_cached_device_reachable_ones_first(cache):
    """Ranked, so the /24 this machine is on leads."""
    assert resolve_ip_specs('all') == ['192.168.1.240', '192.168.1.230', '10.0.0.5']


def test_all_mixes_with_everything_else_and_still_collapses(cache):
    assert resolve_ip_specs('10.0.0.5,all') == ['10.0.0.5', '192.168.1.240', '192.168.1.230']


def test_all_with_an_empty_cache_says_what_to_run(monkeypatch):
    monkeypatch.setattr(cli_utils, 'cached_by_ip', lambda: {})
    monkeypatch.setattr(cli_utils, '_read_cache', lambda: {'devices': {}})
    with pytest.raises(click.ClickException, match="pb find"):
        resolve_ip_specs('all')


def test_one_bad_entry_fails_the_whole_list_rather_than_quietly_doing_less(cache):
    """Half a fan-out is worse than none: you would not know which half."""
    with pytest.raises(click.ClickException, match="nope"):
        resolve_ip_specs('192.168.1.230,nope')


# ── running them ───────────────────────────────────────────────────────────

class Timestamped(io.StringIO):
    """Records when each write happened, to prove output is not held back."""

    def __init__(self):
        super().__init__()
        self.at = []
        self.started = time.monotonic()

    def write(self, text):
        if text.strip():
            self.at.append((time.monotonic() - self.started, text))
        return super().write(text)


@pytest.fixture
def streams():
    """Where the grouped blocks should land. Passed in rather than patched into
    `sys`, which pytest's own capture also owns and re-installs per phase."""
    return Timestamped(), Timestamped()


def test_each_device_output_stays_in_one_piece(streams, cache):
    """Workers interleave; their lines must not."""
    out, err = streams

    def run(address):
        for line in range(3):
            print(f"{address} line {line}")
            time.sleep(0.02)
        return address

    run_per_address(['192.168.1.230', '192.168.1.240', '10.0.0.5'], run, out=out, err=err)

    lines = [l for l in out.getvalue().split("\n") if l]
    assert len(lines) == 9
    for start in range(0, 9, 3):
        block = lines[start:start + 3]
        address = block[0].split()[0]
        assert block == [f"{address} line {i}" for i in range(3)], \
            f"{address}'s lines got shuffled into someone else's"


def test_a_finished_device_prints_before_a_slow_one_is_done(streams):
    """Incremental, not a full wait -- and so, completion order."""
    out, _ = streams

    def run(address):
        time.sleep(0.6 if address == 'slow' else 0.0)
        print(f"{address} done")

    run_per_address(['slow', 'quick'], run, out=out, err=Timestamped())

    when = {text.split()[0]: at for at, text in out.at}
    assert when['quick'] < 0.3, "held up by the slow one ahead of it"
    assert when['slow'] > when['quick']
    assert out.getvalue().index('quick') < out.getvalue().index('slow')


def test_stdout_and_stderr_stay_separate_so_a_pipe_still_works(streams, cache):
    """`pb --ip all ls | jq` must see only the devices' stdout."""
    out, err = streams

    def run(address):
        click.echo(f'{{"ip":"{address}"}}')
        click.echo(f"connecting to {address}...", err=True)

    run_per_address(['192.168.1.230', '10.0.0.5'], run, out=out, err=err)

    assert "connecting" not in out.getvalue()
    assert '{"ip"' not in err.getvalue()
    assert out.getvalue().count('{"ip"') == 2
    # The label is commentary, so it goes with the commentary.
    assert "── 192.168.1.230 (Kitchen Strip)" in err.getvalue()
    assert "── 10.0.0.5 (Garage)" in err.getvalue()


def test_a_failure_is_captured_and_the_others_still_run(streams):
    out, _ = streams

    def run(address):
        if address == 'bad':
            raise RuntimeError("nope")
        print(f"{address} ok")
        return address

    outcomes = run_per_address(['bad', 'good'], run, out=out, err=Timestamped())

    assert [a for a, _, _ in outcomes] == ['bad', 'good'], "returned in the order given"
    assert isinstance(outcomes[0][2], RuntimeError)
    assert outcomes[1][1] == 'good' and outcomes[1][2] is None
    assert "good ok" in out.getvalue()


def test_fan_out_summarises_and_fails_the_command(streams):
    _, err = streams

    def run(address):
        if address.endswith('9'):
            raise RuntimeError("refused")

    with pytest.raises(click.ClickException, match="1 of 2 failed"):
        fan_out(['10.0.0.1', '10.0.0.9'], run, out=Timestamped(), err=err)
    assert "1/2 succeeded" in err.getvalue()
    assert "✗ 10.0.0.9: RuntimeError: refused" in err.getvalue()


def test_the_real_streams_are_put_back_even_when_everything_fails():
    before = (sys.stdout, sys.stderr)
    run_per_address(['a', 'b'], lambda address: 1 / 0,
                    out=Timestamped(), err=Timestamped())
    assert (sys.stdout, sys.stderr) == before


def test_a_captured_stream_does_not_claim_to_be_a_terminal():
    """Otherwise colour codes and progress bars land in the middle of a block."""
    seen = []
    run_per_address(['a'], lambda address: seen.append(sys.stdout.isatty()),
                    out=Timestamped(), err=Timestamped())
    assert seen == [False]


def test_prefix_tags_stdout_for_a_pipe_that_has_no_other_clue(streams):
    """`pb --ip all pixels | ...` is otherwise a column of bare numbers."""
    out, err = streams

    def run(address):
        print(address.split('.')[-1])
        print("second line")

    run_per_address(['10.0.0.5', '10.0.0.6'], run, out=out, err=err, prefix=True)
    lines = sorted(l for l in out.getvalue().split("\n") if l)
    assert lines == ["10.0.0.5\t5", "10.0.0.5\tsecond line",
                     "10.0.0.6\t6", "10.0.0.6\tsecond line"]


def test_prefix_does_not_invent_a_trailing_newline(streams):
    out, err = streams
    run_per_address(['10.0.0.5'], lambda a: sys.stdout.write("no newline"),
                    out=out, err=err, prefix=True)
    assert out.getvalue() == "10.0.0.5\tno newline"


def test_a_device_that_says_nothing_still_gets_its_label(streams):
    out, err = streams
    run_per_address(['10.0.0.5'], lambda a: None, out=out, err=err, prefix=True)
    assert out.getvalue() == ""
    assert "── 10.0.0.5" in err.getvalue()


# ── the wiring: one --ip, N invocations ────────────────────────────────────

def _fake_cli(monkeypatch, fan_out_ips=True):
    """A `pb`-shaped group with one command, connecting to nothing."""
    class FakePixelblaze:
        def __init__(self, ip):
            self.ipAddress = ip

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(cli_utils, 'Pixelblaze', FakePixelblaze)
    monkeypatch.setattr(cli_utils, 'maybe_refresh_cache', lambda *a, **k: False)
    monkeypatch.setattr(cli_utils, 'cache_ip', lambda ip: None)

    @click.group()
    @click.option('--ip', default='auto')
    @click.pass_context
    def group(ctx, ip):
        ctx.ensure_object(dict)
        ctx.obj.update(ip=ip, timeout=5.0, retries=0)

    @cli_utils.cli(group, fan_out_ips=fan_out_ips)
    def touch(pb):
        """Say which device this invocation got."""
        click.echo(f"touched {pb.ipAddress}")

    @cli_utils.cli(group, conn=False, fan_out_ips=fan_out_ips)
    def listed(ctx):
        click.echo(f"list {ctx.obj['ips']}")

    return group


def test_one_ip_still_runs_exactly_once(monkeypatch, cache):
    result = CliRunner().invoke(_fake_cli(monkeypatch), ['--ip', '10.0.0.5', 'touch'])
    assert result.exit_code == 0
    assert result.output.strip() == "touched 10.0.0.5"


def test_several_ips_run_the_command_once_each(monkeypatch, cache):
    result = CliRunner().invoke(_fake_cli(monkeypatch),
                                ['--ip', '10.0.0.5,porch,kitchen strip', 'touch'])
    assert result.exit_code == 0
    for address in ('10.0.0.5', '192.168.1.240', '192.168.1.230'):
        assert f"touched {address}" in result.output


def test_a_command_that_opts_out_gets_the_whole_list(monkeypatch, cache):
    """`pb sensor sound` streams one capture to all of them at once, which is
    not the same thing as running it N times."""
    result = CliRunner().invoke(_fake_cli(monkeypatch, fan_out_ips=False),
                                ['--ip', '10.0.0.5,porch', 'listed'])
    assert result.exit_code == 0
    assert result.output.count("list ") == 1
    assert "'10.0.0.5', '192.168.1.240'" in result.output


def test_each_worker_sees_a_context_aimed_at_its_own_device(monkeypatch, cache):
    seen = []

    class Group(click.Group):
        pass

    group = _fake_cli(monkeypatch)

    @cli_utils.cli(group, conn=False)
    def record(ctx):
        seen.append((ctx.obj['ip'], ctx.obj['ips'], ctx.obj.get('fanning_out')))

    CliRunner().invoke(group, ['--ip', '10.0.0.5,porch', 'record'])
    assert sorted(seen) == [('10.0.0.5', ['10.0.0.5'], True),
                            ('192.168.1.240', ['192.168.1.240'], True)]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
