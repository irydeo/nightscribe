############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE integration (settings flag, routing,
# prefills, save hook, DSS2 cutout) — ADR-044 coexistence
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for the UFE-by-default wiring: the Development tab in
Settings, the entry points routing to the editor or to the legacy
dialogs per the flag, the prefill APIs, the project save hook, and the
survey (DSS2) field download into the Compare tab. Dialog classes are
stubbed where the legacy UI would block; no network anywhere.
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


def _spin_events(ms=20):
    # A plain processEvents() does NOT deliver a deleteLater, but a real
    # event loop does: let it run long enough for the deferred deletion.
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def dlg(qapp):
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.show()
    yield d
    d.tab_blink.shutdown()
    d.view._render_timer.stop()
    d.deleteLater()


@pytest.fixture
def window(qapp):
    from nightscribe.config import config
    from nightscribe.gui.main_window import MainWindow
    orig = config.is_configured
    config.is_configured = lambda: False   # no network worker at startup
    w = MainWindow()
    config.is_configured = orig
    yield w
    w.close()


def test_ufe_default_is_on():
    from nightscribe.config import DEFAULTS
    assert DEFAULTS["ufe_default"] is True


def test_settings_has_the_development_tab(qapp):
    import inspect
    from PySide6.QtCore import QFile
    from PySide6.QtUiTools import QUiLoader
    f = QFile("nightscribe/gui/ui/settings_dialog.ui")
    f.open(QFile.ReadOnly)
    d = QUiLoader().load(f)
    f.close()
    titles = [d.tabWidget.tabText(i) for i in range(d.tabWidget.count())]
    assert "Development" in titles
    assert d.chk_ufe_default is not None
    assert "Image Workbench" in d.lblH_ufe.text()
    from nightscribe.gui import main_window as mw
    src = inspect.getsource(mw.MainWindow.on_open_settings)
    assert 'chk_ufe_default.setChecked' in src
    assert 'ufe_default' in src and 'chk_ufe_default.isChecked()' in src


def test_open_plate_and_show_tab(dlg):
    assert dlg.open_plate(str(MONO))
    assert not dlg.open_plate(str(FIXTURES / "missing.fits"))
    dlg.show_tab(dlg.tab_measure)
    assert dlg.tabs.currentWidget() is dlg.tab_measure


def test_prefills_land(dlg):
    dlg.open_plate(str(MONO))
    cra, cdec = dlg.state.wcs.center()
    dlg.tab_blink.prefill(name="2026zji", ra=cra, dec=cdec)
    assert dlg.tab_blink.edt_name.text() == "2026zji"
    assert dlg.tab_blink.chk_manual.isChecked()
    dlg.tab_annotate.prefill(label="SN 2026zji", notes="SN follow-up",
                             ra=cra, dec=cdec, extra_paths=["/tmp/v2.fits"])
    assert dlg.tab_annotate.edit_label.text() == "SN 2026zji"
    w, h = dlg.state.plate_shape
    assert abs(dlg.tab_annotate._marker[0] - w / 2) < 1
    assert dlg.tab_annotate.lst_extra.count() == 1
    dlg.tab_compare.prefill(target="T CrB", mag=10.5, ra=238.0, dec=25.9)
    assert dlg.tab_compare.edt_target.text() == "T CrB"
    assert dlg.tab_compare.spn_mag.value() == 10.5
    assert dlg.tab_compare._prefill_sky == (238.0, 25.9)


def test_save_hook_fires_and_clears(dlg):
    seen = []
    dlg.set_save_hook(lambda paths, kind, payload: seen.append(kind))
    dlg.notify_saved(["/tmp/x.fits"], "fits")
    dlg.set_save_hook(None)
    dlg.notify_saved(["/tmp/y.fits"], "fits")
    assert seen == ["fits"]


