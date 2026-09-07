############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: ephemeris.position_at (fresh goto)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime

from nightscribe.core import ephemeris


def _when():
    return datetime.datetime(2026, 9, 7, 22, 30,
                             tzinfo=datetime.timezone.utc)


def _horizons_rows():
    # 2-min step around 22:30; RA drifts 0.01 deg per 2 min (= 18"/min at
    # Dec=0), Dec fixed at 0 so cos(dec)=1 keeps the rate arithmetic clean.
    base = datetime.datetime(2026, 9, 7, 20, 30,
                             tzinfo=datetime.timezone.utc)
    from nightscribe.core import coords
    rows = []
    for i in range(121):  # 20:30 .. 00:30 at 2-min step
        t = base + datetime.timedelta(minutes=2 * i)
        ra_deg = 100.0 + 0.01 * i      # 0.01 deg per 2 min = 18"/min
        rows.append({
            "time": t.strftime("%Y-%b-%d %H:%M"),
            "ra": coords.ra_deg_to_hms(ra_deg),
            "dec": "+00 00 00",
            "r": 1.2, "delta": 0.5,
        })
    return rows


def test_interpolate_midpoint_matches_rate():
    # At the exact midpoint the interpolated RA is the average of the two
    # bracketing rows, and the derived rate is 18 arcsec/min.
    rows = _horizons_rows()
    jd = ephemeris.coords.jd_from_datetime(_when())
    out = ephemeris._interpolate(rows, jd)
    assert out is not None
    # 22:30 is 60 steps (120 min) after 20:30 -> ra_deg = 100 + 0.01*60 = 100.6
    assert abs(out["ra_deg"] - 100.6) < 1e-3
    assert abs(out["dec_deg"] - 0.0) < 1e-3
    assert abs(out["rate_arcsec_min"] - 18.0) < 1e-3


def test_interpolate_unwraps_ra_seam():
    # RA crossing the 0h/24h seam must not produce a 360 deg jump.
    rows = [
        {"time": "2026-Sep-07 22:28", "ra": "23 59 58.0", "dec": "+10 00 00",
         "r": 1.0, "delta": 1.0},
        {"time": "2026-Sep-07 22:32", "ra": "00 00 02.0", "dec": "+10 00 00",
         "r": 1.0, "delta": 1.0},
    ]
    from nightscribe.core import coords
    jd = coords.jd_from_datetime(datetime.datetime(
        2026, 9, 7, 22, 30, tzinfo=datetime.timezone.utc))
    out = ephemeris._interpolate(rows, jd)
    assert out is not None
    # midpoint between 359.9583 deg and 0.0417 deg (unwrapped) is 0.0 deg
    assert abs(out["ra_deg"]) < 1e-6 or abs(out["ra_deg"] - 360.0) < 1e-6
    # rate: 4"/min over 4 min of arc -> 1'/min = 60"/min
    assert out["rate_arcsec_min"] > 0


def test_floor_30min():
    dt = datetime.datetime(2026, 9, 7, 22, 47, 13,
                           tzinfo=datetime.timezone.utc)
    f = ephemeris._floor_30min(dt)
    assert f.minute == 30 and f.second == 0
    dt2 = datetime.datetime(2026, 9, 7, 22, 14, 59,
                            tzinfo=datetime.timezone.utc)
    assert ephemeris._floor_30min(dt2).minute == 0


def test_position_at_horizons_path(monkeypatch):
    # Horizons answers -> horizons source, no fallback called.
    import nightscribe.core.sources.horizons as hor
    import nightscribe.core.sources.sbdb as sb
    import nightscribe.core.sources.neofixer as nf
    monkeypatch.setattr(hor, "ephemeris",
                        lambda *a, **k: _horizons_rows())
    monkeypatch.setattr(sb, "get", lambda name: None)
    called = {"nf": False}
    monkeypatch.setattr(nf, "orbit",
                        lambda packed: called.__setitem__("nf", True))
    out = ephemeris.position_at("2026 AB", "Z41", when=_when())
    assert out is not None
    assert out["source"] == "horizons"
    assert out["preliminary"] is False
    assert out["epoch_iso"] == "2026-09-07 22:30:00"
    assert abs(out["ra_deg"] - 100.6) < 1e-3
    assert called["nf"] is False


def test_position_at_falls_back_to_sbdb_kepler(monkeypatch):
    # Horizons empty -> SBDB elements propagated locally.
    import nightscribe.core.sources.horizons as hor
    import nightscribe.core.sources.sbdb as sb
    els = {"a": 2.056, "e": 0.515, "i": 9.65, "om": 328.48, "w": 341.63,
           "ma": 5.985, "epoch": 2461277.5}
    monkeypatch.setattr(hor, "ephemeris", lambda *a, **k: [])
    monkeypatch.setattr(sb, "get", lambda name: {"elements": els})
    out = ephemeris.position_at("Apophis", "Z41", when=_when())
    assert out is not None
    assert out["source"] == "kepler:sbdb"
    assert out["preliminary"] is False
    assert 0 <= out["ra_deg"] < 360
    assert out["rate_arcsec_min"] >= 0


def test_position_at_falls_back_to_neofixer(monkeypatch):
    # Horizons + SBDB empty -> NEOfixer preliminary orbit.
    import nightscribe.core.sources.horizons as hor
    import nightscribe.core.sources.sbdb as sb
    import nightscribe.core.sources.neofixer as nf
    els = {"a": 2.056, "e": 0.515, "i": 9.65, "om": 328.48, "w": 341.63,
           "ma": 5.985, "epoch": 2461277.5}
    monkeypatch.setattr(hor, "ephemeris", lambda *a, **k: [])
    monkeypatch.setattr(sb, "get", lambda name: None)
    monkeypatch.setattr(nf, "orbit", lambda packed: {"elements": els})
    target = {"packed": "6HJ1A21"}
    out = ephemeris.position_at("6HJ1A21", "Z41", when=_when(),
                                fallback_target=target)
    assert out is not None
    assert out["source"] == "kepler:neofixer"
    assert out["preliminary"] is True


def test_position_at_returns_none_when_all_fail(monkeypatch):
    import nightscribe.core.sources.horizons as hor
    import nightscribe.core.sources.sbdb as sb
    import nightscribe.core.sources.neofixer as nf
    monkeypatch.setattr(hor, "ephemeris", lambda *a, **k: [])
    monkeypatch.setattr(sb, "get", lambda name: None)
    monkeypatch.setattr(nf, "orbit", lambda packed: None)
    assert ephemeris.position_at("nobody", "Z41", when=_when()) is None


def test_motion_zero_when_no_time():
    r, pa = ephemeris._motion(0.0, 10.0, 5.0, 0.0, 10.0, 5.0)
    assert r == 0.0 and pa == 0.0
