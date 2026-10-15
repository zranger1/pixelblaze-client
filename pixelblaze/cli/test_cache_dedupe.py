"""The device cache is keyed by BOARD, and split in two.

An address is not an identity. One board is 10.1.1.24 on the router today
and 10.1.9.3 once a fleet is re-formed behind a leader's access point — so
an IP-keyed cache filed one Pixelblaze as three devices, two of them dead, and
`pb find` announced "checking 9 known address(es)" for three boards.

`chipId` is a property of the chip. It is NOT globally unique — these are
~23-bit values, not a 48-bit MAC — so it identifies a fleet's devices, not
every Pixelblaze ever made.

Two files, because one of them is meant to live in version control:

  devices.json   the inventory — who exists, what they are called, and every
                 (name, address) pair each has been seen at, with the first
                 time it was seen. Changes only when something is genuinely
                 new, so a run that learned nothing leaves nothing to commit.
  cache.json     local state — where each board was last seen, the last
                 address addressed, and the bulky `--full` blobs. `lastSeenAt`
                 moves every run and a pattern list is hundreds of ids.
"""

import json

from pixelblaze.cli import cli_utils


def _setup(tmp_path, monkeypatch, inventory=None, state=None, last_ip=None):
    monkeypatch.setattr(cli_utils, 'get_cache_dir', lambda: tmp_path)
    monkeypatch.setattr(cli_utils, 'get_host_ip', lambda: '10.1.1.67')
    monkeypatch.delenv('PB_DEVICES_FILE', raising=False)
    (tmp_path / 'devices.json').write_text(json.dumps(
        {'version': 3, 'devices': inventory or {}}))
    (tmp_path / 'cache.json').write_text(json.dumps(
        {'version': 3, 'lastIp': last_ip, 'devices': state or {}}))


def _inventory(tmp_path):
    return json.loads((tmp_path / 'devices.json').read_text())['devices']


def _state(tmp_path):
    return json.loads((tmp_path / 'cache.json').read_text())['devices']


def _board(chip, name, *sightings):
    return {'chipId': chip, 'name': name,
            'seen': [{'name': n, 'ip': ip, 'firstSeenAt': at} for n, ip, at in sightings]}


def test_one_board_at_three_addresses_is_one_entry(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, inventory={
        '700001': _board('700001', 'aurora',
                          ('aurora', '10.1.1.34', '2026-09-01T00:00:00+00:00'),
                          ('aurora', '10.1.9.3', '2026-09-20T00:00:00+00:00'),
                          ('aurora', '10.1.9.4', '2026-08-01T00:00:00+00:00')),
        '700002': _board('700002', 'cascade',
                          ('cascade', '10.1.1.24', '2026-09-22T00:00:00+00:00')),
    })
    boards = cli_utils.cached_devices()
    assert sorted(b['chipId'] for b in boards) == ['700001', '700002']
    aurora = next(b for b in boards if b['name'] == 'aurora')
    # Every address it has ever had, most recently first — so the one it is
    # at now leads, and an AP-mode address it may go back to is still there.
    assert aurora['ips'] == ['10.1.9.3', '10.1.1.34', '10.1.9.4']
    assert cli_utils.cached_entry('10.1.9.4')['name'] == 'aurora'


def test_first_seen_never_moves(tmp_path, monkeypatch):
    """A device coming back is not a new answer to "when did this first appear".

    The point of the history is that it is history. `lastSeenAt` is what moves,
    and it lives in the other file.
    """
    _setup(tmp_path, monkeypatch, inventory={
        '111': _board('111', 'aurora', ('aurora', '10.1.1.34', '2026-01-01T00:00:00+00:00')),
    })
    cli_utils.update_device_cache([{'ip': '10.1.1.34', 'name': 'aurora', 'chipId': 111}])
    rows = _inventory(tmp_path)['111']['seen']
    assert len(rows) == 1
    assert rows[0]['firstSeenAt'] == '2026-01-01T00:00:00+00:00'
    # …and the sighting went to the volatile file instead.
    assert _state(tmp_path)['111']['lastSeenAt'] > '2026-01-01'


def test_a_move_adds_a_row_and_keeps_the_old_one(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, inventory={
        '111': _board('111', 'aurora', ('aurora', '10.1.1.34', '2026-01-01T00:00:00+00:00')),
    })
    cli_utils.update_device_cache([{'ip': '10.1.9.3', 'name': 'aurora', 'chipId': 111}])
    rows = _inventory(tmp_path)['111']['seen']
    assert [r['ip'] for r in rows] == ['10.1.1.34', '10.1.9.3']
    # One board, two addresses, newest first.
    assert cli_utils.cached_devices()[0]['ips'] == ['10.1.9.3', '10.1.1.34']


def test_a_rename_adds_a_row_and_keeps_the_old_name(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, inventory={
        '111': _board('111', 'lantrn', ('lantrn', '10.1.1.8', '2026-01-01T00:00:00+00:00')),
    })
    cli_utils.update_device_cache([{'ip': '10.1.1.8', 'name': 'lantern', 'chipId': 111}])
    entry = _inventory(tmp_path)['111']
    assert entry['name'] == 'lantern'
    assert [r['name'] for r in entry['seen']] == ['lantrn', 'lantern']


