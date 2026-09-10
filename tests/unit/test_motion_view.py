############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: NEO/comet motion animation (Track C, C1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen/disk-free tests for the motion animation (the "fire test"):
frames are aligned to the stars (affine from WCS) and the crop follows the
predicted position at each DATE-OBS, with the marker on that prediction.
The ephemeris resolver is injected, so no network is needed.
"""

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nightscribe.viz import motion_view


# ---------------- helpers: synthetic FITS headers + frames ----------------

def _hdr(ra=100.0, dec=20.0, date_obs="2026-09-10T21:00:00",
         w=200, h=200, scale=0.5):
    # @args: ra/dec - WCS centre, date_obs - DATE-OBS card, w/h - size,
    #        scale - arcsec/pixel
    # @return: header dict digestible by Wcs.from_header + fits_meta
    cdelt = scale / 3600.0
    return {"CRVAL1": ra, "CRVAL2": dec, "CRPIX1": w / 2.0 + 0.5,
            "CRPIX2": h / 2.0 + 0.5, "NAXIS1": w, "NAXIS2": h,
            "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
            "CDELT1": cdelt, "CDELT2": cdelt, "DATE-OBS": date_obs,
            "FILTER": "R", "EXPTIME": 60.0}


def _frame(w, h, spots, sky=100.0):
    # @args: spots - list of (x, y, flux) Gaussian sources
    # @return: 2D float32 array
    data = np.full((h, w), sky, dtype=np.float32)
    yy, xx = np.ogrid[:h, :w]
    for x, y, flux in spots:
        data += flux * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 3 ** 2))
    return data


def _pos_fn(track):
    # @args: track - list with at least one (ra_deg, dec_deg)
    # @return: fake position_fn honouring the position_at contract; the
    #          fixed first track entry is enough for the skip-path tests
    def fn(name, site, when=None, fallback_target=None):
        ra, dec = track[0]
        return {"ra_deg": ra, "dec_deg": dec, "rate_arcsec_min": 12.3,
                "pa_deg": 87.0, "epoch_iso": None, "source": "horizons",
                "preliminary": False}
    return fn


def _fake_reader(store):
    # @args: store - {path: (header, data)}
    # @return: fake fits_io.read_fits
    def read(path):
        if path not in store:
            raise FileNotFoundError(path)
        return store[path]
    return read


# ---------------- position resolution per DATE-OBS ----------------

def test_position_resolved_at_each_frame_dateobs(monkeypatch):
    # The resolver must be called with the instant of each frame's DATE-OBS.
    calls = []
    store = {
        "a.fits": (_hdr(date_obs="2026-09-10T21:00:00"),
                   _frame(200, 200, [(100, 100, 5000)])),
        "b.fits": (_hdr(date_obs="2026-09-10T22:30:00"),
                   _frame(200, 200, [(100, 100, 5000)])),
    }
    monkeypatch.setattr(motion_view.fits_io, "read_fits",
                        _fake_reader(store))

    def fn(name, site, when=None, fallback_target=None):
        calls.append(when)
        return {"ra_deg": 100.0, "dec_deg": 20.0,
                "rate_arcsec_min": 5.0, "pa_deg": 90.0,
                "source": "horizons", "preliminary": False}

    out = motion_view.load_motion_frames(["b.fits", "a.fits"], "2016 XYZ",
                                         "Z41", position_fn=fn)
    assert len(out["frames_data"]) == 2
    assert not out["skipped"]
    # frames sorted by DATE-OBS: the resolver saw the earlier instant first
    assert calls[0] < calls[1]
    assert calls[0].hour == 21 and calls[1].hour == 22


# ---------------- crop follows the prediction ----------------

def test_crop_follows_predicted_position(monkeypatch):
    # Two frames, the object moves ~20 px between them: each crop must be
    # centred on *its* predicted position (marker lands at the crop centre).
    store = {
        "a.fits": (_hdr(), _frame(200, 200, [(100, 100, 5000)])),
        "b.fits": (_hdr(date_obs="2026-09-10T21:10:00"),
                   _frame(200, 200, [(100, 100, 5000)])),
    }
    monkeypatch.setattr(motion_view.fits_io, "read_fits",
                        _fake_reader(store))
    # 0.005 deg at 0.5 arcsec/px ≈ 36 px of apparent motion
    track = [(100.000, 20.0), (100.005, 20.0)]
    state = {"i": 0}

    def fn(name, site, when=None, fallback_target=None):
        ra, dec = track[state["i"]]
        state["i"] += 1
        return {"ra_deg": ra, "dec_deg": dec, "rate_arcsec_min": 12.3,
                "pa_deg": 87.0, "source": "horizons", "preliminary": False}

    out = motion_view.load_motion_frames(["a.fits", "b.fits"], "2016 XYZ",
                                         "Z41", position_fn=fn, zoom=2)
    assert len(out["frames_data"]) == 2
    for img8, xy in out["frames_data"]:
        h, w = img8.shape
        # marker (predicted position) sits at the crop centre: crop_zoom
        # centres on the requested pixel when away from the edges
        assert abs(xy[0] - w / 2) <= 2
        assert abs(xy[1] - h / 2) <= 2


def _centroid8(img8, thresh=200):
    # @args: img8 - uint8 2D array, thresh - bright-pixel threshold
    # @return: (x, y) centroid of the bright pixels. Robust against the
    #          stretch clipping the PSF core into a plateau (argmax would
    #          return the plateau corner, not the star).
    ys, xs = np.nonzero(img8 > thresh)
    if len(xs) == 0:
        return None
    return float(xs.mean()), float(ys.mean())


def test_affine_keeps_stars_fixed(monkeypatch):
    # Two frames with shifted WCS centres and the star at the *same* sky
    # position: after alignment both crops show the star at the same pixel.
    from nightscribe.core.wcs import Wcs
    hdr_a = _hdr(ra=100.00)
    hdr_b = _hdr(ra=100.01, date_obs="2026-09-10T21:05:00")
    wcs_a, wcs_b = Wcs.from_header(hdr_a), Wcs.from_header(hdr_b)
    star_sky = wcs_a.pixel_to_sky(100, 100)
    bx, by = wcs_b.sky_to_pixel(*star_sky)   # raw pixel in frame B
    store = {
        "a.fits": (hdr_a, _frame(200, 200, [(100, 100, 5000)])),
        "b.fits": (hdr_b, _frame(200, 200, [(bx, by, 5000)])),
    }
    monkeypatch.setattr(motion_view.fits_io, "read_fits",
                        _fake_reader(store))

    def fn(name, site, when=None, fallback_target=None):
        return {"ra_deg": star_sky[0], "dec_deg": star_sky[1],
                "rate_arcsec_min": 0.0, "pa_deg": 0.0,
                "source": "horizons", "preliminary": False}

    out = motion_view.load_motion_frames(["a.fits", "b.fits"], "2016 XYZ",
                                         "Z41", position_fn=fn, zoom=2)
    assert len(out["frames_data"]) == 2
    peaks = [_centroid8(img8) for img8, _ in out["frames_data"]]
    assert all(p is not None for p in peaks)
    # the star lands on the same crop pixel in both frames (±2 px tolerance)
    assert abs(peaks[0][0] - peaks[1][0]) <= 2
    assert abs(peaks[0][1] - peaks[1][1]) <= 2


# ---------------- skips ----------------

def test_frame_without_wcs_is_skipped(monkeypatch):
    store = {
        "a.fits": (_hdr(), _frame(200, 200, [(100, 100, 5000)])),
        # no WCS cards at all
        "b.fits": ({"DATE-OBS": "2026-09-10T21:05:00", "NAXIS1": 200,
                    "NAXIS2": 200}, _frame(200, 200, [(100, 100, 5000)])),
    }
    monkeypatch.setattr(motion_view.fits_io, "read_fits",
                        _fake_reader(store))
    out = motion_view.load_motion_frames(
        ["a.fits", "b.fits"], "2016 XYZ", "Z41",
        position_fn=_pos_fn([(100.0, 20.0)]))
    assert len(out["frames_data"]) == 1
    assert out["skipped"] == [("b.fits", "no WCS")]


def test_frame_without_dateobs_is_skipped(monkeypatch):
    hdr = _hdr()
    del hdr["DATE-OBS"]
    store = {
        "a.fits": (_hdr(), _frame(200, 200, [(100, 100, 5000)])),
        "b.fits": (hdr, _frame(200, 200, [(100, 100, 5000)])),
    }
    monkeypatch.setattr(motion_view.fits_io, "read_fits",
                        _fake_reader(store))
    out = motion_view.load_motion_frames(
        ["a.fits", "b.fits"], "2016 XYZ", "Z41",
        position_fn=_pos_fn([(100.0, 20.0)]))
    assert len(out["frames_data"]) == 1
    assert out["skipped"] == [("b.fits", "no DATE-OBS")]


def test_frame_without_ephemeris_is_skipped(monkeypatch):
    store = {
        "a.fits": (_hdr(), _frame(200, 200, [(100, 100, 5000)])),
        "b.fits": (_hdr(date_obs="2026-09-10T21:05:00"),
                   _frame(200, 200, [(100, 100, 5000)])),
    }
    monkeypatch.setattr(motion_view.fits_io, "read_fits",
                        _fake_reader(store))
    out = motion_view.load_motion_frames(
        ["a.fits", "b.fits"], "2016 XYZ", "Z41",
        position_fn=lambda *a, **k: None)
    assert not out["frames_data"]
    assert [r for _, r in out["skipped"]] == ["no ephemeris"] * 2


# ---------------- caption ----------------

def test_caption_carries_time_rate_pa_and_source():
    pos = {"rate_arcsec_min": 12.3, "pa_deg": 87.2, "source": "horizons",
           "preliminary": False}
    import datetime
    dt = datetime.datetime(2026, 9, 10, 21, 14,
                           tzinfo=datetime.timezone.utc)
    cap = motion_view.position_caption(pos, dt, lang="es")
    assert "10/09/2026 21:14 UT" in cap
    assert "12.3″/min" in cap
    assert "PA 87°" in cap
    assert "Horizons" in cap


def test_caption_marks_preliminary_source():
    pos = {"rate_arcsec_min": None, "pa_deg": None,
           "source": "kepler:neofixer", "preliminary": True}
    cap = motion_view.position_caption(pos, None, lang="es")
    assert "Kepler·NEOfixer" in cap
    assert "(prelim.)" in cap


# ---------------- GIF / MP4 output ----------------

def test_motion_gif_and_video(tmp_path, monkeypatch):
    store = {
        f"f{i}.fits": (_hdr(date_obs=f"2026-09-10T21:0{i}:00"),
                       _frame(200, 200, [(100 + 10 * i, 100, 5000)]))
        for i in range(3)
    }
    monkeypatch.setattr(motion_view.fits_io, "read_fits",
                        _fake_reader(store))
    track = [(100.0 + 0.0025 * i, 20.0) for i in range(3)]
    state = {"i": 0}

    def fn(name, site, when=None, fallback_target=None):
        ra, dec = track[state["i"]]
        state["i"] += 1
        return {"ra_deg": ra, "dec_deg": dec, "rate_arcsec_min": 12.3,
                "pa_deg": 87.0, "source": "horizons", "preliminary": False}

    out = motion_view.load_motion_frames(
        list(store), "2016 XYZ", "Z41", position_fn=fn, zoom=2)
    frames = out["frames_data"]
    assert len(frames) == 3
    gif = tmp_path / "motion.gif"
    mp4 = tmp_path / "motion.mp4"
    xys = [xy for _, xy in frames]
    assert motion_view.make_motion_gif(
        frames, out["dates"], xys, out=str(gif),
        names=["2016 XYZ"] * 3) is not None
    assert gif.exists() and gif.stat().st_size > 1000
    assert motion_view.make_motion_video(
        frames, out["dates"], xys, out=str(mp4),
        names=["2016 XYZ"] * 3) is not None
    assert mp4.exists()


def test_motion_gif_empty():
    assert motion_view.make_motion_gif([], [], [], "/dev/null.gif") is None
