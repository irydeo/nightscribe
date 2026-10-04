############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Object overview panel tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen smoke tests for ObjectPanel, phase D1 (docs/WORKFLOWS.es.md).

Build the panel directly (no MainWindow), drive it with fake enriched
payloads and a fake loader: no network, no project hub. Same spirit as
test_tonight_table.py: QApplication + theme + panel + fake payloads.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QLabel  # noqa: E402

from nightscribe.core import narrative  # noqa: E402

# A small body with a full story: family, size, distances, MOID, a
# preliminary-orbit σ block and an unconfirmed sibling (not used here).
FAKE_ELEMENT = {
    "type": "small_body",
    "name": "2026 QK (443089)",
    "data": {
        "family": "Apollo",
        "sbdb": {
            "fullname": "2026 QK (443089) — example asteroid",
            "elements": {"a": 1.350, "e": 0.400, "i": 6.2,
                         "q": 0.810, "Q": 1.890, "n": None, "per": 560.0},
            "phys": {"H": 20.5, "diameter": 1.1, "spec_B": "S-type",
                     "albedo": 0.18, "rot_per": 12.3},
            "moid": 0.028,
            "sigmas": {"a": 0.0012, "e": 0.008, "i": 0.4},
            "n_resids": 21,
            "arc_days": 14,
            "disc_date": "2026-08-19",
        },
        # same "h m s" / "+d m s" shape enrich.py emits via
        # coords.ra_deg_to_hms / dec_deg_to_dms (what build_charts parses)
        "ephem": {"ra": "12 00 00.000", "dec": "+30 00 00.000",
                  "r": 1.3, "delta": 0.5},
        "mag_now": 19.8,
        "dist_now_km": 74_800_000,
        "next_approach": {"date": "2026-11-04", "dist_ld": 12.4,
                          "v_rel": 11.0},
    },
}

# An unconfirmed PCCP-style candidate: no sbdb at all, NEOfixer facts only.
FAKE_UNCONFIRMED = {
    "type": "neo",
    "name": "PDC11321",
    "data": {
        "unconfirmed": {
            "id": "PDC11321", "name": "PDC11321", "kind": "pccp",
            "nf_score": 8.0, "nf_priority": "A", "nobs": 6,
            "nf_cost_min": 15, "arc_days": 3, "moid": 0.045,
            "pccp_score": 78.0, "mag": 20.2,
        }
    },
}


@pytest.fixture(scope="module")
def qapp():
    if os.environ.get("QT_QPA_PLATFORM") is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    existing = QApplication.instance()
    if existing is not None:
        return existing
    app = QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture()
def panel(qapp, tmp_path):
    # chart_dir points at a throwaway dir: the tests write real PNGs
    # for the pure matplotlib slots (orbit, sky) without touching the
    # user's posts folder.
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(chart_dir=tmp_path / "charts")
    yield p
    p.deleteLater()


def _texts(panel):
    # @return: everything the user can read, one string
    return "\n".join(t for t in (
        panel.lbl_state.text(), panel.lbl_hook.text(),
        panel.lbl_facts.text()) if t)


def _param_cells(panel):
    # @return: the (param, value, meaning) strings of every visible row.
    #   ADR-057: the rows live in themed section cards now (definition
    #   lists), not in the old two-column table; the cards keep the
    #   (param, value, meaning) triples in rows_text.
    out = []
    for card in panel._section_cards:
        out.extend(card.rows_text)
    return out


def _tile_texts(panel):
    # @return: the "value|caption" strings of the KPI strip's tiles
    #   (ADR-057: the numbers of the old capture-chips row live here)
    from nightscribe.gui.widgets.kpi_tile import KpiTile
    return ["|".join(t.texts())
            for t in panel.kpi_strip.findChildren(KpiTile)]


# ---------------- states ----------------

def test_starts_empty(panel):
    assert panel.state() == "empty"
    assert panel.lbl_state.isHidden()
    assert panel.lbl_hook.isHidden()
    assert panel.grp_params.isHidden()


def test_ready_state_hook_and_params_visible(panel, qapp):
    panel.show(FAKE_ELEMENT)
    assert panel.state() == "ready"
    assert panel.lbl_state.isHidden()
    assert not panel.lbl_hook.isHidden()
    hook = panel.lbl_hook.text()
    # the hook is the narrative hook in the active language, verbatim
    assert hook in (narrative.hook(FAKE_ELEMENT)["es"],
                    narrative.hook(FAKE_ELEMENT)["en"]), \
        f"hook is not the narrative hook: {hook!r}"


def test_the_band_spans_the_page(panel, qapp):
    # ADR-057: the band always spans the page, between the coordinates row
    # and the parameters/charts row (it is not inside either column).
    panel.show(FAKE_ELEMENT)
    qapp.processEvents()
    ribbon = panel._ribbon
    vbox = panel.layout()
    assert vbox.indexOf(ribbon) >= 0
    assert vbox.indexOf(ribbon) > vbox.indexOf(panel.row_coords)
    assert vbox.indexOf(ribbon) < vbox.indexOf(panel._ui.row_body)
    # and it carries the night's numbers as its tooltip, because the
    # caption is elided in a narrow column
    assert "19:30" in ribbon.toolTip() or "observatory" in ribbon.toolTip()


def test_parameters_and_charts_share_the_row(panel, qapp):
    # ADR-057 rev.: one row, parameters left and charts right. The columns
    # are widgets so that hiding one hands the width to the other.
    panel.show(FAKE_ELEMENT)
    qapp.processEvents()
    row = panel._row_body
    assert row.indexOf(panel.col_params) == 0
    assert row.indexOf(panel.col_charts) == 1
    assert row.stretch(0) == row.stretch(1) == 1        # 50/50
    # the blocks live inside their column, not loose in the dossier
    assert panel._ui.colParamsLay.indexOf(panel.grp_params) >= 0
    assert panel._ui.colParamsLay.indexOf(panel._ui.sectionsHost) >= 0
    assert panel._ui.colChartsLay.indexOf(panel.grp_charts) >= 0
    assert panel.layout().indexOf(panel.grp_charts) < 0


def test_a_column_without_its_block_gives_the_width_to_the_other(panel, qapp):
    # A hidden block inside a VISIBLE column would leave the column
    # standing and squeeze the other one for nothing: the column follows.
    panel.show(FAKE_ELEMENT)
    qapp.processEvents()
    panel.grp_charts.hide()
    panel._sync_body_columns()
    assert panel.col_charts.isHidden()
    assert not panel.col_params.isHidden()
    panel.grp_params.hide()
    panel._sync_body_columns()
    assert panel.col_params.isHidden()
    # and the dossier is never left with an empty row
    assert panel.col_params.isHidden() and panel.col_charts.isHidden()


def test_the_row_stacks_in_a_narrow_pane(panel, qapp):
    # Below _BODY_STACK_W two 390 px columns do not fit and the charts
    # (300 px floor) would clip instead of shrinking.
    from PySide6.QtWidgets import QBoxLayout, QWidget
    from nightscribe.gui.overview import _BODY_STACK_W
    QWidget.show(panel)     # ObjectPanel.show(e) shadows QWidget.show()
    qapp.processEvents()
    panel.resize(_BODY_STACK_W + 200, 900)
    qapp.processEvents()
    assert panel._row_body.direction() == QBoxLayout.LeftToRight
    panel.resize(_BODY_STACK_W - 100, 900)
    qapp.processEvents()
    assert panel._row_body.direction() == QBoxLayout.TopToBottom
    panel.resize(_BODY_STACK_W + 200, 900)
    qapp.processEvents()
    assert panel._row_body.direction() == QBoxLayout.LeftToRight


def test_ready_params_table_has_meaningful_rows(panel):
    panel.show(FAKE_ELEMENT)
    assert not panel.grp_params.isHidden()
    # Interfaz 1.8: "in depth" is ON by default (the observer asked for it),
    # so this test reads the basic view by turning it OFF
    assert panel.chk_deep.isChecked()
    panel.chk_deep.setChecked(False)
    rows = _param_cells(panel)
    assert len(rows) >= 3, f"expected a few rows, got {len(rows)}"
    meaning = [r[2] for r in rows]
    # the explanation is a real sentence, not an empty cell
    assert all(len(m) > 40 for m in meaning), \
        f"explanation too short: {meaning!r}"
    # the basic rows only, in-depth off
    params = [r[0].lower() for r in rows]
    assert any("family" in p or "familia" in p for p in params)
    assert any("moid" in p for p in params)
    assert not any("semi-major" in p or "semieje" in p for p in params), \
        "deep rows leaked into the basic view"


def test_in_depth_toggle_adds_deep_rows(panel):
    panel.show(FAKE_ELEMENT)
    panel.chk_deep.setChecked(False)
    before = len(_param_cells(panel))
    panel.chk_deep.setChecked(True)
    after = len(_param_cells(panel))
    assert after > before, "checking «in depth» did not add rows"
    params = [r[0].lower() for r in _param_cells(panel)]
    assert any("semi-major" in p or "semieje" in p for p in params), \
        f"deep row missing after toggle: {params}"
    # and un-checking goes back
    panel.chk_deep.setChecked(False)
    assert len(_param_cells(panel)) == before


