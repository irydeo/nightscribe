############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: track & stack worker helpers
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The worker's velocity seed, offline. It sampled +/- 30 s and divided by
two as if the baseline were two minutes, returning exactly HALF the real
rate (measured on 2025 UR: 15.25 instead of 30.6"/min)."""

import pytest

from nightscribe.gui.workers import _rate_pa


def test_rate_pa_is_not_halved():
    # a synthetic motion of exactly 1 arcsec/min towards +dec (PA 0)
    def motion(jd):
        minutes = (jd - 2460000.0) * 1440.0
        return (10.0, 20.0 + minutes * (1.0 / 3600.0))
    rate, pa = _rate_pa(motion, 2460000.0)
    assert rate == pytest.approx(1.0, abs=0.01)
    assert pa == pytest.approx(0.0, abs=0.1)


def test_rate_pa_pa_is_north_through_east():
    # 1 arcsec/min towards +RA only (PA 90) at dec 0
    def motion(jd):
        minutes = (jd - 2460000.0) * 1440.0
        return (10.0 + minutes * (1.0 / 3600.0), 0.0)
    rate, pa = _rate_pa(motion, 2460000.0)
    assert rate == pytest.approx(1.0, abs=0.01)
    assert pa == pytest.approx(90.0, abs=0.1)


def test_rate_pa_without_an_ephemeris_is_none():
    assert _rate_pa(lambda jd: None, 2460000.0) == (None, None)


# ------------------------------------------------- the brightness' centre

def _worker():
    # @return: a worker with no frames: the helpers under test are pure
    from nightscribe.gui.workers import TrackStackWorker
    return TrackStackWorker(["a.fits", "b.fits"], "2025 UR", 1)


def test_the_brightness_centre_prefers_the_measured_centroid():
    # The astrometric measurement already found the object on this very
    # stack: reusing its centroid puts the aperture on the light instead
    # of on the ephemeris, which can be a couple of pixels away. The
    # centroid is ALREADY in the stack's own pixels (measure_stack centres
    # on the stack), so the box origin must not touch it; the ephemeris,
    # which lives in the reference grid, is the one that gets converted.
    from nightscribe.core import astrometry
    worker = _worker()
    sp = astrometry.AstrometryPoint(ra=1.0, dec=2.0, x=110.0, y=90.0)
    assert worker._object_centre(sp, (100.0, 100.0), (0, 0, 2048, 2048)) \
        == (110.0, 90.0)
    # a cutout: the centroid stays where it was measured (110, 90 of the
    # CUTOUT), the ephemeris moves by the box origin
    assert worker._object_centre(sp, (100.0, 100.0), (10, 20, 100, 100)) \
        == (110.0, 90.0)
    assert worker._object_centre(sp, None, (10, 20, 100, 100)) == (110.0, 90.0)


def test_the_brightness_centre_falls_back_to_the_ephemeris():
    # Without a measured position (the point was flagged, or the group had
    # no measurable stack) the ephemeris is the honest fallback, and the
    # flag on the point says so.
    from nightscribe.core import astrometry
    worker = _worker()
    nan = float("nan")
    sp = astrometry.AstrometryPoint(ra=nan, dec=nan, x=nan, y=nan)
    assert worker._object_centre(sp, (100.0, 200.0), (0, 0, 10, 10)) \
        == (100.0, 200.0)
    assert worker._object_centre(None, None, (0, 0, 10, 10)) is None


def test_the_aperture_follows_the_recipe_and_not_a_constant():
    # The recipe is the Fotometria tab's, and the rule is its own: the
    # observer's radii win, a hand edit wins over the seeing rule, and
    # only when they never touched them does the measured FWHM size the
    # aperture.
    from nightscribe.core import photometry
    worker = _worker()
    assert worker._radii({"rap": 5.0, "rin": 9.0, "rout": 14.0}, 3.0) \
        == (5.0, 9.0, 14.0)
    assert worker._radii({"rap": 5.0, "rin": 9.0, "rout": 14.0,
                          "seeing": True, "radii_manual": True}, 3.0) \
        == (5.0, 9.0, 14.0)
    assert worker._radii({"seeing": True}, 3.0) \
        == photometry.aperture_for_fwhm(3.0)
    # no recipe at all: the plate's own defaults, which is None
    assert worker._radii({}, 3.0) is None


# ------------------------------------------------------- ephemeris cascade

_ELEMENTS = {"a": 2.329264345717352, "e": 0.5508738138610355,
             "i": 11.04772931873822, "om": 148.529452272859,
             "w": 207.3810299700251, "ma": 332.5479727971131,
             "epoch": 2461200.5}


def test_sequence_motion_prefers_horizons(monkeypatch):
    from nightscribe.core import track_stack
    from nightscribe.core.sources import horizons
    rows = [{"time": "2026-Aug-16 22:00", "ra": "20 52 00.00",
             "dec": "-04 00 00.0", "r": 1.1, "delta": 0.1},
            {"time": "2026-Aug-16 22:02", "ra": "20 52 01.00",
             "dec": "-04 00 01.0", "r": 1.1, "delta": 0.1}]
    monkeypatch.setattr(horizons, "ephemeris_ex", lambda *a, **k: (rows, ""))
    frames = [track_stack.Frame(path="f.fits", t_mid_jd=2461269.434)]
    motion, source, reason = track_stack.sequence_motion_solution(
        frames, "2026 PY9", site="Z41")
    assert source == "horizons" and reason == ""
    assert motion(2461269.434) is not None


def test_sequence_motion_falls_back_to_the_local_orbit(monkeypatch):
    # JPL down (503): the stack must still run, from the SBDB elements
    # propagated locally, and SAY that is where the position came from.
    from nightscribe.core import track_stack
    from nightscribe.core.sources import horizons, sbdb
    monkeypatch.setattr(horizons, "ephemeris_ex",
                        lambda *a, **k: ([], "http 503"))
    monkeypatch.setattr(sbdb, "get",
                        lambda name, **k: {"elements": dict(_ELEMENTS)})
    frames = [track_stack.Frame(path="f.fits", t_mid_jd=2461269.434)]
    motion, source, reason = track_stack.sequence_motion_solution(
        frames, "2026 PY9", site="Z41")
    assert source == "kepler:sbdb" and reason == ""
    ra, dec = motion(2461269.434)
    assert 310.0 < ra < 316.0 and -8.0 < dec < -2.0


def test_sequence_motion_says_why_when_nothing_answers(monkeypatch):
    from nightscribe.core import track_stack
    from nightscribe.core.sources import horizons, sbdb, neofixer
    monkeypatch.setattr(horizons, "ephemeris_ex",
                        lambda *a, **k: ([], "http 503"))
    monkeypatch.setattr(sbdb, "get", lambda name, **k: None)
    monkeypatch.setattr(neofixer, "orbit", lambda name, **k: None)
    frames = [track_stack.Frame(path="f.fits", t_mid_jd=2461269.434)]
    motion, source, reason = track_stack.sequence_motion_solution(
        frames, "2026 PY9", site="Z41")
    assert motion is None and source is None
    assert reason == "http 503"


# ------------------------------------- the ephemeris' predicted brightness

def test_sequence_ephemeris_carries_the_predicted_magnitude(monkeypatch):
    # Asked for: when the run does not measure the brightness the band must
    # still show how bright the object should be, and say that the ephemeris
    # says so. The magnitude comes from the SAME cascade as the position, in
    # its own cached call.
    from nightscribe.core import track_stack
    from nightscribe.core.sources import horizons
    rows = [{"time": "2026-Aug-16 22:00", "ra": "20 52 00.00",
             "dec": "-04 00 00.0", "r": 1.1, "delta": 0.1},
            {"time": "2026-Aug-16 22:02", "ra": "20 52 01.00",
             "dec": "-04 00 01.0", "r": 1.1, "delta": 0.1}]
    mags = [{"time": "2026-Aug-16 22:00", "mag": 22.21},
            {"time": "2026-Aug-16 22:02", "mag": 22.22}]
    monkeypatch.setattr(horizons, "ephemeris_ex", lambda *a, **k: (rows, ""))
    monkeypatch.setattr(horizons, "magnitude_rows",
                        lambda *a, **k: (mags, "V", ""))
    frames = [track_stack.Frame(path="f.fits", t_mid_jd=2461269.434)]
    out = track_stack.sequence_ephemeris(frames, "2026 PY9", site="Z41")
    assert out["source"] == "horizons"
    # the row nearest the sequence's middle instant (22:02 here)
    assert out["mag"] == pytest.approx(22.22)
    assert out["band"] == "V"
    assert out["mag_source"] == "horizons"


def test_the_local_orbit_predicts_the_magnitude_with_h_and_g(monkeypatch):
    # JPL down: the local two-body orbit answers the position AND the
    # magnitude (IAU H-G from the H and G the elements come with), so a run
    # that fell back still says how bright the object is.
    from nightscribe.core import track_stack
    from nightscribe.core.sources import horizons, sbdb
    monkeypatch.setattr(horizons, "ephemeris_ex",
                        lambda *a, **k: ([], "http 503"))
    monkeypatch.setattr(sbdb, "get", lambda name, **k: {
        "elements": dict(_ELEMENTS), "phys": {"H": 23.356}})
    frames = [track_stack.Frame(path="f.fits", t_mid_jd=2461269.434)]
    out = track_stack.sequence_ephemeris(frames, "2026 PY9", site="Z41")
    assert out["source"] == "kepler:sbdb"
    assert out["mag_source"] == "kepler:sbdb"
    assert out["band"] == "V"
    assert 10.0 < out["mag"] < 35.0        # a figure, not a placeholder


def test_a_run_without_a_magnitude_still_has_its_position(monkeypatch):
    # The magnitude is a nicety of the ephemeris, never a condition: if the
    # call fails the run goes on with mag None and the band falls back to the
    # catalogue, labelled.
    from nightscribe.core import track_stack
    from nightscribe.core.sources import horizons
    rows = [{"time": "2026-Aug-16 22:00", "ra": "20 52 00.00",
             "dec": "-04 00 00.0", "r": 1.1, "delta": 0.1},
            {"time": "2026-Aug-16 22:02", "ra": "20 52 01.00",
             "dec": "-04 00 01.0", "r": 1.1, "delta": 0.1}]
    monkeypatch.setattr(horizons, "ephemeris_ex", lambda *a, **k: (rows, ""))
    monkeypatch.setattr(horizons, "magnitude_rows",
                        lambda *a, **k: ([], None, "http 503"))
    frames = [track_stack.Frame(path="f.fits", t_mid_jd=2461269.434)]
    out = track_stack.sequence_ephemeris(frames, "2026 PY9", site="Z41")
    assert out["motion"] is not None and out["source"] == "horizons"
    assert out["mag"] is None and out["mag_source"] is None


# ------------------------------------------- the run's brightness (P2/P3)

class _PlateResult:
    # The shape photometry.measure_plate returns, stubbed: the point is the
    # ORCHESTRATION in _photometry, not the photometry itself (that has its
    # own tests).
    ok = True
    mag = 18.0
    err_total = 0.05
    check = {"verdict": True}

    @property
    def used(self):
        return [(_comp_entry(),
                 {"ok": True, "snr": 30.0, "x": 10.0, "y": 10.0})]


def _comp_entry():
    return {"kind": "comp",
            "star": {"ra": 30.01, "dec": 10.01, "mag": 15.0, "band": "G"}}


def test_photometry_runs_and_keeps_the_plate_shape_for_every_observation(
        monkeypatch):
    # Two bugs lived here, both because _photometry had NO test:
    #  1. the P3 diagnostics use math.cos/radians/hypot and workers.py only
    #     imported math INSIDE other methods, so a calibrated run died with
    #     "name 'math' is not defined";
    #  2. the P2 elongation dict was assigned to `shape`, clobbering the
    #     plate's (naxis1, naxis2) that the NEXT observation's comp windows
    #     still need, so a two-observation run indexed a dict.
    import numpy as np
    from astropy.wcs import WCS
    from nightscribe.core import astrometry, photometry, track_stack
    from nightscribe.gui.workers import TrackStackWorker

    worker = TrackStackWorker(["a.fits"], "2025 UR", 2,
                              comps=[_comp_entry()], recipe={"band": "G"})
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [30.0, 10.0]
    w.wcs.crpix = [33.0, 33.0]
    w.wcs.cd = [[-0.0003, 0.0], [0.0, 0.0003]]
    w.wcs.radesys = "ICRS"
    w.wcs.equinox = 2000.0
    w.pixel_shape = (64, 64)
    ref = track_stack.Frame(path="a.fits",
                            header={"NAXIS1": 64, "NAXIS2": 64})
    box = (0, 0, 64, 64)
    img = np.zeros((64, 64), dtype=np.float32)
    stack = (img, None)
    sp = astrometry.AstrometryPoint(ra=30.0, dec=10.0, x=32.0, y=32.0)

    shapes_seen = []

    def fake_windows(_frames, _group, entries, _wcs_box, shape):
        # the comp windows are the thing that receives the PLATE shape: if
        # the elongation dict clobbered it, this is a dict and the assert
        # below says so
        shapes_seen.append(shape)
        return [(entries[0], np.zeros((21, 21), dtype=np.float32), 10.0, 10.0)]

    monkeypatch.setattr(worker, "_comp_windows", fake_windows)
    monkeypatch.setattr(worker, "_seeing", lambda _windows: 3.0)
    monkeypatch.setattr(photometry, "measure_plate",
                        lambda _stack, _cfg: _PlateResult())
    monkeypatch.setattr(photometry, "psf_elongation",
                        lambda *_a, **_k: {"ok": False})
    monkeypatch.setattr(photometry, "pick_band",
                        lambda _entries, _band, _fallback: ("G", ["G"]))

    out = worker._photometry(
        [ref], [(0, 1), (1, 1)], [box, box],
        [(32.0, 32.0), (32.0, 32.0)], [stack, stack],
        [(sp, None, []), (sp, None, [])], ref, w)

    assert out is not None and out["n_obs"] == 2
    assert out["mag"] == pytest.approx(18.0)
    assert len(shapes_seen) == 2
    for shape in shapes_seen:
        assert isinstance(shape, tuple) and shape == (64, 64)
