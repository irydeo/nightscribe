############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the astrometry runs of the Analysis tab
# (ADR-062, offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The runs of a moving object, read back without opening the editor.

ADR-062 phase 8 writes one astrometry_runs row per execution, its
observations and its frame manifest; what was missing was a place to SEE
them. These tests drive the Analysis block offscreen: an empty project
hides the whole section, a run is listed with its motion, its check and
its state, the magnitude says WHO wrote it (the run or a measurement made
by hand), both buttons follow the selection, and undoing an execution
empties its observations while the run stays for the audit.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # Redirect the shared db singleton to a throwaway file so the tests
    # never touch the real database (mirrors test_neo_process.py).
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("astroruns") / "t.db")
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
    orig_cfg = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


def _project(window):
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = project.create(mw.db, "neo", "2025 UR",
                       {"ra_deg": 10.0, "dec_deg": 20.0})
    window._current_project = p
    return p


def _run(window, p, **kwargs):
    # @return: the run id, with one stack point and one frames point
    import nightscribe.gui.main_window as mw
    from nightscribe.core import astrometry_store as store
    mjd = kwargs.pop("mjd", 60600.5)
    run = store.create_run(
        mw.db, p["id"], None, {"method": "sum"}, status="complete",
        object_name="2025 UR", method="sum", n_frames=30, n_obs=1,
        rate_arcsec_min=kwargs.pop("rate", 12.34),
        pa_deg=kwargs.pop("pa", 245.0), **kwargs)
    for source, mag in (("stack", 18.18), ("frames", 18.24)):
        store.add_points(mw.db, [{
            "run_id": run, "project_id": p["id"], "session_id": None,
            "group_index": 0, "mjd": mjd, "ra": 10.0, "dec": 20.0,
            "rms_ra": 0.2, "rms_dec": 0.2, "mag": mag, "band": "G",
            "n_frames": 30, "snr": 12.0, "source": source,
            "method": "sum", "check_ok": True,
            "check_note": "residual within the published path"}])
    return run


def _block(window, p):
    # @return: the runs table, with the block built over a throwaway layout
    from PySide6.QtWidgets import QVBoxLayout
    window._analysis_astrometry_block(QVBoxLayout(), p, p["id"])
    return window._project_widgets["astrometry_runs_tbl"]


def test_an_empty_project_hides_the_block(window):
    # An empty list of runs says nothing, and a folded block with nothing
    # inside is noise (ADR-038): the whole section hides itself.
    p = _project(window)
    tbl = _block(window, p)
    assert tbl.rowCount() == 0
    # isHidden() is the explicit hide; isVisible() would be False anyway
    # because the test's layout is never shown
    assert window._project_widgets["astrometry_runs_sec"].isHidden() is True


def test_the_run_is_listed_with_its_motion_check_and_state(window):
    p = _project(window)
    _run(window, p)
    tbl = _block(window, p)
    assert tbl.rowCount() == 1
    assert window._project_widgets["astrometry_runs_sec"].isHidden() is False
    assert tbl.item(0, 1).text() == "1"                    # observations
    assert "12.34" in tbl.item(0, 2).text()                # the resolved rate
    assert "PA 245" in tbl.item(0, 2).text()
    assert tbl.item(0, 4).text() == "in order"             # the check
    assert tbl.item(0, 4).toolTip() == \
        "residual within the published path"
    assert tbl.item(0, 5).text() == "complete"


def test_double_click_opens_the_run(window, monkeypatch):
    # ADR-062 rev: double-clicking a run row opens it in the editor, like the
    # "Open in the editor" button.
    import nightscribe.gui.main_window as mw
    from nightscribe.core import astrometry_store as store
    from PySide6.QtWidgets import QVBoxLayout
    p = _project(window)
    sid = mw.db.execute(
        "INSERT INTO project_sessions (project_id, obs_date, notes, created)"
        " VALUES (?, '2026-10-13', '', 1.0)", (p["id"],)).lastrowid
    mw.db.commit()
    rid = store.create_run(mw.db, p["id"], sid, {}, status="complete",
                           object_name="A", n_obs=1)
    window._analysis_astrometry_block(QVBoxLayout(), p, p["id"])
    tbl = window._project_widgets["astrometry_runs_tbl"]
    opened = []
    monkeypatch.setattr(window, "_open_astrometry_run",
                        lambda run: opened.append(run["id"]))
    tbl.selectRow(0)
    tbl.itemDoubleClicked.emit(tbl.item(0, 0))
    assert opened == [rid]


def test_with_busy_runs_the_work_and_returns_it(window):
    # the static busy dialog wraps the work and hands its result back
    assert window._with_busy("x", lambda: 42) == 42