def test_routing_blink_tools_menu(window, monkeypatch):
    calls = []
    monkeypatch.setattr(window, "_ufe_open",
                        lambda tab, hook_pid=None: calls.append(
                            ("ufe", tab)))
    monkeypatch.setattr(window, "_open_blink_dialog",
                        lambda *a, **k: calls.append(("legacy",)))
    monkeypatch.setattr(window, "_use_ufe", lambda: True)
    window._tools_blink()
    monkeypatch.setattr(window, "_use_ufe", lambda: False)
    window._tools_blink()
    assert calls == [("ufe", "blink"), ("legacy",)]


def test_routing_project_blink(window, monkeypatch):
    window._current_project = {"id": 1, "object_name": "SN 2026zji",
                               "context": {"ra_deg": 10.0, "dec_deg": 20.0,
                                           "mag": 13.2}}
    window._project_widgets = {}
    seen = []

    class _Dlg:
        def set_object(self, obj):
            seen.append(obj)

        def open_plate(self, path):
            return True
    monkeypatch.setattr(window, "_ufe_open",
                        lambda tab, hook_pid=None, obj=None: (
                            seen.append((tab, hook_pid, obj)) or _Dlg()))
    monkeypatch.setattr(window, "_use_ufe", lambda: True)
    window._project_blink()
    assert seen[0] == ("blink", 1, {"name": "SN 2026zji", "ra": 10.0,
                                    "dec": 20.0, "mag": 13.2,
                                    "bv": None})
    # and the object is re-applied on the fresh plate
    assert seen[-1] == seen[0][2]


def test_routing_sequence_and_annotate(window, monkeypatch):
    import nightscribe.gui.main_window as mw
    calls = []
    monkeypatch.setattr(window, "_fu_sequence_via_ufe",
                        lambda pid: calls.append(("seq", pid)))
    monkeypatch.setattr(mw.project, "get", lambda db_, pid: None)
    monkeypatch.setattr(window, "_use_ufe", lambda: True)
    window._fu_sequence_dialog(7)
    assert calls == [("seq", 7)]

    # annotate: a project with one registered image opens the UFE with
    # the plate loaded and the marker prefilled
    monkeypatch.setattr(mw.project, "get",
                        lambda db_, pid: {"id": 1, "object_name": "SN x",
                                          "context": {"ra_deg": 10.0,
                                                      "dec_deg": 20.0}})
    from nightscribe.core import followup as fu
    monkeypatch.setattr(fu, "list_sessions",
                        lambda db_, pid: [{"id": 5, "obs_date": None}])
    monkeypatch.setattr(fu, "list_images",
                        lambda db_, sid: [{"fits_path": str(MONO),
                                           "date_obs": None,
                                           "filter": "V",
                                           "exptime_s": 60}])
    seen = []

    class _Ann:
        def prefill(self, **kw):
            seen.append(kw)

    class _Dlg:
        tab_annotate = _Ann()

        def set_object(self, obj):
            seen.append({"object": obj})

        def open_plate(self, path):
            seen.append({"plate": path})
            return True
    monkeypatch.setattr(window, "_ufe_open",
                        lambda tab, hook_pid=None, obj=None: (
                            calls.append((tab, hook_pid, obj)) or _Dlg()))
    window._fu_export_annotated(1)
    assert ("annotate", 1, {"name": "SN x", "ra": 10.0, "dec": 20.0,
                            "mag": None, "bv": None}) in calls
    assert seen[0]["plate"] == str(MONO)
    # the object re-applies on the fresh plate (the marker needs its WCS)
    assert seen[1]["object"]["name"] == "SN x"
    # the visits/notes still come through the tab's prefill
    assert seen[2]["notes"]


