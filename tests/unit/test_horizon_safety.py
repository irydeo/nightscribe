############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: horizon safety invariants (ADR-020)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

from nightscribe.core import coords, horizon

# The sample file is the canonical TheSkyX export that protects a real
# observatory: every invariant here is one the telescope safety depends on.

SAMPLE = "docs/limits-sample.hrz"
DATE = datetime.date(2026, 8, 28)
LAT, LON = 40.55, -3.37
# a fixed test target that rises east, peaks ~48 deg and sets west:
RA, DEC = 45.0, 0.0


def _sample_horizon():
    # @return: the parsed canonical sample
    h = horizon.load(SAMPLE)
    assert h is not None
    return h


def _samples():
    # Altitude samples of the test target across the darkness of DATE.
    return coords.samples_tonight(RA, DEC, LAT, LON, DATE)


# --- parsed values: golden numbers from the real file ---

def test_golden_altitudes():
    h = _sample_horizon()
    # one altitude per line, azimuth = line index (0..n-1)
    assert abs(h.alt_at(214.0) - 69.29) < 1e-9
    assert abs(h.alt_at(224.0) - 75.00) < 1e-9
    assert abs(h.alt_at(268.0) - 77.50) < 1e-9
    assert abs(h.alt_at(321.0) - 65.00) < 1e-9
    assert abs(h.alt_at(100.0) - 20.00) < 1e-9


def test_interpolation_between_points():
    h = _sample_horizon()
    # between 69.29 (az214) and 70.71 (az215)
    assert abs(h.alt_at(214.5) - 70.00) < 1e-9
    # between 70.71 (az215) and 71.07 (az216)
    assert abs(h.alt_at(215.5) - 70.89) < 1e-9


def test_wrap_around_seam():
    h = _sample_horizon()
    # az 359 and az 0 both say 20.0 -> the seam is flat 20.0
    assert abs(h.alt_at(359.5) - 20.00) < 1e-9
    assert abs(h.alt_at(0.5) - 20.00) < 1e-9
    # any sign / wrap must give the same value
    assert abs(h.alt_at(-355.0) - h.alt_at(5.0)) < 1e-9
    assert abs(h.alt_at(370.0) - h.alt_at(10.0)) < 1e-9


def test_stats_min_max_peak():
    h = _sample_horizon()
    s = h.stats()
    assert s["min_alt"] == 20.0
    assert s["max_alt"] == 77.5
    assert s["peak_az"] == 268.0
    assert not h.is_flat
    assert len(h.points) == 360


def test_alt_always_inside_envelope():
    # basic envelope invariant: the sampled horizon never goes outside the
    # file's own min/max, at any azimuth (safety: no surprise dips)
    h = _sample_horizon()
    lo, hi = h.stats()["min_alt"], h.stats()["max_alt"]
    for az in [a / 8.0 for a in range(0, 360 * 8)]:
        v = h.alt_at(az)
        assert lo - 1e-9 <= v <= hi + 1e-9, (az, v)


# --- session safety: the object never crosses the horizon mid-session ---

def test_session_samples_stay_safe():
    h = _sample_horizon()
    s = _samples()
    best = h.best_span(s, duration_s=3600)
    assert best is not None
    start, end, rec = best
    in_span = [x for x in s if start <= x[0] <= end]
    assert in_span, "safe span must contain samples"
    for (_t, alt, az) in in_span:
        assert alt >= h.alt_at(az) + 0.0 - 1e-9, (_t, alt, az)


def test_session_span_covers_duration():
    h = _sample_horizon()
    best = h.best_span(_samples(), duration_s=3600)
    start, end, _rec = best
    assert (end - start).total_seconds() >= 3600


def test_latest_safe_start_inside_span():
    h = _sample_horizon()
    best = h.best_span(_samples(), duration_s=3600)
    start, end, rec = best
    assert rec == end - datetime.timedelta(seconds=3600)
    assert start <= rec <= end


def test_impossible_duration_gives_none():
    # a 72 h session cannot fit any span: the planner must get None and
    # the UI must say "does not fit tonight" instead of inventing a window
    h = _sample_horizon()
    assert h.best_span(_samples(), duration_s=72 * 3600) is None


def test_margin_never_widens_span():
    # a 5-deg safety margin can shorten the safe span, never stretch it
    h = _sample_horizon()
    s = _samples()
    base = h.best_span(s, margin=0.0)
    marg = h.best_span(s, margin=5.0)
    if marg is None:
        return
    b = (base[1] - base[0]).total_seconds()
    m = (marg[1] - marg[0]).total_seconds()
    assert m <= b + 1e-9


def test_full_span_without_duration():
    h = _sample_horizon()
    best = h.best_span(_samples())
    assert best is not None
    start, end, rec = best
    assert rec == start  # no duration -> recommended start is the span start
    assert (end - start).total_seconds() > 0


# --- planner glue: safe_window / best_time / latest_safe_start ---