def test_opening_a_run_uses_the_busy_dialog(window, monkeypatch):
    import nightscribe.gui.main_window as mw
    from nightscribe.core import astrometry_store as store
    p = _project(window)
    sid = mw.db.execute(
        "INSERT INTO project_sessions (project_id, obs_date, notes, created)"
        " VALUES (?, '2026-10-13', '', 1.0)", (p["id"],)).lastrowid
    mw.db.commit()
    rid = store.create_run(mw.db, p["id"], sid, {}, status="complete",
                           object_name="A", n_obs=1)
    run = next(r for r in store.list_runs(mw.db, p["id"]) if r["id"] == rid)
    called = []
    monkeypatch.setattr(window, "_with_busy",
                        lambda label, fn: (called.append(label), fn())[1])
    monkeypatch.setattr(window, "_visit_astrometry",
                        lambda *a, **k: called.append(("open", a, k)))
    window._open_astrometry_run(run)
    assert ("open", (p["id"], sid), {"run_id": rid}) in called


def test_opening_a_run_tells_the_tab_which_run_to_show(window, monkeypatch):
    # Reported 2026-10-16: a run with 7 observations did not load when the
    # editor was already on that visit. The session key is (project, visit),
    # so another run of the same visit reset nothing and the tab kept the run
    # it held. The host now asks the tab to forget it, by id, before loading
    # the plate (the tab does nothing when the right run is already there).
    import nightscribe.gui.main_window as mw
    from nightscribe.core import astrometry_store as store
    from nightscribe.core import project as proj_mod
    p = _project(window)
    sid = mw.db.execute(
        "INSERT INTO project_sessions (project_id, obs_date, notes, created)"
        " VALUES (?, '2026-10-16', '', 1.0)", (p["id"],)).lastrowid
    mw.db.commit()
    rid = store.create_run(mw.db, p["id"], sid, {}, status="complete",
                           object_name="2025 UR", n_obs=7)
    monkeypatch.setattr(
        proj_mod, "files_for_session",
        lambda _db, _sid: [{"kind": "fits", "path": "/tmp/plate.fits"}])
    calls = []

    class FakeTab:
        def forget_run(self, run_id):
            calls.append(("forget", run_id))

        def show_run_on_stage(self):
            calls.append(("stage", None))
            return True

    class FakeDlg:
        tab_trackstack = FakeTab()

        def open_plate(self, path):
            calls.append(("plate", path))
            return True

        def set_object(self, obj):
            pass

        def show_tab(self, tab):
            pass

    monkeypatch.setattr(window, "_ufe_open", lambda *a, **k: FakeDlg())
    window._visit_astrometry(p["id"], sid, run_id=rid)
    # the run is forgotten, then the plate is loaded (it arms the navigator)
    # and only then the run's own observation goes back on stage
    assert [c[0] for c in calls] == ["forget", "plate", "stage"]
    assert calls[0] == ("forget", rid)
    # and a visit's own button (no run picked) asks for nothing by name
    calls.clear()
    window._visit_astrometry(p["id"], sid)
    assert [c[0] for c in calls] == ["plate", "stage"]


def test_a_visit_click_filters_the_runs(window):
    # ADR-086 rev: one click on a visit shows only ITS runs.
    import nightscribe.gui.main_window as mw
    from nightscribe.core import astrometry_store as store
    from PySide6.QtWidgets import QVBoxLayout
    p = _project(window)
    sid = mw.db.execute(
        "INSERT INTO project_sessions (project_id, obs_date, notes, created)"
        " VALUES (?, '2026-10-13', '', 1.0)", (p["id"],)).lastrowid
    mw.db.commit()
    store.create_run(mw.db, p["id"], sid, {}, status="complete",
                     object_name="A", n_obs=1)
    store.create_run(mw.db, p["id"], None, {}, status="complete",
                     object_name="A", n_obs=1)
    window._analysis_astrometry_block(QVBoxLayout(), p, p["id"])
    tbl = window._project_widgets["astrometry_runs_tbl"]
    assert tbl.rowCount() == 2
    window._set_analysis_visit_filter(p["id"], sid)
    assert tbl.rowCount() == 1
    window._set_analysis_visit_filter(p["id"], None)
    assert tbl.rowCount() == 2


def test_combined_block_lists_and_persists_the_selection(window):
    # ADR-086: all the project's measurements in one place, ticked by the
    # observer; the selection is saved (per observation).
    import nightscribe.gui.main_window as mw
    from nightscribe.core import astrometry_store as store
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QVBoxLayout
    p = _project(window)
    _run(window, p, mjd=60600.5)
    _run(window, p, mjd=60601.5, rate=15.0)          # a different night
    window._analysis_combined_block(QVBoxLayout(), p, p["id"])
    tbl = window._project_widgets["combined_tbl"]
    assert tbl.rowCount() == 2
    assert tbl.item(0, 0).checkState() == Qt.Checked     # all in by default
    tbl.item(0, 0).setCheckState(Qt.Unchecked)
    saved = store.get_combined(mw.db, p["id"])
    assert len(saved["included"]) == 1


