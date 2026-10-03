############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the visits panel and its window (ADR-045)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/widgets/visits_panel.py: the Analysis tab's
core. The tab keeps the light overview (list, count, the single primary
entry point); the visit's work (resources, measurements, notes) lives in
the VisitWindow, opened by the primary action or a double-click and never
modal. The attach/remove cycle against the real registry, the rule that
nothing attaches without a visit, the measurement block (curve kinds
only), and the visit deletion contract (points and files survive,
unlinked). No network.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402

from nightscribe.gui.widgets.passive_wheel import PassiveList  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp, tmp_path):
    # @return: (panel, project_id, opened) on a temp database
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
    vp.close_visit_window()
    vp.deleteLater()
    db.close()


def test_empty_state_first(panel):
    vp, _pid, _o = panel
    assert vp.lbl_empty.isVisibleTo(vp)
    assert not vp.lst.isVisibleTo(vp)
    # the rule: nothing attaches without a visit — no attach action
    # exists outside one, and no window is open
    assert vp._win is None
    assert not vp.btn_open.isEnabled()


def test_new_visit_opens_its_window(panel):
    from nightscribe.core import followup as fu
    from nightscribe.gui.widgets.visits_panel import VisitWindow
    vp, pid, _o = panel
    vp.btn_new.click()
    sessions = fu.list_sessions(vp._db, pid)
    assert len(sessions) == 1
    # the new visit is selected and its window opened (non-modal)
    assert vp.current_session_id() == sessions[0]["id"]
    assert isinstance(vp._win, VisitWindow)
    assert vp._win._sid == sessions[0]["id"]
    assert "1" in vp.lbl_count.text()
    assert not vp.lbl_empty.isVisibleTo(vp)


def test_window_closes_on_project_switch(panel):
    vp, _pid, _o = panel
    vp.btn_new.click()
    assert vp._win is not None
    vp.set_project(999)      # another project: the window dies with it
    assert vp._win is None


def test_reopen_after_the_user_closed_the_window(panel, qapp):
    # The field bug (2026-09-24): WA_DeleteOnClose deletes the window's
    # C++ object when the user closes it; reopening must never call into
    # the deleted object.
    vp, _pid, _o = panel
    vp.btn_new.click()
    first = vp._win
    first.close()                       # the user closes the window
    qapp.processEvents()                # the deletion is delivered
    assert vp._win is None
    vp.btn_new.click()                  # must not raise
    assert vp._win is not None and vp._win is not first


def test_attach_fits_with_editable_meta(panel, monkeypatch, tmp_path):
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from PySide6.QtWidgets import QDialog, QFileDialog
    vp, pid, _o = panel
    vp.btn_new.click()
    w = vp._win
    sid = vp.current_session_id()
    fake = str(tmp_path / "plate.fits")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([fake], ""))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    w._on_attach()
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
    w = vp._win
    sid = vp.current_session_id()
    fake = str(tmp_path / "notes.csv")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([fake], ""))
    w._on_attach()      # no metadata dialog for a non-FITS
    row = [f for f in proj_mod.list_files(vp._db, pid)
           if f["path"] == fake][0]
    assert row["kind"] == "report" and row["session_id"] == sid


def test_remove_resource_unlinks_only(panel, monkeypatch, tmp_path):
    from nightscribe.core import project as proj_mod
    from PySide6.QtWidgets import QDialog, QFileDialog
    vp, pid, _o = panel
    vp.btn_new.click()
    w = vp._win
    fake = str(tmp_path / "plate.fits")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([fake], ""))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    w._on_attach()
    w.lst_res.setCurrentRow(0)
    w._on_remove_resource()
    assert proj_mod.list_files(vp._db, pid) == []


def test_open_fits_routes_to_the_editor_callback(panel, monkeypatch,
                                                 tmp_path):
    from PySide6.QtWidgets import QDialog, QFileDialog
    vp, _pid, opened = panel
    vp.btn_new.click()
    w = vp._win
    sid = vp.current_session_id()
    fake = str(tmp_path / "plate.fits")
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([fake], ""))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Accepted)
    w._on_attach()
    w.lst_res.setCurrentRow(0)
    w._on_open_resource()
    assert opened == [(fake, sid)]


