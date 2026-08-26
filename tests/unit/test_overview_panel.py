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
    # for the pure matplotlib slots (orbit, sky, families) without
    # touching the user's posts folder.
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
    # @return: the (param, value, meaning) strings of every visible row
    tbl = panel.tbl_params
    return [(tbl.item(r, 0).text(), tbl.item(r, 1).text(),
             tbl.item(r, 2).text()) for r in range(tbl.rowCount())]


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


def test_ready_params_table_has_meaningful_rows(panel):
    panel.show(FAKE_ELEMENT)
    assert not panel.grp_params.isHidden()
    rows = _param_cells(panel)
    assert len(rows) >= 3, f"expected a few rows, got {len(rows)}"
    meaning = [r[2] for r in rows]
    # the wide column: a real explanation, not an empty cell
    assert all(len(m) > 40 for m in meaning), \
        f"explanation column too short: {meaning!r}"
    # the basic rows only, in-depth hidden
    params = [r[0].lower() for r in rows]
    assert any("family" in p or "familia" in p for p in params)
    assert any("moid" in p for p in params)
    assert not any("semi-major" in p or "semieje" in p for p in params), \
        "deep rows leaked into the basic view"


def test_in_depth_toggle_adds_deep_rows(panel):
    panel.show(FAKE_ELEMENT)
    before = panel.tbl_params.rowCount()
    panel.chk_deep.setChecked(True)
    after = panel.tbl_params.rowCount()
    assert after > before, "checking «in depth» did not add rows"
    params = [r[0].lower() for r in _param_cells(panel)]
    assert any("semi-major" in p or "semieje" in p for p in params), \
        f"deep row missing after toggle: {params}"
    # and un-checking goes back
    panel.chk_deep.setChecked(False)
    assert panel.tbl_params.rowCount() == before


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


# ---------------- D2: charts grid ----------------
#
# build_charts is allowed to run real here (orbit/families/sky are pure
# matplotlib; only the "field" slot would call the cutouts source, and
# that fails offline so the slot shows its "why not" line). This keeps
# the test self-contained without faking disk output.

def test_charts_grid_present_when_ready(panel):
    panel.show(FAKE_ELEMENT)
    assert panel.state() == "ready"
    # the 2×2 group exists and is visible when we have an object
    assert not panel.grp_charts.isHidden()
    assert set(panel._labels) == {"orbit", "sky", "families", "field"}


def test_bound_element_orbit_slot_has_pixmap(panel):
    # FAKE_ELEMENT is a bound orbit with an ephemeris: orbit, sky and
    # families all render to real PNGs, so those slots carry a pixmap.
    panel.show(FAKE_ELEMENT)
    assert not panel._labels["orbit"].pixmap().isNull(), \
        "orbit slot should have rendered a chart"
    assert not panel._labels["sky"].pixmap().isNull(), \
        "sky slot should have rendered a chart"
    assert not panel._labels["families"].pixmap().isNull(), \
        "families slot should have rendered a chart"
    # only "field" needs the network (a reference cutout); it stays a
    # "why not" line instead of a blank
    assert panel._labels["field"].pixmap().isNull()
    assert panel._labels["field"].property("chart_png") is None
    assert "campo" in panel._labels["field"].text().lower() or \
        "field" in panel._labels["field"].text().lower()


def test_ready_scarce_slots_show_why_not(panel):
    # When build_charts cannot produce a slot, it shows a reason (the
    # "why not" line) instead of an empty box.
    panel.show(FAKE_UNCONFIRMED)
    orbit = panel._labels["orbit"]
    assert orbit.pixmap().isNull()
    t = orbit.text().lower()
    assert "no confirmado" in t or "unconfirmed" in t, \
        f"unconfirmed orbit message wrong: {t!r}"
    families = panel._labels["families"]
    assert families.pixmap().isNull()
    assert "familia" in families.text().lower() or \
        "family" in families.text().lower()


def test_missing_state_keeps_charts_hidden(panel):
    panel.show({})
    assert panel.state() == "missing"
    # the ready group is gone
    assert panel.grp_charts.isHidden()
    for lbl in panel._labels.values():
        assert lbl.isHidden()
        assert lbl.pixmap().isNull()


