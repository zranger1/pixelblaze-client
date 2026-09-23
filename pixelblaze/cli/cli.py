#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Command-line interface for Pixelblaze LED controllers.

This module provides a modern CLI tool for controlling Pixelblazes with
flexible discovery, pattern rendering, and configuration management.
"""

# ----------------------------------------------------------------------------
#
#    ██████╗██╗     ██╗
#   ██╔════╝██║     ██║
#   ██║     ██║     ██║
#   ██║     ██║     ██║
#   ╚██████╗███████╗██║
#    ╚═════╝╚══════╝╚═╝
#   ╔═╗┌─┐┌┬┐┌┬┐┌─┐┌┐┌┌┬┐  ╦  ┬┌┐┌┌─┐  ╦┌┐┌┌┬┐┌─┐┬─┐┌─┐┌─┐┌─┐┌─┐
#   ║  │ │││││││├─┤│││ ││  ║  ││││├┤   ║│││ │ ├┤ ├┬┘├┤ ├─┤│  ├┤ 
#   ╚═╝└─┘┴ ┴┴ ┴┴ ┴┘└┘─┴┘  ╚═╝┴┘└┘└─┘  ╩┘└┘ ┴ └─┘┴└─└  ┴ ┴└─┘└─┘
#

import json as jsonlib
import time
import re
import click
import pathlib
from pixelblaze.pixelblaze import Pixelblaze, PBB
from pixelblaze.cli.cli_utils import cli, log, no_save_option, input_arg, read_input, parse_json, jsons, \
                                     get_cache_dir, check, parse_vars, get_pixelblaze, discover_pixelblaze, \
                                     enumerate_pixelblazes, cache_ip, _read_cache, _write_cache, \
                                     _fetch_device_config, update_device_cache, lookup_cached_device
from pixelblaze.cli.top import register as _register_top

@click.group()
@click.option(
    '--ip',
    default='auto',
    help='IP address of Pixelblaze (default: auto discover mode, checks 192.168.4.1 first for Ad Hoc, then network scan)',
    show_default=True
)
@click.option(
    '--timeout',
    type=float,
    default=5.0,
    help='Command timeout in seconds (default: 5.0)',
    show_default=True
)
@click.option(
    '--retries',
    type=int,
    default=3,
    help='Number of retries on connection errors (default: 3)',
    show_default=True
)
@click.pass_context
def pixelblaze(ctx, ip, timeout, retries):
    """
    Pixelblaze LED Controller CLI

    Control Pixelblaze devices from the command line.
    """
    ctx.ensure_object(dict)
    ctx.obj['ip'] = ip
    ctx.obj['timeout'] = timeout
    ctx.obj['retries'] = retries


@pixelblaze.command()
@click.option('--name', '-n', 'name_filter', default=None,
              help='Filter by device name (case-insensitive substring match, implies --full)')
@click.option('--ip', '-i', 'ip_filter', default=None,
              help='Filter by IP address (substring match)')
@click.option('--timeout', '-t', 'scan_timeout', type=int, default=3000,
              help='Beacon listen timeout in milliseconds (default: 3000)',
              show_default=True)
@click.option('--full', '--slow', '-s', '-f', 'slow', is_flag=True,
              help='Connect to each device to fetch name, version, config (parallel)')
@click.option('--no-cache', is_flag=True, help='Do not cache the selected IP')
@click.option('--passive', is_flag=True,
              help='Only listen for beacons; do not broadcast a probe beacon. '
                   'Sync-group followers never beacon, so they are then found only '
                   'if cached or listed by a peer.')
@click.pass_context
def find(ctx, name_filter, ip_filter, scan_timeout, slow, no_cache, passive):
    """
    Discover and enumerate all Pixelblazes on the network.

    Every source is tried at once, so a sweep takes as long as the beacon
    listen and no longer: UDP beacons; one probe beacon of our own, which
    every Pixelblaze answers (including sync-group followers, which never
    beacon themselves); a connect on ports 80/81 to the ad-hoc address and
    every cached address; and each found device's sync-group peer list.
    Nothing is sent over TCP by the probes, so they are safe against a
    device in any state.

    By default runs fast: returns each IP with how it was found (`via`)
    and, when probed, whether ports 80 (`http`) and 81 (`ws`) answered.
    Use --full/--slow to also connect to each device (in parallel) and fetch
    names, version, pixel count, etc. Using --name implies --full.

    Prints JSONL (one JSON object per line) to stdout. Discovery progress
    is logged to stderr, including why nothing beaconed when that happens.

    The first matching device (after any filters) is cached as the default
    IP for subsequent commands.

    \b
    Examples:
        pb find                          # Fast: IPs, how found, ports
        pb find --full                   # Connect to each, get full info (--slow is an alias)
        pb find --name living            # Filter by name (implies --full)
        pb find --ip 192.168.1           # Filter by IP substring (fast)
        pb find --name tree --ip 10.     # Combine filters
        pb find --timeout 5000           # Scan longer for slow networks
        pb find --passive                # Listen only, no probe broadcast
        pb find --no-cache               # Don't update cached IP
        pb find 2>/dev/null              # Quiet mode (stdout JSONL only)
    """
    # --name requires device info, so imply --full
    if name_filter:
        slow = True

    devices = enumerate_pixelblazes(timeout=scan_timeout, slow=slow, probe=not passive)

    if not devices:
        raise click.ClickException(
            "No Pixelblazes found: nothing beaconed, nothing answered the probe, and no "
            "known address accepted a connection on port 80 or 81."
        )

    # Apply filters
    matched = []
    for dev in devices:
        if name_filter and name_filter.lower() not in dev.get('name', '').lower():
            continue
        if ip_filter and ip_filter not in dev.get('ip', ''):
            continue
        matched.append(dev)

    log(f"\nFound {len(devices)} device(s), {len(matched)} matched filters.")

    if not matched:
        filters = []
        if name_filter:
            filters.append(f"--name '{name_filter}'")
        if ip_filter:
            filters.append(f"--ip '{ip_filter}'")
        raise click.ClickException(
            f"No devices matched filters: {' '.join(filters)}. "
            f"Found {len(devices)} device(s) total."
        )

    # Print all matched devices as JSONL to stdout
    for dev in matched:
        click.echo(jsonlib.dumps(dev, separators=(',', ':')))

    # Cache the best match as the default IP: a device that announced itself
    # or answers on both ports beats a partial answer, and a LAN device beats
    # the emulator on loopback. Ties keep the order in which they answered.
    def _preference(dev):
        via, http, ws = dev.get('via'), dev.get('http'), dev.get('ws')
        announced = via in ('beacon', 'timeSync')
        whole = (http and ws) or announced
        return (0 if whole else 1, 1 if dev['ip'].startswith('127.') else 0)

    selected = min(matched, key=_preference)
    if not no_cache:
        cache_ip(selected['ip'])
        log(f"Cached IP: {selected['ip']}" + (f" ({selected['name']})" if selected.get('name') else ""))
    else:
        log(f"Selected (not cached): {selected['ip']}" + (f" ({selected['name']})" if selected.get('name') else ""))


@cli(pixelblaze)
@click.argument('count', type=int, required=False)
@no_save_option
def pixels(pb: Pixelblaze, count, no_save):
    """
    Get or set the number of pixels configured on the Pixelblaze.

    \b
    Examples:
        pb pixels              # Get current pixel count
        pb pixels 300          # Set pixel count to 300 (saved to flash)
        pb pixels 300 --no-save   # Set pixel count to 300 (temporary only)
    """
    if count is None:
        current_count = pb.getPixelCount()
        click.echo(f"{current_count}")
    else:
        current_count = pb.getPixelCount()
        if count < current_count:
            # Blank orphaned LEDs by toggling brightness off around the change
            log(f"Reducing pixel count ({current_count} → {count})...")
            prev_brightness = pb.getBrightnessSlider()
            pb.setBrightnessSlider(0.0)
            time.sleep(0.1)
            pb.setPixelCount(count, saveToFlash=not no_save)
            time.sleep(0.1)
            pb.setBrightnessSlider(prev_brightness)
        else:
            pb.setPixelCount(count, saveToFlash=not no_save)
        action = "set" if no_save else "saved"
        log(f"Pixel count {action} to {count}")


@cli(pixelblaze)
@click.argument('brightness', type=float, default=1.0, required=False)
@click.option(
    '--play-sequencer',
    is_flag=True,
    help='Also start/resume the pattern sequencer'
)
@no_save_option
def on(pb: Pixelblaze, brightness, play_sequencer, no_save):
    """
    Turn on the Pixelblaze by setting brightness.

    This command sets the brightness to the specified level (default: 1.0).
    Optionally, you can also start/resume the sequencer.

    \b
    Examples:
        pb on                       # Set brightness to 1.0 (full, saved to flash)
        pb on 0.5                   # Set brightness to 50% (saved to flash)
        pb on --play-sequencer      # Set brightness to 1.0 and start sequencer (saved)
        pb on 0.8 --no-save         # Set brightness to 80% (temporary only)
    """
    check(0.0 <= brightness <= 1.0, "Brightness must be between 0.0 and 1.0")

    log(f"Setting brightness to {brightness}...")
    pb.setBrightnessSlider(brightness, saveToFlash=not no_save)

    if play_sequencer:
        log("Starting sequencer...")
        pb.playSequencer(saveToFlash=not no_save)

    action = "turned on" if no_save else "saved and turned on"
    log(f"Pixelblaze {action} (brightness: {brightness})")


@cli(pixelblaze)
@click.option(
    '--pause-sequencer',
    is_flag=True,
    help='Also pause the pattern sequencer'
)
@no_save_option
def off(pb: Pixelblaze, pause_sequencer, no_save):
    """
    Turn off the Pixelblaze by setting brightness to zero.

    This command sets the brightness to 0, effectively turning off all LEDs.
    Optionally, you can also pause the sequencer to stop pattern changes.

    \b
    Examples:
        pb off                      # Set brightness to 0 (saved to flash)
        pb off --pause-sequencer    # Set brightness to 0 and pause sequencer (saved)
        pb off --no-save            # Set brightness to 0 (temporary only)
    """
    log("Setting brightness to 0...")
    pb.setBrightnessSlider(0.0, saveToFlash=not no_save)

    if pause_sequencer:
        log("Pausing sequencer...")
        pb.pauseSequencer(saveToFlash=not no_save)

    action = "turned off" if no_save else "saved and turned off"
    log(f"Pixelblaze {action}")


@cli(pixelblaze)
@input_arg
@click.option('--csv', is_flag=True, help='Output as csv instead of Pixelblaze 3-arrays')
@click.option('--clear', is_flag=True, help='Clear/remove the current pixel map from the device')
def map(pb: Pixelblaze, input, csv, clear):
    """
    Get, set, or clear the pixel map function.

    INPUT is an optional JavaScript file path or inline code. Can also be
    piped via stdin. If no input is provided, the current map function
    is displayed.

    \b
    Examples:
        pb map                       # Get current map coordinates (normalized 0-1)
        pb map map.js                # Set map from file
        pb map < map.js              # Set map from stdin
        pb map --clear               # Remove the current pixel map
    """
    check(not (clear and csv), "Cannot use --clear and --csv together")

    if clear:
        log("Clearing pixel map...")
        pb.deleteFile('/pixelmap.txt')
        pb.deleteFile('/pixelmap.dat')
        log("Pixel map cleared")
        return

    content, _ = read_input(input, "map", required=False)
    setting = content is not None

    if setting:
        if "function" in content:
            log(f"Setting map function...")
            pb.setMapFunction(content)
        else:
            # Also supporting numbers as strings
            log(f"Setting map coordinates...")
            pb.setMapCoordinates(parse_json(jsonlib.dumps(parse_json(content)).replace('"', "")))
    elif csv:
        log(f"Fetching map coordinates as CSV...")
        coords = pb.getMapCoordinates()
        click.echo("index,x,y,z")
        for i in range(0, len(coords[0])):
            click.echo(f"{i},{coords[0][i]},{coords[1][i]},{coords[2][i]}")
    else:
        log(f"Fetching map config...")
        jsons({'coordinates': pb.getMapCoordinates(), 'fn': pb.getMapFunction()})


@pixelblaze.group()
def playlist():
    """
    Playlist and sequencer control commands.

    Control the Pixelblaze pattern sequencer, including play/pause,
    navigation, and playlist management.
    """
    pass


@cli(playlist)
@no_save_option
def pause(pb: Pixelblaze, no_save):
    """
    Pause the pattern sequencer.

    \b
    Examples:
        pb playlist pause           # Pause sequencer (saved to flash)
        pb playlist pause --no-save    # Pause (temporary only)
    """
    log("Pausing sequencer...")
    pb.pauseSequencer(saveToFlash=not no_save)
    action = "paused" if no_save else "paused and saved"
    log(f"Sequencer {action}")


@cli(playlist)
@no_save_option
def play(pb: Pixelblaze, no_save):
    """
    Start/resume the pattern sequencer.

    \b
    Examples:
        pb playlist play           # Start/resume sequencer (saved to flash)
        pb playlist play --no-save    # Start (temporary only)
    """
    log("Starting sequencer...")
    pb.playSequencer(saveToFlash=not no_save)
    action = "started" if no_save else "started and saved"
    log(f"Sequencer {action}")


@cli(playlist)
@no_save_option
def next(pb: Pixelblaze, no_save):
    """
    Advance to the next pattern in the sequence.

    Works with ShuffleAll or Playlist sequencer modes.

    \b
    Examples:
        pb playlist next           # Next pattern (saved to flash)
        pb playlist next --no-save    # Next pattern (temporary only)
    """
    log("Advancing to next pattern...")
    pb.nextSequencer(saveToFlash=not no_save)
    action = "Advanced to next pattern" if no_save else "Advanced to next pattern and saved"
    log(action)


@cli(playlist)
def rand(pb: Pixelblaze):
    """
    Jump to a random pattern.

    Selects a random pattern from all available patterns on the Pixelblaze.

    \b
    Examples:
        pb playlist rand    # Jump to random pattern
    """
    import random as rand

    log("Getting pattern list...")
    patterns = pb.getPatternList()

    check(patterns, "No patterns found on Pixelblaze")

    pattern_id = rand.choice(list(patterns.keys()))
    pattern_name = patterns[pattern_id]

    log(f"Selecting random pattern: {pattern_name}")
    pb.setActivePattern(pattern_id)
    log(f"Now playing: {pattern_name}")


@cli(playlist, name='len')
@click.argument('seconds', type=float)
@no_save_option
def set_duration(pb: Pixelblaze, seconds, no_save):
    """
    Set the duration for all patterns in the sequencer playlist.

    SECONDS is the duration in seconds for each pattern.

    Updates the sequencer playlist to change pattern durations.

    \b
    Examples:
        pb playlist len 10          # Set all durations to 10 seconds (saved)
        pb playlist len 30 --no-save   # Set to 30 seconds (temporary only)
    """
    check(seconds > 0, "Duration must be greater than 0")

    milliseconds = int(seconds * 1000)

    log("Getting current playlist...")
    playlist = pb.getSequencerPlaylist()

    items = playlist.get['playlist']['items']
    check(items, "Playlist is empty")

    original_count = len(items)
    for item in items:
        item['ms'] = milliseconds

    log(f"Setting {original_count} pattern(s) to {seconds} seconds each...")
    pb.setSequencerPlaylist(playlist)

    if not no_save:
        log("Saving playlist to flash...")

    action = "set" if no_save else "saved"
    log(f"Playlist updated and {action}: all patterns set to {seconds}s")


@cli(playlist, name='set')
@click.argument('terms', type=str)
@click.option('--duration', '-d', type=float, default=30.0,
              show_default=True, help='Seconds per pattern')
@click.option('--shuffle', is_flag=True,
              help='Shuffle the resolved order before writing the playlist')
@no_save_option
def playlist_set(pb: Pixelblaze, terms, duration, shuffle, no_save):
    """
    Build a playlist from a CSV of pattern-name searches and/or .js file paths, then play it.

    For each comma-separated term:
      1. case-insensitive substring match against stored pattern names, or
      2. treated as a local .js file path — uploaded to the device, then used.

    Unresolved terms are logged and skipped (best-effort — never fails the whole run).
    Quote the whole arg if any term contains spaces or shell-special characters.

    \b
    Examples:
        pb playlist set 'sparkle,rainbow,wave'
        pb playlist set 'src/patterns/tools/colorOrder.js,sparkle' -d 10
        pb playlist set 'foo,bar,baz' --no-save
    """
    check(terms.strip(), "Provide a comma-separated list of names or .js file paths")
    check(duration > 0, "Duration must be greater than 0")

    parts = [t.strip() for t in terms.split(',') if t.strip()]
    check(parts, "No terms provided")

    log("Fetching pattern list...")
    patterns = dict(pb.getPatternList())  # {id: name}; local copy so we can extend it

    resolved = []  # [(patternId, displayName), ...]

    for term in parts:
        t_lower = term.lower()
        matches = [(pid, name) for pid, name in patterns.items()
                   if t_lower in name.lower()]
        if matches:
            pid, name = matches[0]
            resolved.append((pid, name))
            extra = ''
            if len(matches) > 1:
                others = ', '.join(n for _, n in matches[1:4])
                more = '...' if len(matches) > 4 else ''
                extra = f"  [+{len(matches) - 1} more: {others}{more}]"
            log(f"  ✓ '{term}' → {name}{extra}")
            continue

        path = pathlib.Path(term)
        if path.is_file() and path.suffix.lower() == '.js':
            try:
                code = path.read_text()
                if 'export' not in code:
                    code = 'export function render(index) { ' + code + ' ; }'
                pattern_name = path.stem
                existing_pid = next(
                    (pid for pid, name in patterns.items()
                     if name.lower() == pattern_name.lower()),
                    None
                )
                img_path = pathlib.Path(__file__).parent / '../../site/images/preview_placeholder.jpg'
                preview = img_path.read_bytes()
                verb = 'updating' if existing_pid else 'uploading'
                log(f"  ↑ '{term}' → {verb} '{pattern_name}'")
                pid = pb.savePattern(
                    previewImage=preview,
                    sourceCode=code,
                    name=pattern_name,
                    id=existing_pid,
                    allowCache=True,
                )
                resolved.append((pid, pattern_name))
                patterns[pid] = pattern_name  # so later terms can name-match this
                continue
            except Exception as e:
                log(f"  ✗ '{term}' → file upload failed: {e}; skipping")
                continue

        log(f"  ✗ '{term}' → no name match and not a .js file; skipping")

    check(resolved, "No terms resolved to a pattern; playlist unchanged")

    if shuffle:
        import random as rand
        rand.shuffle(resolved)
        log(f"Shuffled order: {', '.join(name for _, name in resolved)}")

    ms_per = int(duration * 1000)
    log("Building playlist...")
    playlist = pb.getSequencerPlaylist()
    playlist['playlist']['items'] = [{"id": pid, "ms": ms_per} for pid, _ in resolved]

    log(f"Setting playlist ({len(resolved)} pattern{'s' if len(resolved) != 1 else ''}, "
        f"{duration}s each)...")
    pb.setSequencerPlaylist(playlist, saveToFlash=not no_save)

    log("Switching to Playlist mode and starting...")
    pb.setSequencerMode(Pixelblaze.sequencerModes.Playlist, saveToFlash=not no_save)
    pb.playSequencer(saveToFlash=not no_save)

    action = "set (temporary)" if no_save else "saved"
    log(f"Playlist {action}. Playing: {resolved[0][1]}")


@cli(pixelblaze)
@click.argument('input', type=str, required=False)
@click.argument('name', type=str, required=False)
@click.option(
    '--write',
    '-w',
    is_flag=True,
    help='Save pattern to Pixelblaze (uses NAME argument or filename stem)'
)
@click.option(
    '--rm',
    is_flag=True,
    help='Remove/delete the pattern from Pixelblaze'
)
@click.option(
    '--img',
    type=click.Path(exists=True),
    help='Path to preview image (100x150 JPEG) for --write. If omitted, generates SMPTE placeholder'
)
@click.option(
    '--var',
    'var_args',
    multiple=True,
    help='Variables/controls in flexible format: key value, key:value, or \'{json5}\''
)
@no_save_option
@click.option(
    '--exact',
    is_flag=True,
    help='Require exact match for pattern name lookup'
)
@click.option(
    '--lookup',
    is_flag=True,
    help='Force lookup of pattern name/ID instead of treating input as code'
)
@click.option(
    '--cat',
    is_flag=True,
    help='Print the source code of an existing pattern'
)
def pattern(pb: Pixelblaze, input, name, write, rm, img, var_args, no_save, exact, lookup, cat):
    """
    Unified pattern command: switch to, render, or save patterns.

    INPUT can be a pattern name, file path, or inline JavaScript code.
    INPUT can also be read from stdin if not provided.
    NAME (optional) is the target pattern name or ID for --write operations.

    \b
    **Without --write or --rm (render/switch mode):**
    - If INPUT is a file path → render pattern from file
    - If INPUT contains code-like syntax (operators, function calls, etc.) → render as JavaScript code
    - If INPUT is a valid pattern ID → switch to that pattern
    - If INPUT matches a pattern name → switch to that pattern
    - Otherwise → render INPUT as inline JavaScript code
    - Use --lookup to force pattern name/ID lookup and skip code detection

    \b
    **With --write (save mode):**
    - Saves the pattern to Pixelblaze filesystem
    - Uses NAME if provided, otherwise derives name from filename
    - If NAME matches an existing ID, that pattern is overwritten

    \b
    **With --cat (print source mode):**
    - Prints the source code of an existing pattern
    - INPUT should be a pattern name or ID

    \b
    Examples:
        # Switch/Render
        pb pattern rainbow
        pb pattern code.js
        pb pattern abcd123456789012
        pb pattern 'true && hsv(1,1,1) || hsv(0,0,0)'  # Renders as code
        pb pattern 'hsv' --lookup                      # Force lookup (rather than code)

    \b
        # Read from stdin
        echo 'render code here' | pb pattern
        cat code.js | pb pattern --write "My Pattern"

    \b
        # Remove
        pb pattern foo --rm

    \b
        # Print source code
        pb pattern rainbow --cat
        pb pattern abc123456789012 --cat

    \b
        # Save (Write)
        pb pattern code.js --write              # Save as "code"
        pb pattern code.js --write "New Name"   # Save as "New Name"
        pb pattern "hsv(0,1,1)" --write "Solid" # inline, requires name
        pb pattern code.js --write abcd123456789012 # Overwrite existing
    """
    # Check for conflicting flags
    check(not (write and rm), "Cannot use --write and --rm together")
    check(not (write and cat), "Cannot use --write and --cat together")
    check(not (rm and cat), "Cannot use --rm and --cat together")
    check(not (rm and name), "Cannot use extra argument with --rm")
    check(not (cat and name), "Cannot use NAME argument with --cat")

    # Handle --cat mode early
    if cat:
        # --cat requires an INPUT (pattern name or ID)
        check(input is not None, "Pattern name or ID required for --cat")
        _handle_cat_mode(pb, input, exact)
        return

    # In write mode, handle stdin + name argument case
    # When piping: cat file | pb pattern --write name
    # Click parses 'name' as 'input' arg, so swap them if needed
    if write and input is not None and name is None:
        # If input doesn't look like code and isn't a file, it's probably the target name
        if not pathlib.Path(input).is_file() and not _looks_like_code(input):
            name = input
            input = None

    # Read from stdin if input not provided
    input_from_stdin = False
    if input is None:
        input, input_from_stdin = read_input(None, name="pattern", required=True)

    # Parse variables
    variables = parse_vars(var_args) if var_args else {}

    if rm:
        # ===== REMOVE MODE =====
        check(not variables, "Cannot use --var with --rm")
        check(img is None, "Cannot use --img with --rm")
        _handle_remove_mode(pb, input, exact)

    elif write:
        # ===== WRITE MODE =====
        # Map the new 'name' arg to the internal 'write_target' logic
        # If name is None, pass '' so logic knows to use filename stem
        target = name if name else ''
        _handle_write_mode(pb, input, target, img, variables, no_save, input_from_stdin)

    else:
        # ===== RENDER/SWITCH MODE =====
        # If user provided a name but didn't say --write, we could warn,
        # but for now let's just ignore it or assume they meant to write?
        # Ideally, we strictly check:
        if name:
             log(f"Warning: Name argument '{name}' ignored because --write was not specified.")

        _handle_render_or_switch_mode(pb, input, variables, no_save, exact, lookup, from_stdin=input_from_stdin)


def _looks_like_code(s: str) -> bool:
    """
    Detect if a string looks like JavaScript code rather than a pattern name.

    Returns True if the string contains code-like patterns:
    - Operators: &&, ||, +, -, *, /, %, ===, !==, ==, !=, <, >, <=, >=
    - Function calls: word(
    - Brackets: {, }, [, ], ;
    - Comparisons and assignments: =, ?:
    """
    # Check for common code operators and patterns
    code_indicators = [
        '&&', '||',  # Logical operators
        '++', '--',  # Increment/decrement
        '===', '!==', '==', '!=',  # Comparisons
        '<=', '>=', '=>',  # Comparisons and arrow functions
        '{', '}', '[', ']', ';',  # Brackets and statements
        '?', ':',  # Ternary operator
    ]

    # Check for obvious code patterns
    for indicator in code_indicators:
        if indicator in s:
            return True

    # Check for function calls (word followed by open paren)
    if re.search(r'\w+\s*\(', s):
        return True

    # Check for math operators only if not at start (could be negative number)
    if re.search(r'[\d\s]\s*[\+\-\*/%]\s*[\d\s]', s):
        return True

    return False


def _find_pattern(pb: Pixelblaze, search: str, exact: bool = False):
    """Find a pattern by name or ID.

    Returns:
        tuple: (pattern_id, pattern_name) or (None, None) if not found
    """
    results = _find_patterns(pb, search, exact)
    return results[0] if results else (None, None)


def _find_patterns(pb: Pixelblaze, search: str, exact: bool = False):
    """Find all patterns matching a name or ID.

    Returns:
        list[tuple]: List of (pattern_id, pattern_name) tuples
    """
    log("Fetching pattern list...")
    patterns = pb.getPatternList()

    # Try by ID first
    if Pixelblaze.isPatternId(search):
        pattern_name = patterns.get(search)
        return [(search, pattern_name)] if pattern_name else []

    # Search by name
    if not patterns:
        return []

    pattern_regex = re.compile(search, re.IGNORECASE)
    results = []

    for pattern_id, pattern_name in patterns.items():
        if exact:
            if pattern_name.lower() == search.lower():
                results.append((pattern_id, pattern_name))
        else:
            if pattern_regex.search(pattern_name):
                results.append((pattern_id, pattern_name))

    return results


def _handle_cat_mode(pb: Pixelblaze, input, exact):
    """Handle --cat mode: print pattern source code."""
    pattern_id, pattern_name = _find_pattern(pb, input, exact)
    check(pattern_id, f"Pattern '{input}' not found on Pixelblaze")

    log(f"Fetching source code for '{pattern_name}' (ID: {pattern_id})...")
    source_code = pb.getPatternSourceCode(pattern_id)
    check(source_code, f"Failed to retrieve source code for pattern '{pattern_name}'")

    # Parse the JSON to extract the actual source
    try:
        source_obj = jsonlib.loads(source_code)
        actual_source = source_obj.get('main', source_code)
    except:
        actual_source = source_code

    click.echo(actual_source)


def _handle_remove_mode(pb: Pixelblaze, input, exact):
    """Handle --rm mode: remove pattern from Pixelblaze."""
    check(not pathlib.Path(input).is_file(), "Cannot use --rm with a file path. Specify pattern name or ID.")

    pattern_id, pattern_name = _find_pattern(pb, input, exact)
    check(pattern_id, f"Pattern '{input}' not found on Pixelblaze")

    log(f"Deleting pattern '{pattern_name}' (ID: {pattern_id})...")
    pb.deletePattern(pattern_id)
    log(f"Pattern '{pattern_name}' deleted successfully!")


def _handle_write_mode(pb: Pixelblaze, input, write_target, img, variables, no_save, from_stdin=False):
    """Handle --write mode: save pattern to Pixelblaze."""
    # If input came from stdin, it's already the code content; otherwise check if it's a file
    is_file = not from_stdin and pathlib.Path(input).is_file()
    code, _ = read_input(input, "code") if is_file else (input, False)

    # Determine pattern name/ID
    if write_target == '':
        check(is_file, "Pattern name required when not reading from file. Use: --write NAME")
        pattern_name = pathlib.Path(input).stem
        pattern_id = None
    elif Pixelblaze.isPatternId(write_target):
        pattern_id, pattern_name = _find_pattern(pb, write_target)
        check(pattern_name, f"Pattern ID {write_target} not found")
    else:
        pattern_name = write_target
        # Look up existing pattern by name to overwrite instead of creating a dupe
        pattern_id, _ = _find_pattern(pb, write_target, exact=True)

    if "export" not in code:
        code = 'export function render(index) { ' + code + ' ; }'

    img = img or pathlib.Path(__file__).parent / '../../site/images/preview_placeholder.jpg'
    log(f"Loading preview image from {img}...")
    with open(img, 'rb') as f:
        preview_image = f.read()

    is_update = pattern_id is not None
    log(f"{'Updating' if is_update else 'Creating'} pattern '{pattern_name}'"
        f"{f' (ID: {pattern_id})' if is_update else ''}...")
    pattern_id = pb.savePattern(
        previewImage=preview_image,
        sourceCode=code,
        name=pattern_name,
        id=pattern_id,
        allowCache=True
    )

    log(f"Pattern '{pattern_name}' (ID: {pattern_id}) {'updated' if is_update else 'created'} successfully!")
    _set_vars_and_controls(pb, variables, not no_save)
    jsons({'id': pattern_id})


def _handle_render_or_switch_mode(pb: Pixelblaze, input, variables, no_save, exact, lookup=False, from_stdin=False):
    """Handle render or switch mode based on input type."""
    # Only check if it's a file if it didn't come from stdin
    if not from_stdin and pathlib.Path(input).is_file():
        code, _ = read_input(input, "code")
        _render_pattern(pb, code, variables)
        return

    # Determine if input looks like code or a pattern lookup
    input_looks_like_code = _looks_like_code(input)

    # If input looks like code and --lookup is not set, treat as inline code
    if input_looks_like_code and not lookup:
        _render_pattern(pb, input, variables)
        return

    # Try to find as existing pattern (by ID or name)
    pattern_id, pattern_name = _find_pattern(pb, input, exact)

    if pattern_id:
        # Switch to existing pattern
        log(f"Switching to pattern: {pattern_name}")
        pb.setActivePattern(pattern_id, saveToFlash=not no_save)

        action = "activated" if no_save else "activated and saved"
        log(f"Pattern '{pattern_name}' {action}")
        _set_vars_and_controls(pb, variables, not no_save)
    else:
        # Not found as pattern, treat as inline code (unless --lookup was specified)
        if lookup:
            check(False, f"Pattern '{input}' not found on Pixelblaze (use without --lookup to treat as code)")
        _render_pattern(pb, input, variables)


def _render_pattern(pb: Pixelblaze, code, variables):
    """Compile and render a pattern to the Pixelblaze."""
    if "export" not in code:
        code = 'export function render(index) { ' + code + ' ; }'

    log("Compiling pattern...")
    bytecode = pb.compilePattern(code, allow_cache=True)

    log("Sending to renderer...")
    pb.sendPatternToRenderer(bytecode)
    _set_vars_and_controls(pb, variables)

    log("Pattern rendered successfully")


def _set_vars_and_controls(pb: Pixelblaze, variables, save=False):
    """Set variables and/or controls on the active pattern."""
    if not variables:
        return

    log(f"Setting variables/controls: {variables}")
    pb.setActiveControls(variables, saveToFlash=save)
    pb.setActiveVariables(variables)


@cli(pixelblaze)
@click.option('--name', 'device_name', default=None, help='Set device name')
@click.option('--pixels', type=int, default=None, help='Set pixel count')
@click.option('--brightness', type=float, default=None, help='Set brightness (0.0-1.0)')
@click.option('--max-brightness', type=int, default=None, help='Set brightness limit (0-100%%)')
@click.option('--led-type',
              type=click.Choice(['WS2812', 'APA102', 'SK9822', 'WS2801', 'OutputExpander', 'off'],
                                case_sensitive=False),
              default=None, help='Set LED type')
@click.option('--color-order',
              type=click.Choice(['RGB', 'RBG', 'BRG', 'BGR', 'GRB', 'GBR',
                                 'RGBW', 'GRBW', 'RGB-W', 'GRB-W'],
                                case_sensitive=False),
              default=None, help='Set color order')
@click.option('--data-speed', type=int, default=None, help='Set LED data speed (Hz, advanced)')
@click.option('--cpu',
              type=click.Choice(['low', 'medium', 'high'], case_sensitive=False),
              default=None, help='Set CPU speed (80/160/240 MHz, requires reboot)')
@click.option('--discovery/--no-discovery', default=None,
              help='Enable/disable Electromage discovery service')
@click.option('--timezone', 'tz', default=None, help='Set timezone (Unix tz string, e.g. "America/New_York")')
@click.option('--auto-off/--no-auto-off', 'auto_off_enable', default=None,
              help='Enable/disable auto-off scheduler')
@click.option('--auto-off-start', default=None, help='Auto-off start time (HH:MM)')
@click.option('--auto-off-end', default=None, help='Auto-off end time (HH:MM)')
@click.option('--network-power-save/--no-network-power-save', 'net_power_save', default=None,
              help='Enable/disable WiFi power save (requires reboot)')
@click.option('--simple-ui/--no-simple-ui', 'simple_ui', default=None,
              help='Enable/disable Simple UI mode')
@click.option('--learning-ui/--no-learning-ui', 'learning_ui', default=None,
              help='Enable/disable Learning UI mode')
@click.option('--brand-name', default=None, help='Set brand name (VAR/OEM use)')
@click.option('--leader-id', type=int, default=None,
              help='Group-sync leader chipId to follow (0 = Solo/Leader)')
@click.option('--node-id', type=int, default=None,
              help="This device's sync-group node id (readable in patterns via nodeId())")
@no_save_option
def cfg(pb: Pixelblaze, device_name, pixels, brightness, max_brightness,
        led_type, color_order, data_speed, cpu, discovery, tz,
        auto_off_enable, auto_off_start, auto_off_end,
        net_power_save, simple_ui, learning_ui, brand_name,
        leader_id, node_id, no_save):
    """
    Get or set Pixelblaze configuration.

    With no options, fetches and displays the full configuration as JSON.
    With options, sets the specified values (multiple can be combined).

    \b
    Examples:
        pb cfg                                  # Show full config
        pb cfg | jq .config.name                # Query a field
        pb cfg --name "My Pixelblaze"           # Set device name
        pb cfg --pixels 300 --brightness 0.5    # Set multiple values
        pb cfg --led-type WS2812 --color-order GRB
        pb cfg --led-type APA102 --data-speed 2000000
        pb cfg --cpu high                       # Requires reboot
        pb cfg --discovery --timezone America/New_York
        pb cfg --auto-off --auto-off-start 23:00 --auto-off-end 07:00
        pb cfg --leader-id 0 --node-id 1        # Solo/Leader as node 1
        pb cfg --leader-id 9238196 --node-id 2  # Follow leader by chipId
        pb cfg --no-save --brightness 0.2       # Temporary only
    """
    save = not no_save

    # Collect all set operations
    changes = {}

    if device_name is not None:
        pb.setDeviceName(device_name)
        changes['name'] = device_name

    if pixels is not None:
        check(pixels > 0, "Pixel count must be positive")
        pb.setPixelCount(pixels, saveToFlash=save)
        changes['pixelCount'] = pixels

    if brightness is not None:
        check(0.0 <= brightness <= 1.0, "Brightness must be between 0.0 and 1.0")
        pb.setBrightnessSlider(brightness, saveToFlash=save)
        changes['brightness'] = brightness

    if max_brightness is not None:
        check(0 <= max_brightness <= 100, "Max brightness must be between 0 and 100")
        pb.setBrightnessLimit(max_brightness, saveToFlash=save)
        changes['maxBrightness'] = max_brightness

    if led_type is not None:
        led_type_map = {
            'ws2812': Pixelblaze.ledTypes.WS2812,
            'apa102': Pixelblaze.ledTypes.APA102,
            'sk9822': Pixelblaze.ledTypes.SK9822,
            'ws2801': Pixelblaze.ledTypes.WS2801,
            'outputexpander': Pixelblaze.ledTypes.OutputExpander,
            'off': Pixelblaze.ledTypes.noLeds,
        }
        lt = led_type_map[led_type.lower()]
        pb.setLedType(lt, dataSpeed=data_speed, saveToFlash=save)
        changes['ledType'] = led_type
        if data_speed is not None:
            changes['dataSpeed'] = data_speed
    elif data_speed is not None:
        pb.setDataSpeed(data_speed, saveToFlash=save)
        changes['dataSpeed'] = data_speed

    if color_order is not None:
        co = Pixelblaze.colorOrders(color_order.upper())
        pb.setColorOrder(co, saveToFlash=save)
        changes['colorOrder'] = color_order

    if cpu is not None:
        cpu_map = {
            'low': Pixelblaze.cpuSpeeds.low,
            'medium': Pixelblaze.cpuSpeeds.medium,
            'high': Pixelblaze.cpuSpeeds.high,
        }
        pb.setCpuSpeed(cpu_map[cpu.lower()])
        changes['cpuSpeed'] = cpu
        log("Note: CPU speed change requires reboot to take effect")

    if discovery is not None:
        pb.setDiscovery(discovery, timezoneName=tz)
        changes['discoveryEnable'] = discovery
        if tz is not None:
            changes['timezone'] = tz
    elif tz is not None:
        pb.setTimezone(tz)
        changes['timezone'] = tz

    if auto_off_enable is not None:
        pb.setAutoOffEnable(auto_off_enable, saveToFlash=save)
        changes['autoOffEnable'] = auto_off_enable

    if auto_off_start is not None:
        pb.setAutoOffStart(auto_off_start, saveToFlash=save)
        changes['autoOffStart'] = auto_off_start

    if auto_off_end is not None:
        pb.setAutoOffEnd(auto_off_end, saveToFlash=save)
        changes['autoOffEnd'] = auto_off_end

    if net_power_save is not None:
        pb.setNetworkPowerSave(net_power_save)
        changes['networkPowerSave'] = net_power_save
        log("Note: Network power save change requires reboot to take effect")

    if simple_ui is not None:
        pb.setSimpleUiMode(simple_ui)
        changes['simpleUiMode'] = simple_ui

    if learning_ui is not None:
        pb.setLearningUiMode(learning_ui)
        changes['learningUiMode'] = learning_ui

    if brand_name is not None:
        pb.setBrandName(brand_name)
        changes['brandName'] = brand_name

    # Group-sync: leaderId + nodeId bundled in one payload so they commit atomically
    sync_payload = {}
    if leader_id is not None:
        sync_payload['leaderId'] = leader_id
    if node_id is not None:
        sync_payload['nodeId'] = node_id
    if sync_payload:
        sync_payload['save'] = save
        pb.wsSendJson(sync_payload, expectedResponse=None)
        if leader_id is not None:
            changes['leaderId'] = leader_id
            if leader_id == 0:
                log("Note: leaderId=0 → Solo/Leader mode (this device broadcasts or runs standalone)")
            else:
                log(f"Note: this device will follow leader chipId={leader_id}")
        if node_id is not None:
            changes['nodeId'] = node_id

    if changes:
        for k, v in changes.items():
            log(f"  {k}: {v}")
        action = "set" if no_save else "saved"
        log(f"{len(changes)} setting(s) {action}")
    else:
        # No options — read mode: dump full config
        log("Fetching configurations...")
        try:
            wifi = Pixelblaze.getWifiStatus(pb.ipAddress)
            try:
                wifi['mode'] = Pixelblaze.wifiModes(wifi['status']).name
            except (ValueError, KeyError):
                pass
        except Exception as e:
            wifi = {'error': str(e)}
        jsons({
            'config': pb.getConfigSettings(),
            'wifi': wifi,
            'patterns': pb.getPatternList(),
            'playlist': pb.getSequencerPlaylist(),
            'sequencer': pb.getConfigSequencer()
        })


## ─── WiFi ─────────────────────────────────────────────────────────────────────

@pixelblaze.group()
def wifi():
    """
    WiFi configuration commands.

    View WiFi status, scan for networks, join a network, or configure
    the Pixelblaze as an access point. These commands use HTTP-only
    endpoints and work in ad-hoc/setup mode (192.168.4.1).
    """
    pass


@cli(wifi, conn=False)
def status(ctx):
    """
    Show the current WiFi status.

    Displays mode (setup/AP/client), IP address, SSID, and MAC address.

    \b
    Examples:
        pb wifi status
        pb wifi status --ip 192.168.4.1
    """
    ip = discover_pixelblaze(ctx)
    log(f"Fetching WiFi status from {ip}...")
    result = Pixelblaze.getWifiStatus(ip, timeout=ctx.obj['timeout'])

    mode_names = {255: 'setup', 6: 'ap', 3: 'client'}
    mode = result.get('status', -1)
    result['modeName'] = mode_names.get(mode, f'unknown({mode})')
    jsons(result)


@cli(wifi, conn=False)
def scan(ctx):
    """
    Scan for available WiFi networks.

    Initiates a WiFi scan and displays nearby access points sorted by
    signal strength, including SSID, signal (RSSI), channel, and security.

    \b
    Examples:
        pb wifi scan
        pb wifi scan --ip 192.168.4.1
    """
    ip = discover_pixelblaze(ctx)
    log(f"Scanning for WiFi networks from {ip}...")
    results = Pixelblaze.getWifiScan(ip, timeout=ctx.obj['timeout'] * 3)

    if not results:
        log("No networks found (scan may still be in progress, try again)")
        return

    results.sort(key=lambda ap: ap.get('rssi', -999), reverse=True)
    jsons(results)

    log(f"\n  {'SSID':<32} {'RSSI':>5}  {'CH':>3}  {'SECURE'}")
    log(f"  {'─' * 32} {'─' * 5}  {'─' * 3}  {'─' * 6}")
    for ap in results:
        ssid = ap.get('ssid', '?')
        rssi = ap.get('rssi', '?')
        ch = ap.get('channel', '?')
        secure = 'yes' if ap.get('secure') else 'no'
        log(f"  {ssid:<32} {rssi:>5}  {ch:>3}  {secure}")


@cli(wifi, conn=False)
@click.option('--ssid', '-s', required=True, help='SSID of the network to join')
@click.option('--password', '-p', default='', help='Network password (empty for open networks)')
@click.option('--no-discover', is_flag=True, help='Disable Electromage discovery service')
def join(ctx, ssid, password, no_discover):
    """
    Join a WiFi network as a client.

    Connects the Pixelblaze to an existing WiFi network. After joining,
    the device will be reachable at its new IP (check your router or
    run 'pb find' on the target network).

    \b
    Examples:
        pb wifi join -s "MyNetwork" -p "secret"
        pb wifi join --ssid "OpenNetwork"
        pb wifi join -s "MyNet" -p "pass" --no-discover
    """
    ip = discover_pixelblaze(ctx)
    log(f"Joining network '{ssid}' from {ip}...")
    result = Pixelblaze.setWifiConfig(ip, mode="CLIENT", ssid=ssid, passphrase=password,
                                      discover=not no_discover, timeout=ctx.obj['timeout'])
    jsons(result)
    log(f"WiFi config saved — device will connect to '{ssid}'")
    log(f"Use 'pb find' on the target network to discover the new IP")


@cli(wifi, conn=False)
@click.option('--ssid', '-s', required=True, help='SSID (network name) for the access point')
@click.option('--password', '-p', default='', help='Password for the access point (leave empty for open)')
def ap(ctx, ssid, password):
    """
    Configure the Pixelblaze as a WiFi access point.

    Sets the Pixelblaze to create its own WiFi network with the
    given name and optional password.

    \b
    Examples:
        pb wifi ap -s "MyPixelblaze"        # Open AP network
        pb wifi ap -s "MyPB" -p "secret"    # AP with password
    """
    ip = discover_pixelblaze(ctx)
    log(f"Setting AP mode '{ssid}' on {ip}...")
    result = Pixelblaze.setWifiConfig(ip, mode="AP", ssid=ssid, passphrase=password,
                                      timeout=ctx.obj['timeout'])
    jsons(result)
    log(f"AP mode configured — network will be '{ssid}'")


@cli(wifi, conn=False)
def setup(ctx):
    """
    Reset WiFi to setup mode.

    Puts the Pixelblaze back into initial setup mode, equivalent to
    holding the button on boot. The device will create a 'Pixelblaze_*'
    network for configuration.

    \b
    Examples:
        pb wifi setup
    """
    ip = discover_pixelblaze(ctx)
    log(f"Resetting to setup mode on {ip}...")
    result = Pixelblaze.setWifiConfig(ip, mode="SETUP", timeout=ctx.obj['timeout'])
    jsons(result)
    log("WiFi reset to setup mode — look for a 'Pixelblaze_*' network")


@cli(wifi)
def peers(pb: Pixelblaze):
    """
    List the sync-group members this Pixelblaze can see, including itself.

    Follower devices don't broadcast LAN beacons, so `pb find` won't see
    them via the standard discovery path. This command asks the device
    for its current view of the sync group. The connected device is
    prepended to the list and marked with `*`.

    \b
    Examples:
        pb wifi peers
        pb wifi peers --ip 192.168.1.230
    """
    peers = pb.getPeers()

    # getPeers returns only *other* members, not self — synthesize a self row
    # from the device's own config so users see the whole group.
    cfg = pb.getConfigSettings()
    self_entry = {
        'id': cfg.get('chipId', 0),
        'address': pb.ipAddress,
        'name': cfg.get('name', '?'),
        'ver': cfg.get('ver', '?'),
        'isFollowing': 1 if cfg.get('leaderId', 0) else 0,
        'nodeId': cfg.get('nodeId', 0),
        'followerCount': sum(1 for p in peers if p.get('isFollowing')),
        'self': True,
    }
    all_members = [self_entry] + peers
    jsons(all_members)

    log(f"\n    {'NAME':<20} {'ADDRESS':<15} {'CHIPID':>10} {'NODE':>5} {'ROLE':<10} {'VER':<6} {'FOLLOWERS':>9}")
    log(f"    {'─' * 20} {'─' * 15} {'─' * 10} {'─' * 5} {'─' * 10} {'─' * 6} {'─' * 9}")
    for p in all_members:
        role = 'follower' if p.get('isFollowing') else 'leader'
        marker = '*' if p.get('self') else ' '
        # Firmware only fills followerCount reliably from the reporting device's
        # own perspective. From a follower's vantage, a leader peer always
        # reports 0 — mark that unknown instead of parroting a wrong number.
        if p.get('self') or p.get('isFollowing'):
            fc = str(p.get('followerCount', 0))
        else:
            fc = '?'
        log(f"  {marker:<1} {p.get('name', '?'):<20} {p.get('address', '?'):<15} {p.get('id', 0):>10} "
            f"{p.get('nodeId', 0):>5} {role:<10} {p.get('ver', '?'):<6} {fc:>9}")


## ─── Cat ──────────────────────────────────────────────────────────────────────

def _strip_js(source: str) -> str:
    """Strip JS comments (single-line, multi-line) and blank lines."""
    # Remove multi-line comments
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
    # Remove single-line comments (but not URLs like http://)
    source = re.sub(r'(?<!:)//.*$', '', source, flags=re.MULTILINE)
    # Remove blank lines
    lines = [line for line in source.splitlines() if line.strip()]
    return '\n'.join(lines)


@cli(pixelblaze)
@click.argument('path', required=False)
@click.option('--full', is_flag=True, help='Output full source (keep comments and blank lines)')
@click.option('--exact', is_flag=True, help='Match pattern name exactly (no regex/substring)')
@click.option('--one', is_flag=True, help='Output only the first matching pattern (default: all matches)')
def cat(pb: Pixelblaze, path, full, exact, one):
    """
    Output file or pattern source code from the Pixelblaze.

    Without PATH, outputs the currently active pattern's source code.
    With PATH, outputs ALL matching patterns' source code (use --one
    for just the first match).

    By default, strips JS comments and blank lines. Use --full to
    output the raw, unmodified source.

    \b
    Examples:
        pb cat                          # Active pattern source (stripped)
        pb cat --full                   # Active pattern source (full)
        pb cat sound                    # All patterns matching "sound"
        pb cat sound --one              # First pattern matching "sound"
        pb cat "color.*fade" --exact    # Exact name match
        pb cat /config.json             # File from filesystem
        pb cat /pixelmap.txt            # Pixel map function
    """
    # If path starts with /, treat as filesystem path
    if path and path.startswith('/'):
        log(f"Fetching file: {path}")
        content = pb.getFile(path)
        check(content is not None, f"File '{path}' not found on Pixelblaze")
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            # Binary file — write raw bytes to stdout
            import sys
            sys.stdout.buffer.write(content)
            return
        if not full:
            text = _strip_js(text)
        click.echo(text)
        return

    # Pattern mode: find by name/ID, or use active pattern
    if path:
        if one:
            matches = []
            result = _find_pattern(pb, path, exact)
            if result[0]:
                matches = [result]
        else:
            matches = _find_patterns(pb, path, exact)
        check(matches, f"No patterns matching '{path}' on Pixelblaze")
    else:
        log("Fetching active pattern...")
        pattern_id = pb.getActivePattern()
        check(pattern_id, "No active pattern running")
        patterns = pb.getPatternList()
        pattern_name = patterns.get(pattern_id, pattern_id)
        matches = [(pattern_id, pattern_name)]

    for i, (pattern_id, pattern_name) in enumerate(matches):
        if len(matches) > 1:
            if i > 0:
                click.echo("")
            click.echo(f"// ═══ {pattern_name} ({pattern_id}) ═══")

        log(f"Fetching source: '{pattern_name}' ({pattern_id})")
        source_code = pb.getPatternSourceCode(pattern_id)
        if not source_code:
            log(f"  ⚠ Failed to retrieve source for '{pattern_name}'")
            continue

        try:
            source_obj = jsonlib.loads(source_code)
            actual_source = source_obj.get('main', source_code)
        except Exception:
            actual_source = source_code

        if not full:
            actual_source = _strip_js(actual_source)

        click.echo(actual_source)

    if len(matches) > 1:
        log(f"\n{len(matches)} patterns matched '{path}'")


## ─── Filesystem ───────────────────────────────────────────────────────────────

@cli(pixelblaze)
def ls(pb: Pixelblaze):
    """
    List all files stored on the Pixelblaze's filesystem.

    Returns a list of all files including patterns, configuration files,
    and other assets stored on the device.

    \b
    Examples:
        pb ls
        pb ls | jq '.[]' -crM | grep '.c'    # Filter for control files
    """
    log("Fetching file list...")
    jsons(pb.getFileList())


@cli(pixelblaze)
@click.argument('source', type=str)
@click.argument('dest', type=str, required=False)
@click.option(
    '--write',
    '-w',
    is_flag=True,
    help='Upload to Pixelblaze (SOURCE=local file, DEST=Pixelblaze path)'
)
def cp(pb: Pixelblaze, source, dest, write):
    """
    Copy files between the Pixelblaze and local filesystem.

    Without --write (default): Download from Pixelblaze to local
    - SOURCE is the filename on the Pixelblaze (as shown by 'pb ls')
    - DEST is optional local path (defaults to current directory)

    With --write: Upload from local to Pixelblaze
    - SOURCE is the local file path (or Pixelblaze path if piping stdin)
    - DEST is optional Pixelblaze path (defaults to /SOURCE_BASENAME)
    - Supports piping binary data via stdin

    \b
    Examples (download from Pixelblaze):
        pb cp /config.json                    # Save as ./config.json
        pb cp /p/abc123                       # Save as ./abc123
        pb cp /config.json my_config.json     # Save as ./my_config.json
        pb cp /p/abc123 patterns/             # Save as ./patterns/abc123

    \b
    Examples (upload to Pixelblaze):
        pb cp config.json --write             # Upload as /config.json
        pb cp pattern.js --write /p/abc123    # Upload as /p/abc123
        pb cp mymap.txt --write /pixelmap.txt # Upload as /pixelmap.txt
        cat foo.html | gzip | pb cp /index.html.gz --write  # Pipe to Pixelblaze
        cat img.jpg | pb cp /preview.jpg --write            # Binary via stdin
    """
    if write:
        # Upload mode: local → Pixelblaze
        content, is_stdin = read_input(source, name="file", binary=True)

        if is_stdin:
            # When using stdin, SOURCE is the destination on Pixelblaze
            check(dest is None, "Cannot specify DEST when piping stdin (SOURCE becomes the Pixelblaze path)")
            pixelblaze_path = source
        else:
            # Reading from file, SOURCE is local path
            # Determine destination path on Pixelblaze
            if dest is None:
                # Default: use basename with leading slash
                pixelblaze_path = f"/{pathlib.Path(source).name}"
            else:
                pixelblaze_path = dest

        log(f"Uploading to Pixelblaze: {pixelblaze_path}")
        success = pb.putFile(pixelblaze_path, content)

        check(success, f"Failed to upload to '{pixelblaze_path}'")

        size_kb = len(content) / 1024
        log(f"Successfully uploaded → {pixelblaze_path} ({size_kb:.1f} KB)")

    else:
        # Download mode: Pixelblaze → local
        log(f"Fetching file: {source}")
        content = pb.getFile(source)

        check(content is not None, f"File '{source}' not found on Pixelblaze")

        # Determine destination path
        if dest is None:
            # Use basename of source file in current directory
            dest = pathlib.Path(source).name
        else:
            dest_path = pathlib.Path(dest)
            # If dest is a directory, use source basename in that directory
            if dest_path.is_dir():
                dest = dest_path / pathlib.Path(source).name

        dest_path = pathlib.Path(dest)

        # Create parent directories if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        log(f"Writing to: {dest_path}")
        dest_path.write_bytes(content)

        size_kb = len(content) / 1024
        log(f"Successfully copied {source} → {dest_path} ({size_kb:.1f} KB)")


@cli(pixelblaze)
@click.argument('files', nargs=-1, required=True)
def rm(pb: Pixelblaze, files):
    """
    Remove one or more files or patterns from the Pixelblaze.

    FILES can be paths on the Pixelblaze (e.g., /config.json) or pattern IDs.
    If a FILE looks like a pattern ID, it's treated as /p/<id>.

    \b
    Examples:
        pb rm /config.json           # Remove a file
        pb rm abc123456789012       # Remove a pattern (by ID)
        pb rm /p/abc123456789012    # Remove a pattern (by full path)
        pb rm abc123 def456 /data.json  # Remove multiple items
    """
    for file in files:
        # Check if it's a pattern ID
        if Pixelblaze.isPatternId(file):
            # Treat as pattern ID
            log(f"Deleting pattern '{file}'...")
            pb.deletePattern(file)
            log(f"Pattern '{file}' deleted successfully!")
        else:
            # Treat as file path
            log(f"Deleting file '{file}'...")
            success = pb.deleteFile(file)
            check(success, f"Failed to delete file '{file}'")
            log(f"File '{file}' deleted successfully!")


@cli(pixelblaze)
@click.argument('json', type=str)
@click.option(
    '--expect',
    type=str,
    help='Expected response key (e.g., "ack", "playlist")'
)
def ws(pb: Pixelblaze, json, expect):
    """
    Send arbitrary JSON to the Pixelblaze websocket.

    JSON_DATA is the JSON object to send (as a string).

    \b
    Examples:
        pb ws '{ping:true}'
        pb ws '{"getConfig":true}' --expect config
        pb ws '{brightness:0.5, save:false}'
        pb ws '{activeProgramId:"abc123", save:true}'
        pb ws '{'getPlaylist':"_defaultplaylist_"}' --expect playlist
    """
    json_obj = parse_json(json)

    # Send the websocket message, if no --expect is provided, wait for any non-chatty text response
    if expect == "stats":
        expect = pb.messageTypes.specialStats
    response = pb.wsSendJson(json_obj, expectedResponse=expect, waitForAnyResponse=(expect is None))

    if response is None:
        log("No response (fire-and-forget command?)")
    elif isinstance(response, bytes):
        log("Binary response:")
        click.echo(response.hex())
    else:
        log("Response:")
        try:
            jsons(jsonlib.loads(response))
        except:
            # Not JSON, just print it
            click.echo(response)


@click.argument('args', nargs=-1, required=True)
@click.option(
    '--control',
    is_flag=True,
    help='Set as UI controls (sliders) instead of variables'
)
@no_save_option
@cli(pixelblaze)
def var(pb: Pixelblaze, args, control, no_save):
    """
    Set variables or UI controls on the active pattern.

    Variables are pattern exports (export var myVar), while controls are
    UI sliders (export function sliderMyControl(v)).

    Supports multiple input formats that can be mixed:
    - key value pairs: pb var foo bar
    - colon-separated: pb var foo:bar
    - JSON5 objects: pb var '{a:1, b:2}'
    - combined: pb var foo 2 bar:3 '{baz:true}'

    \b
    Examples:
        pb var globalSpeed .3              # Set variable to number
        pb var foo bar                     # Set variable to string
        pb var foo 1                       # Set variable to number 1
        pb var 'foo:bar baz'               # Set foo to "bar baz" (colon format)
        pb var '{a:1, b:2}'                # Set multiple from JSON5 object
        pb var foo 2 bar:3 '{baz:true}'    # Mix all formats
        pb var --control hue 0.33          # Set UI control
        pb var foo bar --no-save           # Don't save to flash
    """
    variables = parse_vars(args)
    check(variables, "No variables specified")

    if control:
        log(f"Setting controls: {variables}")
        pb.setActiveControls(variables, saveToFlash=not no_save)
    else:
        log(f"Setting variables: {variables}")
        pb.setActiveVariables(variables)

    log("Variables set successfully")


@click.option(
    '--count',
    '-c',
    type=int,
    default=5,
    help='Number of pings to send (default: 5)'
)
@cli(pixelblaze)
def ping(pb: Pixelblaze, count):
    """
    Test connection latency to the Pixelblaze.

    Sends ping requests and measures round-trip time to determine
    network latency and Pixelblaze responsiveness.

    \b
    Examples:
        pb ping              # Send 5 pings (default)
        pb ping -c 10        # Send 10 pings
        pb ping --count 3    # Send 3 pings
    """
    log(f"Pinging Pixelblaze...\n")

    times = []
    successful = 0
    failed = 0

    for i in range(count):
        try:
            start = time.time()
            response = pb.sendPing()
            elapsed = (time.time() - start) * 1000

            if response is not None:
                successful += 1
                times.append(elapsed)
                log(f"Ping {i+1}: {elapsed:.2f}ms")
            else:
                failed += 1
                log(f"Ping {i+1}: timeout")

            if i < count - 1:
                time.sleep(0.1)

        except Exception as e:
            failed += 1
            log(f"Ping {i+1}: error - {e}")

    if times:
        min_time = min(times)
        max_time = max(times)
        avg_time = sum(times) / len(times)

        log(f"\n--- Ping statistics ---")
        log(f"Packets: Sent = {count}, Received = {successful}, Lost = {failed} ({failed*100//count}% loss)")
        log(f"Round-trip times: min = {min_time:.2f}ms, max = {max_time:.2f}ms, avg = {avg_time:.2f}ms")

        click.echo(f"{avg_time:.2f}")
    else:
        log(f"\nAll pings failed")
    check(successful > 0, "Failed to ping Pixelblaze")


@cli(pixelblaze, conn=False)
@click.argument('output_file', required=False)
@click.option('--quiet', '-q', is_flag=True, help='Suppress verbose progress output')
@click.option('--decode', '-d', is_flag=True, help='Decode base64 file contents in output')
@click.option('--binary', is_flag=True, help='Include binary content as base64 (with --decode)')
def pbb(ctx, output_file, quiet, decode, binary):
    """
    Export a Pixelblaze Binary Backup (.pbb file).

    Backs up the entire Pixelblaze configuration including patterns, settings,
    map data, and all configuration files.

    If no output file is specified, outputs to stdout as JSON.
    If a filename is provided, saves as a .pbb file (auto-appends .pbb extension if missing).
    If the file already exists, uses that file instead of connecting to Pixelblaze.

    \b
    Examples:
        pb --ip 192.168.1.24 pbb                    # Output to stdout
        pb --ip 192.168.1.24 pbb backup             # Save to backup.pbb
        pb --ip 192.168.1.24 pbb my_config.pbb      # Save to my_config.pbb
        pb --ip 192.168.1.24 pbb -q backup          # Quiet mode
        pb pbb -d backup.pbb                        # Decode existing file
        pb pbb -d --binary backup.pbb               # Include binary as base64
    """
    import pathlib
    import base64

    # Determine the actual file path
    if output_file:
        if not output_file.endswith('.pbb'):
            output_file += '.pbb'

    # Check if file exists and should be used
    if output_file and pathlib.Path(output_file).exists():
        log(f"Using existing file: {output_file}")
        temp_file = output_file
        should_cleanup = False
    else:
        # Need to fetch from Pixelblaze
        log("Creating backup from Pixelblaze...")
        with get_pixelblaze(ctx) as pb:
            backup = PBB.fromPixelblaze(pb, verbose=not quiet)

            if output_file:
                backup.toFile(output_file)
                log(f"Backup saved to {output_file}")
                return
            else:
                temp_file = '/tmp/pixelblaze_backup_temp.pbb'
                backup.toFile(temp_file)
                should_cleanup = True

    # Read and potentially decode the file
    content = pathlib.Path(temp_file).read_text()

    if decode:
        # Decode base64 entries
        from pixelblaze.pixelblaze import PBP

        data = jsonlib.loads(content)
        if 'files' in data:
            decoded_files = {}
            for filename, b64_content in data['files'].items():
                try:
                    # Decode base64
                    decoded = base64.b64decode(b64_content)

                    # Check if it's a PBP (Pixelblaze Binary Pattern) file
                    if filename.startswith('/p/') and len(decoded) > 36:
                        try:
                            # Parse PBP format
                            pbp = PBP.fromBytes(filename.split('/')[-1], decoded)
                            decoded_files[filename] = {
                                'name': pbp.name,
                                'sourceCode': jsonlib.loads(pbp.sourceCode),
                                'preview': '<jpeg>' if not binary else base64.b64encode(pbp.jpeg).decode('utf-8'),
                                'byteCode': '<bytecode>' if not binary else base64.b64encode(pbp.byteCode).decode('utf-8')
                            }
                            continue
                        except Exception:
                            # Not a valid PBP, try other formats
                            pass

                    # Try to parse as UTF-8 text
                    try:
                        text = decoded.decode('utf-8')
                        # Try to parse as JSON
                        try:
                            decoded_files[filename] = jsonlib.loads(text)
                        except jsonlib.JSONDecodeError:
                            # Not JSON, just text
                            decoded_files[filename] = text
                    except UnicodeDecodeError:
                        # Binary content (images, etc.)
                        if binary:
                            decoded_files[filename] = b64_content
                        else:
                            # Detect image format
                            if decoded.startswith(b'\xff\xd8\xff'):
                                decoded_files[filename] = '<jpeg>'
                            elif decoded.startswith(b'\x89PNG'):
                                decoded_files[filename] = '<png>'
                            else:
                                decoded_files[filename] = '<binary>'
                except Exception:
                    # If decode fails, keep original
                    decoded_files[filename] = b64_content

            data['files'] = decoded_files
            content = jsonlib.dumps(data, indent=2)

    click.echo(content)
    if should_cleanup:
        pathlib.Path(temp_file).unlink()


@cli(pixelblaze)
@click.argument('input_file')
@click.option('--quiet', '-q', is_flag=True, help='Suppress verbose progress output')
@click.option('--name', 'device_name', default=None,
              help='Override the device name on the target (avoids identity clash)')
@click.option('--keep-name', is_flag=True,
              help="Preserve the target device's current name (don't overwrite from backup)")
@click.option('--keep-config', is_flag=True,
              help="Skip restoring config files entirely (only restore patterns, playlists, etc.)")
def restore(pb: Pixelblaze, input_file, quiet, device_name, keep_name, keep_config):
    """
    Restore a Pixelblaze from a Binary Backup (.pbb file).

    Restores the entire Pixelblaze configuration from a .pbb backup file,
    including patterns, settings, map data, and all configuration files.

    When cloning a backup to a different Pixelblaze, use --name or
    --keep-name to avoid identity clashes (both devices having the same
    name on the network). Use --keep-config to skip config files entirely
    and only restore patterns and playlists.

    WARNING: This will overwrite all current patterns and settings!

    \b
    Examples:
        pb restore backup.pbb                          # Full restore
        pb restore backup.pbb --name "Living Room 2"   # Restore with new name
        pb restore backup.pbb --keep-name              # Keep target's current name
        pb restore backup.pbb --keep-config            # Only restore patterns/playlists
        pb restore backup.pbb -q                       # Quiet mode
    """
    check(not (device_name and keep_name), "Cannot use --name and --keep-name together")
    check(not (device_name and keep_config), "Cannot use --name and --keep-config together (--keep-config skips all config)")

    if not input_file.endswith('.pbb'):
        input_file += '.pbb'

    log(f"Restoring from {input_file}...")
    backup = PBB.fromFile(input_file)

    if keep_config:
        # Remove all config files from the backup so they won't be restored
        # Note: PBB.deleteFile has an upstream bug (looks at top-level instead
        # of ['files']), so we patch the backup data directly.
        config_files = backup.getFileList(PBB.fileTypes.fileConfig)
        if config_files:
            import json as _json
            _data = _json.loads(backup._PBB__textData)
            for f in config_files:
                if f in _data.get('files', {}):
                    del _data['files'][f]
                    log(f"Skipping config file: {f}")
            backup._PBB__textData = _json.dumps(_data, indent=2)
    elif keep_name or device_name:
        # Determine the name to use
        if keep_name:
            target_name = pb.getDeviceName()
            log(f"Preserving target device name: {target_name}")
        else:
            target_name = device_name
            log(f"Overriding device name to: {target_name}")

        # Patch /config.json in the backup with the desired name
        try:
            config_bytes = backup.getFile('/config.json')
            config = jsonlib.loads(config_bytes.decode('utf-8'))
            old_name = config.get('name', '(unknown)')
            config['name'] = target_name
            log(f"Patching config.json: name '{old_name}' → '{target_name}'")
            backup.putFile('/config.json', jsonlib.dumps(config).encode('utf-8'))
        except (KeyError, jsonlib.JSONDecodeError) as e:
            log(f"Warning: could not patch config.json ({e}), restoring as-is")

    backup.toPixelblaze(pb, verbose=not quiet)
    log("Restore complete!")


@pixelblaze.group()
def cache():
    """
    Manage Pixelblaze CLI cache.

    The cache stores the last used IP address and compiled pattern compilers
    to speed up CLI operations.
    """
    pass


@cache.command()
def show():
    """Show cache location and contents."""
    cache_dir = get_cache_dir()

    log(f"Cache directory: {cache_dir}")
    log("")

    # Show IP cache
    last_ip = _read_cache().get('lastIp')
    log(f"Cached IP: {last_ip}" if last_ip else "Cached IP: (none)")

    # Show compiler cache
    compiler_cache = cache_dir / 'compiler_cache'
    if compiler_cache.exists():
        cached_compilers = list(compiler_cache.glob('*.js'))
        if cached_compilers:
            log(f"\nCached compilers ({len(cached_compilers)}):")
            for compiler_file in sorted(cached_compilers):
                version = compiler_file.stem
                size_kb = compiler_file.stat().st_size / 1024
                log(f"  - Version {version} ({size_kb:.1f} KB)")
        else:
            log("\nCached compilers: (none)")
    else:
        log("\nCached compilers: (none)")


@cache.command()
@click.option('--compiler', is_flag=True, help='Only clear compiler cache')
@click.option('--ip', is_flag=True, help='Only clear IP cache')
def clear(compiler, ip):
    """Clear the cache."""
    import shutil

    cache_dir = get_cache_dir()

    if not compiler and not ip:
        # Clear everything
        if click.confirm(f"Clear all cache in {cache_dir}?", err=True):
            shutil.rmtree(cache_dir, ignore_errors=True)
            log("Cache cleared")
        return

    if ip:
        cache = _read_cache()
        if cache.pop('lastIp', None) is not None:
            _write_cache(cache)
            log("IP cache cleared")
        else:
            log("No IP cache to clear")

    if compiler:
        compiler_cache = cache_dir / 'compiler_cache'
        if compiler_cache.exists():
            shutil.rmtree(compiler_cache, ignore_errors=True)
            log("Compiler cache cleared")
        else:
            log("No compiler cache to clear")


@cli(pixelblaze, conn=False)
@click.option('--wait', is_flag=True, help='Wait for device to come back online after reboot')
def reboot(ctx, wait):
    """
    Reboot the Pixelblaze device.

    Can be useful for getting out of non-responsive state.

    \b
    Examples:
        pb reboot
        pb reboot --wait    # Wait for device to come back online
    """
    import requests

    device_ip = None

    def send_reboot_http(ip):
        """Send reboot command via direct HTTP POST."""
        url = f"http://{ip}/reboot"
        log(f"Sending reboot command to {ip}...")
        try:
            response = requests.post(url, timeout=5)
            if response.status_code in [200, 404]:
                return True
            response.raise_for_status()
        except requests.RequestException as e:
            log(f"Error sending reboot: {e}")
            return False
        return True

    # Try normal method first
    try:
        with get_pixelblaze(ctx) as pb:
            log("Rebooting Pixelblaze...")
            pb.reboot()
            log("Reboot command sent successfully")
            device_ip = pb.ipAddress
    except ConnectionResetError as e:
        if e.errno == 54:
            log("Device websocket not responding, trying direct HTTP reboot...")
            discovered_ip = discover_pixelblaze(ctx)
            if send_reboot_http(discovered_ip):
                log("Reboot command sent successfully (via HTTP)")
                device_ip = discovered_ip
            else:
                log("Failed to send reboot command")
                return
        else:
            raise
    except Exception as e:
        # For any other connection issues, try direct POST
        log(f"Connection failed ({type(e).__name__}), trying direct HTTP reboot...")
        discovered_ip = discover_pixelblaze(ctx)
        if send_reboot_http(discovered_ip):
            log("Reboot command sent successfully (via HTTP)")
            device_ip = discovered_ip
        else:
            log("Failed to send reboot command")
            return

    if wait:
        log("Waiting for device to come back online...")
        # Give the device time to actually reboot
        time.sleep(2)

        reconnected = False
        attempts = 0
        max_attempts = 60  # 60 seconds timeout

        while not reconnected and attempts < max_attempts:
            try:
                # Try to create a fresh connection using context manager
                with Pixelblaze(device_ip) as test_pb:
                    test_pb.getConfigSettings()
                    reconnected = True
                    log("Device is back online!")
            except Exception:
                attempts += 1
                time.sleep(1)

        if not reconnected:
            log("Warning: Timed out waiting for device to reconnect")


@pixelblaze.group()
def cache():
    """View and refresh the on-disk device cache (no network unless 'refresh')."""
    pass


@cache.command(name='ls')
@click.option('--json', 'as_json', is_flag=True, help='Output one JSON object per device.')
def cache_ls(as_json):
    """List all cached Pixelblazes with summary info. No network calls.

    \b
    Examples:
        pb cache ls            # human-readable summary, * marks lastIp
        pb cache ls --json     # JSONL output for piping into jq
    """
    cache_data = _read_cache()
    devices = cache_data.get('devices', {})
    last_ip = cache_data.get('lastIp')
    if not devices:
        log("No cached devices. Run `pb find` to discover.")
        return
    for ip, entry in devices.items():
        if as_json:
            click.echo(jsonlib.dumps(entry, separators=(',', ':')))
            continue
        marker = '*' if ip == last_ip else ' '
        name = entry.get('name', '?') or '?'
        pixels = entry.get('pixelCount', '?')
        ver = entry.get('ver', '?')
        active = entry.get('activePatternName') or entry.get('activePatternId') or '-'
        last_seen = entry.get('lastSeenAt', 'never')
        click.echo(f"{marker} {ip:15}  {name:20}  {pixels}px  v{ver}  → {active}  @ {last_seen}")


@cache.command(name='show')
@click.argument('query', required=False)
def cache_show(query):
    """Show full cached config for a device (no network call).

    QUERY is an IP, a device name, or a name substring. With no QUERY, shows lastIp.

    \b
    Examples:
        pb cache show                  # full dump of lastIp's config
        pb cache show jforb            # lookup by name substring
        pb cache show 192.168.1.86     # lookup by exact IP
    """
    if not query:
        last_ip = _read_cache().get('lastIp')
        if not last_ip:
            raise click.ClickException("No lastIp cached. Specify <ip-or-name> or run `pb find`.")
        query = last_ip
    ip, entry = lookup_cached_device(query)
    click.echo(jsonlib.dumps(entry, indent=2))


@cache.command(name='refresh')
@click.argument('query', required=False)
@click.option('--all', 'all_devices', is_flag=True, help='Refresh every cached device in parallel.')
@click.option('--timeout', 'conn_timeout', type=float, default=5.0,
              help='Per-device connection timeout in seconds.', show_default=True)
def cache_refresh(query, all_devices, conn_timeout):
    """Force-refresh cached config from device(s), bypassing TTL. Always fetches patterns.

    \b
    Examples:
        pb cache refresh              # refresh lastIp
        pb cache refresh jforb        # refresh by name substring
        pb cache refresh --all        # refresh every cached device (parallel)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cache_data = _read_cache()
    devices_cached = cache_data.get('devices', {})
    if not devices_cached:
        raise click.ClickException("No cached devices. Run `pb find` first.")

    if all_devices:
        targets = list(devices_cached.keys())
    elif query:
        ip, _ = lookup_cached_device(query)
        targets = [ip]
    else:
        last_ip = cache_data.get('lastIp')
        if not last_ip:
            raise click.ClickException("Specify QUERY or --all, or set lastIp via `pb find`.")
        targets = [last_ip]

    log(f"Refreshing {len(targets)} device(s)...")
    Pixelblaze.default_recv_timeout = conn_timeout

    def _refresh_one(ip):
        try:
            with Pixelblaze(ip) as pb:
                return _fetch_device_config(pb, ip=ip, include_patterns=True)
        except Exception as e:
            log(f"  {ip}: failed ({type(e).__name__}: {e})")
            return None

    refreshed = []
    with ThreadPoolExecutor(max_workers=min(len(targets), 8)) as pool:
        futures = {pool.submit(_refresh_one, ip): ip for ip in targets}
        for fut in as_completed(futures):
            r = fut.result()
            if r:
                refreshed.append(r)
                log(f"  {r['ip']}: {r.get('name', '?')} "
                    f"(v{r.get('ver', '?')}, {r.get('pixelCount', '?')}px, "
                    f"{len(r.get('patterns', {}))} patterns)")

    if refreshed:
        update_device_cache(refreshed)
        log(f"Refreshed {len(refreshed)}/{len(targets)} device(s).")
    else:
        raise click.ClickException("Could not refresh any devices.")


# `pb top` lives in a sibling module for size; register it onto the group here.
_register_top(pixelblaze)


def main():
    """Entry point for the CLI."""
    pixelblaze(obj={})


if __name__ == '__main__':
    main()
