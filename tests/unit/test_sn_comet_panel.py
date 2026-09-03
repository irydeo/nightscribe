############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - SN/comet panel degradation (ADR-027, offline)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offline regression for ADR-027.

When the external sources (SIMBAD for transients, SBDB for comets) do not
know an object, the panel must still tell a real story from whatever the
planner already had (host, type, magnitude, coordinates, safe window)
instead of falling back to a generic hook and empty bullets.

All sources are stubbed to fail so the tests run with no network, and the
panel is driven offscreen the same way as test_overview_panel.py does.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ------------- shared fixtures -------------

# A fresh supernova row straight from the Rochester list (planner._sn_targets
# shape): SIMBAD does not know it, so we lean on these planner fields.
SN_TARGET = {
    "id": "AT2026yvy", "kind": "sn", "name": "AT2026yvy",
    "mag": 16.4, "ra_deg": 301.143, "dec_deg": 62.644,
    "sn_type": "II", "host": "NGC 5128", "disc_date": "2026/08/20",
    "safe_window": "2026-08-29T03:00:00|2026-08-29T05:30:00",
    "best_time": "2026-08-29T04:15:00",
    "window_start": "2026-08-29T02:00:00",
    "window_end": "2026-08-29T06:00:00",
    "hours_up": 3.5, "duration_s": 3600,
}

# A comet candidate the MPC is still tracking (planner._comet_targets shape):
# SBDB does not resolve the short name, so it is an "unconfirmed" comet.
COMET_TARGET = {
    "id": "C2026F1000", "kind": "comet", "name": "C/2026 F1000 (example)",
    "mag": 14.8, "ra_deg": 45.0, "dec_deg": +12.0,
    "perihelion_date": "2026-09-05", "delta_au": 0.9,
    "safe_window": "2026-08-29T03:00:00|2026-08-29T05:30:00",
    "best_time": "2026-08-29T04:15:00",
    "window_start": "2026-08-29T02:00:00",
    "window_end": "2026-08-29T06:00:00",
    "hours_up": 3.5, "duration_s": 3600,
}


@pytest.fixture()
def no_sources(monkeypatch):
    """Fail every external lookup so enrichment leans on the planner context."""
    from nightscribe.core.enrich import simbad, sbdb, neofixer
    monkeypatch.setattr(simbad, "query_id", lambda *a, **k: None)
    monkeypatch.setattr(simbad, "query_around_galaxy", lambda *a, **k: None)
    monkeypatch.setattr(sbdb, "get", lambda *a, **k: None)
    monkeypatch.setattr(neofixer, "orbit", lambda *a, **k: None)


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
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(chart_dir=tmp_path / "charts")
    yield p
    p.deleteLater()


def _hook_text(e):
    from nightscribe.core import narrative
    return narrative.hook(e)["es"]


# ------------- enrich: transient (route A: SIMBAD unknown) -------------

def test_enrich_transient_from_context(no_sources):
    # SIMBAD knows nothing: the planner row still gives us host/type/mag/coords
    from nightscribe.core import enrich
    e = enrich.enrich("AT2026yvy", fallback_target=SN_TARGET)
    assert e["type"] == "transient"
    d = e["data"]
    assert (d.get("host") or {}).get("name") == "NGC 5128"
    assert d.get("otype") == "II"
    assert d.get("mag") == 16.4
    assert d.get("ra_deg") == 301.143 and d.get("dec_deg") == 62.644
    assert d.get("disc_date") == "2026/08/20"
    # the safe window travels into the data dict (bullet + sky chart)
    assert d.get("safe_window") == SN_TARGET["safe_window"]
    # the hook reads a real story, never the generic follow-up
    hook = _hook_text(e)
    assert "NGC 5128" in hook
    assert "Seguimiento de un fenómeno transitorio" not in hook


def test_enrich_transient_keeps_simbad_over_context(no_sources, monkeypatch):
    # when SIMBAD does answer, it wins over the context (never clobbered)
    from nightscribe.core.enrich import simbad
    monkeypatch.setattr(
        simbad, "query_id", lambda *a, **k:
        {"otype": "Ia", "ra": "18 00 00.0", "dec": "+30 00 00.0",
         "vmag": 15.0})
    monkeypatch.setattr(
        simbad, "query_around_galaxy", lambda *a, **k:
        {"name": "M87", "z": 0.0043})
    from nightscribe.core import enrich
    e = enrich.enrich("SN2023ixf", fallback_target=SN_TARGET)
    d = e["data"]
    assert (d.get("host") or {}).get("name") == "M87"           # SIMBAD host
    assert (d.get("simbad") or {}).get("otype") == "Ia"         # SIMBAD type
    assert d.get("dist_mly")                                     # z -> distance
    # context filled the gaps SIMBAD left (magnitude fallback)
    assert d.get("mag") == 16.4 or d.get("simbad", {}).get("vmag") == 15.0


