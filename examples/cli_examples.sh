#!/bin/bash
# pb — Pixelblaze CLI cookbook: every subcommand, the powerful stuff first.
# A file to copy from, not to run. More: `pb <cmd> --help`, pixelblaze/cli/{cli,test_cli}.py

# ─── pattern: live-code the LEDs ──────────────────────────────────────────────
pb pattern "hsv(0.5, 1, 1)"                  # inline code renders immediately (nothing saved)
pb pattern "hsv(index / pixelCount + time(0.1), 1, 1)"   # rainbow wave one-liner
echo "rgb(0, 0, 1)" | pb pattern             # code from stdin
pb pattern fx.js --var '{speed:.5, glow:1}'  # from file, with vars (JSON5 ok)
pb pattern "KITT"                            # a name or ID switches instead of rendering
pb pattern hsv --lookup                      # force name lookup when input smells like code
pb pattern fire.js --write                   # save to device (name = filename stem)
pb pattern "hsv(time(.1),1,1)" --write "Fast Rainbow" --img preview.jpg
pb pattern updated.js --write ko78Sg5a       # overwrite an existing pattern ID
pb pattern "Bad Pattern" --rm                # delete it
pb cat                                       # active pattern's source (comments stripped)
pb cat sparkle --one                         # first pattern matching "sparkle"
pb cat "glitch bank" --exact --full          # exact name, raw unstripped source

# ─── top + ws: fleet dashboard & raw websocket ────────────────────────────────
pb top                                       # live table of every PB on the LAN; down rows go red
pb top --sort fps -n 0.25                    # sort by FPS, redraw 4×/sec
pb top --active -r 10                        # hide down rows, rediscover every 10s
pb top --all | less -S                       # every column, busiest first
pb top --columns name,ip,fps,seqmode,plleft  # hand-picked columns (--list-columns for keys)
pb top --once --json | jq .                  # one snapshot, exit — cron / dashboards
pb top --json -n 5 | jq -c '.[].name'        # stream a JSON array every 5s
pb ws '{getConfig: true}'                    # arbitrary JSON, loose JSON5 keys fine
pb ws '{brightness: 0.1}' --expect stats     # wait for a specific response key
pb ws '{sendUpdates: false, listPrograms: true, getPeers: 1}' | jq .

# ─── snoop: watch the websocket protocol on the wire ──────────────────────────
# Needs tshark + jq (brew install wireshark jq) and permission to capture
# (brew install --cask wireshark-chmodbpf, or use --sudo).
pb snoop                                     # every frame to/from the resolved device
pb snoop --responses                         # only what the Pixelblaze says back
pb snoop --requests --time                   # only what we send, with a clock
pb --ip kitchen snoop                        # target by cached name, like any command
pb snoop --others 231,bike2                  # several devices in one capture
pb snoop --any                               # every websocket on the wire, no IP resolve
pb snoop --host me                           # ignore the phone app and other clients
pb snoop -v '"fps"'                          # drop the once-a-second status spam
pb snoop -g setVars                          # only variable writes
pb snoop --jq 'select(.msg.activeProgram)'   # arbitrary jq over the decoded stream
pb snoop --bare > session.jsonl              # clean protocol log, no envelope
pb snoop --midstream                         # attach to a connection already open
pb snoop -w cap.pcapng                       # stream AND save raw packets
pb snoop --read cap.pcapng                   # replay a saved capture (no perms needed)
pb snoop --dry-run                           # print the tshark|jq pipeline, run it yourself
pb snoop --requests & pb var speed 0.8       # snoop in the background, then watch a command

# ─── sensor: sound-reactive with no hardware ──────────────────────────────────
pb sensor sound                              # stream host audio FFT as sensor-board vars
pb sensor sound -d "MacBook" -g 20 --log     # built-in mic: boost gain + compress range
pb sensor sound --agc --fps 60               # auto-gain, 60 pushes/sec
pb sensor sound -l                           # list audio inputs (default device: blackhole)
pb sensor sources                            # accel/light/sound/analog source preferences
pb sensor sources --prefer remote --type sound   # audio from the bridge; rest untouched

# ─── playlist / sequencer ─────────────────────────────────────────────────────
pb playlist set 'blink fade,honeycomb,xorcery' --shuffle -d 15   # by name substrings
pb playlist set 'patterns/colorOrder.js,sparkle' -d 10           # .js paths upload + enqueue
pb playlist play; pb playlist pause          # transport
pb playlist next; pb playlist rand           # skip ahead / jump anywhere
pb playlist len 30                           # 30s per pattern (--no-save to just try it)

