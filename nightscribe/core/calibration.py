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
  flat needs its own offset removed first (a dark at the flat's exposure,
  or the bias if the flat is short), or the division amplifies the pedestal
  in the dark corners of the flat.

The order matters: offset first, flat second.

The library holds THREE kinds (bias, dark, flat). What each one is matched
on is decided by physics, not by convenience: a dark carries the level, so
it needs the exposure and the temperature; a flat carries a SHAPE that is
the optical train's, so it needs neither (its level is normalised away);
and a bias is a read-out pedestal, which barely moves with the
temperature. When a piece is missing, the recipe says WHY with the numbers
(Recipe.notes), so an observer who can see the master in the library learns
which criterion left it out instead of reading "no flat" and giving up.

Reading a FITS is not obvious either (ADR-060, D32): astropy refuses to
memory-map an image whose header carries BSCALE/BZERO/BLANK (the usual
uint16-as-int16 of CMOS cameras), so frames are opened with
``do_not_scale_image_data=True`` and the scaling is applied here, by hand,
in float32.
"""

import datetime
import json
import logging
import re
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
# DATE-OBS is the observation's own instant; DATE is often just the file's
# creation time, so it is the last resort.
_DATE_KEYS = ("DATE-OBS", "DATEOBS", "DATE")

# Matching tolerances. Exposure is exact on purpose: in CMOS the thermal
# pattern does not scale linearly with time, so a dark at another exposure
# leaves a residual. Temperature is tolerant because its effect is smooth
# and monotone, and +/-3 C is what the author accepts.
_EXPTIME_TOL_S = 1e-3
_GAIN_TOL = 1e-6
_DEFAULT_TEMP_TOL_C = 3.0

# Above this many days between the flat and the light, the flat is used but
# the recipe warns: the train's dust moves, and a flat from weeks ago may
# carry a mote that is no longer there (or miss one that is). Measured on
# the author's own case: a flat 53 days older than the lights was the one
# the library held.
FLAT_AGE_WARN_DAYS = 30

# The THREE kinds of master the library knows. A "dark of the flats" is not
# a kind of its own: it is a DARK at the flat's exposure, and the exposure
# is what the matching already keys on. Keeping it as a fourth kind asked
# the observer to classify the same frame twice (ADR-061 rev).
KINDS = ("bias", "dark", "flat")


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
    #
    # A region is a SLICE of the memmapped frame, and NOT `hdu.section`:
    # astropy's section reads a window row by row (a 774^2 window from a
    # 2048^2 frame cost 16.5 ms), while slicing the memmap and copying the
    # window costs 1.1 ms, x15 faster (measured 2026-10-15). This is the
    # single hottest read of the stacking: the warp asks for one region per
    # frame and per candidate, so the visit's reads went from minutes to
    # seconds. The copy is made WHILE the file is open, so nothing outlives
    # the memmap.
    from astropy.io import fits
    with fits.open(path, memmap=True, do_not_scale_image_data=True) as hdul:
        hdu = _first(hdul)
        if hdu is None:
            raise ValueError(f"{path}: no 2D image HDU")
        if box is not None:
            x0, y0, x1, y1 = box
            raw = hdu.data[y0:y1, x0:x1]
        else:
            raw = hdu.data
        data = np.array(raw, dtype=np.float32)
        header = dict(hdu.header)
    if data.ndim != 2:
        # A region that does not touch the frame comes back EMPTY and can be
        # 1-D; a 1-D "image" breaks the caller three layers away: scipy sees
        # input.ndim + 1 == 2, takes our 2x2 rotation for a HOMOGENEOUS matrix,
        # finds the bottom row is not [0, 1] and refuses it with "Expected
        # homogeneous transformation matrix with shape (2, 2) for image shape
        # (0,)" (measured on a real visit). An empty 2-D array says the same
        # thing (there is no data here) without the trap, and every caller
        # already handles a zero-sized array.
        data = data.reshape((0, 0))
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
    # @return: dict {camera, gain, temp_c, exptime_s, filter, date_obs}
    #          (missing: None)
    # The same tolerant lookup is used to index a master and to ask for the
    # recipe of a light, so the two speak the same language. date_obs is not
    # part of the matching key: it is what tells the recipe how old a flat is.
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
    for key in _DATE_KEYS:
        if header.get(key):
            out["date_obs"] = str(header[key]).strip()
            break
    else:
        out["date_obs"] = None
    return out


def parse_date_obs(text):
    # @args: text - a FITS date ("2026-10-13T19:40:58.875", or a bare date)
    # @return: a naive datetime, or None when it cannot be read
    # Timezone-aware strings are accepted and their offset dropped: the age
    # is read in days, so a few hours of offset change nothing.
    if not text:
        return None
    text = str(text).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    return parsed.replace(tzinfo=None)


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
    # Newest first, and the id breaks a tie: masters indexed in the same
    # second (a whole folder at once, the usual way) would otherwise come
    # back in insertion order and the "newest wins" rule would pick the
    # oldest of the batch.
    out.sort(key=lambda m: (m.created or "", m.id), reverse=True)
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


# ------------------------------------------------ what a frame IS (ADR-061 rev)
#
# The observer should not have to classify a frame by hand: a calibration
# frame says what it is in its own header, and asking "is this a dark or a
# dark of the flats?" made the observer answer a question the frame already
# answers (a dark of the flats IS a dark, at the flat's exposure).
_IMAGETYP_KEYS = ("IMAGETYP", "IMAGETYPE", "OBSTYPE", "FRAME")
_IMAGETYP_KINDS = {
    "bias": "bias", "biasframe": "bias", "zero": "bias",
    "dark": "dark", "darkframe": "dark",
    "darkflat": "dark", "flatdark": "dark", "darkforflat": "dark",
    "flat": "flat", "flatfield": "flat", "skyflat": "flat",
    "domeflat": "flat", "twilightflat": "flat", "lampflat": "flat",
}
_IMAGETYP_LIGHTS = ("light", "object", "science", "target")
# The exposure is the only fallback when IMAGETYP is missing, and it is a
# NARROW one on purpose: a 0.005 s flat and a bias are both "short", so only
# an exposure at zero is called a bias, and only a clearly long one (the
# usual minutes-long dark) is called a dark. Anything in between is not
# guessed: the observer is asked, because guessing wrong puts the frame in
# the wrong arithmetic.
_BIAS_MAX_EXPTIME_S = 1e-3
_DARK_MIN_EXPTIME_S = 5.0


def classify_master(path):
    # @args: path - a FITS frame the observer wants to index
    # @return: (kind, None) with kind one of KINDS, or (None, why) when it
    #          cannot be told (why is plain language, for the observer)
    # IMAGETYP first, because that is what the frame itself says; the
    # exposure only as a last resort, and only where it is unambiguous.
    try:
        header = read_header(path)
    except Exception as err:
        return None, f"the header could not be read ({err})"
    raw = None
    for key in _IMAGETYP_KEYS:
        value = header.get(key)
        if value:
            raw = str(value).strip()
            break
    if raw:
        norm = re.sub(r"[^a-z]", "", raw.lower())
        if norm in _IMAGETYP_KINDS:
            return _IMAGETYP_KINDS[norm], None
        if norm in _IMAGETYP_LIGHTS:
            return None, ("this is a LIGHT frame, not a calibration "
                          "master")
        return None, f"IMAGETYP says {raw!r}, which is not a master kind"
    exptime = meta_from_header(header).get("exptime_s")
    if exptime is not None and exptime <= _BIAS_MAX_EXPTIME_S:
        return "bias", None
    if exptime is not None and exptime >= _DARK_MIN_EXPTIME_S:
        return "dark", None
    return None, ("IMAGETYP is missing and the exposure alone cannot tell "
                  "a flat from a dark: add IMAGETYP to the frame")


_DATE_CACHE = {}


def master_date_obs(ref):
    # @args: ref - a MasterRef
    # @return: the frame's own DATE-OBS as a string, or None when it is not
    #          known and cannot be read
    # The index stores the date since ADR-061 rev; a row indexed before that
    # carries none, so it is read from the master's own header ONCE and
    # remembered. Without this the age of an existing flat (the author's:
    # 53 days) would stay invisible.
    key = str(ref.path)
    if key in _DATE_CACHE:
        return _DATE_CACHE[key]
    date = (ref.meta or {}).get("date_obs")
    if not date:
        try:
            date = meta_from_header(read_header(ref.path)).get("date_obs")
        except Exception as err:                 # a header is never fatal
            logger.warning("master %s: its date could not be read (%s)",
                           ref.path, err)
            date = None
    _DATE_CACHE[key] = date
    return date


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


def _rejections(ref, camera=None, gain=None, temp_c=None, exptime_s=None,
                filter=None, tol_c=None):
    # @args: ref - a MasterRef, the rest - what the light asks for
    # @return: the criteria this master FAILS, as (name, master value,
    #          wanted value); an empty list means it matches
    # One function decides the match and the same one explains a miss, so
    # the "no flat" line and the matching can never disagree about why a
    # master was left out. A criterion left as None is IGNORED (the caller
    # may not know it): that is what lets the flat be matched without a
    # temperature, or the bias without a gain.
    bad = []
    if camera is not None and ref.camera is not None \
            and not _same_text(ref.camera, camera):
        bad.append(("camera", ref.camera, camera))
    if gain is not None and ref.gain is not None \
            and not _close(ref.gain, gain, _GAIN_TOL):
        bad.append(("gain", ref.gain, gain))
    if exptime_s is not None and ref.exptime_s is not None \
            and not _close(ref.exptime_s, exptime_s, _EXPTIME_TOL_S):
        bad.append(("exposure", ref.exptime_s, exptime_s))
    if filter is not None and ref.filter is not None \
            and not _same_text(ref.filter, filter):
        bad.append(("filter", ref.filter, filter))
    if temp_c is not None and ref.temp_c is not None:
        tol = _DEFAULT_TEMP_TOL_C if tol_c is None else float(tol_c)
        if abs(ref.temp_c - float(temp_c)) > tol:
            bad.append(("temperature", ref.temp_c, temp_c))
    return bad


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
    best = None
    best_delta = None
    for ref in list_masters(db, kind=kind):
        if _rejections(ref, camera, gain, temp_c, exptime_s, filter, tol_c):
            continue
        delta = None
        if ref.temp_c is not None and temp_c is not None:
            delta = abs(ref.temp_c - float(temp_c))
        if best is None or _prefer(delta, ref, best_delta, best):
            best, best_delta = ref, delta
    return best


def closest_rejected(db, kind, camera=None, gain=None, temp_c=None,
                     exptime_s=None, filter=None, tol_c=None):
    # @args: db - Database, kind - one of KINDS, the rest - what the light
    #        asks for
    # @return: (ref, bad) the master of this kind that came CLOSEST to
    #          matching, with the criteria it failed, or (None, []) when
    #          the library holds none of this kind at all
    # The observer who reads "no flat" while KNOWING there is one needs the
    # reason, not a shrug: a master of the right camera with one criterion
    # off beats a stranger that fails everything.
    best, best_bad, best_rank = None, [], None
    for ref in list_masters(db, kind=kind):
        bad = _rejections(ref, camera, gain, temp_c, exptime_s, filter, tol_c)
        if not bad:
            continue
        same_cam = camera is not None and _same_text(ref.camera, camera)
        rank = (0 if same_cam else 1, len(bad))
        if best_rank is None or rank < best_rank:
            best, best_bad, best_rank = ref, bad, rank
    return best, best_bad


def _prefer(delta, ref, best_delta, best):
    # @args: delta - temperature distance of the candidate (or None),
    #        ref - candidate, best_delta/best - current winner
    # @return: True when the candidate wins
    # Nearest temperature first; ties go to the most recent, which is what
    # list_masters returns first. When there is no temperature to compare
    # (delta is None, either because the light does not know its own or the
    # master does not carry one) nothing improves on the first candidate, so
    # it stands: the newest wins. Returning True here would walk all the way
    # to the OLDEST, which is how a flat with no temperature criterion came
    # out years old (measured on the author's library, 2026-10-14).
    if delta is None:
        return False
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
    # WHY a piece could not be found, WITH the numbers, one dict per miss:
    # {"what": "dark"|"bias"|"flat", "reason": "camera"|"gain"|"exposure"|
    #  "filter"|"temperature"|"age", "master": the file name, "value": what
    #  the master has, "wanted": what the light asks for, "tol": the
    #  tolerance it broke, "days": the flat's age}. The warnings stay short
    #  and stable (the log and the run's own note read them); these carry
    #  the detail that lets the observer FIX the library instead of
    #  guessing why the master he can see was not used (ADR-061 rev).
    notes: list[dict] = field(default_factory=list)


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
    # The frame already carried NightScribe's calibration (NSCALIB) and was
    # left as it was: the recipe was NOT applied. It is a fact the run's note
    # and the Calibration tab have to say, because "calibrated" and "already
    # calibrated" are not the same thing to the observer.
    already: bool = False


def _note(recipe, what, reason, master=None, value=None, wanted=None,
          tol=None, days=None):
    # @args: recipe - the Recipe being built, what - "dark"|"bias"|"flat",
    #        reason - the criterion that failed, master - the file left out,
    #        value/wanted - what it has against what the light asks for,
    #        tol - the tolerance it broke, days - the flat's age
    # @return: None
    recipe.notes.append({
        "what": what, "reason": reason,
        "master": Path(master).name if master else None,
        "value": value, "wanted": wanted, "tol": tol, "days": days})


def _note_missing(recipe, db, kind, what, camera=None, gain=None, temp_c=None,
                  exptime_s=None, filter=None, tol_c=None):
    # @args: recipe - the Recipe being built, db - Database, kind - the kind
    #        looked for, what - "dark"|"bias"|"flat", the rest - what the
    #        light asks for
    # @return: None. Adds ONE note naming the closest master that was left
    #          out and the criterion it failed, or nothing when the library
    #          holds none of this kind (the warning already says that).
    ref, bad = closest_rejected(db, kind, camera, gain, temp_c, exptime_s,
                                filter, tol_c)
    if ref is None or not bad:
        return
    # The FIRST failed criterion is the one to name: camera, gain, exposure,
    # filter, temperature, in the order _rejections reports them.
    name, have, want = bad[0]
    _note(recipe, what, name, master=ref.path, value=have, wanted=want,
          tol=tol_c)


def _flat_age_note(recipe, flat, meta):
    # @args: recipe - the Recipe, flat - the chosen flat, meta - the light's
    # @return: None. A flat from weeks ago is USED (it is better than none)
    #          but it is SAID: the train's dust moves between nights, and a
    #          mote that was there in August may not be there in October.
    light = parse_date_obs(meta.get("date_obs"))
    taken = parse_date_obs(master_date_obs(flat))
    if light is None or taken is None:
        return
    days = (light - taken).total_seconds() / 86400.0
    if days >= FLAT_AGE_WARN_DAYS:
        _note(recipe, "flat", "age", master=flat.path, days=int(round(days)))


def resolve_recipe(db, meta, tol_c=None):
    # @args: db - Database, meta - a light's metadata (from a header),
    #        tol_c - temperature tolerance
    # @return: Recipe (with warnings in plain language, never an exception)
    #
    # WHAT EACH PIECE IS MATCHED ON, and why it is not more:
    #   dark   camera + gain + temperature (+/-3 C) + exposure (exact)
    #   bias   camera + gain                    (no exposure of its own, and
    #          its pattern barely moves with the sensor's temperature)
    #   flat   camera + filter                  (its SHAPE is the train's,
    #          which does not depend on the sensor's temperature; its level
    #          is normalised away, so neither the gain nor the exposure
    #          matter)
    # The temperature LEFT the flat's match in ADR-061 rev: requiring it
    # rejected the author's own flat (taken at -14.6 C while the lights sat
    # at -20.0 C, 5.3 C apart) and the recipe then answered "no flat for
    # this filter", blaming the one criterion that DID match. The gain had
    # left it earlier for the same reason (a normalised level).
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
        bias = find_master(db, "bias", camera, gain, None, exptime_s=None,
                           filter=None, tol_c=tol_c)
        if bias is not None:
            recipe.offset, recipe.offset_kind = bias, "bias"
            recipe.warnings.append(
                "no dark at this exposure: the bias was subtracted, so the "
                "thermal current stays in the frame")
            _note_missing(recipe, db, "dark", "dark", camera, gain, temp,
                          exptime, None, tol_c)
        else:
            recipe.warnings.append(
                "no dark or bias in the library: the pedestal and the "
                "thermal current stay in the frame")
            _note_missing(recipe, db, "dark", "dark", camera, gain, temp,
                          exptime, None, tol_c)
            _note_missing(recipe, db, "bias", "bias", camera, gain, None,
                          None, None, tol_c)

    # Flat: same filter (that is its whole point). Its exposure is not the
    # light's, so exposure is not part of the match, and NEITHER IS THE GAIN
    # (a flat is NORMALISED before it is applied, so the gain only scales
    # its whole level, never its shape: requiring it was rejecting real
    # flats) NOR THE TEMPERATURE (its shape is the train's). The dark DOES
    # need the gain and the temperature: there the level IS the signal.
    flat = find_master(db, "flat", camera, None, None, exptime_s=None,
                       filter=filt, tol_c=tol_c)
    if flat is not None:
        recipe.flat = flat
        # The flat needs its own offset: a dark at the FLAT's own exposure
        # (the same pool of darks: a "dark of the flats" is a dark, and the
        # exposure tells them apart), or the bias when the flat is short.
        # Without it the division amplifies the pedestal where the flat is
        # dark. The temperature IS kept here: what this removes is the
        # flat's own dark current, and that one does depend on it.
        recipe.flat_offset = find_master(
            db, "dark", camera, gain, temp, flat.exptime_s,
            filter=None, tol_c=tol_c) or find_master(
            db, "bias", camera, gain, None, None, filter=None, tol_c=tol_c)
        _flat_age_note(recipe, flat, meta)
    else:
        recipe.warnings.append(
            "no flat for this filter: the flat residual is not corrected "
            "(it matters for the magnitude, little for the centroid)")
        _note_missing(recipe, db, "flat", "flat", camera, None, None, None,
                      filt, tol_c)
    return recipe


# ------------------------------------------------------------- the engine

@dataclass
class LoadedMasters:
    # The master arrays, ready to apply (float32).
    offset: np.ndarray | None = None
    flat: np.ndarray | None = None        # already offset-free and normalised
    flat_norm: float | None = None


class MasterCache:
    # The loaded master arrays of a RUN, read once. The calibrating loader is
    # asked for every frame of a visit, and the stacking reads each frame
    # several times (the base stack, every observation, the star stack, the
    # comp windows): without this the dark and the WHOLE flat were re-read
    # from disk and the flat re-median-ed on every single read. Measured on
    # 2048^2 masters: a calibrated read is 27 ms without the cache and 2.6 ms
    # with it, so a 539-frame visit was paying ~13 s of pure I/O and medians
    # per pass (2026-10-15). The lock makes the first read of a master happen
    # ONCE even when sixteen threads ask for it at the same time; after that
    # it is a dict hit.
    def __init__(self):
        import threading
        # REENTRANT on purpose: building the flat asks the cache for the
        # flat's own offset (a dark), which is the same lock one level down.
        # A plain Lock deadlocked there.
        self._lock = threading.RLock()
        self._items = {}

    def get(self, key, build):
        # @args: key - the master's identity (kind + path(s)), build -
        #        callable that reads it from disk
        # @return: the cached value
        with self._lock:
            if key in self._items:
                return self._items[key]
            value = build()
            self._items[key] = value
            return value


def _normalized_flat(recipe, loader, read):
    # @args: recipe - Recipe with .flat (and maybe .flat_offset), loader -
    #        callable(path, box) -> array, read - the cache-aware reader from
    #        load_masters (so the flat's own offset shares the cache with the
    #        light's)
    # @return: (normalised full flat, its full median) or (None, None) when
    #          the median is not positive (the flat is not applied)
    # The flat is read WHOLE and normalised by its full median, which is why
    # the result can be cached as one piece and only sliced per box.
    flat_full = _as_float32(loader(recipe.flat.path, None))
    if recipe.flat_offset is not None:
        flat_off = read(("offset", recipe.flat_offset.path),
                        lambda: _as_float32(
                            loader(recipe.flat_offset.path, None)))
        if flat_off.shape == flat_full.shape:
            flat_full = flat_full - flat_off
        else:
            logger.warning("flat offset %s does not match the flat; "
                           "ignored", recipe.flat_offset.path)
    norm = float(np.median(flat_full))
    if norm > 0:
        return flat_full / norm, norm
    logger.warning("flat %s has a non-positive median; not applied",
                   recipe.flat.path)
    return None, None


def load_masters(recipe, loader=None, box=None, cache=None):
    # @args: recipe - Recipe, loader - callable(path, box) -> array
    #        (defaults to read_image), box - optional (x0,y0,x1,y1) region,
    #        cache - optional MasterCache shared across the frames of a run
    # @return: LoadedMasters
    # The flat is always read WHOLE, even when only a region is wanted,
    # because its normalisation has to be the full-frame median: cropping
    # first would normalise by whatever the crop happens to contain and
    # change the frame's flux level from crop to crop. The box is applied
    # AFTER, on the (cached) full array, so the same master serves every
    # region without being read again.
    loader = loader or read_image

    def read(key, build):
        # one master, once per run when a cache is given
        return cache.get(key, build) if cache is not None else build()

    out = LoadedMasters()
    if recipe.offset is not None:
        full = read(("offset", recipe.offset.path),
                    lambda: _as_float32(loader(recipe.offset.path, None)))
        out.offset = _crop(full, box)
    if recipe.flat is not None:
        flat_key = ("flat", recipe.flat.path,
                    recipe.flat_offset.path if recipe.flat_offset else None)
        flat_full, norm = read(flat_key,
                               lambda: _normalized_flat(recipe, loader, read))
        if flat_full is not None:
            out.flat = _crop(flat_full, box)
            out.flat_norm = norm
    return out


def _crop(full, box):
    # @args: full - a whole master array, box - (x0,y0,x1,y1) or None
    # @return: the boxed view (a view, not a copy)
    if box is None:
        return full
    x0, y0, x1, y1 = box
    return full[y0:y1, x0:x1]


def _as_float32(data):
    # @args: data - array (any float/int dtype), or the (array, header)
    #        pair read_image returns: a loader is allowed to be either
    # @return: the same data as float32 (half the memory, plenty of
    #          precision: 7 significant digits beat photon noise)
    if isinstance(data, tuple):
        data = data[0]
    return np.asarray(data, dtype=np.float32)


# ------------------------------------------- the vignetting model (P5 rev)
#
# ADR-069 built a full-resolution "synthetic flat" out of the frames: a low
# percentile per pixel over the whole visit, a star mask, a fill and a
# hot-pixel restoration. Measured against the author's own real master flat
# (150 flats of 2025-03-31, `tools/bench/bench_flat.py`) it reached 4.16 %
# agreement on the train's SHAPE, and everything that machinery bought over
# a plain smooth surface was the DUST: 2.38 % = 0.026 mag. The vignetting is
# what matters (0.087 mag of systematic without any correction at all) and
# it is SMOOTH, so the model went back to what it should always have been:
# sample the sky on a grid and fit a surface to the samples, throwing away
# the tiles a star or a dust mote pushed off the trend. It lands in the same
# 4-5.5 % band for a tenth of the work.
#
# Measured on that same visit (2048x2048 frames, 207 lights), against the
# real master, as the p5-p95 spread of the ratio between the two:
#
#   candidate                                       shape     time
#   the ADR-069 masked flat, full resolution        4.16 %    20 s
#   the default grid (51 px), 20 frames, degree 6   4.98 %   2.4 s
#   a 48-px grid, 20 frames, a degree-6 surface     3.93 %   2.4 s
#   a 64-px grid, 20 frames, a degree-6 surface     5.46 %   2.4 s
#
# It gives up the dust on purpose, and it is NOT a flat: it also folds in
# the sky's own shape, the honest limit of anything built from the lights
# (the same 0.04 mag the masked flat had). The library still takes a real
# master, built by the observer or by any other tool, for the observer who
# wants the dust corrected too.

# The tile side, as a fraction of the frame's short side: a 2048-px frame
# lands on 51 px. The floor keeps a small frame from ending up with a grid
# too coarse to fit anything.
VIGNETTE_TILES_PER_SIDE = 40
VIGNETTE_TILE_MIN_PX = 32
# How many frames the sky is sampled from, spread over the visit. TWENTY is
# enough: a 48-px tile holds thousands of pixels, so its median already
# carries ~0.1 % where a single pixel's noise is 7.5 %, and reading twenty
# frames instead of two hundred is what makes the model seconds. More
# changed nothing (measured: 20 and 40 frames both land on 4.2 % at 32 px).
VIGNETTE_FRAMES = 20
# The fitted surface's total degree. SIX, measured on FG18: degrees 8 and 10
# were no better (4.85 % and 4.76 % against the 4-5.5 % band of a degree 6)
# at twice the cost, with the frame's edges starting to move on their own.
VIGNETTE_ORDER = 6
# The robust fit: the tiles whose residual passes this many scaled MADs are
# dropped and the surface is fitted again. It is the WHOLE rejection, and it
# needs no mask and no dilation (measured on FG18: 6 % of the tiles at
# 64 px).
VIGNETTE_CLIP_SIGMA = 3.0
VIGNETTE_FIT_ROUNDS = 3
# Below this many surviving tiles there is nothing to fit: the answer is no
# model and a reason, never a surface held up by three points.
VIGNETTE_MIN_TILES = 30


def _vignette_terms(order):
    # @args: order - the surface's total degree
    # @return: the (i, j) exponents of its terms, i + j <= order
    return [(i, j) for i in range(order + 1) for j in range(order + 1)
            if i + j <= order]


def _tile_levels(data, tile):
    # @args: data - one frame (h, w) float32, tile - the tile side in pixels
    # @return: the (ty, tx) MEDIAN of each tile, or None when the frame is
    #          smaller than one tile
    # The MEDIAN and not the mean: a star, a cosmic ray or a plane inside a
    # tile must not move it, and a median is what a star covering less than
    # half a tile cannot touch.
    ty, tx = data.shape[0] // tile, data.shape[1] // tile
    if ty < 1 or tx < 1:
        return None
    block = data[:ty * tile, :tx * tile]
    block = block.reshape(ty, tile, tx, tile).transpose(0, 2, 1, 3)
    levels = np.median(block.reshape(ty * tx, tile * tile), axis=1)
    return levels.reshape(ty, tx)


def _fit_vignette_surface(levels, ny, nx, tile, order):
    # @args: levels - the (ty, tx) sky level per tile, ny/nx - the frame's
    #        size, tile - the tile side, order - the surface's total degree
    # @return: (model, kept, why): the surface normalised to a median of one
    #          and the number of tiles it stands on, or (None, kept, why)
    # The tiles are the SAMPLES and the surface is what they have in common:
    # the train's vignetting. The fit is ROBUST because a tile can hold a
    # star, a galaxy or a dust mote, any of which would drag a plain
    # least-squares surface with it; three passes with a scaled-MAD clip is
    # the whole rejection.
    ty, tx = levels.shape
    terms = _vignette_terms(order)
    floor = max(VIGNETTE_MIN_TILES, len(terms) + 1)
    if ty * tx < floor:
        return None, 0, (f"the frame is too small to sample the sky on a "
                         f"grid of {tile}-pixel tiles")
    ys = (np.arange(ty) + 0.5) * tile
    xs = (np.arange(tx) + 0.5) * tile
    xx, yy = np.meshgrid(xs, ys)
    xn = (xx.ravel() - nx / 2.0) / (nx / 2.0)
    yn = (yy.ravel() - ny / 2.0) / (ny / 2.0)
    design = np.empty((ty * tx, len(terms)), dtype=np.float64)
    for k, (i, j) in enumerate(terms):
        design[:, k] = (xn ** i) * (yn ** j)
    values = levels.ravel().astype(np.float64)
    weights = np.ones_like(values)
    coef = None
    kept = int(values.size)
    for _ in range(VIGNETTE_FIT_ROUNDS):
        try:
            coef, *_ = np.linalg.lstsq(design * weights[:, None],
                                        values * weights, rcond=None)
        except np.linalg.LinAlgError:
            return None, 0, "the vignetting model did not converge"
        resid = values - design @ coef
        sigma = float(outliers.scaled_mad(resid))
        if not np.isfinite(sigma) or sigma <= 0:
            break
        weights = (np.abs(resid) <= VIGNETTE_CLIP_SIGMA * sigma).astype(
            np.float64)
        kept = int(weights.sum())
    if coef is None or kept < floor:
        return None, kept, ("the sources cover almost the whole frame: there "
                            "is not enough sky left to model the vignetting")
    # The surface has a value EVERYWHERE, edges included: it is evaluated on
    # the whole frame, not only on the tiles that were kept.
    yy2, xx2 = np.mgrid[0:ny, 0:nx]
    yyn = (yy2 - ny / 2.0) / (ny / 2.0)
    xxn = (xx2 - nx / 2.0) / (nx / 2.0)
    model = np.zeros((ny, nx), dtype=np.float64)
    for c, (i, j) in zip(coef, terms):
        model += c * (xxn ** i) * (yyn ** j)
    norm = float(np.median(model))
    if not np.isfinite(model).all() or norm <= 0:
        return None, kept, "the vignetting model is not usable (no level)"
    return (model / norm).astype(np.float32), kept, None


class _OffsetSubtractor:
    # A loader that removes the offset (dark or bias) as the frames are read,
    # so the model is built from frames with the SAME pedestal as the light.
    # Without it the division mixes two different things and the model comes
    # out COMPRESSED: measured on 1 s twilight frames of FG18, the pedestal
    # is 827 ADU over a sky of 661 (56 % of the level) and the correction
    # drops to 44 % of what it should be. The tiles carry it just as the
    # old per-pixel statistic did (measured on the same visit: the best
    # pedestal that flattens the ratio against the real flat is p ~ 1.25).
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
            logger.warning("vignette model: the offset could not be resolved "
                           "for %s (%s)", path, err)
            self.missing_paths.add(path)
            return out
        if recipe.offset is None:
            self.missing_paths.add(path)
            return out
        try:
            off = _as_float32(read_image(recipe.offset.path, box))
        except Exception as err:
            logger.warning("vignette model: the offset master could not be "
                           "read (%s)", err)
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


def vignette_model(paths, tile=None, frames=None, order=None, loader=None,
                   progress=None, cancel=None, db=None, cfg=None):
    # @args: paths - the light frames of the visit, tile - the tile side in
    #        pixels (None: a fraction of the frame), frames - how many frames
    #        the sky is sampled from (None: VIGNETTE_FRAMES, spread over the
    #        visit), order - the fitted surface's total degree (None:
    #        VIGNETTE_ORDER), loader - callable(path, box) -> array,
    #        progress - callable(done, total), cancel - callable() -> True to
    #        stop, db - Database (with it the pedestal is removed from the
    #        frames first, see _OffsetSubtractor), cfg - Config
    # @return: (model float32, info dict) or (None, info) when it cannot be
    #          built
    # THE VIGNETTING, SAMPLED FROM THE SKY. The train's vignetting is smooth
    # and fixed on the frame, and the sky is the light that fills it: what a
    # grid of tiles sees, once the tiles a star or a dust mote spoiled are
    # thrown away, IS the vignetting. It replaces ADR-069's masked
    # full-resolution flat, which reached 4.26 % (0.045 mag) against the
    # author's real master for 20 s of work where this one reaches 3.93 %
    # for 3 s.
    #
    # It is not a flat and it does not pretend to be: it carries no dust
    # (2.38 % = 0.026 mag) and it folds in the sky's own shape, the honest
    # limit of anything built from the lights. A real master from the
    # library always wins, and the recipe line says which one was used.
    paths = list(paths or [])
    order = int(VIGNETTE_ORDER if order is None else order)
    info = {"n_frames": len(paths), "tile_px": None, "order": order,
            "n_tiles": None, "n_kept": None, "sampled": 0,
            "median_adu": None, "kind": "vignette_model", "note": "",
            "model_range": None, "offset": None, "seconds": None}
    if not paths:
        info["note"] = "no frames to sample the sky from"
        return None, info
    t0 = time.time()
    try:
        header = read_header(paths[0])
        ny = int(header.get("NAXIS2", 0))
        nx = int(header.get("NAXIS1", 0))
    except Exception:
        ny = nx = 0
    if ny <= 0 or nx <= 0:
        info["note"] = "the first frame does not say its size"
        return None, info
    if tile is None:
        tile = max(VIGNETTE_TILE_MIN_PX,
                   int(round(min(ny, nx) / float(VIGNETTE_TILES_PER_SIDE))))
    tile = max(8, int(tile))
    info["tile_px"] = tile
    # The frames the sky is sampled from, SPREAD over the visit: a sky that
    # changes (the twilight, a cloud coming in) must not land all in one end.
    count = VIGNETTE_FRAMES if frames is None else int(frames)
    count = max(1, min(count, len(paths)))
    idx = np.unique(np.linspace(0, len(paths) - 1, count).astype(int))
    subtractor = _OffsetSubtractor(db, cfg) if db is not None else None
    load = subtractor if subtractor is not None else (loader or read_image)
    levels = []
    for n, i in enumerate(idx, 1):
        if cancel is not None and cancel():
            info["note"] = "cancelled"
            return None, info
        path = paths[int(i)]
        try:
            data = _as_float32(load(path, None))
        except Exception as err:
            logger.warning("vignette model: %s could not be read (%s)",
                           path, err)
            continue
        if data.shape != (ny, nx):
            logger.warning("vignette model: %s is %s and the first frame is "
                           "%s; skipped", path, data.shape, (ny, nx))
            continue
        level = _tile_levels(data, tile)
        if level is None:
            info["note"] = "the frame is smaller than one tile"
            return None, info
        levels.append(level)
        info["sampled"] = n
        if progress is not None:
            progress(n, len(idx))
    if not levels:
        info["note"] = "no frame could be read"
        return None, info
    if subtractor is not None:
        info["offset"] = subtractor.summary()
    # Across the frames: the MEDIAN per tile, which one frame with a
    # satellite, a cloud or a bad row cannot move.
    stacked = np.median(np.stack(levels, axis=0), axis=0)
    info["n_tiles"] = int(stacked.size)
    model, kept, why = _fit_vignette_surface(stacked, ny, nx, tile, order)
    info["n_kept"] = int(kept)
    if model is None:
        info["note"] = why
        return None, info
    info["median_adu"] = float(np.median(stacked))
    info["model_range"] = (float(model.min()), float(model.max()))
    info["seconds"] = time.time() - t0
    return model, info


# The card a calibrated copy carries so it is never calibrated twice, and
# the note both calibrators add when they honour it (one string, so the
# Calibration tab and the run say the same thing).
CALIBRATED_CARD = "NSCALIB"
_ALREADY_NOTE = ("already calibrated by NightScribe: "
                 "the recipe was not applied again")


def is_calibrated(header):
    # @args: header - a FITS header dict
    # @return: True when NightScribe already calibrated this frame
    # The exported calibrated copies KEEP the cards the recipe keys on
    # (camera, gain, exposure, temperature, filter): only the structural ones
    # are dropped (see export_calibrated). So feeding one of them back into
    # the library would subtract the dark and divide the flat a SECOND time,
    # and a double-calibrated frame has no tell in the image. The card is the
    # frame saying "I am already clean", and both calibrators read it.
    value = header.get(CALIBRATED_CARD)
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().upper() in ("T", "TRUE", "YES", "1")
    return bool(value)


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
    #        vignette_model - a model built from the frames themselves (see
    #        vignette_model), used when the library has no flat for the
    #        filter

    def __init__(self, db, cfg=None, vignette_model=None):
        self._db = db
        self._cfg = cfg
        self._vignette_model = vignette_model
        self._tol = (cfg.get("calib_temp_tol_c", _DEFAULT_TEMP_TOL_C)
                     if cfg is not None else _DEFAULT_TEMP_TOL_C)
        self._cache = {}
        # The masters themselves, read once per run: the recipe cache above
        # only remembers WHICH dark and flat apply, and without this the
        # pixels were re-read (and the flat re-median-ed) on every frame.
        self._masters = MasterCache()
        self.reports = []          # one (path, report) per frame read

    def __call__(self, path, box=None):
        # @args: path - the frame, box - optional (x0, y0, x1, y1) region
        # @return: the calibrated float32 array, in the shape the caller
        #          asked for. The header is NOT returned: the callers that
        #          need it read it themselves, and calibrating does not
        #          change it.
        data, header = read_image(path, box)
        if is_calibrated(header):
            # The frame already carries NightScribe's calibration: applying
            # the recipe again would subtract the dark twice. It is said in
            # the report, never done in silence.
            self.reports.append((path, CalibrationReport(
                already=True, ok=True, warnings=[_ALREADY_NOTE])))
            return _as_float32(data)
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
                                vignette_model=self._vignette_model,
                                master_cache=self._masters)
        self.reports.append((path, report))
        return out

    def summary(self):
        # @return: what was applied, for the run's note: the masters' names
        #          and the warnings, deduplicated. The observer has to know
        #          what the magnitude was measured with.
        offsets, flats, warnings = set(), set(), []
        already = 0
        for _path, report in self.reports:
            if getattr(report, "already", False):
                already += 1
            if report.offset_path:
                offsets.add(Path(report.offset_path).name
                            if report.offset_path != "vignette-model"
                            else report.offset_path)
            if report.flat_path:
                flats.add(Path(report.flat_path).name
                          if report.flat_path != "vignette-model"
                          else report.flat_path)
            for note in report.warnings:
                if note not in warnings:
                    warnings.append(note)
        return {"n": len(self.reports), "already": already,
                "offsets": sorted(offsets), "flats": sorted(flats),
                "warnings": warnings[:4]}


def calibrate(data, recipe, loader=None, box=None, vignette_model=None,
              master_cache=None):
    # @args: data - the light (raw, 2D), recipe - Recipe,
    #        loader - callable(path, box) -> array, box - optional region,
    #        vignette_model - a normalised model built from the frames
    #        themselves (see vignette_model), used ONLY when the library has
    #        no flat for this filter, master_cache - optional MasterCache so
    #        the masters are read once per run and not once per frame
    # @return: (calibrated float32 array, CalibrationReport)
    # The order is offset first, flat second: dividing before removing the
    # pedestal would amplify it in the flat's dark corners.
    masters = load_masters(recipe, loader=loader, box=box, cache=master_cache)
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
    # response, dust included, while the vignetting model is smooth and
    # folds in the sky's own shape. The model is the fallback, and it says
    # so in the report.
    flat = masters.flat
    flat_norm = masters.flat_norm
    flat_path = recipe.flat.path if recipe.flat is not None else None
    if flat is None and vignette_model is not None:
        vm = _as_float32(vignette_model)
        if box is not None and vm.shape != out.shape:
            x0, y0, x1, y1 = box
            vm = vm[y0:y1, x0:x1]
        if vm.shape == out.shape:
            flat = vm
            flat_norm = float(np.median(vm)) or 1.0
            flat_path = "vignette-model"
    if flat is not None and flat.shape == out.shape:
        out = out / flat
        report.flat_path = flat_path
        report.flat_norm = flat_norm
        if flat_path == "vignette-model":
            # The recipe warned "no flat for this filter" and it was right:
            # there was none. The model is what stands in for it, so
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
                    progress=None, cancel=None, vignette_model=None):
    # @args: paths - light FITS paths, db - Database, cfg - Config (for the
    #        temperature tolerance), master_loader - callable(path, box) ->
    #        array for the MASTERS (the light is always read from disk with
    #        read_image, which also gives its header), box - optional region,
    #        progress - callable(done, total, label), cancel - callable()
    #        -> True to stop, vignette_model - a model built from the frames
    #        themselves (see vignette_model) for the filters the library has
    #        no flat for
    # @return: list[(path, data, header, report)]
    # The light's header decides the recipe, so this is the entry point the
    # GUI and the stacking engine will call frame by frame.
    tol = None
    if cfg is not None:
        tol = cfg.get("calib_temp_tol_c", _DEFAULT_TEMP_TOL_C)
    out = []
    total = len(paths)
    # One master cache for the whole folder: exporting a visit must not
    # re-read (and re-median) the same dark and flat for every frame either.
    master_cache = MasterCache()
    for index, path in enumerate(paths, 1):
        if cancel is not None and cancel():
            break
        data, header = read_image(path, box)
        if is_calibrated(header):
            # Already calibrated by NightScribe (see is_calibrated): the
            # recipe is skipped and the report says so. The Calibration tab
            # renders that warning instead of a second subtraction nobody
            # would see in the image.
            out.append((path, _as_float32(data), header, CalibrationReport(
                already=True, ok=True, warnings=[_ALREADY_NOTE])))
            if progress is not None:
                progress(index, total, path)
            continue
        meta = meta_from_header(header)
        recipe = resolve_recipe(db, meta, tol_c=tol)
        data_cal, report = calibrate(data, recipe, loader=master_loader,
                                     box=box, vignette_model=vignette_model,
                                     master_cache=master_cache)
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
    # The marker that keeps the copy from being calibrated twice: the
    # camera/gain/exposure/filter cards are still there (they are what makes
    # a master valid), so without this card a run over the copies would
    # subtract the dark and divide the flat again (see is_calibrated).
    hdu.header[CALIBRATED_CARD] = True
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


def export_vignette_model(model, out_path, info=None, header=None):
    # @args: model - the normalised model (float32), out_path - where to
    #        write, info - the vignette_model info dict (its figures go into
    #        the header), header - an optional header to carry over (the
    #        first frame's)
    # @return: the path written
    # THE MODEL IS A PRODUCT OF THE VISIT, and it is written so it can be
    # LOOKED AT: a smooth surface is easy to judge by eye (it must carry no
    # star and no mote), and a figure in a note is not the same thing. It is
    # also what makes it auditable, and what lets it be taken to another
    # tool to be compared or refined.
    #
    # The cards are short, because a FITS keyword is 8 characters, and each
    # one carries a figure the model was built with.
    from astropy.io import fits
    hdu = fits.PrimaryHDU(np.asarray(model, dtype=np.float32))
    for key in ("INSTRUME", "TELESCOP", "FILTER", "GAIN", "EXPTIME",
                "CCD-TEMP", "DATE-OBS", "OBJECT", "SITELAT", "SITELONG"):
        if header and key in header:
            try:
                hdu.header[key] = header[key]
            except (ValueError, TypeError):
                continue
    # IMAGETYP is FLAT on purpose: the file IS a flat to divide by, and it
    # can be indexed in the library like any other one (classify_master
    # reads this card).
    hdu.header["IMAGETYP"] = "FLAT"
    hdu.header["HISTORY"] = "NightScribe vignetting model (ADR-061 rev)"

    def _round(value):
        # @return: the figure rounded for a FITS card, or None when there is
        #          nothing to say (a missing figure is not a zero)
        return None if value is None else round(float(value), 3)

    if info:
        for key, value in (("NS_VIGN", info.get("kind")),
                           ("NS_NFRA", info.get("n_frames")),
                           ("NS_TILE", info.get("tile_px")),
                           ("NS_ORDER", info.get("order")),
                           ("NS_TILES", info.get("n_tiles")),
                           ("NS_KEPT", info.get("n_kept")),
                           ("NS_MED", _round(info.get("median_adu")))):
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
                                     "the model and compresses its shape")
        if info.get("note"):
            hdu.header["HISTORY"] = "note: " + str(info["note"])
    hdu.writeto(str(out_path), overwrite=True)
    return str(out_path)
