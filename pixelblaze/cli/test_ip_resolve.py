#!/usr/bin/env python3
"""Unit tests for the flexible --ip resolution. No Pixelblaze hardware needed."""

import click

from pixelblaze.cli import cli_utils
from pixelblaze.cli.cli_utils import resolve_ip_spec

# Stand-in for ~/.config/pixelblaze/cache.json.
FAKE_CACHE = {
    'lastIp': None,
    'devices': {
        '192.168.1.230': {'ip': '192.168.1.230', 'name': 'Kitchen Strip',
                          'lastSeenAt': '2026-01-01T00:00:00+00:00'},
        '192.168.1.231': {'ip': '192.168.1.231', 'name': 'Kitchen Nook',
                          'lastSeenAt': '2026-06-01T00:00:00+00:00'},
        '10.1.1.240': {'ip': '10.1.1.240', 'name': 'Porch'},
        '10.1.1.241': {'ip': '10.1.1.241', 'name': 'Porch Extra'},
        '192.168.4.1': {'ip': '192.168.4.1'},  # discovered but never named
    },
}

FAKE_HOST_IP = '192.168.1.55'

RESOLVES = [
    # auto / empty means "fall back to discovery"
    ('auto', None),
    ('AUTO', None),
    ('', None),
    ('   ', None),
    (None, None),
    # exact IP — the fast path
    ('192.168.1.230', '192.168.1.230'),
    (' 10.0.0.7 ', '10.0.0.7'),
    # pasted out of a browser
    ('http://192.168.1.230/', '192.168.1.230'),
    ('https://192.168.1.230:8080/edit?x=1#frag', '192.168.1.230'),
    ('HTTP://192.168.1.230', '192.168.1.230'),
    ('http://user:pw@10.0.0.5/', '10.0.0.5'),
    ('http://pixelblaze.local/', 'pixelblaze.local'),
    # bare host number on the local /24
    ('230', '192.168.1.230'),
    ('0', '192.168.1.0'),
    ('255', '192.168.1.255'),
    # cached device name
    ('kitchen strip', '192.168.1.230'),  # exact name beats the substring rule
    ('KITCHEN NOOK', '192.168.1.231'),
    ('nook', '192.168.1.231'),
    ('porch', '10.1.1.240'),  # exact 'Porch' wins over 'Porch Extra'
    ('porch e', '10.1.1.241'),
    # Several matches is not an error: the reachable one wins, the rest are
    # logged. Both Kitchens are on this machine's /24, so the tie falls to the
    # one seen most recently.
    ('kitchen', '192.168.1.231'),
]

REJECTS = [
    ('999.1.1.1', 'octet'),      # dotted quad, out of range
    ('256', 'out of range'),     # bare number, out of range
    ('ab', 'at least 3'),        # too short to name-match
    ('nope', 'Could not resolve'),
    ('http://', 'No host'),
]


def test_ip_resolve():
    """Check every accepted --ip form, and that bad ones fail clearly."""
    original_read_cache, original_host_ip = cli_utils._read_cache, cli_utils.get_host_ip
    cli_utils._read_cache = lambda: FAKE_CACHE
    cli_utils.get_host_ip = lambda: FAKE_HOST_IP
    try:
        for spec, expected in RESOLVES:
            actual = resolve_ip_spec(spec)
            assert actual == expected, f"--ip {spec!r}: expected {expected!r}, got {actual!r}"

        for spec, expected_msg in REJECTS:
            try:
                actual = resolve_ip_spec(spec)
            except click.ClickException as e:
                assert expected_msg in e.message, \
                    f"--ip {spec!r}: expected {expected_msg!r} in error, got {e.message!r}"
            else:
                raise AssertionError(f"--ip {spec!r}: expected failure, got {actual!r}")
    finally:
        cli_utils._read_cache, cli_utils.get_host_ip = original_read_cache, original_host_ip

    print(f"✓ {len(RESOLVES)} resolved, {len(REJECTS)} rejected")


