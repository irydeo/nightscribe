############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the Unified FITS Editor dialog (ADR-044)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_dialog.py: the layout (top bar, dominant
image, one tab per feature, histogram strip), load and error paths with
file dialogs stubbed, the histogram Invert mirroring the state, zoom
presets, PNG export and the add_feature_tab extension API. No network.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = Path(__file__).parents[1] / "fixtures"
MONO = FIXTURES / "sn2026zji_new_image.fits"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture
def dlg(qapp):
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    yield d
    d.view._render_timer.stop()   # never fire on a deleted widget
    d.deleteLater()


def test_layout_three_placeholder_tabs(dlg):
    assert dlg.tabs.count() == 3          # Blink, Photometry, Annotate
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Blink", "Photometry", "Annotate"]
    assert dlg.histogram is not None      # the phase-B histogram strip
    # the image dominates: at 1280 px the view is wider than the tab column
    assert dlg.view.width() > dlg.tabs.width()


def test_buttons_disabled_until_a_plate_lands(dlg):
    assert not dlg.btn_export.isEnabled()
    assert not dlg.histogram.btn_invert.isEnabled()
    dlg.state.load(MONO)
    assert dlg.btn_export.isEnabled()
    assert dlg.histogram.btn_invert.isEnabled()


def test_load_via_dialog_updates_title_state(dlg):
    dlg.state.load(MONO)
    assert dlg.state.has_image
    assert dlg.view._pix_item is not None


def test_invert_mirrors_state_via_the_histogram(dlg):
    # Invert lives in the histogram strip, with the other stretch
    # controls; the strip's button mirrors the state
    dlg.state.load(MONO)
    dlg.histogram.btn_invert.setChecked(True)
    assert dlg.state.inverted
    # loading a fresh plate resets the inversion and the button
    dlg.state.load(MONO)
    assert not dlg.state.inverted
    assert not dlg.histogram.btn_invert.isChecked()


def test_zoom_preset_buttons(dlg, qapp):
    dlg.state.load(MONO)
    dlg.btn_zoom["100"].click()
    assert dlg.view.transform().m11() == pytest.approx(1.0)
    dlg.btn_zoom["400"].click()
    assert dlg.view.transform().m11() == pytest.approx(4.0)
    dlg.btn_zoom["Fit"].click()
    assert 0 < dlg.view.transform().m11() < 1.0


def test_load_error_shows_a_warning(dlg, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    seen = []
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k:
                                     (str(FIXTURES / "bogus.fits"), "")))
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.append(a))
    dlg._on_load()
    assert seen                       # the error surfaced in a box
    assert not dlg.state.has_image    # and no plate was adopted