def test_unconfirmed_object_shows_neofixer_rows(panel):
    panel.show(FAKE_UNCONFIRMED)
    assert panel.state() == "ready"
    rows = _param_cells(panel)
    params = [r[0].lower() for r in rows]
    assert any("neofixer" in p for p in params), \
        f"unconfirmed rows missing NEOfixer: {params}"
    # the NEOfixer score row explains *why the community needs you*
    assert any("comunidad" in r[2].lower() or "community" in r[2].lower()
               for r in rows), "missing the NEOfixer score explanation"


def test_empty_payload_is_the_not_found_state(panel, qapp):
    panel.show({})
    assert panel.state() == "missing"
    assert not panel.lbl_state.isHidden()
    text = panel.lbl_state.text()
    assert "not found" in text.lower() or "no encontrado" in text.lower(), \
        f"missing state unclear: {text!r}"
    assert panel.lbl_hook.isHidden()
    assert panel.grp_params.isHidden()


def test_show_with_context_keeps_it(panel):
    ctx = {"kind": "neo", "mag": 19.5,
           "window_start": "2026-08-26T21:00:00+02:00"}
    panel.show(FAKE_ELEMENT, ctx)
    assert panel.state() == "ready"
    assert panel._ctx == ctx


# ---------------- loader (offscreen, no network) ----------------

class _Signal:
    # The minimal finished signal: connect() then deliver on start().
    def __init__(self):
        self._c = []

    def connect(self, cb):
        self._c.append(cb)

    def disconnect(self, cb=None):
        # the real signal has it; the panel detaches its slot on cancel/done
        if cb is None:
            self._c = []
        elif cb in self._c:
            self._c.remove(cb)

    def deliver(self, payload):
        for cb in self._c:
            cb(payload)


class FakeWorker:
    """A stand-in for ExploreWorker: start() lands the payload at once."""

    def __init__(self, payload):
        self.payload = payload
        self.finished = _Signal()

    def start(self):
        self.finished.deliver(self.payload)


def test_explore_loading_then_ready(panel, qapp):
    captured = {}

    def loader(name, fallback_target=None):
        # records what the hub would ask for and answers off the bat
        captured["name"] = name
        captured["fallback"] = fallback_target
        return FakeWorker(FAKE_ELEMENT)

    p = None
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(loader=loader)
    assert p.state() == "empty"
    p.explore("2026 QK (443089)", fallback_target={"id": "neo1"})
    assert p.state() == "ready"
    assert captured["name"] == "2026 QK (443089)"
    assert captured["fallback"] == {"id": "neo1"}
    p.deleteLater()


def test_explore_not_found_state(panel, qapp):
    def loader(name, fallback_target=None):
        return FakeWorker({})

    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(loader=loader)
    p.explore("SN1987AAA")
    assert p.state() == "missing"
    assert "SN1987AAA" in p.lbl_state.text(), \
        f"not-found state should name the object: {p.lbl_state.text()!r}"
    p.deleteLater()


# ---------------- D2: chart tabs (ADR-029 vector slots) ----------------
#
# orbit / sky are live vector widgets (OrbitChart / SkyChart, ADR-029);
# field / transit are QLabel+QPixmap. build_charts is still run and acts
# as a "can I make this chart?" gate. Each produced chart lands on its own
# tab, labelled with its title. We inspect the tabs by counting children
# and checking _slot_data for the vector ones.

def _chart_tabs(panel):
    """@return: the widgets in the chart tab group, in tab order."""
    return [panel._tabs.widget(i) for i in range(panel._tabs.count())]


def test_charts_tabs_present_when_ready(panel):
    panel.show(FAKE_ELEMENT)
    assert panel.state() == "ready"
    # the group is visible and has tabs in it
    assert not panel.grp_charts.isHidden()
    tabs = _chart_tabs(panel)
    assert len(tabs) >= 2, \
        f"expected ≥2 chart tabs, got {len(tabs)}"
    # orbit and sky are vector slots (data extracted for click rebuild)
    assert "orbit" in panel._slot_data, "orbit slot data missing"
    assert "sky" in panel._slot_data, "sky slot data missing"
    # field needs the network (a reference cutout); it is absent offline
    assert "field" not in panel._slot_data
    assert "field" not in [w.property("chart_key") for w in tabs]


def test_chart_tab_titles_recorded(panel):
    # FAKE_ELEMENT renders orbit/sky/approach: each tab is labelled with
    # the chart's translated title and the viewer title matches.
    panel.show(FAKE_ELEMENT)
    assert panel._tabs.count() >= 3, f"expected ≥3 tabs, got {panel._tabs.count()}"
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    from nightscribe.gui.widgets.orbit_widget import OrbitChart
    from nightscribe.gui.widgets.sky_widget import SkyChart
    tabs = _chart_tabs(panel)
    keys = [w.property("chart_key") for w in tabs]
    assert keys == ["orbit", "sky", "approach"], f"tab order wrong: {keys}"
    for i, w in enumerate(tabs):
        title = panel._tabs.tabText(i)
        assert title, f"tab {i} has an empty title"
        assert panel._slot_titles[w.property("chart_key")] == title, \
            f"tab title {title!r} != viewer title for {w.property('chart_key')}"
    assert isinstance(tabs[0], OrbitChart)
    assert isinstance(tabs[1], SkyChart)
    assert isinstance(tabs[2], ApproachChart)


def test_vector_slots_are_live_widgets(panel):
    # FAKE_ELEMENT is a bound orbit with an ephemeris: orbit and sky
    # become live chart widgets (OrbitChart / SkyChart) with working views.
    panel.show(FAKE_ELEMENT)
    from nightscribe.gui.widgets.orbit_widget import OrbitChart
    from nightscribe.gui.widgets.sky_widget import SkyChart
    tabs = _chart_tabs(panel)
    orbit_w = next((w for w in tabs if isinstance(w, OrbitChart)), None)
    sky_w = next((w for w in tabs if isinstance(w, SkyChart)), None)
    assert orbit_w is not None, "no OrbitChart in the tabs"
    assert sky_w is not None, "no SkyChart in the tabs"
    # both have a ChartView with a non-empty scene
    from nightscribe.gui.widgets.base_chart import ChartView
    assert isinstance(orbit_w.view, ChartView)
    assert isinstance(sky_w.view, ChartView)
    assert orbit_w.view.scene().items(), "orbit scene is empty"
    assert sky_w.view.scene().items(), "sky scene is empty"


def test_single_chart_hides_tab_bar(panel, monkeypatch):
    # When only ONE chart can be produced, the tab bar auto-hides so the
    # chart stands alone (no useless single-tab strip); the group stays.
    from nightscribe.core import post
    monkeypatch.setattr(post, "build_charts", lambda *_a, **_k: {})
    panel.show(FAKE_ELEMENT)          # vector approach still renders
    assert panel.state() == "ready"
    assert not panel.grp_charts.isHidden(), "charts group must stay visible"
    assert panel._tabs.count() == 1, f"expected 1 tab, got {panel._tabs.count()}"
    assert panel._tabs.tabBarAutoHide(), \
        "tab bar must auto-hide for a single chart"


def test_no_charts_hides_the_whole_group(panel):
    # FAKE_UNCONFIRMED has no elements, no ephemeris and no simbad:
    # build_charts produces nothing, so the whole charts group disappears.
    panel.show(FAKE_UNCONFIRMED)
    assert panel.grp_charts.isHidden()
    assert panel._tabs.count() == 0, "tabs should be empty"
    assert panel._slot_data == {}


def test_missing_state_keeps_charts_hidden(panel):
    panel.show({})
    assert panel.state() == "missing"
    assert panel.grp_charts.isHidden()
    assert panel._tabs.count() == 0
    assert panel._slot_data == {}


def test_charts_slot_title_recorded(panel):
    # When a chart lands, its viewer/tab title is stored in _slot_titles.
    panel.show(FAKE_ELEMENT)
    assert "orbit" in panel._slot_titles, "orbit title not recorded"
    assert panel._slot_titles["orbit"], "orbit title is empty"


def test_approach_slot_present_for_bound_orbit(panel):
    # The approach tab appears for a body with propagatable elements (a or
    # q) — FAKE_ELEMENT has both.
    panel.show(FAKE_ELEMENT)
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    tabs = _chart_tabs(panel)
    ap_w = next((w for w in tabs if isinstance(w, ApproachChart)), None)
    assert ap_w is not None, "no ApproachChart in the tabs"
    assert ap_w.property("chart_key") == "approach"
    # rebuild data is stored for the click-through viewer
    assert "approach" in panel._slot_data
    assert "elements" in panel._slot_data["approach"]
    assert "jd" in panel._slot_data["approach"]
    assert "approach" in panel._slot_titles


