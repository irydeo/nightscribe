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
    # t0 + n*P must land inside the window exactly when expected — the
    # contract is mid-times strictly within [from_jd, to_jd]
    from_jd = 2461274.0
    to_jd = 2461275.0
    times = transits.transit_times(2459554.20747, 0.73654635, from_jd, to_jd)
    assert times
    for t in times:
        assert from_jd <= t <= to_jd
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


def test_transits_threshold_fn_rejects_and_accepts(exoclock_sample):
    # A 90-degree horizon rejects everything; a 0-degree horizon accepts
    # what the flat min_alt check would too (threshold_fn replaces it).
    from nightscribe.core import horizon
    planets = []
    for key, p in exoclock_sample.items():
        planets.append({
            "name": p["name"], "ra": coords.ra_hms_to_deg(p["ra_j2000"]),
            "dec": coords.dec_dms_to_deg(p["dec_j2000"]),
            "t0": float(p["ephem_mid_time"]),
            "period": float(p["ephem_period"]),
            "duration_h": p.get("duration_hours"),
            "v_mag": p.get("v_mag"),
        })
    date = datetime.date(2026, 8, 21)
    out = transits.transits_tonight(planets, 40.55, -3.37, date,
                                    threshold_fn=horizon.FlatHorizon(90).alt_at)
    assert out == []
    out = transits.transits_tonight(planets, 40.55, -3.37, date,
                                    threshold_fn=horizon.FlatHorizon(0).alt_at)
    for t in out:
        assert t["max_alt"] >= 0.0


def _synth_transit_planet(dec_deg):
    # A synthetic planet whose star transits at midnight (RA == LST), so
    # the star is on the meridian at mid-transit — alt = 90 - |lat - dec|,
    # the exact max. @return: (planets, lat, lon, date)
    lat, lon = 40.55, -3.37
    midnight = datetime.datetime(2026, 8, 22, 0, 0,
                                 tzinfo=datetime.timezone.utc)
    lst = coords.lst_degrees(coords.jd_from_datetime(midnight), lon)
    planets = [{
        "name": "SYN b", "star": "SYN",
        "ra": lst, "dec": dec_deg,
        "t0": coords.jd_from_datetime(midnight),
        "period": 1.0,
        "duration_h": 2.0,
        "v_mag": 8.0,
    }]
    return planets, lat, lon, datetime.date(2026, 8, 21)


def test_transit_rejected_when_star_never_rises():
    # dec -80 from lat +40.55 peaks 39 degrees BELOW the horizon: the
    # mid-transit gate must drop this transit no matter the fallback
    # (the old "one of three samples above" gate admitted it).
    from nightscribe.core import horizon
    planets, lat, lon, date = _synth_transit_planet(-80.0)
    out = transits.transits_tonight(planets, lat, lon, date,
                                    threshold_fn=horizon.FlatHorizon(30.0).alt_at)
    assert out == []


def test_transit_mid_gate_applies_margin():
    # Meridian altitude exactly 31.0 degrees: kept against a 30-degree
    # floor, rejected when the margin pushes the requirement to 32.
    from nightscribe.core import horizon
    planets, lat, lon, date = _synth_transit_planet(-18.45)
    out = transits.transits_tonight(planets, lat, lon, date,
                                    threshold_fn=horizon.FlatHorizon(30.0).alt_at)
    assert out
    assert all(t["max_alt"] >= 30.5 for t in out)
    out = transits.transits_tonight(planets, lat, lon, date,
                                    threshold_fn=horizon.FlatHorizon(30.0).alt_at,
                                    margin=2.0)
    assert out == []


def test_transit_targets_forwards_margin(monkeypatch):
    # The planner must pass the horizon margin into the gate, so an
    # invisible star never leaks into the night list (end-to-end wiring).
    from nightscribe.core import horizon, planner
    from nightscribe.core.sources import exoclock
    planets, lat, lon, date = _synth_transit_planet(-80.0)
    monkeypatch.setattr(exoclock, "planets", lambda: planets)
    hor = horizon.FlatHorizon(30.0)
    assert planner._transit_targets(lat, lon, date, hor, 20.0,
                                    margin=2.0) == []


def test_transit_aperture_gate_drops_too_big_a_scope():
    # object-card plan, subplan 6: ExoClock says this transit needs a 71"
    # telescope; a 10" rig never sees it leave the list, an 80" one does
    from nightscribe.core import horizon
    planets, lat, lon, date = _synth_transit_planet(-18.45)
    planets[0]["min_telescope_in"] = 71.0
    out = transits.transits_tonight(
        planets, lat, lon, date,
        threshold_fn=horizon.FlatHorizon(30.0).alt_at, aperture_in=10.0)
    assert out == [], "a 71\"-class transit must not reach a 10\" tonight list"
    out = transits.transits_tonight(
        planets, lat, lon, date,
        threshold_fn=horizon.FlatHorizon(30.0).alt_at, aperture_in=80.0)
    assert out, "the same transit must pass with an 80\" aperture"


