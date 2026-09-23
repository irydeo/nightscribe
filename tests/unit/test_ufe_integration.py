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
                               "context": {"ra_deg": 10.0,
                                           "dec_deg": 20.0}}
    window._project_widgets = {}
    seen = []

    class _Blink:
        def prefill(self, **kw):
            seen.append(kw)

    class _Dlg:
        tab_blink = _Blink()

        def open_plate(self, path):
            return True
    monkeypatch.setattr(window, "_ufe_open",
                        lambda tab, hook_pid=None: (
                            seen.append((tab, hook_pid)) or _Dlg()))
    monkeypatch.setattr(window, "_use_ufe", lambda: True)
    window._project_blink()
    assert seen[0] == ("blink", 1)
    assert seen[1]["name"] == "SN 2026zji"
    assert seen[1]["ra"] == 10.0


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

        def open_plate(self, path):
            seen.append({"plate": path})
            return True
    monkeypatch.setattr(window, "_ufe_open",
                        lambda tab, hook_pid=None: (
                            calls.append((tab, hook_pid)) or _Dlg()))
    window._fu_export_annotated(1)
    assert ("annotate", 1) in calls
    assert seen[0]["plate"] == str(MONO)
    assert seen[1]["label"] == "SN x"


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
                progress = Signal(str)
            self._sig = _Sig()
            self.finished = self._sig.finished
            self.progress = self._sig.progress

        def start(self):
            self.finished.emit((str(MONO), "DSS2-red"))

    monkeypatch.setattr("nightscribe.gui.workers.UfeCutoutWorker",
                        _CutWorker)
    tab._on_load_survey()
    assert tab._prefill_sky == (10.0, 20.0)
    assert dlg.state.has_image                  # the cutout became the plate
    assert "DSS2-red" in tab.lbl_status.text()
