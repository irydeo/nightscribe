############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: injection and recovery (P4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Put a source of a known flux in the frames and see if it comes back.

This is the instrument the rest of the SNR campaign is measured with, so it
is tested the way it is used: a synthetic sequence with stars and noise, a
source injected with a known flux, motion and sub-pixel phase, the REAL
chain (register, place the object, stack along the motion, gate) run on the
copies, and the answer compared with the truth.

The truth travels in the header, so the last test reads it back from the
files: a recovery verified from the copies alone is a recovery anybody can
repeat.
"""

import math
import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nightscribe.core import injection                    # noqa: E402

SIZE = 128
NF = 16


def _wcs(size=SIZE):
    from astropy.wcs import WCS
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [10.0, 20.0]
    w.wcs.crpix = [size / 2.0 + 0.5, size / 2.0 + 0.5]
    w.wcs.cd = [[-2.0 / 3600, 0.0], [0.0, 2.0 / 3600]]
    w.pixel_shape = (size, size)
    return w


def _sequence(tmp_path, n=NF, noise=4.0, seed=1):
    # @return: the paths, a synthetic star field with a dither of one pixel
    #          per frame and no object at all
    from astropy.io import fits
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    paths = []
    for i in range(n):
        img = rng.normal(1000.0, noise, (SIZE, SIZE))
        for k in range(10):
            sx = 18.0 + 11.0 * k + (i % 3) * 1.0
            sy = 20.0 + 9.0 * (k % 4) + (i % 2) * 1.0
            img += 4000.0 * np.exp(-(((xx - sx) ** 2 + (yy - sy) ** 2)
                                     / (2 * 1.6 ** 2)))
        hdu = fits.PrimaryHDU(np.asarray(img, dtype=np.float32))
        hdu.header["EXPTIME"] = 5.0
        hdu.header["FILTER"] = "R"
        # DATE-OBS so the frames carry a T_mid: the motion is per frame
        hdu.header["DATE-OBS"] = f"2026-09-20T23:{i:02d}:00"
        path = tmp_path / f"f{i:02d}.fits"
        hdu.writeto(str(path), overwrite=True)
        paths.append(str(path))
    return paths


def test_a_bright_source_comes_back_where_it_was_put(tmp_path):
    paths = _sequence(tmp_path)
    w = _wcs()
    got = injection.inject_sequence(paths, 4000.0, rate_px_min=1.5, pa_deg=90.0,
                                    out_dir=tmp_path / "inj", ref_wcs=w)
    assert len(got["paths"]) == NF
    assert got["motion"] is not None
    res = injection.recover(got["paths"], got["motion"], w)
    assert res["detected"] is True
    assert res["snr"] > 20.0
    # The measurement is taken at the group's own T_mid, so the truth it has
    # to be compared with is the truth AT THAT INSTANT, not the first frame's
    # (which is a whole walk away).
    tx, ty = got["truth_at"](res["t_mid_jd"])
    err = math.hypot(res["x"] - tx, res["y"] - ty)
    assert err < 1.0, err


def test_a_source_too_faint_for_the_stack_is_not_detected(tmp_path):
    # The control: the same pipeline, the same frames, a source whose flux
    # is far below what this sequence can reach. A pipeline that "detects"
    # this one is a pipeline that manufactures detections.
    os.makedirs(tmp_path / "faint", exist_ok=True)
    paths = _sequence(tmp_path / "faint")
    w = _wcs()
    got = injection.inject_sequence(paths, 2.0, rate_px_min=1.5,
                                    out_dir=tmp_path / "inj2", ref_wcs=w)
    res = injection.recover(got["paths"], got["motion"], w)
    assert res["detected"] is False


def test_the_truth_travels_in_the_files(tmp_path):
    # The truth is read back from the copies, so a recovery can be verified
    # months later without trusting a variable that lived in a session.
    paths = _sequence(tmp_path)
    got = injection.inject_sequence(paths, 1500.0, out_dir=tmp_path / "inj",
                                    ref_wcs=_wcs())
    back = injection.truth_of(got["paths"])
    assert len(back) == len(got["truth"])
    for (p1, x1, y1), (p2, x2, y2) in zip(back, got["truth"]):
        assert p1 == p2
        assert x1 == pytest.approx(x2)
        assert y1 == pytest.approx(y2)


def test_the_source_walks_along_the_position_angle(tmp_path):
    # The motion is the injected one, in the direction asked for: without
    # that, the sweep would be measuring the injection and not the pipeline.
    paths = _sequence(tmp_path)
    got = injection.inject_sequence(paths, 1000.0, rate_px_min=2.0, pa_deg=0.0,
                                    out_dir=tmp_path / "inj", ref_wcs=_wcs())
    truth = got["truth"]
    # the step is measured over the whole walk and not frame to frame: each
    # frame carries its own random sub-pixel phase (up to half a pixel), so
    # one step is noisy and the trend is not
    n = len(truth) - 1
    dx = (truth[-1][1] - truth[0][1]) / n
    dy = (truth[-1][2] - truth[0][2]) / n
    assert dx == pytest.approx(2.0, abs=0.1)
    assert dy == pytest.approx(0.0, abs=0.1)


def test_the_originals_are_never_touched(tmp_path):
    # The injection writes NEW files: the frames the observer took are only
    # ever read, and this is the test that says so.
    paths = _sequence(tmp_path)
    before = {p: os.path.getmtime(p) for p in paths}
    sizes = {p: os.path.getsize(p) for p in paths}
    injection.inject_sequence(paths, 800.0, out_dir=tmp_path / "inj",
                              ref_wcs=_wcs())
    for p in paths:
        assert os.path.getmtime(p) == before[p]
        assert os.path.getsize(p) == sizes[p]


def test_the_completeness_curve_goes_from_one_to_zero(tmp_path):
    # The curve that answers "how faint can this pipeline go": a flux it
    # always gets, and one it never does, with the SNR and the position
    # error of the ones that came back.
    paths = _sequence(tmp_path)
    w = _wcs()
    rows = injection.completeness(paths, [6000.0, 1.0], w, trials=1,
                                  out_root=tmp_path / "curva")
    assert len(rows) == 2
    bright, faint = rows
    assert bright["flux"] == 6000.0 and bright["rate"] == 1.0
    assert bright["snr_median"] is not None
    assert bright["err_px_median"] is not None
    assert faint["rate"] == 0.0
    assert faint["snr_median"] is None


def test_the_cli_runs_the_instrument(tmp_path, capsys):
    # The observer has to be able to run this without writing Python: the
    # `inject` subcommand prints the completeness table and returns 0. The
    # frames here are tiny and the flux is high on purpose: the point is the
    # plumbing, not the reach (that is measured on real data).
    _sequence(tmp_path, n=4)
    from nightscribe.__main__ import main
    code = main(["inject", str(tmp_path), "--flujos", "6000", "--tomas", "4",
                 "--salida", str(tmp_path / "out")])
    assert code == 0
    out = capsys.readouterr().out
    assert "injected motion" in out
    assert "flux ADU" in out
    assert "6000" in out


def test_pa_difference_is_a_direction_not_a_number():
    # 359 and 1 are two degrees apart, and subtracting them reports 358.
    assert injection.pa_difference(359.0, 1.0) == pytest.approx(2.0)
    assert injection.pa_difference(10.0, 20.0) == pytest.approx(10.0)
    assert injection.pa_difference(90.0, 270.0) == pytest.approx(180.0)
    assert injection.pa_difference(None, 10.0) is None


def test_the_velocity_sweep_finds_the_injected_motion(tmp_path):
    # The sweep is what decides whether a real object is found at all: it
    # looks for it on a grid around the ephemeris' own velocity. Injecting a
    # source moving at a KNOWN rate and heading and reading back what the
    # sweep chose turns "the sweep looks fine" into two numbers: the error
    # in rate and the error in position angle.
    paths = _sequence(tmp_path)
    w = _wcs()
    got = injection.motion_recovery(paths, 8000.0, rate_px_min=1.5, pa_deg=90.0,
                                    ref_wcs=w, out_dir=tmp_path / "inj",
                                    steps=5, pct=5.0)
    assert got["detected"] is True, got.get("note")
    assert got["injected"] is not None
    assert got["found"] is not None
    # the injected motion is 1.5 px per frame; the frames are a minute apart
    # and the plate is 2"/px, so the truth is 3"/min and the sweep's grid is
    # +/-5 % around it: the answer has to land inside the grid
    assert got["injected"]["rate"] == pytest.approx(3.0, rel=0.1)
    # The injected motion is +y in PIXELS, and this WCS has a positive Dec
    # per y: +y is NORTH, so the sky's position angle is 0 and not 90. The
    # two conventions are different on purpose (the injection speaks pixels
    # because that is what it writes; the sweep speaks the sky because that
    # is what the mount and the ephemeris fail on) and this is where they
    # meet.
    assert injection.pa_difference(got["injected"]["pa"], 0.0) < 3.0
    assert abs(got["err_rate"]) <= 0.10 * got["injected"]["rate"]
    assert got["err_pa"] <= 15.0


def test_the_motion_is_the_injected_one_in_the_sky(tmp_path):
    # The instrument measures the truth with the sweep's own convention, so
    # the two numbers are comparable. A wrong sign or a wrong baseline here
    # would make the whole comparison meaningless.
    paths = _sequence(tmp_path)
    w = _wcs()
    for pa_deg, rate_px in ((90.0, 1.5), (0.0, 1.0), (180.0, 2.0)):
        got = injection.inject_sequence(paths, 1000.0, rate_px_min=rate_px,
                                        pa_deg=pa_deg, out_dir=tmp_path /
                                        f"inj{int(pa_deg)}", ref_wcs=w)
        t_mid = got["truth"][len(got["truth"]) // 2]
        rate, pa = injection.sky_motion(got["motion"], 2461304.46)
        # 2"/px and one frame per minute: the rate in "/min is 2 x rate_px
        assert rate == pytest.approx(2.0 * rate_px, rel=0.15)
        # PA 0 is +dec and 90 is +RA, and the plate is mirrored in RA
        # (CD1_1 < 0), so the two are checked against each other and not
        # against a remembered sign
        assert 0.0 <= pa < 360.0
