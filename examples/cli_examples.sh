#!/bin/bash
# Pixelblaze CLI Examples
# Collection of common usage patterns for the pb command

# >>>>>>>>>>>
# >>>>>>>>>>> See Also:
# >>>>>>>>>>> test_cli.py examples, and --help strings, and, of course, cli.py
# >>>>>>>>>>>

# Basic Discovery and Connection
# ==============================

# Auto-discover Pixelblaze (checks 192.168.4.1 first, then network scan)
pb pixels

# Use specific IP address
pb --ip 192.168.1.100 pixels

# Check connection latency
pb ping


# Realtime Dashboard (top-style)
# ==============================

# Live table of every Pixelblaze on the LAN — FPS, memory, active pattern,
# uptime, brightness, etc. Devices that drop off go red; when they rejoin
# they turn back green.
pb top

# Faster redraw
pb top -n 0.25

# Sort by frames-per-second
pb top --sort fps

# One-shot machine-readable snapshot (great for cron / dashboards)
pb top --once --json | jq .

# Rediscover every 10s (default 30s) — pick up devices that just booted
pb top -r 10


# Basic Controls
# =============

# Turn off all LEDs
pb off

# Turn on at full brightness
pb on

# Turn on / set 50% brightness, do not save to flash
pb on 0.5 --no-save

# Turn off and save state to flash
pb off

# Turn on with sequencer
pb on --play-sequencer

# Print most configs (pipe to yq for colors if available)
pb cfg
pb cfg | yq -P


# Pixel Configuration
# ===================

# Get current pixel count
pb pixels

# Set pixel count to 300 (temporary)
pb pixels 300

# Set pixel count and save to flash
pb pixels 144 --save

# Show current pixel mapper coordinates / function
pb map
pb map --csv


# Sequencer Control
# =================

# Start the sequencer
pb playlist play

# Pause the sequencer
pb playlist pause

# Go to next pattern
pb playlist next

# Jump to random pattern
pb playlist rand

# Set all patterns to 10 seconds
pb playlist len 10

# Set all patterns to 30 seconds and save
pb playlist len 30 --save

# Save the playlist matching case insensitive CSV pattern name substrings,
# each 15 seconds, shuffle the supplied order
pb playlist set 'blink fade,block reflections,honeycom,xorc' --shuffle -d 15


# Live Pattern Rendering (Temporary)
# ==================================

# Simple solid color (inline code)
pb pattern "hsv(0.5, 1, 1)"

# Rainbow wave (inline code)
pb pattern "hsv(index / pixelCount + time(0.1), 1, 1)"

# Render from file without saving
pb pattern examples/test_pattern.js

# Render with variables
pb pattern examples/test_pattern.js --var speed 0.5

# Render with JSON variables (supports JSON5/loose keys)
pb pattern src.js --var '{speed: 0.5, brightness: 1.0}'

# Render from stdin
echo "rgb(0, 0, 1)" | pb pattern


# Pattern Management (Save/Switch/Delete)
# =======================================

# Switch to an existing pattern by name
pb pattern "KITT"

# Switch to existing pattern by ID
pb pattern "wDn9FrZh8zZfKweL4"

# Save a local file to Pixelblaze (name defaults to filename)
pb pattern my_pattern.js --write

# Save with a custom name
pb pattern my_pattern.js --write "My Cool Pattern"

# Save with a specific preview image
pb pattern fire.js --write --img fire_preview.jpg

# Save inline code as a new pattern
pb pattern "hsv(time(.1),1,1)" --write "Fast Rainbow"

# Overwrite a specific pattern ID
pb pattern updated_code.js --write ko78Sg5a

# Delete a pattern
pb pattern "Bad Pattern" --rm


# Variables & Controls
# ====================

# Set a variable on the currently running pattern
pb var speed 0.2

# Set multiple variables (flexible syntax)
pb var speed:0.5 color:1
pb var '{speed: 0.5, color: 1}'

# Set a UI Control (slider) value
pb var --control hue 0.5


# Backup & Restore (.pbb)
# =======================

# Backup everything to a file
pb pbb backup.pbb

# Output backup JSON to stdout (great for piping)
pb pbb

# Decode a backup file to inspect contents (decodes base64 files/code)
pb pbb -d backup.pbb
pb pbb -d --binary backup.pbb

# Pretty print all pattern source code
pb pbb -d backup.pbb | jq '.files[].sourceCode?.main' -crM | bat -l js

# Restore from a backup file (WARNING: Overwrites device)
pb restore backup.pbb


# File Operations (ls/cp)
# =======================

# List all files on Pixelblaze
pb ls
pb ls | jq '.[]' -crM | grep '.c'

# Download a file from Pixelblaze
pb cp /config.json
pb cp /config.json backup_config.json

# Backup the stock index.html.gz
pb cp /index.html.gz bak.index.html.gz

# Upload a file to Pixelblaze
pb cp config.json --write

# Upload custom HTML with gzip pipe
cat custom.html | gzip | pb cp /index.html.gz --write


# Advanced / Debugging
# ====================

# Send raw JSON command to Websocket
pb ws '{getConfig: true}'
pb ws '{sendUpdates: false, getConfig: true, listPrograms: true, getUpgradeState: true, getPeers: 1}' | jq .

# Set a raw property
pb ws '{"brightness": 0.1}' --expect stats

# Check cache info
pb cache show

# Clear cache
pb cache clear