def test_load_cancel_keeps_state(dlg, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    dlg._on_load()
    assert not dlg.state.has_image


def test_export_png_via_dialog(dlg, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    dlg.state.load(MONO)
    out = tmp_path / "export.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    dlg._on_export_png()
    assert out.exists() and out.stat().st_size > 0


def test_add_feature_tab_is_the_whole_extension_api(dlg):
    from PySide6.QtWidgets import QLabel
    idx = dlg.add_feature_tab("Future", QLabel("soon"))
    assert dlg.tabs.count() == 4
    assert dlg.tabs.tabText(idx) == "Future"


def _fire(dlg, seq):
    # The offscreen QPA never delivers window-activation, so synthetic
    # key events cannot reach the shortcut map; emitting the registered
    # shortcut's signal exercises the same wiring (the house's other
    # shortcuts, Ctrl+1..4 in main_window, share this blind spot).
    from PySide6.QtGui import QKeySequence, QShortcut
    for sc in dlg.findChildren(QShortcut):
        if sc.key() == QKeySequence(seq):
            sc.activated.emit()
            return True
    return False


def test_keyboard_shortcuts_registered_and_wired(dlg):
    dlg.state.load(MONO)
    assert _fire(dlg, "1")
    assert dlg.view.transform().m11() == pytest.approx(1.0)
    assert _fire(dlg, "+")
    assert dlg.view.transform().m11() == pytest.approx(1.5)
    assert _fire(dlg, "-")
    assert dlg.view.transform().m11() == pytest.approx(1.0)
    assert _fire(dlg, "F")
    assert 0 < dlg.view.transform().m11() < 1.0
    # arrows pan a quarter viewport per press
    dlg.view.fit_to_factor(4.0)
    h0 = dlg.view.horizontalScrollBar().value()
    assert _fire(dlg, "Right")
    assert dlg.view.horizontalScrollBar().value() - h0 > 100
    # the load/export shortcuts exist too
    for seq in ("Ctrl+O", "Ctrl+E", "=", "Left", "Up", "Down"):
        from PySide6.QtGui import QKeySequence, QShortcut
        assert any(sc.key() == QKeySequence(seq)
                   for sc in dlg.findChildren(QShortcut))


def test_zoom_keys_noop_on_empty_state(dlg):
    assert _fire(dlg, "1")              # registered...
    assert dlg.view._pix_item is None   # ...but nothing to zoom


def test_zoom_label_follows_the_view(dlg):
    dlg.state.load(MONO)
    dlg.view.fit_to_factor(2.0)
    assert dlg.lbl_zoom.text() == "200 %"


def test_title_carries_the_file_name(dlg):
    assert dlg.windowTitle() == "NightScribe Image Workbench"
    dlg.state.load(MONO)
    assert "sn2026zji_new_image.fits" in dlg.windowTitle()
    assert dlg.windowTitle().startswith("NightScribe Image Workbench")


def test_keep_stretch_checkbox_drives_the_state(dlg):
    dlg.state.load(MONO)
    dlg.state.set_stretch(black=3000.0, white=9000.0)
    dlg.histogram.chk_keep.setChecked(True)
    assert dlg.state.keep_stretch
    dlg.state.load(MONO)
    assert dlg.state.black == 3000.0 and dlg.state.white == 9000.0


def test_accessible_names(dlg):
    assert dlg.view.accessibleName()
    assert dlg.histogram.canvas.accessibleName()
    assert dlg.histogram.spn_black.accessibleName()


_FAKE_CARDS = {"CRVAL1": 300.0, "CRVAL2": 60.0, "CRPIX1": 8.0,
               "CRPIX2": 8.0, "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
               "CD1_1": -0.0003, "CD1_2": 0.0, "CD2_1": 0.0,
               "CD2_2": 0.0003}


def test_hud_buttons_follow_the_wcs(dlg, tmp_path):
    from test_fits_annotate import _make_fits
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    assert not dlg.btn_north.isEnabled()           # no WCS: no HUD toggles
    assert not dlg.btn_scale.isEnabled()
    assert dlg.btn_solve.isEnabled()               # but solving is offered
    dlg.state.load(MONO)
    assert dlg.btn_north.isEnabled() and dlg.btn_scale.isEnabled()
    dlg.btn_north.setChecked(False)
    assert not dlg.view.show_north                 # button drives the HUD


def test_solve_without_api_key_explains(dlg, monkeypatch):
    # No key and no ASTAP binary: the solve would go to nova, so the
    # guard explains (the resolver is pinned: a real ASTAP on PATH must
    # not change what this test sees).
    from nightscribe import config
    from nightscribe.core.sources import astap
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setattr(config.config, "get",
                        lambda *a, **k: "")
    monkeypatch.setattr(astap, "resolve_binary", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: seen.append(a))
    dlg.state.load(MONO)
    dlg._on_solve()
    assert seen                                     # pointed at Settings
    assert dlg._solve_worker is None


def test_solve_auto_with_astap_skips_the_nova_key(dlg, monkeypatch):
    # P1 #11 / ADR-051: with solver=auto and a resolvable ASTAP binary
    # the solve never demands a nova key; the worker starts straight
    # away (auto tries ASTAP first and only falls back to nova).
    from nightscribe import config
    from nightscribe.core.sources import astap
    from nightscribe.gui import workers
    from PySide6.QtWidgets import QMessageBox
    asked, started = [], []
    monkeypatch.setitem(config.config._data, "astrometry_key", "")
    monkeypatch.setitem(config.config._data, "solver", "auto")
    monkeypatch.setitem(config.config._data, "astap_path", "")
    monkeypatch.setattr(astap, "resolve_binary",
                        lambda *a, **k: "/fake/astap")
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: asked.append(a))

    class _Sig:
        def connect(self, *a):
            pass

    class _FakeWorker:                      # stands in for the QThread
        progress = _Sig()
        finished = _Sig()

        def __init__(self, path, pointing=None):
            pass

        def start(self):
            started.append(True)

    monkeypatch.setattr(workers, "UfeSolveWorker", _FakeWorker)
    dlg.state.load(MONO)
    dlg._on_solve()
    assert not asked                            # no API-key guard fired
    assert started and dlg._solve_worker is not None


def test_solve_nova_without_key_still_guards(dlg, monkeypatch):
    # The other half of P1 #11: solver forced to nova with no key, the
    # guard still fires even when an ASTAP binary exists (it is not
    # used), and no worker starts.
    from nightscribe import config
    from nightscribe.core.sources import astap
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setitem(config.config._data, "astrometry_key", "")
    monkeypatch.setitem(config.config._data, "solver", "astrometry")
    monkeypatch.setattr(astap, "resolve_binary",
                        lambda *a, **k: "/fake/astap")
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: seen.append(a))
    dlg.state.load(MONO)
    dlg._on_solve()
    assert seen
    assert dlg._solve_worker is None


def test_solved_cards_land_in_memory(dlg, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: None)
    dlg.state.load(MONO)
    old_scale = dlg.state.wcs.pixel_scale()
    dlg._on_solved(_FAKE_CARDS)                    # the worker's payload
    assert dlg.state.wcs.pixel_scale() != old_scale
    assert dlg.btn_solve.isEnabled()
    assert dlg.btn_solve.text() == "Solve astrometry…"


def test_solve_failure_warns(dlg, monkeypatch):
    # The failure message names the solver(s) that ran (P1 #11): with
    # "auto" that is ASTAP first and nova as the fallback.
    from nightscribe import config
    from PySide6.QtWidgets import QMessageBox
    seen = []
    monkeypatch.setitem(config.config._data, "solver", "auto")
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.append(a))
    dlg.state.load(MONO)
    dlg._on_solved({})
    assert seen
    assert "ASTAP" in seen[0][2] and "Astrometry.net" in seen[0][2]


# -------------------------------------------- the plate's band (ADR-046 rev.)