def test_save_hook_registers_files_and_sequence(window, monkeypatch):
    import nightscribe.gui.main_window as mw
    saved = []
    ctx = []
    monkeypatch.setattr(mw.project, "get",
                        lambda db_, pid: {"id": pid, "object_name": "SN x",
                                          "context": {}})
    monkeypatch.setattr(mw.project, "add_file",
                        lambda db_, pid, path, kind: saved.append(
                            (path, kind)))
    monkeypatch.setattr(mw.project, "update_context",
                        lambda db_, pid, payload: ctx.append(payload))
    window._populate_project_files = lambda pid: None
    window._ufe_save_hook(1, ["/tmp/a.fits"], "fits", {})
    assert saved == [("/tmp/a.fits", "fits")]
    entries = [{"name": "Comp1",
                "star": {"band": "V", "mag": 12.3, "ra": 1, "dec": 2}}]
    window._ufe_save_hook(1, ["/tmp/s.csv"], "sequence",
                          {"which": "csv", "entries": entries,
                           "catalog": "gaia", "catalog_name": "Gaia EDR3",
                           "fov_arcmin": 30.0, "target_mag": 12.0})
    assert saved[-1] == ("/tmp/s.csv", "report")
    assert ctx and ctx[0]["sequence"]["entries"] == entries
    window._ufe_save_hook(1, ["/tmp/c.png"], "sequence",
                          {"which": "png"})
    assert saved[-1] == ("/tmp/c.png", "chart")
    assert len(ctx) == 1                     # png does not rewrite it


def test_survey_field_flow(dlg, monkeypatch):
    # no plate: the survey button resolves the object and loads the FITS
    # cutout the worker brings (both faked; no network)
    tab = dlg.tab_compare
    assert "No plate loaded" in tab.lbl_status.text()
    from nightscribe.core import blink as core_blink
    monkeypatch.setattr(
        core_blink, "resolve_sn",
        lambda name, **k: {"ra": 10.0, "dec": 20.0, "name": "M 31"})

    class _Ask:
        @staticmethod
        def getText(*a, **k):
            return "M31", True

    monkeypatch.setattr(
        "PySide6.QtWidgets.QInputDialog.getText", _Ask.getText)

    class _CutWorker:
        def __init__(self, ra, dec, fov_arcmin=30.0):
            self._ra, self._dec = ra, dec

            from PySide6.QtCore import QObject, Signal

            class _Sig(QObject):
                finished = Signal(object)
                progress = Signal(dict)
            self._sig = _Sig()
            self.finished = self._sig.finished
            self.progress = self._sig.progress

        def start(self):
            self.progress.emit({"es": "Descargando el campo del survey…",
                                "en": "Downloading the survey field…"})
            self.finished.emit((str(MONO), "DSS2-red"))

    monkeypatch.setattr("nightscribe.gui.workers.UfeCutoutWorker",
                        _CutWorker)
    tab._on_load_survey()
    assert tab._prefill_sky == (10.0, 20.0)
    assert dlg.state.has_image                  # the cutout became the plate
    assert "DSS2-red" in tab.lbl_status.text()


def test_survey_download_runs_behind_the_busy_dialog(dlg, monkeypatch):
    # The survey download also takes seconds: it runs behind the same
    # modal, cancel-less busy dialog as the catalog query (the UFE
    # rewrite dropped it), reaped the moment the cutout arrives.
    from nightscribe.core import blink as core_blink
    monkeypatch.setattr(
        core_blink, "resolve_sn",
        lambda name, **k: {"ra": 10.0, "dec": 20.0, "name": "M 31"})

    class _Ask:
        @staticmethod
        def getText(*a, **k):
            return "M31", True
    monkeypatch.setattr("PySide6.QtWidgets.QInputDialog.getText",
                        _Ask.getText)

    created = {}

    class _Holding:
        def __init__(self, ra, dec, fov_arcmin=30.0):
            from PySide6.QtCore import QObject, Signal

            class _Sig(QObject):
                finished = Signal(object)
                progress = Signal(dict)
            self._sig = _Sig()
            self.finished = self._sig.finished
            self.progress = self._sig.progress
            created["worker"] = self

        def start(self):
            self.progress.emit({"es": "Descargando el campo del survey…",
                                "en": "Downloading the survey field…"})

        def land(self):
            self.finished.emit((str(MONO), "DSS2-red"))
    monkeypatch.setattr("nightscribe.gui.workers.UfeCutoutWorker", _Holding)

    from PySide6.QtWidgets import QProgressDialog, QPushButton
    tab = dlg.tab_compare
    tab._on_load_survey()
    waits = tab.findChildren(QProgressDialog)
    assert len(waits) == 1
    assert not waits[0].findChildren(QPushButton)  # no cancel button: nothing to abort
    assert waits[0].maximum() == 0              # indeterminate
    assert "Descargando el campo del survey" in waits[0].labelText()
    assert "Descargando el campo del survey" in tab.lbl_status.text()
    # the cutout lands: the dialog is reaped before the plate loads
    created["worker"].land()
    _spin_events()                            # let the deleteLater run
    assert not tab.findChildren(QProgressDialog)
    assert dlg.state.has_image                  # the cutout became the plate
    assert "DSS2-red" in tab.lbl_status.text()