def test_approach_slot_rebuild_widget_works(panel):
    # Clicking the slot rebuilds a fresh ApproachChart for the viewer:
    # the rebuilt widget must accept the stored data without raising and
    # expose the same elements.
    panel.show(FAKE_ELEMENT)
    data = panel._slot_data.get("approach")
    assert data is not None, "approach slot data missing"
    rebuilt = panel._rebuild_widget("approach", data)
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    assert isinstance(rebuilt, ApproachChart)
    assert rebuilt.elements() == data["elements"]


def test_approach_slot_absent_without_elements(panel):
    # FAKE_UNCONFIRMED has no sbdb: the approach chart cannot be drawn,
    # and it must not appear (nor leave a dangling title for it).
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    panel.show(FAKE_UNCONFIRMED)
    tabs = _chart_tabs(panel)
    assert not any(isinstance(w, ApproachChart) for w in tabs)
    assert "approach" not in panel._slot_data
    # and the make/extract helpers answer None for it
    assert panel._make_vector("approach", FAKE_UNCONFIRMED) is None
    assert panel._extract("approach", FAKE_UNCONFIRMED) is None


# ---------------- object-card plan, subplan 0: coordinates block -----
#
# The block sits under the hook and shows RA/Dec in decimal AND
# sexagesimal, with a copy button that puts both on the clipboard. It
# hides for objects without a known position (ESA alerts, bare
# unconfirmed rows). No network: fixtures carry their own coordinates.

def test_coords_block_shows_decimal_and_sexagesimal(panel):
    # FAKE_ELEMENT ephem: ra "12 00 00.000" (180°), dec "+30 00 00.000"
    panel.show(FAKE_ELEMENT)
    assert panel.state() == "ready"
    assert not panel.row_coords.isHidden()
    txt = panel.lbl_coords.text()
    assert "180.00000°" in txt, f"decimal RA missing: {txt!r}"
    assert "12h 00m 00.0s" in txt, f"sexagesimal RA missing: {txt!r}"
    assert "+30.00000°" in txt, f"decimal Dec missing: {txt!r}"
    assert "+30° 00′ 00.0″" in txt, f"sexagesimal Dec missing: {txt!r}"


def test_coords_copy_button_fills_clipboard(panel, qapp):
    # One click copies both formats (decimal and sexagesimal).
    from PySide6.QtGui import QGuiApplication
    panel.show(FAKE_ELEMENT)
    panel.btn_copy_coords.click()
    clip = QGuiApplication.clipboard().text()
    assert "180.00000°" in clip, f"decimal RA not copied: {clip!r}"
    assert "12h 00m 00.0s" in clip, f"sexagesimal RA not copied: {clip!r}"
    assert "+30.00000°" in clip, f"decimal Dec not copied: {clip!r}"
    assert "+30° 00′ 00.0″" in clip, f"sexagesimal Dec not copied: {clip!r}"


def test_coords_block_hidden_without_position(panel):
    # FAKE_UNCONFIRMED carries no ra/dec anywhere: the block must hide
    # (the «omit what is missing» rule) and the panel stays ready.
    panel.show(FAKE_UNCONFIRMED)
    assert panel.state() == "ready"
    assert panel.row_coords.isHidden()


def test_coords_block_simbad_fallback(panel):
    # No ephemeris: SIMBAD coordinates (sexagesimal strings) are used.
    from nightscribe.core import coords
    fx = _sn_fixture()
    fx["data"]["simbad"] = {"ra": "14 03 38.6", "dec": "+54 18 42.0",
                            "otype": "SN*", "vmag": 14.2}
    panel.show(fx)
    assert not panel.row_coords.isHidden()
    txt = panel.lbl_coords.text()
    assert "14h 03m 38.6s" in txt, f"SIMBAD RA not rendered: {txt!r}"
    dec_deg = coords.dec_dms_to_deg("+54 18 42.0")
    assert f"{dec_deg:+.5f}°" in txt, f"SIMBAD Dec not rendered: {txt!r}"


def test_coords_block_shows_epoch_for_moving_target(panel):
    # A moving target carries an ephemeris epoch: the block shows it so the
    # observer sees how fresh the position is.
    fx = __import__("copy").deepcopy(FAKE_ELEMENT)
    fx["data"]["ephem_epoch"] = "2026-Sep-07 22:30"
    panel.show(fx)
    txt = panel.lbl_coords.text()
    assert "Epoch" in txt, f"epoch label missing: {txt!r}"
    # Horizons-style month is normalised to ISO
    assert "2026-09-07 22:30" in txt


def test_coords_block_no_epoch_for_fixed_target(panel):
    # A supernova (fixed coordinates) has no ephemeris epoch: no epoch line.
    fx = _sn_fixture()
    fx["data"]["simbad"] = {"ra": "14 03 38.6", "dec": "+54 18 42.0",
                            "otype": "SN*", "vmag": 14.2}
    panel.show(fx)
    assert "Epoch" not in panel.lbl_coords.text()


def test_nearest_ephemeris_row_picks_closest_to_now():
    # The helper used by enrich picks the row closest to the reference time,
    # not the first one (which is 00:00 UT and up to 24 h stale for a NEO).
    import datetime
    from nightscribe.core import enrich
    rows = [
        {"time": "2026-Sep-07 00:00", "ra": "10 00 00", "dec": "+00 00 00",
         "r": 1.0, "delta": 1.0},
        {"time": "2026-Sep-07 22:30", "ra": "10 00 30", "dec": "+00 00 02",
         "r": 1.0, "delta": 1.0},
        {"time": "2026-Sep-08 00:00", "ra": "10 01 00", "dec": "+00 00 04",
         "r": 1.0, "delta": 1.0},
    ]
    when = datetime.datetime(2026, 9, 7, 22, 35,
                             tzinfo=datetime.timezone.utc)
    row = enrich._nearest_ephemeris_row(rows, when)
    assert row["time"] == "2026-Sep-07 22:30"


# ---------------- ADR-057: parameter sections --------------------------
#
# The single QTableWidget is gone: the rows live in themed section cards
# (definition lists that wrap and size themselves). These tests pin the
# grouping, the wrapped explanations and the "In depth" filtering.

def test_params_grouped_in_titled_sections(panel):
    # FAKE_ELEMENT is a small body: its rows land in the orbit / physical
    # / provenance sections, in that order, with their translated titles.
    panel.show(FAKE_ELEMENT)
    from nightscribe.core import orbits
    lang = panel._lang()
    titles = [c.lbl_title.text() for c in panel._section_cards]
    expect = [orbits.SECTION_TITLES[g][lang]
              for g in ("orbit", "physical", "provenance")]
    assert titles == expect, f"section order/titles wrong: {titles!r}"
    # every row landed somewhere, and no section is empty
    assert sum(c.row_count() for c in panel._section_cards) \
        == len(panel._rows)
    assert all(c.row_count() > 0 for c in panel._section_cards)


def test_section_rows_carry_the_full_explanation(panel):
    # the "what it means" sentence survives the move to cards, wrapped
    panel.show(FAKE_ELEMENT)
    from PySide6.QtWidgets import QLabel
    explanations = [r[2] for r in _param_cells(panel)]
    assert all(len(t) > 40 for t in explanations), \
        f"explanation too short: {explanations!r}"
    # and the labels really wrap (no one-word-per-line columns)
    wraps = [l for c in panel._section_cards
             for l in c.findChildren(QLabel) if l.wordWrap()]
    assert wraps, "no wrapped explanation label in the section cards"


def test_in_depth_filters_every_section(panel):
    # with the switch off, only basic rows survive, in every section
    panel.show(FAKE_ELEMENT)
    panel.chk_deep.setChecked(False)
    basic = _param_cells(panel)
    params = [r[0].lower() for r in basic]
    assert any("family" in p or "familia" in p for p in params)
    assert not any("semi-major" in p or "semieje" in p for p in params), \
        "deep rows leaked into the basic view"
    # a section whose rows are ALL deep disappears, it does not stay empty
    assert all(c.row_count() > 0 for c in panel._section_cards)


def test_new_provenance_rows(panel):
    # ADR-057 shows what the card hid before: the discovery date (SBDB)
    panel.show(FAKE_ELEMENT)
    rows = _param_cells(panel)
    disc = next((r for r in rows
                 if "discover" in r[0].lower() or "descub" in r[0].lower()),
                None)
    assert disc is not None, f"no discovery row: {[r[0] for r in rows]!r}"
    assert "2026-08-19" in disc[1], f"discovery date missing: {disc[1]!r}"


# ---------------- object-card plan, subplan 2: SN parameters table ---
#
# Supernovae get the same parameters table the small bodies already
# had (orbits.explain_transient): event type, host galaxy, distance,
# brightness, discovery date — redshift under the «in depth» toggle.

