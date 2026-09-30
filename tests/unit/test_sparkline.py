############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the project list's sparkline
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The thumbnail of the project list read upside down (reported).

Measured with a star fading from 12.0 to 13.0: the bright point landed at
y=26 of 30 (the bottom) and the faint one at y=2 (the top). The cause was a
double inversion: `py` already puts the bright end on top (the astronomical
way, the same as the big chart's `_map_y`) and the code returned
`height - py`, which flipped it back.

These tests read the painted pixels, because that is the only place a
direction can be checked: the numbers in the code look reasonable both ways
round.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                   # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


def _span(img, x):
    # @args: img - the QImage of a sparkline, x - the column to read
    # @return: (top, bottom) rows with ink in that column, or None
    rows = [y for y in range(img.height())
            if img.pixelColor(x, y).alpha() > 40]
    return (min(rows), max(rows)) if rows else None


def _fading():
    # a star that fades: the magnitude grows with time
    return [{"mjd": 60000.0 + i, "mag": 12.0 + i * 0.2} for i in range(6)]


def test_a_fading_star_goes_down_the_thumbnail(qapp):
    # The magnitude axis is inverted, so "fainter" is LOWER on screen: the
    # first point (the brightest) has to be above the last one.
    from nightscribe.gui.widgets.sparkline import sparkline_pixmap
    img = sparkline_pixmap(_fading(), width=120, height=30).toImage()
    first = _span(img, 4)
    last = _span(img, 115)
    assert first and last
    assert first[0] < last[0], (first, last)     # bright on top


def test_a_brightening_star_goes_up_the_thumbnail(qapp):
    # and the other way round, so the test cannot pass by accident
    from nightscribe.gui.widgets.sparkline import sparkline_pixmap
    pts = [{"mjd": 60000.0 + i, "mag": 13.0 - i * 0.2} for i in range(6)]
    img = sparkline_pixmap(pts, width=120, height=30).toImage()
    assert _span(img, 4)[0] > _span(img, 115)[0]


def test_an_empty_thumbnail_is_null_and_a_row_hides_it(qapp):
    # fewer than two usable points: nothing to draw, and the row hides the
    # label instead of showing an empty box
    from nightscribe.gui.widgets.sparkline import sparkline_pixmap
    assert sparkline_pixmap([]).isNull()
    assert sparkline_pixmap([{"mjd": None, "mag": 12.0},
                             {"mjd": 60000.0, "mag": None}]).isNull()