def test_transit_aperture_gate_keeps_unknowns():
    # no min_telescope datum is NOT a reason to discard (ADR-025 spirit:
    # hard only where the catalogue speaks)
    from nightscribe.core import horizon
    planets, lat, lon, date = _synth_transit_planet(-18.45)
    assert planets[0].get("min_telescope_in") is None
    out = transits.transits_tonight(
        planets, lat, lon, date,
        threshold_fn=horizon.FlatHorizon(30.0).alt_at, aperture_in=4.0)
    assert out, "a transit without aperture data must survive"


def test_transit_targets_forwards_aperture(monkeypatch):
    # end-to-end wiring: the planner passes the gate down (same pattern
    # as test_transit_targets_forwards_margin)
    from nightscribe.core import horizon, planner
    from nightscribe.core.sources import exoclock
    planets, lat, lon, date = _synth_transit_planet(-18.45)
    planets[0]["min_telescope_in"] = 71.0
    monkeypatch.setattr(exoclock, "planets", lambda: planets)
    hor = horizon.FlatHorizon(30.0)
    assert planner._transit_targets(lat, lon, date, hor, 20.0,
                                    aperture_in=10.0) == []
    out = planner._transit_targets(lat, lon, date, hor, 20.0,
                                   aperture_in=80.0)
    assert out


def test_transit_aperture_helper_toggle_and_fallback():
    # the Settings toggle decides: off -> no gate; on -> the configured
    # aperture; missing/garbage aperture -> no gate (never discard blind)
    from nightscribe.core import planner
    cfg = {"transit_scope_filter": True, "aperture_inches": 10.0}
    assert planner._transit_aperture(cfg) == 10.0
    assert planner._transit_aperture(
        {**cfg, "transit_scope_filter": False}) is None
    assert planner._transit_aperture(
        {"transit_scope_filter": True, "aperture_inches": None}) is None
    assert planner._transit_aperture(
        {"transit_scope_filter": True, "aperture_inches": "junk"}) is None


def test_visibility_safe_span(fake_cfg):
    # A star transiting at midnight (RA == LST at midnight) from the
    # north at dec +30, against a flat 30-degree horizon, with a planned
    # 2 h session: safe window + best time + consistent latest start.
    from nightscribe.core import horizon, planner
    lat, lon = 40.55, -3.37
    date = datetime.date(2026, 8, 21)
    midnight = datetime.datetime(2026, 8, 22, 0, 0,
                                 tzinfo=datetime.timezone.utc)
    lst = coords.lst_degrees(coords.jd_from_datetime(midnight), lon)
    hor = horizon.FlatHorizon(30.0)
    v = planner._visibility(lst, 30.0, lat, lon, date, hor, 0.0,
                            duration_s=7200)
    assert v["safe_window"] is not None
    s_start, s_end = (datetime.datetime.fromisoformat(x)
                      for x in v["safe_window"].split("|"))
    best = datetime.datetime.fromisoformat(v["best_time"])
    latest = datetime.datetime.fromisoformat(v["latest_safe_start"])
    assert s_start <= best <= latest <= s_end
    assert (s_end - s_start) >= datetime.timedelta(seconds=7200)


def test_visibility_no_session_gives_meridian(fake_cfg):
    # Without a planned session, best_time is the meridian crossing.
    from nightscribe.core import horizon, planner
    lat, lon = 40.55, -3.37
    date = datetime.date(2026, 8, 21)
    midnight = datetime.datetime(2026, 8, 22, 0, 0,
                                 tzinfo=datetime.timezone.utc)
    lst = coords.lst_degrees(coords.jd_from_datetime(midnight), lon)
    hor = horizon.FlatHorizon(30.0)
    v = planner._visibility(lst, 30.0, lat, lon, date, hor, 0.0)
    assert v["safe_window"] is None
    # meridian crossing = peak altitude = max_time
    assert v["best_time"] == v["max_time"]
    assert v["window_start"] is not None and v["window_end"] is not None


def test_visibility_never_rises(fake_cfg):
    # A far-southern target (dec -80 from the north) never clears the
    # 30-degree floor → no window, no best time, zero hours up.
    from nightscribe.core import horizon, planner
    lat, lon = 40.55, -3.37
    date = datetime.date(2026, 8, 21)
    hor = horizon.FlatHorizon(30.0)
    v = planner._visibility(100.0, -80.0, lat, lon, date, hor, 0.0)
    assert v["window_start"] is None
    assert v["best_time"] is None
    assert v["hours_up"] == 0.0


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


