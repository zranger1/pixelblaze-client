# Snooping the wire

`pb snoop` (alias `pb watch`) decodes live Pixelblaze websocket traffic to
JSON. It shells out to `tshark` for capture and dissection and pipes the result
through `jq`, so everything below composes with the rest of your shell. With
`--udp` it decodes the [discovery beacons](#discovery-beacons-udp) instead.

```console
$ pb snoop
{"dir":"→","msg":{"getConfig":true}}
{"dir":"←","msg":{"fps":42.5,"vmerr":0,"mem":10000}}
{"dir":"←","msg":{"activeProgram":{"name":"sparks"}}}
{"dir":"→","msg":{"setVars":{"speed":0.5}}}
```

`→` is a frame going **to** a Pixelblaze (a request), `←` one coming **from**
it (a response).

## Installing the dependencies

Both `tshark` and `jq` must be on `PATH`. `pb snoop` checks for them up front
and prints the right command for your platform rather than failing with
tshark's own error.

=== "macOS"

    ```bash
    brew install wireshark          # CLI only — tshark, no GUI
    brew install --cask wireshark   # GUI app, also ships tshark
    brew install jq
    ```

=== "Linux"

    ```bash
    sudo apt install tshark jq              # Debian/Ubuntu
    sudo dnf install wireshark-cli jq       # Fedora/RHEL
    ```

=== "Windows"

    ```powershell
    choco install wireshark jq              # Chocolatey
    winget install WiresharkFoundation.Wireshark; winget install jqlang.jq
    scoop install wireshark jq
    ```

    The Wireshark installer does not always add `tshark` to `PATH`; it lives at
    `C:\Program Files\Wireshark\tshark.exe`.

### Capture permissions

Capturing raw packets is privileged on every platform.

| Platform | Mechanism | Fix |
|---|---|---|
| macOS | `/dev/bpf*` is root-only | `brew install --cask wireshark-chmodbpf`, then log out and back in — or `pb snoop --sudo` |
| Linux | `dumpcap` capabilities | `sudo usermod -aG wireshark $USER`, or `sudo setcap cap_net_raw,cap_net_admin+eip $(which dumpcap)` — or `pb snoop --sudo` |
| Windows | Npcap driver | Install Npcap (bundled with Wireshark). If it was installed with *Restrict to Administrators*, run from an elevated terminal — `--sudo` does nothing on Windows |

`pb snoop` checks macOS BPF readability before starting and tells you which of
these applies. `--read` needs no permissions at all.

## What you can and cannot see

!!! warning "You only see traffic that crosses this machine"

    A switch or access point forwards a unicast frame only to the port owning
    the destination MAC. `--others` and `--any` widen the **filter**; they do
    not widen what the **interface** can physically see.

| Traffic | Visible |
|---|---|
| this machine ↔ a Pixelblaze | :material-check: yes |
| this machine ↔ an emulator on localhost | :material-check: yes (auto-selects `lo0`) |
| anyone's broadcast/multicast (UDP:1889 beacons, see [`--udp`](#discovery-beacons-udp)) | :material-check: yes |
| Pixelblaze ↔ Pixelblaze unicast (sync-group leader/follower) | :material-close: **no** |

To see traffic between two other devices you need WiFi monitor mode with WPA2
decryption, a mirrored switch port, or to make this machine the access point.

## Timing matters for decoding

tshark identifies a websocket stream by watching for the HTTP upgrade
handshake, so **start `pb snoop` before the traffic you want to see**.

To attach to a connection that is already open — a browser tab you left
running — pass `--midstream`, which decodes the port as websocket directly.
Do *not* use it when the handshake is in the capture; tshark will try to parse
the handshake as frames and produce garbage.

```bash
pb snoop                 # start first, then run commands / click the UI
pb snoop --midstream     # attach to a connection already established
```

## Choosing what to watch

Targeting reuses the same flexible resolution as the global `--ip`, so
addresses, pasted URLs, bare host octets and cached name fragments all work.

```bash
pb snoop                                # the resolved device
pb --ip kitchen snoop                   # cached name fragment
pb snoop --others 231,bike2             # several devices in one capture
pb snoop --others http://192.168.1.5/   # pasted from a browser
pb snoop --any                          # every websocket on the wire, no resolution
```

`--host` restricts the *other* end of the conversation. It defaults to `any`,
which shows every client talking to the device — including a phone app, when
the network lets you see it.

```bash
pb snoop --host me                      # only this machine's traffic
pb snoop --host 192.168.1.55            # only that client's traffic
```

Direction, both shown by default:

```bash
pb snoop --requests                     # only what we send
pb snoop --responses                    # only what the Pixelblaze says
```

Under `--any`, direction is decided by the **listening port** rather than by
your own address — a Pixelblaze is always the websocket server — so
`pb snoop --any --requests` means every client's requests, not just yours.

## Filtering and shaping the stream

```bash
pb snoop -v '"fps"'                        # drop the once-a-second status spam
pb snoop -g setVars                        # only variable writes
pb snoop --jq 'select(.msg.activeProgram)' # arbitrary jq over the decoded stream
pb snoop --jq 'select(.msg.fps) | .msg.fps'
```

`-g`/`--grep` and `-v`/`--exclude` are regexes matched against the raw payload;
`--jq` is appended to the pipeline and sees the finished record.

The envelope adapts — fields that would be identical on every line are dropped,
so a single device with `--responses` degrades to bare protocol JSON. Force it
either way with `--bare` or `--full`:

```bash
pb snoop --bare > session.jsonl   # just the messages, no envelope
pb snoop --full                   # always ts, dir, peer, src, dst
pb snoop --time                   # add a local clock timestamp
```

## Discovery beacons (`--udp`)

Every Pixelblaze that is not a sync-group *follower* broadcasts a small beacon
on UDP:1889 about once a second. It is what `pb find` listens for, and what
Firestorm answers with a `timeSync` packet to keep clocks aligned. Because it
is broadcast, it is visible from anywhere on the LAN — the one kind of
Pixelblaze traffic you can watch without being a party to it.

`--udp` (alias `--beacons`) captures and decodes both packet types instead of
websocket frames:

```console
$ pb snoop --udp -t
{"ts":"11:08:45.104","kind":"beacon","src":"192.168.1.230","sender_id":3858868416,"sender_ip":"192.168.1.230","sender_ms":567447843,"skew_ms":-12}
{"ts":"11:08:45.106","kind":"timeSync","src":"192.168.1.67","dst":"192.168.1.230","sync_id":890,"time_ms":567447855,"sender_id":3858868416,"sender_ip":"192.168.1.230","sender_ms":567447843}
```

| Field | Meaning |
|---|---|
| `kind` | `beacon` (device → broadcast), `timeSync` (Firestorm → device), `sensor` (see below), or `unknown` with the raw `hex` |
| `sender_id` / `sender_ip` | The same four bytes: the Pixelblaze's IPv4 address, raw as the library keys devices by it, and dotted |
| `sender_ms` | The device's clock — the low 32 bits of unix time in milliseconds |
| `skew_ms` | Beacons only: `sender_ms` minus the capture time, i.e. how far the device's clock is from this machine's. What `timeSync` exists to correct |
| `sync_id`, `time_ms` | timeSync only: the sender's id and authoritative clock |

No `--ip` means every device; the usual forms narrow it. `--requests` keeps
what is sent *to* a device (`timeSync` and sensor frames), `--responses` only
beacons (sent *by* one). The rest of the options apply as-is:

```bash
pb snoop --udp                        # every beacon on the LAN
pb --ip bike2 snoop --udp             # one device's beacons and its timeSyncs
pb watch --udp --responses -g 1.230   # beacons from .230 only
pb snoop --udp -w beacons.pcapng      # save, then --read later
pb snoop --udp --jq '.skew_ms'        # just the clock drift
```

!!! tip "When `pb find` comes up empty"

    `pb snoop --udp` is the quickest way to tell whether beacons are on the
    wire at all. Two common reasons they are not: the device is a sync-group
    follower (followers stop beaconing — ask a leader for its peers instead),
    or another process already holds UDP:1889 on this machine.

The wire format is three or five little-endian 32-bit words; see the
[protocol notes](pixelblazeProtocol.md#network-discovery). tshark has no
dissector for it, so the pipeline pulls the raw bytes with `-e data.data` and
the jq program decodes them itself — `--dry-run` shows the helper functions.

## Sensor board frames (`--sensor`)

The same UDP port carries Sensor Expansion Board readings: a sync-group leader
broadcasts its board to the group, and `pb sensor sound` streams a host's
audio the same way. `--sensor` implies `--udp` and keeps only those frames:

```console
$ pb snoop --sensor
{"kind":"sensor","src":"192.168.1.67","dst":"192.168.1.86","sender_id":13683454,"sender_ms":2275967545,"expansion":1,"energy":0.0625,"max_mag":0.3052,"max_hz":1170,"accel":[0,0,0],"light":0.125,"analog":[0,0,0,0,0],"peak":0.003,"spectrum":"▁▁▁▁▁▁▂▃▄▄▅▆▇██████▇▆▅▄▄▃▂▁▁▁▁▁▁"}
```

| Field | Meaning |
|---|---|
| `sender_id`, `sender_ms` | Who sent the frame and when, by their own clock. Neither has to mean anything to the receiver |
| `expansion` | Expansion type; `1` is an SB1.0 sensor board, the only one defined |
| `energy` | `energyAverage` — overall loudness, 0.0-1.0 |
| `max_hz`, `max_mag` | `maxFrequency` in Hz, and its magnitude |
| `light`, `accel`, `analog` | The board's other readings, as the pattern sees them |
| `peak` | The loudest of the 32 bands, so the sparkline's scale is legible |
| `spectrum` | The 32 bands drawn as blocks, each scaled against `peak` — spectrum *shape*, readable however quiet the source is |
| `bins` | `--bare` only: the 32 bands as numbers |

```bash
pb snoop --sensor                      # is anything streaming, and what does it look like
pb snoop --sensor --bare               # the 32 bands as numbers
pb snoop --sensor --jq '.max_hz'       # just the dominant tone
pb --ip bike2 snoop --sensor           # only frames aimed at one device
```

!!! tip "When a sound-reactive pattern isn't reacting"

    `pb snoop --sensor` separates the two halves of the problem. Frames on the
    wire with a moving `spectrum` means the sending side is fine and the
    device is the issue — check that its sound source is *Prefer Remote*
    (`pb sensor sources`), and that the pattern was loaded *after* the frames
    started, because the firmware binds a pattern's sensor globals when the
    pattern loads. No frames at all means look at the sender.

The frame is 104 bytes: the 12-byte discovery header, an expansion type byte
and three of padding, then 44 little-endian 16-bit readings. See the
[protocol notes](pixelblazeProtocol.md#sensor-board-packet) for the layout and
the scaling.

## Saving and replaying

```bash
pb snoop -w capture.pcapng        # stream decoded output AND save raw packets
pb snoop --read capture.pcapng    # replay later; no capture permissions needed
```

A saved capture keeps the whole TCP stream including the handshake, so it
replays without `--midstream`.

!!! note

    `tshark` refuses a display filter while saving a live capture, so with
    `-w` the narrowing is done by the BPF capture filter and the rest moves
    into `jq`. The output is identical; the saved file is simply less
    aggressively filtered, which is what makes it replayable.

## Other options

```bash
pb snoop -i en0                   # pick the interface (default: routed to target)
pb snoop -p 81,80                 # extra ports to decode as websocket (--udp: default 1889)
pb snoop -c 200                   # stop after 200 packets (not frames)
pb snoop -d 30                    # stop after 30 seconds
pb snoop --color never            # or --no-color; honors NO_COLOR
pb snoop --sudo                   # run tshark under sudo
```

The interface is auto-detected from the kernel's route to the target, so AP
mode, a second adapter and loopback all work without `-i`.

## Escape hatch: `--dry-run`

Prints the exact pipeline and exits. Copy it, tweak it, run it yourself — this
is the way in to anything `pb snoop` does not expose directly.

```console
$ pb snoop --dry-run
tshark -i en0 -l -n -q -d tcp.port==81,http \
  -f 'tcp port 81 and host 192.168.1.230' \
  -Y 'websocket and (ip.src == 192.168.1.230 or ip.dst == 192.168.1.230)' \
  -T ek -e ip.src -e ip.dst -e tcp.srcport -e tcp.dstport \
        -e frame.time_epoch -e websocket.payload.text \
  | jq -c --unbuffered -C --argjson devs '["192.168.1.230"]' ... '<program>'
```

Two details in there are worth knowing if you write your own:

- **`-T ek`, not `-T fields`.** A single TCP packet can carry several websocket
  frames. `-T fields` comma-joins them into `{"fps":41},{"activeProgram":…}`,
  which is not valid JSON. `-T ek` keeps them as an array so each frame becomes
  its own line.
- **Direction belongs in `-Y`, never in `-f`.** Filtering one direction at
  capture time also drops the server's `101 Switching Protocols` reply, which is
  what primes the websocket dissector — you would get silence.

## Not yet covered

Binary websocket frames (preview pixels, pattern uploads) and plain HTTP on
port 80 are not decoded today. See the roadmap notes on the `cli-snoop`
branch.
