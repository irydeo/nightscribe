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
from dataclasses import dataclass, field

import numpy as np

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
    data = np.asarray(raw).astype(np.float32)
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
    # light's, so exposure is not part of the match.
    flat = find_master(db, "flat", camera, gain, temp, exptime_s=None,
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
    # @args: data - array (any float/int dtype)
    # @return: the same data as float32 (half the memory, plenty of
    #          precision: 7 significant digits beat photon noise)
    return np.asarray(data, dtype=np.float32)


def calibrate(data, recipe, loader=None, box=None):
    # @args: data - the light (raw, 2D), recipe - Recipe,
    #        loader - callable(path, box) -> array, box - optional region
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
    if masters.flat is not None and masters.flat.shape == out.shape:
        out = out / masters.flat
        report.flat_path = recipe.flat.path
        report.flat_norm = masters.flat_norm
    elif masters.flat is not None:
        report.warnings.append(
            "the flat does not match the frame size; not applied")
    report.ok = report.offset_kind is not None and report.flat_path is not None
    return out, report


def calibrate_paths(paths, db, cfg=None, master_loader=None, box=None,
                    progress=None, cancel=None):
    # @args: paths - light FITS paths, db - Database, cfg - Config (for the
    #        temperature tolerance), master_loader - callable(path, box) ->
    #        array for the MASTERS (the light is always read from disk with
    #        read_image, which also gives its header), box - optional region,
    #        progress - callable(done, total, label), cancel - callable()
    #        -> True to stop
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
                                     box=box)
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
