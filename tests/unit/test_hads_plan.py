############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - HADS capture-plan block tests (ADR-034, subplan D.1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen tests for the HADS plan block: the 2-period session summary,
the safe window with the cycles count, the heuristic exposure preselected,
the cadence check (P/12, 15-min cap) and the persistent checklist. Mirrors
tests/unit/test_transit_plan.py.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _hads_ctx(session_fits=True):
    # A HADS context as the planner snapshots it (ISO strings survive the
    # db JSON round-trip; the block must tolerate both)
    return {"kind": "hads", "ra_deg": 339.4, "dec_deg": 1.53,
            "mag": 11.65, "max_alt": 48.0, "max_time": "2026-09-12T01:12:00",
            "window_start": "2026-09-11T22:00:00",
            "window_end": "2026-09-12T04:30:00",
            "safe_window": "2026-09-11T23:00:00|2026-09-12T03:56:00",
            "best_time": "2026-09-12T00:28:00",
            "latest_safe_start": "2026-09-12T01:04:00",
            "hours_up": 6.5,
            "hads": {"period_h": 1.46, "max": 11.3, "min": 11.8, "amp": 0.5,
                     "cycles": 4.5, "cadence_s": 438.0, "session_req_h": 2.92,
                     "session_fits": session_fits, "exp_s": 60,
                     "priority": None, "observed": True,
                     "multiperiodic": False, "non_radial": False,
                     "covered_this_month": True}}


@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # Redirect the shared db singleton to a throwaway file
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("hadsdb") / "t.db")
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
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


def _select(window, name, ctx):
    # @return: the created hads project, current and with tabs built
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = project.create(mw.db, "hads", name, ctx)
    window._current_project = p
    window._build_step_tabs(p)
    return p


def test_block_built_with_summary_window_and_checklist(window):
    _select(window, "CY Aqr", _hads_ctx())
    w = window._project_widgets
    assert "2.9" in w["hads_summary"].text()          # 2P = 2.92 h
    assert "1.46" in w["hads_summary"].text()
    assert "00:28" in w["hads_window"].text()         # best_time UTC
    assert "4.5" in w["hads_window"].text()           # cycles tonight
    assert "01:04" in w["hads_window"].text()         # latest safe start
    assert len(w["hads_checklist"]) == 5


def test_exposure_preselected_from_heuristic(window):
    _select(window, "DY Peg", _hads_ctx())
    assert window._project_widgets["spn_exps"].value() == 60.0


def test_frames_default_covers_two_periods(window):
    # 2.92 h session at 60 s + 15 s overhead -> 140 frames (ADR-034, D.2)
    _select(window, "V1051 Ara", _hads_ctx())
    assert window._project_widgets["spn_nframes"].value() == 140


def test_cadence_label_and_warning(window):
    _select(window, "SZ Lyn", _hads_ctx())
    lbl = window._project_widgets["hads_cadence"]
    # 60 s + 15 s pause -> one point every 75 s, well under the 438 s cap
    assert "75" in lbl.text() and "438" in lbl.text()
    assert "⚠" not in lbl.text()
    window._project_widgets["spn_exps"].setValue(500.0)
    assert "⚠" in lbl.text()


def test_session_fits_warning_only_when_2p_overflows(window):
    _select(window, "XX Cyg", _hads_ctx(session_fits=False))
    assert "hads_fits_warn" in window._project_widgets
    _select(window, "V2455 Cyg", _hads_ctx(session_fits=True))
    assert "hads_fits_warn" not in window._project_widgets


def test_checklist_persists_across_rebuild(window):
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = _select(window, "AD CMi", _hads_ctx())
    cbs = window._project_widgets["hads_checklist"]
    cbs[0].setChecked(True)
    cbs[3].setChecked(True)
    p2 = project.get(mw.db, p["id"])
    window._current_project = p2
    window._build_step_tabs(p2)
    cbs2 = window._project_widgets["hads_checklist"]
    assert cbs2[0].isChecked() and cbs2[3].isChecked()
    assert not cbs2[1].isChecked()


# ---------------- follow-up + process (subplan D.3) ----------------

def _tab(window, name):
    from PySide6.QtWidgets import QWidget
    return window.projects.tabs_steps.findChild(QWidget, name)


def test_followup_tab_visible_for_hads(window):
    _select(window, "T UMa", _hads_ctx())
    tab = _tab(window, "tab_followup")
    idx = window.projects.tabs_steps.indexOf(tab)
    assert window.projects.tabs_steps.isTabVisible(idx)


def test_followup_hides_sn_analysis_buttons_for_hads(window):
    from PySide6.QtWidgets import QPushButton
    _select(window, "V0392 UMa", _hads_ctx())
    buttons = {b.text(): b for b in _tab(window, "tab_followup")
               .findChildren(QPushButton)}
    assert buttons["Run quick-look"].isHidden()
    assert buttons["Generate animation"].isHidden()
    assert buttons["Export annotated FITS"].isHidden()
    assert not buttons["Add visit"].isHidden()
    assert not buttons["Import file…"].isHidden()


def test_process_tab_fotodif_webobs_block(window):
    from PySide6.QtWidgets import QPushButton
    _select(window, "DY Her", _hads_ctx())
    buttons = [b.text() for b in _tab(window, "tab_process")
               .findChildren(QPushButton)]
    assert any("WebObs" in t for t in buttons)


def test_fotodif_output_imports_into_the_project(window):
    # FotoDif hands over «JD mag err» text — the tolerant parser (B3) reads
    # it unchanged and the points land on the hads project
    import nightscribe.gui.main_window as mw
    from nightscribe.core import followup, photometry_import
    p = _select(window, "V1116 Her", _hads_ctx())
    text = "2459653.44800 11.42 0.02\n2459653.45500 11.45 0.02\n"
    pts, skipped = photometry_import.parse_photometry(text)
    assert not skipped and len(pts) == 2
    for pt in pts:
        followup.add_point(mw.db, p["id"], pt["mjd"], pt["filter"],
                           pt["mag"], pt.get("err"), source="file")
    assert len(followup.list_points(mw.db, p["id"])) == 2