# ------------- enrich: comet (route B: SBDB unknown) -------------

def test_enrich_comet_unconfirmed_from_context(no_sources):
    from nightscribe.core import enrich
    e = enrich.enrich("2026 F1000", fallback_target=COMET_TARGET)
    assert e["type"] in ("comet", "small_body", "neo")
    d = e["data"]
    assert d.get("unconfirmed"), "comet without SBDB is the unconfirmed path"
    # the hook names the comet, not "este objeto" / generic follow-up
    hook = _hook_text(e)
    assert "C/2026 F1000 (example)" in hook
    # bullets carry the perihelion (bilingual) — the "candidate" bullet only
    # appears when the planner had no perihelion, so do not require it here
    from nightscribe.core import narrative
    bullets = narrative.fact_bullets(e)
    assert any("2026-09-05" in b["es"] or "2026-09-05" in b["en"]
               for b in bullets)


# ------------- narrative: bullets + hook for a degraded SN -------------

def test_hook_comet_candidate_without_perihelion():
    # a comet candidate the planner has no perihelion for: the hook is the
    # candidate follow-up and the bullets say we are looking for a coma/tail
    from nightscribe.core import narrative
    t = dict(COMET_TARGET, perihelion_date=None)
    e = {"type": "comet", "name": "C/2026 F1000 (example)",
         "data": {"unconfirmed": t}}
    h = narrative.hook(e)["es"]
    assert "candidato" in h.lower() and "C/2026 F1000 (example)" in h
    bullets = narrative.fact_bullets(e)
    assert any("candidato" in b["es"].lower() or "candidate" in b["en"].lower()
               for b in bullets)


def test_fact_bullets_transient_safe_window():
    # an SN with a safe window gets the same window bullet the others do
    from nightscribe.core import narrative
    e = {"type": "transient", "name": "AT2026yvy",
         "data": dict((SN_TARGET),
                      host={"name": "NGC 5128"}, otype="II")}
    es = " ".join(b["es"] for b in narrative.fact_bullets(e))
    assert "03:00–05:30 UTC" in es
    assert "NGC 5128" in es and "II" in es


def test_hook_unconfirmed_sn_mentions_host_and_type():
    # a still-unconfirmed SN (planner kind "sn", no SIMBAD) reads as an SN,
    # names its host and type — not the generic "object still unconfirmed"
    from nightscribe.core import narrative
    e = {"type": "sn", "name": "AT2026yvy", "data": {"unconfirmed": SN_TARGET}}
    h = narrative.hook(e)["es"]
    assert "supernova" in h.lower()
    assert "NGC 5128" in h
    assert "tipo II" in h
    assert "Objeto aún sin confirmar" not in h


# ------------- gui: the panel renders hook + bullets + sky -------------

def test_panel_sn_sky_chart_offline(panel, no_sources):
    # degraded SN end-to-end through the real panel: hook, bullets, chips and
    # a real sky PNG from the planner coordinates (the field slot is absent
    # because there is no reference cutout and no SIMBAD ra/dec either).
    from nightscribe.core import enrich
    e = enrich.enrich("AT2026yvy", fallback_target=SN_TARGET)
    panel.show(e, SN_TARGET)
    assert panel.state() == "ready"
    # hook is the real story, not the generic one
    assert "NGC 5128" in panel.lbl_hook.text()
    # bullets mention host + type
    facts = panel.lbl_facts.text()
    assert "NGC 5128" in facts and "II" in facts
    # the sky slot is now a live vector widget (ADR-029) with a non-empty scene
    from nightscribe.gui.widgets.sky_widget import SkyChart
    sky = next((item.widget() for item in [panel._grid.itemAt(r * 2 + c) for r in range(2) for c in range(2)] if item and isinstance(item.widget(), SkyChart)), None)
    assert sky is not None, "no SkyChart widget found in the grid"
    assert not sky.isHidden()
    assert sky.view.scene().items(), "sky scene is empty"
    # capture chips: magnitude + the safe window the planner computed
    from PySide6.QtWidgets import QLabel
    chips = " ".join(w.text()
                     for w in panel.row_capture.findChildren(QLabel)
                     if w.text().strip())
    assert "16.4" in chips
    assert "03:00" in chips
