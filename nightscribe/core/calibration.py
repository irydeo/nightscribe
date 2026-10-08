############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Image calibration and master library (ADR-061)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Calibrating a frame: bias/dark and flat, and the library of masters.

A faint asteroid does not emerge from the noise if the frame still carries
the sensor's thermal pattern and the dust of the optical train: stacking
adds the signal, but it adds the pedestal and the vignetting too. This
module turns a raw frame into a usable one and keeps the user's masters
(a library indexed by what makes a master valid: camera, gain, sensor
temperature, exposure and filter).

Two physical facts decide the arithmetic, and both are easy to get wrong:

- A **dark taken at the light's own exposure already contains the bias**
  (the read-out pedestal). Subtracting a dark AND a bias would subtract
  the pedestal twice, so the engine subtracts a dark when it exists and
  falls back to the bias only when it does not (and says so, because then
  the thermal current stays in the frame).
- A **flat must be normalised before dividing**. Dividing by the flat
  without normalising it would rescale the whole frame's flux level; the
  flat's job is to remove the shape, not to change the brightness. And the
  flat needs its own offset removed first (a dark-flat, or the bias if the
  flat is short), or the division amplifies the pedestal in the dark
  corners of the flat.

The order matters: offset first, flat second.

Reading a FITS is not obvious either (ADR-060, D32): astropy refuses to
memory-map an image whose header carries BSCALE/BZERO/BLANK (the usual
uint16-as-int16 of CMOS cameras), so frames are opened with
``do_not_scale_image_data=True`` and the scaling is applied here, by hand,
in float32.
"""

import datetime
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import outliers

logger = logging.getLogger(__name__)

# Header keys tried in order, most specific first. Amateur headers are a
# zoo: INSTRUME is the FITS standard, CAMERA/DETECTOR are common aliases.
_CAMERA_KEYS = ("INSTRUME", "CAMERA", "DETECTOR")
_GAIN_KEYS = ("GAIN", "EGAIN", "CCD-GAIN")
_TEMP_KEYS = ("CCD-TEMP", "DET-TEMP", "SET-TEMP", "TEMP")
_EXPTIME_KEYS = ("EXPTIME", "EXPOSURE", "ELAPSED")
_FILTER_KEYS = ("FILTER", "FILTERS", "FILT")

# Matching tolerances. Exposure is exact on purpose: in CMOS the thermal
# pattern does not scale linearly with time, so a dark at another exposure
# leaves a residual. Temperature is tolerant because its effect is smooth
# and monotone, and +/-3 C is what the author accepts.
_EXPTIME_TOL_S = 1e-3
_GAIN_TOL = 1e-6
_DEFAULT_TEMP_TOL_C = 3.0

# The four kinds of master the library knows.
KINDS = ("bias", "dark", "dark_flat", "flat")


# ------------------------------------------------------------------ reading

def _first(hdul):
    # @args: hdul - an open astropy HDUList
    # @return: the first 2D image HDU, or None
    # Masters and lights are 2D images; a table or a data cube is not our
    # business here (the old fits_io collapses RGB; calibration does not).
    for hdu in hdul:
        if hdu.header.get("NAXIS", 0) == 2:
            return hdu
    return None


def read_header(path):
    # @args: path - FITS file
    # @return: the header as a plain dict (astropy Card mapping -> dict)
    # Only the header is read, so this is cheap even for a 16 MP frame.
    from astropy.io import fits
    with fits.open(path, memmap=True, do_not_scale_image_data=True) as hdul:
        hdu = _first(hdul)
        return dict(hdu.header) if hdu is not None else {}


def read_image(path, box=None):
    # @args: path - FITS file, box - optional (x0, y0, x1, y1) region
    # @return: (float32 array, header dict)
    # The scaling is applied by hand: with do_not_scale_image_data the raw
    # values come unscaled (and big-endian), and BSCALE/BZERO are ours to
    # apply. Applying them here, once, keeps every later module honest.
    from astropy.io import fits
    with fits.open(path, memmap=True, do_not_scale_image_data=True) as hdul:
        hdu = _first(hdul)
        if hdu is None:
            raise ValueError(f"{path}: no 2D image HDU")
        if box is not None:
            x0, y0, x1, y1 = box
            raw = hdu.section[y0:y1, x0:x1]
        else:
            raw = hdu.data
        header = dict(hdu.header)
    data = np.asarray(raw)
    if data.ndim != 2:
        # A region that does not touch the frame comes back from astropy's
        # section as a 1-D EMPTY array, and a 1-D "image" breaks the caller
        # three layers away: scipy sees input.ndim + 1 == 2, takes our 2x2
        # rotation for a HOMOGENEOUS matrix, finds the bottom row is not
        # [0, 1] and refuses it with "Expected homogeneous transformation
        # matrix with shape (2, 2) for image shape (0,)" (measured on a
        # real visit). An empty 2-D array says the same thing (there is no
        # data here) without the trap, and every caller already handles a
        # zero-sized array.
        data = data.reshape((0, 0))
    data = data.astype(np.float32)
    bscale = _num(header.get("BSCALE"), 1.0)
    bzero = _num(header.get("BZERO"), 0.0)
    if bscale != 1.0:
        data *= bscale
    if bzero != 0.0:
        data += bzero
    return data, header


def _num(value, default=None):
    # @args: value - header card value (may be a string like "+2.0C"),
    #        default - what to return when it is not a number
    # @return: float or default
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("C", "").replace("c", "")
    try:
        return float(s)
    except ValueError:
        return default


def meta_from_header(header):
    # @args: header - dict
    # @return: dict {camera, gain, temp_c, exptime_s, filter} (missing: None)
    # The same tolerant lookup is used to index a master and to ask for the
    # recipe of a light, so the two speak the same language.
    out = {}
    for key in _CAMERA_KEYS:
        if header.get(key):
            out["camera"] = str(header[key]).strip()
            break
    else:
        out["camera"] = None
    for key in _GAIN_KEYS:
        if header.get(key) is not None:
            out["gain"] = _num(header[key])
            break
    else:
        out["gain"] = None
    for key in _TEMP_KEYS:
        if header.get(key) is not None:
            out["temp_c"] = _num(header[key])
            break
    else:
        out["temp_c"] = None
    for key in _EXPTIME_KEYS:
        if header.get(key) is not None:
            out["exptime_s"] = _num(header[key])
            break
    else:
        out["exptime_s"] = None
    for key in _FILTER_KEYS:
        if header.get(key):
            out["filter"] = str(header[key]).strip()
            break
    else:
        out["filter"] = None
    return out


# ------------------------------------------------------------- the library

@dataclass(frozen=True)
class MasterRef:
    # One master file, with the key that makes it valid for a given light.
    id: int
    kind: str
    path: str
    camera: str | None = None
    gain: float | None = None
    temp_c: float | None = None
    exptime_s: float | None = None
    filter: str | None = None
    created: str | None = None
    meta: dict = field(default_factory=dict)


def _row_to_ref(row):
    # @args: row - sqlite row (id, kind, path, camera, gain, temp_c,
    #        exptime_s, filter, created, meta)
    # @return: MasterRef
    (mid, kind, path, camera, gain, temp_c, exptime_s, filt,
     created, meta) = row
    try:
        meta = json.loads(meta) if meta else {}
    except (TypeError, ValueError):
        meta = {}
    return MasterRef(id=mid, kind=kind, path=path, camera=camera, gain=gain,
                     temp_c=temp_c, exptime_s=exptime_s, filter=filt,
                     created=created, meta=meta)


def add_master(db, path, meta):
    # Indexes a master the user already built. Any field missing from meta
    # is read from the file's own header, so a well-headed master can be
    # indexed with just its kind.
    # @args: db - Database, path - master FITS, meta - dict with at least
    #        {"kind": bias|dark|dark_flat|flat} and any of camera/gain/
    #        temp_c/exptime_s/filter
    # @return: the new row id
    meta = dict(meta or {})
    kind = meta.get("kind")
    if kind not in KINDS:
        raise ValueError(f"a master needs kind in {KINDS}, got {kind!r}")
    from_header = meta_from_header(read_header(path))
    for key, value in from_header.items():
        if meta.get(key) is None:
            meta[key] = value
    created = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")
    extra = {k: v for k, v in meta.items()
             if k not in ("kind", "camera", "gain", "temp_c", "exptime_s",
                          "filter")}
    cur = db.execute(
        "INSERT INTO calib_masters (kind, path, camera, gain, temp_c,"
        " exptime_s, filter, created, meta) VALUES (?,?,?,?,?,?,?,?,?)",
        (kind, str(path), meta.get("camera"), meta.get("gain"),
         meta.get("temp_c"), meta.get("exptime_s"), meta.get("filter"),
         created, json.dumps(extra)))
    db.commit()
    return cur.lastrowid


def list_masters(db, camera=None, kind=None):
    # @args: db - Database, camera - optional filter, kind - optional filter
    # @return: list[MasterRef], newest first
    sql = ("SELECT id, kind, path, camera, gain, temp_c, exptime_s, filter,"
           " created, meta FROM calib_masters")
    rows = db.execute(sql).fetchall()
    out = [_row_to_ref(r) for r in rows]
    if camera is not None:
        out = [m for m in out if _same_text(m.camera, camera)]
    if kind is not None:
        out = [m for m in out if m.kind == kind]
    out.sort(key=lambda m: m.created or "", reverse=True)
    return out


def delete_master(db, master_id, delete_file=False):
    # @args: db - Database, master_id - row id, delete_file - also remove
    #        the file from disk (off by default: the user's data)
    # @return: the path that was removed from the index, or None
    row = db.execute("SELECT path FROM calib_masters WHERE id=?",
                     (master_id,)).fetchone()
    if not row:
        return None
    path = row[0]
    db.execute("DELETE FROM calib_masters WHERE id=?", (master_id,))
    db.commit()
    if delete_file:
        import os
        try:
            os.remove(path)
        except OSError as err:
            logger.warning("could not remove master %s: %s", path, err)
    return path


def _same_text(a, b):
    # @args: a, b - two optional strings
    # @return: True when both are known and equal (case-insensitive)
    if a is None or b is None:
        return False
    return a.strip().lower() == b.strip().lower()


def _close(a, b, tol):
    # @args: a, b - two optional numbers, tol - tolerance
    # @return: True when both are known and within tol
    if a is None or b is None:
        return False
    return abs(float(a) - float(b)) <= tol


def find_master(db, kind, camera=None, gain=None, temp_c=None,
                exptime_s=None, filter=None, tol_c=None):
    # The best master for a light. A criterion left as None is IGNORED
    # (the caller may not know it), which is why resolve_recipe warns when
    # it has to fall back to a loose match.
    # Camera/gain/exposure/filter match exactly (with float tolerances);
    # temperature takes the NEAREST one inside tol_c, because it is a
    # smooth physical variable and an exact match would leave the library
    # almost always empty.
    # @args: db - Database, kind - one of KINDS, camera/gain/temp_c/
    #        exptime_s/filter - what the light asks for, tol_c - temperature
    #        tolerance (config default when None)
    # @return: MasterRef or None
    tol = _DEFAULT_TEMP_TOL_C if tol_c is None else float(tol_c)
    best = None
    best_delta = None
    for ref in list_masters(db, kind=kind):
        if not _same_text(ref.camera, camera) and ref.camera and camera:
            continue
        if not _close(ref.gain, gain, _GAIN_TOL) and ref.gain is not None \
                and gain is not None:
            continue
        if not _close(ref.exptime_s, exptime_s, _EXPTIME_TOL_S) \
                and ref.exptime_s is not None and exptime_s is not None:
            continue
        if not _same_text(ref.filter, filter) and ref.filter and filter:
            continue
        delta = None
        if ref.temp_c is not None and temp_c is not None:
            delta = abs(ref.temp_c - float(temp_c))
            if delta > tol:
                continue
        if best is None or _prefer(delta, ref, best_delta, best):
            best, best_delta = ref, delta
    return best


def _prefer(delta, ref, best_delta, best):
    # @args: delta - temperature distance of the candidate (or None),
    #        ref - candidate, best_delta/best - current winner
    # @return: True when the candidate wins
    # Nearest temperature first; ties (or no temperature at all) go to the
    # most recent, which is what list_masters returns first.
    if delta is None:
        return best_delta is None
    if best_delta is None:
        return True
    return delta < best_delta


# ------------------------------------------------------------- the recipe

@dataclass
class Recipe:
    # What the engine will do to a light, resolved against the library.
    meta: dict = field(default_factory=dict)
    offset: MasterRef | None = None       # the dark or bias to subtract
    offset_kind: str | None = None        # "dark" | "bias" | None
    flat: MasterRef | None = None
    flat_offset: MasterRef | None = None  # offset removed from the flat
    warnings: list[str] = field(default_factory=list)


@dataclass
class CalibrationReport:
    # What actually happened, in plain language, for the card and the log.
    offset_kind: str | None = None
    offset_path: str | None = None
    flat_path: str | None = None
    flat_norm: float | None = None
    pedestal_adu: float | None = None     # median of the offset removed
    warnings: list[str] = field(default_factory=list)
    ok: bool = True


def resolve_recipe(db, meta, tol_c=None):
    # @args: db - Database, meta - a light's metadata (from a header),
    #        tol_c - temperature tolerance
    # @return: Recipe (with warnings in plain language, never an exception)
    camera = meta.get("camera")
    gain = meta.get("gain")
    temp = meta.get("temp_c")
    exptime = meta.get("exptime_s")
    filt = meta.get("filter")
    recipe = Recipe(meta=dict(meta))

    # Offset: a dark at the light's exposure if there is one, else the bias.
    # Darks and biases do not depend on the filter, so the filter is not
    # part of their match (a dark through a different filter is the same
    # dark); the flat does.
    dark = find_master(db, "dark", camera, gain, temp, exptime,
                       filter=None, tol_c=tol_c)
    if dark is not None:
        recipe.offset, recipe.offset_kind = dark, "dark"
    else:
        # A bias has no exposure of its own: matching it against the
        # light's exposure would find nothing. It is the fallback offset.
        bias = find_master(db, "bias", camera, gain, temp, exptime_s=None,
                           filter=None, tol_c=tol_c)
        if bias is not None:
            recipe.offset, recipe.offset_kind = bias, "bias"
            recipe.warnings.append(
                "no dark at this exposure: the bias was subtracted, so the "
                "thermal current stays in the frame")
        else:
            recipe.warnings.append(
                "no dark or bias in the library: the pedestal and the "
                "thermal current stay in the frame")

    # Flat: same filter (that is its whole point). Its exposure is not the
    # light's, so exposure is not part of the match, and NEITHER IS THE GAIN:
    # a flat is NORMALISED before it is applied, so the gain only scales its
    # whole level, never its shape. Requiring it was rejecting real flats
    # (measured on the author's own 2025 FG18 night: the flats were taken at
    # gain 3 and the lights at gain 5, so the library said "no flat" and the
    # run fell back to a pseudo-flat). The dark DOES need the gain: there the
    # level is the signal.
    flat = find_master(db, "flat", camera, None, temp, exptime_s=None,
                       filter=filt, tol_c=tol_c)
    if flat is not None:
        recipe.flat = flat
        # The flat needs its own offset: a dark-flat at the flat's own
        # exposure, or the bias when the flat is short. Without it the
        # division amplifies the pedestal where the flat is dark.
        recipe.flat_offset = find_master(
            db, "dark_flat", camera, gain, temp, flat.exptime_s,
            filter=None, tol_c=tol_c) or find_master(
            db, "bias", camera, gain, temp, None, filter=None, tol_c=tol_c)
    else:
        recipe.warnings.append(
            "no flat for this filter: the flat residual is not corrected "
            "(it matters for the magnitude, little for the centroid)")
    return recipe


# ------------------------------------------------------------- the engine

@dataclass
class LoadedMasters:
    # The master arrays, ready to apply (float32).
    offset: np.ndarray | None = None
    flat: np.ndarray | None = None        # already offset-free and normalised
    flat_norm: float | None = None


def load_masters(recipe, loader=None, box=None):
    # @args: recipe - Recipe, loader - callable(path, box) -> array
    #        (defaults to read_image), box - optional (x0,y0,x1,y1) region
    # @return: LoadedMasters
    # The flat is always read WHOLE, even when only a region is wanted,
    # because its normalisation has to be the full-frame median: cropping
    # first would normalise by whatever the crop happens to contain and
    # change the frame's flux level from crop to crop.
    loader = loader or read_image
    out = LoadedMasters()
    if recipe.offset is not None:
        out.offset = _as_float32(loader(recipe.offset.path, box))
    if recipe.flat is not None:
        flat_full = _as_float32(loader(recipe.flat.path, None))
        if recipe.flat_offset is not None:
            flat_off = _as_float32(loader(recipe.flat_offset.path, None))
            if flat_off.shape == flat_full.shape:
                flat_full = flat_full - flat_off
            else:
                logger.warning("flat offset %s does not match the flat; "
                               "ignored", recipe.flat_offset.path)
        norm = float(np.median(flat_full))
        if norm > 0:
            out.flat = flat_full / norm
            out.flat_norm = norm
            if box is not None:
                x0, y0, x1, y1 = box
                out.flat = out.flat[y0:y1, x0:x1]
        else:
            logger.warning("flat %s has a non-positive median; not applied",
                           recipe.flat.path)
    return out


def _as_float32(data):
    # @args: data - array (any float/int dtype), or the (array, header)
    #        pair read_image returns: a loader is allowed to be either
    # @return: the same data as float32 (half the memory, plenty of
    #          precision: 7 significant digits beat photon noise)
    if isinstance(data, tuple):
        data = data[0]
    return np.asarray(data, dtype=np.float32)


# ------------------------------------------------------- the pseudo-flat (P5)
#
# Revised 2026-10-07 (ADR-069). Two things changed, and both were measured
# against the author's own real master flat of the same night (150 flats of
# 2025-03-31, `tools/bench/bench_flat.py`):
#
# 1. THE MASK COMES BEFORE THE STATISTIC. The old version computed the
#    percentile first and went looking for stars afterwards, so the stars
#    were already inside it and the only thing left was to give up. On a
#    STATIC field (measured on 2025 FG18: 2 px of drift in 207 frames, 17 to
#    33 stars matched) the percentile cannot remove them at all: the flat
#    came out with a maximum of 2.83 against the real flat's 1.11, and a
#    comparison star sitting on a bright star went 1.08 mag off.
# 2. THE PEDESTAL IS REMOVED. A pseudo-flat is built from the lights, so it
#    carries their pedestal: flat_obs = P + sky * R. The normalisation does
#    not remove it and the SHAPE comes out COMPRESSED. Measured: P = 827 ADU
#    (56 % of the level) and the compression is 1/(1+p) = 0.44, so the flat
#    was correcting only 44 % of the vignetting. With the pedestal removed,
#    the agreement with the real flat goes from 15.6 % to 4.16 %.

# The percentile the pseudo-flat takes over the frames. 33 % and not 50 %
# because the sky and the stars only ADD light: a low percentile is
# biased away from them, and whatever bias is left is divided out by the
# renormalisation at the end. Tycho's pseudo-flat uses the same 33 %.
PSEUDO_FLAT_ORDER = 0.33
# The smoothing window in pixels, applied `passes` times. It has to be MUCH
# larger than the PSF (measured on 2025 UR: 4.6 px) so the residual star
# bumps are averaged away, and much smaller than the vignetting, which is
# hundreds of pixels across. 41 px sits in that gap with room on both sides.
PSEUDO_FLAT_WINDOW = 41
# Three box passes, which is how Tycho describes its pseudo-flat. Three box
# filters approximate a Gaussian well enough (the central limit does the
# work) and each one is O(1) per pixel, so the whole flat is seconds and not
# minutes: a 41-px MEDIAN filter on 2048x2048 would be the minutes.
PSEUDO_FLAT_PASSES = 3
# How much small-scale structure survived the smoothing, as a scaled MAD, in
# per cent. KEPT AS A FIGURE, NOT AS THE CHECK: a scaled MAD is robust by
# construction, the stars cover 0.3 % of the pixels, and a flat carrying them
# (a maximum of 2.83) moves it by nothing at all (measured: 0.06 % with the
# stars, 0.05 % without them). The check is PSEUDO_FLAT_VERIFY_PCT.
PSEUDO_FLAT_RESIDUAL_PCT = 2.0
# Rows per chunk when reading the frames: the percentile needs every frame at
# the same time, so the pass is done in bands. 64 rows x 207 frames x 2048
# px x 4 B = 108 MB, which is a working set and not a problem.
_PSEUDO_FLAT_ROWS = 64

# ---- the mask, the fill and the hot pixels (P5 rev) ---------------------
# Above this many robust sigmas over the SMOOTHED percentile is a source that
# does not move. It is the only detector that can see the FAINT stars: the
# pixel noise is 117 ADU on a sky of 1552 (7.5 %), so a star worth 1 % of the
# sky is at S/N 0.13 in one frame and only exists in the combination.
PSEUDO_FLAT_MASK_SIGMA = 5.0
# px around it: the halo, the spikes, the bloom of a bright star.
PSEUDO_FLAT_MASK_DILATE = 12
# What is not bigger than this is a HOT PIXEL and not a star: it is FIXED, so
# it belongs in the flat (the division removes it) and it must NOT be
# dilated. Measured on FG18: 10,150 isolated spikes, 0.242 % of the frame, up
# to 9,232 ADU on a sky of 1,488. Dilating them masked 50 % of the frame.
PSEUDO_FLAT_HOT_MAX_PX = 2
# The check that replaced the MAD: how far the FINAL flat deviates from its
# own smoothed version AT THE PIXELS THAT WERE MASKED, which is where a star
# was and therefore where a bump cannot exist. Measured: 33.83 % on the flat
# that carried the stars, 2.11 % on the masked one, and 4.58 % on the real
# master (it carries the dust, which is not masked and is a dip, not a bump).
PSEUDO_FLAT_VERIFY_PCT = 8.0
# Above this fraction of filled pixels there is not enough sky left to model
# anything, and the smooth vignetting model is what is left (see below).
PSEUDO_FLAT_MAX_FILLED_PCT = 30.0
# ---- the smooth vignetting model, the LAST resort -----------------------
# A flat that carries the stars is worse than no flat: every star is divided
# by itself. When the sky coverage is not enough to build a clean flat, what
# IS still usable from those frames is the VIGNETTING, which is smooth and
# fixed: a low-order surface fitted to the percentile where there are no
# stars. Measured against the author's real flat: it agrees to within 3 %
# (p5-p95 0.95-1.05) and the fine structure it does not correct (the dust) is
# worth 0.6 % = 0.007 mag. The vignetting itself is 13-22 %.
PSEUDO_FLAT_MODEL_ORDER = 4      # the total degree of the fitted surface
_PSEUDO_FLAT_FIT_STRIDE = 8      # fit on every 8th pixel: the vignetting is
                                 # smooth, and 2048x2048 rows would be a
                                 # 480 MB design matrix for nothing


def _vignetting_model(raw, star_mask, order=PSEUDO_FLAT_MODEL_ORDER):
    # @args: raw - the per-pixel percentile over the frames (h, w), star_mask
    #        - True where a star does not move, order - the surface's total
    #        degree
    # @return: (model, None) with the model normalised to a median of one, or
    #          (None, why) when it cannot be built
    from scipy import ndimage
    h, w = raw.shape
    # the dilation is what takes the halo, the spikes and the bloom of a
    # bright star out of the fit, not just the core the mask found
    keep = ~ndimage.binary_dilation(star_mask,
                                    iterations=PSEUDO_FLAT_MASK_DILATE)
    ys, xs = np.nonzero(keep)
    if len(ys) < 4 * (order + 1) ** 2:
        return None, ("the stars cover almost the whole frame: there is not "
                      "enough sky left to model the vignetting")
    ys, xs = ys[::_PSEUDO_FLAT_FIT_STRIDE], xs[::_PSEUDO_FLAT_FIT_STRIDE]
    yn = (ys - h / 2.0) / (h / 2.0)
    xn = (xs - w / 2.0) / (w / 2.0)
    terms = [(i, j) for i in range(order + 1) for j in range(order + 1)
             if i + j <= order]
    design = np.empty((len(xs), len(terms)), dtype=np.float64)
    for k, (i, j) in enumerate(terms):
        design[:, k] = (xn ** i) * (yn ** j)
    values = raw[ys, xs].astype(np.float64)
    try:
        coef, *_ = np.linalg.lstsq(design, values, rcond=None)
    except np.linalg.LinAlgError:
        return None, "the vignetting model did not converge"
    yy, xx = np.mgrid[0:h, 0:w]
    yyn = (yy - h / 2.0) / (h / 2.0)
    xxn = (xx - w / 2.0) / (w / 2.0)
    model = np.zeros((h, w), dtype=np.float64)
    for c, (i, j) in zip(coef, terms):
        model += c * (xxn ** i) * (yyn ** j)
    norm = float(np.median(model))
    if not np.isfinite(model).all() or norm <= 0:
        return None, "the vignetting model is not usable (it has no level)"
    return (model / norm).astype(np.float32), None


def _star_mask(raw, ref, sigma=None, dilate=None):
    # @args: raw - the per-pixel percentile over the frames, ref - its own
    #        smoothed version, sigma - significance, dilate - px of halo
    # @return: (mask, hot, stats): mask = the EXTENDED sources, dilated;
    #          hot = the isolated spikes, NOT dilated
    # WHAT IS WELL ABOVE THE SMOOTHED PERCENTILE IS A SOURCE THAT DOES NOT
    # MOVE. It is the only detector that can see the faint ones: a star worth
    # 1 % of the sky is at S/N 0.13 in a single frame (117 ADU of noise on a
    # sky of 1552) and only exists in the combination.
    #
    # The split between EXTENDED and ISOLATED is what makes the mask usable:
    # a star is extended (its core plus its halo) and a hot pixel is one
    # pixel, fixed on the sensor. Measured on FG18: 10,150 isolated against 99
    # extended, and dilating the isolated ones masked 50 % of the frame.
    from scipy import ndimage
    sigma = PSEUDO_FLAT_MASK_SIGMA if sigma is None else float(sigma)
    dilate = PSEUDO_FLAT_MASK_DILATE if dilate is None else int(dilate)
    diff = raw - ref
    noise = float(outliers.scaled_mad(diff.ravel()))
    flag = diff > sigma * max(noise, 1e-6)
    lab, nl = ndimage.label(flag)
    sizes = np.bincount(lab.ravel())[1:] if nl else np.array([])
    big = np.zeros_like(flag)
    hot = np.zeros_like(flag)
    if nl:
        big = np.isin(lab, np.nonzero(sizes > PSEUDO_FLAT_HOT_MAX_PX)[0] + 1)
        hot = np.isin(lab, np.nonzero(sizes <= PSEUDO_FLAT_HOT_MAX_PX)[0] + 1)
    mask = ndimage.binary_dilation(big, iterations=dilate) if dilate else big
    stats = {"n_sources": int(nl), "n_hot": int(hot.sum()),
             "n_masked": int(mask.sum()), "noise": noise}
    return mask, hot, stats


def _fill_masked(x, mask, window, passes):
    # THE FILL AND THE SMOOTHING ARE THE SAME OPERATION: a normalised
    # convolution, uniform(x * m) / uniform(m), which is a box filter that
    # ignores what is missing and interpolates it from the sky around it. It
    # is what makes a full-resolution flat WITH dust possible on a static
    # field, where the pixels under a star hold no data in any frame.
    #
    # The price, said and not hidden: a dust mote sitting UNDER a star cannot
    # be recovered, and the fraction filled is reported.
    # @return: (filled float32, filled_pct)
    from scipy import ndimage
    valid = np.isfinite(x) & ~mask
    y = np.where(valid, x, 0.0).astype(np.float32)
    v = valid.astype(np.float32)
    filled = float(100.0 * (1.0 - v.mean()))
    for _ in range(max(1, int(passes))):
        num = ndimage.uniform_filter(y, size=int(window), mode="nearest")
        den = ndimage.uniform_filter(v, size=int(window), mode="nearest")
        ok = den > 1e-6
        y = np.where(ok, num / np.where(ok, den, 1.0), 0.0).astype(np.float32)
        v = ok.astype(np.float32)
    return y, filled


class _OffsetSubtractor:
    # A loader that removes the offset (dark or bias) as the frames are read,
    # so the pseudo-flat is built from frames with the SAME pedestal as the
    # light. Without it the division mixes two different things and the flat
    # comes out COMPRESSED: measured on 1 s twilight frames of FG18, the
    # pedestal is 827 ADU over a sky of 661 (56 % of the level) and the
    # correction drops to 44 % of what it should be.
    #
    # The recipe is resolved from EACH frame's own header and cached by the
    # key the recipe itself uses, so a visit is one query and not two hundred.

    def __init__(self, db, cfg=None):
        self._db = db
        self._tol = (cfg.get("calib_temp_tol_c", _DEFAULT_TEMP_TOL_C)
                     if cfg is not None else _DEFAULT_TEMP_TOL_C)
        self._cache = {}
        self.applied = set()          # the master names that were used
        self.seen_paths = set()       # frames, not calls: the loader is asked
        self.missing_paths = set()    # once PER BAND, so counting calls said
                                      # 6,624 missing for a 207-frame visit

    def __call__(self, path, box=None):
        data, header = read_image(path, box)
        out = _as_float32(data)
        self.seen_paths.add(path)
        try:
            meta = meta_from_header(header)
            temp = meta.get("temp_c")
            key = (meta.get("camera"), meta.get("gain"),
                   meta.get("exptime_s"), meta.get("filter"),
                   (None if temp is None
                    else int(round(float(temp) / max(self._tol, 1e-6)))))
            recipe = self._cache.get(key)
            if recipe is None:
                recipe = resolve_recipe(self._db, meta, tol_c=self._tol)
                self._cache[key] = recipe
        except Exception as err:                  # never break the flat
            logger.warning("pseudo-flat: the offset could not be resolved "
                           "for %s (%s)", path, err)
            self.missing_paths.add(path)
            return out
        if recipe.offset is None:
            self.missing_paths.add(path)
            return out
        try:
            off = _as_float32(read_image(recipe.offset.path, box))
        except Exception as err:
            logger.warning("pseudo-flat: the offset master could not be read "
                           "(%s)", err)
            self.missing_paths.add(path)
            return out
        if off.shape != out.shape:
            self.missing_paths.add(path)
            return out
        self.applied.add(Path(recipe.offset.path).name)
        return out - off

    def summary(self):
        # @return: how the pedestal was treated, for the flat's own report.
        #          The counts are FRAMES and not calls, which is what the
        #          observer reads.
        return {"applied": sorted(self.applied),
                "n_applied": len(self.seen_paths - self.missing_paths),
                "n_missing": len(self.missing_paths)}


def pseudo_flat(paths, window=None, passes=None, order=None, loader=None,
                progress=None, cancel=None, db=None, cfg=None,
                mask_sigma=None, mask_dilate=None):
    # @args: paths - the light frames of the visit, window/passes/order - the
    #        recipe's knobs (defaults above), loader - callable(path, box) ->
    #        array, progress - callable(done, total), cancel - callable() ->
    #        True to stop, db - Database (with it the pedestal is removed from
    #        the frames first, see _OffsetSubtractor), cfg - Config (for the
    #        temperature tolerance), mask_sigma/mask_dilate - the source
    #        mask's knobs (defaults above; the tests use them to turn the mask
    #        off and prove it is what keeps the stars out)
    # @return: (flat float32, info dict) or (None, info) when it cannot be
    #          built
    # A FLAT MADE FROM THE FRAMES THEMSELVES, for the observer who has none
    # (which is most of them: ADR-061 could only warn "no flat for this
    # filter" and leave the dust and the vignetting in).
    #
    # The physics is that the train's dust and the sensor's vignetting are
    # FIXED on the frame, so they survive any statistic taken over the frames,
    # while the stars MOVE. When they do NOT move (measured on FG18: 2 px of
    # drift over 207 frames, 17 to 33 stars matched) the statistic alone
    # cannot remove them, so the sources are MASKED, the masked pixels are
    # dropped, and the flat is INTERPOLATED there from the sky around them.
    # What comes out is a multiplicative map of the train, normalised to a
    # median of one, with no star in it: measured against the author's own
    # real flat, the maximum agrees to 0.3 % (1.1137 against 1.1102) where
    # the version without the mask gave 2.83.
    #
    # It is NOT a substitute for a real flat: a true flat measures the train's
    # response and this one measures that response times the sky's shape, so
    # the flat-field error is larger (measured: 4.16 % = 0.045 mag with the
    # pedestal removed). It is the honest fallback, and the recipe line says
    # which one was used.
    window = int(PSEUDO_FLAT_WINDOW if window is None else window)
    passes = int(PSEUDO_FLAT_PASSES if passes is None else passes)
    order = float(PSEUDO_FLAT_ORDER if order is None else order)
    subtractor = _OffsetSubtractor(db, cfg) if db is not None else None
    load = subtractor if subtractor is not None else (loader or read_image)
    paths = list(paths or [])
    info = {"n_frames": len(paths), "window": window, "passes": passes,
            "order": order, "median_adu": None, "residual_pct": None,
            "kind": "pseudo_flat", "model_range": None, "note": "",
            "mask_pct": None, "filled_pct": None, "hot_px": None,
            "n_sources": None, "verify_pct": None, "offset": None,
            "seconds": None}
    if not paths:
        info["note"] = "no frames to build a flat from"
        return None, info
    t0 = time.time()
    from scipy import ndimage
    try:
        header = read_header(paths[0])
        ny = int(header.get("NAXIS2", 0))
        nx = int(header.get("NAXIS1", 0))
    except Exception:
        ny = nx = 0
    if ny <= 0 or nx <= 0:
        info["note"] = "the first frame does not say its size"
        return None, info
    raw = np.empty((ny, nx), dtype=np.float32)
    total = len(paths)
    for y0 in range(0, ny, _PSEUDO_FLAT_ROWS):
        if cancel is not None and cancel():
            info["note"] = "cancelled"
            return None, info
        y1 = min(ny, y0 + _PSEUDO_FLAT_ROWS)
        band = np.empty((total, y1 - y0, nx), dtype=np.float32)
        for k, path in enumerate(paths):
            try:
                data = load(path, (0, y0, nx, y1))
            except Exception as err:
                logger.warning("pseudo-flat: %s could not be read (%s)",
                               path, err)
                band[k] = np.nan
                continue
            band[k] = _as_float32(data)
        # The order statistic over the FRAMES, per pixel: the stars move, the
        # train does not. It is taken with a PARTITION and not with
        # np.percentile: the percentile sorts (or interpolates) the whole
        # band, and the answer wanted here is one element of the ordered
        # list, which partition gives in O(n) instead of O(n log n).
        # Measured on the real 2025 UR visit (140 frames of 2048x2048): 197 s
        # with the percentile, 12 s with the partition, and the same flat.
        #
        # The low order is also what makes a NaN frame harmless: a partition
        # puts the NaNs at the end of the ordering, and the 33rd percentile
        # of 140 frames is nowhere near them.
        k = int(round(order * (band.shape[0] - 1)))
        k = max(0, min(band.shape[0] - 1, k))
        with np.errstate(invalid="ignore"):
            raw[y0:y1] = np.partition(band, k, axis=0)[k]
        if progress is not None:
            progress(y1, ny)
    if not np.isfinite(raw).any():
        info["note"] = "no frame could be read"
        return None, info
    raw = np.nan_to_num(raw, nan=float(np.nanmedian(raw)))
    if subtractor is not None:
        info["offset"] = subtractor.summary()
    # The smoothed percentile: the reference the mask is measured against, and
    # the smoothing the flat used to have.
    smooth = raw
    for _ in range(max(1, passes)):
        smooth = ndimage.uniform_filter(smooth, size=window, mode="nearest")
    norm0 = float(np.median(smooth))
    if not np.isfinite(norm0) or norm0 <= 0:
        info["note"] = "the flat has a non-positive median"
        return None, info
    # How much small-scale structure survived the smoothing, as a FIGURE and
    # not as the check: a scaled MAD is robust, so a flat carrying the stars
    # (a maximum of 2.83) moves it by nothing at all (measured: 0.06 % with
    # the stars, 0.05 % without them). The check is verify_pct, below.
    inner = raw[window:-window, window:-window] if ny > 3 * window else raw
    ref = smooth[window:-window, window:-window] if ny > 3 * window else smooth
    if inner.size and ref.size:
        ratio = (inner / np.maximum(ref, 1e-6)) - 1.0
        info["residual_pct"] = float(100.0 * outliers.scaled_mad(
            ratio.ravel()))
    # THE MASK, BEFORE ANYTHING ELSE IS DECIDED: the stars never enter the
    # flat, and the hot pixels stay in it.
    mask, hot, mstats = _star_mask(raw, smooth, sigma=mask_sigma,
                                   dilate=mask_dilate)
    info["mask_pct"] = float(100.0 * mask.mean())
    info["hot_px"] = int(hot.sum())
    info["n_sources"] = int(mstats["n_sources"])
    # THE FILL, which is also the smoothing.
    flat_raw, filled = _fill_masked(raw, mask, window, passes)
    info["filled_pct"] = filled
    # THE HOT PIXELS GO BACK AFTER THE SMOOTHING. They are FIXED, so they are
    # part of the train's response and the division removes them; but the box
    # filter would dilute a single pixel 1681 times and the division would
    # then leave it exactly where it was (measured: 1484 ADU in the smoothed
    # flat against 1744 in the statistic, over a sky of 1488).
    if hot.any():
        flat_raw = np.where(hot, raw, flat_raw)
    norm = float(np.median(flat_raw))
    if not np.isfinite(norm) or norm <= 0:
        info["note"] = "the flat has a non-positive median"
        return None, info
    flat = (flat_raw / norm).astype(np.float32)
    info["median_adu"] = norm
    info["seconds"] = time.time() - t0
    # The flat's own range, and the one figure that says whether a STAR got in:
    # its maximum OUTSIDE the hot pixels. The hot pixels are deliberately kept
    # in the flat (the division removes them) and on a 1 s twilight frame they
    # reach 6.2 times the sky, so the raw maximum says nothing by itself: the
    # measured FG18 flat goes to 6.22 with them and to 1.11 without, against a
    # real flat's 1.11.
    info["flat_min"] = float(flat.min())
    info["flat_max"] = float(flat.max())
    info["flat_max_no_hot"] = float(flat[~hot].max()) if hot.any() \
        else float(flat.max())
    # THE CHECK: how far the flat deviates from its own smoothed version AT
    # THE PIXELS THAT WERE MASKED, which is where a star was and therefore
    # where a bump cannot exist. Measured: 33.83 % on the flat that carried
    # the stars, 2.11 % on this one, and 4.58 % on the real master (which
    # carries the dust, and the dust is not masked and is a dip).
    if mask.any():
        ref2 = flat
        for _ in range(max(1, passes)):
            ref2 = ndimage.uniform_filter(ref2, size=window, mode="nearest")
        dev = np.abs((flat / np.maximum(ref2, 1e-6)) - 1.0)[mask]
        info["verify_pct"] = float(100.0 * np.percentile(dev, 99))
    if filled > PSEUDO_FLAT_MAX_FILLED_PCT:
        # Not enough sky left to build a flat: what IS usable is the
        # VIGNETTING, which is smooth, so a low-order surface is fitted where
        # there are no sources. It does not correct the dust and it says so.
        model, why = _vignetting_model(raw, mask)
        if model is None:
            info["note"] = ("the sources cover almost the whole frame, so a "
                            "flat from it would be all interpolation: " + why)
            return None, info
        info["kind"] = "vignette_model"
        info["median_adu"] = float(np.median(raw))
        info["model_range"] = (float(model.min()), float(model.max()))
        info["note"] = ("a smooth model of the vignetting (the sources cover "
                        f"{filled:.0f} % of the frame, so a flat from it "
                        "would be all interpolation): it does not correct "
                        "the dust")
        return model, info
    if info["verify_pct"] is not None \
            and info["verify_pct"] > PSEUDO_FLAT_VERIFY_PCT:
        info["note"] = ("the flat still deviates "
                        f"{info['verify_pct']:.1f} % over the sources that "
                        "were masked: it may still carry them")
    return flat, info


class FrameCalibrator:
    # A LOADER that calibrates on the way in. The stacking engine reads each
    # frame many times and in pieces (the registration wants the whole frame,
    # the warp wants a box per candidate of the sweep), so writing calibrated
    # copies to disk first would cost gigabytes of I/O per visit; applying
    # the recipe as the pixels are read costs one division per read and keeps
    # ADR-061's promise (calibration works in memory).
    #
    # The recipe is resolved from EACH frame's own header, because the
    # camera, the gain, the temperature, the exposure and the filter are what
    # make a master valid; the resolution is CACHED by that key rounded to
    # the tolerance the recipe itself uses, so a visit (one camera, one
    # filter, one temperature within a degree) is one database query and not
    # one hundred.
    #
    # @args: db - Database, cfg - Config (for the temperature tolerance),
    #        pseudo_flat - a flat built from the frames themselves (see
    #        pseudo_flat), used when the library has no flat for the filter

    def __init__(self, db, cfg=None, pseudo_flat=None):
        self._db = db
        self._cfg = cfg
        self._pseudo_flat = pseudo_flat
        self._tol = (cfg.get("calib_temp_tol_c", _DEFAULT_TEMP_TOL_C)
                     if cfg is not None else _DEFAULT_TEMP_TOL_C)
        self._cache = {}
        self.reports = []          # one (path, report) per frame read

    def __call__(self, path, box=None):
        # @args: path - the frame, box - optional (x0, y0, x1, y1) region
        # @return: the calibrated float32 array, in the shape the caller
        #          asked for. The header is NOT returned: the callers that
        #          need it read it themselves, and calibrating does not
        #          change it.
        data, header = read_image(path, box)
        meta = meta_from_header(header)
        temp = meta.get("temp_c")
        key = (meta.get("camera"), meta.get("gain"), meta.get("exptime_s"),
               meta.get("filter"),
               (None if temp is None
                else int(round(float(temp) / max(self._tol, 1e-6)))))
        recipe = self._cache.get(key)
        if recipe is None:
            recipe = resolve_recipe(self._db, meta, tol_c=self._tol)
            self._cache[key] = recipe
        out, report = calibrate(data, recipe, box=box,
                                pseudo_flat=self._pseudo_flat)
        self.reports.append((path, report))
        return out

    def summary(self):
        # @return: what was applied, for the run's note: the masters' names
        #          and the warnings, deduplicated. The observer has to know
        #          what the magnitude was measured with.
        offsets, flats, warnings = set(), set(), []
        for _path, report in self.reports:
            if report.offset_path:
                offsets.add(Path(report.offset_path).name
                            if report.offset_path != "pseudo-flat"
                            else report.offset_path)
            if report.flat_path:
                flats.add(Path(report.flat_path).name
                          if report.flat_path != "pseudo-flat"
                          else report.flat_path)
            for note in report.warnings:
                if note not in warnings:
                    warnings.append(note)
        return {"n": len(self.reports),
                "offsets": sorted(offsets), "flats": sorted(flats),
                "warnings": warnings[:4]}


def calibrate(data, recipe, loader=None, box=None, pseudo_flat=None):
    # @args: data - the light (raw, 2D), recipe - Recipe,
    #        loader - callable(path, box) -> array, box - optional region,
    #        pseudo_flat - a normalised flat built from the frames
    #        themselves (see pseudo_flat), used ONLY when the library has no
    #        flat for this filter
    # @return: (calibrated float32 array, CalibrationReport)
    # The order is offset first, flat second: dividing before removing the
    # pedestal would amplify it in the flat's dark corners.
    masters = load_masters(recipe, loader=loader, box=box)
    report = CalibrationReport(warnings=list(recipe.warnings))
    out = _as_float32(data)
    if masters.offset is not None and masters.offset.shape == out.shape:
        report.pedestal_adu = float(np.median(masters.offset))
        out = out - masters.offset
        report.offset_kind = recipe.offset_kind
        report.offset_path = recipe.offset.path
    elif masters.offset is not None:
        report.warnings.append(
            "the offset master does not match the frame size; not applied")
    # A real flat from the library always wins: it measures the train's
    # response, while a pseudo-flat measures the response times the sky's
    # shape. The pseudo-flat is the fallback, and it says so in the report.
    flat = masters.flat
    flat_norm = masters.flat_norm
    flat_path = recipe.flat.path if recipe.flat is not None else None
    if flat is None and pseudo_flat is not None:
        pf = _as_float32(pseudo_flat)
        if box is not None and pf.shape != out.shape:
            x0, y0, x1, y1 = box
            pf = pf[y0:y1, x0:x1]
        if pf.shape == out.shape:
            flat = pf
            flat_norm = float(np.median(pf)) or 1.0
            flat_path = "pseudo-flat"
    if flat is not None and flat.shape == out.shape:
        out = out / flat
        report.flat_path = flat_path
        report.flat_norm = flat_norm
        if flat_path == "pseudo-flat":
            # The recipe warned "no flat for this filter" and it was right:
            # there was none. The pseudo-flat is what stands in for it, so
            # repeating the warning beside it would be a lie in the same
            # line (measured: the run's summary said both at once).
            report.warnings = [w for w in report.warnings
                               if "no flat for this filter" not in w]
    elif flat is not None:
        report.warnings.append(
            "the flat does not match the frame size; not applied")
    report.ok = report.offset_kind is not None and report.flat_path is not None
    return out, report


def calibrate_paths(paths, db, cfg=None, master_loader=None, box=None,
                    progress=None, cancel=None, pseudo_flat=None):
    # @args: paths - light FITS paths, db - Database, cfg - Config (for the
    #        temperature tolerance), master_loader - callable(path, box) ->
    #        array for the MASTERS (the light is always read from disk with
    #        read_image, which also gives its header), box - optional region,
    #        progress - callable(done, total, label), cancel - callable()
    #        -> True to stop, pseudo_flat - a flat built from the frames
    #        themselves (see pseudo_flat) for the filters the library has no
    #        flat for
    # @return: list[(path, data, header, report)]
    # The light's header decides the recipe, so this is the entry point the
    # GUI and the stacking engine will call frame by frame.
    tol = None
    if cfg is not None:
        tol = cfg.get("calib_temp_tol_c", _DEFAULT_TEMP_TOL_C)
    out = []
    total = len(paths)
    for index, path in enumerate(paths, 1):
        if cancel is not None and cancel():
            break
        data, header = read_image(path, box)
        meta = meta_from_header(header)
        recipe = resolve_recipe(db, meta, tol_c=tol)
        data_cal, report = calibrate(data, recipe, loader=master_loader,
                                     box=box, pseudo_flat=pseudo_flat)
        out.append((path, data_cal, header, report))
        if progress is not None:
            progress(index, total, path)
    return out


def export_calibrated(data, header, out_path, report=None):
    # @args: data - calibrated array, header - the original header dict,
    #        out_path - where to write, report - CalibrationReport (its
    #        trace goes into the header so the copy is auditable)
    # @return: the path written
    # astropy keeps the rest of the header and adds the provenance: which
    # masters were used and their paths, so a calibrated copy can be traced
    # back to the library that produced it.
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.asarray(data, dtype=np.float32))
    for key, value in (header or {}).items():
        if key in ("SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2",
                   "EXTEND", "BSCALE", "BZERO"):
            continue
        try:
            hdu.header[key] = value
        except (ValueError, TypeError):
            continue
    hdu.header["HISTORY"] = "NightScribe calibration (ADR-061)"
    if report is not None:
        if report.offset_path:
            hdu.header["HISTORY"] = f"offset ({report.offset_kind}): " \
                                    f"{report.offset_path}"
        if report.flat_path:
            hdu.header["HISTORY"] = f"flat: {report.flat_path} " \
                                    f"(norm {report.flat_norm:.3g})"
        for note in report.warnings:
            hdu.header["HISTORY"] = f"warning: {note}"
    hdu.writeto(str(out_path), overwrite=True)
    return str(out_path)


def export_flat(flat, out_path, info=None, header=None):
    # @args: flat - the flat (normalised, float32), out_path - where to write,
    #        info - the pseudo_flat info dict (its figures go into the header),
    #        header - an optional header to carry over (the first frame's)
    # @return: the path written
    # THE FLAT IS A PRODUCT OF THE VISIT, and it is written so it can be
    # LOOKED AT. The observer's own criterion for "this is a flat and not a
    # map of the stars" is to see it, and a figure in a note is not the same
    # thing. It is also what makes it auditable, and what lets it be taken to
    # another tool (PixInsight included) to be compared or refined.
    #
    # The cards are short, because a FITS keyword is 8 characters, and each
    # one carries a figure the flat was built with.
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.asarray(flat, dtype=np.float32))
    for key in ("INSTRUME", "TELESCOP", "FILTER", "GAIN", "EXPTIME",
                "CCD-TEMP", "DATE-OBS", "OBJECT", "SITELAT", "SITELONG"):
        if header and key in header:
            try:
                hdu.header[key] = header[key]
            except (ValueError, TypeError):
                continue
    hdu.header["IMAGETYP"] = "FLAT"
    hdu.header["HISTORY"] = "NightScribe pseudo-flat (ADR-069)"

    def _round(value):
        # @return: the figure rounded for a FITS card, or None when there is
        #          nothing to say (a missing figure is not a zero)
        return None if value is None else round(float(value), 3)

    if info:
        for key, value in (("NS_FLAT", info.get("kind")),
                           ("NS_NFRA", info.get("n_frames")),
                           ("NS_MASK", _round(info.get("mask_pct"))),
                           ("NS_FILL", _round(info.get("filled_pct"))),
                           ("NS_HOT", info.get("hot_px")),
                           ("NS_VERIF", _round(info.get("verify_pct"))),
                           ("NS_RESID", _round(info.get("residual_pct")))):
            if value is None:
                continue
            try:
                hdu.header[key] = value
            except (ValueError, TypeError):
                continue
        off = info.get("offset") or {}
        if off.get("n_applied"):
            hdu.header["HISTORY"] = ("offset removed: "
                                     + ", ".join(off.get("applied") or []))
        elif off.get("n_missing"):
            hdu.header["HISTORY"] = ("no dark/bias: the pedestal stays in "
                                     "the flat and compresses its shape")
        if info.get("note"):
            hdu.header["HISTORY"] = "note: " + str(info["note"])
    hdu.writeto(str(out_path), overwrite=True)
    return str(out_path)
