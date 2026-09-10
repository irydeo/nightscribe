############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - NEO/PCCP/comet session products tests (Track C, C0; offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen tests for the C0 "Session products" block (track C,
docs/PLANS/neo-consistency.md).

The NEO/PCCP/comet Process step registers what the observer actually keeps
from the session: the FITS frames (metadata auto-read via fits_meta), the
Tycho annotated images (kind "image") and the MPC report (registered on
save, already covered). Registration goes to project_files (visible in the
Details tab, A4) and a summary is persisted in the process step data, so
the block survives a project switch.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # Redirect the shared db singleton to a throwaway file so the tests
    # never touch the real database (mirrors test_projects_hub.py).
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("c0db") / "t.db")
    dbmod.db = tmp
    mw.db = tmp
    yield
    dbmod.db = old_dbmod
    mw.db = old_mw


@pytest.fixture(scope="module")
def window(_point_db_at_tmpdir):
    from PySide6.QtWidgets import QApplication
    from nightscribe.config import config
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    from nightscribe.gui.main_window import MainWindow
    # keep the tests hermetic: no auto-compute network worker on startup
    orig_cfg = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


def _select_project(window, kind, name):
    # @args: window - MainWindow, kind - project kind, name - target name
    # @return: the created project dict, set as current and with step tabs
    #          built (as if the user had selected it in the hub)
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = project.create(mw.db, kind, name, {"ra_deg": 10.0, "dec_deg": 20.0})
    window._current_project = p
    window._build_step_tabs(p)
    return p


def _fake_fits_meta(path):
    # Tolerant stand-in for fits_meta.read_meta (never touches the disk).
    return {"date_obs": "2026-09-10T21:00:00", "mjd": 61293.875,
            "filter": "R", "exptime_s": 60.0, "object": "2016 XYZ"}


def test_register_fits_records_files_and_step_data(window, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = _select_project(window, "neo", "2016 XYZ")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames",
        staticmethod(lambda *a, **k: (["/tmp/a.fits", "/tmp/b.fit"], "")))
    monkeypatch.setattr(
        "nightscribe.core.fits_meta.read_meta", _fake_fits_meta)
    window._neo_register_fits()
    # every FITS lands in project_files with kind "fits"
    files = [f for f in project.list_files(mw.db, p["id"])
             if f["kind"] == "fits"]
    assert [f["path"] for f in files] == ["/tmp/a.fits", "/tmp/b.fit"]
    # and a metadata summary is persisted in the process step data
    fresh = project.get(mw.db, p["id"])
    step = next(s for s in fresh["steps"] if s["step"] == "process")
    fits = step["data"]["session_fits"]
    assert len(fits) == 2
    assert fits[0]["filter"] == "R"
    assert fits[0]["exptime_s"] == 60.0
    # the visible summary shows the file name and the metadata
    lst = window._project_widgets["neo_products"]
    texts = [lst.item(i).text() for i in range(lst.count())]
    assert len(texts) == 2
    assert "a.fits" in texts[0] and "R" in texts[0] and "60" in texts[0]


def test_register_images_records_image_kind(window, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = _select_project(window, "neo", "2026 AB1")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames",
        staticmethod(lambda *a, **k: (["/tmp/tycho1.png"], "")))
    window._neo_register_image()
    files = [f for f in project.list_files(mw.db, p["id"])
             if f["kind"] == "image"]
    assert [f["path"] for f in files] == ["/tmp/tycho1.png"]
    fresh = project.get(mw.db, p["id"])
    step = next(s for s in fresh["steps"] if s["step"] == "process")
    assert step["data"]["session_images"] == [{"path": "/tmp/tycho1.png"}]
    lst = window._project_widgets["neo_products"]
    texts = [lst.item(i).text() for i in range(lst.count())]
    assert texts == ["IMG  tycho1.png"]


def test_products_accumulate_and_survive_rebuild(window, monkeypatch):
    # Two registrations in a row must accumulate (in-memory sync), and a
    # rebuild from the database must restore the full summary.
    from PySide6.QtWidgets import QFileDialog
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = _select_project(window, "pccp", "P11ABCD")
    monkeypatch.setattr(
        "nightscribe.core.fits_meta.read_meta", _fake_fits_meta)
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames",
        staticmethod(lambda *a, **k: (["/tmp/n1.fits"], "")))
    window._neo_register_fits()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames",
        staticmethod(lambda *a, **k: (["/tmp/n2.fits", "/tmp/n3.fits"], "")))
    window._neo_register_fits()
    lst = window._project_widgets["neo_products"]
    assert lst.count() == 3
    # rebuild from the db (project switch) — the block must restore
    fresh = project.get(mw.db, p["id"])
    window._current_project = fresh
    window._build_step_tabs(fresh)
    lst = window._project_widgets["neo_products"]
    assert lst.count() == 3


def test_register_without_project_is_noop(window, monkeypatch):
    # No current project: both handlers bail out quietly.
    window._current_project = None
    window._neo_register_fits()
    window._neo_register_image()  # must not raise


def test_comet_gets_products_block_without_mpc(window):
    # Comets keep the same products (FITS + annotated images) but have no
    # MPC report block.
    _select_project(window, "comet", "C/2026 A1")
    assert "neo_products" in window._project_widgets
    assert "txt_mpc" not in window._project_widgets


def test_sn_has_no_products_block(window):
    # SN keeps its own FITS import + follow-up tab; no products block.
    _select_project(window, "sn", "SN 2026zz")
    assert "neo_products" not in window._project_widgets