def test_measurements_add_and_delete(panel):
    from nightscribe.core import followup as fu
    vp, pid, _o = panel
    vp.btn_new.click()
    w = vp._win
    sid = vp.current_session_id()
    w.spn_mag.setValue(16.25)
    w.cmb_filt.setCurrentText("V")
    w._on_add_measurement()
    pts = fu.list_points(vp._db, pid)
    assert len(pts) == 1 and pts[0]["session_id"] == sid
    assert pts[0]["source"] == "manual"
    w.lst_meas.setCurrentRow(0)
    w._on_delete_measurement()
    assert fu.list_points(vp._db, pid) == []


def test_delete_visit_keeps_points_unlinked(panel):
    from nightscribe.core import followup as fu
    from PySide6.QtWidgets import QMessageBox
    vp, pid, _o = panel
    vp.btn_new.click()
    w = vp._win
    sid = vp.current_session_id()
    w.spn_mag.setValue(16.0)
    w._on_add_measurement()
    orig = QMessageBox.question
    QMessageBox.question = lambda *a, **k: QMessageBox.Yes
    try:
        w._on_delete_visit()
    finally:
        QMessageBox.question = orig
    assert fu.list_sessions(vp._db, pid) == []
    pts = fu.list_points(vp._db, pid)
    assert len(pts) == 1 and pts[0]["session_id"] is None
    # and the panel forgets the visit (the window closed with it)
    assert vp.lst.count() == 0


def test_notes_autosave_from_the_window(panel):
    from nightscribe.core import followup as fu
    vp, pid, _o = panel
    vp.btn_new.click()
    sid = vp.current_session_id()
    vp._win._notes.setPlainText("Clear night, good seeing")
    assert fu.get_session(vp._db, sid)["notes"] == "Clear night, good seeing"


def test_no_measurement_block_for_non_curve_kinds(qapp, tmp_path):
    from nightscribe.core.db import Database
    from nightscribe.core import project
    from nightscribe.gui.widgets.visits_panel import VisitsPanel
    db = Database(tmp_path / "n.db")
    p = project.create(db, "neo", "2026 QK")
    vp = VisitsPanel(db, lang="en", curve_kind=False)
    vp.set_project(p["id"])
    vp.btn_new.click()
    assert vp._win.findChild(PassiveList, "vp_measurements") is None
    # resources and notes remain for every kind
    assert vp._win.findChild(PassiveList, "vp_resources") is not None
    vp.close_visit_window()
    vp.deleteLater()
    db.close()


# ---------------- the night's astrometry block (ADR-045, form A) -------

def _neo_panel(qapp, tmp_path):
    # @return: (panel, pid) for a NEO project (the MPC block shows)
    from nightscribe.core.db import Database
    from nightscribe.core import project
    from nightscribe.gui.widgets.visits_panel import VisitsPanel
    db = Database(tmp_path / "m.db")
    p = project.create(db, "neo", "2099 MPC",
                       {"ra_deg": 10.0, "dec_deg": 20.0})
    vp = VisitsPanel(db, lang="en", kind="neo", on_change=lambda: None)
    vp.set_project(p["id"])
    return vp, p["id"], db


def test_mpc_block_lives_in_the_window_for_neo(qapp, tmp_path):
    from PySide6.QtWidgets import QPushButton
    vp, _pid, db = _neo_panel(qapp, tmp_path)
    vp.btn_new.click()
    assert vp._win.findChild(QPushButton, "vp_mpc_save") is not None
    vp.close_visit_window()
    vp.deleteLater()
    db.close()


def test_mpc_block_absent_for_sn(panel):
    # an SN visit has no astrometry block (curve kinds keep measurements)
    from PySide6.QtWidgets import QPushButton
    vp, _pid, _o = panel
    vp.btn_new.click()
    assert vp._win.findChild(QPushButton, "vp_mpc_save") is None


def test_mpc_save_registers_to_the_windows_visit(qapp, tmp_path,
                                                 monkeypatch):
    from test_mpc_report import _MPC80_GOOD
    from nightscribe.core import project as proj_mod
    from PySide6.QtWidgets import QFileDialog
    vp, pid, db = _neo_panel(qapp, tmp_path)
    vp.btn_new.click()
    w = vp._win
    sid = vp.current_session_id()
    out = tmp_path / "report.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(out), ""))
    w.txt_mpc.setPlainText(_MPC80_GOOD)
    w._on_mpc_save()
    rows = proj_mod.list_files(db, pid)
    assert len(rows) == 1 and rows[0]["kind"] == "report"
    assert rows[0]["session_id"] == sid
    assert out.exists()
    # the visit is dated today, the report carries 2021-03-15: the
    # mismatch warning must show (and never block)
    assert "⚠" in w.lbl_mpc_status.text()
    vp.close_visit_window()
    vp.deleteLater()
    db.close()


