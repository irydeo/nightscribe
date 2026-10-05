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
    # the work area's HEIGHT and on the viewport's WIDTH. A busy full-suite
    # run needs more turns than an isolated one, and measuring before it
    # settled is measuring a window halfway through a resize (this is exactly
    # how this test failed in the suite and passed alone). The width matters
    # for the same reason: the plate's own HUD (the object's band) is laid
    # out from it, and a band measured against a viewport that is still
    # resizing reads as too narrow.
    # @args: d - the dialog, turns - the patience budget
    # @return: None
    last = None
    for _ in range(turns):
        QApplication.processEvents()
        now = (d.splitter.height(), d.view.viewport().width())
        if now == last and now[0] > 0:
            return
        last = now


def _chrome(d):
    # The four heights the window spends on chrome, found by IDENTITY and
    # not by index: this layout has already changed twice (the object's row
    # went, the status line arrived) and an index-based measurement would
    # have been measuring the wrong widget both times.
    # @return: (top bar, work area, histogram strip, status line) in px
    lay = d.layout()
    bar = strip = status = 0
    for i in range(lay.count()):
        item = lay.itemAt(i)
        if item.layout() is not None:
            bar = item.geometry().height()
        elif item.widget() is d.hist_section:
            strip = item.geometry().height()
        elif item.widget() is d._ui.lbl_status_bar:
            status = item.geometry().height()
    return bar, d.splitter.height(), strip, status


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
    bar, work, strip, status = _chrome(d)
    assert bar <= 40                    # the bar's own size, not a share
    assert strip <= 130                 # the strip with its fold header
    assert status <= 30                 # one line, and it stays one line
    # the work area is what remains, within the window's own margins
    slack = d.height() - (bar + work + strip + status)
    assert 0 <= slack <= 40, (work, d.height(), bar, strip, status, slack)
    if d.height() >= 990:
        # The history of this number, so it is not a goalpost moved in
        # silence: 697 px (70 %) before U1; 820 (82 %) once the bar stopped
        # growing and the strip got compact; 794-803 (79.4-80.3 %) now that
        # the status line has arrived, 23 px spent on purpose (U4: one
        # place for the messages instead of four).
        #
        # The floor is 78 % and not 80: the exact figure moves a point with
        # the FONT METRICS the environment happens to have (this test
        # measured 80.3 % alone and 79.4 % in a full run, with everything
        # else identical). The invariant above is the real acceptance: the
        # work area owns everything the chrome does not need.
        assert work >= 0.78 * d.height()
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
    #
    # The two heights are asked against the SCREEN: the Windows runner's
    # desktop is 1024x768, so a 1100-tall window came back clamped and the
    # growth measured 49 px instead of 400 with the design intact (measured
    # 2026-10-01). What must hold is the transfer, not the absolute size.
    _app()
    room = QApplication.primaryScreen().availableGeometry().height()
    small = _dialog(1500, max(420, room // 2), _OBJECT)
    small_work, small_real = _chrome(small)[1], small.height()
    small.close()
    big = _dialog(1500, room - 40, _OBJECT)   # as tall as the desktop allows
    big_work, big_real = _chrome(big)[1], big.height()
    big.close()
    # the ACHIEVED heights, not the asked ones: the layout has a floor
    # (measured: asking for 420 gives 640) and the desktop has a ceiling
    if big_real - small_real < 60:
        import pytest
        pytest.skip("this screen cannot show two windows of a different "
                    "height")
    assert big_work - small_work >= 0.9 * (big_real - small_real)


def test_the_histogram_strip_folds_and_remembers_it():
    from nightscribe.config import config
    _app()
    d = _dialog(1500, 1000, _OBJECT)
    assert not d.hist_section.isCollapsed()
    # a REAL click on the header (the fold section stays silent for a
    # programmatic setCollapsed on purpose: closing a block must not fire
    # back), which is also the only thing the memory should react to
    d.hist_section._btn.click()
    _settle(d)
    assert d.hist_section.isCollapsed()
    bar, work, strip, status = _chrome(d)
    assert strip <= 30                        # a header, nothing else
    # The chrome is a fixed strip of PIXELS, so it is ~11 % of a 1000 px
    # window and ~13 % of a 750 px one: on the CI's 1024x768 desktop the
    # window was clamped and the ratio failed with the design intact
    # (measured 2026-10-01). What must hold is that the strip is thin.
    assert bar + strip + status <= 110
    assert work >= d.height() - 110
    # the choice is written down...
    assert bool(config.get("ufe_histogram_folded", 0)) is True
    d.close()
    # ...and the next window comes as it was left
    again = _dialog(1500, 1000, _OBJECT)
    assert again.hist_section.isCollapsed()
    assert _chrome(again)[1] >= again.height() - 110
    again.close()


def test_the_object_is_painted_over_the_plate_not_a_row_of_the_window():
    # The object's line used to be a ROW of the window under the top bar
    # (31 px of height for one line of text, and it drew the eye out of the
    # picture). It is part of the plate's band now (ADR-046 rev.): painted
    # over the image, so the window keeps its four items and the export
    # carries it.
    from nightscribe.gui.ufe_dialog import UfeDialog
    _app()
    d = UfeDialog()
    d.resize(1500, 1000)
    d.show()
    assert d.open_plate(str(MONO))
    _settle(d)
    # the top bar, the work area, the histogram's section and the status
    # line: four items, and NOT one of them is an object row
    assert d.layout().count() == 4
    # without an object the plate names itself
    assert d.view.band_lines()["lines"][0][0]["text"] == \
        "sn2026zji_new_image"
    d.set_object(_OBJECT)
    first = d.view.band_lines()["lines"][0]
    text = " · ".join(seg["text"] for seg in first)
    assert "HAT-P-32 b" in text and "RA" in text and "11.30" in text
    d.close()


def test_the_band_owns_the_top_and_nothing_collides():
    # The observer preferred it at the top, across the whole width, with the
    # other labels moved down: it is the plate's heading. What it must never
    # do is overlap them, so the compass starts below it.
    from nightscribe.gui.ufe_dialog import UfeDialog
    _app()
    d = UfeDialog()
    d.resize(1000, 800)
    d.show()
    assert d.open_plate(str(MONO))
    d.set_object(_OBJECT)
    _settle(d)
    d.view.repaint()                        # the HUD paints on the viewport
    QApplication.processEvents()
    rect = d.view._title_rect
    assert rect is not None
    vp = d.view.viewport()
    assert rect.top() < 40                          # the top band
    assert rect.width() > vp.width() * 0.8          # and across the plate
    # the other top overlays start under it
    assert d.view._title_h > 0
    assert 10 + d.view._title_h > rect.bottom()     # the boxes' own margin
    # the band is the PLATE's heading: it stays without an object (the
    # frame's own date, exposure and scale are still its data) and only
    # goes when the plate does
    d.set_object(None)
    QApplication.processEvents()
    assert d.view._title_rect is not None
    d.state.clear()
    d.view.repaint()
    QApplication.processEvents()
    assert d.view._title_rect is None
    assert d.view._title_h == 0.0
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
    _settle(d)
    without = d.view.export_png(tmp_path / "without.png").read_bytes()
    d.set_object(_OBJECT)
    with_object = d.view.export_png(tmp_path / "with.png").read_bytes()
    assert with_object != without
    d.close()


# ---------------- U6: the left panel's doors --------------------------

_CHART_KNOBS = (
    "cmb_series_scale", "btn_series_robust", "btn_series_fixaxis",
    "spn_series_maglo", "spn_series_maghi", "btn_series_zoomfit",
    "btn_series_errors", "btn_series_hideflags", "cmb_series_bin",
    "spn_series_binn", "chk_series_mean", "spn_series_meanwin",
    "chk_series_outliers", "spn_series_outsigma", "btn_series_exclout",
    "btn_series_exclsel", "btn_series_restore")


def test_the_chart_knobs_live_in_their_own_window():
    # Seventeen controls about how the curve is DRAWN were stacked in the
    # left panel's 300 px column, mixed with the action that measures the
    # night. They are knobs you touch while LOOKING at the curve, so they
    # have their own window, and it does not block the workbench: the whole
    # point is to change them while watching the curve move.
    _app()
    d = _dialog(1500, 1000, _OBJECT)
    tab = d.tab_measure
    chart_dlg = tab._series_dlg
    assert not chart_dlg.isVisible()          # closed until asked
    tab._open_series_chart()
    QApplication.processEvents()
    assert chart_dlg.isVisible()
    assert not chart_dlg.isModal()
    # the SAME widgets, by name: the tab wires them exactly as before
    for name in _CHART_KNOBS:
        assert getattr(tab, name) is getattr(chart_dlg, name), name
    chart_dlg.close()
    d.close()


def test_the_panel_keeps_only_what_is_touched_while_measuring():
    # The count is the measure of the overload: the left panel showed ~30
    # interactive controls. What must stay visible is the frame navigator,
    # the measuring action and the doors; everything else is one click
    # away, and NOTHING is gone (the widgets are all still there).
    from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                                   QPushButton, QSpinBox, QToolButton, QWidget)
    _app()
    d = _dialog(1500, 1000, _OBJECT)
    d.set_series_hook(lambda: {"pid": 1, "session_id": 2, "paths": []})
    _settle(d)
    panel = d.series_pane
    assert panel.isVisible()                  # a visit arms the panel
    kinds = (QPushButton, QToolButton, QComboBox, QSpinBox, QDoubleSpinBox,
             QCheckBox)
    visible = [w for w in panel.findChildren(QWidget)
               if isinstance(w, kinds) and w.isVisible()]
    assert len(visible) <= 14, [w.objectName() for w in visible]
    # and every knob is still there, one click away
    assert all(getattr(d.tab_measure, n, None) is not None
               for n in _CHART_KNOBS)
    d.close()


# ---------------- U4: one place for the messages ----------------------

def test_a_tab_message_lands_in_the_window_s_own_line():
    # The tabs said things in labels of their own (four windows, four
    # places, none of them where an observer looks). They still keep their
    # own record — fifty-odd tests read it — but the reader reads the line
    # at the bottom.
    _app()
    d = _dialog(1400, 900, _OBJECT)
    tab = d.tab_measure
    tab._say("Serie medida: 142 puntos")
    QApplication.processEvents()
    bar = d._ui.lbl_status_bar
    assert "Serie medida: 142 puntos" in bar.text()
    assert bar.text().startswith("ⓘ")
    assert d.status_text() == "Serie medida: 142 puntos"
    # the tab's own label is still the record (and takes no room)
    assert tab.lbl_status.text() == "Serie medida: 142 puntos"
    assert not tab.lbl_status.isVisible()
    d.close()


def test_a_warning_looks_like_a_warning():
    # A message that already carries the ⚠ keeps it, and an explicit level
    # is obeyed: the glyph is read before the text is.
    _app()
    d = _dialog(1400, 900, _OBJECT)
    d.tab_measure._say("⚠ 4 frames heredaron la alineación")
    QApplication.processEvents()
    assert d._ui.lbl_status_bar.text().startswith("⚠")
    d.set_status("La serie falló: negative dimensions", "error")
    assert d._ui.lbl_status_bar.text().startswith("✕")
    d.close()


def test_a_long_message_is_elided_and_never_eats_the_plate():
    # A message that wraps grows the window and costs the plate its height:
    # the line is ONE line, elided, with the whole text in the tooltip, and
    # the work area does not move.
    _app()
    d = _dialog(1200, 900, _OBJECT)
    work_before = d.splitter.height()
    long_text = ("Serie: 142 puntos de 142 tomas · " + "muy largo " * 40)
    d.set_status(long_text)
    _settle(d)
    bar = d._ui.lbl_status_bar
    # ONE line: the height is the font's own line, not a magic 22 (Windows
    # measures a taller line and the assertion failed with the design intact,
    # measured 2026-10-01)
    assert bar.height() <= bar.fontMetrics().height() + 6, bar.height()
    assert d.status_text() == long_text          # kept whole for the reader
    assert bar.toolTip() == long_text            # and reachable
    assert len(bar.text()) < len(long_text)      # elided, not wrapped
    # the plate did not move: a re-elide can reflow the layout by a pixel
    # or two, and a couple of pixels is not "eating the plate" (a wrapping
    # message would move it by tens). Four, not two: with a wider font the
    # reflow measured 3 px (2026-10-01).
    assert abs(d.splitter.height() - work_before) <= 4
    d.close()


def test_the_status_line_re_elides_on_resize_without_looping():
    # The elide depends on the width, so a resize must redo it; an
    # unguarded version of that looped until the process was killed by
    # memory (a label that changes its text re-lays the window out). This
    # test is a loop on purpose: if the guard goes, it hangs or dies here.
    _app()
    d = _dialog(1400, 900, _OBJECT)
    d.set_status("Serie: 142 puntos de 142 tomas, 4 heredadas")
    for width in (600, 1500, 800, 1200):
        d.resize(width, 900)
        _settle(d)
        assert "Serie" in d._ui.lbl_status_bar.text()
    assert d.status_text() == "Serie: 142 puntos de 142 tomas, 4 heredadas"
    d.close()


# ---------------- U2: the top bar's two doors -------------------------

def test_the_bar_keeps_the_daily_actions_and_opens_two_doors():
    # Eighteen items in the bar is a cockpit. What a visit needs is open,
    # export, solve (this plate), solve the visit (all its frames, next to
    # it: the pair explains itself), the two zooms that are used all the
    # time, the current factor and the page switch; the VIEW switches (they
    # are states, not actions) and the occasional zoom factors live behind
    # one door each.
    _app()
    d = _dialog(1400, 800, _OBJECT)
    bar = d._ui.topbar
    visible = [bar.itemAt(i).widget() for i in range(bar.count())
               if bar.itemAt(i).widget() is not None]
    names = [w.objectName() for w in visible]
    assert len(names) <= 11, names
    for must in ("btn_load", "btn_export", "btn_solve", "btn_solve_visit",
                 "btn_zoom_fit",
                 "btn_zoom_100", "btn_view", "btn_zoom_more", "lbl_zoom"):
        assert must in names, must
    # the two solve actions are side by side, and the visit one comes after
    assert names.index("btn_solve_visit") == names.index("btn_solve") + 1
    d.close()


def test_the_doors_hold_the_same_widgets_and_nothing_is_lost():
    # The doors are not deletions: every view switch and every zoom preset is
    # still its own widget, still connected, still reachable by its name, and
    # the door has one item per button that drives it. (It used to be a panel
    # with the widgets moved into it; that crashed Windows while the dialog
    # was being built, see gui/widgets/door_menu.py.)
    _app()
    d = _dialog(1400, 800, _OBJECT)
    assert [a.data() for a in d.btn_view.menu().actions()] == [
        "btn_north", "btn_scale", "btn_annot", "btn_boxes", "btn_mark"]
    assert [a.data() for a in d.btn_zoom_more.menu().actions()] == [
        "btn_zoom_50", "btn_zoom_200", "btn_zoom_400"]
    # the widgets are still there (hidden), and the item drives them
    assert not d.btn_north.isVisibleTo(d)
    seen = []
    d._ui.btn_zoom_50.clicked.connect(lambda: seen.append("zoom50"))
    d.btn_zoom_more.menu().actions()[0].trigger()
    assert seen == ["zoom50"]
    # and a checkable button's own state is the truth: the item follows it
    act = d.btn_view.menu().actions()[0]
    d.btn_north.setChecked(False)
    assert act.isChecked() is False
    d.btn_north.setChecked(True)
    assert act.isChecked() is True
    d.close()


# ---------------- E: the series' summary box, and its column ----------

def test_the_summary_box_keeps_its_room_and_its_column_scrolls():
    # Reported: "the Photometric Series text box is still small and has no
    # scroll". Measured before: the content of the Measure half needs 446 px;
    # in a 1000 px window the half got 471 (the box, 192 px) but at 800 px it
    # was clamped to 345, the box fell to its 160 px floor and the rest of
    # the form was cut off WITH NO WAY to reach it (a splitter cannot
    # scroll). Now the box has 200 px of room and the column scrolls.
    _app()
    for height in (1000, 800, 700, 600):
        d = _dialog(1400, height, _OBJECT)
        d.set_series_hook(lambda: {"pid": 1, "session_id": 2, "paths": []})
        d.show_tab("measure")
        _settle(d)
        box = d.tab_measure.lbl_result
        assert box.height() >= 200, (height, box.height())
        # the content is always reachable: either it fits, or the column
        # offers the bar (never clipped in silence)
        area = d.tab_photometry.area_measure
        fits = (d.tab_measure.minimumSizeHint().height()
                <= d.tab_measure.height())
        assert fits or area.verticalScrollBar().maximum() > 0, height
        d.close()


def test_the_measure_half_is_still_the_same_widget():
    # The scroll area is a wrapper, not a new hierarchy: the halves stay
    # the objects every other piece of code and every test reaches for.
    _app()
    d = _dialog(1200, 800, _OBJECT)
    ph = d.tab_photometry
    assert ph.area_measure.widget() is d.tab_measure
    assert ph.area_compare.widget() is d.tab_compare
    assert ph.splitter.widget(1) is ph.area_measure
    d.close()


# ---------------- U5: the ways out of a measurement -------------------

def test_the_result_row_keeps_two_doors_and_the_buttons_are_reachable():
    # Four buttons took two rows of the column: the CSV, the AAVSO EFF
    # report, "reset the plate's state" and "remove the plate's points".
    # They are not gone and they are not copies: the SAME widgets are the
    # items of two doors now (the export pair in "Export", the reset pair in
    # "Reset"), so every name the code and the tests reach for is untouched.
    _app()
    d = _dialog(1500, 1000, _OBJECT)
    t = d.tab_measure
    row = t._ui.row_result_actions
    in_row = [row.itemAt(i).widget().objectName() for i in range(row.count())
              if row.itemAt(i).widget() is not None]
    assert in_row == ["btn_manual_mag", "btn_export_more", "btn_reset_more",
                    "btn_save_project"]
    assert [a.data() for a in t.btn_export_more.menu().actions()] == [
        "btn_csv", "btn_eff"]
    assert [a.data() for a in t.btn_reset_more.menu().actions()] == [
        "btn_reset_state", "btn_reset_points"]
    # the buttons are the same widgets, alive and hidden
    for btn in (t.btn_csv, t.btn_eff, t.btn_reset_state, t.btn_reset_points):
        assert not btn.isVisibleTo(t)
    # and the two rows that used to hold them are not left behind empty
    assert not hasattr(t._ui, "row_export")
    assert not hasattr(t._ui, "row_project")
    d.close()


def test_the_reset_door_comes_and_goes_with_the_project():
    # The plate's two resets only make sense inside a project (ADR-047).
    # The door follows them: without the hooks the row must not keep a
    # "Reset" that opens onto nothing, and with them it must be there and
    # live. The two buttons live INSIDE the door, so what changes is whether
    # their items are enabled, not whether the widgets show: showing them put
    # them floating over the window (reported 2026-10-01).
    _app()
    d = _dialog(1500, 1000, _OBJECT)
    t = d.tab_measure
    t.setEnabled(True)             # a plate is behind: the tab is live
    t.set_reset_attached(True)
    assert not t.btn_reset_more.isHidden()
    # what the observer reads is the door: its two items are live
    items = {a.data(): a for a in t.btn_reset_more.menu().actions()}
    assert items["btn_reset_state"].isEnabled()
    assert items["btn_reset_points"].isEnabled()
    # and the buttons themselves can never show: they live inside the door's
    # hidden holder, so the product's own setVisible(True) does not put them
    # over the window (reported 2026-10-01: one came out floating and read as
    # a duplicate)
    assert not t.btn_reset_state.isVisible()
    assert not t.btn_reset_points.isVisible()
    t.set_reset_attached(False)
    assert t.btn_reset_more.isHidden()
    assert not items["btn_reset_state"].isEnabled()
    assert not items["btn_reset_points"].isEnabled()
    d.close()