def _sn_full_fixture():
    # A supernova with everything the panel can tabulate (SIMBAD +
    # the ADR-027 planner-context merge already applied).
    return {
        "type": "transient",
        "name": "2026ziz",
        "data": {
            "simbad": {"otype": "SN Ia", "ra": "14 03 38.6",
                       "dec": "+54 18 42.0", "vmag": 14.2, "z": 0.0114},
            "host": {"name": "NGC 5908", "z": 0.0114},
            "dist_mly": 121.0,
            "disc_date": "2026/08/30",
        },
    }


def test_sn_has_params_table(panel):
    panel.show(_sn_full_fixture())
    assert panel.state() == "ready"
    assert not panel.grp_params.isHidden(), "SN must get a params table"
    rows = _param_cells(panel)
    assert len(rows) >= 4, f"expected ≥4 SN rows, got {len(rows)}"
    # every explanation is a real sentence, in whichever language is on
    assert all(len(r[2]) > 40 for r in rows), \
        f"explanation column too short: {[r[2] for r in rows]!r}"
    params = [r[0].lower() for r in rows]
    assert any("tipo" in p or "type" in p for p in params), params
    assert any("galaxia" in p or "host" in p for p in params), params
    assert any("distancia" in p or "distance" in p for p in params), params
    assert any("descub" in p or "discover" in p for p in params), params


def test_sn_table_explains_the_event_type(panel):
    # the Ia row must translate the jargon, not just repeat it
    panel.show(_sn_full_fixture())
    rows = _param_cells(panel)
    typerow = next(r for r in rows if "SN Ia" in r[1])
    meaning = typerow[2].lower()
    assert "enana blanca" in meaning or "white dwarf" in meaning, meaning
    assert "vela" in meaning or "candle" in meaning, meaning


def test_sn_table_redshift_is_deep_only(panel):
    panel.show(_sn_full_fixture())
    panel.chk_deep.setChecked(False)
    basic = [r[0].lower() for r in _param_cells(panel)]
    assert not any("redshift" in p or "corrimiento" in p for p in basic), \
        f"redshift leaked into the basic view: {basic}"
    panel.chk_deep.setChecked(True)
    deep = _param_cells(panel)
    zrow = next((r for r in deep
                 if "redshift" in r[0].lower()
                 or "corrimiento" in r[0].lower()), None)
    assert zrow is not None, "no redshift row after the in-depth toggle"
    assert "0.0114" in zrow[1], f"redshift value missing: {zrow[1]!r}"


def test_sn_table_from_context_only(panel):
    # ADR-027 fallback: SIMBAD silent, the planner context carries
    # type/mag/date — the table must still tell the story.
    fx = {"type": "transient", "name": "2026zzz",
          "data": {"otype": "II", "mag": 16.7, "disc_date": "2026-09-01",
                   "host": {"name": "UGC 11852"}}}
    panel.show(fx)
    rows = _param_cells(panel)
    assert len(rows) >= 4, f"context-only SN too thin: {rows!r}"
    typerow = next(r for r in rows if r[1] == "II")
    assert "masiva" in typerow[2].lower() or "massive" in typerow[2].lower()


def test_sn_table_omits_missing_facts(panel):
    # a minimal fixture (host name only) must not raise and shows only
    # what exists — the «omit what is missing» rule
    fx = {"type": "transient", "name": "2026zzz",
          "data": {"host": {"name": "NGC 5908"}}}
    panel.show(fx)
    rows = _param_cells(panel)
    params = [r[0].lower() for r in rows]
    assert any("galaxia" in p or "host" in p for p in params), params
    assert not any("distancia" in p or "distance" in p for p in params), params
    assert not any("descub" in p or "discover" in p for p in params), params


# ---------------- object-card plan, subplan 3b: transit table --------
#
# Exoplanet transits get the table too: tonight's event (start, end,
# depth, duration, telescope verdict) plus the planet's story in the
# «in depth» rows. Data = Archive fields + the merged ExoClock event.

def _transit_fixture():
    import datetime
    return {
        "type": "exoplanet",
        "name": "HD 209458 b",
        "data": {
            "pl_name": "HD 209458 b", "hostname": "HD 209458",
            "pl_orbper": 3.5247, "pl_radj": 1.38, "pl_bmassj": 0.73,
            "sy_dist": 48.3, "disc_year": 1999, "discoverymethod": "Transit",
            "ra": 330.795, "dec": 18.884,
            "transit": {
                "ingress": datetime.datetime(2026, 9, 7, 22, 40,
                                             tzinfo=datetime.timezone.utc),
                "mid": datetime.datetime(2026, 9, 8, 0, 15,
                                         tzinfo=datetime.timezone.utc),
                "egress": datetime.datetime(2026, 9, 8, 1, 50,
                                            tzinfo=datetime.timezone.utc),
                "duration_h": 3.1, "depth_mmag": 16.4, "v_mag": 7.65,
                "min_telescope_in": 6.0, "oc_min": -12.0,
            },
        },
    }


def test_transit_has_params_table(panel):
    panel.show(_transit_fixture())
    assert panel.state() == "ready"
    assert not panel.grp_params.isHidden(), "transit must get a params table"
    rows = _param_cells(panel)
    assert all(len(r[2]) > 40 for r in rows), \
        f"explanation column too short: {[r[2] for r in rows]!r}"
    params = [r[0].lower() for r in rows]
    assert any("tránsito" in p or "transit tonight" in p for p in params), params
    assert any("profundidad" in p or "depth" in p for p in params), params
    assert any("duración" in p or "duration" in p for p in params), params


def test_transit_table_shows_start_end_and_depth(panel):
    # the headline facts: when it starts (ingress), when it ends and
    # how deep the dip is — in mmag and in % of flux
    panel.show(_transit_fixture())
    rows = _param_cells(panel)
    when = next(r for r in rows if "UTC" in r[1])
    assert "22:40" in when[1] and "01:50" in when[1], when[1]
    depth = next(r for r in rows
                 if "profundidad" in r[0].lower() or "depth" in r[0].lower())
    assert "16.4" in depth[1], f"mmag missing: {depth[1]!r}"
    assert "1.5%" in depth[1], f"flux % missing: {depth[1]!r}"


def test_transit_table_telescope_verdict(panel):
    # aperture 10″ vs minimum 6″: the verdict row says the user makes it
    from nightscribe.config import config
    saved = config.get("aperture_inches")
    config._data["aperture_inches"] = 10.0
    try:
        panel.show(_transit_fixture())
    finally:
        config._data["aperture_inches"] = saved
    rows = _param_cells(panel)
    tel = next(r for r in rows
               if "telescop" in r[0].lower() or "telescope" in r[0].lower())
    assert "6″" in tel[1] and "10″" in tel[1], f"verdict value: {tel[1]!r}"
    meaning = tel[2].lower()
    assert ("llega" in meaning or "up to it" in meaning), meaning
    assert not ("corto" in meaning or "falls short" in meaning), meaning


def test_transit_table_telescope_verdict_short(panel):
    # aperture 4″ vs minimum 6″: the verdict must say so, honestly
    from nightscribe.config import config
    saved = config.get("aperture_inches")
    config._data["aperture_inches"] = 4.0
    try:
        panel.show(_transit_fixture())
    finally:
        config._data["aperture_inches"] = saved
    rows = _param_cells(panel)
    tel = next(r for r in rows
               if "telescop" in r[0].lower() or "telescope" in r[0].lower())
    meaning = tel[2].lower()
    assert ("corto" in meaning or "falls short" in meaning), meaning


def test_transit_table_deep_rows(panel):
    # the planet's story lives under «in depth»: period, size, distance,
    # discovery and the O-C drift (why tonight's timing matters)
    panel.show(_transit_fixture())
    # Interfaz 1.8: "in depth" is on by default, so the basic view is the
    # one with it turned off
    panel.chk_deep.setChecked(False)
    basic = [r[0].lower() for r in _param_cells(panel)]
    assert not any("o-c" in p or "deriva" in p for p in basic), basic
    panel.chk_deep.setChecked(True)
    deep = _param_cells(panel)
    params = [r[0].lower() for r in deep]
    assert any("año" in p or "year" in p for p in params), params
    assert any("tamaño" in p or "size" in p for p in params), params
    assert any("o-c" in p or "deriva" in p for p in params), params
    oc = next(r for r in deep
              if "o-c" in r[0].lower() or "deriva" in r[0].lower())
    assert "-12" in oc[1], f"O-C value missing: {oc[1]!r}"


def test_transit_table_without_event_shows_archive_only(panel):
    # typed into Explore with no planner row: no «tonight» row, but the
    # planet's story is still tabulated in the deep rows
    fx = _transit_fixture()
    del fx["data"]["transit"]
    panel.show(fx)
    rows = _param_cells(panel)
    params = [r[0].lower() for r in rows]
    assert not any("tránsito" in p or "transit tonight" in p
                   for p in params), params
    panel.chk_deep.setChecked(True)
    assert _param_cells(panel), "archive-only transit table is empty"


