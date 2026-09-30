############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: one night, one curve (reported 2026-09-30)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The chart of a visit was corrupted after closing and reopening the app.

The cause was not the drawing: the chart of a visit drew EVERY series run
of the visit at once. Measured on the observer's own database (V0526 Per,
30 Sep 2026): the visit held four passes, 976 points, at two different
levels (11.96-12.07 calibrated in G and 12.70-12.81 in V) joined by a
zigzag, while the live chart had drawn one run (244 points). Two visits
of another project held five passes each, and the project's own curve
added them all up too.

These tests drive the HOST hooks the editor calls (the same seam as
test_series_run_status.py) against a real database: the curve the chart
loads is one pass, the band it says is the one the calibration used, the
detrended curve comes back, and a live session is one run.
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
    tmp = dbmod.Database(tmp_path_factory.mktemp("visitcurve") / "t.db")
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
    p = project.create(mw.db, "variable", "V0526 Per")
    return p["id"], fu.create_session(mw.db, p["id"], obs_date="2026-09-30")


def _rows(n=3, mag0=12.70, filter_name=None, airmass0=None):
    # @return: the point rows the Measure tab sends for one pass
    out = []
    for i in range(n):
        row = {"mjd": 60297.77 + i * 0.002, "filter": filter_name,
               "mag": mag0 + i * 0.01, "err": 0.01, "mag_raw": -9.5 + i,
               "path": f"/tmp/f{i}.fits", "flags": [], "source": "measure"}
        if airmass0 is not None:
            row["airmass"] = airmass0 + i * 0.05
        out.append(row)
    return out


def _pass(window, pid, sid, rows, cfg):
    # @return: the run id of one stored pass
    return window._ufe_points_hook(pid, sid, rows, cfg)


def test_the_curve_the_chart_loads_is_the_visit_s_last_pass(window, visit):
    # The reported corruption, at its source: four passes, one curve.
    pid, sid = visit
    first = _pass(window, pid, sid, _rows(2, 12.70), {"band": "V"})
    second = _pass(window, pid, sid, _rows(3, 11.96), {"band": "G"})
    curve = window._ufe_visit_curve(pid, sid)
    points = curve["points"]
    assert len(points) == 3                    # one pass, not five points
    assert {round(p["mag"], 2) for p in points} == {11.96, 11.97, 11.98}
    assert all(p["source"] == "measure" for p in points)
    # and the first pass is still in the project for the trail
    from nightscribe.core import followup as fu
    import nightscribe.gui.main_window as mw
    assert len(fu.points_for_session(mw.db, sid, curve=False)) == 5
    assert fu.curve_run_for_session(mw.db, sid) == second
    assert first != second


def test_the_loaded_curve_says_the_band_it_was_calibrated_with(window, visit):
    # The frames of a real series carried no FILTER keyword, so the stored
    # points had no filter: a curve calibrated in G said "no filter" in the
    # chart and reached the AAVSO file with an empty filter. The band the
    # calibration used is in the RUN, and it is what the number means.
    pid, sid = visit
    _pass(window, pid, sid, _rows(2, 11.96), {"band": "G"})
    points = window._ufe_visit_curve(pid, sid)["points"]
    assert {p["filter"] for p in points} == {"G"}


def test_a_frame_filter_is_not_overwritten_by_a_missing_band(window, visit):
    # The other way round: when the observer chose no band but the frames
    # say which filter they were taken in, that one is the truth.
    pid, sid = visit
    _pass(window, pid, sid, _rows(2, 11.96, filter_name="R"), {"band": None})
    points = window._ufe_visit_curve(pid, sid)["points"]
    assert {p["filter"] for p in points} == {"R"}


def test_the_loaded_curve_brings_the_detrended_one_back(window, visit):
    # The detrended curve is not stored (only the raw magnitudes are), but
    # it is deterministic: the same points with the same airmass give the
    # same coefficients, so a reloaded curve can draw it again instead of
    # leaving the "show the detrended" switch with nothing to show.
    pid, sid = visit
    _pass(window, pid, sid, _rows(6, 11.96, airmass0=1.1),
          {"band": "G", "detrend_policy": "airmass"})
    points = window._ufe_visit_curve(pid, sid)["points"]
    raw = [p for p in points if p["source"] == "measure"]
    det = [p for p in points if p["source"] == "detrend"]
    assert len(raw) == 6 and len(det) == 6
    assert [p["mjd"] for p in det] == [p["mjd"] for p in raw]
    # the detrended points are the same night at another level: if the two
    # lists were equal, the curve would be a copy and the switch a lie
    assert [p["mag"] for p in det] != [p["mag"] for p in raw]