def test_planner_visibility_safe_window():
    from nightscribe.core import planner
    vis = planner._visibility(RA, DEC, LAT, LON, DATE, _sample_horizon(),
                              0.0, 3600)
    assert vis["safe_window"] is not None
    s_str, e_str = vis["safe_window"].split("|")
    start = datetime.datetime.fromisoformat(s_str)
    end = datetime.datetime.fromisoformat(e_str)
    assert (end - start).total_seconds() >= 3600
    assert vis["best_time"] is not None
    assert vis["latest_safe_start"] is not None
    b = datetime.datetime.fromisoformat(vis["best_time"])
    l = datetime.datetime.fromisoformat(vis["latest_safe_start"])
    # the recommended start sits inside the span, the latest one ends it
    assert start <= b <= end
    assert l == end - datetime.timedelta(seconds=3600)


def test_planner_visibility_without_duration():
    from nightscribe.core import planner
    vis = planner._visibility(RA, DEC, LAT, LON, DATE, _sample_horizon())
    assert vis["safe_window"] is None
    assert vis["window_start"] is not None
    assert vis["best_time"] is not None  # highest safe instant tonight


def test_best_time_never_lands_on_blocked_azimuth():
    # A ridge 80 deg tall across the south (az 140-220), 20 deg floor
    # elsewhere. This target's meridian crossing (its highest altitude)
    # sits right under the ridge: recommending the raw peak would suggest
    # an hour the object is behind a local obstacle — a safety error.
    from nightscribe.core import planner
    pts = [(az, 80.0) for az in range(140, 221, 10)]
    pts += [(az, 20.0) for az in range(0, 360) if not (140 <= az <= 220)]
    h = horizon.Horizon(pts)
    ra, dec = 0.0, 5.0
    vis = planner._visibility(ra, dec, LAT, LON, DATE, h)
    # the astronomical peak really is blocked by this horizon
    t_peak = datetime.datetime.fromisoformat(vis["max_time"])
    alt_p, az_p = coords.current_altaz(ra, dec, LAT, LON, t_peak)
    assert alt_p < h.alt_at(az_p)
    # ... yet a safe span exists, so a recommended time must exist too
    assert vis["window_start"] is not None
    assert vis["best_time"] is not None
    assert vis["best_time"] != vis["max_time"]
    # and it is guaranteed safe at that instant
    t_best = datetime.datetime.fromisoformat(vis["best_time"])
    alt_b, az_b = coords.current_altaz(ra, dec, LAT, LON, t_best)
    assert alt_b >= h.alt_at(az_b)
    # and the advertised altitude is the reachable one, not the raw peak
    assert vis["safe_max_alt"] < vis["max_alt"]
    assert vis["safe_max_alt"] is not None
    assert vis["safe_max_alt"] >= 20.0  # above the 20 deg floor, actually visible


def test_unblocked_object_keeps_full_altitude():
    # A target whose peak is a free azimuth: safe_max_alt is its own peak
    from nightscribe.core import planner
    h = _sample_horizon()
    vis = planner._visibility(RA, DEC, LAT, LON, DATE, h)
    # the test target (RA 45, dec 0) peaks in a free east/south-east azimuth
    assert vis["safe_max_alt"] == vis["max_alt"]


# --- parser negatives (fallback behaviour must be honest) ---

def _write(tmp_path, text, name="bad.hrz"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_load_truncated_body_rejected(tmp_path):
    # cardinality says 360 but only 10 altitudes -> pairs fallback fails too
    text = "0.00|  0.00\n360\n" + "\n".join(" 20.00" for _ in range(10)) + "\n"
    assert horizon.load(_write(tmp_path, text)) is None


def test_load_bad_cardinality_rejected(tmp_path):
    text = "0.00|  0.00\n1000\n" + "\n".join(" 20.00" for _ in range(10)) + "\n"
    assert horizon.load(_write(tmp_path, text)) is None


def test_load_alt_out_of_range_rejected(tmp_path):
    text = ("0.00|  0.00\n2\n 20.00\n 120.00\n")
    assert horizon._parse_thesky(text.splitlines()) is None


def test_load_two_numbers_in_body_rejected(tmp_path):
    text = "0.00|  0.00\n2\n 20.00  30.00\n 40.00\n"
    assert horizon._parse_thesky(text.splitlines()) is None


def test_open_reference_warns_on_unreadable_file(fake_cfg, tmp_path):
    fake_cfg._v["horizon_file"] = str(tmp_path / "missing.hrz")
    h, notes = horizon.open_reference(fake_cfg)
    assert h.is_flat
    assert any(n[0] == "warn" for n in notes)
    # and it still falls back to the configured min_alt
    assert h.alt_at(90.0) == 30.0


def test_pairs_format_still_loads():
    # the simple "az alt" text stays supported (hand-made files, NINA)
    h = horizon.load("tests/fixtures/horizon_sample.txt")
    assert h is not None
    assert abs(h.alt_at(60.0) - 60.0) < 1e-6
