#!/usr/bin/env python3
"""Quieting a board before it is flashed.

The firmware's own `recovery.html` opens its websocket with
`{"sendUpdates":false,"getConfig":true,"getUpgradeState":true}` — it silences the
device before it does anything else. This client did not, so every flash it
attempted ran with the board still rendering and still pushing a frame after
every render cycle, over the same websocket it was being flashed through.
"""

from pixelblaze.pixelblaze import Pixelblaze


class Spy(Pixelblaze):
    """Records the quieting calls instead of making them."""

    def __init__(self, settings=None):            # no connection
        self.calls = []
        self._settings = settings if settings is not None else {
            'brightness': 0.42, 'runSequencer': True,
        }

    def getConfigSettings(self):
        return self._settings

    def setSendPreviewFrames(self, on):    self.calls.append(('sendUpdates', on))
    def pauseSequencer(self, **kw):        self.calls.append(('pauseSequencer',))
    def playSequencer(self, **kw):         self.calls.append(('playSequencer',))
    def pauseRenderer(self, on):           self.calls.append(('pauseRenderer', on))
    def setBrightnessSlider(self, v, **kw): self.calls.append(('brightness', round(float(v), 4)))


def test_quieting_stops_the_stream_and_the_renderer():
    pb = Spy()
    prior = pb.quietForUpdate()

    assert ('sendUpdates', False) in pb.calls, pb.calls
    assert ('pauseRenderer', True) in pb.calls, pb.calls
    assert ('brightness', 0.0) in pb.calls, pb.calls
    assert prior['brightness'] == 0.42
    assert prior['sequencerWasRunning'] is True


def test_the_sequencer_is_stopped_before_the_renderer():
    """A pattern switch unpauses the renderer, and the sequencer switches
    patterns on a timer — so pausing the renderer first does not hold for the
    length of an upload."""
    pb = Spy()
    pb.quietForUpdate()
    names = [c[0] for c in pb.calls]
    assert names.index('pauseSequencer') < names.index('pauseRenderer'), names


def test_restore_puts_back_what_it_found():
    pb = Spy()
    prior = pb.quietForUpdate()
    pb.calls.clear()
    pb.unquietAfterUpdate(prior)

    assert ('pauseRenderer', False) in pb.calls, pb.calls
    assert ('playSequencer',) in pb.calls, pb.calls
    assert ('brightness', 0.42) in pb.calls, pb.calls
    assert ('sendUpdates', True) in pb.calls, pb.calls


def test_restore_leaves_a_stopped_sequencer_stopped():
    pb = Spy(settings={'brightness': 0.1, 'runSequencer': False})
    prior = pb.quietForUpdate()
    pb.calls.clear()
    pb.unquietAfterUpdate(prior)
    assert ('playSequencer',) not in pb.calls, pb.calls


def test_quieting_survives_a_device_that_refuses_part_of_it():
    """A board that rejects one step must not abort the rest, or a partial
    failure leaves it noisier than if we had not tried."""
    class Picky(Spy):
        def pauseRenderer(self, on):
            raise RuntimeError("nope")

    pb = Picky()
    prior = pb.quietForUpdate()
    assert prior['steps']['renderer'] is False
    assert prior['steps']['sendUpdates'] is True
    assert ('brightness', 0.0) in pb.calls, pb.calls


def test_fresh_version_bypasses_the_cache():
    """`getVersion()` memoises in `latestVersion`, so after a flash it reports
    the version the device used to run — which is worse than not checking."""
    class Versioned(Spy):
        def __init__(self):
            super().__init__()
            self.reads = 0

        def getConfigSettings(self):
            self.reads += 1
            return {'ver': '3.51' if self.reads == 1 else '3.70'}

    pb = Versioned()
    assert str(pb.getVersion()) == '3.51'
    assert str(pb.getVersion()) == '3.51'        # cached
    assert str(pb.freshVersion()) == '3.70'      # re-read
