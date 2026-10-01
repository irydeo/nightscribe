############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: a series run keeps its real status (D18)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""A series the user cancelled used to be stored as a COMPLETE run
(usability review P2 #23a): the Measure tab answers "incomplete" with
the points measured so far (D18), but the host's points hook called
followup.create_run without the status, and the column's default
("complete") won. The run row lied, and "incomplete" is exactly the
state ADR-048 wants visible after a restart.

The tab now sends the run's real status in its echo and the hook lifts
it into the status column (never into cfg_json, which stays the config
echo). These tests drive the host hook against the real DB and read the
row back. Offscreen, no network, temp db (the test_main_window_close.py
harness pattern).
"""

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # main_window imports the shared `db` singleton; redirect it to a
    # throwaway file so nothing touches the real database.
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("runstatus") / "t.db")
    dbmod.db = tmp
    mw.db = tmp
    yield
    dbmod.db = old_dbmod
    mw.db = old_mw


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture(scope="module")
def window(_point_db_at_tmpdir, qapp):
    from nightscribe.config import config
    from nightscribe.gui.main_window import MainWindow
    orig_cfg = config.is_configured
    config.is_configured = lambda: False   # no auto-compute network worker
    w = MainWindow()
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


@pytest.fixture
def visit(_point_db_at_tmpdir):
    # A project with one visit: the series hook writes under it.
    # @return: (project id, session id)
    from nightscribe.core import followup as fu, project
    import nightscribe.gui.main_window as mw
    p = project.create(mw.db, "transit", "HAT-P-32b")
    return p["id"], fu.create_session(mw.db, p["id"])


def _rows(n=3):
    # @return: the point rows the Measure tab sends for one run
    return [{"mjd": 60940.5 + i * 0.002, "filter": "V",
             "mag": 14.100 + i * 0.01, "err": 0.008,
             "mag_raw": -13.900 + i * 0.01, "path": f"/tmp/f{i}.fits",
             "flags": [], "source": "measure"} for i in range(n)]


def _run_row(window, pid, sid, cfg):
    # @args: cfg - the run echo the tab sends
    # @return: (run id, status, cfg_json parsed, the run's points)
    from nightscribe.core import followup as fu
    import nightscribe.gui.main_window as mw
    run_id = window._ufe_points_hook(pid, sid, _rows(), cfg)
    row = mw.db.execute(
        "SELECT status, cfg_json FROM measurement_runs WHERE id=?",
        (run_id,)).fetchone()
    return run_id, row[0], json.loads(row[1]), fu.list_points_for_run(
        mw.db, run_id)


def test_cancelled_series_is_persisted_incomplete(window, qapp, visit):
    # The issue: the engine answered "incomplete" (cancelled) and the run
    # row said "complete". The real status must reach the column.
    pid, sid = visit
    echo = {"band": "V", "group_n": 1, "status": "incomplete"}
    run_id, status, cfg_json, points = _run_row(window, pid, sid, echo)
    assert status == "incomplete"
    assert len(points) == 3                 # the points measured so far
    assert all(p["run_id"] == run_id and p["session_id"] == sid
               for p in points)
    # the status lives in its column, not in the config echo
    assert cfg_json == {"series": {"band": "V", "group_n": 1}}
    # ... and the tab's own dict is left alone
    assert echo["status"] == "incomplete"
    assert "3 points" in window.statusBar().currentMessage()


def test_complete_series_is_persisted_complete(window, qapp, visit):
    # The unchanged happy path: a run that measured every frame stays
    # "complete".
    pid, sid = visit
    _run_id, status, cfg_json, points = _run_row(
        window, pid, sid, {"band": "V", "status": "complete"})
    assert status == "complete"
    assert len(points) == 3
    assert cfg_json == {"series": {"band": "V"}}


def test_echo_without_a_status_defaults_to_complete(window, qapp, visit):
    # The Live mode commits whole batches and sends the plain config
    # echo (no status): those runs are complete, as before.
    pid, sid = visit
    _run_id, status, cfg_json, _points = _run_row(
        window, pid, sid, {"band": "Clear", "group_n": 4})
    assert status == "complete"
    assert cfg_json == {"series": {"band": "Clear", "group_n": 4}}