def test_the_band_provider_reads_the_live_state(dlg, monkeypatch):
    # Name: the plate's stem when nothing else speaks, and the attached
    # object wins over it. Date, exposure, filter and kit come from the
    # frame itself. The position is placed by the plate's own solution (in
    # the ink colour) and the magnitude is only the session's measurement:
    # a catalogue value wears its own colour and SAYS it is one.
    from nightscribe.config import config
    monkeypatch.setitem(config._data, "mpc_code", "Z41")
    assert dlg._chart_band() == {"lines": []}     # no plate, nothing to say
    dlg.state.load(MONO)
    first, second = dlg._chart_band()["lines"]
    assert first[0]["text"] == "sn2026zji_new_image"
    assert first[0]["role"] == "name"
    assert "2026-08-21 20:54 UT" in second[0]["text"]
    ctx = " · ".join(seg["text"] for seg in second)
    assert "10.0 s" in ctx and "Z41" in ctx
    # solved plate: scale and field are there; the position waits for a
    # known object (a field centre is not the object)
    assert any(seg["field"] == "psc" for seg in second)
    assert any(seg["field"] == "fov" for seg in second)
    assert not any(seg["field"] == "pos" for seg in first)
    assert not any(seg["field"] == "mag" for seg in first)
    # the attached object wins the name, pins the position (this plate's
    # own solution places it) and adds the CATALOGUE magnitude
    from nightscribe.core import coords
    cra, cdec = dlg.state.wcs.center()
    dlg.set_object({"name": "AT 2026zji", "ra": cra, "dec": cdec,
                    "mag": 17.1})
    first = dlg._chart_band()["lines"][0]
    assert first[0]["text"] == "AT 2026zji"
    pos = next(seg for seg in first if seg["field"] == "pos")
    assert pos["role"] == "pos"
    assert coords.ra_deg_to_hms(cra)[:8] in pos["text"]
    cat = next(seg for seg in first if seg["field"] == "mag")
    assert cat["role"] == "mag-cat" and cat["text"].endswith(" cat")
    # a calibrated measurement THIS session beats it, in the measured colour
    # a CLEAN measurement of this plate: error under 0.05, more than the
    # minimum comparisons and a check star that passes (three comps alone
    # would already be the orange "usable but not clean")
    dlg.tab_measure._last = {"mag": 16.391, "err": 0.04, "band": "V",
                             "col": 100.0, "row": 200.0,
                             "used": [1, 2, 3, 4, 5],
                             "check": {"ok": True}}
    first = dlg._chart_band()["lines"][0]
    mag = next(seg for seg in first if seg["field"] == "mag")
    assert mag["role"] == "mag"
    assert mag["text"] == "16.39 ± 0.04 (V)"
    # ... and the position now speaks from the measured centroid
    ra, dec = dlg.state.wcs.pixel_to_sky(100.0, 200.0)
    pos = next(seg for seg in first if seg["field"] == "pos")
    assert coords.ra_deg_to_hms(ra)[:8] in pos["text"]
    # a doubtful measurement wears the warning colour (the numbers decide)
    dlg.tab_measure._last = {"mag": 16.391, "err": 0.30, "band": "V",
                             "col": 100.0, "row": 200.0,
                             "used": [1, 2, 3, 4, 5]}
    first = dlg._chart_band()["lines"][0]
    assert next(seg for seg in first
                if seg["field"] == "mag")["role"] == "mag-doubt"


def test_the_band_says_nothing_without_a_plate(dlg):
    dlg.state.clear()
    assert dlg._chart_band() == {"lines": []}


def test_the_band_toggle_default_comes_from_config(dlg, monkeypatch):
    # The plate's band says what it says by default (chart_data): the
    # corner boxes' own switch (chart_boxes) belongs to the OTHER charts
    # (the blink and the finder), which keep them.
    from nightscribe.config import config
    monkeypatch.setitem(config._data, "chart_data", False)
    dlg.hide()
    dlg.show()                          # showEvent re-reads the default
    assert not dlg.btn_boxes.isChecked()
    assert not dlg.view.show_data
    monkeypatch.setitem(config._data, "chart_data", True)
    dlg.hide()
    dlg.show()
    assert dlg.btn_boxes.isChecked()
    assert dlg.view.show_data


# ------------------------------------- top-bar style (ADR-044 rev, 2026-09-24)


def test_topbar_icons_only_is_the_default(dlg):
    # Pinned ufe_bar_icons: True -> a compact glyph bar. The short
    # actions drop their labels entirely; Solve keeps its own in both
    # modes, because the action is long and the glyph only hints at it.
    from PySide6.QtGui import QIcon
    from nightscribe.gui import theme
    # U2: the rule has a second half. The bar's own buttons drop their
    # labels (a glyph and its tooltip); the ones that live inside the
    # "View" and "Zoom" panels KEEP them, because an icon with no label in
    # a dropdown is a riddle.
    for name in ("btn_load", "btn_export"):
        btn = getattr(dlg, name)
        assert btn.text() == ""
        assert not btn.icon().isNull()
    for name in ("btn_north", "btn_scale", "btn_annot", "btn_boxes",
                 "btn_mark"):
        btn = getattr(dlg, name)
        assert btn.text() != ""              # in the View panel, labelled
        assert not btn.icon().isNull()
    # the checked toggles sit on the _on glyph (they start checked)
    want = QIcon(str(theme.asset("ufe_north_on.svg"))).pixmap(16, 16)
    assert dlg.btn_north.icon().pixmap(16, 16).toImage() == \
        want.toImage()
    assert dlg.btn_solve.text() == "Solve astrometry…"
    assert dlg.lbl_zoom_hint.isVisible() == False
    for label, btn in dlg.btn_zoom.items():
        assert not btn.icon().isNull()
        # Fit and 100 % are in the bar (no label), 50/200/400 in the panel
        assert btn.text() == ("" if label in ("Fit", "100") else label)