# ─── var: pattern variables & UI controls ─────────────────────────────────────
pb var                                       # {"vars":…, "controls":…} — exports + sliders
pb var | jq .controls.sliderArms             # read one control
pb var speed .3                              # set — sent to both vars and controls
pb var speed:0.5 color:1                     # colon pairs
pb var '{speed: 0.5, on: true}'              # JSON5 object
pb vars foo 2 bar:3 '{baz:true}' --no-save   # mix formats (vars = alias), skip flash

# ─── backup, restore, firmware ────────────────────────────────────────────────
pb pbb backup                                # full device backup → backup.pbb
pb pbb                                       # backup JSON to stdout
pb pbb -d backup.pbb                         # decode base64 innards (--binary keeps blobs)
pb pbb -d backup.pbb | jq '.files[].sourceCode?.main' -crM | bat -l js   # read all source
pb restore backup.pbb                        # WARNING: overwrites the whole device
pb restore backup.pbb --name "Porch 2"       # clone to a 2nd PB without an identity clash
pb restore backup.pbb --keep-config          # patterns + playlists only
pb update ~/Downloads/v3.70.pb32.stfu        # flash firmware: chunked upload, live progress
pb --ip 192.168.4.1 update fw.stfu --no-monitor   # SoftAP recovery, fire and wait

# ─── targeting a device ───────────────────────────────────────────────────────
pb pixels                                    # no --ip: auto (192.168.4.1 ad-hoc, then LAN scan)
pb --ip 192.168.1.100 pixels                 # exact IP (fastest)
pb --ip http://192.168.1.100/ pixels         # URL pasted straight from the browser
pb --ip 100 pixels                           # bare host octet → .100 on this subnet
pb --ip kitch pixels                         # cached device-name fragment (3+ chars)

# ─── discovery, latency, cache ────────────────────────────────────────────────
pb find                                      # fast: beacon IPs as JSONL (first hit → cached)
pb find --full                               # connect to each: names, versions, pixel counts
pb find --name tree --ip 10.                 # filters combine (--name implies --full)
pb find 2>/dev/null                          # stdout is pure JSONL
pb ping -c 10                                # round-trip latency
pb cache ls                                  # cached devices, * marks lastIp — no network
pb cache show kitch                          # full cached config by name fragment
pb cache refresh --all                       # re-pull every cached device in parallel

# ─── power, pixels, config ────────────────────────────────────────────────────
pb on                                        # full brightness (saved to flash)
pb on 0.5 --no-save                          # 50%, temporary
pb on --play-sequencer                       # …and start the sequencer
pb off --pause-sequencer                     # dark + halt pattern changes
pb reboot --wait                             # bounce it, block until it's back
pb pixels                                    # read pixel count
pb pixels 300 --no-save                      # set it (drop --no-save to persist)
pb cfg                                       # full config JSON (| yq -P for color)
pb cfg --name "Porch" --brightness 0.5       # set any mix of fields
pb cfg --led-type apa102 --data-speed 2000000 --color-order grb
pb cfg --cpu high                            # 240 MHz (takes effect after reboot)
pb cfg --auto-off --auto-off-start 23:00 --auto-off-end 07:00
pb cfg --leader-id 9238196 --node-id 2       # follow a sync-group leader by chipId

# ─── map: pixel mapper ────────────────────────────────────────────────────────
pb map                                       # current coords, normalized 0–1
pb map --csv > coords.csv                    # export as x,y,z CSV
pb map map.js                                # set from mapper JS (stdin works too)
pb map --csv < coords.csv                    # set from CSV
pb map --clear                               # remove the map

# ─── files on the device ──────────────────────────────────────────────────────
pb ls                                        # everything on the flash FS
pb ls | jq '.[]' -crM | grep '\.c$'          # just pattern-control files
pb cat /config.json                          # print any file (also /pixelmap.txt etc.)
pb cp /config.json                           # download → ./config.json
pb cp /config.json backup_config.json        # download to an explicit local path
pb cp /p/abc123 patterns/                    # download a pattern into a directory
pb cp /index.html.gz bak.index.html.gz       # download (stock web UI backup!)
pb cp config.json --write                    # upload as /config.json
pb cp mymap.txt --write /pixelmap.txt        # upload to an explicit device path
cat custom.html | gzip | pb cp /index.html.gz --write   # pipe binary via stdin
pb rm /data.json abc123456789012             # files and/or patterns (bare ID → /p/<id>)

# ─── wifi ─────────────────────────────────────────────────────────────────────
pb wifi status                               # mode, IP, SSID, MAC
pb wifi scan                                 # nearby APs by signal strength
pb wifi join -s "MyNet" -p "secret"          # become a client
pb wifi ap -s "MyPB" -p "secret"             # become an access point
pb wifi setup                                # back to Pixelblaze_* setup mode
pb wifi peers                                # sync group incl. self (*) — followers don't beacon