def test_charts_slot_uses_panel_title(panel):
    # When a chart lands, its click→zoom viewer title is the panel one.
    panel.show(FAKE_ELEMENT)
    assert panel._labels["orbit"].property("chart_png"), \
        "orbit slot should record its chart file for click→zoom"
    assert panel._labels["orbit"].property("chart_title"), \
        "orbit slot should carry a title for the chart viewer"


# ---------------- D3: capture / window block ----------------
#
# The block reads the project context snapshot (the numbers a capture plan
# actually uses): magnitude, apparent rate (NEO/PCCP only), max no-trail
# exposure (rate + camera profile) and the hours-above-horizon window. It
# omits whatever is missing, and hides itself entirely when it has nothing
# to show. No network: the SN fixture renders hook + bullets + "why not"
# slot lines entirely offline.

def _chip_texts(panel):
    # @return: the visible chip labels, in order (skips the trailing stretch)
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
    # An SN: mag + window apply, but the rate and max-exposure chips are
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
    assert not panel.row_capture.isHidden()
    chips = _chip_texts(panel)
    assert any("14.2" in c for c in chips), f"mag chip missing: {chips!r}"
    assert any("21:00" in c and "23:30" in c for c in chips), \
        f"window chip missing: {chips!r}"
    assert any("2.5 h" in c for c in chips), f"hours chip missing: {chips!r}"
    assert not any("″/min" in c for c in chips), \
        f"rate must be omitted for an SN: {chips!r}"
    assert not any("max" in c.lower() for c in chips), \
        f"exposure must be omitted for an SN: {chips!r}"


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
    assert not panel.row_capture.isHidden()
    chips = _chip_texts(panel)
    # magnitude
    assert any("19.5" in c for c in chips), f"mag chip missing: {chips!r}"
    # rate ″/min
    assert any("″/min" in c for c in chips), f"rate chip missing: {chips!r}"
    # window HH:MM–HH:MM
    assert any("21:00" in c and "23:30" in c for c in chips), \
        f"window chip missing: {chips!r}"
    # hours above
    assert any("2.5 h" in c for c in chips), f"hours chip missing: {chips!r}"


def test_capture_block_neo_max_exposure_present(panel):
    # A NEO with a rate and a complete camera profile gets a max no-trail
    # exposure chip (the whole point of the camera profile for NEOs).
    from nightscribe.config import config
    saved = (config.get("pixel_um"), config.get("focal_mm"))
    config._data["pixel_um"] = 3.76
    config._data["focal_mm"] = 2000.0
    try:
        panel.show(FAKE_ELEMENT, {"kind": "neo", "mag": 19.5,
                                  "rate_arcsec_min": 12.0})
    finally:
        config._data["pixel_um"], config._data["focal_mm"] = saved
    chips = _chip_texts(panel)
    assert any("max" in c.lower() for c in chips), \
        f"max-exposure chip missing for a NEO with a rate: {chips!r}"
    # and the rate chip is present alongside it
    assert any("″/min" in c for c in chips), f"rate chip missing: {chips!r}"


def test_capture_block_empty_ctx_does_not_break(panel):
    # show() with a valid payload and an empty/None context: the block hides
    # itself instead of raising, and the rest of the panel stays ready.
    panel.show(FAKE_ELEMENT, {})
    assert panel.state() == "ready"
    assert panel.row_capture.isHidden()
    assert _chip_texts(panel) == []
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
    assert not panel.row_capture.isHidden()
    chips = _chip_texts(panel)
    assert any("20.2" in c for c in chips), f"mag chip missing: {chips!r}"
    assert any("20:00" in c and "22:00" in c for c in chips), \
        f"window chip missing: {chips!r}"
    assert any("2.0 h" in c for c in chips), f"hours chip missing: {chips!r}"
    assert not any("″/min" in c for c in chips), \
        f"rate must be omitted without a rate: {chips!r}"
    assert not any("max" in c.lower() for c in chips), \
        f"exposure must be omitted without a rate: {chips!r}"
