"""Render-forwarder tests. No device, no network — pure source transformation.

Why this exists: a Pixelblaze picks ONE render function per frame, chosen by the
pixel map it holds. Measured on a v3.51 device with a 3D map installed, it calls
render3D, else render(index) — never render2D. So a pattern exporting only
render2D draws every pixel black on that device, with no error anywhere, and a
render3D-only pattern does the same on an unmapped one. 169 of the 506 patterns
in the public corpus are render2D-only, so this is the common case, not an edge.

_add_render_forwarders appends the missing exports so an upload renders under
whatever map the target happens to have.
"""

import pytest

from pixelblaze.cli.cli import _add_render_forwarders

R1 = 'export function render(index) { rgb(1, 0, 0) }'
R2 = 'export function render2D(index, x, y) { rgb(1, 0, 0) }'
R3 = 'export function render3D(index, x, y, z) { rgb(1, 0, 0) }'


@pytest.mark.parametrize('source, expected', [
    # render2D only: needs render3D (for 3D-mapped devices) and render (unmapped)
    (R2, {'render', 'render3D'}),
    # render3D only: needs render2D (2D-mapped) and render (unmapped)
    (R3, {'render', 'render2D'}),
    # render alone already works everywhere — the firmware always falls back to
    # it (3D map -> render3D else render; 2D -> render2D else render; none ->
    # render). Adding dimensional forwarders would change nothing, so we don't.
    (R1, set()),
    (R1 + '\n' + R2, {'render3D'}),
    (R1 + '\n' + R3, {'render2D'}),
    (R2 + '\n' + R3, {'render'}),
    (R1 + '\n' + R2 + '\n' + R3, set()),
    # nothing renderable: left strictly alone rather than given a render()
    ('export var foo = 1', set()),
])
def test_adds_exactly_the_missing_forwarders(source, expected):
    out, added = _add_render_forwarders(source)
    assert set(added) == expected
    for name in added:
        assert f'export function {name}(' in out


def test_preserves_the_original_exports():
    out, _ = _add_render_forwarders(R2)
    assert R2 in out


def test_all_three_is_returned_byte_identical():
    source = R1 + '\n' + R2 + '\n' + R3
    assert _add_render_forwarders(source)[0] == source


def test_is_idempotent():
    """A second pass must not stack a duplicate export on the first pass's output
    (which would be a compile error on the device, not merely wasteful)."""
    once, first = _add_render_forwarders(R2)
    twice, second = _add_render_forwarders(once)
    assert first and not second
    assert twice == once


def test_commented_out_export_does_not_count_as_present():
    """The detector is anchored to the start of a line, so a commented-out
    export is correctly seen as absent and still gets its forwarder."""
    out, added = _add_render_forwarders('// ' + R3 + '\n' + R2)
    assert 'render3D' in added


def test_indented_export_is_detected():
    out, added = _add_render_forwarders('  ' + R2)
    assert set(added) == {'render', 'render3D'}