def test_topbar_text_mode_restores_the_labels(dlg, monkeypatch):
    from PySide6.QtGui import QIcon
    from nightscribe.config import config
    from nightscribe.gui import theme
    # The same cached dialog reskins between shows: text mode brings the
    # labels back (icon stays as a hint), icon mode puts them away again.
    monkeypatch.setitem(config._data, "ufe_bar_icons", False)
    dlg.hide()
    dlg.show()
    assert dlg.btn_load.text() == "Load FITS…"
    assert dlg.btn_north.text() == "N"
    assert dlg.btn_scale.text() == "Scale"
    assert dlg.btn_annot.text() == "A"
    assert dlg.btn_boxes.text() == "Data"
    assert dlg.btn_mark.text() == "Mark"
    assert dlg.btn_solve.text() == "Solve astrometry…"   # unchanged either way
    assert dlg.lbl_zoom_hint.isVisible()
    assert dlg.btn_zoom["100"].text() == "100"
    assert not dlg.btn_zoom["100"].icon().isNull()
    monkeypatch.setitem(config._data, "ufe_bar_icons", True)
    dlg.hide()
    dlg.show()
    assert dlg.btn_load.text() == ""
    assert dlg.btn_zoom["Fit"].text() == ""      # Fit stays in the bar
    # ...while the ones behind the doors keep their words (U2)
    assert dlg.btn_north.text() == "N"
    assert dlg.btn_zoom["50"].text() == "50"
    # a checked-state flip re-skins the glyph in icon mode
    dlg.btn_north.setChecked(False)
    off = QIcon(str(theme.asset("ufe_north_off.svg"))).pixmap(16, 16)
    assert dlg.btn_north.icon().pixmap(16, 16).toImage() == off.toImage()
    dlg.btn_north.setChecked(True)


def test_topbar_missing_asset_keeps_the_text(dlg, monkeypatch):
    # The SVG is missing: the button must not go silent.
    from pathlib import Path
    from nightscribe.gui import theme
    monkeypatch.setattr(
        theme, "asset",
        staticmethod(lambda name: Path("/nonexistent") / name))
    dlg.hide()
    dlg.show()
    assert dlg.btn_load.text() == "Load FITS…"
    assert dlg.btn_load.icon().isNull()
    assert dlg.btn_zoom["100"].text() == "100"
    # and the toggle re-skin silently does nothing with no asset
    dlg.btn_north.setChecked(False)
    assert dlg.btn_north.text() == "N"


# ADR-044 rev 2026-09-25: the Sequence section's own amber target mark
# (and the bar's «Move marker…») went away; the dialog's global red
# object mark (btn_mark) is the one object marker now.


def test_move_marker_is_gone_and_the_object_mark_covers_it(dlg):
    assert not hasattr(dlg, "btn_move")
    comp = dlg.tab_photometry.tab_compare
    assert not hasattr(comp, "chk_target")
    assert not hasattr(comp, "_target_pos")
    assert not hasattr(comp, "request_target_move")
    # the global mark follows set_object and the bar toggle
    dlg.state.load(MONO)
    w, h = dlg.state.plate_shape
    ra, dec = dlg.state.wcs.pixel_to_sky(w / 2.0, h / 2.0)
    dlg.set_object({"name": "SN test", "ra": ra, "dec": dec})
    assert dlg.btn_mark.isEnabled()
    assert len(dlg.view._object_mark_items) == 5
    dlg.btn_mark.setChecked(False)
    assert all(not it.isVisible() for it in dlg.view._object_mark_items)
    dlg.set_object(None)
    assert not dlg.btn_mark.isEnabled()
    assert dlg.view._object_mark_items == []


# ------------------------------------------- auto-solve + persistence (ADR-051 rev.)

def test_request_wcs_runs_now_when_solved(dlg):
    from test_fits_annotate import _make_fits
    import tempfile
    from pathlib import Path as _P
    # MONO already carries a WCS: the action runs at once, no worker
    dlg.state.load(MONO)
    seen = []
    dlg.request_wcs(lambda: seen.append(True))
    assert seen == [True] and dlg._wcs_pending == []