# ---------------- object-card plan, subplan 4: per-kind chips --------
#
# Every family fills its chip row with the same grammar: an SN card or
# a transit card must not look sparse next to a NEO's. The extras come
# from the enriched data, so they show even without a planner context.

def test_capture_block_sn_type_and_freshness_chips(panel):
    # SN card: event type + days-since-discovery tiles from the data
    from nightscribe.core import orbits
    panel.show(_sn_full_fixture())
    tiles = _tile_texts(panel)
    assert any("SN Ia" in c for c in tiles), f"type tile missing: {tiles!r}"
    days = orbits.days_since("2026/08/30")
    assert any(c.startswith(f"{days} d|") for c in tiles), \
        f"freshness tile missing: {tiles!r}"


def test_sn_type_tile_tooltip_explains(panel):
    # ADR-058: the "Event type" tile shows the code, and its tooltip
    # explains what the code means, never just «Type of stellar explosion»
    from nightscribe.gui.widgets.kpi_tile import KpiTile
    panel.show(_sn_full_fixture())
    tiles = panel.kpi_strip.findChildren(KpiTile)
    ev = next(t for t in tiles
              if t.texts()[1] in ("Event type", "Tipo de evento"))
    tip = ev.toolTip().lower()
    assert "enana blanca" in tip or "white dwarf" in tip, ev.toolTip()


def test_capture_block_transit_depth_chip(panel):
    # transit card: the star-dimming tile from the merged ExoClock event
    panel.show(_transit_fixture())
    tiles = _tile_texts(panel)
    assert any("16.4" in c and "mmag" in c.lower() for c in tiles), \
        f"depth tile missing: {tiles!r}"


def _hads_fixture():
    # A HADS payload as enrich.enrich builds it (planner values merged)
    return {"type": "hads", "name": "CY Aqr",
            "data": {"hads": {"period_h": 1.46, "max": 11.3, "min": 11.8,
                              "amp": 0.5, "cycles": 4.2, "session_fits": True,
                              "priority": "period_change", "observed": True,
                              "multiperiodic": True, "non_radial": False}}}


def test_capture_block_hads_chips(panel):
    # HADS card: period/amplitude/cycles tiles + the programme flag pills
    # (ADR-034; ADR-057 split: numbers are tiles, alerts stay pills)
    panel.show(_hads_fixture())
    tiles = _tile_texts(panel)
    assert any("1.46 h" in c for c in tiles), f"period tile: {tiles!r}"
    assert any("0.5 mag" in c for c in tiles), f"amp tile: {tiles!r}"
    assert any("×4.2" in c for c in tiles), f"cycles tile: {tiles!r}"
    chips = _chip_texts(panel)
    assert any("Period change" in c for c in chips), f"priority: {chips!r}"
    assert any("Multiperiodic" in c for c in chips), f"multi: {chips!r}"


def test_capture_block_extras_omit_missing(panel):
    # bare SN (host name only, no context): no invented tiles or flags —
    # both rows hide themselves, same «omit what is missing» rule
    panel.show(_sn_fixture())
    assert panel.state() == "ready"
    assert panel.row_capture.isHidden()
    assert _chip_texts(panel) == []
    assert panel.kpi_strip.isHidden()
    assert _tile_texts(panel) == []


# ---------------- D3: capture / window block ----------------
#
# The block reads the project context snapshot (the numbers a capture plan
# actually uses): magnitude, apparent rate (NEO/PCCP only), max no-trail
# exposure (rate + camera profile) and the hours-above-horizon window. It
# omits whatever is missing, and hides itself entirely when it has nothing
# to show. No network: the SN fixture renders hook + bullets + "why not"
# slot lines entirely offline.

def _chip_texts(panel):
    # @return: the visible flag-pill labels, in order (ADR-057: the flags
    #   row keeps only alerts; the numbers moved to the KPI strip)
    from PySide6.QtWidgets import QLabel
    return [w.text() for w in panel.row_capture.findChildren(QLabel)
            if w.text().strip()]


def _sn_fixture():
    # A transient/supernova payload with just enough to render the hook,
    # the fact bullets and every "why not" slot — nothing needs the network.
    return {
        "type": "transient",
        "name": "2026ziz",
        "data": {
            "host": {"name": "NGC 5908"},
            "dist_mly": 74,
            "simbad": {},              # an empty simbad: no cutout, no field
        },
    }


def test_capture_block_sn_no_rate_exposure(panel):
    # An SN: mag + window apply, but the rate and max-exposure tiles are
    # gated to neo/pccp, so they are omitted — even when a rate is present in
    # the context (the "con sn: sin tasa/exposición" rule).
    ctx = {
        "kind": "sn",
        "mag": 14.2,
        "rate_arcsec_min": 9.0,   # sneaked in: must still be hidden (an SN)
        "window_start": "2026-08-26T21:00:00+02:00",
        "window_end": "2026-08-26T23:30:00+02:00",
        "hours_up": 2.5,
    }
    panel.show(_sn_fixture(), ctx)
    assert panel.state() == "ready"
    assert not panel.kpi_strip.isHidden()
    tiles = _tile_texts(panel)
    assert any("14.2" in c for c in tiles), f"mag tile missing: {tiles!r}"
    assert any("21:00" in c and "23:30" in c for c in tiles), \
        f"window tile missing: {tiles!r}"
    assert any("2.5 h" in c for c in tiles), f"hours tile missing: {tiles!r}"
    assert not any("″/min" in c for c in tiles), \
        f"rate must be omitted for an SN: {tiles!r}"
    assert not any("max exposure" in c.lower() for c in tiles), \
        f"exposure must be omitted for an SN: {tiles!r}"


def test_capture_block_full_neo_chips(panel):
    # A NEO context snapshot with everything: mag, rate, window + hours.
    ctx = {
        "kind": "neo",
        "mag": 19.5,
        "rate_arcsec_min": 12.0,
        "window_start": "2026-08-26T21:00:00+02:00",
        "window_end": "2026-08-26T23:30:00+02:00",
        "hours_up": 2.5,
    }
    panel.show(FAKE_ELEMENT, ctx)
    assert panel.state() == "ready"
    assert not panel.kpi_strip.isHidden()
    tiles = _tile_texts(panel)
    # magnitude
    assert any("19.5" in c for c in tiles), f"mag tile missing: {tiles!r}"
    # rate ″/min
    assert any("″/min" in c for c in tiles), f"rate tile missing: {tiles!r}"
    # window HH:MM–HH:MM
    assert any("21:00" in c and "23:30" in c for c in tiles), \
        f"window tile missing: {tiles!r}"
    # hours above
    assert any("2.5 h" in c for c in tiles), f"hours tile missing: {tiles!r}"


def test_capture_block_neo_max_exposure_present(panel):
    # A NEO with a rate and a complete camera profile gets a max no-trail
    # exposure tile (the whole point of the camera profile for NEOs).
    from nightscribe.config import config
    saved = (config.get("pixel_um"), config.get("focal_mm"))
    config._data["pixel_um"] = 3.76
    config._data["focal_mm"] = 2000.0
    try:
        panel.show(FAKE_ELEMENT, {"kind": "neo", "mag": 19.5,
                                  "rate_arcsec_min": 12.0})
    finally:
        config._data["pixel_um"], config._data["focal_mm"] = saved
    tiles = _tile_texts(panel)
    assert any("max exposure" in c.lower() for c in tiles), \
        f"max-exposure tile missing for a NEO with a rate: {tiles!r}"
    # and the rate tile is present alongside it
    assert any("″/min" in c for c in tiles), f"rate tile missing: {tiles!r}"


def test_capture_block_empty_ctx_does_not_break(panel):
    # show() with a valid payload and an empty/None context: no crash, the
    # panel stays ready. ADR-057: the enriched dict's own magnitude still
    # feeds a tile (the dossier shows what it knows), but there are no
    # flags without a context.
    panel.show(FAKE_ELEMENT, {})
    assert panel.state() == "ready"
    assert panel.row_capture.isHidden()
    assert _chip_texts(panel) == []
    assert any("19.8" in t for t in _tile_texts(panel)), \
        "the enriched mag should feed the strip even without a context"
    # again with no context at all (the D3 «no rompe con ctx vacío» rule)
    panel.show(FAKE_ELEMENT, None)
    assert panel.state() == "ready"
    assert panel.row_capture.isHidden()


def test_capture_block_pccp_omits_rate_when_missing(panel):
    # A PCCP with a window but no rate: window + hours show, while rate and
    # exposure are omitted (the «omit what is missing» rule).
    ctx = {
        "kind": "pccp",
        "mag": 20.2,
        "window_start": "2026-08-26T20:00:00+02:00",
        "window_end": "2026-08-26T22:00:00+02:00",
        "hours_up": 2.0,
    }
    panel.show(FAKE_UNCONFIRMED, ctx)
    assert panel.state() == "ready"
    assert not panel.kpi_strip.isHidden()
    tiles = _tile_texts(panel)
    assert any("20.2" in c for c in tiles), f"mag tile missing: {tiles!r}"
    assert any("20:00" in c and "22:00" in c for c in tiles), \
        f"window tile missing: {tiles!r}"
    assert any("2.0 h" in c for c in tiles), f"hours tile missing: {tiles!r}"
    assert not any("″/min" in c for c in tiles), \
        f"rate must be omitted without a rate: {tiles!r}"
    assert not any("max exposure" in c.lower() for c in tiles), \
        f"exposure must be omitted without a rate: {tiles!r}"


