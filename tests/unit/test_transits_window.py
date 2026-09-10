############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: transit capture window (Track D, subplan 0)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The transit event core: the recommended capture window (baseline +
transit + baseline, Conti/AAVSO), its feasibility inside the safe night,
the maximum cadence that resolves the ingress and the heuristic exposure.
"""

import datetime

from nightscribe.core import coords, exposure, transits

LAT, LON = 40.55, -3.37          # Madrid area (same site as the other tests)
DATE = datetime.date(2026, 8, 21)


def _planet_at(mid_dt, name="WASP-999 b", dur_h=2.0, v_mag=11.5):
    # @args: mid_dt - UTC datetime of the mid-transit
    # @return: synthetic ExoClock-style planet whose mid-transit culminates
    #          (RA = LST at mid, Dec = site latitude -> near-zenith star)
    jd = coords.jd_from_datetime(mid_dt)
    return {"name": name, "star": "WASP-999",
            "ra": coords.lst_degrees(jd, LON), "dec": LAT,
            "t0": jd, "period": 3.0, "duration_h": dur_h,
            "v_mag": v_mag, "depth_mmag": 10.0}


def _tonight_midpoint():
    start, end = coords.tonight_window(LAT, LON, DATE)
    return start, end, start + (end - start) / 2


def _event_for(out, mid_dt):
    # @args: out - transits_tonight results, mid_dt - intended mid-transit
    # @return: the event whose mid matches (the catalogue period makes
    #          sibling transits from adjacent nights show up too — the gate
    #          is at mid-transit altitude, not at darkness containment)
    for t in out:
        if abs((t["mid"] - mid_dt).total_seconds()) < 60:
            return t
    raise AssertionError(f"no event at {mid_dt} in {len(out)} results")


# ---------------- recommended_window ----------------

def test_recommended_window_floor_30min():
    # duration 1 h -> frac baseline 15 min, so the 30-min floor rules
    mid = datetime.datetime(2026, 8, 22, 0, 0, tzinfo=datetime.timezone.utc)
    t = {"ingress": mid - datetime.timedelta(minutes=30),
         "egress": mid + datetime.timedelta(minutes=30),
         "duration_h": 1.0}
    cs, ce = transits.recommended_window(t)
    assert t["ingress"] - cs == datetime.timedelta(minutes=30)
    assert ce - t["egress"] == datetime.timedelta(minutes=30)


def test_recommended_window_fraction_over_floor():
    # duration 4 h -> 0.25 * 4 h = 60 min baseline (above the floor)
    mid = datetime.datetime(2026, 8, 22, 0, 0, tzinfo=datetime.timezone.utc)
    t = {"ingress": mid - datetime.timedelta(hours=2),
         "egress": mid + datetime.timedelta(hours=2),
         "duration_h": 4.0}
    cs, ce = transits.recommended_window(t)
    assert t["ingress"] - cs == datetime.timedelta(hours=1)
    assert ce - t["egress"] == datetime.timedelta(hours=1)


# ---------------- transits_tonight enrichment ----------------

def test_capture_fields_present_and_ordered():
    _start, _end, mid = _tonight_midpoint()
    out = transits.transits_tonight([_planet_at(mid)], LAT, LON, DATE)
    t = _event_for(out, mid)
    for key in ("capture_start", "capture_end", "baseline_fits",
                "cadence_max_s", "exp_recommended_s"):
        assert key in t, key
    # baseline + transit + baseline, strictly ordered
    assert t["capture_start"] < t["ingress"] < t["egress"] < t["capture_end"]
    # 2 h transit -> 0.25 * 2 h = 30 min baseline (exactly the floor)
    assert t["ingress"] - t["capture_start"] == datetime.timedelta(minutes=30)
    assert t["capture_end"] - t["egress"] == datetime.timedelta(minutes=30)
    # cadence: >= 3 points in the ingress (~15 % of the duration)
    assert t["cadence_max_s"] == round(0.15 * 2.0 * 3600 / 3) == 360
    # v_mag 11.5 -> 60 s (table, no plate scale given)
    assert t["exp_recommended_s"] == 60


def test_baseline_fits_true_when_window_is_comfortable():
    _start, _end, mid = _tonight_midpoint()
    out = transits.transits_tonight([_planet_at(mid)], LAT, LON, DATE)
    assert _event_for(out, mid)["baseline_fits"] is True


def test_baseline_fits_false_when_capture_overflows_darkness():
    # Mid-transit 30 min before the end of darkness: the transit itself is
    # still listed (the gate is at mid), but the post-egress baseline falls
    # outside the night -> the event must be flagged, not hidden.
    _start, end, _mid = _tonight_midpoint()
    mid = end - datetime.timedelta(minutes=30)
    out = transits.transits_tonight([_planet_at(mid)], LAT, LON, DATE)
    assert _event_for(out, mid)["baseline_fits"] is False


def test_baseline_fits_false_when_star_sets_during_baseline():
    # Star comfortably up at mid-transit (the gate passes) but below the
    # horizon threshold at the post-egress baseline edge -> flagged.
    # Geometry: dec such that the star culminates at 65 deg, placed at
    # hour angle +55 deg at mid (alt ~36 deg at the gate); the capture end
    # (mid + 1 h for a 1 h transit) pushes it to H ~ +70 deg (alt ~25 deg,
    # below the default 30 deg flat threshold).
    _start, _end, mid = _tonight_midpoint()
    jd_mid = coords.jd_from_datetime(mid)
    ra = (coords.lst_degrees(jd_mid, LON) - 55.0) % 360.0
    p = {"name": "HD 000 b", "star": "HD 000", "ra": ra, "dec": LAT - 25.0,
         "t0": jd_mid, "period": 3.0, "duration_h": 1.0, "v_mag": 10.0}
    out = transits.transits_tonight([p], LAT, LON, DATE)
    t = _event_for(out, mid)
    assert t["baseline_fits"] is False


# ---------------- heuristic exposure ----------------

def test_transit_exposure_table_and_scaling():
    # reference scale (None -> 1.0 arcsec/px): table values
    assert exposure.recommended_transit_exposure(8.5) == 15
    assert exposure.recommended_transit_exposure(10.5) == 40
    assert exposure.recommended_transit_exposure(13.5) == 120
    assert exposure.recommended_transit_exposure(15.9) == 180
    # finer plate (0.5"/px) -> x4 longer; coarser (2"/px) -> x0.25
    assert exposure.recommended_transit_exposure(10.5, 0.5) == 160
    assert exposure.recommended_transit_exposure(10.5, 2.0) == 10
    # the scaling is clamped: a very fine plate cannot blow the 300 s cap
    assert exposure.recommended_transit_exposure(13.5, 0.2) == 300
    # unknown magnitude -> no recommendation
    assert exposure.recommended_transit_exposure(None) is None
