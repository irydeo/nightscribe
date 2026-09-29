############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the workbench's layout (U1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The editor's breathing room (U1).

The workbench is a tool that lives maximized, so every pixel of chrome is
a pixel taken from the plate. These tests pin the measurements that made
the redesign necessary, so the space cannot be quietly given away again:

* the top bar used to measure 69 px in a tall window and 25 px in a short
  one (its zoom label has a Preferred policy and the layout's stretch was
  never applied by the loader): the bar is stable now;
* the histogram strip reserved 175-200 px, a fifth of the window, for two
  rows of controls: it is compact and foldable now;
* the object line was a ROW of the window (31 px for one line of text):
  it is painted over the plate now.
"""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication          # noqa: E402

FIXTURES = Path(__file__).parents[1] / "fixtures"
MONO = FIXTURES / "sn2026zji_new_image.fits"

_OBJECT = {"name": "HAT-P-32 b", "ra": 31.04, "dec": 46.68, "mag": 11.3}


def _app():
    return QApplication.instance() or QApplication([])


def _dialog(width, height, obj=None, folded=None):
    # @args: width/height - the window's size, obj - the attached object
    #        or None, folded - the histogram's state to force or None
    # @return: the dialog, laid out and shown
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(width, height)
    d.show()
    if obj is not None:
        d.set_object(obj)
    if folded is not None:
        d.hist_section.setCollapsed(folded)
    _settle(d)
    return d


def _settle(d, turns=16):
    # The layout has settled when two consecutive event-loop turns agree on
    # the work area's height. A busy full-suite run needs more turns than an
    # isolated one, and measuring before it settled is measuring a window
    # halfway through a resize (this is exactly how this test failed in the
    # suite and passed alone).
    # @args: d - the dialog, turns - the patience budget
    # @return: None
    last = None
    for _ in range(turns):
        QApplication.processEvents()
        now = d.splitter.height()
        if now == last and now > 0:
            return
        last = now


def _chrome(d):
    # @return: (top bar, work area, bottom strip) heights in pixels
    lay = d.layout()
    return (lay.itemAt(0).geometry().height(), d.splitter.height(),
            lay.itemAt(lay.count() - 1).geometry().height())


def test_the_work_area_owns_the_extra_height():
    # The plate is what the window is for: the chrome takes what it NEEDS
    # and the work area gets everything else. Two things are asserted, and
    # the first one is the real invariant:
    #
    #   1. nothing between the bar and the strip can take height: the work
    #      area measures the window minus the chrome, always;
    #   2. the chrome is capped (the bar was reaching 69 px, the strip 200).
    #
    # The proportion is checked only when the environment can actually give
    # a 1000 px window: the offscreen platform used by the tests reports an
    # 800x800 screen and, depending on the run, the window manager hands
    # back a smaller window than the one asked for. Measuring a window
    # halfway through that is measuring the platform, not the layout.
    _app()
    d = _dialog(1500, 1000, _OBJECT)
    bar, work, strip = _chrome(d)
    assert bar <= 40                    # the bar's own size, not a share
    assert strip <= 130                 # the strip with its fold header
    # the work area is what remains, within the window's own margins
    slack = d.height() - (bar + work + strip)
    assert 0 <= slack <= 40, (work, d.height(), bar, strip, slack)
    if d.height() >= 990:
        assert work >= 0.80 * d.height()
    d.close()


def test_the_top_bar_is_the_same_height_in_every_window():
    # The bar used to grow to 69 px in a tall window and shrink to 25 in a
    # short one, because NOBODY owned the extra height: the stretch the
    # Designer file carries is not applied by QUiLoader, so the space went
    # to the first item that could absorb it (the zoom label).
    _app()
    heights = []
    for (w, h, obj) in ((1500, 1000, None), (1500, 1000, _OBJECT),
                        (1500, 700, _OBJECT)):
        d = _dialog(w, h, obj)
        heights.append(_chrome(d)[0])
        d.close()
    assert len(set(heights)) == 1       # one height, always


def test_the_work_area_grows_with_the_window():
    # Scaling the window up must give the pixels to the PLATE: the extra
    # height of a taller window shows up in the work area, not in the bar.
    _app()
    small = _dialog(1500, 700, _OBJECT)
    small_work = _chrome(small)[1]
    small.close()
    big = _dialog(1500, 1100, _OBJECT)
    big_work = _chrome(big)[1]
    big.close()
    assert big_work - small_work >= 380      # 400 px more, minus slack


def test_the_histogram_strip_folds_and_remembers_it():
    from nightscribe.config import config
    _app()
    d = _dialog(1500, 1000, _OBJECT)
    assert not d.hist_section.isCollapsed()
    # a REAL click on the header (the fold section stays silent for a
    # programmatic setCollapsed on purpose: closing a block must not fire
    # back), which is also the only thing the memory should react to
    d.hist_section._btn.click()
    for _ in range(2):
        QApplication.processEvents()
    assert d.hist_section.isCollapsed()
    bar, work, strip = _chrome(d)
    assert strip <= 30                        # a header, nothing else
    assert work >= 0.90 * 1000
    # the choice is written down...
    assert bool(config.get("ufe_histogram_folded", 0)) is True
    d.close()
    # ...and the next window comes as it was left
    again = _dialog(1500, 1000, _OBJECT)
    assert again.hist_section.isCollapsed()
    assert _chrome(again)[1] >= 0.90 * 1000
    again.close()


def test_the_object_is_painted_over_the_plate_not_a_row_of_the_window():
    # 31 px of window height for one line of text, and it drew the eye out
    # of the picture: the object belongs to the image.
    _app()
    d = _dialog(1500, 1000)
    assert d.layout().count() == 3            # bar, work area, strip: no row
    assert d.view.title_line() == ""          # nothing attached, no line
    d.set_object(_OBJECT)
    line = d.view.title_line()
    assert "HAT-P-32 b" in line and "RA" in line and "mag 11.30" in line
    d.close()


def test_the_object_line_goes_into_the_exported_png(tmp_path):
    # "On screen and in the exported PNG" is the rule the corner boxes and
    # the compass already follow; the object's line is part of the HUD, so
    # a figure mailed to a colleague still says which object it is.
    from nightscribe.gui.ufe_dialog import UfeDialog
    _app()
    d = UfeDialog()
    d.resize(900, 700)
    d.show()
    assert d.open_plate(str(MONO))
    for _ in range(2):
        QApplication.processEvents()
    without = d.view.export_png(tmp_path / "without.png").read_bytes()
    d.set_object(_OBJECT)
    with_object = d.view.export_png(tmp_path / "with.png").read_bytes()
    assert with_object != without
    d.close()