def test_capture_block_safe_window_chip(panel):
    # (ADR-020) a saved capture plan computes a safe window: the tile shows
    # the safe span plus the latest-safe-start, and the red warning is absent.
    ctx = {
        "kind": "neo",
        "mag": 19.5,
        "window_start": "2026-08-26T21:00:00+02:00",
        "window_end": "2026-08-26T23:30:00+02:00",
        "safe_window": "2026-08-27T02:00:00|2026-08-27T04:00:00",
        "best_time": "2026-08-27T02:30:00",
        "duration_s": 7200,
    }
    panel.show(FAKE_ELEMENT, ctx)
    assert not panel.kpi_strip.isHidden()
    tiles = _tile_texts(panel)
    assert any("02:00" in c and "04:00" in c for c in tiles), \
        f"safe window tile missing: {tiles!r}"
    assert any("≤ 02:30" in c for c in tiles), \
        f"latest-safe-start missing: {tiles!r}"
    assert not any("does not fit" in c.lower() for c in tiles), \
        f"must not warn when it fits: {tiles!r}"


def test_capture_block_does_not_fit_red_chip(panel):
    # (ADR-020) a session is planned but it does not fit: the one red safety
    # tile appears FIRST (it must never scroll off), and no green safe tile.
    ctx = {
        "kind": "neo",
        "mag": 19.5,
        "window_start": "2026-08-26T21:00:00+02:00",
        "window_end": "2026-08-26T21:30:00+02:00",
        "duration_s": 7200,
    }
    panel.show(FAKE_ELEMENT, ctx)
    assert not panel.kpi_strip.isHidden()
    tiles = _tile_texts(panel)
    assert any("does not fit" in c.lower() and "120 min" in c
               for c in tiles), \
        f"red 'does not fit' tile missing: {tiles!r}"
    assert tiles[0].startswith("⚠"), \
        f"the safety tile must lead the strip: {tiles!r}"
    assert not any("≤" in c for c in tiles), \
        f"no latest-safe-start when the session does not fit: {tiles!r}"


def test_capture_block_no_plan_no_safe_chips(panel):
    # (ADR-020) no capture plan saved: the safe-window and red tiles are
    # absent (the plain window/hours tiles are the whole block).
    ctx = {
        "kind": "neo",
        "mag": 19.5,
        "window_start": "2026-08-26T21:00:00+02:00",
        "window_end": "2026-08-26T23:30:00+02:00",
    }
    panel.show(FAKE_ELEMENT, ctx)
    tiles = _tile_texts(panel)
    assert not any("≤" in c for c in tiles), \
        f"no latest-safe-start without a plan: {tiles!r}"
    assert not any("does not fit" in c.lower() for c in tiles), \
        f"no warning without a plan: {tiles!r}"


# ---------------- phase E (corrected 2026-09-02): the single CTA -------
#
# The Explore dialog is now this same panel with for_post=True and a
# single CTA at the bottom of the layout (the "Create project" /
# "Continue project" face, depending on what the injected lookup says).
# The old "Create post" affordance is gone: it lived inside the project
# on its Publish step (or ad-hoc under Tools).
#
# The hub flavour (for_post=False) keeps the CTA invisible — the panel
# is read-only there.

class _PendingWorker(FakeWorker):
    """A worker that never delivers until the test releases it."""

    def __init__(self, payload):
        super().__init__(payload)
        self._pending = True

    def start(self):
        self._pending = False
        # do not deliver yet; release() fires it later


def _release(worker):
    worker._pending = False
    worker.finished.deliver(worker.payload)


def test_cta_hidden_in_hub_flavour(qapp, tmp_path):
    # the Projects hub keeps for_post=False: the CTA is not part of the
    # panel's surface there, even after the object lands on it
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(chart_dir=tmp_path / "charts")
    try:
        assert p.btn_project.isHidden()
        assert p.name() is None  # ... and no stale object either
        # even after show() + ready, nothing changes
        p.show(FAKE_ELEMENT)
        assert p.btn_project.isHidden()
    finally:
        p.deleteLater()


def test_cta_hidden_without_lookup(qapp, tmp_path):
    # for_post=True but no project_lookup: the "Explore without hub
    # wiring" case, the CTA stays hidden — we don't know which face to
    # give it
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(chart_dir=tmp_path / "charts", for_post=True)
    try:
        assert p.btn_project.isHidden()
        p.show(FAKE_ELEMENT)
        assert p.btn_project.isHidden()
    finally:
        p.deleteLater()


def test_cta_create_face_when_no_active(qapp, tmp_path):
    # for_post=True + lookup returning None -> the CTA shows "Create
    # project"
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(chart_dir=tmp_path / "charts", for_post=True,
                    project_lookup=lambda name: None)
    try:
        p.show(FAKE_ELEMENT)
        assert not p.btn_project.isHidden()
        assert p._action == "create"
        assert "Create project" in p.btn_project.text()
    finally:
        p.deleteLater()


def test_cta_continue_face_when_active(qapp, tmp_path):
    # for_post=True + lookup returning a project -> the CTA shows
    # "Continue project"
    from nightscribe.gui.overview import ObjectPanel
    hit = {"id": 1, "status": "active"}
    p = ObjectPanel(chart_dir=tmp_path / "charts", for_post=True,
                    project_lookup=lambda name: hit)
    try:
        p.show(FAKE_ELEMENT)
        assert not p.btn_project.isHidden()
        assert p._action == "continue"
        assert "Continue project" in p.btn_project.text()
    finally:
        p.deleteLater()


def test_cta_create_signal_emits_object(qapp, tmp_path):
    # clicking the CTA in "create" face fires project_create(name,
    # fallback) — exactly the two args the owner (the Explore dialog's
    # glue) needs; nothing else.
    from nightscribe.gui.overview import ObjectPanel
    fb = {"id": "neo1", "kind": "neo"}
    p = ObjectPanel(loader=lambda n, f=None: FakeWorker(FAKE_ELEMENT),
                    chart_dir=tmp_path / "charts", for_post=True,
                    project_lookup=lambda n: None)
    try:
        p.explore("2026 QK (443089)", fallback_target=fb)
        assert p.state() == "ready"
        got = []
        p.project_create.connect(lambda n, f: got.append((n, f)))
        p.btn_project.clicked.emit()
        assert got == [("2026 QK (443089)", fb)], got
    finally:
        p.deleteLater()


def test_cta_continue_signal_emits_object(qapp, tmp_path):
    # clicking the CTA in "continue" face fires project_continue(name,
    # fallback) — a separate signal from project_create, so the owner
    # never has to decode a flag argument to know the intent.
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(chart_dir=tmp_path / "charts", for_post=True,
                    project_lookup=lambda n: {"id": 1})
    try:
        p.show(FAKE_ELEMENT, None)
        got = []
        p.project_continue.connect(lambda n, f: got.append((n, f)))
        p.btn_project.clicked.emit()
        assert got == [("2026 QK (443089)", None)], got
    finally:
        p.deleteLater()


def test_cta_signals_are_two_and_distinct(qapp, tmp_path):
    # both signals exist on the class with two args each (and only two,
    # no stray third-arg `continue_` that PySide refuses to emit). The
    # old project_action is gone.
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(chart_dir=tmp_path / "charts")
    from PySide6.QtCore import QMetaMethod
    mm = p.metaObject()
    names = [mm.method(i).name() for i in range(mm.methodCount())
             if mm.method(i).methodType() == QMetaMethod.Signal]
    assert "project_create" in names
    assert "project_continue" in names
    assert "project_action" not in names
    assert "post_requested" not in names
    p.deleteLater()


def test_cta_ignored_while_loading(qapp, tmp_path):
    # the dialog must not fire the CTA for an object that is still in
    # flight: the button is hidden while the worker is out there
    from nightscribe.gui.overview import ObjectPanel
    loader = {}

    def slow_loader(name, fallback_target=None):
        w = _PendingWorker(FAKE_ELEMENT)
        loader["w"] = w
        return w

    p = ObjectPanel(loader=slow_loader, chart_dir=tmp_path / "charts",
                    for_post=True, project_lookup=lambda n: None)
    try:
        p.explore("2026 QK (443089)")
        assert p.state() == "loading"
        assert p.btn_project.isHidden()
        got = []
        p.project_create.connect(lambda n, f: got.append((n, f)))
        p.project_continue.connect(lambda n, f: got.append((n, f)))
        # the button is not clickable while hidden, but guard the
        # signal-emission path too — a stray emit must not happen
        p._cta_clicked()
        assert got == [], "no CTA signal while the worker is out there"
        # release the worker; now the CTA is visible and fires
        _release(loader["w"])
        assert p.state() == "ready"
        assert not p.btn_project.isHidden()
        p._cta_clicked()
        assert got == [("2026 QK (443089)", None)], got
    finally:
        p.deleteLater()