def test_a_pass_without_airmass_has_no_detrended_curve(window, visit):
    # Points measured before v14 have no airmass: there is nothing honest
    # to fit, so the detrended curve is simply absent (the panel says so).
    pid, sid = visit
    _pass(window, pid, sid, _rows(4, 11.96), {"band": "G",
                                              "detrend_policy": "airmass"})
    points = window._ufe_visit_curve(pid, sid)["points"]
    assert all(p["source"] == "measure" for p in points)


def test_the_passes_door_lists_them_and_goes_back(window, visit):
    # The observer's own question: "if we keep the old passes, how do we get
    # them back?". The door lists them, says which one is drawn and lets any
    # of them be that one WITHOUT deleting anything.
    pid, sid = visit
    first = _pass(window, pid, sid, _rows(2, 12.70), {"band": "V"})
    second = _pass(window, pid, sid, _rows(3, 11.96), {"band": "G"})
    payload = window._ufe_visit_passes(pid, sid)
    assert [r["id"] for r in payload["runs"]] == [first, second]
    assert payload["curve_run_id"] == second
    assert payload["runs"][0]["band"] == "V"
    assert payload["runs"][0]["points"] == 2
    assert payload["runs"][0]["status"] == "complete"
    # going back to the first pass: nothing is deleted
    assert window._ufe_choose_curve(pid, sid, first) is True
    assert window._ufe_visit_passes(pid, sid)["curve_run_id"] == first
    assert len(window._ufe_visit_curve(pid, sid)["points"]) == 2
    from nightscribe.core import followup as fu
    import nightscribe.gui.main_window as mw
    assert len(fu.points_for_session(mw.db, sid, curve=False)) == 5


def test_a_pass_that_is_undone_leaves_the_list_but_not_the_trail(window,
                                                                 visit):
    # A real visit had 26 undone passes against 4 that mattered: listing the
    # empty ones buries the ones you can choose. They are counted, not
    # listed, and nothing is deleted (the trail keeps every run).
    pid, sid = visit
    first = _pass(window, pid, sid, _rows(2, 12.70), {"band": "V"})
    _pass(window, pid, sid, _rows(3, 11.96), {"band": "G"})
    assert window._ufe_visit_passes(pid, sid)["undone_empty"] == 0
    assert window._ufe_run_undo(first) == 2          # the pass is undone
    payload = window._ufe_visit_passes(pid, sid)
    assert first not in [r["id"] for r in payload["runs"]]
    assert payload["undone_empty"] == 1
    # and the curve fell back to the pass before it
    assert len(window._ufe_visit_curve(pid, sid)["points"]) == 3


def test_a_live_batch_continues_the_run_its_session_opened(window, visit):
    # One live session, ONE run: the first batch opens it, the rest pile
    # into it. Two measured reasons: one click undoes the whole session,
    # and the curve reloaded from the project is the whole session instead
    # of its last batch (49 runs for one night otherwise).
    pid, sid = visit
    first = window._ufe_points_hook(pid, sid, _rows(2), {"band": "V"})
    second = window._ufe_points_hook(
        pid, sid, _rows(3), {"band": "V", "append_run": first})
    assert second == first
    from nightscribe.core import followup as fu
    import nightscribe.gui.main_window as mw
    assert len(fu.list_points_for_run(mw.db, first)) == 5
    # a run that is gone is never an error: the batch opens a new one
    third = window._ufe_points_hook(
        pid, sid, _rows(1), {"band": "V", "append_run": 999999})
    assert third not in (None, first)
    # and an undone run is not continued either (its points are gone)
    fu.set_run_status(mw.db, first, "undone")
    fourth = window._ufe_points_hook(
        pid, sid, _rows(1), {"band": "V", "append_run": first})
    assert fourth != first


def test_the_run_echo_never_carries_the_append_marker(window, visit):
    # The marker is plumbing, not configuration: it must not land in the
    # run's stored cfg (that row is the audit trail of how it was measured).
    pid, sid = visit
    first = _pass(window, pid, sid, _rows(2), {"band": "V"})
    _pass(window, pid, sid, _rows(2), {"band": "V", "append_run": first})
    import nightscribe.gui.main_window as mw
    row = mw.db.execute("SELECT cfg_json FROM measurement_runs WHERE id=?",
                        (first,)).fetchone()
    assert "append_run" not in json.loads(row[0])


# ---------------- multi-night: one pass, one run per visit -------------
#
# The observer's ask (2026-09-30): "en las secuencias multi-noche, en UFE no
# se cargan las imágenes de una visita (una noche), se han de cargar las de
# todas las visitas". A series that runs over several nights is measured in
# ONE pass: the frames of every visit, and each night's points filed in the
# visit that night is, so the visit's curve and the project's both read
# right.

def _frames(window, pid, sid, tag, n=2):
    # registers n frames of a visit and returns their paths
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project as project_mod
    out = []
    for i in range(n):
        path = f"/tmp/{tag}-{i}.fits"
        project_mod.add_file(mw.db, pid, path, "fits", session_id=sid,
                             meta={})
        out.append(path)
    return out