def test_request_wcs_queues_and_drains_on_solve(dlg, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from test_fits_annotate import _make_fits
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    ran = []
    dlg.request_wcs(lambda: ran.append("after"),
                    on_fail=lambda: ran.append("fail"))
    assert ran == [] and len(dlg._wcs_pending) == 1
    dlg._on_solved(_FAKE_CARDS)
    assert ran == ["after"]
    assert dlg._wcs_pending == []


def test_request_wcs_failure_calls_on_fail(dlg, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from test_fits_annotate import _make_fits
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    ran = []
    dlg.request_wcs(lambda: ran.append("after"),
                    on_fail=lambda: ran.append("fail"))
    dlg._on_solved({})                       # the solve failed
    assert ran == ["fail"]
    assert dlg._wcs_pending == []


def test_solved_cards_are_persisted_into_the_fits(dlg, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from nightscribe import config
    from nightscribe.core import fits_io
    from test_fits_annotate import _make_fits
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setitem(config.config._data, "solve_save", True)
    plate = _make_fits(tmp_path / "plain.fits")
    dlg.state.load(plate)
    dlg._on_solved(_FAKE_CARDS)
    header = fits_io.read_header(plate)
    assert header["CRVAL1"] == pytest.approx(300.0)   # saved solved
    assert header["CTYPE1"] == "RA---TAN"


def test_persist_failure_keeps_the_wcs_in_memory(dlg, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core import wcs_store
    from test_fits_annotate import _make_fits
    warns = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: warns.append(a))
    monkeypatch.setattr(wcs_store, "persist_solution",
                        lambda *a, **k: (False, "read-only file"))
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    dlg._on_solved(_FAKE_CARDS)
    assert dlg.state.wcs is not None          # the session keeps working
    assert warns                              # and the observer is told


# ---------------------------------------------- maximize / bars (ADR-051 rev.)

def test_workbench_can_be_maximized(dlg):
    from PySide6.QtCore import Qt
    flags = dlg.windowFlags()
    assert flags & Qt.WindowMaximizeButtonHint
    assert flags & Qt.WindowMinimizeButtonHint


def test_the_width_goes_to_the_plate_not_to_the_form(dlg):
    # Reported: maximizing the window grew the right column (the tabs) and
    # the plate stayed in the middle with two fat margins. The plate is
    # what the window is FOR: the sides keep the width they need and the
    # centre takes every extra pixel.
    from PySide6.QtWidgets import QApplication
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2, "paths": []})
    QApplication.processEvents()
    sizes = {}
    for width in (1000, 1700, 2400):
        dlg.resize(width, 900)
        for _ in range(3):
            QApplication.processEvents()
        sizes[width] = (dlg.series_pane.width(), dlg.view.width(),
                        dlg.tabs.width())
    # the visit pane and the tab column keep their width...
    assert sizes[1000][0] == sizes[2400][0]
    assert sizes[1000][2] == sizes[2400][2]
    # ...and the plate takes the 1400 px the window gained
    assert sizes[2400][1] - sizes[1000][1] == 1400
    # and the tab column is capped, so a 4K window does not give it a
    # runway either
    assert dlg.tabs.maximumWidth() <= 600


def test_series_pane_is_not_capped(dlg):
    assert dlg.series_pane.maximumWidth() > 1000


def test_refit_on_state_change_respects_a_manual_zoom(dlg, monkeypatch):
    dlg.state.load(MONO)                    # has_image
    calls = []
    monkeypatch.setattr(dlg.view, "fit_to_scene",
                        lambda *a, **k: calls.append(1))
    dlg.view._user_zoomed = True
    dlg._refit_on_state_change()
    assert calls == []                      # an inspection zoom is kept
    dlg.view._user_zoomed = False
    dlg._refit_on_state_change()
    assert calls == [1]


# ------------------------------------- visit frames + EXOTIC block (ADR-048 follow-up)

def test_frame_navigator_steps_through_the_visit(dlg, tmp_path):
    from test_fits_annotate import _make_fits
    a = _make_fits(tmp_path / "a.fits")
    b = _make_fits(tmp_path / "b.fits")
    c = _make_fits(tmp_path / "c.fits")
    dlg.set_series_hook(lambda: {"paths": [str(a), str(b), str(c)],
                                 "kind": "transit"})
    dlg.open_plate(a)
    assert dlg.visit_panel.lbl_frame.text() == "Frame 1/3"
    assert not dlg.visit_panel.btn_frame_prev.isEnabled()
    assert dlg.visit_panel.btn_frame_next.isEnabled()
    dlg._frame_next()
    assert dlg.visit_panel.lbl_frame.text() == "Frame 2/3"
    assert dlg.visit_panel.lbl_frame_file.text() == "b.fits"
    dlg._frame_next()
    assert dlg.visit_panel.lbl_frame.text() == "Frame 3/3"
    assert not dlg.visit_panel.btn_frame_next.isEnabled()
    dlg._frame_prev()
    dlg._frame_first()
    assert dlg.visit_panel.lbl_frame.text() == "Frame 1/3"


def test_frame_navigator_keeps_the_compare_state(dlg, tmp_path, monkeypatch):
    from test_fits_annotate import _make_fits
    a = _make_fits(tmp_path / "a.fits")
    b = _make_fits(tmp_path / "b.fits")
    dlg.set_series_hook(lambda: {"paths": [str(a), str(b)], "kind": "transit"})
    seen = {}
    monkeypatch.setattr(dlg.tab_photometry, "capture_state",
                        lambda: seen.setdefault("captured", {"sequence": {}}))
    monkeypatch.setattr(dlg.tab_photometry, "apply_state",
                        lambda st: seen.setdefault("applied", st))
    dlg.open_plate(a)
    dlg._frame_next()
    assert "captured" in seen and "applied" in seen
    assert dlg.visit_panel.lbl_frame.text() == "Frame 2/2"


def test_exotic_block_only_for_transit_with_a_sequence(dlg, tmp_path,
                                                       monkeypatch):
    from test_fits_annotate import _make_fits
    a = _make_fits(tmp_path / "a.fits")
    calls = []
    dlg.set_exotic_hooks(lambda: calls.append("r"), lambda: calls.append("e"))
    assert not dlg.visit_panel.grp_exotic.isVisible()      # no visit yet
    dlg.set_series_hook(lambda: {"paths": [str(a)], "kind": "transit"})
    assert dlg.visit_panel.grp_exotic.isVisible()
    # no sequence yet: the buttons wait and the line says why
    assert not dlg.visit_panel.btn_exotic_reduce.isEnabled()
    assert "sequence" in dlg.visit_panel.lbl_exotic_status.text().lower()
    # a sequence lands: the block enables and the hooks fire
    monkeypatch.setattr(dlg.tab_compare, "entries",
                        lambda: [{"name": "A", "kind": "comp", "star": {}}])
    dlg.tab_compare.sequence_changed.emit()
    assert dlg.visit_panel.btn_exotic_reduce.isEnabled()
    dlg.visit_panel.btn_exotic_reduce.click()
    dlg.visit_panel.btn_exotic_export.click()
    assert calls == ["r", "e"]


def test_exotic_block_hidden_off_transit(dlg, tmp_path):
    from test_fits_annotate import _make_fits
    a = _make_fits(tmp_path / "a.fits")
    dlg.set_exotic_hooks(lambda: None, lambda: None)
    dlg.set_series_hook(lambda: {"paths": [str(a)], "kind": "variable"})
    assert not dlg.visit_panel.grp_exotic.isVisible()


def test_exotic_block_shows_the_last_reduction_and_opens_it(dlg, tmp_path):
    # The result of a reduction comes back to where it was launched from:
    # the line with the two numbers, and the whole result (figure, files)
    # one click away. No reduction yet: an empty line and dead buttons,
    # never zeros.
    from test_fits_annotate import _make_fits
    a = _make_fits(tmp_path / "a.fits")
    calls = []
    dlg.set_exotic_hooks(lambda: None, lambda: None,
                         result_fn=lambda: calls.append("result"),
                         folder_fn=lambda: calls.append("folder"),
                         result_text="T_mid 2458107.7146 ± 0.0011")
    dlg.set_series_hook(lambda: {"paths": [str(a)], "kind": "transit"})
    assert dlg.visit_panel.lbl_exotic_result.text() == \
        "T_mid 2458107.7146 ± 0.0011"
    assert dlg.visit_panel.btn_exotic_result.isEnabled()
    assert dlg.visit_panel.btn_exotic_folder.isEnabled()
    dlg.visit_panel.btn_exotic_result.click()
    dlg.visit_panel.btn_exotic_folder.click()
    assert calls == ["result", "folder"]
    # an empty summary (no reduction yet) disables both doors
    dlg.set_exotic_hooks(lambda: None, lambda: None,
                         result_fn=lambda: calls.append("result"),
                         folder_fn=lambda: calls.append("folder"))
    assert dlg.visit_panel.lbl_exotic_result.text() == ""
    assert not dlg.visit_panel.btn_exotic_result.isEnabled()
    assert not dlg.visit_panel.btn_exotic_folder.isEnabled()


def test_cancelled_solve_shows_no_failure_box(dlg, monkeypatch):
    # the busy dialog's Cancel: the queued action gets its way out, never
    # the misleading "could not solve the plate"
    from PySide6.QtWidgets import QMessageBox
    warns = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: warns.append(a))

    class _W:
        def cancelled(self):
            return True

    dlg._solve_worker = _W()
    fail = []
    dlg._wcs_pending = [(lambda: None, lambda: fail.append(1))]
    dlg._on_solved({})
    assert warns == [] and fail == [1]