def test_cta_reset_on_blank(qapp, tmp_path):
    # cancel() blanks the panel: the CTA hides and the stale name drops,
    # so the next object's intent does not inherit the previous one
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(chart_dir=tmp_path / "charts", for_post=True,
                    project_lookup=lambda n: None)
    try:
        p.show(FAKE_ELEMENT)
        assert not p.btn_project.isHidden()
        p.cancel()
        assert p.state() == "empty"
        assert p.name() is None
        assert p.btn_project.isHidden()
    finally:
        p.deleteLater()


# ---------------- i18n (D6) ----------------

def test_panel_strings_resolve_in_spanish(qapp, tmp_path, monkeypatch):
    # the compiled .qm (nightscribe_es.qm) must carry every string the
    # panel shows: install it, check the labels, remove it after.
    # ADR-014: base language in code is English; Spanish is a translation.
    from pathlib import Path
    from PySide6.QtCore import QTranslator
    from PySide6.QtWidgets import QLabel
    from nightscribe.config import config

    # The section cards do NOT go through the .qm: they pick their language
    # from the config, and under pytest the config file is the throwaway one
    # (no "language" key), so it falls back to "system" = the HOST locale.
    # This test says "Spanish", so it must ask for Spanish: it passed on the
    # author's es_ES machine and failed on the en-US Windows runner with
    # "section titles not translated: ['Orbit', ...]".
    monkeypatch.setitem(config._data, "language", "es")

    qm = (Path(__file__).parents[2] / "nightscribe" / "gui" / "i18n"
          / "nightscribe_es.qm")
    tr = QTranslator(qapp)
    assert tr.load(str(qm)), "nightscribe_es.qm must load"
    qapp.installTranslator(tr)
    try:
        from nightscribe.gui.overview import ObjectPanel
        p = ObjectPanel(chart_dir=tmp_path / "charts", for_post=True,
                        project_lookup=lambda n: None)
        assert p.btn_project.isHidden()
        p.show(FAKE_ELEMENT)
        # phase E single CTA, "create" face
        assert p.btn_project.text() == "\U0001f680  Crear proyecto"
        assert p.btn_project.toolTip() == (
            "Empezar un proyecto nuevo de este objeto")
        # "continue" face once the lookup finds an active project
        p2 = ObjectPanel(chart_dir=tmp_path / "charts", for_post=True,
                         project_lookup=lambda n: {"id": 1})
        p2.show(FAKE_ELEMENT)
        assert p2.btn_project.text() == "\u25b6  Continuar proyecto"
        assert p2.btn_project.toolTip() == (
            "Reanudar el proyecto activo de este objeto")
        p2.deleteLater()
        # Interfaz 1.7: the block keeps its own header row (ADR-057: the
        # sections under it are cards now, not a table)
        assert p._ui.lbl_params_title.text() == "Parámetros"
        assert p.chk_deep.text() == "A fondo"
        assert p.grp_charts.title() == "Gráficos"
        # ADR-057: the rows live in titled section cards, translated too
        assert any(c.lbl_title.text() == "Órbita"
                   for c in p._section_cards), \
            f"section titles not translated: {[c.lbl_title.text() for c in p._section_cards]!r}"
        # capture chips (D3) come from the context; show() paints them
        p.show(FAKE_ELEMENT, {"kind": "neo", "mag": 20.1,
                              "rate_arcsec_min": 12.4,
                              "window_start": "2026-11-04T18:20:00+00:00",
                              "window_end": "2026-11-04T21:10:00+00:00",
                              "hours_up": 2.8})
        tips = " ".join(c.toolTip()
                        for c in p.findChildren(QLabel) if c.toolTip())
        assert "Magnitud aparente prevista para esta noche" in tips
        assert "Tasa en el cielo esta noche" in tips
        assert "por encima del límite" in tips
        p.lbl_state.setText(p.tr("Not found: %1").replace(
            "%1", p.tr("the requested object")))
        assert p.lbl_state.text() == "No encontrado: el objeto solicitado"
        p.deleteLater()
    finally:
        qapp.removeTranslator(tr)


def test_panel_strings_resolve_in_english(qapp, tmp_path):
    # same smoke in English: the passthrough .qm must render the base
    # strings, so the ES and EN .qm never drift apart silently.
    from pathlib import Path
    from PySide6.QtCore import QTranslator

    qm = (Path(__file__).parents[2] / "nightscribe" / "gui" / "i18n"
          / "nightscribe_en.qm")
    tr = QTranslator(qapp)
    assert tr.load(str(qm)), "nightscribe_en.qm must load"
    qapp.installTranslator(tr)
    try:
        from nightscribe.gui.overview import ObjectPanel
        p = ObjectPanel(chart_dir=tmp_path / "charts", for_post=True,
                        project_lookup=lambda n: {"id": 1})
        p.show(FAKE_ELEMENT)
        assert p.btn_project.text() == "\u25b6  Continue project"
        assert p.btn_project.toolTip() == (
            "Resume the active project for this object")
        # Interfaz 1.7: the block is a frame with its own header row
        assert p._ui.lbl_params_title.text() == "Parameters"
        assert p.grp_charts.title() == "Charts"
        p.deleteLater()
    finally:
        qapp.removeTranslator(tr)


# ---------------- ready signal (Explore dialog sizing) ----------------

def test_ready_signal_in_metaobject(qapp):
    # ADR-029 phase 5+: the `ready` signal lets the Explore dialog
    # resize itself to the panel's content (see docs/PLANS/
    # explore-orbit-state.md, Slice 1).
    from PySide6.QtCore import QMetaMethod
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(chart_dir="/tmp/charts")
    mm = p.metaObject()
    names = [mm.method(i).name() for i in range(mm.methodCount())
             if mm.method(i).methodType() == QMetaMethod.Signal]
    assert "ready" in names, f"ready signal missing: {names}"
    p.deleteLater()


def test_ready_signal_fires_with_enriched_payload(panel, qapp):
    # When the panel reaches "ready" state via show(FAKE_ELEMENT),
    # the `ready` signal must fire exactly once and the payload
    # must be the enriched dict.
    events = []
    panel.ready.connect(lambda e: events.append(e))
    panel.show(FAKE_ELEMENT)
    assert panel.state() == "ready"
    assert len(events) == 1, f"ready should fire exactly once, got {len(events)}"
    assert events[0] == FAKE_ELEMENT


def test_ready_signal_not_fired_by_missing_state(panel, qapp):
    # A missing payload ({} from a fake loader) should leave the
    # panel in "missing" and never fire `ready`.
    from PySide6.QtCore import QMetaMethod
    events = []
    panel.ready.connect(lambda e: events.append(e))
    # force missing state directly
    panel._state_missing("SN1987AAA")
    assert panel.state() == "missing"
    assert events == [], "ready must not fire in missing state"


def test_resize_to_panel_content_uses_hint(qapp):
    # The helper is module-level so the Explore dialog (and any other
    # caller) can reuse it without dragging a whole panel fixture. The
    # width follows the hint (with the reading floor); the height adds the
    # window-chrome headroom so the panel's foot (the CTA) fits the viewport.
    from PySide6.QtWidgets import QWidget, QLabel
    from nightscribe.gui.overview import (resize_to_panel_content,
                                          _DLG_CHROME)
    from PySide6.QtCore import QSize

    class FixedHint(QWidget):
        def sizeHint(self):
            return QSize(990, 760)

    p = FixedHint()
    p.show()
    cont = QWidget()
    cont.show()
    resize_to_panel_content(cont, p)
    # hint width 990 > floor -> followed exactly.
    assert cont.size().width() == 990
    # height = hint + chrome (760 + 60) — the chrome headroom, above the floor.
    assert cont.size().height() == 760 + _DLG_CHROME
    p.deleteLater()
    cont.deleteLater()


def test_resize_to_panel_content_applies_floor(qapp):
    # A degenerate hint (0,0) must still give the dialog a usable, readable
    # minimum — wide enough for the text columns, tall enough to show the
    # whole panel — not collapse the window.
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.overview import (resize_to_panel_content,
                                           _MIN_READ_W, _MIN_READ_H)
    from PySide6.QtCore import QSize

    class ZeroHint(QWidget):
        def sizeHint(self):
            return QSize(0, 0)

    p = ZeroHint()
    p.show()
    cont = QWidget()
    cont.show()
    resize_to_panel_content(cont, p)
    assert cont.size().width() >= _MIN_READ_W, \
        f"got width {cont.size().width()} < {_MIN_READ_W}"
    assert cont.size().height() >= _MIN_READ_H, \
        f"got height {cont.size().height()} < {_MIN_READ_H}"
    p.deleteLater()
    cont.deleteLater()


