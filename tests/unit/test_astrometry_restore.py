############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: reopening a visit shows its astrometry run
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Asked for: if a visit already holds a track & stack run, reopening it
must SHOW it (the notes, the points, the strip, the blink and the report)
instead of an empty column, the way the Photometry tab shows the visit's
curve, and the whole-sequence stack must come back with it so the manual mark
can still be placed.

The seam is the HOST: the tab never touches the database. `persist` writes
the run (its summary riding in cfg_json, so no schema change), and
`_ufe_astrometry_result` reads the last complete run of the visit back, with
its points and the stack files the visit registered.

These tests drive those two hooks against a real database, and the last one
drives BOTH ends at once (the host's answer into the real tab), which is what
proves they speak the same language.
"""

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
    tmp = dbmod.Database(tmp_path_factory.mktemp("astrometryrestore")
                         / "t.db")
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
def visit(_point_db_at_tmpdir, tmp_path):
    # A project with one visit, and a stack file registered on it.
    # @return: (project id, session id, the stack's path)
    import nightscribe.gui.main_window as mw
    from nightscribe.core import followup as fu, project
    p = project.create(mw.db, "neo", "2026 PY9")
    sid = fu.create_session(mw.db, p["id"], obs_date="2026-10-06")
    path = tmp_path / "2026PY9_obs1.fits"
    path.write_bytes(b"")               # the hook only needs it to exist
    project.add_file(mw.db, p["id"], str(path), "stack", session_id=sid)
    return p["id"], sid, str(path)


def _payload(mag=18.42):
    # @return: the worker's result dict, in the shape the tab hands over
    import numpy as np
    from nightscribe.core import astrometry, findorb, track_stack
    sp = astrometry.AstrometryPoint(
        ra=30.0, dec=10.0, rms_ra=0.2, rms_dec=0.2, x=8.0, y=8.0, snr=14.0,
        mag=mag, band="G", mjd=61000.5, n_frames=4, group_index=0,
        source="stack")
    fp = astrometry.AstrometryPoint(
        ra=30.0, dec=10.0, rms_ra=0.1, rms_dec=0.1, x=8.5, y=8.5, snr=8.0,
        mag=mag, band="G", mjd=61000.5, n_frames=4, group_index=0,
        source="frames")
    return {
        "status": "ok", "method": "sigma", "n_obs": 1, "n_failed": 0,
        "ephem_source": "horizons",
        "detection": track_stack.DetectionReport(detected=True, snr=14.0,
                                                 mag_limit=19.4),
        "dither": track_stack.DitherReport(dithered=True, spread_px=12.0),
        "wcs_qc": track_stack.WcsQCReport(checked=6, max_offset_arcsec=0.31,
                                          ok=True),
        "sweep": track_stack.SweepResult(best={"rate": 0.42, "pa": 271.0},
                                         grid=[{"rate": 0.42, "pa": 271.0}]),
        "photometry": {"mag": mag, "err": 0.11, "band": "G", "n_comps": 7,
                       "n_obs": 1, "n_frames": 4, "source": "project",
                       "trail_px": 2.4, "trail_pa_deg": 271.0,
                       "snr_gain": 1.6,
                       "limit": {"ok": True, "mag": 19.4,
                                 "sky_limited": True},
                       "grid": {"ok": True, "median": 0.18, "worst": 0.4}},
        "register_report": {"n_rotation": 2, "n_failed": 1,
                            "reasons": {"no stars": 1}},
        "check": findorb.CheckReport(available=True, blocked=False,
                                     our_residual=(0.31, -0.22),
                                     n_stations=4),
        "calibration": {"n": 139, "offsets": ["dark120.fits"],
                        "flats": ["flatG.fits"], "warnings": []},
        "points": [(sp, fp, [])],
        "stacks": [(np.zeros((8, 8), dtype=np.float32), None)],
        "star_stacks": [(np.zeros((8, 8), dtype=np.float32), None)],
        "boxes": [(0, 0, 8, 8)], "qs": [(8.0, 8.0)], "mids": [2461000.5],
        "w0": None, "frames": [],
        # the whole-sequence stack and what the manual mark needs to use it
        # on a run that is reopened
        "base_stack": np.zeros((8, 8), dtype=np.float32),
        "box_all": (10, 20, 42, 52), "q_all": (26.0, 36.0),
        "base_rate": 0.42, "base_pa": 271.0,
        # the ephemeris' own answer about the light
        "ephem_mag": 22.21, "ephem_band": "V",
        "ephem_mag_source": "horizons",
    }


def test_the_run_is_written_with_a_summary_the_visit_can_read_back(window,
                                                                  visit):
    # The run's own words ride in cfg_json: the detection, the sweep, the
    # brightness, the registration, the calibration and the check. No
    # schema change, and the summary is JSON (numpy scalars unwrapped).
    pid, sid, _path = visit
    run_id = window._ufe_astrometry_persist(pid, sid, _payload())
    assert run_id
    from nightscribe.core import astrometry_store as store
    import nightscribe.gui.main_window as mw
    run = [r for r in store.list_runs(mw.db, pid) if r["id"] == run_id][0]
    summary = (run["cfg"] or {}).get("result")
    assert summary, "the run carries its own summary"
    assert summary["detection"]["snr"] == pytest.approx(14.0)
    assert summary["detection"]["mag_limit"] == pytest.approx(19.4)
    assert summary["photometry"]["mag"] == pytest.approx(18.42)
    assert summary["photometry"]["limit"]["mag"] == pytest.approx(19.4)
    assert summary["register_report"]["reasons"] == {"no stars": 1}
    assert summary["calibration"]["flats"] == ["flatG.fits"]
    assert summary["check"]["available"] is True
    assert summary["check"]["our_residual"] == [0.31, -0.22]
    assert summary["check"]["n_stations"] == 4
    # What the manual mark needs on a run that is reopened: the base stack's
    # cutout origin in the reference grid, and the ephemeris' magnitude for
    # the band when the run did not measure the brightness.
    assert summary["box_all"] == [10, 20, 42, 52]
    assert summary["base_rate"] == pytest.approx(0.42)
    assert summary["base_pa"] == pytest.approx(271.0)
    assert summary["ephem_mag"] == pytest.approx(22.21)
    assert summary["ephem_band"] == "V"
    assert summary["ephem_mag_source"] == "horizons"
    assert summary["ephem_source"] == "horizons"
    # JSON in, JSON out: a numpy bool would have come back as the string
    # "True", which is truthy for the wrong reason
    import json
    assert json.loads(json.dumps(summary)) == summary


def test_the_visit_hands_back_its_last_run_with_points_and_stacks(window,
                                                                  visit):
    pid, sid, path = visit
    run_id = window._ufe_astrometry_persist(pid, sid, _payload())
    data = window._ufe_astrometry_result(pid, sid)
    assert data and data["run"]["id"] == run_id
    assert data["stacks"] == [path]
    assert {p["source"] for p in data["points"]} == {"stack", "frames"}
    assert all(p["ra"] == pytest.approx(30.0) for p in data["points"])


def test_an_undone_run_is_not_handed_back(window, visit):
    # Undo takes the run back and marks its row "undone": the visit must
    # not resurrect it when it is reopened.
    pid, sid, _path = visit
    run_id = window._ufe_astrometry_persist(pid, sid, _payload())
    window._ufe_astrometry_undo(run_id)
    assert window._ufe_astrometry_result(pid, sid) is None


def test_a_visit_with_no_run_hands_back_nothing(window, visit):
    # A fresh visit (and an ad-hoc open) answer None: the tab then paints
    # an empty column instead of inventing a result.
    _pid, _sid, _path = visit
    assert window._ufe_astrometry_result(None, None) is None
    assert window._ufe_astrometry_result(9999, 9999) is None


def test_the_stack_files_that_vanished_are_not_offered(window, visit):
    # A stack deleted from disk (the observer cleaned up) must not be
    # handed to the tab as if it could be shown.
    pid, sid, path = visit
    window._ufe_astrometry_persist(pid, sid, _payload())
    os.remove(path)
    data = window._ufe_astrometry_result(pid, sid)
    assert data and data["stacks"] == []


def test_the_host_and_the_tab_agree_on_the_saved_run(window, visit, tmp_path,
                                                     qapp):
    # The whole seam in one go: the host writes the run and reads it back, and
    # the TAB (with a real visit context) paints it without stacking anything.
    # The two halves are tested apart; this is what proves they speak the same
    # language (a summary key the tab does not read is a run that reopens
    # empty).
    import numpy as np
    from astropy.io import fits
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    pid, sid, stack_path = visit
    # the visit fixture registers an empty file as the stack: give it pixels,
    # or the restore would (correctly) say the stack cannot be read
    fits.PrimaryHDU(np.zeros((16, 16), dtype=np.float32)).writeto(
        stack_path, overwrite=True)
    frames = []
    for i in range(4):
        p = tmp_path / f"f{i}.fits"
        hdu = fits.PrimaryHDU(np.zeros((32, 32), dtype=np.float32))
        hdu.header["DATE-OBS"] = f"2026-10-06T22:{i * 5:02d}:00"
        hdu.header["EXPTIME"] = 60.0
        hdu.writeto(str(p), overwrite=True)
        frames.append(str(p))
    window._ufe_astrometry_persist(pid, sid, _payload())
    host = QWidget()
    host.astrometry_context = lambda: {"pid": pid, "session_id": sid,
                                       "paths": frames,
                                       "object_name": "2026 PY9"}
    host.export_folder = lambda: str(tmp_path)
    host.astrometry_result = lambda: window._ufe_astrometry_result(pid, sid)
    tab = UfeTrackStackTab(UfeImageState(host), "en", parent=host)
    tab.refresh_context()
    assert tab._result is not None and tab._result.get("restored")
    assert tab._result["box_all"] == (10, 20, 42, 52)
    assert tab._result["ephem_mag"] == pytest.approx(22.21)
    assert tab.tbl_points.rowCount() == 1
    assert tab._result["stacks"][0][0] is not None      # read from the file
    assert tab.btn_undo.isEnabled()
