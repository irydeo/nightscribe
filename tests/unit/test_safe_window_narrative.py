############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: planned safe window (narrative + planner helper)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

from nightscribe.core import narrative, planner

SAMPLE = "docs/limits-sample.hrz"
DATE = datetime.date(2026, 8, 28)
RA, DEC = 45.0, 0.0


def _cfg(fake_cfg):
    fake_cfg._v["horizon_file"] = SAMPLE
    return fake_cfg


def _planned_target(fake_cfg, duration_s):
    # @return: a planner target dict with a computed safe_window
    vis = planner._visibility(RA, DEC, fake_cfg.get("lat"),
                              fake_cfg.get("lon"), DATE,
                              _horizon_from(fake_cfg), 0.0, duration_s)
    return vis


def _horizon_from(cfg):
    from nightscribe.core import horizon
    h = horizon.from_config(cfg)
    return h


# --- planner.safe_window_for: same maths as build_tonight ---

def test_safe_window_for_fits(fake_cfg):
    cfg = _cfg(fake_cfg)
    sw = planner.safe_window_for(RA, DEC, cfg, 3600, DATE)
    assert sw["fits"] is True
    assert sw["safe_window"] is not None
    s0, s1 = sw["safe_window"].split("|")
    start = datetime.datetime.fromisoformat(s0)
    end = datetime.datetime.fromisoformat(s1)
    assert (end - start).total_seconds() >= 3600
    lat = datetime.datetime.fromisoformat(sw["latest_safe_start"])
    assert lat == end - datetime.timedelta(seconds=3600)
    assert start <= lat <= end
    assert sw["best_time"] is not None
    b = datetime.datetime.fromisoformat(sw["best_time"])
    assert start <= b <= end


def test_safe_window_for_does_not_fit(fake_cfg):
    # 72 h cannot fit tonight: fits is False, safe_window is None
    cfg = _cfg(fake_cfg)
    sw = planner.safe_window_for(RA, DEC, cfg, 72 * 3600, DATE)
    assert sw["fits"] is False
    assert sw["safe_window"] is None
    assert sw["duration_s"] == 72 * 3600


# --- narrative.safe_window_text: the bilingual prose ---

def test_narrative_safe_window_text():
    t = {
        "safe_window": "2026-08-28T04:00:00|2026-08-28T07:00:00",
        "best_time": "2026-08-28T04:30:00",
        "window_start": "2026-08-28T03:00:00",
        "window_end": "2026-08-28T08:00:00",
    }
    out = narrative.safe_window_text(t, duration_s=3600)
    assert out is not None
    assert "04:00–07:00 UTC" in out["es"]
    assert "04:00–07:00 UTC" in out["en"]
    assert "04:30" in out["es"]
    assert "04:30" in out["en"]
    # 5 h window is enough for 1 h: no "does not fit" warning
    assert "no cabe" not in out["es"]
    assert "does not fit" not in out["en"]


def test_narrative_safe_window_text_does_not_fit():
    t = {
        "safe_window": "2026-08-28T04:00:00|2026-08-28T05:00:00",
        "best_time": "2026-08-28T04:30:00",
        "window_start": "2026-08-28T04:00:00",
        "window_end": "2026-08-28T05:30:00",
    }
    out = narrative.safe_window_text(t, duration_s=7200)
    assert out is not None
    assert "no cabe" in out["es"]
    assert "does not fit" in out["en"]


def test_narrative_safe_window_text_none_when_absent():
    assert narrative.safe_window_text({}) is None
    assert narrative.safe_window_text({"best_time": "2026-08-28T04:00:00"}) \
        is None


# --- fact_bullets picks up the safe window for confirmed + unconfirmed ---

def test_fact_bullets_with_safe_window_small_body():
    e = {
        "type": "small_body",
        "data": {
            "safe_window": "2026-08-28T04:00:00|2026-08-28T07:00:00",
            "best_time": "2026-08-28T04:30:00",
        },
    }
    bullets = narrative.fact_bullets(e)
    assert any("04:00–07:00 UTC" in b.get("es", "") for b in bullets)


def test_fact_bullets_with_safe_window_unconfirmed():
    e = {
        "type": "neo",
        "data": {
            "unconfirmed": {
                "safe_window": "2026-08-28T04:00:00|2026-08-28T07:00:00",
                "best_time": "2026-08-28T04:30:00",
            }
        },
    }
    bullets = narrative.fact_bullets(e)
    assert any("04:00–07:00 UTC" in b.get("es", "") for b in bullets)


def test_fact_bullets_without_safe_window_unchanged():
    e = {"type": "small_body", "data": {
        "mag_now": 18.0, "dist_now_km": 2_500_000,
    }}
    bullets = narrative.fact_bullets(e)
    # none of them mention a safe window
    assert not any("segura" in b.get("es", "").lower() for b in bullets)
