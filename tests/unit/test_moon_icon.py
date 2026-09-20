############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - moon phase icon tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for the real-disc moon phase icon (gui/moon_icon.py).

We never call the network and never mutate the asset: geometry (lit-side
and lit fraction) plus the graceful fallback when the photo is missing.
Because the surface is a real photograph (maria are dark, highlands bright)
absolute brightness is not assertable; instead we check the fraction that
the terminator geometry predicts, allowing for the photo's own dimness,
and that waxing/waning render symmetrically. The shared qapp fixture
mirrors the module-scoped pattern used in test_theme.py so these run
headless in CI and on a laptop alike.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    # One QApplication per process; module scope mirrors test_theme.py.
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _lit_ratio(pix):
    # Fraction of the disc's opaque pixels that are "bright". A dark
    # maria-free photograph gives ~0.7 of the theoretical fraction.
    # @args: pix - the icon QPixmap
    # @return: float 0..1 (bright = clearly not the near-black night side)
    img = pix.toImage()
    total = bright = 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = img.pixel(x, y)
            if ((c >> 24) & 0xFF) < 32:  # transparent corner
                continue
            total += 1
            if min((c >> 16) & 0xFF, (c >> 8) & 0xFF) > 96:
                bright += 1
    return bright / total if total else 0.0


def _lit_side(pix):
    # @args: pix - the icon QPixmap
    # @return: "right" | "left" — which half carries the lit area
    img = pix.toImage()
    w = img.width()
    r = l = 0
    for y in range(0, img.height(), 3):
        for x in range(0, w, 3):
            c = img.pixel(x, y)
            if ((c >> 24) & 0xFF) < 32:
                continue
            if min((c >> 16) & 0xFF, (c >> 8) & 0xFF) > 96:
                if x >= w / 2:
                    r += 1
                else:
                    l += 1
    return "right" if r >= l else "left"


def test_never_null(qapp):
    from nightscribe.gui import moon_icon
    for e in (0, 45, 90, 135, 180, -180, -45):
        assert not moon_icon.moon_pixmap(e, 28).isNull(), \
            f"null pixmap for elong={e}"


def test_formula_endpoints(qapp):
    from nightscribe.gui import moon_icon
    assert moon_icon.lit_fraction(0) == pytest.approx(0.0, abs=1e-6)
    assert moon_icon.lit_fraction(90) == pytest.approx(0.5, abs=1e-3)
    assert moon_icon.lit_fraction(-90) == pytest.approx(0.5, abs=1e-3)
    assert moon_icon.lit_fraction(180) == pytest.approx(1.0, abs=1e-6)


def test_new_moon_is_all_dark(qapp):
    from nightscribe.gui import moon_icon
    assert _lit_ratio(moon_icon.moon_pixmap(0, 40)) < 0.02


def test_crescent_illumination_in_band(qapp):
    from nightscribe.gui import moon_icon
    # predicted (1 - cos|E|)/2 = 0.25 at E=60; the photograph is dimmer,
    # but it must still clearly be a thin lit arc, not empty nor full
    r = _lit_ratio(moon_icon.moon_pixmap(-60, 40))
    assert 0.05 < r < 0.45, f"crescent lit ratio out of band: {r}"


def test_gibbous_illumination_in_band(qapp):
    from nightscribe.gui import moon_icon
    # E=120 -> 0.75 predicted; again dimmer in practice, but well above
    # the crescent value (the lit region is large)
    r = _lit_ratio(moon_icon.moon_pixmap(-120, 40))
    assert 0.16 < r < 0.78, f"gibbous lit ratio out of band: {r}"


def test_waxing_lit_right_waning_lit_left(qapp):
    from nightscribe.gui import moon_icon
    assert _lit_side(moon_icon.moon_pixmap(-120, 40)) == "right"
    assert _lit_side(moon_icon.moon_pixmap(120, 40)) == "left"


def test_waxing_waning_symmetry(qapp):
    # Same |E|, opposite sign: the lit fraction on the disc is identical;
    # the photograph may make one side marginally brighter, the other
    # must not collapse to zero.
    from nightscribe.gui import moon_icon
    for e in (-80, 80):
        left, right = (e, -e)
        r1 = _lit_ratio(moon_icon.moon_pixmap(left, 40))
        r2 = _lit_ratio(moon_icon.moon_pixmap(right, 40))
        assert 0.05 < r1 < 0.7 and 0.05 < r2 < 0.7, \
            f"unexpected asymmetry at {left}/{right}: {r1}, {r2}"


def test_fallback_when_asset_missing(qapp, monkeypatch, tmp_path):
    # Point the module at a non-existent asset and confirm a pixmap still
    # comes back (grey fallback), never an exception, at every phase.
    from nightscribe.gui import moon_icon
    real = moon_icon.ASSET
    try:
        monkeypatch.setattr(moon_icon, "ASSET", tmp_path / "nope.png")
        for e in (-45, 0, 45, 90, -135, 135, -180, 180):
            pix = moon_icon.moon_pixmap(e, 28)
            assert not pix.isNull()
        # the fallback is a flat light disc; crescent vs full differ hugely
        assert _lit_ratio(moon_icon.moon_pixmap(-45, 40)) > 0.05
        assert _lit_ratio(moon_icon.moon_pixmap(-135, 40)) > 0.5
    finally:
        moon_icon.ASSET = real
