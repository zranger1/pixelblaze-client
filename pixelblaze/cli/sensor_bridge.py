"""Virtual Pixelblaze Sensor Board — feed sensor-shaped readings into patterns.

The Pixelblaze Sensor Expansion Board publishes a specific set of pattern
globals (`frequencyData[32]`, `energyAverage`, `maxFrequency`,
`maxFrequencyMagnitude`). This module fills those same globals from
alternative host-side sources, so sound-reactive patterns work with no
physical SB attached.

Currently implemented: `SoundBridge` — captures audio from a system input
device (mic, loopback, etc.), computes 32 log-spaced frequency bins on the
same center-frequency grid the SB uses, and streams them to a Pixelblaze at
a configurable frame rate over one of two transports:

`UdpSink` (the default) sends the same UDP datagrams a sync-group leader
uses to share its sensor board with the group — see `SensorPacket` in
`pixelblaze.pixelblaze` for the wire format. The device does no JSON
parsing, so streaming costs it no pattern framerate, and a single broadcast
feeds every Pixelblaze on the network at once. Suggested by the library's
maintainer (zranger1) on PR #30, after his Java testbed for the same
protocol, https://github.com/zranger1/SoundServerFX.

The one catch, verified on firmware 3.70: the firmware binds a pattern's
sensor globals to their source when the *pattern* loads. A pattern that was
already running when the frames start arriving keeps simulating and ignores
them, which looks exactly like the packets being malformed. So the bridge
reloads the active pattern once the frames are flowing (`on_flowing`), which
is what SoundServerFX's README is getting at when it says to switch to the
audio-reactive pattern last. Nothing else is required — unicast or
broadcast, any `senderTime`, any source port, no sync group.

`VarsSink` sends the readings as pattern variables over the websocket with
`setActiveVariables`. It reaches a Pixelblaze whose sensor sources are
pinned to local, and it works on any pattern that exports the variables by
name whether or not it is a sensor board pattern — but the device parses
JSON on its render thread for every frame, which costs framerate on complex
patterns and gets worse on a marginal wifi link.

It also measures the input's loudness in LUFS (`loudness.py`) and watches for
the two things a spectrum cannot show you: digital silence, and an input that
opens and then delivers nothing at all. `spectrum.py` draws both, live.

The audio can come from a file instead of a device: `Playlist` holds the tracks
`--file` named and decodes them one at a time, and `FileSource` plays them in
real time while being steered -- paused, seeked, moved between tracks -- from
the keyboard (`keys.py` reads it, `controls.py` decides what a key means). The
same keys turn the gain, AGC, gate and log scaling of a live capture, because
those are settings you cannot pick in advance: the right gain depends on the
room, the source and the pattern, and the way to find it is to watch the lights
while you turn it.

Both transports carry the same reading contract:
  frequencyData: [32 floats]  # magnitudes, nominally 0.0-1.0
  energyAverage: float        # overall loudness, nominally 0.0-1.0
  maxFrequency: float         # Hz
  maxFrequencyMagnitude: float

Notes on the vars transport, verified on firmware 3.51 and 3.70 (the same
device, before and after upgrading, 2026-09-08): arrays must be sent whole.
`{"setVars": {"frequencyData": [..32..]}}` lands in the pattern, while the
indexed form `{"setVars": {"frequencyData[3]": v}}` is silently dropped on
both — `light` flips to 0, the bins never move, and the pattern's last
simulated frame sits there frozen. (`getVars` returns arrays whole too.)
The UDP transport has no such wrinkle; it carries the whole frame always.
"""

import contextlib
import threading
import time

import numpy as np

from pixelblaze.cli.loudness import SILENT, LoudnessMeter
from pixelblaze.pixelblaze import SensorPacket, SensorSender

# `sounddevice` is imported where it is used, not here: it needs PortAudio, and
# `--tone` is a complete run of this whole module without either. A box with no
# sound stack at all can still exercise the bridge, the meter and the display.

# PB sensor board bin center frequencies (from stock pattern source)
PB_BIN_CENTERS = np.array([
    37.5, 50, 75, 100, 125, 163, 195, 234, 312, 391, 469, 586,
    703, 859, 976, 1170, 1370, 1560, 1800, 2070, 2380, 2730,
    3120, 3590, 4100, 4650, 5310, 6020, 6840, 7770, 8790, 9960
])

# Bin edges (geometric mean between adjacent centers)
PB_BIN_EDGES = np.zeros(33)
PB_BIN_EDGES[0] = PB_BIN_CENTERS[0] / (PB_BIN_CENTERS[1] / PB_BIN_CENTERS[0]) ** 0.5
for i in range(31):
    PB_BIN_EDGES[i + 1] = (PB_BIN_CENTERS[i] * PB_BIN_CENTERS[i + 1]) ** 0.5
PB_BIN_EDGES[32] = PB_BIN_CENTERS[31] * (PB_BIN_CENTERS[31] / PB_BIN_CENTERS[30]) ** 0.5


def find_device(name_substring: str) -> tuple[int, dict]:
    """Find an input device by name substring."""
    import sounddevice as sd
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if name_substring.lower() in dev['name'].lower() and dev['max_input_channels'] > 0:
            return i, dev
    raise RuntimeError(
        f"No input device matching '{name_substring}'. Available:\n" +
        "\n".join(f"  [{i}] {d['name']} (in={d['max_input_channels']})"
                  for i, d in enumerate(devices) if d['max_input_channels'] > 0)
    )