def test_mpc_save_matching_date_warns_nothing(qapp, tmp_path, monkeypatch):
    from test_mpc_report import _MPC80_GOOD
    from nightscribe.core import followup as fu
    from PySide6.QtWidgets import QFileDialog
    vp, pid, db = _neo_panel(qapp, tmp_path)
    sid = fu.create_session(db, pid, obs_date="2021-03-15")
    vp.refresh()
    w = vp.open_visit(sid)
    out = tmp_path / "report.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        lambda *a, **k: (str(out), ""))
    w.txt_mpc.setPlainText(_MPC80_GOOD)
    w._on_mpc_save()
    assert "⚠" not in w.lbl_mpc_status.text()
    vp.close_visit_window()
    vp.deleteLater()
    db.close()


# ---------------- pin and the editable date (ADR-045 review) -----------

def test_visit_date_editable_from_the_window(panel):
    from nightscribe.core import followup as fu
    vp, pid, _o = panel
    vp.btn_new.click()
    sid = vp.current_session_id()
    # the save gesture arms exactly while the field is dirty (the field
    # report: an invisible save-on-focus-out alone leaves the observer
    # guessing)
    btn = vp._win.btn_save_date
    assert not btn.isEnabled()
    vp._win._date_ed.setText("2026-09-20")
    assert btn.isEnabled()
    btn.click()
    assert fu.get_session(vp._db, sid)["obs_date"] == "2026-09-20"
    assert not btn.isEnabled()          # clean again after the save
    assert vp.lst.item(0).text().startswith("2026-09-20")
    # Enter/focus-out shares the same path
    vp._win._date_ed.setText("2026-09-21")
    vp._win._on_date_edited()
    assert fu.get_session(vp._db, sid)["obs_date"] == "2026-09-21"
    # an invalid date reverts to the stored one, text selected, no crash
    vp._win._date_ed.setText("ayer por la noche")
    vp._win._on_date_edited()
    assert vp._win._date_ed.text() == "2026-09-21"
    assert not btn.isEnabled()
    assert fu.get_session(vp._db, sid)["obs_date"] == "2026-09-21"


def test_pinned_visit_floats_to_the_top(panel):
    from nightscribe.core import followup as fu
    vp, pid, _o = panel
    fu.create_session(vp._db, pid, "2026-09-22")
    sid_old = fu.create_session(vp._db, pid, "2026-09-20")
    vp.refresh()
    assert vp.lst.item(0).data(Qt.UserRole) != sid_old   # newest first
    vp.open_visit(sid_old)
    vp._win.btn_pin.setChecked(True)
    # the pinned visit leads the list, marked
    assert vp.lst.item(0).data(Qt.UserRole) == sid_old
    assert vp.lst.item(0).text().startswith("📌")
    vp.open_visit(sid_old)
    vp._win.btn_pin.setChecked(False)
    assert vp.lst.item(0).data(Qt.UserRole) != sid_old


def test_save_and_close_flushes_the_date_and_closes(panel, qapp):
    # The explicit closing gesture: a dirty valid date saves, the window
    # closes and the panel forgets it (the destroyed signal).
    from nightscribe.core import followup as fu
    vp, pid, _o = panel
    vp.btn_new.click()
    sid = vp.current_session_id()
    w = vp._win
    w._date_ed.setText("2026-09-19")
    assert w.btn_save_date.isEnabled()
    w.btn_close.click()
    assert fu.get_session(vp._db, sid)["obs_date"] == "2026-09-19"
    qapp.processEvents()
    assert vp._win is None