def test_combined_block_merges_re_measures_of_the_same_observation(window):
    # ADR-086 rev: four runs at the same instant are ONE observation, not four
    # (feeding Find_Orb duplicate points produced absurd residuals).
    import nightscribe.gui.main_window as mw
    from nightscribe.core import astrometry_store as store
    from PySide6.QtWidgets import QVBoxLayout
    p = _project(window)
    _run(window, p, mjd=60600.5)
    _run(window, p, mjd=60600.5)
    _run(window, p, mjd=60600.5)
    obs, merged = store.dedupe_observations(store.project_observations(
        mw.db, p["id"]))
    assert len(obs) == 1 and merged == 2
    window._analysis_combined_block(QVBoxLayout(), p, p["id"])
    assert window._project_widgets["combined_tbl"].rowCount() == 1


def test_combined_report_needs_a_tick(window):
    from PySide6.QtWidgets import QVBoxLayout
    p = _project(window)
    _run(window, p)
    window._analysis_combined_block(QVBoxLayout(), p, p["id"])
    tbl = window._project_widgets["combined_tbl"]
    tbl.item(0, 0).setCheckState(tbl.item(0, 0).checkState())   # no-op
    # unticking everything leaves nothing to report
    from PySide6.QtCore import Qt
    tbl.item(0, 0).setCheckState(Qt.Unchecked)
    window._analysis_combined_report(p["id"])
    assert "tick" in window._project_widgets["combined_lbl"].text().lower() \
        or window.statusBar().currentMessage() != ""


def test_the_date_is_a_date_and_not_an_epoch(window):
    # `created` stores epoch seconds and SQLite's TEXT affinity hands them
    # back as a string, so the Date column printed "1791221326.12345" (seen
    # on a render): the number is parsed, not sliced.
    import re as _re
    p = _project(window)
    _run(window, p)
    tbl = _block(window, p)
    assert _re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$",
                     tbl.item(0, 0).text())


def test_the_magnitude_says_who_wrote_it(window):
    # The observer must never read a magnitude without knowing whether the
    # machine measured it or they did (D).
    import nightscribe.gui.main_window as mw
    from nightscribe.core import astrometry_store as store
    p = _project(window)
    run = _run(window, p)
    tbl = _block(window, p)
    assert tbl.item(0, 3).text() == "18.18 G (automatic)"
    # a measurement made by hand takes over the effective magnitude
    assert store.set_manual_magnitude(mw.db, run, 0, 17.98, "G") == 1
    window._analysis_astrometry_refresh(p["id"])
    assert tbl.item(0, 3).text() == "17.98 G (by hand)"


def test_both_buttons_follow_the_selection(window):
    p = _project(window)
    _run(window, p)
    tbl = _block(window, p)
    open_btn = window._project_widgets["astrometry_runs_btn_open"]
    undo_btn = window._project_widgets["astrometry_runs_btn_undo"]
    assert open_btn.isEnabled() is False
    assert undo_btn.isEnabled() is False
    tbl.selectRow(0)
    assert open_btn.isEnabled() is True
    assert undo_btn.isEnabled() is True


def test_undoing_a_run_empties_it_but_keeps_it_for_the_audit(window,
                                                              monkeypatch):
    import nightscribe.gui.main_window as mw
    from PySide6.QtWidgets import QMessageBox
    p = _project(window)
    run = _run(window, p)
    tbl = _block(window, p)
    tbl.selectRow(0)
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    window._analysis_astrometry_undo(tbl)
    # the observations go, the run stays marked as undone (the audit trail)
    assert tbl.rowCount() == 1
    assert tbl.item(0, 5).text() == "undone"
    assert tbl.item(0, 3).text() == "—"
    from nightscribe.core import astrometry_store as store
    assert store.points_for_run(mw.db, run) == []
    assert "undone" in window._project_widgets["astrometry_runs_note"].text()


def test_a_not_detected_run_is_listed_too(window):
    # "We looked and there was nothing" is data: the next night needs to
    # know it was tried.
    import nightscribe.gui.main_window as mw
    from nightscribe.core import astrometry_store as store
    p = _project(window)
    store.create_run(mw.db, p["id"], None, {}, status="not_detected",
                     object_name="2025 UR", n_obs=0)
    tbl = _block(window, p)
    assert tbl.rowCount() == 1
    assert tbl.item(0, 5).text() == "not detected"
    assert tbl.item(0, 3).text() == "—"
