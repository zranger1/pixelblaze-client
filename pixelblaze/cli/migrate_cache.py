"""One-shot migration: an IP-keyed `cache.json` to a chipId-keyed pair of files.

The old cache filed a device under whichever address it happened to have, so
one board that had moved was several entries and none of them said which. This
reads whatever is there, files every entry under its `chipId`, and splits the
result: the inventory (who exists, what they are called, every name/address
they have been seen at) into `devices.json`, everything volatile and bulky
into `cache.json`.

`firstSeenAt` for each (name, address) pair is taken from the old entry's
`lastSeenAt` — the only evidence the old format kept, and an upper bound on
the truth. Said plainly here rather than pretended to be exact.

    python -m pixelblaze.cli.migrate_cache            # in place, with a backup
    python -m pixelblaze.cli.migrate_cache --dry-run  # print, write nothing
"""

from __future__ import annotations

import argparse
import datetime
import json
import shutil

from pixelblaze.cli.cli_utils import (
    CACHE_VERSION, chip_of, devices_path, get_cache_dir, record_sighting,
)

# Facts about one board, not about one run: these ride along in the inventory.
_IDENTITY = ('chipId', 'name', 'brandName', 'boardType')


def migrate(dry_run: bool = False) -> tuple[dict, dict]:
    cache_file = get_cache_dir() / 'cache.json'
    old = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    entries = old.get('devices', {})

    inventory: dict = {}
    state: dict = {}
    orphans: list[str] = []

    for ip, entry in entries.items():
        chip = chip_of(entry)
        if not chip:
            # No chipId, no board. Kept in the report rather than dropped
            # silently — an address nothing ever identified is still a thing
            # you may want to know you had.
            orphans.append(ip)
            continue
        when = entry.get('lastSeenAt') or datetime.datetime.now(datetime.timezone.utc).isoformat()
        name = entry.get('name') or ''
        record_sighting(inventory, chip, name, ip, when)
        # Every address it was ever filed under, including the alternates the
        # first pass at de-duplication had already folded in.
        for alt in entry.get('otherIps') or []:
            record_sighting(inventory, chip, name, alt, when)

        st = state.setdefault(chip, {'chipId': chip})
        for k, v in entry.items():
            if k in ('otherIps',):
                continue
            st[k] = v
        st['ip'] = ip

    return (
        {'version': CACHE_VERSION, 'devices': inventory},
        {'version': CACHE_VERSION, 'lastIp': old.get('lastIp'),
         'lastChip': chip_of(entries.get(old.get('lastIp') or '', {})) or None,
         'devices': state},
    ), orphans


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dry-run', action='store_true', help='print the result, write nothing')
    args = ap.parse_args()

    (inventory, state), orphans = migrate()
    cache_file = get_cache_dir() / 'cache.json'

    print(f"{len(inventory['devices'])} board(s) from {len(json.loads(cache_file.read_text()).get('devices', {})) if cache_file.exists() else 0} cache entries")
    for chip, entry in sorted(inventory['devices'].items()):
        rows = entry.get('seen', [])
        print(f"  chip {chip:<12} {entry.get('name', '?'):<18} "
              f"{len(rows)} address(es): {', '.join(r['ip'] for r in rows)}")
    if orphans:
        print(f"  no chipId, not migrated: {', '.join(orphans)}")

    if args.dry_run:
        print("\n--dry-run: nothing written")
        return

    if cache_file.exists():
        backup = cache_file.with_suffix('.json.pre-chipid')
        shutil.copy2(cache_file, backup)
        print(f"\nbacked up {cache_file} -> {backup}")
    devices_file = devices_path()
    devices_file.parent.mkdir(parents=True, exist_ok=True)
    # Through the symlink if there is one: the repo copy is the real file.
    target = devices_file.resolve() if devices_file.is_symlink() else devices_file
    target.write_text(json.dumps(inventory, indent=2, sort_keys=True) + '\n')
    cache_file.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
    print(f"wrote {devices_file} ({len(inventory['devices'])} boards)")
    print(f"wrote {cache_file} (local state)")


if __name__ == '__main__':
    main()