def test_post_markdown_references_charts(tmp_path, fake_cfg):
    # the ES/EN drafts must reference every chart with a relative
    # markdown link, so the file is ready to publish on a web page
    e = _fake_enriched()
    p = post.render_post(e, fake_cfg)
    charts = {"orbit": tmp_path / "TEST1_orbit.png",
              "sky": tmp_path / "TEST1_sky.png"}
    written = post.save_outputs(p, tmp_path, "TEST1", e=e, charts=charts)
    es = written["es"].read_text(encoding="utf-8")
    en = written["en"].read_text(encoding="utf-8")
    assert "## Galería" in es and "## Gallery" in en
    assert "TEST1_orbit.png" in es and "TEST1_orbit.png" in en
    assert "TEST1_sky.png" in es and "TEST1_sky.png" in en
    assert "![Órbita" in es and "![Orbit" in en


def test_post_markdown_references_resources(tmp_path, fake_cfg):
    # extra blink resources (gif/mp4/before-after) get their own section
    e = _fake_enriched()
    p = post.render_post(e, fake_cfg)
    res = {"gif": tmp_path / "TEST1_blink.gif",
           "mp4": tmp_path / "TEST1_blink.mp4",
           "pair": tmp_path / "TEST1_before_after.png"}
    written = post.save_outputs(p, tmp_path, "TEST1", e=e, resources=res)
    es = written["es"].read_text(encoding="utf-8")
    en = written["en"].read_text(encoding="utf-8")
    assert "## Recursos" in es and "## Resources" in en
    assert "TEST1_blink.gif" in es and "TEST1_blink.gif" in en
    assert "TEST1_blink.mp4" in es and "TEST1_blink.mp4" in en
    assert "TEST1_before_after.png" in es


def test_post_charts_plus_resources(tmp_path, fake_cfg):
    # charts and extra resources together, without colliding
    e = _fake_enriched()
    p = post.render_post(e, fake_cfg)
    charts = {"orbit": tmp_path / "TEST1_orbit.png"}
    res = {"gif": tmp_path / "TEST1_blink.gif"}
    written = post.save_outputs(p, tmp_path, "TEST1", e=e,
                                charts=charts, resources=res)
    es = written["es"].read_text(encoding="utf-8")
    assert "## Galería" in es and "## Recursos" in es
    assert es.index("## Galería") < es.index("## Recursos")
    assert "TEST1_orbit.png" in es and "TEST1_blink.gif" in es


def test_attach_charts_idempotent(fake_cfg):
    # attaching twice must replace the old block, not stack two sections
    e = _fake_enriched()
    p = post.render_post(e, fake_cfg)
    charts = {"orbit": "x_orbit.png"}
    post.attach_charts(p, charts)
    post.attach_charts(p, charts)
    assert p["es"].count("## Galería") == 1
    assert p["en"].count("## Gallery") == 1


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


def _exoplanet_enriched(with_transit=False):
    # Exoplanet Archive shape: ra/dec as plain float degrees (no `ra_deg`
    # twin) — the regression from commit 3412c3c (ADR-027) dropped the
    # sky chart for exactly this shape.
    d = {"ra": 330.795, "dec": 18.884, "pl_orbper": 3.5247,
         "mag": 7.65, "depth_mmag": 16.4, "duration_h": 3.1}
    if with_transit:
        # The Exoplanet Archive's transit_times() returns t0/t1 as ISO
        # strings; enrich.py passes them through verbatim. Both viz
        # consumers (sky_view._pos, transit_view) must accept strings.
        d["transit"] = {
            "name": "HD 209458 b", "star": "HD 209458",
            "ingress": "2026-09-07T22:40:00+00:00",
            "mid": "2026-09-08T00:15:00+00:00",
            "egress": "2026-09-08T01:50:00+00:00",
            "depth_mmag": 16.4, "duration_h": 3.1,
        }
    return {"name": "HD 209458 b", "type": "exoplanet", "data": d}


def test_build_charts_exoplanet_float_ra_dec_gets_sky(tmp_path, fake_cfg):
    # the Archive branch hands us `ra`/`dec` floats; the sky chart must not
    # silently disappear because only `ra_deg` was checked before
    e = _exoplanet_enriched()
    charts = post.build_charts(e, tmp_path, "HD209458b_", cfg=fake_cfg,
                               fmt="facebook")
    assert "sky" in charts, "exoplanet float ra/dec lost the sky slot"
    assert (tmp_path / "HD209458b_sky.png").exists()


def test_build_charts_exoplanet_transit_gets_lightcurve(tmp_path, fake_cfg):
    # with tonight's transit event merged by enrich, both the sky slot
    # (ingress/egress shading) and the light-curve slot render
    e = _exoplanet_enriched(with_transit=True)
    charts = post.build_charts(e, tmp_path, "HD209458b_", cfg=fake_cfg,
                               fmt="facebook")
    assert "sky" in charts and "transit" in charts
    assert (tmp_path / "HD209458b_sky.png").exists()
    assert (tmp_path / "HD209458b_transit.png").exists()


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
