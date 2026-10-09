############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the object brief (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""`core/object_brief.build_brief` — the fact sheet the writer (and the
grounded assistant) reads. Pure local data over a temp database: the whole
point is that it carries the observer's OWN work, not just the catalogue
entry, and that every figure arrives with its why (ADR-058)."""

import pytest

from nightscribe.core import followup, object_brief, project
from nightscribe.core.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "t.db"))


@pytest.fixture
def cfg():
    class Cfg:
        _v = {"observatory_name": "Test Observatory", "mpc_code": "Z41",
              "aperture_inches": 10.0, "ai_temperature": 0.7}
        def get(self, k, d=None):
            return self._v.get(k, d)
    return Cfg()


def _sn_with_points(db, context=None):
    p = project.create(db, "sn", "SN 2026abc",
                       context or {"kind": "sn", "sn_type": "SN Ia",
                                   "mag": 15.0, "host": "NGC 4414"})
    sid = followup.create_session(db, p["id"], obs_date="2026-09-30")
    # three nights, fading: 15.0 -> 15.3 -> 15.6
    for i, m in enumerate((15.0, 15.3, 15.6)):
        followup.add_point(db, p["id"], 60900.0 + i, "Clear", m, err=0.03,
                           session_id=sid)
    return p


def test_brief_has_identity_and_observatory(db, cfg):
    p = _sn_with_points(db)
    b = object_brief.build_brief(p, db, lang="es", cfg=cfg)
    assert b["object"]["name"] == "SN 2026abc"
    assert b["object"]["kind"] == "sn"
    assert b["observatory"]["mpc"] == "Z41"


def test_brief_carries_the_observers_own_work(db, cfg):
    # The half the old post never saw: the visits, the curve, the verdict.
    p = _sn_with_points(db)
    b = object_brief.build_brief(p, db, lang="es", cfg=cfg)
    obs = b["observations"]
    assert obs["n_points"] == 3
    assert obs["n_nights"] == 3
    assert obs["filters"] == ["Clear"]
    assert obs["latest"]["mag"] == pytest.approx(15.6)
    assert obs["campaign"]["points"] == 3
    # a monotone fade: the slope is positive (mag grows = fainter)
    assert obs["campaign"]["slope_mag_per_day"] > 0
    assert obs["sessions"][0]["date"] == "2026-09-30"


def test_brief_without_enrichment_omits_object_facts(db, cfg):
    # No enriched dict -> no half-told figures (the writer is told to use
    # only what it finds, never to fill the gap itself).
    p = _sn_with_points(db)
    b = object_brief.build_brief(p, db, lang="es", cfg=cfg)
    assert b["object_facts"] == []


def test_explained_facts_come_from_the_card_dispatch():
    # A transient: the type must arrive WITH its meaning, not as a bare code
    # (ADR-058), reusing the very same rows the object card shows.
    enriched = {"type": "transient", "name": "SN 2026abc",
                "data": {"otype": "SN Ia", "mag": 15.0,
                         "host": {"name": "NGC 4414"}}}
    rows = object_brief.explained_facts(enriched)
    assert rows, "the transient dispatch should yield explained rows"
    assert any("Ia" in str(r.get("value")) for r in rows)
    assert all(r.get("es") and r.get("en") for r in rows)


def test_text_renders_the_sections_it_has(db, cfg):
    p = _sn_with_points(db)
    b = object_brief.build_brief(p, db, lang="es", cfg=cfg)
    txt = object_brief.to_text(b)
    assert "SN 2026abc" in txt
    assert "OUR OBSERVATIONS" in txt
    assert "mag 15.60" in txt
    assert "MPC Z41" in txt


def test_text_shows_the_night_with_its_why(db, cfg):
    p = project.create(db, "neo", "2026 QK", {
        "kind": "neo", "mag": 19.0,
        "safe_window": "2026-10-09T21:10:00+00:00|2026-10-09T23:40:00+00:00",
        "best_time": "2026-10-09T21:40:00+00:00", "hours_up": 3.5,
        "max_alt": 62.4})
    b = object_brief.build_brief(p, db, lang="es", cfg=cfg)
    txt = object_brief.to_text(b)
    assert "21:10–23:40 UTC" in txt
    assert "Maximum altitude: 62.4" in txt
    # the altitude figure never travels alone: its why comes from explain
    assert b["night"]["max_alt_why"]


def test_empty_project_is_honest_not_invented(db, cfg):
    p = project.create(db, "comet", "29P", {"kind": "comet"})
    b = object_brief.build_brief(p, db, lang="en", cfg=cfg)
    assert b["observations"].get("n_points") is None
    assert b["object_facts"] == []
    # the render still works and says nothing it does not know
    assert "29P" in object_brief.to_text(b)


# ---------------- the long report's extra context (2026-10-09) ---------

def test_long_brief_adds_the_analysis_campaign_and_gallery(db, cfg):
    p = _sn_with_points(db, context={"kind": "sn", "sn_type": "SN Ia",
                                     "period_d": 12.3, "period_method": "LS",
                                     "period_fap": 0.001})
    b = object_brief.build_brief(
        p, db, lang="es", cfg=cfg, long=True,
        gallery=[{"key": "lightcurve", "name": "SN_lightcurve.png",
                  "caption": {"es": "Curva", "en": "Curve"}}])
    assert b["analysis"]["period"]["days"] == 12.3
    assert b["analysis"]["period"]["why"]
    assert b["gallery"][0]["name"] == "SN_lightcurve.png"
    txt = object_brief.to_text(b, deep=True)
    assert "THE ANALYSIS" in txt
    assert "IMAGES WE MADE" in txt
    assert "SN_lightcurve.png" in txt


def test_short_brief_has_no_analysis_or_gallery(db, cfg):
    p = _sn_with_points(db)
    b = object_brief.build_brief(p, db, lang="es", cfg=cfg)
    assert "analysis" not in b
    assert "gallery" not in b


def test_deep_facts_are_kept_only_for_the_long_report(db, cfg):
    p = _sn_with_points(db)
    enriched = {"type": "small_body", "name": "2026 QK",
                "data": {"sbdb": {"elements": {"a": 1.35, "e": 0.4, "i": 6.2,
                                               "q": 0.81, "Q": 1.89},
                                  "phys": {"H": 20.5, "diameter": 1.1},
                                  "moid": 0.028}}}
    b = object_brief.build_brief(p, db, enriched=enriched, lang="es",
                                 cfg=cfg, long=True)
    assert any(f.get("level") == "deep" for f in b["object_facts"]), \
        "the fixture should carry deep rows"
    short = object_brief.to_text(b)
    deep = object_brief.to_text(b, deep=True)
    assert len(deep) > len(short)