def _rows_for(paths, mag0=12.0, filter_name=None, airmass0=None):
    # filter_name None is what a real series sends when the frames carry no
    # FILTER keyword: the point then says the band the calibration used.
    # airmass0 is what the detrend needs (a night without airmass has no
    # detrended curve, which is honest and tested above).
    out = []
    for i, path in enumerate(paths):
        row = {"mjd": 60940.5 + i * 0.002, "filter": filter_name,
               "mag": mag0 + i * 0.01, "err": 0.01, "mag_raw": -9.5 + i,
               "path": path, "flags": [], "source": "measure"}
        if airmass0 is not None:
            row["airmass"] = airmass0 + i * 0.05
        out.append(row)
    return out


def test_the_multi_night_scope_hands_the_frames_of_every_visit(window, visit):
    pid, sid = visit
    from nightscribe.core import followup as fu
    other = fu.create_session(mw_db(), pid, obs_date="2026-09-29")
    _frames(window, pid, sid, "night-a", 2)
    _frames(window, pid, other, "night-b", 3)
    one = window._ufe_series_context(pid, sid, "visit")
    assert len(one["paths"]) == 2 and one["visits"] == 2
    allof = window._ufe_series_context(pid, sid, "project")
    assert len(allof["paths"]) == 5            # every night, one pass
    assert allof["nights"] == 2 and allof["scope"] == "project"


def mw_db():
    import nightscribe.gui.main_window as mw
    return mw.db


def test_a_multi_night_pass_writes_one_run_per_visit(window, visit):
    pid, sid = visit
    from nightscribe.core import followup as fu
    other = fu.create_session(mw_db(), pid, obs_date="2026-09-29")
    a = _frames(window, pid, sid, "pass-a", 2)
    b = _frames(window, pid, other, "pass-b", 3)
    run_id = window._ufe_points_hook(pid, sid, _rows_for(a + b), {"band": "V"})
    assert run_id is not None
    # two runs (one per night), each holding ITS night's points
    assert len(fu.points_for_session(mw_db(), sid)) == 2
    assert len(fu.points_for_session(mw_db(), other)) == 3
    # and both belong to the same pass
    group = fu.run_pass_group(mw_db(), run_id)
    assert group
    runs = fu.runs_in_pass(mw_db(), group)
    assert len(runs) == 2
    assert {r["session_id"] for r in runs} == {sid, other}
    # the project's curve is the two nights, once each
    assert len(fu.list_points(mw_db(), pid)) == 5


def test_undoing_a_multi_night_pass_undoes_every_night(window, visit):
    pid, sid = visit
    from nightscribe.core import followup as fu
    other = fu.create_session(mw_db(), pid, obs_date="2026-09-29")
    a = _frames(window, pid, sid, "undo-a", 2)
    b = _frames(window, pid, other, "undo-b", 3)
    run_id = window._ufe_points_hook(pid, sid, _rows_for(a + b), {"band": "V"})
    assert window._ufe_run_undo(run_id) == 5     # the WHOLE pass, one click
    assert fu.points_for_session(mw_db(), sid) == []
    assert fu.points_for_session(mw_db(), other) == []
    # the trail stays: the runs are marked, not deleted
    assert {r["status"] for r in fu.runs_in_pass(mw_db(), group_of(run_id))} \
        == {"undone"}


def group_of(run_id):
    from nightscribe.core import followup as fu
    return fu.run_pass_group(mw_db(), run_id)


def test_the_project_scope_curve_carries_the_band_of_each_night(window,
                                                                visit):
    # The whole-project curve is the union of the nights: each point says
    # the band ITS run was calibrated in, and the detrend is refitted per
    # night (one run, one night, one policy).
    pid, sid = visit
    from nightscribe.core import followup as fu
    other = fu.create_session(mw_db(), pid, obs_date="2026-09-29")
    a = _frames(window, pid, sid, "band-a", 3)
    b = _frames(window, pid, other, "band-b", 3)
    window._ufe_points_hook(pid, sid, _rows_for(a, 11.96, airmass0=1.1),
                            {"band": "G", "detrend_policy": "airmass"})
    window._ufe_points_hook(pid, other, _rows_for(b, 12.70), {"band": "V"})
    curve = window._ufe_visit_curve(pid, sid, "project")
    points = curve["points"]
    raw = [p for p in points if p["source"] == "measure"]
    det = [p for p in points if p["source"] == "detrend"]
    assert len(raw) == 6
    assert {p["filter"] for p in raw} == {"G", "V"}   # one per night
    assert det                                       # the G night's detrend
    assert {p["filter"] for p in det} == {"G"}
    # the visit's own scope is only its night
    own = window._ufe_visit_curve(pid, sid, "visit")["points"]
    assert len([p for p in own if p["source"] == "measure"]) == 3