def fft_to_pb_bins(samples: np.ndarray, sample_rate: int,
                   gain: float = 1.0, noise_gate: float = 0.0) -> dict:
    """Convert audio samples to PB sensor board format.

    Args:
        samples: Raw audio samples (float32, mono or multi-channel)
        sample_rate: Sample rate in Hz
        gain: Linear gain multiplier applied to spectrum magnitudes
        noise_gate: Values below this threshold are zeroed

    Returns dict with keys matching PB export vars:
        frequencyData: list of 32 floats
        energyAverage: float
        maxFrequency: float (Hz)
        maxFrequencyMagnitude: float
    """
    # Mono mixdown
    if samples.ndim > 1:
        samples = samples.mean(axis=1)

    n = len(samples)

    # Hann window + FFT
    window = np.hanning(n)
    spectrum = np.abs(np.fft.rfft(samples * window)) / n
    freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)

    # Apply gain
    spectrum *= gain

    # Noise gate
    if noise_gate > 0:
        spectrum[spectrum < noise_gate] = 0

    # Bin into 32 PB bins.
    #
    # The low bands are narrower than the FFT's resolution: at the default
    # 1024 samples / 48kHz the bins are 46.9Hz apart, while band 0 spans
    # 32.5-43.3Hz and band 2 spans 61.2-86.6Hz — neither contains an FFT bin
    # at all, so both used to read a flat 0 forever and the bass end of every
    # spectrum pattern was dead. Interpolate the spectrum at the band's center
    # frequency when that happens. (The real sensor board solves this with a
    # second, downsampled 400Hz FFT for its low six bands.)
    bins = np.zeros(32)
    for b in range(32):
        lo = PB_BIN_EDGES[b]
        hi = PB_BIN_EDGES[b + 1]
        mask = (freqs >= lo) & (freqs < hi)
        if mask.any():
            bins[b] = spectrum[mask].mean()
        else:
            bins[b] = np.interp(PB_BIN_CENTERS[b], freqs, spectrum)

    # Aggregate metrics. The peak search starts above the lowest band edge:
    # DC and sub-audio rumble otherwise win it outright on most inputs (a mic
    # with any DC offset pins maxFrequency to 0Hz), which is why the sensor
    # board's own firmware starts its search at bin 1 rather than bin 0.
    energy_avg = float(spectrum.mean())
    audible = freqs >= PB_BIN_EDGES[0]
    peak_idx = int(np.argmax(np.where(audible, spectrum, 0.0)))
    max_freq = float(freqs[peak_idx])
    max_freq_mag = float(spectrum[peak_idx])

    return {
        "frequencyData": bins.tolist(),
        "energyAverage": energy_avg,
        "maxFrequency": max_freq,
        "maxFrequencyMagnitude": max_freq_mag,
    }


class VarsSink:
    """Sends sensor readings as pattern variables over the websocket.

    The original transport for this bridge, kept as an alternative to
    `UdpSink`: it reaches a Pixelblaze whose sensor sources are pinned to
    local, and it works with any pattern that exports the variables by name.
    The cost is that the device parses a JSON frame on its render thread every
    time, which shows up as lost framerate on complex patterns.
    """

    def __init__(self, pb):
        self.pb = pb

    targets = None
    """One websocket, so there is no address list for the display to count."""

    def describe(self) -> str:
        return f"setVars over websocket → {self.pb.ipAddress}"

    def start(self):
        # Signal to PB patterns that real sensor data is available
        self.pb.setActiveVariables({"light": 0})

    def send(self, data: dict):
        # frequencyData goes as one array: firmware applies whole arrays and
        # silently ignores "frequencyData[i]" keys (see module docstring).
        # Round to 6 decimals — finer than the device's 16.16 fixed point, a
        # third the JSON of a full double at `fps` frames per second.
        self.pb.setActiveVariables({
            "frequencyData": [round(v, 6) for v in data["frequencyData"]],
            "energyAverage": round(data["energyAverage"], 6),
            "maxFrequency": round(data["maxFrequency"], 6),
            "maxFrequencyMagnitude": round(data["maxFrequencyMagnitude"], 6),
            "light": 0,
        })

    def stop(self):
        # Reset sentinels so patterns know sensor data stopped and go back to
        # simulating sound. Nothing expires a variable we set, so we must.
        self.pb.setActiveVariables({
            "light": -1,
            "maxFrequencyMagnitude": -1,
            "energyAverage": -1,
        })


class UdpSink:
    """Sends sensor readings as sensor-board UDP datagrams (the default transport).

    This is the protocol a Pixelblaze sync group leader uses to share its own
    Sensor Expansion Board with the rest of the group, so the readings arrive
    the way the firmware already expects them: no JSON, no websocket, no
    parsing on the render thread, and one broadcast feeds every Pixelblaze on
    the network at once.

    A Pixelblaze only uses the readings if its source preference for them is
    "prefer remote" (`pb sensor sources --prefer remote`), or if it has no
    local sensor board to prefer — and if its pattern was loaded *after* the
    frames started arriving, which is what `--rebind` takes care of.
    """

    SILENCE_FRAMES = 3

    def __init__(self, targets, senderId: int = None):
        self.sender = SensorSender(targets, senderId=senderId)

    @property
    def targets(self) -> list:
        """The addresses frames are going to, live: `add_target` while running."""
        return self.sender.targets

    def add_target(self, address: str) -> bool:
        """Start sending to one more device. True if it wasn't already a target."""
        if address in self.sender.targets:
            return False
        self.sender.targets.append(address)
        return True

    def remove_target(self, address: str) -> bool:
        """Stop sending to a device, after a frame of silence so its pattern
        doesn't latch whatever was playing (see `stop`)."""
        if address not in self.sender.targets:
            return False
        for _ in range(self.SILENCE_FRAMES):
            self.sender.socket.sendto(SensorPacket.pack(senderId=self.sender.senderId),
                                      (address, self.sender.port))
        self.sender.targets.remove(address)
        return True

    def describe(self) -> str:
        targets = self.sender.targets
        shown = ', '.join(targets[:4]) + (f", +{len(targets) - 4} more" if len(targets) > 4 else "")
        return (f"sensor board UDP → {len(targets)} device(s) on :{self.sender.port} "
                f"({shown})")

    def start(self):
        pass

    def send(self, data: dict):
        self.sender.send(
            frequencyData=data["frequencyData"],
            energyAverage=data["energyAverage"],
            maxFrequency=data["maxFrequency"],
            maxFrequencyMagnitude=data["maxFrequencyMagnitude"],
        )

    def stop(self):
        # A pattern bound to remote sensor data keeps the last frame it was
        # sent — on 3.70 it was still showing it 100s after the stream stopped,
        # and reloading the pattern doesn't put it back to simulating either.
        # So say "silence" on the way out instead of freezing mid-spectrum.
        # Repeated because this is UDP and the last packet may not arrive.
        for _ in range(self.SILENCE_FRAMES):
            self.sender.send()
        self.sender.close()




