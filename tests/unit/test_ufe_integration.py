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


def test_open_plate_and_show_tab(dlg, qapp):
    assert dlg.open_plate(str(MONO))
    assert not dlg.open_plate(str(FIXTURES / "missing.fits"))
    # the legacy section names are routed to the Photometry tab; there
    # are no modes anymore (ADR-044 rev 2026-09-25): both links land on
    # the same tab, and the closed manual window leaves the clicks
    # measuring
    dlg.show_tab(dlg.tab_measure)
    assert dlg.tabs.currentWidget() is dlg.tab_photometry
    assert dlg.tab_measure._active
    dlg.show_tab("compare")
    assert dlg.tabs.currentWidget() is dlg.tab_photometry
    # opening the manual window hands the clicks to the star picking
    dlg.tab_compare.btn_manual.click()
    qapp.processEvents()
    dlg.tab_photometry._apply()
    assert dlg.tab_compare._active and not dlg.tab_measure._active


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


def test_blink_has_no_ad_hoc_entry_in_the_tools_menu(window, monkeypatch):
    # Asked for 2026-10-06: "quita Blink (ad hoc) del menú Herramientas". With
    # the unified editor on (the default) that entry opened the editor's own
    # Blink window, which is already its own button in the workbench, so it
    # was redundant. The menu entry, its action and its handler are gone; the
    # classic dialog stays in the code without a door (the observer's own
    # choice) and nothing in the interface reaches it.
    assert not hasattr(window._menus, "action_blink")
    assert not hasattr(window, "_tools_blink")
    assert hasattr(window, "_open_blink_dialog")     # kept, unreachable
    # and the workbench's Blink tool is still the door
    dlg = window._ufe_build()
    assert dlg._tools["blink"].panel is dlg.tab_blink
    dlg.show_tab("blink")
    assert dlg._tools["blink"].isVisible()


def test_routing_visit_plate_opens_the_editor(window, monkeypatch):
    # ADR-045: the retired Process-tab blink button is gone; a visit's
    # plate opens in the editor from the visits manager, with both hooks
    # armed for THAT visit.
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

        def load_saved_sequence(self, seq):
            return False
    monkeypatch.setattr(window, "_ufe_open",
                        lambda tab, hook_pid=None, obj=None,
                        session_id=None: (
                            seen.append((tab, hook_pid, obj, session_id))
                            or _Dlg()))
    monkeypatch.setattr(window, "_use_ufe", lambda: True)
    import nightscribe.gui.main_window as _mw
    monkeypatch.setattr(_mw.project, "get",
                        lambda db_, pid: dict(window._current_project))
    window._visit_open_in_editor(1, "/tmp/plate.fits", 42)
    assert seen[0][:2] == ("measure", 1)
    assert seen[0][2] == {"name": "SN 2026zji", "ra": 10.0, "dec": 20.0,
                          "mag": 13.2, "bv": None}
    assert seen[0][3] == 42          # the point/save hooks land on it
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
                        lambda db_, pid, path, kind, session_id=None:
                        saved.append((path, kind, session_id)))
    monkeypatch.setattr(mw.project, "update_context",
                        lambda db_, pid, payload: ctx.append(payload))
    window._populate_project_files = lambda pid: None
    window._ufe_save_hook(1, ["/tmp/a.fits"], "fits", {})
    assert saved == [("/tmp/a.fits", "fits", None)]
    # ADR-045: opened from a visit, the files land on it
    window._ufe_save_hook(1, ["/tmp/b.png"], "chart", {}, session_id=42)
    assert saved[-1] == ("/tmp/b.png", "chart", 42)
    entries = [{"name": "Comp1",
                "star": {"band": "V", "mag": 12.3, "ra": 1, "dec": 2}}]
    window._ufe_save_hook(1, ["/tmp/s.csv"], "sequence",
                          {"which": "csv", "entries": entries,
                           "catalog": "gaia", "catalog_name": "Gaia EDR3",
                           "fov_arcmin": 30.0, "target_mag": 12.0})
    assert saved[-1] == ("/tmp/s.csv", "report", None)
    assert ctx and ctx[0]["sequence"]["entries"] == entries
    window._ufe_save_hook(1, ["/tmp/c.png"], "sequence",
                          {"which": "png"})
    assert saved[-1] == ("/tmp/c.png", "chart", None)
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

    from PySide6.QtWidgets import QWidget as _QWidget

    class _Dlg(_QWidget):
        # the mapping in _ufe_open touches all four tabs; the object
        # lands whole via set_object (the tabs prefill inside it).
        # Interfaz 1.0: the workbench is a QWidget hosted in the shell.
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

        def set_reset_hooks(self, state_fn, points_fn):
            pass

        def set_series_hook(self, fn):
            pass

        def set_points_hook(self, fn):
            pass

        def set_run_undo_hook(self, fn):
            pass

        def set_exoclock_hook(self, fn):
            pass

        def set_sequence_hook(self, fn):
            pass

        def set_exotic_hooks(self, reduce_fn=None, export_fn=None):
            pass

        def load_saved_sequence(self, seq):
            return False

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
    # the plate first (its load prefills the tab fields), then the object:
    # the band heads a PLATE, and it carries the object (ADR-046 rev.):
    # name, position and the catalogue magnitude, which says it is one
    dlg.state.load(MONO)
    dlg.set_object(obj)
    assert dlg.windowTitle().startswith(
        "NightScribe Image Workbench · T CrB")
    first = dlg.view.band_lines()["lines"][0]
    text = " · ".join(seg["text"] for seg in first)
    assert "T CrB" in text and "RA" in text and "10.50 cat" in text
    assert dlg.view.band_lines()["lines"][0]
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
    assert dlg.view.band_lines()["lines"][0]
    dlg.set_object(None)                          # the ad-hoc open
    assert dlg.object() is None
    # the band is the PLATE's heading: without an object it names the plate
    text = " · ".join(seg["text"]
                      for seg in dlg.view.band_lines()["lines"][0])
    assert "sn2026zji_new_image" in text
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

        # The editor opened on the plate, with the Annotate window up (it is
        # a tool window of its own since ADR-044 rev, not a tab). Interfaz
        # 1.0: "opened" means the shell is on the workbench view.
        from nightscribe.gui.main_window import VIEW_UFE
        uf = window._ufe
        assert uf is not None
        assert window._shell_stack().currentIndex() == VIEW_UFE
        assert uf._tools["annotate"].isVisible()
        assert uf._active_tool == "annotate"
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


