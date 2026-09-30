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


# ------------------------------------------------- chart boxes (ADR-046)

def test_chart_boxes_provider_reads_the_live_state(dlg, monkeypatch):
    # name: the plate stem when nothing else speaks; the attached object
    # wins over it. Date/exposure from the header, position/scale/FOV
    # from the WCS, brightness only after a measurement.
    from nightscribe.config import config
    monkeypatch.setitem(config._data, "observer_name", "F. Calvo")
    monkeypatch.setitem(config._data, "mpc_code", "Z41")
    monkeypatch.setitem(config._data, "chart_boxes", True)
    assert dlg._chart_boxes() == {}                    # no plate, no boxes
    dlg.state.load(MONO)
    boxes = dlg._chart_boxes()
    assert boxes["top_left"] == ["sn2026zji_new_image"]
    assert "Date: 2026-08-21 20:54 UT" in boxes["top_right"]
    assert "Exp: 10.0 s" in boxes["top_right"]
    # solved plate: scale and FOV always; the RA/Dec lines wait for a
    # known object position (a field centre is not the object)
    assert not any(ln.startswith("RA: ") for ln in boxes["top_right"])
    assert any(ln.startswith("PSc: ") for ln in boxes["bottom_left"])
    assert "Obs: F. Calvo" in boxes["bottom_left"]
    assert "Stn: Z41" in boxes["bottom_left"]
    # no measurement yet: no Mag line
    assert not any(ln.startswith("Mag: ") for ln in boxes["top_right"])
    # the attached object wins the name and pins the position (an
    # off-plate object would paint no position lines at all)
    from nightscribe.core import coords
    cra, cdec = dlg.state.wcs.center()
    dlg.set_object({"name": "AT 2026zji", "ra": cra, "dec": cdec,
                    "mag": 17.1})
    boxes = dlg._chart_boxes()
    assert boxes["top_left"] == ["AT 2026zji"]
    col, row = dlg.state.wcs.sky_to_pixel(cra, cdec)
    era, edec = dlg.state.wcs.pixel_to_sky(col, row)
    assert f"RA: {coords.ra_deg_to_hms(era)}" in boxes["top_right"]
    assert f"Dec: {coords.dec_deg_to_dms(edec)}" in boxes["top_right"]
    # a catalog magnitude from the project is NOT a calibration: no Mag
    assert not any(ln.startswith("Mag: ") for ln in boxes["top_right"])
    # a calibrated measurement this session is
    dlg.tab_measure._last = {"mag": 16.391, "err": 0.04, "band": "V",
                             "col": 100.0, "row": 200.0}
    boxes = dlg._chart_boxes()
    assert "Mag: 16.39 ± 0.04 (V)" in boxes["top_right"]
    # ... and the position now speaks from the measured centroid
    ra, dec = dlg.state.wcs.pixel_to_sky(100.0, 200.0)
    assert f"RA: {coords.ra_deg_to_hms(ra)}" in boxes["top_right"]


def test_chart_boxes_toggle_default_comes_from_config(dlg, monkeypatch):
    from nightscribe.config import config
    monkeypatch.setitem(config._data, "chart_boxes", True)
    dlg.hide()
    dlg.show()                          # showEvent re-reads the default
    assert dlg.btn_boxes.isChecked()
    assert dlg.view.show_boxes
    monkeypatch.setitem(config._data, "chart_boxes", False)
    dlg.hide()
    dlg.show()
    assert not dlg.btn_boxes.isChecked()
    assert not dlg.view.show_boxes


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
    assert dlg.btn_boxes.text() == "Boxes"
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
    dlg.set_series_hook(lambda: ctx)


def test_the_visit_solve_button_needs_frames_and_the_write_option(
        dlg, monkeypatch):
    # A batch leaves the visit solved ON DISK: with "save the solved WCS in
    # the FITS" off, the 35 solutions would die with the session, so the
    # button says why instead of doing a useless job.
    from nightscribe.config import config
    btn = dlg.visit_panel.btn_solve_visit
    _visit(dlg, [])
    assert not btn.isEnabled()
    _visit(dlg, [MONO, MONO])
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
