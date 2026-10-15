#!/usr/bin/env python3
"""A chatty board must not be able to hang a receive.

Every Pixelblaze pushes `{"fps":...}` stats frames nobody asked for, about once
a second. `wsReceive` reads them, keeps none of them, and loops -- and its only
way out is the socket timeout, which a stats frame resets every time it lands.
So on hardware "how long until this gives up" is a race against the push
interval rather than a deadline, and the loop that waits for an output expander
a board hasn't got depends on losing that race to terminate at all.

These tests hold a fake board that always wins it, so the failure is a hang
every time instead of once an hour on a WiFi AP.
"""

import socket
import threading
import time

from pixelblaze.pixelblaze import Pixelblaze

# Long enough that a real deadline has clearly expired, short enough that a
# hanging test is a fast test.
GRACE_SECONDS = 8.0


class FakeSocket:
    """Stands in for `ws.sock`, which `_connection_maint` hands to `select`.

    Never readable, so the drain it does before every send falls straight
    through -- the frames in these tests all arrive via `recv`.
    """

    def __init__(self):
        self._ours, self._theirs = socket.socketpair()

    def fileno(self):
        return self._ours.fileno()

    def close(self):
        self._ours.close()
        self._theirs.close()


class ChattyBoard:
    """A Pixelblaze that pushes stats faster than the socket timeout.

    Answers `{"getConfig":true}` the way firmware does -- the settings frame,
    then the sequencer frame -- and, like every board with no output expander
    attached, never sends an expanderConfig.
    """

    STATS = '{"fps":42.5,"vmerr":0,"mem":10000}'
    SETTINGS = '{"name":"ls2","pixelCount":200,"brandName":""}'
    SEQUENCER = ('{"activeProgram":{"name":"sound - spectrokalidamandala",'
                 '"activeProgramId":"xYz123","controls":{}},'
                 '"sequencerMode":0,"runSequencer":false}')

    def __init__(self, statsInterval=0.05):
        self.statsInterval = statsInterval
        self.sock = FakeSocket()
        self.sent = []
        self.statsSent = 0
        self._pending = []

    def settimeout(self, seconds):
        self.timeout = seconds

    def close(self):
        self.sock.close()

    def send(self, payload):
        self.sent.append(payload)
        if b'getConfig' in payload:
            self._pending += [self.SETTINGS, self.SEQUENCER]

    def recv(self):
        if self._pending:
            return self._pending.pop(0)
        # Sooner than default_recv_timeout, so WebSocketTimeoutException -- the
        # only thing that makes wsReceive give up -- never gets a chance to fire.
        time.sleep(self.statsInterval)
        self.statsSent += 1
        return self.STATS


def connectedTo(board):
    """A Pixelblaze wired to `board`, without opening a socket."""
    pb = Pixelblaze.__new__(Pixelblaze)
    pb.ipAddress = '10.17.76.53'
    pb.proxyUrl = None
    pb.ws = board
    pb.connected = True
    pb.setCacheRefreshTime(600)
    return pb


def runBounded(call, seconds=GRACE_SECONDS):
    """Run `call` on a daemon thread. Returns (returned, result, error).

    A hang leaves the thread parked forever, which is why it is a daemon: the
    test reports the hang and the interpreter can still exit.
    """
    outcome = {}

    def target():
        try:
            outcome['value'] = call()
        except BaseException as e:  # noqa: BLE001 - the test reports whatever it was
            outcome['error'] = e

    thread = threading.Thread(target=target, daemon=True, name='pb-bounded-call')
    thread.start()
    thread.join(seconds)
    return (not thread.is_alive()), outcome.get('value'), outcome.get('error')


def test_wsReceive_gives_up_on_a_board_that_only_chatters():
    """A receive with nothing but stats to read must expire, not spin."""
    board = ChattyBoard()
    pb = connectedTo(board)

    returned, value, error = runBounded(
        lambda: pb.wsReceive(binaryMessageType=Pixelblaze.messageTypes.specialConfig))

    assert returned, (
        f"wsReceive never returned: it read {board.statsSent} stats frames in "
        f"{GRACE_SECONDS}s and kept waiting. Its deadline is only checked inside "
        f"the WebSocketTimeoutException handler, and a board this chatty never "
        f"lets that fire.")
    assert error is None, f"wsReceive raised {error!r}"
    assert value is None, f"expected None on expiry, got {value!r}"