def test_notify_sequence_ignores_empty_unless_forced(dlg):
    seen = []
    dlg.set_sequence_hook(lambda st: seen.append(st))
    assert dlg.notify_sequence({"entries": []}) is False
    assert dlg.notify_sequence({"entries": []}, force=True) is True
    assert dlg.notify_sequence({"entries": [{"name": "A"}]}) is True
    assert len(seen) == 2


# ---------------- where the plate looks (ADR-051) ---------------------

def test_the_solve_carries_where_the_project_looks(dlg, monkeypatch):
    # The frames of a real visit carry no position of their own (the V0526
    # Per ones have FOCALLEN=0 and no RA/DEC), and without a pointing ASTAP
    # sweeps the sky: measured, 66 s per frame against 0.13 s with it. The
    # window already knows the field: it is the object it was opened from.
    from nightscribe.core.sources import astap
    monkeypatch.setattr(astap, "resolve_binary", lambda *a, **k: "/fake/astap")
    dlg.state.load(MONO)
    dlg.set_object({"name": "V0526 Per", "ra": 49.99038, "dec": 49.86875})
    dlg._on_solve()
    assert dlg._solve_worker is not None
    assert dlg._solve_worker.pointing == (49.99038, 49.86875)


def test_an_ad_hoc_plate_still_solves_blind(dlg, monkeypatch):
    # Opened from the Tools menu there is no project behind it: nothing is
    # invented (the header's own RA is ambiguous: hours in OBJCTRA, degrees
    # in CRVAL1), so ASTAP is left to sweep, as it always was.
    from nightscribe.core.sources import astap
    monkeypatch.setattr(astap, "resolve_binary", lambda *a, **k: "/fake/astap")
    dlg.state.load(MONO)
    dlg.set_object(None)
    dlg._on_solve()
    assert dlg._solve_worker is not None
    assert dlg._solve_worker.pointing is None


def test_the_busy_line_speaks_about_the_solve(dlg):
    # The solver's stages in the observer's words (the raw search output no
    # longer reaches this line at all: see the astap tests), and its own
    # lines still come through as they are.
    dlg._on_solve_stage("astap:blind")
    assert "sweeping the sky" in dlg.btn_solve.text()
    dlg._on_solve_stage("astap:pointed")
    assert "project's field" in dlg.btn_solve.text()
    dlg._on_solve_stage("login")
    assert "Astrometry.net" in dlg.btn_solve.text()
    dlg._on_solve_stage("Warning scale was inaccurate! Set FOV=0.54d")
    assert dlg.btn_solve.text().startswith("Warning scale")


def test_a_blind_failure_explains_itself(dlg, monkeypatch):
    # The plate carries no position and the editor was opened from nowhere:
    # that is WHY the solver had to search the whole sky. Saying it is the
    # difference between a mystery and an instruction.
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.core.sources import astap
    monkeypatch.setattr(astap, "resolve_binary", lambda *a, **k: "/fake/astap")
    seen = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: seen.append(a[2]))
    dlg.state.load(MONO)
    dlg.set_object(None)
    dlg._on_solve()
    dlg._on_solved({})
    assert seen and "whole sky" in seen[0]
    # with a project behind it, no excuse is invented
    seen.clear()
    dlg.set_object({"name": "V0526 Per", "ra": 49.99038, "dec": 49.86875})
    dlg._on_solve()
    dlg._on_solved({})
    assert seen and "whole sky" not in seen[0]


# ---------------- solving the whole visit (ADR-051) -------------------

def _visit(dlg, paths, context=None):
    ctx = {"pid": 1, "session_id": 2, "paths": [str(p) for p in paths]}
    if context:
        ctx["context"] = context
    dlg.set_series_hook(lambda scope="visit": ctx)


