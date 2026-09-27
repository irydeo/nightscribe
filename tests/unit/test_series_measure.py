############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: photometric series engine (series plan,
# phase 2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Phase-2 acceptance tests for core/series_measure.py: synthetic frames
written as FITS with a TAN WCS and a fixed seed, a fixed comparison set,
and the D12 anchors that do not need the detrend (a without detrend, c, d,
e), plus the quality gates, grouping, cancellation and a performance
reference. No network.
"""

import math
import time
from pathlib import Path

import numpy as np
import pytest

from nightscribe.core import photometry as phot
from nightscribe.core import series_measure as sm
from nightscribe.core import wcs as wcs_mod

W = H = 160
SIGMA = 3.0
ZP_TRUE = 22.0
TARGET_XY = (80.4, 80.3)
COMP_XY = [(45, 45), (115, 45), (45, 115), (115, 115), (80, 125)]
CHECK_XY = (110, 70)


def _card(key, value=None, comment=""):
    s = key.ljust(8) if value is None else f"{key.ljust(8)}= {value}"
    return (s + (f" / {comment}" if comment else ""))[:80].ljust(80)


def _header(date_obs="2026-09-20T23:30:00", exptime=10.0, extra=()):
    cards = [_card("SIMPLE", "T"), _card("BITPIX", "-32"),
             _card("NAXIS", "2"), _card("NAXIS1", str(W)),
             _card("NAXIS2", str(H)),
             _card("CTYPE1", "'RA---TAN'"), _card("CTYPE2", "'DEC--TAN'"),
             _card("CRVAL1", "300.0"), _card("CRVAL2", "60.0"),
             _card("CRPIX1", str(W / 2)), _card("CRPIX2", str(H / 2)),
             _card("CD1_1", "-0.0003"), _card("CD1_2", "0.0"),
             _card("CD2_1", "0.0"), _card("CD2_2", "0.0003"),
             _card("GAIN", "2.0"), _card("RDNOISE", "5.0"),
             _card("EXPTIME", str(exptime)),
             _card("DATE-OBS", f"'{date_obs}'")]
    cards += list(extra)
    return "".join(cards + [_card("END")]).encode("latin-1")


def _write_plate(path, data, date_obs="2026-09-20T23:30:00", exptime=10.0,
                 extra=()):
    header = _header(date_obs, exptime, extra)
    header += b" " * ((2880 - len(header) % 2880) % 2880)
    raw = np.ascontiguousarray(data, dtype=">f4").tobytes()
    raw += b"\0" * ((2880 - len(raw) % 2880) % 2880)
    Path(path).write_bytes(header + raw)
    return path


def _reference_wcs():
    return wcs_mod.Wcs.from_header(_parsed_header())


def _parsed_header():
    from nightscribe.core import fits_io
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as fh:
        p = fh.name
    _write_plate(p, np.zeros((H, W), dtype=np.float32))
    header, _data = fits_io.read_fits(p)
    Path(p).unlink()
    return header


def _stars(target_amp=7000.0):
    return ([(TARGET_XY[0], TARGET_XY[1], target_amp)]
            + [(x, y, a) for (x, y), a in
               zip(COMP_XY, (11000, 10500, 11500, 10800, 10200))]
            + [(CHECK_XY[0], CHECK_XY[1], 9000.0)])


def _plate(target_amp=7000.0, sky=100.0, noise=0.0, seed=1, gradient=0.0):
    data = np.full((H, W), sky, dtype=np.float64)
    yy, xx = np.ogrid[:H, :W]
    if gradient:
        data += gradient * (xx - TARGET_XY[0])
    for sx, sy, amp in _stars(target_amp):
        data += amp * np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2)
                             / (2 * SIGMA ** 2))
    if noise > 0.0:
        data += np.random.default_rng(seed).normal(0.0, noise, (H, W))
    return data


def _comp_set(wcs):
    # Fixed comparison set (D35): five comps plus a check, catalog values
    # bootstrapped from the reference plate at the known zero point.
    ref = _plate()
    entries = []
    for j, (x, y) in enumerate(COMP_XY):
        r = phot.measure_point(ref, x, y)
        inst = -2.5 * math.log10(r["flux"])
        ra, dec = wcs.pixel_to_sky(x, y)
        entries.append({"name": f"C{j + 1}", "kind": "comp",
                        "star": {"ra": ra, "dec": dec, "mag": inst + ZP_TRUE,
                                 "band": "V",
                                 "bands": [{"label": "V",
                                            "value": inst + ZP_TRUE,
                                            "err": 0.01, "derived": False}],
                                 "bv": 0.6}})
    r = phot.measure_point(ref, *CHECK_XY)
    inst = -2.5 * math.log10(r["flux"])
    ra, dec = wcs.pixel_to_sky(*CHECK_XY)
    entries.append({"name": "CHK", "kind": "check",
                    "star": {"ra": ra, "dec": dec, "mag": inst + ZP_TRUE,
                             "band": "V",
                             "bands": [{"label": "V",
                                        "value": inst + ZP_TRUE,
                                        "err": 0.01, "derived": False}],
                             "bv": 0.6}})
    return entries


def _config(wcs, comps, **over):
    base = dict(wcs=wcs, target_xy=TARGET_XY, comp_set=tuple(comps),
                band="V", site_gain=2.0, site_ron=5.0,
                site_lat=40.0, site_lon=-3.0, site_aperture_m=0.254,
                site_height_m=650.0)
    base.update(over)
    return sm.SeriesConfig(**base)


def _write_frames(tmp_path, n, amps=None, noise=0.0, seed=1, start=0):
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    paths = []
    for i in range(n):
        amp = 7000.0 if amps is None else amps[i]
        data = _plate(target_amp=amp, noise=noise, seed=seed + i)
        # a couple of minutes between frames, so the times are monotonic
        date = f"2026-09-20T23:{30 + i:02d}:00"
        paths.append(_write_plate(tmp_path / f"f{i:03d}.fits", data,
                                  date_obs=date, exptime=10.0))
    return paths, wcs, comps


# ---------------- D12 anchor (a) without detrend ----------------

def test_series_constant_and_a_dip_is_recovered(tmp_path):
    # A flat series plus a 1 % dip on two frames: the recovered depth is
    # -2.5*log10(0.99) = 0.0109 mag, inside +/-0.001 (D12a without detrend).
    amps = [7000.0, 7000.0, 6930.0, 6930.0, 7000.0]
    paths, wcs, comps = _write_frames(tmp_path, 5, amps=amps)
    res = sm.measure_series(paths, _config(wcs, comps))
    assert res.status == "complete"
    assert len(res.points) == 5
    assert all(p.flags == [] for p in res.points), [p.flags
                                                    for p in res.points]
    flat = [p.mag for p in res.points if p.mag is not None]
    assert len(flat) == 5
    depth = max(flat) - min(flat)
    assert depth == pytest.approx(-2.5 * math.log10(0.99), abs=0.001)
    # times: mid exposure, monotonic; HJD computed from the reference WCS
    assert all(p.mjd is not None and p.hjd is not None for p in res.points)
    assert res.points[0].mjd < res.points[-1].mjd


def test_series_time_is_mid_exposure(tmp_path):
    # T6/D15: T_mid = T_start + EXPTIME/2. With EXPTIME = 10 s the mid
    # instant is 5 s after DATE-OBS, i.e. 5/86400 days.
    paths, wcs, comps = _write_frames(tmp_path, 1)
    res = sm.measure_series(paths, _config(wcs, comps))
    from nightscribe.core import fits_meta
    start = fits_meta.read_meta(paths[0])["mjd"]
    assert res.points[0].mjd == pytest.approx(start + 5.0 / 86400.0,
                                              abs=1e-9)


# ---------------- D12 anchor (c): corrupted comp ----------------

def test_corrupted_comp_is_vetoed(tmp_path):
    # Six frames; in frame 2 a comp flares by a magnitude. The MAD veto
    # must drop it from that frame's ensemble so the point does not jump.
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    paths = []
    for i in range(6):
        data = _plate(noise=0.5, seed=10 + i)
        if i == 2:
            yy, xx = np.ogrid[:H, :W]
            cx, cy = COMP_XY[0]
            data += 9000.0 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2)
                                    / (2 * SIGMA ** 2))
        paths.append(_write_plate(tmp_path / f"c{i:03d}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    res = sm.measure_series(paths, _config(wcs, comps))
    mags = [p.mag for p in res.points]
    assert all(m is not None for m in mags)
    # the corrupted frame is within a couple of mmag of the clean median
    clean = float(np.median([m for j, m in enumerate(mags) if j != 2]))
    assert abs(mags[2] - clean) < 0.01
    # the veto left that frame with fewer comps than the rest
    assert res.points[2].n_comps < res.points[0].n_comps


# ---------------- D12 anchor (d): a flagged point stays ----------------

def test_cloud_point_is_flagged_but_kept(tmp_path):
    # Frame 3 has all the comps 0.3 mag brighter (a thin cloud shifts the
    # zero point): the point is flagged "cloud", never deleted, and the
    # robust median of the clean points still holds the truth.
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    paths = []
    for i in range(6):
        data = _plate(noise=0.3, seed=20 + i)
        if i == 3:
            # brighten every comp and the check (but not the target)
            yy, xx = np.ogrid[:H, :W]
            for cx, cy in COMP_XY + [CHECK_XY]:
                data += 2000.0 * np.exp(-((xx - cx) ** 2
                                          + (yy - cy) ** 2)
                                        / (2 * SIGMA ** 2))
        paths.append(_write_plate(tmp_path / f"d{i:03d}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    res = sm.measure_series(paths, _config(wcs, comps))
    assert len(res.points) == 6                 # never deleted
    flagged = [p for p in res.points if "cloud" in p.flags]
    assert len(flagged) == 1
    clean = float(np.median([p.mag for p in res.points
                             if "cloud" not in p.flags]))
    # the clean points recover the true target ZP-based magnitude
    ref = phot.measure_point(_plate(), *TARGET_XY)
    truth = -2.5 * math.log10(ref["flux"]) + ZP_TRUE
    assert clean == pytest.approx(truth, abs=0.01)


# ---------------- D12 anchor (e): relative mode over a gradient -----

def test_relative_mode_recovers_over_a_gradient(tmp_path):
    # An SN on its host's gradient, measured differentially (relative
    # mode, no catalog): the gradient cancels with a symmetric comp ring
    # and the injected 0.05 mag change comes back within 1 %.
    wcs = _reference_wcs()
    comps = [(45, 45), (115, 45), (45, 115), (115, 115), (80, 125)]
    # symmetric around the target in x so the median comp carries the
    # same gradient level as the target
    entries = []
    for j, (x, y) in enumerate(comps):
        ra, dec = wcs.pixel_to_sky(x, y)
        entries.append({"name": f"C{j + 1}", "kind": "comp",
                        "star": {"ra": ra, "dec": dec, "band": "V",
                                 "bands": [], "bv": None}})
    paths = []
    for i, amp in enumerate((7000.0, 7350.0)):     # ~0.053 mag rise
        data = _plate(target_amp=amp, noise=0.0, seed=30 + i, gradient=0.8)
        paths.append(_write_plate(tmp_path / f"r{i}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    cfg = _config(wcs, entries, zp_mode="relative")
    res = sm.measure_series(paths, cfg)
    assert all(p.inst is not None for p in res.points)
    dm = res.points[1].mag - res.points[0].mag
    expected = -2.5 * math.log10(7350.0 / 7000.0)
    assert dm == pytest.approx(expected, rel=0.01)


# ---------------- gates ----------------

def test_guide_jump_is_flagged(tmp_path):
    # The target jumps 4 px on frame 2 (beyond the 2 px guide gate): the
    # point is flagged and kept.
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    paths = []
    for i in range(4):
        data = _plate(noise=0.2, seed=40 + i)
        if i == 2:
            # the target drifts 3 px (inside the centroid's lock reach,
            # beyond the 2 px guide gate), comps and noise untouched
            yy, xx = np.ogrid[:H, :W]
            tx, ty = TARGET_XY
            data -= 7000.0 * np.exp(-((xx - tx) ** 2 + (yy - ty) ** 2)
                                    / (2 * SIGMA ** 2))
            data += 7000.0 * np.exp(-((xx - tx - 3.0) ** 2
                                      + (yy - ty) ** 2)
                                    / (2 * SIGMA ** 2))
        paths.append(_write_plate(tmp_path / f"g{i}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    res = sm.measure_series(paths, _config(wcs, comps))
    assert "guide_jump" in res.points[2].flags
    assert "guide_jump" not in res.points[0].flags


def test_saturated_target_is_flagged(tmp_path):
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    paths = []
    for i in range(3):
        data = _plate(noise=0.2, seed=50 + i)
        extra = [_card("SATURATE", "5000.0")] if i == 1 else []
        paths.append(_write_plate(tmp_path / f"s{i}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00",
                                  extra=extra))
    res = sm.measure_series(paths, _config(wcs, comps))
    assert "saturated" in res.points[1].flags
    assert res.points[1].mag is None


def test_cosmic_hit_is_flagged(tmp_path):
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    paths = []
    for i in range(3):
        data = _plate(noise=1.0, seed=60 + i)
        if i == 1:
            data[int(TARGET_XY[1]), int(TARGET_XY[0]) + 2] += 9000.0
        paths.append(_write_plate(tmp_path / f"x{i}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    res = sm.measure_series(paths, _config(wcs, comps))
    assert "cosmic" in res.points[1].flags


# ---------------- grouping, cancellation, errors ----------------

def test_grouping_collapses_points(tmp_path):
    paths, wcs, comps = _write_frames(tmp_path, 6)
    res = sm.measure_series(paths, _config(wcs, comps, group_n=3))
    assert res.group_n == 3
    assert len(res.points) == 2
    assert len(res.points[0].members) == 3
    assert res.points[0].err >= res.points[0].err_internal


def test_cancellation_leaves_an_incomplete_series(tmp_path):
    paths, wcs, comps = _write_frames(tmp_path, 6)
    state = {"n": 0}

    def cancel():
        state["n"] += 1
        return state["n"] > 3

    res = sm.measure_series(paths, _config(wcs, comps), cancel=cancel)
    assert res.status == "incomplete"
    assert len(res.points) <= 3


def test_unreadable_frame_is_recorded(tmp_path):
    paths, wcs, comps = _write_frames(tmp_path, 2)
    bad = tmp_path / "broken.fits"
    bad.write_bytes(b"not a fits file at all")
    res = sm.measure_series(paths + [bad], _config(wcs, comps))
    assert str(bad) in res.errors
    assert len(res.points) == 2


# ---------------- error honesty and performance reference -----------

def test_total_error_is_never_below_internal(tmp_path):
    paths, wcs, comps = _write_frames(tmp_path, 4, noise=1.0)
    res = sm.measure_series(paths, _config(wcs, comps))
    for p in res.points:
        assert p.err is not None and p.err_internal is not None
        assert p.err >= p.err_internal


def test_performance_reference(tmp_path):
    # Referential, not a gate (D43): the 142-frame dataset budget is
    # < 0.5 s/frame. Small frames stand in for the real ones.
    paths, wcs, comps = _write_frames(tmp_path, 142, noise=0.5)
    t0 = time.perf_counter()
    res = sm.measure_series(paths, _config(wcs, comps))
    elapsed = time.perf_counter() - t0
    assert len(res.points) == 142
    assert elapsed / 142 < 0.5, f"{elapsed:.2f}s for 142 frames"


# ---------------- phase 3: T3 aperture + T5 detrend ----------------

def _plate_sigma(sigma, target_amp=7000.0, sky=100.0, noise=0.0, seed=1):
    data = np.full((H, W), sky, dtype=np.float64)
    yy, xx = np.ogrid[:H, :W]
    for sx, sy, amp in _stars(target_amp):
        data += amp * np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2)
                             / (2 * sigma ** 2))
    if noise > 0.0:
        data += np.random.default_rng(seed).normal(0.0, noise, (H, W))
    return data


def test_detrend_keeps_the_dip(tmp_path):
    # D12 anchor (a) WITH detrend: a 1 % dip on an airmass-flat series is
    # still recovered to +/-0.001 mag; the detrend is additive and does
    # not eat the signal.
    amps = [7000.0, 7000.0, 6930.0, 6930.0, 7000.0]
    paths, wcs, comps = _write_frames(tmp_path, 5, amps=amps)
    res = sm.measure_series(paths, _config(wcs, comps,
                                           detrend_policy="airmass"))
    assert res.detrend is not None
    vals = [p.mag_detrended for p in res.points]
    assert all(v is not None for v in vals)
    assert max(vals) - min(vals) == pytest.approx(
        -2.5 * math.log10(0.99), abs=0.001)


def test_detrend_leaves_a_sine_undistorted():
    # D12 anchor (b): a 0.3 mag (peak-to-peak) / 2 h artificial sine on
    # top of an airmass trend passes through the detrend undistorted: the
    # oscillation keeps its amplitude and its shape (the raw curve is in
    # any case always kept beside it, T5).
    n = 80
    cycles = 1.5
    pts = []
    for i in range(n):
        mjd = 61300.2 + i * (3.0 / 24.0) / n       # 3 h, 1.5 cycles
        airmass = 1.0 + 0.5 * i / n
        trend = 0.30 * math.exp(-1.0 * (airmass - 1.0))
        sine = 0.15 * math.sin(2 * math.pi * cycles * i / n)
        pts.append(sm.SeriesPoint(mjd=mjd, airmass=airmass, err=0.005,
                                  mag=8.0 + trend + sine))
    info = sm.detrend_series(pts, policy="airmass")
    assert info is not None
    det = np.asarray(info["detrended"], dtype=np.float64)
    det = det - det.mean()
    inj = np.asarray([0.15 * math.sin(2 * math.pi * cycles * i / n)
                      for i in range(n)])
    assert (det.max() - det.min()) == pytest.approx(0.30, rel=0.1)
    assert float(np.corrcoef(det, inj)[0, 1]) > 0.95
    assert info["rms_after"] < info["rms_before"]


def test_two_nights_transparency_offset_is_flat_after_detrend():
    # Two nights with a 3 % transparency offset: the per-night detrend
    # flattens the curve; the raw one jumps.
    pts = []
    for i in range(6):
        pts.append(sm.SeriesPoint(mjd=61300.2 + i * 0.001, airmass=1.2,
                                  err=0.005, mag=8.0, fwhm=4.0, sky=100.0,
                                  x=80.0, y=80.0))
    for i in range(6):
        pts.append(sm.SeriesPoint(mjd=61301.2 + i * 0.001, airmass=1.2,
                                  err=0.005, mag=8.03, fwhm=4.0, sky=100.0,
                                  x=80.0, y=80.0))
    raw = [p.mag for p in pts]
    assert max(raw) - min(raw) == pytest.approx(0.03, abs=1e-6)
    info = sm.detrend_series(pts, policy="airmass")
    det = [d for d in info["detrended"]]
    assert max(det) - min(det) < 1e-6
    # both nights fell back to an offset (constant airmass)
    assert all(n["fallback"] == "offset" for n in info["nights"])


def test_short_night_falls_back_to_offset():
    pts = [sm.SeriesPoint(mjd=61300.2 + i * 0.01, airmass=1.0 + 0.2 * i,
                          err=0.005, mag=8.0 + i * 0.01)
           for i in range(2)]
    info = sm.detrend_series(pts, policy="airmass")
    assert info is not None
    assert info["nights"][0]["fallback"] == "offset"


def test_sweep_aperture_picks_per_night(tmp_path):
    # Two nights with different seeing: the T3 sweep returns per-night
    # radii that follow the FWHM (larger seeing -> larger aperture).
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    nights = [("2026-09-20T23:30:00", 2.0), ("2026-09-21T23:30:00", 4.5)]
    paths = []
    for j, (date, sigma) in enumerate(nights):
        for i in range(5):
            data = _plate_sigma(sigma, noise=3.0, seed=100 + 10 * j + i)
            paths.append(_write_plate(tmp_path / f"n{j}_{i}.fits", data,
                                      date_obs=date))
    swept = sm.sweep_aperture(paths, _config(wcs, comps))
    assert len(swept) == 2
    radii = [swept[k]["radii"][0] for k in swept]
    assert all(1.0 <= swept[k]["k"] <= 2.0 for k in swept)
    assert abs(radii[0] - radii[1]) > 0.5     # the seeing drives it


def test_measure_series_auto_aperture_runs(tmp_path):
    paths, wcs, comps = _write_frames(tmp_path, 5, noise=1.0)
    res = sm.measure_series(paths, _config(wcs, comps,
                                           auto_aperture=True))
    assert res.points                      # the sweep ran and measured
    assert res.apertures                   # per-night entry recorded