def test_getConfigSettings_returns_on_a_board_with_no_expander():
    """The common case: no output expander, so no expanderConfig frame, ever."""
    board = ChattyBoard()
    pb = connectedTo(board)

    returned, value, error = runBounded(lambda: pb.getConfigSettings())

    assert returned, (
        f"getConfigSettings never returned after {GRACE_SECONDS}s "
        f"({board.statsSent} stats frames read). It waits for an expanderConfig "
        f"this board will never send, and the only exit is wsReceive timing out.")
    assert error is None, f"getConfigSettings raised {error!r}"
    assert value['pixelCount'] == 200, f"settings not parsed: {value!r}"


class SlowTransferBoard(ChattyBoard):
    """Sends a multi-frame binary message slowly, chattering between the frames.

    Total transfer time is well past the give-up deadline, which is the point: the
    deadline is about making no progress, not about taking a while. A board on the
    far side of a WiFi AP sending a 500-pattern list looks exactly like this.
    """

    def __init__(self, chunks, gap=0.4, messageType=Pixelblaze.messageTypes.getProgramList):
        super().__init__(statsInterval=0.05)
        self.gap = gap
        self.messageType = messageType
        self.chunks = list(chunks)
        self.chunksSent = 0

    def recv(self):
        if not self.chunks:
            return super().recv()  # nothing left to send; back to chattering
        # A stats frame between every chunk, as hardware does.
        if self.chunksSent and self.chunksSent % 2:
            time.sleep(self.statsInterval)
            self.chunksSent += 1
            self.statsSent += 1
            return self.STATS
        time.sleep(self.gap)
        chunk = self.chunks.pop(0)
        flags = Pixelblaze.frameTypes.frameFirst.value if self.chunksSent == 0 else 0
        if not self.chunks:
            flags |= Pixelblaze.frameTypes.frameLast.value
        self.chunksSent += 1
        return bytes([int(self.messageType), flags]) + chunk


def test_a_slow_multi_frame_transfer_still_completes():
    """Progress resets the clock, so a transfer longer than the deadline survives."""
    chunks = [b'{"aaa":"one"', b',"bbb":"two"', b',"ccc":"three"', b'}']
    board = SlowTransferBoard(chunks, gap=0.4)
    pb = connectedTo(board)

    started = time.monotonic()
    returned, value, error = runBounded(
        lambda: pb.wsReceive(binaryMessageType=Pixelblaze.messageTypes.getProgramList))
    elapsed = time.monotonic() - started

    assert returned, f"a slow transfer was abandoned after {elapsed:.1f}s"
    assert error is None, f"wsReceive raised {error!r}"
    assert value == b''.join(chunks), f"message not reassembled: {value!r}"
    assert elapsed > 1.0, (
        f"transfer finished in {elapsed:.1f}s, too fast to prove anything -- it must "
        f"outlast the {Pixelblaze.default_recv_timeout}s deadline for this to be a test")


def test_getConfigExpander_says_no_instead_of_asking_forever():
    """No expander attached is an answer, not a reason to re-request config forever."""
    board = ChattyBoard()
    pb = connectedTo(board)

    returned, value, error = runBounded(lambda: pb.getConfigExpander())

    assert returned, (
        f"getConfigExpander never returned after {GRACE_SECONDS}s "
        f"({board.statsSent} stats frames read).")
    assert error is None, f"getConfigExpander raised {error!r}"
    assert value is None, f"expected None for a board with no expander, got {value!r}"


def test_getConfigSequencer_returns_on_a_board_with_no_expander():
    """`pb reload` and `pb p` both land here, via the post-command cache refresh."""
    board = ChattyBoard()
    pb = connectedTo(board)

    returned, value, error = runBounded(lambda: pb.getConfigSequencer())

    assert returned, (
        f"getConfigSequencer never returned after {GRACE_SECONDS}s "
        f"({board.statsSent} stats frames read).")
    assert error is None, f"getConfigSequencer raised {error!r}"
    assert value['activeProgram']['activeProgramId'] == 'xYz123', f"got {value!r}"