# Several cached devices answering to one name is the normal state of a
# Pixelblaze that has been on more than one network. The reported case:
#
#   $ pb --ip aurora cfg
#   Error: Ambiguous --ip 'aurora': matches aurora (10.1.1.34), aurora (10.1.9.4), ...
#
# Refusing to choose is wrong when one of them is on the subnet this machine is
# on right now and the rest are from another building.

SAME_NAME_CACHE = {
    'lastIp': None,
    'devices': {
        '10.1.1.34': {'ip': '10.1.1.34', 'name': 'aurora',
                         'lastSeenAt': '2026-09-01T10:00:00+00:00'},
        '10.1.9.4': {'ip': '10.1.9.4', 'name': 'aurora',
                        'lastSeenAt': '2026-09-18T10:00:00+00:00'},
        '10.1.9.3': {'ip': '10.1.9.3', 'name': 'aurora',
                        'lastSeenAt': '2026-09-19T10:00:00+00:00'},
    },
}


def _with_cache(cache, host_ip):
    """Swap in a fake cache and host address for one call."""
    original = cli_utils._read_cache, cli_utils.get_host_ip
    cli_utils._read_cache = lambda: cache
    cli_utils.get_host_ip = lambda: host_ip
    return original


def _restore(original):
    cli_utils._read_cache, cli_utils.get_host_ip = original


def test_same_name_picks_the_one_this_machine_can_reach():
    for host_ip, expected in [('10.1.9.55', '10.1.9.3'),    # newest on my /24
                              ('10.1.1.55', '10.1.1.34'),   # only one on my /24
                              ('10.0.0.7', '10.1.9.3')]:       # none: newest wins
        original = _with_cache(SAME_NAME_CACHE, host_ip)
        try:
            assert resolve_ip_spec('aurora') == expected, f"from {host_ip}"
        finally:
            _restore(original)


def test_the_host_address_it_was_last_seen_from_breaks_a_tie():
    """Weaker evidence than the subnet, for a /24 this machine has since left."""
    cache = {'lastIp': None, 'devices': {
        '10.1.1.9': {'ip': '10.1.1.9', 'name': 'aurora', 'hostIp': '172.16.0.5',
                     'lastSeenAt': '2026-09-19T10:00:00+00:00'},
        '10.2.2.9': {'ip': '10.2.2.9', 'name': 'aurora', 'hostIp': '192.168.9.9',
                     'lastSeenAt': '2026-09-20T10:00:00+00:00'},
    }}
    original = _with_cache(cache, '172.16.0.5')
    try:
        assert resolve_ip_spec('aurora') == '10.1.1.9', "seen from here beats seen later"
    finally:
        _restore(original)


def test_the_other_matches_are_named_not_silently_dropped(capsys):
    original = _with_cache(SAME_NAME_CACHE, '10.1.9.55')
    try:
        resolve_ip_spec('aurora')
    finally:
        _restore(original)
    said = capsys.readouterr().err
    assert "matched 3 devices" in said
    assert "using 10.1.9.3" in said
    assert "subnet 10.1.9.x" in said
    assert "10.1.9.4" in said and "10.1.1.34" in said
    assert "comma-separated" in said, "and how to reach all of them"


def test_ranking_is_stable_when_nothing_separates_the_matches():
    cache = {'lastIp': None, 'devices': {
        '10.0.0.9': {'ip': '10.0.0.9', 'name': 'aurora'},
        '10.0.0.2': {'ip': '10.0.0.2', 'name': 'aurora'},
    }}
    original = _with_cache(cache, '')
    try:
        assert resolve_ip_spec('aurora') == '10.0.0.2'
        assert resolve_ip_spec('aurora') == '10.0.0.2'
    finally:
        _restore(original)


if __name__ == '__main__':
    test_ip_resolve()