def test_the_visit_solve_button_needs_frames_and_the_write_option(
        dlg, monkeypatch):
    # A batch leaves the visit solved ON DISK: with "save the solved WCS in
    # the FITS" off, the 35 solutions would die with the session, so the
    # button says why instead of doing a useless job.
    from nightscribe.config import config
    btn = dlg.btn_solve_visit                 # in the top bar, with Solve
    _visit(dlg, [])
    assert not btn.isEnabled()
    # and with nothing to solve it is not even shown: it is prep for the
    # visit's PRODUCTS (the astrometry report and EXOTIC), not a step of
    # the measurement, and an always-there dead button is what made the
    # observer ask "no entiendo qué hace ahí"
    assert btn.isHidden()
    _visit(dlg, [MONO, MONO])
    assert not btn.isHidden()
    monkeypatch.setitem(config._data, "solve_save", True)
    dlg._sync_visit_solve()
    assert btn.isEnabled()
    monkeypatch.setitem(config._data, "solve_save", False)
    dlg._sync_visit_solve()
    assert not btn.isEnabled()
    assert "Settings" in btn.toolTip()


def test_solving_a_visit_without_frames_says_so(dlg):
    dlg.set_series_hook(None)
    dlg._on_solve_visit()
    assert "not opened from a visit" in dlg.status_text()


def test_solving_the_visit_reports_and_hands_the_open_frame_its_wcs(
        dlg, monkeypatch, tmp_path):
    # The batch writes each solution into its file; the frame OPEN in the
    # editor needs its cards in memory too, and the observer needs a count
    # they can trust.
    from nightscribe.config import config
    from nightscribe.gui import workers
    from PySide6.QtCore import QObject, Signal

    monkeypatch.setitem(config._data, "solve_save", True)
    frames = [tmp_path / "a.fits", tmp_path / "b.fits"]
    for f in frames:
        f.write_bytes(b"x")
    _visit(dlg, frames, context={"ra_deg": 49.99038, "dec_deg": 49.86875})

    class _Worker(QObject):
        progress = Signal(int, int, str)
        finished = Signal(object)
        failed = Signal(str)

        def __init__(self, paths, pointing=None, open_path=None):
            super().__init__()
            self.paths = list(paths)
            self.pointing = pointing
            self.open_path = open_path

        def start(self):
            self.finished.emit({
                "solved": 1, "skipped": 1, "failed": 0, "not_written": 0,
                "failures": [], "cancelled": False,
                "cards": {"CRVAL1": 49.9937, "CRVAL2": 49.7802,
                          "CRPIX1": 832.0, "CRPIX2": 626.5,
                          "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
                          "CD1_1": -0.000427, "CD1_2": 4.9e-05,
                          "CD2_1": -4.9e-05, "CD2_2": -0.000427}})

        def isRunning(self):
            return False

        def cancel(self):
            pass

    made = []
    monkeypatch.setattr(workers, "VisitSolveWorker",
                        lambda *a, **kw: (made.append(_Worker(*a, **kw)) or
                                          made[-1]))
    dlg.state.load(MONO)
    dlg._on_solve_visit()
    assert made and made[0].pointing == (49.99038, 49.86875)
    assert "1 frames solved" in dlg.status_text()
    assert dlg.state.wcs is not None              # the open frame got it


def test_a_visit_without_coordinates_is_solved_from_its_first_frame(
        dlg, monkeypatch, tmp_path):
    # The project knows nothing: the batch is still worth running, because
    # the first frame's own solution points the rest (a minute once, not
    # an hour). It is said before starting.
    from nightscribe.config import config
    from nightscribe.gui import workers
    from PySide6.QtCore import QObject, Signal

    monkeypatch.setitem(config._data, "solve_save", True)
    f = tmp_path / "a.fits"
    f.write_bytes(b"x")
    _visit(dlg, [f])
    dlg.set_object(None)

    class _Worker(QObject):
        progress = Signal(int, int, str)
        finished = Signal(object)
        failed = Signal(str)

        def __init__(self, *a, **kw):
            super().__init__()
            self.pointing = kw.get("pointing")

        def start(self):
            pass

        def isRunning(self):
            return False

        def cancel(self):
            pass

    made = []
    monkeypatch.setattr(workers, "VisitSolveWorker",
                        lambda *a, **kw: (made.append(_Worker(*a, **kw)) or
                                          made[-1]))
    dlg._on_solve_visit()
    assert made and made[0].pointing is None
    assert "first frame" in dlg.status_text()


def test_the_band_colours_the_measurement_of_this_frame(dlg):
    # The observer asked for the scale: GREEN clean, ORANGE usable but not
    # clean, RED not worth reporting without looking, WHITE the catalogue.
    # And the measurement shown is the one made on THIS frame (the visit's
    # curve), not the catalogue's value.
    from nightscribe.core import fits_meta
    dlg.state.load(MONO)
    dlg.set_object({"name": "AT 2026zji", "ra": 20.0, "dec": 62.0,
                    "mag": 17.1})
    tab = dlg.tab_measure
    meta = fits_meta.meta_from_header(dlg.state.header or {})

    def mag_role():
        first = dlg._chart_band()["lines"][0]
        return next(seg for seg in first if seg["field"] == "mag")

    point = {"mjd": meta["mjd"], "mag": 16.50, "err": 0.04, "filter": "V",
             "source": "measure", "path": str(MONO), "comps": 5, "flags": []}
    tab._series_payload = [point]
    seg = mag_role()
    assert seg["role"] == "mag" and "16.50" in seg["text"]
    point["comps"] = 3                     # the minimum: usable, not clean
    assert mag_role()["role"] == "mag-fair"
    point["comps"] = 5
    point["err"] = 0.30                    # not worth reporting unwatched
    assert mag_role()["role"] == "mag-doubt"
    # with no measurement at all the catalogue's value is shown, in white
    tab._series_payload = []
    tab._last = None
    seg = mag_role()
    assert seg["role"] == "mag-cat" and seg["text"].endswith(" cat")


