<!-- ==========================================================================
     DO NOT COMMIT / DO NOT MERGE — delete this whole block before this
     branch (cli-snoop) is merged anywhere. Scratch notes only.
     ========================================================================== -->

> # 🚧 DO NOT COMMIT — `pb snoop` needs revisiting
>
> **Delete this whole section before merging.** Notes-to-self on the `cli-snoop` branch.
>
> ### 1. The big one: we can only snoop OUR OWN traffic
>
> I built `--others` and `--any` assuming we could watch traffic between *any*
> two Pixelblazes on the LAN — e.g. a sync-group **leader talking to its
> followers**. That is basically **not possible** as written, and the options
> currently oversell it. A switch/AP only forwards a unicast frame to the port
> that owns the destination MAC, so this laptop never sees it.
>
> What actually works today:
>
> | Traffic | Snoopable? | Why |
> |---|---|---|
> | laptop ↔ Pixelblaze on the LAN | ✅ yes | we are an endpoint |
> | laptop ↔ emulator on localhost | ✅ yes | verified: auto-iface already resolves `127.0.0.1` → `lo0`. Still needs BPF perms, and the emulator may not be on port 81 (`-p`) |
> | anyone's **broadcast/multicast** | ✅ yes | flooded to every port — this is why UDP:1889 beacons work (see #2) |
> | Pixelblaze ↔ Pixelblaze unicast (leader/follower sync, `getPeers` peer-to-peer) | ❌ **no** | switched unicast, never reaches us |
>
> Escape hatches worth investigating before we either fix or de-scope this:
> - **WiFi monitor mode** — `tshark -I -i en0` + WPA2 decryption
>   (`-o wlan.enable_decryption:TRUE` and a `uat:80211_keys` `wpa-pwd` entry).
>   Needs the PSK *and* a captured 4-way handshake for each device, so devices
>   must be made to re-associate. Also kicks en0 off the network on macOS.
>   Verified the tshark flags exist; **not verified end to end.**
> - **Port mirroring / SPAN** on a managed switch.
> - **Make the laptop the AP** (macOS Internet Sharing, or join the Pixelblaze's
>   own SoftAP) so the traffic genuinely transits us.
>
> **TODO:** at minimum, warn in `--others`/`--any` help that widening the
> *filter* does not widen what the *interface can see*. Possibly add
> `--monitor`. Decide whether leader/follower snooping is in scope at all.
>
> ### 2. UDP beacons — ✅ done: `pb snoop --udp` (alias `--beacons`)
>
> These are **broadcast**, so unlike the above they are visible from anywhere on
> the LAN, including beacons from Pixelblazes we have never talked to. Great fit.
>
> - Went with option (a): a jq little-endian helper (`le32`, `ip4`, `wrap32`)
>   over `-e data.data`. ~6 lines of jq, no Lua to ship, everything still goes
>   through the one pipeline. `--dry-run` shows it.
> - `senderId` is **not a chipId** — it is the device's own IPv4 in byte order
>   (protocol doc example agrees; `PixelblazeEnumerator` just treats it as
>   opaque and echoes it in the timeSync). Emitted both raw and dotted.
> - Beacon lines carry `skew_ms` (device clock − capture clock, signed 32-bit),
>   which is the leader/follower drift signal. Sync jitter between devices is
>   readable straight off consecutive lines.
> - `--requests` = timeSync only, `--responses` = beacons only; `-w`/`--read`,
>   `-g`/`-v`, `-t`/`--full`/`--bare`, `--jq` all work unchanged.
> - **Discovered while building it:** sync-group *followers* do not beacon at
>   all (bike2 following an offline bike1 → zero packets on the LAN, `pb find`
>   empty while the web UI works fine). `pb find` needs a non-beacon fallback;
>   that work is on `cli-top`.
> - ~~Still unverified against live hardware from this machine~~ — verified
>   2026-09-09: real beacons and real sensor frames decode off `en0`.
>   The FIFO tests still cover the pipeline end to end on synthetic packets.
>
> ### 2b. Sensor board frames — ✅ done: `pb snoop --sensor`
>
> Same UDP:1889, packet type 50: a sync-group leader broadcasting its Sensor
> Expansion Board, or `pb sensor sound` (#30) streaming a host's audio.
>
> - `--sensor` implies `--udp` and filters to that one type. Frames are sent
>   *to* a device, so they land in the `--requests` bucket with timeSync.
> - Decoded with two more jq helpers, `le16`/`s16` — the body is 44 16-bit
>   readings, not 32-bit words like the beacon.
> - 32 floats a line at 40Hz is unreadable, so the default view carries a
>   `spectrum` sparkline (each band scaled against the frame's own peak, so
>   shape survives a quiet source) and `--bare` keeps the raw `bins`.
> - **Discovered while building it** (on #30, the sensor bridge): the firmware
>   binds a pattern's sensor globals when the *pattern* loads. Data arriving
>   for an already-running pattern is ignored. That is the first thing to
>   check when `--sensor` shows a healthy stream and the LEDs disagree.
>
> ### 3. Other power-user snooping to try
>
> - **Binary websocket frames** (opcode 2) — currently invisible; we only pull
>   `websocket.payload.text`. That hides preview pixel frames, pattern binary
>   uploads and `.epe` transfers. Add `--binary` emitting `{op, len, hex}`.
> - **HTTP on port 80** — pattern/file uploads, and the firmware `.stfu` POST to
>   `/update`. `-p 80` widens the capture today but the jq program still expects
>   websocket fields, so it decodes nothing useful. Needs its own mode.
> - **Emulator** — interface selection already works (`127.0.0.1` → `lo0`), but
>   it is untested against a real emulator, and the port is probably not 81.
>   Worth a `--local` shortcut and an examples entry once confirmed.
> - **Timing** — `--delta` (ms since previous frame) and request→response
>   round-trip pairing. jq `foreach` can carry the state.
> - **`--stats`** — frames/sec, bytes/sec, histogram of message keys, instead of
>   a raw stream. Either `tshark -z` or a jq `reduce`.
> - **ARP / DHCP / mDNS** — catch a Pixelblaze joining the network or changing
>   IP, which is the usual reason a cached address goes stale.
>
> ### 4. Windows — partly done, needs a real machine to finish
>
> Windows used to fall through to the Linux branch, so a Windows user missing
> `tshark` was told to run `sudo apt install`. **Fixed in this branch**, along
> with a guaranteed crash: `subprocess` rejects `preexec_fn` outright on
> Windows (`ValueError`), and we passed it unconditionally, so `pb snoop` died
> on the first call. Now dropped on `win32` — there is no SIGPIPE there anyway.
>
> Install hints now emitted (`choco` first, matching the ask):
>
> ```
> choco install wireshark jq
> winget install WiresharkFoundation.Wireshark ; winget install jqlang.jq
> scoop install wireshark jq
> ```
>
> **Still unverified — no Windows box to test on:**
>
> - **`tshark` is often not on PATH.** The installer drops it at
>   `C:\Program Files\Wireshark\tshark.exe`. `shutil.which('tshark')` then
>   fails even though Wireshark is installed, and we tell the user to install
>   something they already have. Should we probe the default install dir before
>   giving up? (Docs mention the path; the code does not look there.)
> - **Capture permissions are Npcap, not BPF.** `_can_capture()` returns `True`
>   for everything non-darwin, so there is no preflight at all on Windows. If
>   Npcap was installed with *Restrict to Administrators*, the user just gets
>   tshark's raw error. Is there a cheap way to detect that?
> - **`--sudo` is meaningless on Windows.** The permission text says so, but the
>   flag is still accepted and silently prepends a `sudo` that does not exist.
>   Hide it, or error, or map it to a UAC re-launch? (Note Windows 11 24H2 does
>   ship a real `sudo` — so maybe keep it and version-detect.)
> - **Interface auto-detection has no Windows path.** `route -n get` is macOS,
>   `ip route get` is Linux; Windows hits the `tshark -D` fallback, whose names
>   look like `\Device\NPF_{GUID}`. The `lo0`/`lo` loopback skip does not match
>   `\Device\NPF_Loopback`. tshark also accepts the interface *number*, which
>   may be the easier answer.
> - **`--dry-run` quoting is POSIX.** `shlex.join` produces single-quoted output
>   that cmd.exe and PowerShell will not take, so the copy-paste escape hatch is
>   broken on Windows exactly where people most need it.
>
> ### 5. Housekeeping
>
> - Live capture against real hardware is **untested** — no Pixelblaze was
>   reachable and sudo needed a password. The test suite substitutes a FIFO as
>   the capture interface, which covers `-i`, `-f`, `-w` and the process
>   plumbing but not an actual BPF device.
> - Power-user material is now written up in **`docs/snooping.md`** (added to
>   the mkdocs nav). The rest of the CLI — `pb top`, `pb find`, `pb pattern`,
>   everything from cli-2/cli-3 — still has **no page under `docs/`** at all,
>   only `examples/cli_examples.sh` and `--help`. That gap predates this branch
>   and is worth its own pass.

# pixelblaze-client
A Python library that presents a simple, synchronous interface for communicating with and
controlling one or more Pixelblaze LED controllers. 

## Requirements
- Python 3.9 or newer
- websocket-client (installable via `pip install websocket-client`, or from https://github.com/websocket-client/websocket-client)
- requests (installable via `pip install requests`, or from https://github.com/psf/requests)
- pytz (installable via `pip install pytz`, or from https://github.com/stub42/pytz)
- mini-racer (installable via `pip install mini-racer`

## Installation
Install pixelblaze-client with all required packages using pip:

```pip install pixelblaze-client```

Or, if you prefer, drop a copy of [pixelblaze.py](pixelblaze/pixelblaze.py) into your project directory and reference it within your project:

```from pixelblaze import *```

## <a name="documentation"></a>Documentation

API and other documention is available in [Markdown](docs/index.md) and [HTML](https://zranger1.github.io/pixelblaze-client/).

Sample code illustrating usage is provided in the [examples directory](examples/).

**Please note that version 1.0.0 was a major refactoring and enhancement of the library, with many new features and significant changes.** The API surface is completely new. See the the [API documentation](#documentation) for details.  

## Current Version [**v1.1.8**] - 2026-07-22

#### Fixed

* gh issue #28: Fixed a bug in the lightweight enumerator that caused it to fail to enumerate devices when called multiple times.  The enumerator now resets its internal list of seen devices each time it is called.

#### Added
* No new functionality in this release.

### Older Versions

See [CHANGELOG.md](CHANGELOG.md) for complete version history.

## Known Issues
- Check our github repo; if you find something, [let us know](/../../issues/new/choose)!