def test_save_and_close_reverts_an_invalid_date(panel, qapp):
    # a dirty INVALID value reverts to the stored one and the window
    # still closes: nothing is ever saved silently nor lost silently
    from nightscribe.core import followup as fu
    vp, pid, _o = panel
    vp.btn_new.click()
    sid = vp.current_session_id()
    stored = fu.get_session(vp._db, sid)["obs_date"]
    w = vp._win
    w._date_ed.setText("no es una fecha")
    w.btn_close.click()
    assert fu.get_session(vp._db, sid)["obs_date"] == stored
    qapp.processEvents()
    assert vp._win is None


def test_visit_window_measure_series_action(qapp, tmp_path):
    # ADR-048 (D8/D36): the visit window carries a "Measure the sequence"
    # action that hands the visit id to the host (which opens the editor's
    # series block). The action exists only with a callback armed.
    from nightscribe.core.db import Database
    from nightscribe.core import project, followup as fu
    from nightscribe.gui.widgets.visits_panel import VisitWindow
    db = Database(tmp_path / "v.db")
    p = project.create(db, "transit", "HAT-P-32 b")
    sid = fu.create_session(db, p["id"], obs_date="2026-09-20")
    seen = []
    w = VisitWindow(db, p["id"], sid, lang="en", kind="transit",
                    measure_series=lambda s: seen.append(s))
    w._ui.vp_btn_series.click()
    assert seen == [sid]
    w.close()
    db.close()


# ---------------- batch FITS attach (review: one dialog, not N) -------

def _fits(path, filt="V", date="2026-09-20T23:30:00", exp=10.0):
    # a minimal header-only FITS (fits_meta only reads the header)
    def card(k, v):
        s = k.ljust(8) if v is None else f"{k.ljust(8)}= {v}"
        return s[:80].ljust(80)
    cards = [card("SIMPLE", "T"), card("BITPIX", "-32"), card("NAXIS", "0"),
             card("FILTER", f"'{filt}'"), card("DATE-OBS", f"'{date}'"),
             card("EXPTIME", str(exp)), card("END", None)]
    data = "".join(cards).encode("latin-1")
    data += b" " * ((2880 - len(data) % 2880) % 2880)
    from pathlib import Path
    Path(path).write_bytes(data)
    return str(path)


def test_attach_fits_asks_once_and_registers_all(panel, monkeypatch,
                                                 tmp_path):
    from PySide6.QtWidgets import QFileDialog, QDialog
    from nightscribe.core import project as proj_mod
    vp, pid, _o = panel
    vp.btn_new.click()
    w = vp._win
    files = [_fits(tmp_path / f"seq{i}.fits") for i in range(5)]
    calls = []

    class _Cnt:
        def __call__(self):
            calls.append(1)
            return QDialog.Accepted

    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        staticmethod(lambda *a, **k: (files, "")))
    monkeypatch.setattr(QDialog, "exec", _Cnt())
    w._on_attach()
    rows = proj_mod.files_for_session(vp._db, w._sid)
    assert len(rows) == 5
    assert len(calls) == 1                    # ONE dialog for the batch
    assert all((r.get("meta") or {}).get("filter") == "V" for r in rows)


def test_attach_fits_cancel_registers_nothing(panel, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QDialog
    from nightscribe.core import project as proj_mod
    vp, pid, _o = panel
    vp.btn_new.click()
    w = vp._win
    files = [_fits(tmp_path / f"x{i}.fits") for i in range(3)]
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        staticmethod(lambda *a, **k: (files, "")))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Rejected)
    w._on_attach()
    assert proj_mod.files_for_session(vp._db, w._sid) == []


def test_attach_fits_lists_the_exception(panel, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog, QDialog
    vp, pid, _o = panel
    vp.btn_new.click()
    w = vp._win
    files = [_fits(tmp_path / f"a{i}.fits") for i in range(3)]
    files.append(_fits(tmp_path / "odd.fits", filt="R"))   # one off-filter
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        staticmethod(lambda *a, **k: (files, "")))
    seen = {}
    monkeypatch.setattr(QDialog, "exec",
                        lambda self: QDialog.Accepted)
    # capture the dialog's exceptions list via the build step
    import nightscribe.gui.widgets.visits_panel as vp_mod
    orig = vp_mod.adopt_ui

    def _spy(host, name):
        ui = orig(host, name)
        if name == "visit_files_meta":
            seen["ui"] = ui
        return ui
    monkeypatch.setattr(vp_mod, "adopt_ui", _spy)
    w._on_attach()
    assert seen["ui"].lst_except.count() == 1
