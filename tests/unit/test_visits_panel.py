############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the visits panel (ADR-045)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/widgets/visits_panel.py: the Analysis tab's
core. The empty state and the single primary entry point, the
attach/remove cycle against the real registry (a FITS with its editable
metadata dialog, a generic file), the rule that nothing attaches without
a visit, the measurement block (curve kinds only) and the visit deletion
contract (points and files survive, unlinked). No network.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, tmp_path):
    # @return: (panel, project_id) on a temp database
    from nightscribe.core.db import Database
    from nightscribe.core import project
    from nightscribe.gui.widgets.visits_panel import VisitsPanel
    db = Database(tmp_path / "t.db")
    p = project.create(db, "sn", "SN2026vp")
    opened = []
    vp = VisitsPanel(db, lang="en",
                     open_in_editor=lambda path, sid:
                         opened.append((path, sid)),
                     on_change=lambda: None)
    vp.set_project(p["id"])
    yield vp, p["id"], opened
    vp.deleteLater()
    db.close()


def test_empty_state_first(panel):
    vp, _pid, _o = panel
    assert vp.lbl_empty.isVisibleTo(vp)
    assert not vp.lst.isVisibleTo(vp)
    # the rule: nothing attaches without a visit — no attach action exists
    # outside one
    assert vp.findChild(type(vp.lst), "vp_resources") is None


def test_new_visit_single_entry_point(panel):
    from nightscribe.core import followup as fu
    vp, pid, _o = panel
    vp.btn_new.click()
    sessions = fu.list_sessions(vp._db, pid)
    assert len(sessions) == 1
    # the new visit is selected and the detail card is live
    assert vp.current_session_id() == sessions[0]["id"]
    assert vp.findChild(type(vp.lst), "vp_resources") is not None
    assert "1" in vp.lbl_count.text()


def test_attach_fits_with_editable_meta(panel, monkeypatch, tmp_path):
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from PySide6.QtWidgets import QDialog, QFileDialog
    vp, pid, _o = panel
    vp.btn_new.click()
    sid = vp.current_session_id()
    fake = str(tmp_path / "plate.fits")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([fake], ""))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    vp._on_attach()
    imgs = fu.list_images(vp._db, sid)
    assert len(imgs) == 1
    assert imgs[0]["fits_path"] == fake
    # and the registry row carries the visit link (ADR-045)
    row = [f for f in proj_mod.list_files(vp._db, pid)
           if f["path"] == fake][0]
    assert row["kind"] == "fits" and row["session_id"] == sid


def test_attach_generic_file_needs_no_dialog(panel, monkeypatch, tmp_path):
    from nightscribe.core import project as proj_mod
    from PySide6.QtWidgets import QFileDialog
    vp, pid, _o = panel
    vp.btn_new.click()
    sid = vp.current_session_id()
    fake = str(tmp_path / "notes.csv")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([fake], ""))
    vp._on_attach()     # no metadata dialog for a non-FITS
    row = [f for f in proj_mod.list_files(vp._db, pid)
           if f["path"] == fake][0]
    assert row["kind"] == "report" and row["session_id"] == sid


def test_remove_resource_unlinks_only(panel, monkeypatch, tmp_path):
    from nightscribe.core import project as proj_mod
    from PySide6.QtWidgets import QDialog, QFileDialog
    vp, pid, _o = panel
    vp.btn_new.click()
    fake = str(tmp_path / "plate.fits")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([fake], ""))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    vp._on_attach()
    vp.lst_res.setCurrentRow(0)
    vp._on_remove_resource()
    assert proj_mod.list_files(vp._db, pid) == []


def test_open_fits_routes_to_the_editor_callback(panel, monkeypatch,
                                                 tmp_path):
    from PySide6.QtWidgets import QDialog, QFileDialog
    vp, _pid, opened = panel
    vp.btn_new.click()
    sid = vp.current_session_id()
    fake = str(tmp_path / "plate.fits")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([fake], ""))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    vp._on_attach()
    vp.lst_res.setCurrentRow(0)
    vp._on_open_resource()
    assert opened == [(fake, sid)]


def test_measurements_add_and_delete(panel):
    from nightscribe.core import followup as fu
    vp, pid, _o = panel
    vp.btn_new.click()
    sid = vp.current_session_id()
    vp.spn_mag.setValue(16.25)
    vp.cmb_filt.setCurrentText("V")
    vp._on_add_measurement()
    pts = fu.list_points(vp._db, pid)
    assert len(pts) == 1 and pts[0]["session_id"] == sid
    assert pts[0]["source"] == "manual"
    vp.lst_meas.setCurrentRow(0)
    vp._on_delete_measurement()
    assert fu.list_points(vp._db, pid) == []


def test_delete_visit_keeps_points_unlinked(panel):
    from nightscribe.core import followup as fu
    from PySide6.QtWidgets import QMessageBox
    vp, pid, _o = panel
    vp.btn_new.click()
    sid = vp.current_session_id()
    vp.spn_mag.setValue(16.0)
    vp._on_add_measurement()
    orig = QMessageBox.question
    QMessageBox.question = lambda *a, **k: QMessageBox.Yes
    try:
        vp._on_delete_visit()
    finally:
        QMessageBox.question = orig
    assert fu.list_sessions(vp._db, pid) == []
    pts = fu.list_points(vp._db, pid)
    assert len(pts) == 1 and pts[0]["session_id"] is None


def test_no_measurement_block_for_non_curve_kinds(qapp, tmp_path):
    from nightscribe.core.db import Database
    from nightscribe.core import project
    from nightscribe.gui.widgets.visits_panel import VisitsPanel
    db = Database(tmp_path / "n.db")
    p = project.create(db, "neo", "2026 QK")
    vp = VisitsPanel(db, lang="en", curve_kind=False)
    vp.set_project(p["id"])
    vp.btn_new.click()
    assert vp.findChild(type(vp.lst), "vp_measurements") is None
    # resources and notes remain for every kind
    assert vp.findChild(type(vp.lst), "vp_resources") is not None
    vp.deleteLater()
    db.close()