def test_prefill_mag_falls_back_to_the_saved_sequence(window, monkeypatch):
    # the target magnitude was saved with an earlier sequence: the
    # prefill finds it there when the context lacks planner/VSX fields
    import nightscribe.gui.main_window as mw
    monkeypatch.setattr(mw.project, "get",
                        lambda db_, pid: {"id": pid,
                                          "object_name": "V0001 Cyg",
                                          "context": {"sequence":
                                                      {"target_mag":
                                                       11.25}}})
    from nightscribe.core import followup as fu
    monkeypatch.setattr(fu, "list_sessions", lambda db_, pid: [])
    seen = []

    class _Cmp:
        def prefill(self, **kw):
            seen.append(kw)

    class _Dlg:
        # the mapping in _ufe_open touches all four tabs; the object
        # lands whole via set_object (the tabs prefill inside it)
        tab_blink = _Cmp()
        tab_compare = _Cmp()
        tab_annotate = _Cmp()
        tab_measure = _Cmp()

        def set_object(self, obj):
            seen.append(obj)

        def set_save_hook(self, fn):
            pass

        def set_point_hook(self, fn):
            pass

        def show_tab(self, tab):
            pass

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass
    monkeypatch.setattr(window, "_ufe_build", lambda: _Dlg())
    monkeypatch.setattr(window, "_use_ufe", lambda: True)
    window._fu_sequence_dialog(3)
    assert seen and seen[0]["mag"] == 11.25


def test_save_hook_persists_the_target_magnitude(window, monkeypatch):
    import nightscribe.gui.main_window as mw
    ctx = []
    monkeypatch.setattr(mw.project, "get",
                        lambda db_, pid: {"id": pid, "object_name": "V1",
                                          "context": {}})
    monkeypatch.setattr(mw.project, "add_file", lambda *a, **k: None)
    monkeypatch.setattr(mw.project, "update_context",
                        lambda db_, pid, payload: ctx.append(payload))
    window._populate_project_files = lambda pid: None
    entries = [{"name": "Comp1",
                "star": {"band": "V", "mag": 12.3, "ra": 1, "dec": 2}}]
    window._ufe_save_hook(1, ["/tmp/s.csv"], "sequence",
                          {"which": "csv", "entries": entries,
                           "catalog": "gaia", "catalog_name": "Gaia EDR3",
                           "fov_arcmin": 30.0, "target_mag": 11.25})
    assert ctx[0]["mag"] == 11.25          # it lives in the project now
    assert ctx[0]["sequence"]["target_mag"] == 11.25


def test_set_object_fills_everything(dlg):
    obj = {"name": "T CrB", "ra": 238.08392, "dec": 25.92,
           "mag": 10.5, "bv": 0.62}
    dlg.set_object(obj)
    assert dlg.windowTitle() == "NightScribe Image Workbench · T CrB"
    line = dlg.lbl_object.text()
    assert "T CrB" in line and "RA" in line and "mag 10.50" in line
    assert dlg.lbl_object.isVisible()
    assert dlg.tab_blink.edt_name.text() == "T CrB"
    assert dlg.tab_blink.chk_manual.isChecked()
    assert dlg.tab_compare.edt_target.text() == "T CrB"
    assert dlg.tab_compare.spn_mag.value() == 10.5
    assert dlg.tab_compare._prefill_sky == (238.08392, 25.92)
    assert dlg.tab_annotate.edit_label.text() == "T CrB"
    assert dlg.tab_measure.spn_target_bv.value() == 0.62


