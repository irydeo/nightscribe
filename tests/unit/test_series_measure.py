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
import weakref
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
# Seeing disc used by the focus-excursion tests: small enough that the
# 19 px FWHM cutout measures both the sharp and the broadened frames
# without truncating them (the default SIGMA is a very broad PSF here).
_SEEING_SIGMA = 1.2


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


def _plate(target_amp=7000.0, sky=100.0, noise=0.0, seed=1, gradient=0.0,
           sigma=SIGMA):
    data = np.full((H, W), sky, dtype=np.float64)
    yy, xx = np.ogrid[:H, :W]
    if gradient:
        data += gradient * (xx - TARGET_XY[0])
    for sx, sy, amp in _stars(target_amp):
        data += amp * np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2)
                             / (2 * sigma ** 2))
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


def test_fwhm_is_measured_on_every_frame(tmp_path):
    # P3: each point carries its OWN frame's seeing (measured on the target
    # and the comps it used), so the detrend's "auto" FWHM column is real
    # and a defocused frame is visible in the point's metadata. The seeing
    # varies inside estimate_fwhm's range (a 19x19 cutout truncates a very
    # broad disc).
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    paths = []
    for i, sigma in enumerate((1.5, 1.5, SIGMA)):
        data = _plate(sigma=sigma)
        paths.append(_write_plate(tmp_path / f"w{i}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    res = sm.measure_series(paths, _config(wcs, comps))
    fwhms = [p.fwhm for p in res.points]
    assert all(f is not None for f in fwhms)
    assert fwhms[0] == pytest.approx(2.3548 * 1.5, rel=0.05)
    assert fwhms[1] == pytest.approx(fwhms[0], rel=0.05)
    assert fwhms[2] > 1.5 * fwhms[0]              # the defocused frame
    # a group collapses to the median of its members' own seeing, never to
    # the first member's
    grouped = sm.measure_series([paths[0], paths[2]],
                                _config(wcs, comps, group_n=2))
    assert len(grouped.points) == 1
    assert fwhms[0] < grouped.points[0].fwhm < fwhms[2]


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
    # and the one it dropped is the one that flared, not an arbitrary one
    assert "C1" not in (res.points[2].zp_used or [])
    assert "C1" in (res.points[0].zp_used or [])


# ---------------- D12 anchor (d): a flagged point stays ----------------

def test_a_cloud_is_flagged_when_the_psf_does_not_change(tmp_path):
    # A thin cloud dims the WHOLE field with the same seeing: the zero
    # point moves and the FWHM does not. That is a cloud, and it is
    # flagged as one (quality plan, B2).
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    paths = []
    for i in range(6):
        data = _plate(noise=0.3, seed=20 + i)
        if i == 3:
            # dim everything but the target: the comps lose flux, so the
            # zero point of that frame drops
            yy, xx = np.ogrid[:H, :W]
            for cx, cy in COMP_XY + [CHECK_XY]:
                data -= 1500.0 * np.exp(-((xx - cx) ** 2
                                          + (yy - cy) ** 2)
                                        / (2 * SIGMA ** 2))
        paths.append(_write_plate(tmp_path / f"c{i:03d}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    res = sm.measure_series(paths, _config(wcs, comps))
    flags = [f for p in res.points for f in p.flags]
    assert "cloud" in flags
    assert "seeing" not in flags
    assert res.seeing_report["flagged"] == 0


def test_a_focus_excursion_is_seeing_not_cloud(tmp_path):
    # Two frames of the night lose their focus: the PSF balloons, the sky
    # does not move and the flux leaves a fixed aperture. The engine must
    # flag `seeing` (and NOT `cloud`, which would send the observer to
    # look at the sky), and the aperture must follow the seeing so the
    # lost flux comes back (quality plan, B1/B2).
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    paths = []
    for i in range(8):
        wide = i in (3, 4)
        # a seeing disc the 19 px FWHM cutout can still measure honestly:
        # at the test's default sigma the cutout truncates the broad frame
        # and the ratio it sees is far smaller than the injected one
        data = _plate(noise=0.3, seed=30 + i,
                      sigma=_SEEING_SIGMA * (2.0 if wide else 1.0))
        paths.append(_write_plate(tmp_path / f"s{i:03d}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    res = sm.measure_series(paths, _config(wcs, comps))
    flags = [f for p in res.points for f in p.flags]
    assert "seeing" in flags
    assert "cloud" not in flags
    assert res.seeing_report["flagged"] >= 2
    wide = [p for p in res.points if "seeing" in p.flags]
    assert all(p.fwhm > 1.5 * np.median([q.fwhm for q in res.points])
               for p in wide)


def test_the_aperture_follows_the_seeing_and_recovers_the_flux(tmp_path):
    # The same excursion measured with the aperture following the seeing:
    # the observer's radius (4 px on a 2.8 px FWHM, as tight as real use)
    # scales with each frame's FWHM, so the defocused frame stops losing
    # its light.
    #
    # Read the premise, because it is the honest part of this test: the
    # scaling only pays when the reference aperture sits close to the
    # PSF. With a deliberately generous aperture (6 px on a 2.8 px FWHM)
    # the fixed one already holds the whole star, and nothing improves
    # because there is nothing to recover.
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    radii = (4.0, 8.0, 12.0)
    paths = []
    for i in range(8):
        wide = i in (3, 4)
        data = _plate(noise=0.3, seed=30 + i,
                      sigma=_SEEING_SIGMA * (1.8 if wide else 1.0))
        paths.append(_write_plate(tmp_path / f"f{i:03d}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    fixed = sm.measure_series(paths, _config(wcs, comps, radii=radii))
    scaled = sm.measure_series(paths, _config(wcs, comps, radii=radii,
                                              seeing_aperture=True))
    assert scaled.aperture_report["scaled"] >= 2
    assert scaled.aperture_report["scale_max"] > 1.5
    # the defocused points move closer to the level of the sharp ones
    def spread(res):
        mags = [p.mag for p in res.points]
        clean = float(np.median([m for m in mags]))
        return max(abs(m - clean) for m in mags)
    assert spread(scaled) < spread(fixed)


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


def test_grouped_exoclock_start_is_the_first_frame_start(tmp_path):
    # End to end through the real engine (review #10): with group_n=3 the
    # ExoClock JD_UTC must be the start of the group's first frame, not
    # the mid time biased by (span - exptime)/2. Frames here start at
    # 23:30/23:31/23:32 with 10 s each, so the true start of group 1 is
    # 2026-09-20T23:30:00 UTC.
    from nightscribe.core import exoclock_export, fits_meta, variables
    paths, wcs, comps = _write_frames(tmp_path, 6)
    res = sm.measure_series(paths, _config(wcs, comps, group_n=3))
    assert res.status == "complete" and len(res.points) == 2
    pts = [{"mjd": p.mjd, "jd_start": p.jd_start, "mag": p.mag,
            "err": p.err, "exptime": p.exptime, "flags": list(p.flags)}
           for p in res.points]
    rows, warnings, _mode = exoclock_export.build_data(pts)
    assert warnings == []
    # independent anchor: DATE-OBS of the first frame IS the start of
    # the group's first exposure (the engine times at DATE-OBS + exp/2)
    want = fits_meta.read_meta(paths[0])["mjd"]
    assert want is not None
    assert rows[0][0] == pytest.approx(want + variables.MJD0, abs=1e-6)


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


# ---------------- memory: frames are never accumulated ----------------

def _watch_reads(monkeypatch):
    # Spy on fits_io.read_fits that counts how many of the returned frame
    # arrays are alive at once (weakrefs, no strong reference kept).
    # @args: monkeypatch - the pytest fixture
    # @return: (live id set, peak holder list with the maximum count)
    live = set()
    peak = [0]
    real_read = sm.fits_io.read_fits

    def spy(path):
        header, data = real_read(path)
        wid = id(data)
        live.add(wid)
        weakref.finalize(data, live.discard, wid)
        peak[0] = max(peak[0], len(live))
        return header, data

    monkeypatch.setattr(sm.fits_io, "read_fits", spy)
    return live, peak


def test_measure_series_releases_frame_arrays(tmp_path, monkeypatch):
    # P0: a 300-frame series must never hold 300 images in RAM. Each
    # frame is measured and flagged (cosmic gate included) inside the
    # loop and its array released there: at most the frame being read
    # and the one being measured are alive at any time.
    paths, wcs, comps = _write_frames(tmp_path, 50, noise=0.5)
    _live, peak = _watch_reads(monkeypatch)
    res = sm.measure_series(paths, _config(wcs, comps))
    assert len(res.points) == 50               # the series is complete
    assert peak[0] <= 2, f"{peak[0]} frame arrays alive at once"


def test_sweep_aperture_keeps_fluxes_not_images(tmp_path, monkeypatch):
    # T3: the k sweep accumulates per-frame magnitudes and FWHM, never
    # the images; at most the frame being read and the one being swept
    # are alive at any time.
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    paths = []
    for i in range(8):
        data = _plate(noise=0.5, seed=200 + i)
        paths.append(_write_plate(tmp_path / f"m{i}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    _live, peak = _watch_reads(monkeypatch)
    swept = sm.sweep_aperture(paths, _config(wcs, comps))
    assert swept                               # the sweep really measured
    assert peak[0] <= 2, f"{peak[0]} frame arrays alive at once"


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


# ---------------- phase 6: cadence guard, multi-night QC, analysis ---

def _pts(n, cadence_s, mjd0=61300.2, **kw):
    return [sm.SeriesPoint(mjd=mjd0 + i * cadence_s / 86400.0, **kw)
            for i in range(n)]


def test_cadence_guard_transit_ingress():
    # 2.5 h transit: the ingress window is 0.15*9000 = 1350 s. A 60 s
    # cadence resolves it; a 900 s one leaves 1.5 points (red).
    good = sm.cadence_guard(_pts(30, 60), "transit", duration_h=2.5)
    assert good["level"] == "ok" and not good["messages"]
    bad = sm.cadence_guard(_pts(20, 900), "transit", duration_h=2.5)
    assert bad["level"] == "red" and bad["messages"]


def test_cadence_guard_hads_and_variable():
    hads = sm.cadence_guard(_pts(10, 1000), "hads", period_h=2.0)
    assert hads["level"] == "warn"
    var = sm.cadence_guard(_pts(10, 5000), "variable", period_d=0.1)
    assert var["level"] == "warn"
    fine = sm.cadence_guard(_pts(40, 200), "variable", period_d=0.1)
    assert fine["level"] == "ok"


def test_night_qc_band_and_zp():
    pts = []
    for i, (night, filt, zp) in enumerate([
            (61300.2, "V", 22.00), (61301.2, "V", 22.01),
            (61302.2, "V", 22.02), (61303.2, "V", 22.50)]):
        pts.append(sm.SeriesPoint(mjd=night, filter=filt, zp=zp,
                                  mag=10.0))
    qc = sm.night_qc(pts)
    assert qc["level"] == "warn"
    assert any("22.50" in m["es"] or "desplazado" in m["es"]
               for m in qc["messages"])
    # a second filter trips the band guard
    pts[0].filter = "R"
    qc2 = sm.night_qc(pts)
    assert any("filtros" in m["es"] for m in qc2["messages"])
    assert qc2["filters"] == ["R", "V"]


def test_build_payload_carries_measure_points_and_folds():
    # D24/D33: the series points (source "measure") flow into the analysis
    # payload as any other, and a variable still folds by its VSX period.
    from nightscribe.core import lightcurve_data as lc
    pts = [{"mjd": 61300.2, "mag": 12.0, "source": "measure",
            "filter": "V"},
           {"mjd": 61300.3, "mag": 11.9, "source": "measure",
            "filter": "V"}]
    payload = lc.build_payload({"points": pts})
    assert len(payload["points"]) == 2
    var = {"period_d": 0.5, "epoch_mjd": 0.2, "amp": 0.3,
           "max": 12.0, "min": 12.3}
    folded = lc.build_payload({"points": pts}, variable=var)
    assert folded["fold_period_d"] == 0.5
    assert folded["epoch_mjd"] == 0.2
    assert "schematic" in folded


# ---------------- phase 7B: opt-in per-frame registration -------------

def test_series_alignment_recovers_a_drifting_field(tmp_path):
    # A field that translates between frames (an alt-az mount without
    # derotation, no WCS): with align="off" the fixed-coordinate recipe
    # cannot follow it; with align="similarity" the curve is flat.
    from nightscribe.core import register
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    ref = _plate(noise=1.0, seed=70)
    # a drifting AND rotating field (an alt-az mount without derotation)
    moves = [(0.0, 0, 0), (3.0, 6, -4), (-4.0, -5, 8), (5.0, 10, 5),
             (-6.0, -8, -6), (2.0, 4, 9)]
    paths = []
    for i, (ang, dx, dy) in enumerate(moves):
        data = register.apply_transform(ref, math.radians(ang), dx, dy)
        paths.append(_write_plate(tmp_path / f"a{i}.fits", data,
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    cfg = _config(wcs, comps, align="similarity", guide_jump_px=1.0)
    res = sm.measure_series(paths, cfg)
    mags = [p.mag for p in res.points if p.mag is not None]
    assert len(mags) == len(moves)
    assert float(np.std(mags)) < 0.02
    # without alignment the fixed coordinates measure a rotated field and
    # the differential curve scatters (or points drop out)
    res_off = sm.measure_series(paths, _config(wcs, comps))
    mags_off = [p.mag for p in res_off.points if p.mag is not None]
    assert len(mags_off) < len(moves) or float(np.std(mags_off)) > 0.05


def test_warp_edge_fill_is_flagged(tmp_path):
    # Review #16: the warp zero-fills the off-footprint strip; with a
    # near-zero sky that inflates the flux. A 40 px shift pushes the
    # invalid strip over the comp at x=45 (r_ap box reaches x~39), so
    # the point must carry "align_edge" (flags mark, never delete).
    from nightscribe.core import register
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    ref = _plate(noise=1.0, seed=70)
    paths = [_write_plate(tmp_path / "e0.fits", ref,
                          date_obs="2026-09-20T23:30:00")]
    shifted = register.apply_transform(ref, 0.0, 40.0, 0.0)
    paths.append(_write_plate(tmp_path / "e1.fits", shifted,
                              date_obs="2026-09-20T23:31:00"))
    res = sm.measure_series(paths, _config(wcs, comps, align="warp"))
    assert len(res.points) == 2
    assert "align_edge" in res.points[1].flags
    assert "align_edge" not in res.points[0].flags


def test_low_quality_registration_is_flagged(tmp_path):
    # Review #16: a frame with no common structure (pure noise) must not
    # be silently trusted: under the null hypothesis the correlation
    # peak is ~sqrt(2 ln N) ~ 5-6, far below QUALITY_MIN.
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    ref = _plate(noise=1.0, seed=70)
    paths = [_write_plate(tmp_path / "n0.fits", ref,
                          date_obs="2026-09-20T23:30:00")]
    noise = np.random.default_rng(5).normal(100, 1.0, (H, W))
    paths.append(_write_plate(tmp_path / "n1.fits", noise,
                              date_obs="2026-09-20T23:31:00"))
    res = sm.measure_series(paths, _config(wcs, comps, align="warp"))
    assert len(res.points) == 2
    assert "align_failed" in res.points[1].flags
    assert "align_failed" not in res.points[0].flags


# ---------------- moving targets (a NEO, a comet) ----------------------

def _moving_plate(offset_px, sigma=SIGMA):
    # The same field, with the TARGET drawn at a different place: the comps
    # and the check stay put (the field is fixed), only the object walks.
    data = _plate(sigma=sigma, sky=100.0, noise=0.0)
    yy, xx = np.ogrid[:H, :W]
    data -= 7000.0 * np.exp(-((xx - TARGET_XY[0]) ** 2
                              + (yy - TARGET_XY[1]) ** 2)
                            / (2 * sigma ** 2))
    data += 7000.0 * np.exp(-((xx - (TARGET_XY[0] + offset_px)) ** 2
                              + (yy - TARGET_XY[1]) ** 2)
                            / (2 * sigma ** 2))
    return data


def _motion_from_offsets(offsets):
    # The ephemeris that goes with _moving_plate: it answers "where is the
    # object" with the sky position of the star that was drawn for that
    # frame. The frames are one minute apart (the test writes them so), and
    # the engine asks with the MIDDLE of the exposure, so the sample is
    # picked from the fraction of a day.
    import datetime
    from nightscribe.core import coords
    wcs = _reference_wcs()
    # the first frame's instant, built the same way the engine does it:
    # never a hardcoded Julian date in a test
    base = coords.jd_from_datetime(
        datetime.datetime(2026, 9, 20, 23, 30,
                          tzinfo=datetime.timezone.utc))

    def motion(jd):
        # the frames are one minute apart, and the engine asks with the
        # MIDDLE of the exposure, so the sample is the minute of the frame
        idx = int(round((jd - base) * 1440.0))
        idx = max(0, min(len(offsets) - 1, idx))
        return wcs.pixel_to_sky(TARGET_XY[0] + offsets[idx], TARGET_XY[1])
    return motion


def test_a_moving_target_is_measured_where_the_ephemeris_says(tmp_path):
    # A NEO walks 3 px per frame across a fixed field (232 px in 8 frames:
    # it leaves any sane aperture). With the ephemeris the engine measures
    # it where it is and the curve stays flat; without it, the aperture
    # watches the empty sky behind.
    offsets = [3.0 * i for i in range(8)]
    paths = []
    for i, off in enumerate(offsets):
        paths.append(_write_plate(tmp_path / f"m{i}.fits",
                                  _moving_plate(off),
                                  date_obs=f"2026-09-20T23:{30 + i:02d}:00"))
    wcs = _reference_wcs()
    comps = _comp_set(wcs)

    fixed = sm.measure_series(paths, _config(wcs, comps))
    mags_fixed = [p.mag for p in fixed.points if p.mag is not None]
    # the moving target ruins the fixed-coordinate curve
    assert max(mags_fixed) - min(mags_fixed) > 0.5

    moved = sm.measure_series(paths, _config(
        wcs, comps, target_motion=_motion_from_offsets(offsets)))
    mags = [p.mag for p in moved.points if p.mag is not None]
    assert len(mags) == len(paths)
    assert max(mags) - min(mags) < 0.05


# ---------------- a campaign pass: several targets, one read ----------

# A second object of the same field, well clear of the comps (the nearest
# one is 34 px away, the annulus ends at 15) and of the main target.
SECOND_XY = (80.4, 45.0)


def _plate_two(target_amp=7000.0, second_amp=3200.0, sky=100.0, noise=0.0,
               seed=1, sigma=SIGMA):
    # The same field as _plate, plus a second object: the campaign case,
    # where the frames carry two variables and the comps serve both.
    data = np.full((H, W), sky, dtype=np.float64)
    yy, xx = np.ogrid[:H, :W]
    stars = [(TARGET_XY[0], TARGET_XY[1], target_amp),
             (SECOND_XY[0], SECOND_XY[1], second_amp)]
    stars += [(x, y, a) for (x, y), a in
              zip(COMP_XY, (11000, 10500, 11500, 10800, 10200))]
    stars.append((CHECK_XY[0], CHECK_XY[1], 9000.0))
    for sx, sy, amp in stars:
        data += amp * np.exp(-((xx - sx) ** 2 + (yy - sy) ** 2)
                             / (2 * sigma ** 2))
    if noise > 0.0:
        data += np.random.default_rng(seed).normal(0.0, noise, (H, W))
    return data


def _write_pass_frames(tmp_path, n=6, second_amp=3200.0):
    paths = []
    for i in range(n):
        data = _plate_two(second_amp=second_amp, seed=1 + i)
        date = f"2026-09-20T23:{30 + i:02d}:00"
        paths.append(_write_plate(tmp_path / f"pass{i:03d}.fits", data,
                                  date_obs=date, exptime=10.0))
    return paths


def _both_targets():
    return (("A", TARGET_XY[0], TARGET_XY[1]),
            ("B", SECOND_XY[0], SECOND_XY[1]))


def test_a_pass_measures_every_target_with_one_ensemble(tmp_path):
    # Two objects of the same field, one read of the frames: each gets its
    # own curve, flat, and the comparison stars (therefore the ensemble
    # and the zero point) are the same for both.
    paths = _write_pass_frames(tmp_path)
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    cfg = _config(wcs, comps)
    passed = sm.measure_pass(paths, cfg, targets=_both_targets())
    assert passed.status == "complete"
    assert [t["label"] for t in passed.targets] == ["A", "B"]
    for entry in passed.targets:
        result = entry["result"]
        assert result.target_label == entry["label"]
        pts = [p for p in result.points if p.mag is not None]
        assert len(pts) == len(paths)
        mags = [p.mag for p in pts]
        assert max(mags) - min(mags) < 0.02
    # one ensemble for both: the zero point of the frame is the comps', and
    # the comps are the same stars
    zp_a = passed.targets[0]["result"].points[0].zp
    zp_b = passed.targets[1]["result"].points[0].zp
    assert zp_a == pytest.approx(zp_b, abs=1e-9)


def test_a_pass_curve_is_the_curve_a_solo_run_gives(tmp_path):
    # Parity, the acceptance of the feature: measuring two objects together
    # must not change either object's numbers. If it did, the saving would
    # be paid in science.
    paths = _write_pass_frames(tmp_path)
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    passed = sm.measure_pass(paths, _config(wcs, comps),
                             targets=_both_targets())
    solo_a = sm.measure_series(paths, _config(wcs, comps))
    solo_b = sm.measure_series(paths, _config(wcs, comps,
                                              target_xy=SECOND_XY))
    for got, want in zip(passed.targets[0]["result"].points, solo_a.points):
        assert got.mag == pytest.approx(want.mag, abs=1e-9)
        assert got.err == pytest.approx(want.err, abs=1e-12)
    for got, want in zip(passed.targets[1]["result"].points, solo_b.points):
        assert got.mag == pytest.approx(want.mag, abs=1e-9)
        assert got.err == pytest.approx(want.err, abs=1e-12)
    # the shared blocks are the pass's, and they are copied to each curve
    assert passed.targets[0]["result"].align_report == \
        passed.targets[1]["result"].align_report
    assert (passed.targets[0]["result"].gain_report
            == passed.targets[1]["result"].gain_report)


def test_the_pass_measures_the_comps_once_per_frame(tmp_path, monkeypatch):
    # The saving, measured: adding a target costs ONE measurement per
    # frame, not a whole second pass over the comparison stars.
    paths = _write_pass_frames(tmp_path, n=5)
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    cfg = _config(wcs, comps)
    calls = []
    real = phot.measure_point

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(phot, "measure_point", counting)
    sm.measure_series(paths, cfg)
    solo = len(calls)
    calls.clear()
    sm.measure_pass(paths, cfg, targets=_both_targets())
    both = len(calls)
    assert both - solo == len(paths)      # one more target per frame
    assert both < 2 * solo                # and nothing else was repeated
    assert both == len(paths) * (2 + 6)   # 2 targets + 5 comps + 1 check


def test_a_lost_target_does_not_take_the_other_with_it(tmp_path):
    # A wrong coordinate (or a satellite trail, or an object out of the
    # field) loses ITS curve and says why; the sibling is measured as if
    # nothing had happened. Mark, never delete; and never drag the other
    # down with it.
    paths = _write_pass_frames(tmp_path, n=4)
    wcs = _reference_wcs()
    comps = _comp_set(wcs)
    passed = sm.measure_pass(
        paths, _config(wcs, comps),
        targets=(("A", TARGET_XY[0], TARGET_XY[1]), ("lost", 4.0, 4.0)))
    good = passed.targets[0]["result"]
    assert len([p for p in good.points if p.mag is not None]) == len(paths)
    lost = passed.targets[1]["result"]
    assert all(p.mag is None for p in lost.points)
    assert all("unusable" in p.flags for p in lost.points)
    assert passed.status == "complete"


def test_the_engine_builds_the_rows_a_host_persists(tmp_path):
    # One shape for a single series and for a campaign pass: the GUI and
    # the pass both persist this, and two copies of it would drift the
    # moment one of them gains a column.
    paths = _write_pass_frames(tmp_path, n=3)
    wcs = _reference_wcs()
    res = sm.measure_series(paths, _config(wcs, _comp_set(wcs)))
    rows = sm.series_rows(res.points)
    assert len(rows) == len(paths)
    # airmass and the measured position travel with the point: the night
    # figures are made of them, and a curve read back from the database has
    # to be able to explain its night
    assert set(rows[0]) == {"mjd", "filter", "mag", "err", "err_internal",
                            "mag_raw", "path", "flags", "source",
                            "airmass", "x", "y", "fwhm", "sky"}
    assert rows[0]["source"] == "measure"
    assert rows[0]["path"] in [str(p) for p in paths]
    # a point without a time cannot be placed on a curve: it is not a row
    res.points[1].mjd = None
    assert len(sm.series_rows(res.points)) == len(paths) - 1


def test_a_comparison_star_off_the_frame_does_not_kill_the_run(tmp_path):
    # The real failure: a HAT-P-32 b sequence of 142 frames died at frame
    # ~18 with "negative dimensions are not allowed" because one comparison
    # star of the sequence fell off the top of the frame and the seeing
    # estimation sliced a negative window. A star that is not there is not
    # an error, and it must not cost the observer the whole night.
    paths, wcs, comps = _write_frames(tmp_path, 4)
    off = wcs.pixel_to_sky(4000.0, -4000.0)          # far outside 160x160
    broken = list(comps)
    broken[-1] = dict(comps[-1],
                      star=dict(comps[-1]["star"], ra=off[0], dec=off[1]))
    cfg = _config(wcs, broken, seeing_aperture=True)
    res = sm.measure_series(paths, cfg)
    assert res.status == "complete"
    pts = [p for p in res.points if p.mag is not None]
    assert len(pts) == len(paths)          # the target is measured
    assert all(p.err is not None for p in pts)
    # the star that was not there is skipped, never silently "measured"
    assert all(p.n_comps < len(broken) for p in pts)


def test_with_every_spot_off_frame_there_is_still_no_crash(tmp_path):
    # The extreme of the same case: EVERY comparison star off the frame.
    # There is no zero point to be had, so there are no magnitudes; what
    # must never happen is the run dying with an exception instead of
    # saying it plainly.
    paths, wcs, comps = _write_frames(tmp_path, 3)
    far = []
    for e in comps:
        ra, dec = wcs.pixel_to_sky(9000.0, 9000.0)
        far.append(dict(e, star=dict(e["star"], ra=ra, dec=dec)))
    cfg = _config(wcs, far, seeing_aperture=True)
    res = sm.measure_series(paths, cfg)
    assert res.status == "complete"                  # never a crash
    assert all(p.mag is None for p in res.points)    # no comps, no zero point
    assert any("few_comps" in p.flags for p in res.points)


def test_an_inherited_alignment_does_not_crash_the_report(tmp_path,
                                                          monkeypatch):
    # The second failure of the same real run (HAT-P-32 b, 142 frames): a
    # frame whose alignment cannot be verified INHERITS the previous
    # transform, and the report then read used["shift_px"] off that
    # inherited dict, which never carried it: KeyError, dead run.
    #
    # A report is diagnostic. It must never be able to stop a measurement,
    # so the inherited transform now travels complete AND the report reads
    # every field defensively.
    paths, wcs, comps = _write_frames(tmp_path, 5)
    from nightscribe.core import register
    calls = {"n": 0}
    real = register.trusted

    def sometimes(info, *a, **k):
        calls["n"] += 1
        return calls["n"] not in (2, 4)      # the 2nd and 4th are refused

    monkeypatch.setattr(register, "trusted", sometimes)
    res = sm.measure_series(paths, _config(wcs, comps, align="coords"))
    assert res.status == "complete"
    rep = res.align_report
    assert rep["inherited"] == 2
    assert rep["n_failed"] == 2
    # the first frame IS the reference (nothing to align it to), so the
    # rest are all aligned, the two refused ones through inheritance
    assert rep["aligned"] == len(paths) - 1
    # and the report still carries the numbers, inherited frames included
    # (the previous transform's own shift, which is the honest value)
    assert "shift_median_px" in rep and "shift_max_px" in rep
    monkeypatch.setattr(register, "trusted", real)
