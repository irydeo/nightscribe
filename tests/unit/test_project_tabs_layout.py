############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the project tab layout (Interfaz 1.7/1.8)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Object card and the Analysis tabs, measured (the layout side:
`test_project_tabs.py` covers the tab bar's behaviour).

The acceptance criterion of Interfaz 1.7/1.8 is written down here as a
test: no WORKING tab may need a vertical scroll at 1360x940 (the usual
desktop) nor at 1360x860 (a laptop), with a project that has a visit, its
frames and a measured curve. ADR-057 carved the Object card out of that
contract: it is a vertical dossier now (hero, KPI strip, section cards)
and may scroll; Capture, Analysis and Publish keep the no-scroll rule.

Interfaz 1.8 added the hardest case of all: the Capture tab **with CCDciel
connected**, which is when the observatory status appears and used to land
161 px below the fold.

Offscreen, no network.
"""

import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture()
def window(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from nightscribe.config import config
    from nightscribe.core import db as coredb, followup, project
    from nightscribe.gui import main_window as mwmod
    from nightscribe.gui import theme
    from nightscribe.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    tmp = tempfile.mkdtemp()
    throwaway = coredb.Database(str(Path(tmp) / "t.db"))
    monkeypatch.setattr(coredb, "db", throwaway)
    monkeypatch.setattr(mwmod, "db", throwaway)
    config.is_configured = lambda: True
    config.set("app_version", "9.9.9")
    config.set("lat", 40.55)
    config.set("lon", -3.37)
    p = project.create(throwaway, "sn", "2026abc", {
        "ra_deg": 187.7, "dec_deg": 21.0, "mag": 15.2, "sn_type": "Ia",
        "host": "NGC 4414", "otype": "SN Ia", "discovered": "2026-09-28",
        "id": "2026abc"})
    sid = followup.create_session(throwaway, p["id"], notes="clear night")
    for i in range(12):
        # with a real DATE-OBS: the Analysis band draws the visit's frames
        # on the night they were shot, and that is worth a test
        followup.add_image(throwaway, sid, "V",
                           "/tmp/frames/2026abc-%03d.fits" % i,
                           date_obs="2026-10-02T21:%02d:00" % i)
        followup.add_point(throwaway, p["id"], 61000.0 + i * 0.08, "V",
                           15.0 + 0.12 * ((i % 4) - 1.5), err=0.03,
                           session_id=sid)
    project.add_file(throwaway, p["id"], "/tmp/frames/2026abc-000.fits",
                     "fits", session_id=sid)
    w = MainWindow(snapshot=None)
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    w._project_id = p["id"]
    # SHOWN: the acceptance criterion is about real geometry, and a hidden
    # window has none (the scroll viewport measured 30 px)
    w.resize(1360, 940)
    w.show()
    for _ in range(6):
        app.processEvents()
    yield w
    w.close()


class _FakeWorker:
    """The enriched payload the object card renders, delivered at once."""

    def __init__(self, payload):
        self.payload = payload
        self._cbs = []

    class _fin:
        def __init__(self, w):
            self._w = w

        def connect(self, cb):
            self._w._cbs.append(cb)

        def disconnect(self, cb=None):
            self._w._cbs = []

        def emit(self, p):
            for cb in list(self._w._cbs):
                cb(p)

    @property
    def finished(self):
        return self._fin(self)

    def start(self):
        self._fin(self).emit(self.payload)


SN_PAYLOAD = {
    "type": "transient", "name": "2026abc",
    "data": {"host": {"name": "NGC 4414", "dist_mly": 62.0},
             "dist_mly": 62.0, "otype": "SN Ia", "disc_date": "2026-09-28",
             "mag_now": 15.2, "simbad": {"ids": ["SN 2026abc"]},
             "images": [], "followup": {"points": []},
             "ephem_epoch": "J2000"},
    "ephem": {"ra": "12 28 34.56", "dec": "+31 13 22.1", "r": 1.0,
              "delta": 0.0}}


def _open(window, tab):
    from nightscribe.gui.main_window import VIEW_DETAIL
    window.navigate(VIEW_DETAIL, pid=window._project_id, tab=tab)
    from PySide6.QtWidgets import QApplication
    for _ in range(6):
        QApplication.processEvents()
    # the object card asks the network for the object; offline, the panel
    # would stay on "Loading…" and the test would measure that instead of
    # the card a reader actually gets
    panel = window._get_proj_panel()
    panel.cancel()
    panel._loader = lambda name, fallback_target=None: _FakeWorker(SN_PAYLOAD)
    panel.explore("2026abc", ctx={"kind": "sn", "mag": 15.2,
                                  "sn_type": "Ia", "host": "NGC 4414"})
    for _ in range(8):
        QApplication.processEvents()


def test_neither_tab_scrolls(window):
    # ADR-057: the Object card ("details") is a vertical dossier now and
    # MAY scroll (its sections breathe); the no-scroll contract stays for
    # the working tabs (Capture, Analysis, Publish).
    from PySide6.QtWidgets import QApplication
    for size in ((1360, 940), (1360, 860)):
        window.resize(*size)
        for _ in range(8):
            QApplication.processEvents()
        for tab in ("analysis",):
            _open(window, tab)
            page = window.projects.page_container
            viewport = window.projects.scroll_page.viewport().height()
            assert page.sizeHint().height() <= viewport, (
                f"the {tab} tab asks for {page.sizeHint().height()} px "
                f"in a {viewport} px viewport at {size}")


def test_the_analysis_band_draws_the_visit_frames(window):
    # Interfaz 1.8: the band above the visits is the night the selected
    # visit happened in, with its frames as one block on the timeline.
    _open(window, "analysis")
    ribbon = window._project_widgets["analysis_ribbon"]
    assert ribbon.has_night()
    assert len(ribbon._blocks) == 1
    block = ribbon._blocks[0]
    assert block["end"] > block["start"]
    assert "12" in block["label"]          # twelve frames, one block
    # and the frame times really came from the headers
    assert "min" in ribbon._note


def test_capture_fits_with_ccdciel_connected(window):
    # The observatory status only appears once CCDciel answers, and it used
    # to land 161 px BELOW the fold: the observer connected and saw nothing
    # new. Now the block is a colour and a row, and the page still fits.
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme

    class _Client:
        host = "127.0.0.1"
        port = 3277

    _open(window, "capture")
    window._ccd_client = _Client()
    window._ccd_on_connect({"version": "1.0", "filters": ["L"],
                            "dashboard": {"camera": {"temperature": -10.0,
                                                     "tracking": True},
                                          "mount": {"slewing": False}}},
                           None)
    window._ccd_timer.stop()
    for _ in range(8):
        QApplication.processEvents()
    assert window._ccd_state_grp.isVisible()
    widgets = window._ccd_widgets()
    assert theme.C_GOOD in widgets["ccd_status"].styleSheet()
    assert theme.C_GOOD in widgets["ccd_tracking"].styleSheet()
    page = window.projects.page_container
    viewport = window.projects.scroll_page.viewport().height()
    assert page.sizeHint().height() <= viewport, (
        f"with CCDciel connected the Capture tab asks for "
        f"{page.sizeHint().height()} px in {viewport}")


def test_capture_summary_strip_reads_the_plan(window):
    # ADR-059: the Capture console opens with a summary strip (integration,
    # filter, dawn verdict) and its blocks live in titled PanelCards.
    from nightscribe.gui.widgets.kpi_tile import KpiTile
    from nightscribe.gui.widgets.section_card import PanelCard
    _open(window, "capture")
    page = window.projects.page_container
    tiles = {t.texts()[1]: t
             for t in page.findChildren(KpiTile)}
    assert {"Integration", "Filter", "Before dawn"} <= set(tiles), tiles
    # the default plan is 30 × 60 s: the strip must say so (not "—")
    assert tiles["Integration"].texts()[0].endswith(("min", "h")), \
        tiles["Integration"].texts()
    assert tiles["Before dawn"].texts()[0] in ("fits", "does not fit", "—")
    titles = [c.lbl_title.text() for c in page.findChildren(PanelCard)]
    assert any("Exposure plan" in t for t in titles), titles
    assert any("Telescope and camera" in t for t in titles), titles


def test_the_project_chrome_is_three_rows(window):
    # the four small buttons and the context line live in the masthead row
    # now, and the "next" band is a plain frame (no group title)
    from nightscribe.gui.main_window import VIEW_DETAIL
    window.navigate(VIEW_DETAIL, pid=window._project_id)
    mast = window.projects.masthead
    for name in ("btn_home", "btn_favorite", "btn_manage", "lbl_context"):
        child = getattr(window.projects, name)
        assert mast.isAncestorOf(child), f"{name} is not in the masthead"
    assert window.projects.nextBand is not None
    assert not hasattr(window.projects, "grp_next")


def test_a_page_does_not_repeat_its_tab_name(window):
    # Interfaz 1.7: the active tab says which page you are on; a bold title
    # above the content was 25 px spent saying it twice
    from PySide6.QtWidgets import QLabel
    from nightscribe.gui.main_window import VIEW_DETAIL
    window.navigate(VIEW_DETAIL, pid=window._project_id, tab="details")
    page = window.projects.page_container.findChildren(object)
    titles = [w for w in window.projects.page_container.findChildren(QLabel)
              if w.text() == window._tab_label("details")]
    assert not titles, "the page still repeats the tab's name"
    assert page is not None


def test_the_analysis_tab_is_visits_beside_curve(window):
    from nightscribe.gui.main_window import VIEW_DETAIL
    _open(window, "analysis")
    panel = window._project_widgets["visits_panel"]
    chart = window._project_widgets["fu_curve"]
    group = chart.parentWidget()          # the curve's block
    # same row: the visits (with their night band above them) on the left,
    # the curve on the right, and the two share a parent
    left = panel.parentWidget()
    assert left is not group
    assert left.parentWidget() is group.parentWidget()
    assert left.x() < group.x()
    assert left.width() < group.width()   # the chart takes the rest
    # and the band sits ABOVE the visits, inside that left column
    ribbon = window._project_widgets["analysis_ribbon"]
    assert ribbon.parentWidget() is left
    assert ribbon.y() < panel.y()


def test_a_chart_asks_for_a_sane_size(window):
    # a QGraphicsView with no sizeHint of its own answers with the SCENE's,
    # which is whatever the data spans (a light curve asked for 520 px)
    from nightscribe.gui.widgets.base_chart import ChartView
    from nightscribe.gui.widgets.lightcurve_widget import LightCurveChart
    hint = LightCurveChart().sizeHint()
    assert hint.height() == ChartView.PREFERRED_H
    assert hint.height() <= 300


def test_the_params_block_carries_its_own_switch(window):
    from nightscribe.gui.main_window import VIEW_DETAIL
    window.navigate(VIEW_DETAIL, pid=window._project_id, tab="details")
    ui = window._get_proj_panel()._ui
    # the "In depth" switch shares the header row with the title
    assert ui.row_deep.indexOf(ui.chk_deep) >= 0
    assert ui.row_deep.indexOf(ui.lbl_params_title) >= 0


def test_one_visit_is_one_visit(window):
    from nightscribe.core import db as coredb
    from nightscribe.gui.main_window import VIEW_DETAIL
    _open(window, "analysis")
    panel = window._project_widgets["visits_panel"]
    panel.set_project(window._project_id)
    assert panel.lbl_count.text() == "1 visit"
    from nightscribe.core import followup
    followup.create_session(coredb.db, window._project_id)
    panel.set_project(window._project_id)
    assert panel.lbl_count.text() == "2 visits"