# ── playing a file, and hearing what is being sent ──────────────────────────

def parse_time(value) -> float:
    """Seconds, or `m:ss` / `h:mm:ss`, as seconds."""
    if value is None:
        return None
    text = str(value).strip()
    try:
        parts = [float(p) for p in text.split(':')]
    except ValueError:
        raise ValueError(f"{text!r} is not a time: use seconds (12.5) or m:ss / h:mm:ss")
    if not 1 <= len(parts) <= 3 or any(p < 0 for p in parts):
        raise ValueError(f"{text!r} is not a time: use seconds (12.5) or m:ss / h:mm:ss")
    total = 0.0
    for part in parts:
        total = total * 60 + part
    return total


#: What counts as a track when `--file` names a directory. ffmpeg will read
#: more than this; the list is only here to decide what to pick up off a folder
#: without trying to decode its cover art and its .cue sheet.
AUDIO_SUFFIXES = ('.wav', '.mp3', '.m4a', '.aac', '.flac', '.ogg', '.oga', '.opus',
                  '.aif', '.aiff', '.alac', '.wma', '.caf', '.mp4', '.m4b', '.webm')


def expand_tracks(spec) -> list:
    """The files `--file` named: a comma-separated list, with any directory in
    it replaced by the audio files directly inside it, in name order.

    A spec that is itself an existing file is taken whole and never split, so a
    track called `Hello, Goodbye.mp3` works; a list of them cannot contain a
    comma, which is the same trade `pb playlist set` makes.
    """
    import pathlib as _pathlib

    text = str(spec).strip()
    if not text:
        raise RuntimeError("--file needs a path (or several, comma-separated)")
    whole = _pathlib.Path(text).expanduser()
    parts = [text] if whole.is_file() else [p.strip() for p in text.split(',')]

    tracks = []
    for part in parts:
        if not part:
            continue
        path = _pathlib.Path(part).expanduser()
        if path.is_dir():
            found = sorted(child for child in path.iterdir()
                           if child.is_file() and child.suffix.lower() in AUDIO_SUFFIXES)
            if not found:
                raise RuntimeError(f"no audio files in {path}")
            tracks += found
        elif path.is_file():
            tracks.append(path)
        else:
            raise RuntimeError(f"no such file: {part}")
    if not tracks:
        raise RuntimeError(f"--file {spec!r} named nothing to play")
    return tracks


def _ffmpeg(*args) -> bytes:
    """Run an ffmpeg-family tool, raising its own error text rather than a
    return code nobody can act on."""
    import subprocess
    try:
        done = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        raise RuntimeError(f"{args[0]} is not installed")
    if done.returncode != 0:
        detail = done.stderr.decode('utf-8', 'replace').strip().splitlines()
        raise RuntimeError(detail[-1] if detail else f"{args[0]} failed ({done.returncode})")
    return done.stdout


def decode_audio(path, start: float = None, end: float = None,
                 sample_rate: int = None, channels: int = 2):
    """Decode a file (or a section of one) to (frames, channels) float32.

    ffmpeg if it is installed -- it reads anything, seeks, and resamples.
    Otherwise the stdlib `wave` module, which is PCM WAV only and cannot
    resample, so the file's own rate is what you get.

    The section is decoded into memory rather than streamed, because looping it
    has to be gapless: this is for beaming a passage at an installation over and
    over, and a hitch at the seam is the thing you would notice. A whole track is
    a few tens of MB at 48 kHz stereo; that is the cost of the seam being clean.

    Returns (samples, sample_rate).
    """
    import pathlib as _pathlib

    path = str(path)
    if not _pathlib.Path(path).is_file():
        raise RuntimeError(f"no such file: {path}")
    if start is not None and end is not None and end <= start:
        raise RuntimeError(f"--to ({end:g}s) must come after --from ({start:g}s)")

    try:
        rate = sample_rate or _probe_sample_rate(path)
        args = ['ffmpeg', '-v', 'error', '-nostdin']
        if start:
            args += ['-ss', f"{start:.6f}"]
        if end is not None:
            args += ['-t', f"{end - (start or 0):.6f}"]
        args += ['-i', path, '-f', 'f32le', '-ac', str(channels), '-ar', str(rate), '-']
        raw = _ffmpeg(*args)
    except RuntimeError as e:
        if 'not installed' not in str(e):
            raise RuntimeError(f"could not decode {path}: {e}")
        samples, rate = _decode_wav(path, start, end)
        if sample_rate and sample_rate != rate:
            raise RuntimeError(
                f"{path} is {rate} Hz and --sample-rate says {sample_rate}; "
                f"install ffmpeg to resample")
        return samples, rate

    samples = np.frombuffer(raw, dtype='<f4')
    if samples.size == 0:
        raise RuntimeError(f"{path} decoded to no audio"
                           + (" in that --from/--to range" if start or end else ""))
    return samples.reshape(-1, channels).copy(), rate


def _probe_sample_rate(path: str) -> int:
    """The file's own rate, so nothing is resampled unless asked."""
    out = _ffmpeg('ffprobe', '-v', 'error', '-select_streams', 'a:0',
                  '-show_entries', 'stream=sample_rate', '-of', 'csv=p=0', path)
    try:
        return int(out.decode().strip().splitlines()[0])
    except (ValueError, IndexError):
        raise RuntimeError(f"{path} has no audio stream")


