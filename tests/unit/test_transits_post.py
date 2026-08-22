############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: transits, narrative and post
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

from nightscribe.core import coords, post, suggest, transits


def test_transit_times_arithmetic():
    # t0 + n*P must land inside the window exactly when expected
    from_jd = 2461274.0
    to_jd = 2461275.0
    times = transits.transit_times(2459554.20747, 0.73654635, from_jd, to_jd)
    assert times
    for t in times:
        assert from_jd - 1 < t < to_jd + 1
        # must sit on the arithmetic grid
        n = round((t - 2459554.20747) / 0.73654635)
        assert abs(t - (2459554.20747 + n * 0.73654635)) < 1e-6


def test_transit_window_tonight(exoclock_sample):
    # with the real two-planet sample, the function must not crash and
    # must only return events crossing tonight's darkness
    planets = []
    for key, p in exoclock_sample.items():
        planets.append({
            "name": p["name"], "star": p.get("star"),
            "ra": coords.ra_hms_to_deg(p["ra_j2000"]),
            "dec": coords.dec_dms_to_deg(p["dec_j2000"]),
            "t0": float(p["ephem_mid_time"]),
            "period": float(p["ephem_period"]),
            "depth_mmag": p.get("depth_r_mmag"),
            "duration_h": p.get("duration_hours"),
            "v_mag": p.get("v_mag"),
        })
    out = transits.transits_tonight(planets, 40.55, -3.37,
                                    datetime.date(2026, 8, 21))
    for t in out:
        assert t["egress"] > t["ingress"]


def _fake_enriched():
    return {
        "type": "small_body", "name": "TEST1",
        "data": {
            "sbdb": {"fullname": "TEST1", "phys": {"H": 20.0},
                     "elements": {"a": 1.2, "e": 0.3, "per": 480.0},
                     "orbit_code": "APO"},
            "family": "Apollo",
            "dist_now_km": 384400 * 8.0,
            "mag_now": 19.5,
        },
    }


def test_post_bilingual_and_tweet(fake_cfg):
    e = _fake_enriched()
    p = post.render_post(e, fake_cfg)
    assert "Apollo" in p["es"] or "Apollo" in p["en"]
    assert "#astronomia" in p["es"]
    assert "#astronomy" in p["en"]
    assert len(p["tweet"]) <= 280
    assert "TEST1" in p["es"] and "TEST1" in p["en"]


def test_post_save_outputs(tmp_path, fake_cfg):
    e = _fake_enriched()
    p = post.render_post(e, fake_cfg)
    written = post.save_outputs(p, tmp_path, "TEST1")
    for k in ("es", "en", "tweet"):
        assert written[k].exists()
        assert written[k].read_text(encoding="utf-8")


def test_visible_now(fake_cfg):
    # "right now" filter: only objects currently above min altitude
    import datetime as dt
    from nightscribe.core import planner
    when = dt.datetime(2026, 8, 21, 22, 0, tzinfo=dt.timezone.utc)
    jd = coords.jd_from_datetime(when)
    lst = coords.lst_degrees(jd, -3.37)
    targets = [
        {"id": "UP", "kind": "neo", "ra_deg": lst, "dec_deg": 40.55},
        {"id": "DOWN", "kind": "neo", "ra_deg": (lst + 180) % 360,
         "dec_deg": -40.0},
    ]
    now = planner.visible_now(targets, fake_cfg, when=when)
    assert [t["id"] for t, _a, _z in now] == ["UP"]
    assert now[0][1] > 89  # at the zenith


def test_post_unconfirmed_fallback(fake_cfg):
    # an unconfirmed PCCP/NEOCP candidate still gets a decent draft,
    # built from planner data only (no SBDB)
    from nightscribe.core import enrich
    fake = {"id": "PTEST", "kind": "pccp", "name": "PTEST", "mag": 21.2,
            "pccp_score": 90.0, "nobs": "23"}
    e = enrich.enrich("PTEST", fallback_target=fake)
    assert e and e.get("data")
    p = post.render_post(e, fake_cfg)
    assert "PCCP" in p["es"] or "PCCP" in p["en"]
    assert len(p["tweet"]) <= 280