def test_a_run_that_learned_nothing_leaves_the_inventory_alone(tmp_path, monkeypatch):
    """It is a file in a repo. A no-op run must not produce a diff."""
    _setup(tmp_path, monkeypatch, inventory={
        '111': _board('111', 'aurora', ('aurora', '10.1.1.34', '2026-01-01T00:00:00+00:00')),
    })
    before = (tmp_path / 'devices.json').read_text()
    cli_utils.update_device_cache([{'ip': '10.1.1.34', 'name': 'aurora', 'chipId': 111}])
    assert (tmp_path / 'devices.json').read_text() == before


def test_a_device_not_seen_this_run_is_kept(tmp_path, monkeypatch):
    """Nothing is ever dropped for failing to answer.

    A Pixelblaze that is switched off, asleep, or has wedged is still a device
    you own, and its addresses are how you reach it when it comes back.
    """
    _setup(tmp_path, monkeypatch, inventory={
        '111': _board('111', 'aurora', ('aurora', '10.1.1.34', '2026-01-01T00:00:00+00:00')),
        '222': _board('222', 'beacon', ('beacon', '10.1.9.1', '2026-01-01T00:00:00+00:00')),
    })
    cli_utils.update_device_cache([{'ip': '127.0.0.1', 'name': 'PB Emulator', 'chipId': 999}])
    assert sorted(_inventory(tmp_path)) == ['111', '222', '999']
    assert cli_utils.cached_names()['10.1.9.1'] == 'beacon'


def test_an_address_that_changed_hands_belongs_to_whoever_has_it_now(tmp_path, monkeypatch):
    """DHCP hands addresses round, and the newer sighting wins.

    THIS WENT WRONG ONCE: `cascade` remembered `10.1.9.1` from an
    earlier AP-mode session, `beacon` lives there now, and a lookup returned
    cascade — which then got written back as beacon's name.
    """
    _setup(tmp_path, monkeypatch, inventory={
        '700002': _board('700002', 'cascade',
                          ('cascade', '10.1.9.1', '2026-01-01T00:00:00+00:00')),
        '700003': _board('700003', 'beacon',
                          ('beacon', '10.1.9.1', '2026-09-19T00:00:00+00:00')),
    })
    assert cli_utils.cached_names()['10.1.9.1'] == 'beacon'
    assert cli_utils.cached_entry('10.1.9.1')['chipId'] == '700003'


def test_an_address_with_no_chipId_files_no_device(tmp_path, monkeypatch):
    """A probe that never learned who answered is an address, not a device.

    Filing it would create a board with no identity that can never be merged
    with the real one when it finally introduces itself.
    """
    _setup(tmp_path, monkeypatch)
    cli_utils.update_device_cache([{'ip': '10.1.1.9', 'via': 'cache', 'http': True}])
    assert _inventory(tmp_path) == {}
    assert _state(tmp_path) == {}


def test_a_fast_find_can_say_who_answered(tmp_path, monkeypatch):
    """`pb find` never connects in fast mode, so the name comes from disk.

    Free, and the whole reason anyone reads the output. An address nothing has
    ever been seen at stays anonymous rather than borrowing a name.
    """
    _setup(tmp_path, monkeypatch, inventory={
        '111': _board('111', 'aurora',
                      ('aurora', '10.1.1.34', '2026-01-01T00:00:00+00:00'),
                      ('aurora', '10.1.9.3', '2026-09-20T00:00:00+00:00')),
    })
    names = cli_utils.cached_names()
    assert names['10.1.1.34'] == 'aurora'
    assert names['10.1.9.3'] == 'aurora'
    assert '10.1.1.8' not in names


def test_every_address_is_still_probed(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, inventory={
        '111': _board('111', 'aurora',
                      ('aurora', '10.1.1.34', '2026-01-01T00:00:00+00:00'),
                      ('aurora', '10.1.9.3', '2026-09-20T00:00:00+00:00')),
    })
    assert set(cli_utils.cached_addresses()) == {'10.1.1.34', '10.1.9.3'}
    assert cli_utils.cached_addresses()[0] == '10.1.9.3'


def test_the_inventory_can_live_somewhere_else(tmp_path, monkeypatch):
    """`PB_DEVICES_FILE` — and, in practice, a symlink into a repo."""
    _setup(tmp_path, monkeypatch)
    elsewhere = tmp_path / 'repo' / 'fleet' / 'pixelblazes.json'
    monkeypatch.setenv('PB_DEVICES_FILE', str(elsewhere))
    cli_utils.update_device_cache([{'ip': '10.1.1.34', 'name': 'aurora', 'chipId': 111}])
    assert json.loads(elsewhere.read_text())['devices']['111']['name'] == 'aurora'
    # …and not in the default location.
    assert _inventory(tmp_path) == {}


def test_a_symlinked_inventory_is_written_through(tmp_path, monkeypatch):
    """The repo copy is the real file; the write must not replace the link."""
    _setup(tmp_path, monkeypatch)
    real = tmp_path / 'repo-pixelblazes.json'
    real.write_text(json.dumps({'version': 3, 'devices': {}}))
    link = tmp_path / 'devices.json'
    link.unlink()
    link.symlink_to(real)

    cli_utils.update_device_cache([{'ip': '10.1.1.34', 'name': 'aurora', 'chipId': 111}])
    assert link.is_symlink(), 'the symlink was replaced by a regular file'
    assert json.loads(real.read_text())['devices']['111']['name'] == 'aurora'