def test_resize_to_panel_content_sizes_the_dialog_to_the_panel(qapp):
    # The Explore dialog must come out sized to the PANEL plus its chrome, so
    # the whole ready card is on screen instead of behind a fold. What this
    # test can assert anywhere is the helper's CONTRACT, not the geometry:
    # the chrome is a platform number (22 px on this machine, 193 on the
    # Windows runner, where the panel is taller too because the fonts are
    # wider) and comparing the panel's height against the viewport measured
    # the platform instead of the design. That comparison failed there for six
    # consecutive runs with the card perfectly fine, which is a lesson about
    # what a layout test can promise.
    import tempfile, pathlib
    from PySide6.QtWidgets import (QDialog, QScrollArea, QFrame, QVBoxLayout)
    from nightscribe.gui.overview import (ObjectPanel, resize_to_panel_content,
                                          _MIN_READ_W)
    tmp = pathlib.Path(tempfile.mkdtemp())
    p = ObjectPanel(chart_dir=tmp / "charts", for_post=True,
                    project_lookup=lambda _n: None)
    p.show(FAKE_ELEMENT)
    dlg = QDialog()
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(p)
    lay = QVBoxLayout(dlg)
    lay.addWidget(area)
    dlg.resize(720, 540)                # the Explore dialog's first size
    resize_to_panel_content(dlg, p)
    qapp.processEvents()
    # room for the whole panel, and never narrower than a comfortable column
    assert dlg.height() >= p.sizeHint().height(), \
        f"the dialog ({dlg.height()} px) is shorter than the panel " \
        f"({p.sizeHint().height()} px): the card would be cut off"
    assert dlg.width() >= _MIN_READ_W
    assert dlg.width() >= p.sizeHint().width()
    # the CTA the fold used to hide is there
    assert not p.btn_project.isHidden(), "CTA must be shown for for_post"
    dlg.deleteLater()
    p.deleteLater()


# ---------------- B4: SN light-curve slot + followup injection ----------------

FAKE_SN = {
    "type": "transient",
    "name": "SN2026b (NGC 1234)",
    "data": {"simbad": {"otype": "SN Ia"}},
}

_SN_POINTS = [
    {"mjd": 60600.0, "mag": 16.0, "err": 0.02, "filter": "Clear",
     "source": "manual"},
    {"mjd": 60603.0, "mag": 16.3, "err": 0.03, "filter": "Clear",
     "source": "survey:atlas"},
    {"mjd": 60606.0, "mag": 16.1, "err": None, "filter": "NIR",
     "source": "quicklook"},
]


def test_lightcurve_slot_renders_with_points(panel, monkeypatch):
    # followup points already present in the enriched dict -> the panel
    # puts a live LightCurveChart on its own tab.
    monkeypatch.setattr(panel, "_inject_followup",
                        lambda e: None)   # points come from the payload
    e = dict(FAKE_SN)
    e["data"] = dict(FAKE_SN["data"],
                     followup={"points": _SN_POINTS,
                               "sn_type": "SN Ia"})
    panel.show(e)
    from nightscribe.gui.widgets.lightcurve_widget import LightCurveChart
    tabs = [w for w in _chart_tabs(panel) if isinstance(w, LightCurveChart)]
    assert tabs, "no LightCurveChart tab"
    assert "lightcurve" in panel._slot_data
    assert len(panel._slot_data["lightcurve"]["points"]) == 3
    # click-rebuild works off the extracted data
    rebuilt = panel._rebuild_widget("lightcurve", panel._slot_data["lightcurve"])
    assert isinstance(rebuilt, LightCurveChart)
    assert len(rebuilt._points) == 3


def test_lightcurve_slot_absent_without_points(panel, monkeypatch):
    # no photometry (and injection neutralised) -> no lightcurve tab.
    monkeypatch.setattr(panel, "_inject_followup",
                        lambda e: None)
    panel.show(dict(FAKE_SN, data=dict(FAKE_SN["data"])))
    from nightscribe.gui.widgets.lightcurve_widget import LightCurveChart
    assert not [w for w in _chart_tabs(panel)
                if isinstance(w, LightCurveChart)]
    assert "lightcurve" not in panel._slot_data


def test_lightcurve_slot_folds_for_hads(panel, monkeypatch):
    # ADR-034 (D.4): a HADS payload with photometry folds its curve by the
    # catalog period and carries the schematic sawtooth
    monkeypatch.setattr(panel, "_inject_followup", lambda e: None)
    pts = [{"mjd": 60600.0 + 0.125 * i, "mag": 11.3 + 0.4 * (i % 2),
            "err": 0.02, "filter": "Clear", "source": "file"}
           for i in range(9)]
    e = {"type": "hads", "name": "CY Aqr",
         "data": {"hads": {"period_h": 1.46, "max": 11.3, "min": 11.8},
                  "followup": {"points": pts}}}
    panel.show(e)
    from nightscribe.gui.widgets.lightcurve_widget import LightCurveChart
    tabs = [w for w in _chart_tabs(panel) if isinstance(w, LightCurveChart)]
    assert tabs, "no LightCurveChart tab for the hads payload"
    chart = tabs[0]
    assert abs(chart._fold_p - 1.46 / 24.0) < 1e-9
    assert chart._schematic is not None          # the sawtooth is drawn
    # the extracted data rebuilds the same folded chart (click path)
    data = panel._slot_data["lightcurve"]
    rebuilt = panel._rebuild_widget("lightcurve", data)
    assert rebuilt._fold_p == chart._fold_p
    assert rebuilt._schematic is not None


def test_inject_followup_pulls_points_from_db(panel, tmp_db,
                                              monkeypatch):
    # project ctx with photometry in the (tmp) database -> the panel
    # pulls the points into data["followup"]["points"] while rendering.
    import time
    from nightscribe.core import followup
    now = time.time()
    tmp_db.execute(
        "INSERT INTO projects (kind, object_name, status, created, updated,"
        " context) VALUES (?, ?, 'active', ?, ?, '{}')",
        ("transient", "SN Test", now, now))
    tmp_db.commit()
    followup.add_point(tmp_db, 1, 60600.0, "Clear", 16.0, err=0.02)
    followup.add_point(tmp_db, 1, 60603.0, "Clear", 16.3,
                       source="survey:atlas")
    from nightscribe.core import db as _db
    monkeypatch.setattr(_db, "Database", lambda *a, **k: tmp_db)
    e = dict(FAKE_SN, data=dict(FAKE_SN["data"]))
    panel.show(e, ctx={"project_id": 1})
    pts = (e.get("data") or {}).get("followup", {}).get("points") or []
    assert len(pts) == 2
    assert {p["source"] for p in pts} == {"manual", "survey:atlas"}


def test_inject_followup_no_ctx_no_points(panel):
    # no project ctx -> transient renders but no lightcurve data lands.
    e = dict(FAKE_SN, data=dict(FAKE_SN["data"]))
    panel.show(e)
    assert not ((e.get("data") or {}).get("followup") or {}).get("points")



# ------------------------------------------------- VC.2: variable star

FAKE_VARIABLE = {
    "type": "variable", "name": "T CrB",
    "data": {"variable": {"var_type": "NR+ELL", "period_d": 227.5528,
                          "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8,
                          "amp": 8.8, "spectral": "M3III+WD",
                          "next_extremum": {"kind": "max", "mjd": 61250.0,
                                            "days": 3.0}},
             "campaign": {"name": "Campaña T CrB"}},
}


def test_variable_params_table(panel):
    panel.show(FAKE_VARIABLE)
    texts = [r[0] for r in _param_cells(panel)]
    assert any("Period" in t or "Periodo" in t for t in texts)
    assert any("Variable type" in t or "Tipo de variable" in t
               for t in texts)


def test_variable_chips(panel):
    panel.show(FAKE_VARIABLE)
    labels = [c.text() for c in panel.grp_chips.findChildren(QLabel)] \
        if hasattr(panel, "grp_chips") else []
    # fallback: walk the whole panel for chip labels
    if not labels:
        labels = [l.text() for l in panel.findChildren(QLabel)]
    # ADR-057: the period is a KPI tile (value + "Period" caption), the
    # campaign stays a flag pill
    assert any("227.6 d" in t for t in labels)
    assert any("Campaña T CrB" in t for t in labels)


def test_variable_lightcurve_extract_folds_with_epoch(panel):
    e = {"type": "variable", "name": "T CrB",
         "data": {"variable": dict(FAKE_VARIABLE["data"]["variable"]),
                  "followup": {"points": [
                      {"mjd": 61000.0, "filter": "V", "mag": 10.1,
                       "err": None, "source": "manual"},
                      {"mjd": 61010.0, "filter": "V", "mag": 10.3,
                       "err": None, "source": "manual"}]}}}
    out = panel._extract("lightcurve", e)
    assert out["fold_period_d"] == 227.5528
    assert out["epoch_mjd"] == 55828.4
    assert out["schematic"]
