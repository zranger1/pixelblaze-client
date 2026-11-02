"""Resolving a device NAME to the address it actually answers at today.

The bug these pin down: a board that has lived at several addresses kept
resolving to a dead one. `--ip hat` went to 192.168.1.12, last seen in
September, while the hat was answering at 192.168.1.9 — so every command
timed out, and `pb sensor sound` beamed UDP into the void at 0 fps.

Two causes, both here:
  * ranking used the BOARD's `lastSeenAt`, which is one value shared by every
    address it has ever had, so all of them tied;
  * the tie fell through to the raw address string, where '192.168.1.12'
    sorts before '192.168.1.9' because '1' < '9'.
"""

import pytest

from pixelblaze.cli.cli_utils import (
    addr_last_seen, rank_matches, record_sighting, _ip_sort_key,
)

SEP = '2026-09-19T02:45:27+00:00'
OCT = '2026-10-03T21:31:43+00:00'
NOW = '2026-11-02T20:00:00+00:00'


def hat(rows):
    return {'chipId': '1082965', 'name': 'hat', 'lastSeenAt': OCT, 'seen': rows}


def test_the_exact_field_failure_resolves_to_the_live_address():
    """.9 (October) must beat .12 (September) on the same subnet."""
    e = hat([
        {'name': 'hat', 'ip': '192.168.1.12', 'firstSeenAt': SEP},
        {'name': 'hat', 'ip': '192.168.1.9', 'firstSeenAt': OCT},
    ])
    ranked = rank_matches([('192.168.1.12', e), ('192.168.1.9', e)])
    assert ranked[0][0] == '192.168.1.9'


def test_addresses_sort_numerically_not_as_text():
    assert _ip_sort_key('192.168.1.9') < _ip_sort_key('192.168.1.12')
    # the old lexicographic behaviour, kept here as the thing we must not do
    assert '192.168.1.12' < '192.168.1.9'


def test_per_address_recency_prefers_lastSeenAt_over_firstSeenAt():
    e = hat([{'name': 'hat', 'ip': '10.0.0.5', 'firstSeenAt': SEP, 'lastSeenAt': NOW}])
    assert addr_last_seen(e, '10.0.0.5') == NOW


def test_a_row_with_only_firstSeenAt_still_ranks():
    """Caches written before lastSeenAt existed must still get this right,
    without being rebuilt."""
    e = hat([{'name': 'hat', 'ip': '10.0.0.5', 'firstSeenAt': SEP}])
    assert addr_last_seen(e, '10.0.0.5') == SEP


def test_unknown_address_has_no_recency():
    assert addr_last_seen(hat([]), '10.0.0.1') == ''


def test_sighting_stamps_lastSeenAt_every_time_and_reports_the_change():
    """'Correct it any time it sees an IP + config' — the timestamp moves on
    a repeat sighting, and the caller is told so the file gets written."""
    inv = {}
    assert record_sighting(inv, '1082965', 'hat', '192.168.1.9', OCT) is True
    rows = inv['1082965']['seen']
    assert rows[0]['firstSeenAt'] == OCT and rows[0]['lastSeenAt'] == OCT

    assert record_sighting(inv, '1082965', 'hat', '192.168.1.9', NOW) is True
    assert rows[0]['firstSeenAt'] == OCT, 'firstSeenAt must never move'
    assert rows[0]['lastSeenAt'] == NOW, 'lastSeenAt must move'


def test_an_older_sighting_never_rewinds_the_clock():
    inv = {}
    record_sighting(inv, '1082965', 'hat', '192.168.1.9', NOW)
    assert record_sighting(inv, '1082965', 'hat', '192.168.1.9', OCT) is False
    assert inv['1082965']['seen'][0]['lastSeenAt'] == NOW


def test_a_fresh_sighting_flips_the_winner():
    """The self-correcting property: talk to the board at .9 and .9 wins,
    even though .12 was there first."""
    inv = {}
    record_sighting(inv, '1082965', 'hat', '192.168.1.12', SEP)
    record_sighting(inv, '1082965', 'hat', '192.168.1.9', SEP)   # same instant
    e = inv['1082965']
    record_sighting(inv, '1082965', 'hat', '192.168.1.9', NOW)   # answers today
    ranked = rank_matches([('192.168.1.12', e), ('192.168.1.9', e)])
    assert ranked[0][0] == '192.168.1.9'


def test_an_offsubnet_address_loses_to_one_on_this_subnet(monkeypatch):
    import pixelblaze.cli.cli_utils as U
    monkeypatch.setattr(U, 'get_host_ip', lambda: '192.168.1.67')
    e = hat([
        {'name': 'hat', 'ip': '192.168.4.1', 'firstSeenAt': NOW},   # newer...
        {'name': 'hat', 'ip': '192.168.1.9', 'firstSeenAt': SEP},   # ...but unreachable
    ])
    ranked = U.rank_matches([('192.168.4.1', e), ('192.168.1.9', e)])
    assert ranked[0][0] == '192.168.1.9', 'reachability outranks recency'


def test_the_winning_reason_is_stated():
    e = hat([{'name': 'hat', 'ip': '192.168.1.9', 'firstSeenAt': OCT}])
    assert rank_matches([('192.168.1.9', e)])[0][2]
