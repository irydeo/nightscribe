############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: Galilean satellite events (Track SC2-SD)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""`core/satellites.galilean_events` — transits of the Galilean moons and
their shadows across Jupiter's disc, for the observer's site.

Offline, no network. The "truth" windows baked below come from JPL
Horizons observer tables, quantity 12 (angular separation + satellite
visibility codes: "/t" = transiting the primary's disk), site Z41,
fetched 2026-09-17 (see docs/PLANS/sky-calendar.md §SD). The engine's
honest precision is ±10 min (planning grade); the test tolerance is
15 min to absorb the 2-min step quantization of the truth extraction.
"""

import datetime

import pytest

from nightscribe.core import coords, satellites

# the author's observatory (Irydeo, MPC Z41) — same as config.DEFAULTS
LAT, LON = 40.55, -3.37
JD = lambda iso: coords.jd_from_datetime(
    datetime.datetime.strptime(iso, "%Y-%m-%d %H:%M")
    .replace(tzinfo=datetime.timezone.utc))


# (satellite, t0, t1) — JPL Horizons quantity-12 "/t" windows, UTC
TRUTH = [
    ("io",       "2026-09-19 18:02", "2026-09-19 20:22"),
    ("io",       "2026-09-21 12:32", "2026-09-21 14:52"),
    ("io",       "2026-09-23 07:02", "2026-09-23 09:22"),
    ("io",       "2026-09-25 01:32", "2026-09-25 03:52"),
    ("europa",   "2026-09-21 03:24", "2026-09-21 06:20"),
    ("europa",   "2026-09-24 16:46", "2026-09-24 19:44"),
    ("ganymede", "2026-09-22 05:00", "2026-09-22 08:46"),
    ("callisto", "2026-09-19 00:00", "2026-09-19 01:52"),  # window-clipped
    ("callisto", "2026-10-05 16:48", "2026-10-05 21:48"),
    ("callisto", "2026-10-22 12:14", "2026-10-22 17:12"),
    ("callisto", "2026-11-08 07:02", "2026-11-08 11:58"),
    ("europa",   "2026-10-16 01:02", "2026-10-16 03:58"),
    ("ganymede", "2026-10-20 22:06", "2026-10-21 01:50"),
    ("ganymede", "2026-11-11 10:26", "2026-11-11 14:10"),
]

# the fully-covered validation week: exactly these many engine transits
# per moon may appear inside it (no invented events)
TRUTH_WEEK_COUNTS = {"io": 4, "europa": 2, "ganymede": 1, "callisto": 1}

TOL_MIN = 15.0      # engine honesty ±10 + 2-min truth quantization


@pytest.fixture(scope="module")
def engine_events():
    jd0 = JD("2026-09-19 00:00")
    jd1 = JD("2026-11-12 00:00")
    return satellites.galilean_events(jd0, jd1, LAT, LON)


def _match(events, sat, t0_iso):
    # @return: the engine's sat_transit of `sat` containing t0_iso's day+
    #          hour neighbourhood, or None
    target = datetime.datetime.strptime(t0_iso, "%Y-%m-%d %H:%M") \
        .replace(tzinfo=datetime.timezone.utc)
    for e in events:
        if e["satellite"] == sat and e["kind"] == "sat_transit" \
                and abs((e["t0"] - target).total_seconds()) < 7200:
            return e
    return None


@pytest.mark.parametrize("sat,t0,t1", TRUTH)
def test_transit_windows_match_horizons(engine_events, sat, t0, t1):
    # every Horizons transit window must appear in the engine within the
    # tolerance, on both edges
    ev = _match(engine_events, sat, t0)
    assert ev is not None, f"no engine transit of {sat} near {t0}"
    t0t = datetime.datetime.strptime(t0, "%Y-%m-%d %H:%M") \
        .replace(tzinfo=datetime.timezone.utc)
    t1t = datetime.datetime.strptime(t1, "%Y-%m-%d %H:%M") \
        .replace(tzinfo=datetime.timezone.utc)
    assert abs((ev["t0"] - t0t).total_seconds()) / 60 <= TOL_MIN
    assert abs((ev["t1"] - t1t).total_seconds()) / 60 <= TOL_MIN


def test_no_spurious_transits_in_the_truth_week(engine_events):
    # inside the fully-validated week the engine must not invent windows:
    # exactly the Horizons count per moon. (Compare on the CLIPPED t0:
    # jd0 is the raw ingress and can sit just before the window.)
    from collections import Counter
    lo = datetime.datetime(2026, 9, 19, tzinfo=datetime.timezone.utc)
    hi = datetime.datetime(2026, 9, 26, tzinfo=datetime.timezone.utc)
    got = Counter(
        e["satellite"] for e in engine_events
        if e["kind"] == "sat_transit" and lo <= e["t0"] <= hi)
    for sat, want in TRUTH_WEEK_COUNTS.items():
        assert got[sat] == want, \
            f"{sat}: engine {got[sat]} vs truth {want}"


def test_io_period_spacing(engine_events):
    # Io transits repeat at its orbital period (~1.769 d)
    ios = [e for e in engine_events
           if e["satellite"] == "io" and e["kind"] == "sat_transit"]
    assert len(ios) >= 2
    for a, b in zip(ios, ios[1:]):
        gap = b["jd0"] - a["jd0"]
        assert abs(gap - satellites.GALILEANS["io"]["period_d"]) < 0.05


def test_every_callisto_transit_validates(engine_events):
    # Callisto DOES transit on consecutive orbits in this season (D_E is
    # small): every engine window matches a truth window — 4 of them in
    # the span (see TRUTH), none extra
    cal = [e for e in engine_events if e["satellite"] == "callisto"
           and e["kind"] == "sat_transit"]
    truth_cal = [(t0, t1) for (s, t0, t1) in TRUTH if s == "callisto"]
    assert len(cal) == len(truth_cal)
    for ev, (t0, _t1) in zip(cal, truth_cal):
        t0t = datetime.datetime.strptime(t0, "%Y-%m-%d %H:%M") \
            .replace(tzinfo=datetime.timezone.utc)
        assert abs((ev["t0"] - t0t).total_seconds()) / 60 <= TOL_MIN


def test_shadow_and_moon_windows_exist_and_differ(engine_events):
    # shadows are the point: they must exist, and — this far from
    # opposition — they lead/trail the moon's own window measurably.
    # Io's tight geometry guarantees a same-orbit moon window per shadow.
    sh = [e for e in engine_events if e["kind"] == "shadow_transit"]
    tr = [e for e in engine_events if e["kind"] == "sat_transit"]
    assert sh and tr
    io_sh = [s for s in sh if s["satellite"] == "io"]
    io_tr = [t for t in tr if t["satellite"] == "io"]
    assert io_sh and io_tr
    for s in io_sh:
        twin = next((t for t in io_tr if abs(t["jd0"] - s["jd0"]) < 0.2),
                    None)
        assert twin is not None, "every Io shadow pairs its moon's orbit"
        assert abs(twin["jd0"] - s["jd0"]) > 0.005   # > 7 min apart


def test_event_contract(engine_events):
    for e in engine_events:
        assert e["kind"] in ("sat_transit", "shadow_transit")
        assert e["satellite"] in satellites.GALILEANS
        assert e["jd1"] > e["jd0"]
        assert e["uncertainty_min"] == satellites.UNCERTAINTY_MIN
        assert e["observable"] in (True, False)
        assert 0.5 <= (e["jd1"] - e["jd0"]) * 24 <= 6.0   # hours


# ---------------- the observability gate (ADR-020 site limit) ----------------

def test_gate_respects_the_site_limit():
    # io 2026-09-25 01:32-03:52: a genuinely DARK window whose CORE has
    # Jupiter at only ~3-7 deg yet whose EGRESS TAIL climbs to ~16 deg.
    # The site's own limit (ADR-020) must drive the decision, judged on
    # the core band — so a loose 5-deg floor lets it through, but a real
    # 10-deg one hides it even though the tail clears 10 deg. The old
    # 0-deg tail gate advertised both the same (the reported bug).
    a, b = JD("2026-09-25 01:32"), JD("2026-09-25 03:52")
    loose, _ = satellites._observable(a, b, LAT, LON,
                                      alt_at=lambda az: 5.0, margin=0.0)
    strict, best = satellites._observable(a, b, LAT, LON,
                                          alt_at=lambda az: 10.0, margin=0.0)
    assert loose is True      # above a 5-deg limit, dark -> usable
    assert strict is False    # core (~7 deg) under a 10-deg limit -> hidden
    assert best >= 10         # honesty note still reports the window's tail


def test_gate_requires_dark_sky():
    # io 2026-09-23 07:02-09:22: Jupiter high (~60 deg) but the Sun is up
    # (~+27 deg) — a daytime window is never usable, however loose the
    # altitude limit
    ok, _ = satellites._observable(JD("2026-09-23 07:02"),
                                   JD("2026-09-23 09:22"), LAT, LON,
                                   alt_at=lambda az: 1.0, margin=0.0)
    assert ok is False


def test_no_site_means_no_observability():
    # without a site the event still computes, observability stays None
    evs = satellites.galilean_events(JD("2026-09-19 00:00"),
                                     JD("2026-09-20 00:00"))
    assert all(e["observable"] is None for e in evs)


def test_sorted_output(engine_events):
    jds = [e["jd0"] for e in engine_events]
    assert jds == sorted(jds)