def _decode_wav(path: str, start: float = None, end: float = None):
    """The no-ffmpeg fallback: PCM WAV, at whatever rate it already is."""
    import wave

    try:
        with wave.open(path, 'rb') as wav:
            rate, width, channels = wav.getframerate(), wav.getsampwidth(), wav.getnchannels()
            frames = wav.readframes(wav.getnframes())
    except wave.Error as e:
        raise RuntimeError(f"could not decode {path}: {e}. Install ffmpeg to read "
                           f"anything other than PCM WAV.")
    dtype = {1: np.uint8, 2: '<i2', 4: '<i4'}.get(width)
    if dtype is None:
        raise RuntimeError(f"{path} is {width * 8}-bit WAV; install ffmpeg to read it")
    data = np.frombuffer(frames, dtype=dtype).reshape(-1, channels).astype(np.float32)
    data = (data - 128) / 128 if width == 1 else data / float(1 << (width * 8 - 1))
    lo = int((start or 0) * rate)
    hi = int(end * rate) if end is not None else len(data)
    return data[lo:hi].copy(), rate


class Playlist:
    """The tracks `--file` named, decoded one at a time.

    Decoding is lazy because a decoded track is tens of megabytes (see
    `decode_audio`) and a playlist can be a folder. One track is in memory, the
    next one is fetched in the background so that pressing "next" on a set is
    silent rather than a pause while ffmpeg runs, and nothing else is kept.

    A track that will not decode does not end the run: it is reported and
    skipped, because losing a set because track 9 of 40 is a corrupt download
    is not a trade anybody would choose. All of them failing does end it.
    """

    def __init__(self, tracks, decode, on_error=None):
        self.tracks = list(tracks)
        self.decode = decode
        self.on_error = on_error
        self.index = 0
        self._cache = {}
        self._lock = threading.Lock()
        self._prefetching = set()

    @property
    def count(self) -> int:
        return len(self.tracks)

    @property
    def track(self):
        return self.tracks[self.index]

    @property
    def title(self) -> str:
        return str(self.tracks[self.index])

    def seed(self, index: int, samples):
        """Hand over a track that has already been decoded -- the first one is,
        before the run starts, so that a file that cannot be read fails the
        command rather than the playlist."""
        with self._lock:
            self._cache[index] = samples

    def load(self, index: int = None):
        """The samples for a track, decoding it if it isn't already in hand."""
        index = self.index if index is None else index
        with self._lock:
            cached = self._cache.get(index)
        if cached is not None:
            return cached
        samples = self.decode(self.tracks[index])
        with self._lock:
            self._cache[index] = samples
        return samples

    def select(self, index: int):
        """Move to a track, decoding it. Returns its samples, or None if every
        track from here on refuses to decode."""
        if not self.count:
            return None
        attempts = 0
        while attempts < self.count:
            index %= self.count
            try:
                samples = self.load(index)
            except Exception as e:
                if self.on_error is not None:
                    self.on_error(self.tracks[index], e)
                index, attempts = index + 1, attempts + 1
                continue
            self.index = index
            self._evict()
            self._prefetch(index + 1)
            return samples
        return None

    def move(self, delta: int):
        """Step `delta` tracks, wrapping. Returns the new track's samples."""
        return self.select(self.index + delta)

    def _evict(self):
        """Hold the current track and the one being fetched ahead of it; a
        decoded track is far too big to keep a history of."""
        keep = {self.index, (self.index + 1) % self.count} | self._prefetching
        with self._lock:
            for index in [i for i in self._cache if i not in keep]:
                del self._cache[index]

    def _prefetch(self, index: int):
        if self.count < 2:
            return
        index %= self.count
        with self._lock:
            if index in self._cache or index in self._prefetching:
                return
            self._prefetching.add(index)

        def fetch():
            try:
                self.load(index)
            except Exception:
                # Reported when it is actually needed, not from a thread
                # nobody asked to hear from.
                pass
            finally:
                with self._lock:
                    self._prefetching.discard(index)

        threading.Thread(target=fetch, name='pb-prefetch', daemon=True).start()


class Transport:
    """What the file source is doing, for the display to draw. Plain attributes
    rather than a dataclass so a display can read whatever it likes."""

    def __init__(self, paused, title, index, count, position, duration, loop):
        self.paused = paused
        self.title = title
        self.index = index
        self.count = count
        self.position = position
        self.duration = duration
        self.loop = loop