def test_object_survives_a_plate_load_and_clears_adhoc(dlg):
    dlg.set_object({"name": "T CrB", "ra": 238.0, "dec": 25.9})
    dlg.open_plate(str(MONO))
    assert "T CrB" in dlg.windowTitle()          # the object stays
    assert "sn2026zji_new_image.fits" in dlg.windowTitle()
    assert dlg.lbl_object.isVisible()
    dlg.set_object(None)                          # the ad-hoc open
    assert dlg.object() is None
    assert not dlg.lbl_object.isVisible()
    assert "T CrB" not in dlg.windowTitle()
    assert "sn2026zji_new_image.fits" in dlg.windowTitle()


def test_object_builder_chain(window):
    # planner mag wins; else VSX MaxMag; else the last saved sequence
    p = {"object_name": "V1", "context": {"ra_deg": 1.0, "dec_deg": 2.0,
                                          "mag": 12.3,
                                          "variable": {"bv": 0.5}}}
    assert window._ufe_object_from_project(p) == {
        "name": "V1", "ra": 1.0, "dec": 2.0, "mag": 12.3, "bv": 0.5}
    p2 = {"object_name": "V2", "context": {"variable": {"max": 9.75,
                                                        "ra_deg": 3.0,
                                                        "dec_deg": 4.0}}}
    o2 = window._ufe_object_from_project(p2)
    assert o2["mag"] == 9.75 and o2["ra"] == 3.0 and o2["bv"] is None
    p3 = {"object_name": "V3", "context": {"sequence":
                                           {"target_mag": 11.25}}}
    assert window._ufe_object_from_project(p3)["mag"] == 11.25


def test_files_window_opens_ufe_for_a_project_plate(window):
    # End to end: the Projects Files window double-clicks a plate row
    # and the unified FITS editor opens on that plate with the
    # project's object attached, ready to annotate. The project
    # save hook is live too: files saved in the editor register
    # on the project (ADR-044, the files-window rework).
    from PySide6.QtWidgets import QMessageBox
    QMessageBox.warning = staticmethod(lambda *a, **k: None)
    from nightscribe.core import db as dbmod
    from nightscribe.core import project as proj

    p = proj.create(dbmod.db, "sn", "SN 2110ff",
                    {"ra_deg": 275.0, "dec_deg": 10.5, "mag": 17.8})
    proj.add_file(dbmod.db, p["id"], str(MONO), "fits")
    try:
        window._current_project = proj.get(dbmod.db, p["id"])
        window._populate_project_files(p["id"])
        assert window.projects.btn_files.isEnabled()
        assert window.projects.btn_files.text() == "Files (1)"
        window._show_project_files()
        fd = window._proj_files_dlg
        assert fd.project_id == p["id"]
        assert fd.tbl.rowCount() == 1
        # Offscreen the QTest synthetic mouse does not reach
        # QTableWidget, so the double-click is emitted by hand
        # (tests/unit/test_tonight_table.py does the same).
        fd.tbl.itemDoubleClicked.emit(fd.tbl.item(0, 0))

        # The editor opened on the plate, Annotate tab, object attached.
        uf = window._ufe
        assert uf is not None and uf.isVisible()
        assert uf.tabs.currentWidget() is uf.tab_annotate
        assert uf.state.has_image
        assert uf.state.path == str(MONO)
        assert uf.object() == {"name": "SN 2110ff", "ra": 275.0,
                               "dec": 10.5, "mag": 17.8, "bv": None}
        # The project save hook is live: saving a FITS there writes
        # it into the project files like the legacy dialogs did.
        saved = str(FIXTURES / "e2e_annotated.fits")
        uf.notify_saved([saved], "fits")
        files = proj.list_files(dbmod.db, p["id"])
        assert any(f["path"] == saved and f["kind"] == "fits"
                   for f in files)
    finally:
        proj.delete(dbmod.db, p["id"])