# ---------------- the band reflects every change (asked) --------------

def _band_strip(dlg):
    # @return: a hash of the TOP STRIP of the painted plate: the band and
    #          nothing else (the measurement's rings, the object's mark and
    #          the compass all live below it), so a change here can only be
    #          the band's own pixels.
    #          The plate's render is COALESCED by a timer and the band is
    #          painted on a repaint, so the window is given a moment to
    #          arrive: measuring before that is measuring the old frame (the
    #          first version of this test read the previous plate).
    import hashlib
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(250, loop.quit)
    loop.exec()
    img = dlg.view.grab().toImage()
    h = min(60, img.height())
    return hashlib.sha1(bytes(img.copy(0, 0, img.width(), h).bits())
                        ).hexdigest()


def _band_mag(dlg):
    # @return: the magnitude's segment of the band
    first = dlg._chart_band()["lines"][0]
    return next(seg for seg in first if seg["field"] == "mag")


def test_the_band_repaints_whenever_the_magnitude_changes(dlg, tmp_path):
    # Asked: "check that every time the object's magnitude changes, it shows
    # in the band". The content is read WHEN IT PAINTS (no cache), so the
    # only thing that can go wrong is a missing repaint, and that is
    # invisible in the code: this compares the top strip of the painted plate
    # for every source of the magnitude, through the app's own paths.
    from nightscribe.core import fits_meta
    from nightscribe.core.series_measure import SeriesPoint, SeriesResult
    dlg.state.load(MONO)
    tab = dlg.tab_measure
    meta = fits_meta.meta_from_header(dlg.state.header or {})
    before = _band_strip(dlg)

    # 1 · the object's magnitude (the catalogue's value, in white)
    dlg.set_object({"name": "AT 2026zji", "ra": 20.0, "dec": 62.0,
                    "mag": 17.1})
    assert _band_mag(dlg)["role"] == "mag-cat"
    a = _band_strip(dlg)
    assert a != before                            # the band repainted
    dlg.set_object({"name": "AT 2026zji", "ra": 20.0, "dec": 62.0,
                    "mag": 15.0})
    b = _band_strip(dlg)
    assert b != a and "15.00" in _band_mag(dlg)["text"]

    # 2 · a series measured HERE (what a run does when it lands)
    point = SeriesPoint(index=0, path=str(MONO), mjd=meta["mjd"], mag=11.11,
                        err=0.03, exptime=10.0, n_comps=6, filter="V",
                        flags=[])
    tab._series_result = SeriesResult(points=[point])
    tab._draw_series([point])
    c = _band_strip(dlg)
    assert c != b and "11.11" in _band_mag(dlg)["text"]

    # 3 · the visit's curve loaded from the project (the same value, another
    # way in): the band follows the payload
    tab._series_result = None
    tab._series_payload = []
    tab.set_visit_curve_hooks(lambda: [{"mjd": meta["mjd"], "mag": 12.99,
                                        "err": 0.05, "filter": "V",
                                        "source": "measure", "comps": 5,
                                        "flags": []}], None)
    tab.load_visit_curve()
    d = _band_strip(dlg)
    assert d != c and "12.99" in _band_mag(dlg)["text"]

    # 4 · another plate (the same field, the same header): the visit's curve
    # still answers for that frame by time, so the band follows it
    import shutil
    # the copy goes to tmp_path: writing it beside the fixture left a
    # second_plate.fits inside the repository (found in the working tree)
    second = tmp_path / "second_plate.fits"
    shutil.copyfile(dlg.state.path, second)
    dlg.open_plate(str(second))
    e = _band_strip(dlg)
    assert e != d and "12.99" in _band_mag(dlg)["text"]

    # 5 · and with nothing measured at all the catalogue comes back, in white
    tab._series_payload = []
    tab._curve_from_visit = False
    dlg.view.viewport().update()
    f = _band_strip(dlg)
    assert f != e and _band_mag(dlg)["role"] == "mag-cat"


def test_a_hand_measurement_wins_over_the_visit_s_curve(dlg):
    # The order that tells the truth: the visit's curve is loaded when the
    # visit opens, BEFORE any click, so a measurement that exists on top of it
    # is the last thing the observer did and the band shows it. A series
    # measured NOW (not the visit's) wins over it: then the curve IS the
    # fresher measurement.
    from nightscribe.core import fits_meta
    dlg.state.load(MONO)
    dlg.set_object({"name": "X", "ra": 20.0, "dec": 62.0, "mag": 17.1})
    tab = dlg.tab_measure
    meta = fits_meta.meta_from_header(dlg.state.header or {})
    tab._curve_from_visit = True
    tab._series_payload = [{"mjd": meta["mjd"], "mag": 11.11, "err": 0.03,
                            "filter": "V", "source": "measure",
                            "comps": 5, "flags": []}]
    assert "11.11" in _band_mag(dlg)["text"]      # the visit's curve alone
    tab._last = {"mag": 12.34, "err": 0.04, "band": "V", "col": 1.0,
                 "row": 1.0, "used": [1, 2, 3, 4, 5],
                 "check": {"ok": True}, "result": {}}
    assert "12.34" in _band_mag(dlg)["text"]      # the hand one wins
    tab._curve_from_visit = False                 # the series just ran here
    assert "11.11" in _band_mag(dlg)["text"]