class FileSource:
    """Decoded audio, delivered in real time, looping -- and steerable while it
    runs: pause, seek, and move between the tracks of a `Playlist`.

    Real time on purpose: the point is to beam a track at an installation as it
    plays, so the blocks arrive at the rate they would from a capture and every
    meter, silence check and stall check downstream behaves identically.

    That is also why pausing keeps delivering blocks, of digital silence, at
    exactly the same rate. Stopping the blocks instead would trip the bridge's
    stall watchdog after three seconds, starve the monitor's output stream, and
    leave every pattern latched on the last frame it was sent -- a paused track
    with the lights frozen mid-spectrum. Silence is both true and what a pattern
    should do about it.

    Every control is a request that the playing thread picks up at the next
    block boundary, so the cursor is only ever moved by one thread.
    """

    def __init__(self, samples, sample_rate: int, block_size: int, callback,
                 loop: bool = True, on_end=None, playlist=None, on_track=None):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.callback = callback
        self.loop = loop
        self.on_end = on_end
        #: Called with (title, index, count) when the track changes.
        self.on_track = on_track
        self.playlist = playlist if playlist is not None else Playlist(
            [''], decode=lambda _track: samples)
        self.samples = samples if samples is not None else self.playlist.load()
        self.paused = False
        self.finished = False
        #: True while a track is being decoded, which happens on this thread
        #: and stops blocks arriving. The bridge watches it, because otherwise
        #: a slow decode looks exactly like an input that has died.
        self.switching = False

        self._pos = 0
        self._seek_to = None
        self._move_by = 0
        self._running = False
        self._thread = None

    # -- what it is doing ---------------------------------------------------

    @property
    def duration(self) -> float:
        """Of the track playing now."""
        return len(self.samples) / float(self.sample_rate)

    @property
    def position(self) -> float:
        return self._pos / float(self.sample_rate)

    @property
    def title(self) -> str:
        return self.playlist.title

    def state(self) -> Transport:
        return Transport(paused=self.paused, title=self.title,
                         index=self.playlist.index, count=self.playlist.count,
                         position=self.position, duration=self.duration,
                         loop=self.loop)

    # -- steering it (from any thread) --------------------------------------

    def toggle_pause(self) -> bool:
        self.paused = not self.paused
        return self.paused

    def seek(self, delta: float):
        """Move `delta` seconds from where the cursor is now."""
        base = self._seek_to if self._seek_to is not None else self.position
        self._seek_to = max(0.0, base + delta)

    def seek_to(self, seconds: float):
        self._seek_to = max(0.0, seconds)

    def move_track(self, delta: int):
        self._move_by += delta

    # -- playing it ---------------------------------------------------------

    def __enter__(self):
        self._running = True
        self._thread = threading.Thread(target=self._play, name='pb-file', daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        return False

    def _play(self):
        period = self.block_size / self.sample_rate
        due = time.monotonic()
        while self._running:
            block = self._next_block()
            if block is not None and len(block):
                self.callback(block, len(block), None, None)
            if self.finished:
                self._running = False
                break
            due += period
            time.sleep(max(0.0, due - time.monotonic()))
        if self.finished and self.on_end is not None:
            self.on_end()

    def _silence(self):
        """Shaped exactly like a real block, so nothing downstream can tell the
        difference between a paused track and a quiet one."""
        if self.samples.ndim == 1:
            return np.zeros(self.block_size, dtype=np.float32)
        return np.zeros((self.block_size, self.samples.shape[1]), dtype=np.float32)

    def _next_block(self):
        """One block of audio, and everything asked of the transport since the
        last one. Only ever called from the playing thread."""
        if self._move_by:
            delta, self._move_by = self._move_by, 0
            self._switch(delta)
        if self._seek_to is not None:
            target, self._seek_to = self._seek_to, None
            self._pos = min(len(self.samples), int(target * self.sample_rate))

        if self.paused:
            return self._silence()

        samples = self.samples
        total = len(samples)
        if total == 0:
            return self._silence()

        pos = min(self._pos, total)
        end = pos + self.block_size
        if end < total:
            self._pos = end
            return samples[pos:end]

        # The last block of this track. One track on a loop wraps *inside* the
        # block, so the seam is a sample boundary rather than a gap however long
        # a restart takes -- this is meant for beaming a passage at an
        # installation over and over, and a hitch at the seam is the thing you
        # would notice.
        if self.loop and self.playlist.count == 1:
            block = (np.concatenate([samples[pos:], samples[:end - total]])
                     if end > total else samples[pos:end])
            self._pos = end - total if end > total else 0
            return block

        block = samples[pos:end]
        if self.playlist.count > 1 and (self.loop or self.playlist.index < self.playlist.count - 1):
            self._switch(1)
        else:
            self.finished = True
        return block

    def _switch(self, delta: int):
        """Change track. A playlist that cannot decode any of them is the end
        of the run -- `finished`, which the bridge treats as the file ending."""
        if self.playlist.count < 2:
            self._pos = 0
            return
        self.switching = True
        try:
            samples = self.playlist.move(delta)
        finally:
            self.switching = False
        if samples is None:
            self.finished = True
            return
        self.samples = samples
        self._pos = 0
        if self.on_track is not None:
            self.on_track(self.playlist.title, self.playlist.index, self.playlist.count)


class Monitor:
    """Play what is being sent out of an output device, so you can hear it.

    A queue and a writer thread, never a blocking write from inside the audio
    callback: a monitor that stalls the capture costs frames, and the frames are
    the whole point. A full queue drops blocks and counts them instead of
    backing up -- audio you cannot keep up with is better late-free than
    in sync.
    """

    #: Blocks of slack before dropping. At 1024/48 kHz that is about 85 ms.
    DEPTH = 4

    def __init__(self, device, sample_rate: int, channels: int):
        self.device = device
        self.sample_rate = sample_rate
        self.channels = channels
        self.dropped = 0
        #: Silence the speakers without touching what is sent to the lights.
        #: Zeroes rather than nothing: an output stream with no blocks coming
        #: underruns, and an underrun clicks.
        self.muted = False
        self._queue = None
        self._stream = None
        self._thread = None
        self._running = False

    def __enter__(self):
        import queue

        import sounddevice as sd
        self._queue = queue.Queue(maxsize=self.DEPTH)
        self._stream = sd.OutputStream(samplerate=self.sample_rate, device=self.device,
                                       channels=self.channels, dtype='float32')
        self._stream.start()
        self._running = True
        self._thread = threading.Thread(target=self._pump, name='pb-monitor', daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
        return False

    def write(self, block):
        """From the audio callback. Never blocks."""
        import queue
        if not self._running:
            return
        if block.ndim == 1:
            block = block[:, None]
        if block.shape[1] != self.channels:
            # Mix down (or fan out) to what the output device took.
            block = (block.mean(axis=1, keepdims=True) if block.shape[1] > self.channels
                     else np.repeat(block[:, :1], self.channels, axis=1))
        if self.muted:
            block = np.zeros_like(block)
        try:
            self._queue.put_nowait(np.ascontiguousarray(block, dtype=np.float32))
        except queue.Full:
            self.dropped += 1

    def _pump(self):
        import queue
        while self._running:
            try:
                block = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._stream.write(block)
            except Exception:
                return


# ── which output device to monitor on, and whether to at all ───────────────
#
# The interesting case is the one you cannot see from inside the process. On a
# Mac the normal loopback setup is: an aggregate / multi-output device that
# feeds BOTH a virtual device (BlackHole) and the speakers, selected as the
# system output, with this bridge capturing the virtual device. The audio is
# already reaching the speakers that way, so playing it again here would double
# it. Every other arrangement -- a microphone, a line input, a file we are
# beaming -- wants a monitor.
#
# Nothing in a portable audio API reports "this output routes through that
# input", so the default is a GUESS, said out loud, and --mix / --no-mix
# settles it. It is never silently wrong: the reason is logged either way.

#: Inputs that are something else's output coming back around.
LOOPBACK_HINTS = ('blackhole', 'loopback', 'soundflower', 'vb-audio', 'vb-cable',
                  'voicemeeter', 'virtual', 'stereo mix', 'what u hear', 'monitor')


def is_loopback_name(name: str) -> bool:
    """Does this input device look like a loopback rather than a microphone?"""
    lowered = (name or '').lower()
    return any(hint in lowered for hint in LOOPBACK_HINTS)


def find_output_device(query=None):
    """An output device by index, name fragment, or None for the OS default.

    Returns (index, info). The index is None when the default is wanted and
    sounddevice's default is fine to leave unset.
    """
    import sounddevice as sd

    devices = sd.query_devices()
    if query in (None, ''):
        index = sd.default.device[1]
        if index is None or index < 0:
            raise RuntimeError("this machine has no default output device")
        return index, devices[index]

    try:
        index = int(query)
    except (TypeError, ValueError):
        pass
    else:
        if not 0 <= index < len(devices) or devices[index]['max_output_channels'] < 1:
            raise RuntimeError(f"device {index} is not an output")
        return index, devices[index]

    lowered = str(query).lower()
    for index, device in enumerate(devices):
        if lowered in device['name'].lower() and device['max_output_channels'] > 0:
            return index, device
    available = "\n".join(f"  [{i}] {d['name']}" for i, d in enumerate(devices)
                          if d['max_output_channels'] > 0)
    raise RuntimeError(f"no output device matching '{query}'. Available:\n{available}")


def _describes_an_aggregate(name: str) -> bool:
    """macOS only: ask the system whether this device is an aggregate or
    multi-output. Anything unexpected -- another OS, no tool, new JSON -- is
    False, and the name heuristic below gets the question instead."""
    import json
    import subprocess
    import sys as _sys

    if _sys.platform != 'darwin' or not name:
        return False
    try:
        raw = subprocess.run(['system_profiler', 'SPAudioDataType', '-json'],
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=10).stdout
        report = json.loads(raw or b'{}')
    except Exception:
        return False

    def walk(node):
        if isinstance(node, dict):
            if str(node.get('_name', '')).strip() == name.strip():
                yield ' '.join(str(v) for v in node.values() if isinstance(v, str)).lower()
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    return any('aggregate' in facts or 'multi-output' in facts or 'multioutput' in facts
               for facts in walk(report))


def _name_suggests_routing(input_name: str, output_name: str) -> bool:
    """Does the OUTPUT's name say it carries this input?

    People name these things after what is in them -- an aggregate of BlackHole
    and the speakers gets called "BH Speakers" or "BlackHole + Speakers". So:
    a shared word of four characters or more, or the input's initials as a word
    of the output's name ("BlackHole" -> "bh").
    """
    import re as _re

    output = (output_name or '').lower()
    input_words = _re.findall(r'[a-z]{4,}', (input_name or '').lower())
    if any(word in output for word in input_words):
        return True
    output_words = set(_re.findall(r'[a-z0-9]+', output))
    initials = ''.join(part[0] for part in _re.findall(r'[A-Z][a-z]*', input_name or '')).lower()
    return len(initials) >= 2 and initials in output_words


def choose_monitor(mix, no_mix: bool, input_name: str, is_capture: bool,
                   is_tone: bool = False):
    """Which output device to play through, and why. Returns (device, reason).

    `device` is None for "don't". See the note at the top of this section --
    the no-flags answer is a guess, and the reason is meant to be printed.
    """
    if no_mix:
        return None, "--no-mix"
    if mix:
        index, info = find_output_device(mix)
        return index, f"{info['name']} (--mix {mix})"
    if mix == '':                      # bare --mix: the OS default, no guessing
        index, info = find_output_device(None)
        return index, f"{info['name']} (--mix, the default output)"
    if is_tone:
        return None, "a generated tone is a test signal, not something to play"

    try:
        index, info = find_output_device(None)
    except Exception as e:
        return None, f"no monitor: {e}"

    if is_capture and is_loopback_name(input_name):
        if _describes_an_aggregate(info['name']):
            return None, (f"{info['name']} is an aggregate/multi-output device, so it "
                          f"already carries {input_name} to your speakers (--mix to "
                          f"play it again anyway)")
        if _name_suggests_routing(input_name, info['name']):
            return None, (f"{info['name']} looks like it already carries {input_name} "
                          f"to your speakers — guessing from the name (--mix to play "
                          f"it anyway, --no-mix to make this certain)")

    return index, f"{info['name']} (the default output)"


class MicSource:
    """A capture from a system input device, as a context manager."""

    def __init__(self, device_idx: int, sample_rate: int, block_size: int,
                 channels: int, callback):
        self.device_idx = device_idx
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self.callback = callback
        self._stream = None

    def __enter__(self):
        import sounddevice as sd
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            device=self.device_idx,
            channels=self.channels,
            dtype='float32',
            callback=self.callback,
        )
        self._stream.__enter__()
        return self

    def __exit__(self, *exc):
        return self._stream.__exit__(*exc)


class ToneSource:
    """A generated sine instead of a capture.

    No device, no permission prompt, and no PortAudio -- which makes it the one
    way to exercise this whole module (bins, loudness, display, datagrams) on a
    box with no sound stack at all, and a known-good signal to point a
    Pixelblaze at when the question is whether the *device* is listening.
    """

    def __init__(self, hz: float, sample_rate: int, block_size: int,
                 channels: int, callback, amplitude: float = 0.25):
        self.hz = hz
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.channels = channels
        self.callback = callback
        self.amplitude = amplitude
        self._phase = 0.0
        self._running = False
        self._thread = None

    def __enter__(self):
        self._running = True
        self._thread = threading.Thread(target=self._generate, name='pb-tone', daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        return False

    def _generate(self):
        period = self.block_size / self.sample_rate
        step = 2 * np.pi * self.hz / self.sample_rate
        due = time.monotonic()
        while self._running:
            phases = self._phase + step * np.arange(self.block_size)
            self._phase = float((phases[-1] + step) % (2 * np.pi))
            block = (self.amplitude * np.sin(phases)).astype(np.float32)
            block = np.repeat(block[:, None], self.channels, axis=1)
            self.callback(block, self.block_size, None, None)
            due += period
            time.sleep(max(0.0, due - time.monotonic()))


class SoundBridge:
    """Captures audio and pushes FFT results to a Pixelblaze through a transport sink.

    Two things here are not about the spectrum at all, and both exist because
    the failure they catch is otherwise indistinguishable from a quiet room:

    **Silence** is the input delivering blocks of digital zeroes. That is not an
    error -- it is what a loopback with nothing playing sounds like, and it is
    the truth about the room, so it is sent. It is reported (`display.silent`)
    because "is anything playing?" is the first question when the lights don't
    move.

    **A stall** is no blocks arriving at all for `stall_timeout` seconds while
    the stream is nominally running: an aggregate device with a missing member,
    an interface unplugged mid-stream, an input another app holds exclusively.
    Nothing goes out, the pattern sits on its last frame, and the device side
    cannot see the difference. So `run()` stops and leaves `stalled_for` set,
    and the CLI fails loudly rather than sitting there looking busy.
    """

    #: The longest the run loop will sleep. It wakes sooner when the next frame
    #: is due; this bounds how late the display's 30 fps and the stall watchdog
    #: can be when the frame rate itself is slow.
    TICK = 1.0 / 60

    def __init__(self, sink, device_idx: int, sample_rate: int, block_size: int,
                 fps: int, gain: float = 1.0, noise_gate: float = 0.0,
                 log_scale: bool = False, agc: bool = False, on_flowing=None,
                 display=None, seconds: float = None, channels: int = 1,
                 tone: float = None, samples=None, loop: bool = True,
                 monitor=None, stall_timeout: float = 3.0,
                 silence_timeout: float = 2.0, playlist=None, controls=None):
        self.sink = sink
        # Called once, after a few frames have gone out. The UDP transport
        # needs this: a Pixelblaze binds a pattern's sensor globals when the
        # pattern loads, so the pattern has to be reloaded once data is
        # actually arriving or it goes on simulating (see UdpSink).
        self.on_flowing = on_flowing
        self.device_idx = device_idx
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.fps = fps
        self.gain = gain
        self.noise_gate = noise_gate
        self.log_scale = log_scale
        self.agc = agc
        self.channels = channels
        self.tone = tone
        #: Decoded audio to beam instead of capturing -- see `decode_audio`.
        self.samples = samples
        #: More than one track to beam, decoded as they come up (`Playlist`).
        self.playlist = playlist
        self.loop = loop
        #: A `Monitor`, or None for "don't play it out of anything".
        self.monitor = monitor
        #: Keyboard control (`pixelblaze.cli.controls.Controls`), or None. Its
        #: `poll()` is called on every tick of the run loop, and it is entered
        #: as a context manager for the run -- it owns the terminal mode.
        self.controls = controls
        #: Set by the source when there is one to steer; None for a capture.
        self.source = None
        self.seconds = seconds
        self.stall_timeout = stall_timeout
        self.silence_timeout = silence_timeout

        #: A spectrum / status display (see `pixelblaze.cli.spectrum`), or None.
        self.display = display

        #: Set when the run ended because no audio arrived -- see the class docs.
        self.stalled_for = None

        # Loudness is measured on the input as captured: before `gain`, which
        # scales what the pattern is sent, not the sound. And on the channels as
        # they came, because BS.1770 sums channel power -- a mono mixdown first
        # reads up to 3 dB low and cancels out-of-phase content outright.
        self.meter = LoudnessMeter(sample_rate)
        self.loudness = SILENT

        # Enough frames that the device has certainly seen some, but a small
        # fraction of a second so the pattern reload isn't a visible pause.
        self.flowing_after = max(1, fps // 4)

        self._latest = None
        self._lock = threading.Lock()
        self._running = False
        self._frame_count = 0
        self._start_time = 0
        self._last_block_at = 0.0
        self._silent_since = None
        self._silent = False

        # AGC state
        self._agc_level = 1.0       # current auto-gain multiplier
        self.agc_target = 0.15      # target peak level for frequency bins ([ ] keys)
        self._agc_attack = 0.3      # how fast gain increases (per second)
        self._agc_release = 2.0     # how fast gain decreases (per second)

    @property
    def frames_sent(self) -> int:
        return self._frame_count

    @property
    def is_silent(self) -> bool:
        # A paused track is silent on purpose, and saying "is anything playing?"
        # at someone who just pressed pause is noise.
        return self._silent and not self.is_paused

    @property
    def is_paused(self) -> bool:
        return bool(self.source is not None and getattr(self.source, 'paused', False))

    @property
    def transport(self):
        """What the file source is doing (`Transport`), or None for a capture."""
        state = getattr(self.source, 'state', None)
        return state() if state is not None else None

    def _say(self, line: str):
        """Above the live spectrum, or on its own line."""
        if self.display is not None:
            self.display.log(line)
        else:
            import sys
            print(line, file=sys.stderr, flush=True)

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self._say(str(status))

        self._last_block_at = time.monotonic()
        if self.monitor is not None:
            self.monitor.write(indata)
        self.meter.process(indata)
        self.loudness = self.meter.loudness
        self._track_silence(indata)

        effective_gain = self.gain * (self._agc_level if self.agc else 1.0)
        result = fft_to_pb_bins(indata.copy(), self.sample_rate,
                                gain=effective_gain, noise_gate=self.noise_gate)

        # Log scale: compress dynamic range
        if self.log_scale:
            for i in range(32):
                v = result["frequencyData"][i]
                result["frequencyData"][i] = np.log1p(v * 1000) / np.log1p(1000) if v > 0 else 0
            mag = result["maxFrequencyMagnitude"]
            result["maxFrequencyMagnitude"] = float(np.log1p(mag * 1000) / np.log1p(1000)) if mag > 0 else 0
            ea = result["energyAverage"]
            result["energyAverage"] = float(np.log1p(ea * 1000) / np.log1p(1000)) if ea > 0 else 0

        # AGC: adjust gain so peak bin stays near target
        if self.agc:
            peak_val = max(result["frequencyData"])
            if peak_val > 0:
                ratio = self.agc_target / peak_val
                dt = 1.0 / max(self.fps, 1)
                if ratio > 1:
                    # Too quiet — increase gain slowly
                    self._agc_level += (ratio - 1) * self._agc_attack * dt
                else:
                    # Too loud — decrease gain faster
                    self._agc_level += (ratio - 1) * self._agc_release * dt
                self._agc_level = max(0.1, min(self._agc_level, 500.0))

        with self._lock:
            self._latest = result

    def _track_silence(self, block):
        """Digital silence -- nothing above -120 dBFS -- for `silence_timeout`."""
        quiet = bool(np.max(np.abs(block)) < 1e-6) if block.size else True
        if not quiet:
            self._silent_since = None
            self._silent = False
            return
        if self._silent_since is None:
            self._silent_since = time.monotonic()
        elif time.monotonic() - self._silent_since >= self.silence_timeout:
            self._silent = True

    def _on_track(self, title, index, count):
        """A new track is playing. The integrated LUFS figure is reset with it,
        so `I` answers "how loud is this track" rather than averaging a set."""
        import os
        self.meter.reset()
        self._say(f"  ▸ {index + 1}/{count}  {os.path.basename(str(title))}")

    def _source(self):
        if self.samples is not None or self.playlist is not None:
            return FileSource(self.samples, self.sample_rate, self.block_size,
                              self._audio_callback, loop=self.loop, on_end=self.stop,
                              playlist=self.playlist, on_track=self._on_track)
        if self.tone:
            return ToneSource(self.tone, self.sample_rate, self.block_size,
                              self.channels, self._audio_callback)
        return MicSource(self.device_idx, self.sample_rate, self.block_size,
                         self.channels, self._audio_callback)

    def stop(self):
        """Ask `run()` to wind up. Safe from another thread."""
        self._running = False

    def run(self):
        """Start capturing and pushing. Blocks until Ctrl-C, `seconds`, a stall
        or `stop()`. Check `stalled_for` afterwards."""
        self._running = True
        self._start_time = time.monotonic()
        self._last_block_at = self._start_time
        self._frame_count = 0
        self.stalled_for = None
        self.meter.reset()

        push_interval = 1.0 / max(self.fps, 1)
        next_push = self._start_time
        fps_at = self._start_time
        fps_frames = 0

        self.sink.start()
        if self.display is not None:
            self.display.start()

        with contextlib.ExitStack() as stack:
            if self.monitor is not None:
                stack.enter_context(self.monitor)
            if self.controls is not None:
                # After the monitor and before the source, so that unwinding
                # puts the terminal back before closing the output stream: a
                # PortAudio close that hangs must not be the thing standing
                # between Ctrl-C and a usable shell.
                stack.enter_context(self.controls)
            self.source = stack.enter_context(self._source())
            try:
                while self._running:
                    now = time.monotonic()

                    if self.controls is not None:
                        self.controls.poll()

                    if now >= next_push:
                        # Advance rather than reset, so the rate is the rate;
                        # but never try to make up a whole backlog at once.
                        next_push = max(now, next_push) + push_interval
                        self._push_frame()

                    if self.display is not None:
                        if now - fps_at >= 1.0:
                            self.display.fps = self._frame_count - fps_frames
                            fps_frames = self._frame_count
                            fps_at = now
                        self.display.loudness = self.loudness
                        self.display.silent = self.is_silent
                        self.display.gain = self.gain
                        self.display.agc = self._agc_level if self.agc else None
                        self.display.transport = self.transport
                        if self.sink.targets is not None:
                            self.display.targets = len(self.sink.targets)
                        self.display.draw()

                    if getattr(self.source, 'switching', False):
                        # Decoding the next track holds up the playing thread.
                        # That is work, not a dead input -- and on a long track
                        # over a slow disk it can outlast the stall timeout.
                        self._last_block_at = now

                    quiet_for = now - self._last_block_at
                    if quiet_for >= self.stall_timeout:
                        self.stalled_for = quiet_for
                        break

                    if self.seconds is not None and now - self._start_time >= self.seconds:
                        break

                    # Sleep to the *next* thing due, not a fixed tick: a flat
                    # 1/60 s nap rounds a 40 fps push interval up to 34 ms and
                    # the frame rate silently reads 30.
                    deadline = min(next_push, now + self.TICK)
                    time.sleep(max(0.0, deadline - time.monotonic()))
            except KeyboardInterrupt:
                pass
            finally:
                self._running = False
                self.sink.stop()

    def _push_frame(self):
        with self._lock:
            data = self._latest
            self._latest = None

        if data is None:
            return

        self.sink.send(data)
        self._frame_count += 1

        if self.display is not None:
            self.display.update(data)

        if self.on_flowing is not None and self._frame_count >= self.flowing_after:
            callback, self.on_flowing = self.on_flowing, None
            callback()
