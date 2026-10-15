############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE Calibration tab (astrometry plan,
# phase 7 / ADR-061)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_calibration_tab.py and its worker: the
recipe is resolved against the master library and painted in plain
language (which master each piece uses, or what is missing), the export
checkbox defaults to the setting, CalibrationWorker calibrates and
exports frame by frame without ever starting a thread in the test, and
no widget declared in the Designer file is left orphaned. The recipe's
physics lives in test_calibration.py; here the wiring is."""

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

UI = Path(__file__).parents[2] / "nightscribe" / "gui" / "ui" \
    / "ufe_calibration_tab.ui"


def _write_fits(path, data, **cards):
    # @return: the path (str), a minimal float32 FITS
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.asarray(data, dtype=np.float32))
    for key, value in cards.items():
        hdu.header[key] = value
    hdu.writeto(str(path), overwrite=True)
    return str(path)


def _write_frames(tmp_path, n=2):
    # @return: n light frames whose header speaks the camera's language
    #          (the same keys core/calibration indexes masters by)
    out = []
    for i in range(n):
        out.append(_write_fits(
            tmp_path / f"light{i}.fits", np.full((64, 64), 1000.0),
            **{"DATE-OBS": f"2026-09-20T23:{30 + i}:00", "EXPTIME": 30.0,
               "GAIN": 2.0, "INSTRUME": "TestCam", "CCD-TEMP": -10.0,
               "FILTER": "R"}))
    return out


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def _tab(qapp, tmp_path, visit=True):
    # @return: (tab, host): the tab over a host double with
    #          astrometry_context(), the way the real dialog exposes it
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_calibration_tab import UfeCalibrationTab
    from nightscribe.gui.ufe_state import UfeImageState
    host = QWidget()           # parentless: it IS the tab's window()
    ctx = None
    if visit:
        ctx = {"pid": 1, "session_id": 2,
               "paths": _write_frames(tmp_path), "object_name": "2026 QX"}
    host.astrometry_context = lambda: ctx
    state = UfeImageState(host)
    tab = UfeCalibrationTab(state, "en", parent=host)
    tab.set_active(True)
    return tab, host


# ------------------------------------------------------------ the visit

def test_button_disabled_without_visit(qapp, tmp_path):
    # Without a visit there is nothing to calibrate: the button says so
    # with its state and the recipe line with its text.
    tab, _host = _tab(qapp, tmp_path, visit=False)
    assert tab.btn_calibrate.isEnabled() is False
    assert tab.lbl_recipe.text()          # says why, never empty
    assert tab.warnings_text() == ""


def test_export_checkbox_defaults_to_the_setting(qapp, tmp_path):
    # D6: writing calibrated copies is explicit; the default is the
    # setting's (calib_export, off by default), so the choice survives.
    tab, _host = _tab(qapp, tmp_path, visit=False)
    assert tab.chk_export.isChecked() is False


def test_the_export_checkbox_writes_its_setting(qapp, tmp_path, monkeypatch):
    # D6: writing calibrated copies is explicit, and the choice survives the
    # session. The pseudo-flat policy is NOT here any more (ADR-061 rev): it
    # lives in Settings, its single home, and this tab only READS it.
    from nightscribe.config import config
    monkeypatch.setitem(config._data, "calib_export", 0)
    tab, _host = _tab(qapp, tmp_path, visit=False)
    tab.chk_export.setChecked(True)
    assert int(config.get("calib_export")) == 1
    assert not hasattr(tab, "chk_pseudo_flat")


def test_short_recipe_says_what_the_calibration_will_do(qapp, tmp_path,
                                                        tmp_db, monkeypatch):
    # The one-liner the astrometry hint shows comes from HERE, the single
    # source of the recipe: an empty library says the vignetting stays; the
    # policy (read from Settings) says a vignetting model will stand in; and
    # a real flat always wins and is named.
    import nightscribe.core.db as db_mod
    from nightscribe.config import config
    from nightscribe.core import calibration as cal
    monkeypatch.setattr(db_mod, "db", tmp_db)
    monkeypatch.setitem(config._data, "calib_vignette_model", 0)
    tab, _host = _tab(qapp, tmp_path)
    text = tab.short_recipe()
    assert "no dark/bias" in text and "vignetting stays" in text
    config._data["calib_vignette_model"] = 1
    assert "vignetting model" in tab.short_recipe()
    flat = _write_fits(tmp_path / "flatR.fits", np.full((64, 64), 5000.0))
    cal.add_master(tmp_db, flat, {"kind": "flat", "camera": "TestCam",
                                  "gain": 2.0, "temp_c": -10.0,
                                  "exptime_s": 5.0, "filter": "R"})
    tab._sync_context()          # re-resolve against the new library
    text = tab.short_recipe()
    assert "flatR.fits" in text and "vignetting model" not in text


# ------------------------------------------------------------- the recipe

def test_recipe_shows_the_masters_it_uses(qapp, tmp_path, tmp_db,
                                          monkeypatch):
    # With a dark at the light's exposure and a flat for its filter in
    # the library, the summary names them (by file) and nothing is left
    # to warn about.
    import nightscribe.core.db as db_mod
    from nightscribe.core import calibration as cal
    monkeypatch.setattr(db_mod, "db", tmp_db)
    dark = _write_fits(tmp_path / "dark.fits", np.full((64, 64), 900.0))
    flat = _write_fits(tmp_path / "flat.fits", np.full((64, 64), 5000.0))
    cal.add_master(tmp_db, dark, {"kind": "dark", "camera": "TestCam",
                                  "gain": 2.0, "temp_c": -10.0,
                                  "exptime_s": 30.0})
    cal.add_master(tmp_db, flat, {"kind": "flat", "camera": "TestCam",
                                  "gain": 2.0, "temp_c": -10.0,
                                  "exptime_s": 5.0, "filter": "R"})
    tab, _host = _tab(qapp, tmp_path)
    recipe = tab.lbl_recipe.text()
    assert "dark.fits" in recipe
    assert "flat.fits" in recipe
    assert tab.warnings_text() == ""
    assert tab.btn_calibrate.isEnabled() is True


def test_missing_masters_warn_in_plain_language(qapp, tmp_path, tmp_db,
                                                monkeypatch):
    # An empty library is not an error: the recipe says exactly what
    # stays in the frames (the core's warnings re-said through the GUI's
    # own language), and the button still runs.
    import nightscribe.core.db as db_mod
    monkeypatch.setattr(db_mod, "db", tmp_db)
    tab, _host = _tab(qapp, tmp_path)
    warnings = tab.warnings_text()
    assert "No dark or bias in the library" in warnings
    assert "No flat for this filter" in warnings
    assert "missing" in tab.lbl_recipe.text()
    assert tab.btn_calibrate.isEnabled() is True


# ------------------------------------------------------------- the worker

def test_calibration_worker_exports_frame_by_frame(qapp, tmp_path, tmp_db):
    # run() is called DIRECTLY (no thread is ever started in a unit
    # test): the payload carries one report per frame and the exported
    # copies exist. The pixels die with each frame inside the worker
    # (memory discipline, D32), so a big visit never piles up in RAM.
    from nightscribe.gui.workers import CalibrationWorker
    paths = _write_frames(tmp_path)
    out = tmp_path / "calibrados"
    payload = {}
    progress = []
    w = CalibrationWorker(paths, tmp_db, out)
    w.finished.connect(lambda p: payload.update(p))
    w.progress.connect(lambda d, t: progress.append((d, t)))
    w.run()
    assert payload["status"] == "ok"
    assert len(payload["reports"]) == 2
    assert progress == [(1, 2), (2, 2)]
    written = payload["written"]
    assert len(written) == 2
    for path in written:
        assert Path(path).exists()
        assert path.endswith("_cal.fits")
    assert w.isRunning() is False


def test_calibration_worker_cancel_keeps_what_it_did(qapp, tmp_path,
                                                     tmp_db):
    # Cancel between frames: the status says "cancelled" and the frames
    # already exported are kept (nothing half-written is claimed).
    from nightscribe.gui.workers import CalibrationWorker
    paths = _write_frames(tmp_path, 3)
    payload = {}
    w = CalibrationWorker(paths, tmp_db, tmp_path / "cal")
    w.finished.connect(lambda p: payload.update(p))
    w.progress.connect(lambda d, t: d == 1 and w.cancel())
    w.run()
    assert payload["status"] == "cancelled"
    assert len(payload["reports"]) == 1
    assert len(payload["written"]) == 1


# ------------------------------------------------------------- no orphans

def test_no_orphan_widgets(qapp, tmp_path):
    # Every widget the Designer file declares resolves to a real widget
    # on the loaded .ui: nothing floats without a layout (the reported
    # class of bug this suite pins elsewhere).
    from PySide6.QtWidgets import QWidget
    tab, _host = _tab(qapp, tmp_path, visit=False)
    tree = ET.parse(UI).getroot()
    root = tree.find("widget")
    names = [w.get("name") for w in tree.iter("widget")
             if w.get("name") and w.get("name") != root.get("name")]
    assert names, "the Designer file declares its widgets"
    for name in names:
        w = getattr(tab._ui, name, None)
        assert isinstance(w, QWidget), name


def test_the_settings_button_is_the_door_to_the_library(qapp, tmp_path):
    # ADR-061 rev: the library and the policy live in Settings, their single
    # home; this tab only reads them and its button is the deep link there.
    # The tab never touches the database: it asks the host. Without a hook
    # it says where the library is instead of failing.
    tab, host = _tab(qapp, tmp_path)
    seen = {}

    def _open(page):
        seen["page"] = page
    host.open_settings_page = _open
    tab.btn_settings.click()
    assert seen["page"] == "page_measurement"
    # the library is NOT here any more: one home, no second copy
    assert not hasattr(tab, "cmb_master_kind")
    assert not hasattr(tab, "btn_master_add")
    host.open_settings_page = None
    tab.btn_settings.click()
    assert "Settings" in tab.lbl_status.text()


def test_a_master_out_of_tolerance_is_explained(qapp, tmp_path, tmp_db,
                                                monkeypatch):
    # The observer who can SEE a dark in the library must learn why it was
    # left out, with the numbers: "no dark" on its own is the message that
    # sent the author hunting (ADR-061 rev).
    import nightscribe.core.db as db_mod
    from nightscribe.core import calibration as cal
    monkeypatch.setattr(db_mod, "db", tmp_db)
    dark = _write_fits(tmp_path / "dark_cold.fits", np.full((64, 64), 900.0))
    cal.add_master(tmp_db, dark, {"kind": "dark", "camera": "TestCam",
                                  "gain": 2.0, "temp_c": -16.0,
                                  "exptime_s": 30.0})
    tab, _host = _tab(qapp, tmp_path)     # the lights sit at -10 C
    warnings = tab.warnings_text()
    assert "dark_cold.fits" in warnings
    assert "out of tolerance" in warnings
    assert "-16" in warnings and "-10" in warnings


# ------------------------------------------------------- colour by level

def test_a_failure_is_reported_as_an_error(qapp, tmp_path, tmp_db,
                                           monkeypatch):
    # "The calibration failed:" carries no ⚠, so it used to reach the
    # window's line as plain news. The level is explicit now (asked for
    # 2026-10-15: the text is long and hard to read, use colours for an
    # error and for a warning).
    import nightscribe.core.db as db_mod
    monkeypatch.setattr(db_mod, "db", tmp_db)
    tab, _host = _tab(qapp, tmp_path)
    seen = []
    tab.set_status_hook(lambda text, level: seen.append((text, level)))
    tab._on_failed("boom")
    assert seen and seen[-1][1] == "error"


def test_the_warnings_block_wears_one_colour_per_line(qapp, tmp_path, tmp_db,
                                                      monkeypatch):
    # A missing piece is a WARNING and a "why a master was left out" is a
    # NOTE: the block says which is which with the app's own level colours
    # (theme.LEVEL_COLOURS, the single source), so it can be read by colour
    # instead of sentence by sentence. The plain text is kept beside the
    # HTML, so what the observer copies is what it always was.
    import nightscribe.core.db as db_mod
    from nightscribe.core import calibration as cal
    from nightscribe.gui import theme
    monkeypatch.setattr(db_mod, "db", tmp_db)
    dark = _write_fits(tmp_path / "dark_cold.fits", np.full((64, 64), 900.0))
    cal.add_master(tmp_db, dark, {"kind": "dark", "camera": "TestCam",
                                  "gain": 2.0, "temp_c": -16.0,
                                  "exptime_s": 30.0})
    tab, _host = _tab(qapp, tmp_path)      # the lights sit at -10 C
    html = tab.lbl_warnings.text()
    assert theme.level_colour("warn") in html    # the piece that is missing
    assert theme.level_colour("info") in html    # why the master was left out
    text = tab.warnings_text()
    assert "No dark or bias" in text
    assert "out of tolerance" in text
    # nothing to say: the block is empty and so is the plain text
    tab._set_concerns([])
    assert tab.lbl_warnings.text() == ""
    assert tab.warnings_text() == ""