def test_ufe_sequence_hook_stores_the_sequence(window, monkeypatch):
    # the editor's sequence lands in the project context (plus the target
    # magnitude), ready for the next open
    import nightscribe.gui.main_window as mw
    seen = {}
    monkeypatch.setattr(mw.project, "update_context",
                        lambda db_, pid, ctx: seen.update(pid=pid, ctx=ctx))
    entries = [{"name": "A", "kind": "comp",
                "star": {"ra": 1.0, "dec": 2.0, "mag": 12.0}}]
    window._ufe_sequence_hook(7, {"catalog": "gaia",
                                  "catalog_name": "Gaia EDR3",
                                  "fov_arcmin": 36.0, "target_mag": 12.0,
                                  "entries": entries})
    assert seen["pid"] == 7
    assert seen["ctx"]["sequence"]["entries"] == entries
    assert seen["ctx"]["sequence"]["catalog"] == "gaia"
    assert seen["ctx"]["mag"] == 12.0


def test_load_editor_sequence_falls_back_to_the_project(window, monkeypatch):
    # a plate state saved without a sequence must not block the project's
    # saved sequence from filling the Compare tab
    import nightscribe.gui.main_window as mw
    monkeypatch.setattr(
        mw.project, "find_file",
        lambda db_, pid, path: {"meta": {"ufe": {"stretch": {}}}})
    seq = {"catalog": "gaia", "catalog_name": "Gaia EDR3",
           "entries": [{"name": "A", "kind": "comp",
                        "star": {"ra": 1.0, "dec": 2.0}}]}
    monkeypatch.setattr(mw.project, "get",
                        lambda db_, pid: {"context": {"sequence": seq}})
    calls = {"applied": 0, "loaded": []}

    class _D:
        def apply_plate_state(self, st):
            calls["applied"] += 1

        def load_saved_sequence(self, s):
            calls["loaded"].append(s)

    window._load_editor_sequence(_D(), 1, "/x.fits")
    assert calls["applied"] == 1
    assert calls["loaded"] == [seq]


# ---------------- the workbench is one session at a time (issue) ------

def test_another_project_does_not_inherit_the_previous_session(dlg):
    # Reported: switching project kept the previous one's plate, sequence
    # and target in the workbench, and it did the same when opening it
    # from the Tools menu. The dialog is persistent on purpose (the plate
    # and the stretch survive a close), which is exactly why it has to
    # know when the SESSION changed.
    dlg.begin_session((1, 10))
    dlg.set_object({"name": "T CrB", "ra": 238.0, "dec": 25.9})
    dlg.state.load(MONO)
    dlg.tab_compare.edt_target.setText("T CrB")
    assert dlg.state.has_image and dlg.view.band_lines()["lines"][0]
    # the same session again: nothing is thrown away
    assert dlg.begin_session((1, 10)) is False
    assert dlg.state.has_image
    # another project: a clean workbench, and nothing is lost (the plate,
    # the sequence and the points live in their own project)
    assert dlg.begin_session((2, 20)) is True
    assert not dlg.state.has_image
    assert not dlg.view.band_lines()["lines"]
    assert dlg.tab_compare.edt_target.text() == ""
    # the ad-hoc open from Tools is its own session too
    dlg.state.load(MONO)
    assert dlg.begin_session(None) is True
    assert not dlg.state.has_image
