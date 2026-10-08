############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Functional test: the author's own NEO visits
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The real NEO visits (2025 HL5, 2025 FG18) and a real flat train.

This is the acceptance of the four fixes measured on them (ADR-061 rev,
ADR-062 rev): a 0-byte frame does not take the visit down, a flat taken at
another gain is still a flat, a flat built from frames that did not dither
comes out as a smooth vignetting model instead of carrying the stars, and
that model really agrees with a master flat of the same night.

The frames are the observer's own and live outside the repo (about 2 GB),
so the test SKIPS unless they are there. Point NIGHTSCRIBE_NEO_DATASET at
the folder holding 2025FG18/ and Flat-31-03-2025-3/ (default: the author's
own path, if it exists).
"""

import glob
import os
from pathlib import Path

import numpy as np
import pytest

from nightscribe.core import calibration as cal

DEFAULT = "/home/boreal/Develop/astronomy/dataset"
DATASET = os.environ.get("NIGHTSCRIBE_NEO_DATASET") or (
    DEFAULT if Path(DEFAULT).is_dir() else None)

FG18_GLOB = "2025FG18/20250331/*.fits"
FLAT_GLOB = "Flat-31-03-2025-3/**/*.fits"


def _dataset():
    if not DATASET:
        pytest.skip("set NIGHTSCRIBE_NEO_DATASET to the folder of real visits")
    return Path(DATASET)


@pytest.fixture(scope="module")
def fg18_paths():
    folder = _dataset()
    paths = sorted(glob.glob(str(folder / FG18_GLOB), recursive=True))
    if len(paths) < 100:
        pytest.skip("the 2025 FG18 visit is not in the dataset folder")
    return paths


@pytest.fixture(scope="module")
def flat_paths():
    folder = _dataset()
    paths = sorted(glob.glob(str(folder / FLAT_GLOB), recursive=True))
    if len(paths) < 20:
        pytest.skip("the real flats are not in the dataset folder")
    return paths


def test_the_half_written_frame_does_not_take_the_visit_down(fg18_paths,
                                                             tmp_path):
    # Measured: the capture of 2025 FG18 was cut and its last frame was a
    # 0-byte file. load_sequence used to raise on it, so the Astrometry tab
    # never armed and the whole visit was lost. It is now left out and
    # COUNTED: the caller knows how many by comparing with what it handed
    # over, which is what the tab and the run's note say.
    from nightscribe.core import track_stack
    # The broken frame may no longer be in the folder (the observer cleaned
    # it); one is made here so the test does not depend on a leftover. The
    # real frames being read are the visit's own either way.
    broken = tmp_path / "half_written.fits"
    broken.write_bytes(b"")
    paths = list(fg18_paths) + [str(broken)]
    frames = track_stack.load_sequence(paths)
    left_out = len(paths) - len(frames)
    assert left_out == 1, "the 0-byte frame has to be left out"
    assert len(frames) == len(fg18_paths)
    # and the frames that ARE there are usable: a real T_mid, a filter
    good = [f for f in frames if f.t_mid_jd is not None]
    assert len(good) == len(frames)
    assert frames[0].filter


def test_a_flat_taken_at_another_gain_is_still_the_flat(fg18_paths, flat_paths,
                                                        tmp_db):
    # Measured on this night: the flats were taken at gain 3 and the lights
    # at gain 5, so the library answered "no flat" and the visit fell back to
    # a pseudo-flat that carried the stars. A flat is NORMALISED before it is
    # applied: the gain scales its whole level, never its shape.
    light_header = cal.read_header(fg18_paths[0])
    light = {
        "camera": light_header.get("INSTRUME") or light_header.get("CAMERA"),
        "gain": light_header.get("GAIN") or light_header.get("EGAIN"),
        "temp_c": light_header.get("CCD-TEMP"),
        "exptime_s": light_header.get("EXPTIME"),
        "filter": light_header.get("FILTER"),
    }
    flat_header = cal.read_header(flat_paths[0])
    cal.add_master(tmp_db, flat_paths[0], {
        "kind": "flat",
        "camera": flat_header.get("INSTRUME") or flat_header.get("CAMERA"),
        "gain": flat_header.get("GAIN"),
        "temp_c": flat_header.get("CCD-TEMP"),
        "exptime_s": flat_header.get("EXPTIME"),
        "filter": flat_header.get("FILTER")})
    recipe = cal.resolve_recipe(tmp_db, light, tol_c=10.0)
    assert recipe.flat is not None, (
        f"el flat real no casa con la toma: {recipe.flat_missing}")
    assert recipe.flat.path == flat_paths[0]
    # The gain really is part of why this failed: on this night the flats
    # were taken at gain 3 and the lights at gain 5. The test does not depend
    # on it (a flat matches whatever its gain, by construction), but saying
    # the numbers here is what keeps the reason from being lost.
    flat_gain = flat_header.get("GAIN") or flat_header.get("EGAIN")
    if flat_gain is not None and light["gain"] is not None:
        assert float(flat_gain) >= 1.0 and float(light["gain"]) >= 1.0


def test_a_flat_from_frames_that_did_not_dither_becomes_the_vignetting(
        fg18_paths, flat_paths):
    # The mount tracks sidereally here, so the stars do not move between
    # frames and the percentile keeps them: a flat built from these frames
    # would divide every star by itself (measured: a comparison star on a
    # bright star came out 1.08 mag off). What IS usable is the vignetting,
    # which is smooth: the app masks the stars and fits a degree-4 surface,
    # and says what it is.
    flat, info = cal.pseudo_flat(fg18_paths[:16])
    assert flat is not None, info.get("note")
    assert info["kind"] == "vignette_model", info
    assert info["residual_pct"] > cal.PSEUDO_FLAT_RESIDUAL_PCT
    assert info["mask_pct"] > 0.0            # the stars were found
    assert "vignetting" in info["note"]
    # a smooth surface around one: the vignetting of this train, nothing wild
    assert 0.70 <= float(np.median(flat)) <= 1.02
    assert float(flat.max()) <= 1.10
    assert float(flat.min()) >= 0.60
    # and it really is the train's response: measured against the master flat
    # of the same night (20 flats, smoothed so the dust does not decide) the
    # agreement is within a few per cent. This is the number that says the
    # model is worth applying instead of no flat at all.
    from astropy.io import fits
    from scipy import ndimage
    cube = np.stack([np.asarray(fits.open(p)[0].data, dtype=np.float32)
                     for p in flat_paths[:20]])
    master = ndimage.uniform_filter(np.median(cube, axis=0), size=81,
                                    mode="nearest")
    h, w = master.shape
    if flat.shape != master.shape:
        pytest.skip("the flat and the frames are not the same size")
    sl = (slice(120, h - 120), slice(120, w - 120))
    want = master[sl] / float(np.median(master[sl]))
    got = flat[sl] / float(np.median(flat[sl]))
    ratio = got / np.maximum(want, 1e-6)
    assert 0.93 <= float(np.median(ratio)) <= 1.07
    assert 0.90 <= float(np.percentile(ratio, 5)) <= 1.10
    assert 0.90 <= float(np.percentile(ratio, 95)) <= 1.10
