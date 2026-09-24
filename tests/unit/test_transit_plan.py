############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - transit Plan & Capture block tests (Track D, subplan 2;
# offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen tests for the first-timer transit block in the Plan & Capture
step (docs/PLANS/exoplanet-transit-project.md, subplan 2): the visual
timeline, the five-times strip, the heuristic exposure preselected, the
cadence check with explicit overhead and the persistent pre-flight
checklist.
"""

import datetime
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_MID = datetime.datetime(2026, 8, 22, 0, 20, tzinfo=datetime.timezone.utc)


def _transit_ctx(baseline_fits=True):
    # A transit context as the planner snapshots it (datetimes — the db
    # JSON round-trip turns them into ISO strings, and the block must
    # tolerate both).
    return {"kind": "transit", "ra_deg": 330.0, "dec_deg": 40.5,
            "max_alt": 88.0, "max_time": _MID.isoformat(),
            "transit": {
                "star": "WASP-999", "depth_mmag": 100.0, "duration_h": 2.0,
                "v_mag": 11.5, "priority": "high", "min_telescope_in": 8.0,
                "ingress": _MID - datetime.timedelta(hours=1),
                "mid": _MID,
                "egress": _MID + datetime.timedelta(hours=1),
                "capture_start": _MID - datetime.timedelta(hours=1,
                                                           minutes=30),
                "capture_end": _MID + datetime.timedelta(hours=1,
                                                         minutes=30),
                "baseline_fits": baseline_fits,
                "cadence_max_s": 360,
                "exp_recommended_s": 60}}


# Borrowed from test_projects_hub.py (UD.5): stand-in for the real
# ExploreWorker, so the object card never touches the network (the panel
# never starts its worker in these tests; the payload is just a name).
class FakeWorker:
    def __init__(self, element, deliver=True):
        self._element, self._deliver = element, deliver

    # @return: a QThread that would deliver the element
    def start(self):
        from PySide6.QtCore import QThread
        return QThread()

    def cancel(self):
        pass


FAKE_ELEMENT = {
    "type": "exoplanet",
    "name": "WASP-999 b",
    "data": {},
}


@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # Redirect the shared db singleton to a throwaway file (mirrors
    # tests/unit/test_projects_hub.py).
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("d2db") / "t.db")
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
    # drain the constructor's deferred singleShot (main_window L370:
    # singleShot(0, on_refresh_projects)). If it fires LATER (inside a test's
    # processEvents), the list rebuild finds no current selection and
    # _clear_project_detail() wipes the page the test just built.
    app.processEvents()
    yield w
    config.is_configured = orig_cfg
    w.close()


def _select(window, name, ctx):
    # @return: the created transit project, current and with its page built
    #          (no ExploreWorker; the hub's fake-panel pattern)
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = project.create(mw.db, "transit", name, ctx)
    window._current_project = p
    orig_panel, orig_loader = window._proj_panel, window._proj_panel_loader
    try:
        window._proj_panel = None
        window._proj_panel_loader = (lambda name_, fallback_target=None:
                                     FakeWorker(FAKE_ELEMENT))
        window._build_project_page(p)
    finally:
        window._proj_panel, window._proj_panel_loader = orig_panel, orig_loader
    return p


def test_block_built_with_timeline_times_and_checklist(window):
    _select(window, "WASP-999 b", _transit_ctx())
    w = window._project_widgets
    assert "transit_times" in w
    assert "22:50" in w["transit_times"].text()          # capture_start UTC
    assert "transit_checklist" in w
    assert len(w["transit_checklist"]) == 5
    # the timeline drew bands + milestones
    from nightscribe.gui.widgets.timeline_widget import TransitTimeline
    tl = window.findChild(TransitTimeline)
    assert tl is not None
    assert len(tl._items_registered) > 5


def test_exposure_preselected_from_heuristic(window):
    _select(window, "WASP-998 b", _transit_ctx())
    assert window._project_widgets["spn_exps"].value() == 60.0


def test_cadence_label_and_ingress_warning(window):
    _select(window, "WASP-997 b", _transit_ctx())
    lbl = window._project_widgets["transit_cadence"]
    # 60 s + 15 s pause -> one point every 75 s, well under the 360 s cap
    assert "75" in lbl.text()
    assert "⚠" not in lbl.text()
    # push the exposure past the cadence cap -> the warning shows
    window._project_widgets["spn_exps"].setValue(400.0)
    assert "⚠" in lbl.text()


def test_baseline_warning_only_when_it_overflows(window):
    _select(window, "WASP-996 b", _transit_ctx(baseline_fits=False))
    assert "transit_baseline_warn" in window._project_widgets
    _select(window, "WASP-995 b", _transit_ctx(baseline_fits=True))
    assert "transit_baseline_warn" not in window._project_widgets


def test_checklist_persists_across_rebuild(window):
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = _select(window, "WASP-994 b", _transit_ctx())
    cbs = window._project_widgets["transit_checklist"]
    cbs[0].setChecked(True)
    cbs[2].setChecked(True)
    # persisted into the plan step data
    fresh = project.get(mw.db, p["id"])
    step = next(s for s in fresh["steps"] if s["step"] == "plan")
    assert step["data"]["checklist"] == [True, False, True, False, False]
    # and restored on rebuild (project switch, fake panel as in _select)
    window._current_project = fresh
    orig_panel, orig_loader = window._proj_panel, window._proj_panel_loader
    window._proj_panel = None
    window._proj_panel_loader = (lambda name_, fallback_target=None:
                                 FakeWorker(FAKE_ELEMENT))
    try:
        window._build_project_page(fresh)
    finally:
        window._proj_panel, window._proj_panel_loader = orig_panel, orig_loader
    cbs = window._project_widgets["transit_checklist"]
    assert [cb.isChecked() for cb in cbs] == [True, False, True, False, False]


# ---------------- the timeline widget itself ----------------

def test_timeline_widget_bands_and_labels():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui.widgets.timeline_widget import TransitTimeline
    tl = TransitTimeline()
    dusk = datetime.datetime(2026, 8, 21, 20, 50,
                             tzinfo=datetime.timezone.utc)
    dawn = datetime.datetime(2026, 8, 22, 3, 50,
                             tzinfo=datetime.timezone.utc)
    tl.set_data(dusk=dusk, dawn=dawn,
                capture_start=_MID - datetime.timedelta(hours=1, minutes=30),
                capture_end=_MID + datetime.timedelta(hours=1, minutes=30),
                ingress=_MID - datetime.timedelta(hours=1),
                mid=_MID,
                egress=_MID + datetime.timedelta(hours=1))
    from PySide6.QtWidgets import QGraphicsSimpleTextItem
    texts = [i.text() for i in tl.scene().items()
             if isinstance(i, QGraphicsSimpleTextItem)]
    # the five milestones with their HH:MM labels are all drawn
    joined = "\n".join(texts)
    for hm in ("22:50", "23:20", "00:20", "01:20", "01:50"):
        assert hm in joined, hm
    tl.deleteLater()


def test_timeline_widget_empty_is_safe():
    from nightscribe.gui.widgets.timeline_widget import TransitTimeline
    tl = TransitTimeline()
    tl.set_data()          # nothing given: nothing drawn, no crash
    assert tl._items_registered == []
    tl.set_data(mid=_MID)  # a lone milestone still draws
    assert tl._items_registered
    tl.deleteLater()


# ---------------- EXOTIC handoff (subplan 4d) ----------------

def _fake_enrich():
    # an exoplanet enrich result as the ExploreWorker delivers it
    return {"type": "exoplanet", "name": "WASP-994 b",
            "data": {"pl_name": "WASP-994 b", "hostname": "WASP-994",
                     "ra": 330.0, "dec": 40.5, "pl_orbper": 3.27,
                     "pl_radj": 1.5, "st_rad": 1.2, "pl_orbsmax": 0.05,
                     "pl_tranmid": 2459123.456789, "st_teff": 6100.0}}


def test_exotic_button_in_process_tab(window):
    from PySide6.QtWidgets import QPushButton
    _select(window, "WASP-994 b", _transit_ctx())
    # ADR-041: the process tab is lazy — open it, the user path
    window.projects.btn_tab_analysis.click()
    sec = window._tab_pages["analysis"]
    texts = [b.text() for b in sec.findChildren(QPushButton)]
    assert any("EXOTIC" in t for t in texts)


def test_step_tabs_do_not_grow_window(window):
    # Regression: the transit page must keep its content scrollable inside
    # the hub, so the window itself is not forced off-screen (UD.5).
    _select(window, "WASP-991 b", _transit_ctx())
    assert window.projects.scroll_page is not None
    # and the page container is the scollable widget, not the tabs anymore
    assert window.projects.scroll_page.widget() is window.projects.page_container


def test_transit_timeline_capped(window):
    from nightscribe.gui.widgets.timeline_widget import TransitTimeline
    _select(window, "WASP-990 b", _transit_ctx())
    tl = window.findChild(TransitTimeline)
    assert tl is not None and tl.maximumHeight() == 220
    # the timeline lives inside the plan tab of the project page (ADR-041)
    assert window._tab_pages["plan"].findChild(TransitTimeline) is tl


def test_timeline_fill_fits_the_panel(window):
    # @args: none
    # The old KeepAspectRatio fit letterboxed this chart into a thin strip
    # (~30% of the height at a default 640x480 viewport). The fill fit must
    # cover >=95% of BOTH viewport dimensions, with the labels re-fonted to
    # a sane size (no stretched or microscopic text).
    from PySide6.QtWidgets import QApplication, QGraphicsSimpleTextItem
    app = QApplication.instance()
    from nightscribe.gui.widgets.timeline_widget import TransitTimeline
    _select(window, "WASP-989 b", _transit_ctx())
    tl = window.findChild(TransitTimeline)
    assert tl is not None
    tl.resize(900, 220)          # as capped in the Plan tab
    app.processEvents()
    tl.fit_to_scene()
    vp = tl.viewport()
    assert vp.width() > 100 and vp.height() > 50
    m0 = tl.mapFromScene(tl.sceneRect().topLeft())
    m1 = tl.mapFromScene(tl.sceneRect().bottomRight())
    assert abs(m1.x() - m0.x()) >= 0.95 * vp.width()
    assert abs(m1.y() - m0.y()) >= 0.95 * vp.height()
    for it in tl.scene().items():
        if isinstance(it, QGraphicsSimpleTextItem):
            assert 6 <= it.font().pixelSize() <= 30


def test_timeline_uses_transit_night_not_next_night(window):
    # @args: none
    # A transit that straddles local midnight has `mid` on the NEXT calendar
    # day; the block must still pick the PRIOR evening's night so the capture
    # and the darkness share one axis. Regression for the HAT-P-53b
    # "bunched-left" PNG (capture fill 53% vs 14%; axis 480 vs 1770 min).
    _select(window, "HAT-P-53b", _transit_ctx())
    kw = window._project_widgets["transit_timeline"]["kw"]
    dusk, dawn, cs, ce = (kw["dusk"], kw["dawn"],
                          kw["capture_start"], kw["capture_end"])
    assert all(isinstance(x, datetime.datetime)
               for x in (dusk, dawn, cs, ce))
    # night (dusk->dawn ~8h) + baselines: one calendar night, far less than
    # the ~30h the buggy next-night window produced
    span_h = (max(dawn, ce) - min(dusk, cs)).total_seconds() / 3600.0
    assert span_h < 14.0, (
        f"night+capture span {span_h:.1f}h is not the transit's own night")
    # and the darkness must bracket the transit itself
    assert dusk <= cs and dawn >= ce, "transit not bracketed by the night"


def test_timeline_click_opens_shared_viewer(window, monkeypatch):
    # @args: none
    # A plain click on the embedded timeline must open the same
    # ChartViewer used elsewhere, around a FRESH widget (the one in the
    # Plan tab must not be reparented out of its page).
    from PySide6.QtCore import QPointF
    from nightscribe.gui import chart_viewer
    from nightscribe.gui.widgets.timeline_widget import TransitTimeline
    _select(window, "WASP-988 b", _transit_ctx())
    calls = []
    def fake_open(parent, widget, title="", obj_name="", chart_key=""):
        calls.append(dict(parent=parent, widget=widget, title=title,
                          obj=obj_name, key=chart_key))
    monkeypatch.setattr(chart_viewer, "open_chart_widget", fake_open)
    tl = window.findChild(TransitTimeline)
    home = tl.parentWidget()
    tl.scene_clicked.emit(QPointF(10.0, 1.0))
    assert len(calls) == 1
    c = calls[0]
    assert c["parent"] is window
    assert c["widget"] is not tl and type(c["widget"]) is TransitTimeline
    assert tl.parentWidget() is home                # still in its tab
    assert "Transit capture plan" in c["title"]
    assert c["obj"] == "WASP-988 b"
    assert c["key"] == "transit_plan"
    assert c["widget"]._items_registered            # the fresh copy drew
    w = window._project_widgets["transit_timeline"]
    assert w["kw"] and w["obj"] == "WASP-988 b"
    c["widget"].deleteLater()


def test_viewer_falls_back_to_bare_chartview():
    # @args: none
    # A bare ChartView widget (the timeline) has no .view attribute; the
    # viewer must treat the widget itself as the interactive canvas, so
    # Fit and the zoom steps keep working.
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from nightscribe.gui.chart_viewer import ChartViewer
    from nightscribe.gui.widgets.timeline_widget import TransitTimeline
    tl = TransitTimeline()
    tl.set_data(
        dusk=datetime.datetime(2026, 8, 21, 20, 50,
                               tzinfo=datetime.timezone.utc),
        dawn=datetime.datetime(2026, 8, 22, 3, 50,
                               tzinfo=datetime.timezone.utc),
        capture_start=_MID - datetime.timedelta(hours=1, minutes=30),
        capture_end=_MID + datetime.timedelta(hours=1, minutes=30),
        ingress=_MID - datetime.timedelta(hours=1), mid=_MID,
        egress=_MID + datetime.timedelta(hours=1))
    dlg = ChartViewer(widget=tl, title="Transit capture plan",
                      obj_name="WASP-987 b", chart_key="transit_plan")
    assert dlg._view is tl
    dlg._zoom_fit()
    dlg._zoom_in()
    dlg._zoom_out()
    dlg.close()
    dlg.deleteLater()


def test_standalone_timeline_keeps_proportions():
    # @args: none
    # The window (the ChartViewer's fresh widget) shows the timeline with
    # set_embedded left off, inside a TALL frame. The old un-conditional fill
    # fit stretched it several times taller than wide (bloated bands: "lo
    # estás ajustando y no se ve bien"). A standalone timeline must instead use
    # the base's uniform KeepAspectRatio fit, so it keeps its natural
    # wide-short proportions: the on-screen frame must have the same aspect as
    # the scene. (test_timeline_fill_fits_the_panel pins the OPPOSITE for the
    # embedded panel, where fill is the right call.)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui.widgets.timeline_widget import TransitTimeline
    tl = TransitTimeline()            # standalone: the window never embeds it
    assert tl._embedded is False
    tl.set_data(
        dusk=datetime.datetime(2026, 8, 21, 20, 50,
                               tzinfo=datetime.timezone.utc),
        dawn=datetime.datetime(2026, 8, 22, 3, 50,
                               tzinfo=datetime.timezone.utc),
        capture_start=_MID - datetime.timedelta(hours=1, minutes=30),
        capture_end=_MID + datetime.timedelta(hours=1, minutes=30),
        ingress=_MID - datetime.timedelta(hours=1), mid=_MID,
        egress=_MID + datetime.timedelta(hours=1))
    tl.resize(1000, 740)              # the tall ChartViewer frame
    app.processEvents()
    tl.fit_to_scene()
    vp = tl.viewport()
    assert vp.width() > 100 and vp.height() > 200
    scene = tl.sceneRect()
    m = tl.mapFromScene
    tl_ = m(scene.topLeft())
    tr_ = m(scene.topRight())
    bl_ = m(scene.bottomLeft())
    mapped_w = abs(tr_.x() - tl_.x())          # top edge: top-left .. top-right
    mapped_h = abs(bl_.y() - tl_.y())          # left edge: top-left .. bottom-left
    scene_aspect = scene.width() / scene.height()
    # a wide-short, UNDISTORTED chart: its screen frame keeps the scene's
    # aspect (the old fill fit would have squashed it to ~sx:sy of the width)
    assert scene_aspect > 1.0
    assert abs(mapped_w / mapped_h - scene_aspect) <= 0.05 * scene_aspect


def test_exotic_write_registers_the_file(window, monkeypatch, tmp_path):
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = _select(window, "WASP-993 b", _transit_ctx())
    out = tmp_path / "inits_test.json"
    from PySide6.QtWidgets import QFileDialog
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    window._exotic_write(p["id"], _fake_enrich())
    assert out.exists()
    import json
    data = json.loads(out.read_text(encoding="utf-8"))
    # the name comes from the Archive row of the enrich, not the project
    assert data["planetary_parameters"]["Planet Name"] == "WASP-994 b"
    files = [f for f in project.list_files(mw.db, p["id"])
             if f["kind"] == "exotic_inits"]
    assert len(files) == 1


def test_exotic_write_without_data_warns_and_stops(window, tmp_path):
    import nightscribe.gui.main_window as mw
    from nightscribe.core import project
    p = _select(window, "WASP-992 b", _transit_ctx())
    window._exotic_write(p["id"], {})   # enrich failed -> no file, no crash
    files = [f for f in project.list_files(mw.db, p["id"])
             if f["kind"] == "exotic_inits"]
    assert files == []
