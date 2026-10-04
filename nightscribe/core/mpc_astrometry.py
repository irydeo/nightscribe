############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - MPC astrometry report generators module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Generate MPC 80-column and ADES PSV reports from measured points.

The two official formats are emitted from the same measured observations, so
the report can never disagree with what was measured. Both are validated by
``core.mpc_report.validate`` before they leave the module: whatever we produce
must pass the same judge the user's pasted measurements pass (ADR-022, D13).

A *point* is one observation (one contiguous group of frames, D22). It is a
plain dict or any object with attributes, using these names (the DB columns of
``astrometry_points``):

    mjd         - T_mid of the group, UTC Modified Julian Date (D13/D23)
    ra_deg      - right ascension, J2000 degrees (alias: ``ra``)
    dec_deg     - declination, J2000 degrees (alias: ``dec``)
    rms_ra      - RA uncertainty in arcsec (0 = unknown)
    rms_dec     - Dec uncertainty in arcsec (0 = unknown)
    mag         - calibrated magnitude, or None when it cannot be measured
    band        - filter/band name (translated to an MPC code)
    snr         - signal-to-noise of the detection
    n_frames    - frames averaged into this observation
    group_index - which observation of the sequence (0-based)

``rms_ra``/``rms_dec`` are arcsec on the sky; the RA one is already divided by
cos(dec) by the phase-4 error budget, so it can go straight into ADES.
"""

import logging
import math
import re

from . import mpc_report

logger = logging.getLogger(__name__)

# One Julian Date is one MJD plus this offset (MJD = JD - 2400000.5).
_MJD_JD_OFFSET = 2400000.5

# Century letters of the MPC packed designations: I=1800, J=1900, K=2000...
_CENTURY = {18: "I", 19: "J", 20: "K", 21: "L"}

# Comet designations: "C/2023 A3", "P/2010 A2", "1P", "73P-B".
_COMET_RE = re.compile(r"^\s*(\d+)?\s*([CPDXAcpdxa])\s*/", re.IGNORECASE)
_COMET_NUMBERED_RE = re.compile(r"^\s*(\d+)\s*([PDpd])\s*(?:-([A-Za-z]))?\s*$")

# Filter name -> MPC band code. Case matters for the single letters: the
# app's filters are Johnson-Cousins (V, B, R, I) in uppercase, while the
# lowercase letters are the SDSS filters (g, r, i, z). A primed filter
# ("r'") is SDSS, so the prime is kept as a 'p' marker before the other
# separators are stripped. An unknown filter NEVER gets an invented code: it
# falls to "C" (clear / unfiltered) with a warning, which is the honest
# answer when the band is unknown.
_BAND_EXACT = {
    "V": "V", "v": "V",
    "B": "B", "b": "B",
    "R": "R",
    "I": "I",
    "U": "U", "u": "U",
    "C": "C", "c": "C",
    "g": "g", "G": "g",
    "r": "r",
    "i": "i",
    "z": "z", "Z": "z",
    "gp": "g", "Gp": "g", "rp": "r", "Rp": "r",
    "ip": "i", "Ip": "i", "zp": "z", "Zp": "z",
}
_BAND_MAP = {
    "cv": "V", "rc": "R", "cr": "R", "bc": "B", "ic": "I", "uc": "U",
    "clear": "C", "unfiltered": "C", "open": "C", "none": "C",
    "lum": "C", "luminance": "C", "white": "C",
    "sg": "g", "sdssg": "g", "gprim": "g", "gprime": "g",
    "sr": "r", "sdssr": "r", "rprim": "r", "rprime": "r",
    "si": "i", "sdssi": "i", "iprim": "i", "iprime": "i",
    "sz": "z", "sdssz": "z", "zprim": "z", "zprime": "z",
}

# ADES PSV columns, in order. The uncertainty and magnitude columns may be
# empty: ADES makes them optional, and an empty cell is the honest way to say
# "not measured" instead of writing a zero that looks like a measurement.
_ADES_FIELDS = ("objid", "mode", "stn", "obsTime", "ra", "dec",
                "rmsRA", "rmsDec", "mag", "band", "astCat", "ref", "subFmt")


def _point_get(point, key, default=None):
    # @args: point - dict or object, key - field name, default - fallback
    # @return: the field value
    # Points come from a dict (tests, DB rows) or from an AstrometryPoint
    # dataclass, so both shapes are accepted; a dict is checked first because
    # that is the cheap case.
    if isinstance(point, dict):
        return point.get(key, default)
    return getattr(point, key, default)


def _ra_dec(point):
    # @args: point - a measured point
    # @return: (ra_deg, dec_deg)
    # The app's AstrometryPoint calls them ra/dec; the task's contract calls
    # them ra_deg/dec_deg. Accept both so no caller has to rename anything.
    ra = _point_get(point, "ra_deg")
    if ra is None:
        ra = _point_get(point, "ra")
    dec = _point_get(point, "dec_deg")
    if dec is None:
        dec = _point_get(point, "dec")
    return float(ra), float(dec)


def _jd_to_ymdf(jd):
    # @args: jd - Julian Date (UTC)
    # @return: (year, month, day_float) in the Gregorian calendar
    # Fliegel-Van Flandern conversion: no astropy needed, and the fractional
    # day keeps the microseconds that T_mid carries. The 2299161 guard is the
    # Gregorian reform; astrometry never predates it, but the branch is cheap.
    jd = float(jd)
    z = jd + 0.5
    day = math.floor(z)
    frac = z - day
    if day < 2299161:
        a = day
    else:
        alpha = math.floor((day - 1867216.25) / 36524.25)
        a = day + 1 + alpha - math.floor(alpha / 4)
    b = a + 1524
    c = math.floor((b - 122.1) / 365.25)
    d = math.floor(365.25 * c)
    e = math.floor((b - d) / 30.6001)
    day_f = b - d - math.floor(30.6001 * e) + frac
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715
    return int(year), int(month), float(day_f)


def format_time_mpc80(jd_utc):
    # @args: jd_utc - Julian Date (UTC), normally the group's T_mid
    # @return: "YYYY MM DD.dddddd"
    year, month, day_f = _jd_to_ymdf(jd_utc)
    # 6 decimals of a day is ~0.086 s: enough to keep T_mid faithful without
    # pretending to a precision the exposure does not have.
    return f"{year:04d} {month:02d} {day_f:09.6f}"


def format_ra_mpc80(ra_deg):
    # @args: ra_deg - right ascension in degrees
    # @return: "HH MM SS.sss"
    # Work in total seconds and round once: decomposing the degrees directly
    # accumulates error and can yield the impossible "60.000" seconds.
    total = round((float(ra_deg) % 360.0) * 240.0, 3)
    hh = int(total // 3600.0)
    rem = total - hh * 3600.0
    mm = int(rem // 60.0)
    ss = rem - mm * 60.0
    return f"{hh:02d} {mm:02d} {ss:06.3f}"


def format_dec_mpc80(dec_deg):
    # @args: dec_deg - declination in degrees
    # @return: "sDD MM SS.ss" with an explicit sign
    # The sign is always written: the MPC format needs it even for +00.
    sign = "-" if float(dec_deg) < 0 else "+"
    total = round(abs(float(dec_deg)) * 3600.0, 2)
    dd = int(total // 3600.0)
    rem = total - dd * 3600.0
    mm = int(rem // 60.0)
    ss = rem - mm * 60.0
    return f"{sign}{dd:02d} {mm:02d} {ss:05.2f}"


def band_code(filter_name):
    # @args: filter_name - the filter as written by the observer/camera
    # @return: the MPC band code, or "C" when the filter is unknown
    if filter_name is None:
        return "C"
    # A prime means the SDSS filter, so "r'" must stay distinct from "R":
    # turn the apostrophe into a 'p' before stripping the other separators.
    key = str(filter_name).strip().replace("'", "p").replace("\u2032", "p")
    key = re.sub(r"[\s\-_]+", "", key)
    # Single letters keep their case (R = Cousins, r = SDSS); longer names
    # are matched case-insensitively.
    code = _BAND_EXACT.get(key)
    if code is None:
        code = _BAND_MAP.get(key.lower())
    if code is None:
        logger.warning(
            "Unknown photometric filter %r: reporting band 'C' (clear). "
            "Check the filter name if the band matters.", filter_name)
        return "C"
    return code


def _base62_cycle(first):
    # @args: first - the tens part of a cycle number (10..61)
    # @return: the MPC packed letter (A..Z, a..z)
    if first <= 35:
        return chr(ord("A") + first - 10)
    return chr(ord("a") + first - 36)


def _pack_cycle(num):
    # @args: num - the provisional cycle number
    # @return: the 2-char packed cycle, or None when it does not fit
    if num < 100:
        return f"{num:02d}"
    first = num // 10
    if first < 10 or first > 61:
        return None
    return _base62_cycle(first) + str(num % 10)


def _pack_number(n):
    # @args: n - a minor planet number
    # @return: the 5-char packed number, or None when out of range
    if 0 <= n < 100000:
        return f"{n:05d}"
    first = n // 10000
    if first < 10 or first > 61:
        return None
    return _base62_cycle(first) + f"{n % 10000:04d}"


def _pack_provisional(raw):
    # @args: raw - a provisional designation, "2021 EQ3" or "2021EQ3"
    # @return: the 7-char packed form ("K21E03Q"), or None
    m = re.match(r"^(\d{4})\s*([A-Z])([A-Z])\s*(\d*)$", raw.upper())
    if not m:
        return None
    century = _CENTURY.get(int(m.group(1)) // 100)
    cycle = _pack_cycle(int(m.group(4) or 0))
    if century is None or cycle is None:
        return None
    return (f"{century}{int(m.group(1)) % 100:02d}"
            f"{m.group(2)}{cycle}{m.group(3)}")


def _pack_comet(raw):
    # @args: raw - a comet designation, "C/2023 A3" or "73P-B"
    # @return: (packed, note)
    m = _COMET_NUMBERED_RE.match(raw)
    if m:
        # Numbered periodic comet: "1P" -> "0001P", "73P-B" -> "0073Pb".
        n = int(m.group(1))
        frag = m.group(3).lower() if m.group(3) else ""
        return f"{n:04d}{m.group(2).upper()}{frag}", ""
    m = re.match(r"^\s*([CPDXA])\s*/\s*(\d{4})\s*([A-Z])\s*(\d+)\s*"
                 r"(?:-([A-Za-z]))?\s*$", raw.upper())
    if m:
        century = _CENTURY.get(int(m.group(2)) // 100)
        cycle = _pack_cycle(int(m.group(4)))
        if century is not None and cycle is not None:
            frag = m.group(5).lower() if m.group(5) else "0"
            packed = (f"{m.group(1)}{century}{int(m.group(2)) % 100:02d}"
                      f"{m.group(3)}{cycle}{frag}")
            return packed, ""
    return None, ""


def pack_designation(name, kind=None):
    # @args: name - the object designation, kind - "numbered" | "provisional"
    #        | "comet" | "pccp" (None lets the name decide)
    # @return: (packed, note); note is "" when nothing needs confirming
    # This extends mpc_report._pack_desig rather than replacing it: the old
    # best-effort is tried first, and only when it cannot answer do we apply
    # the full packing. For PCCP (a candidate without a confirmed orbit) the
    # packing is deliberately best-effort: the code is emitted as-is and the
    # note asks the user to confirm it, because a wrong tracklet tag can lose
    # the object (D15).
    raw = (name or "").strip()
    if not raw:
        return "", "Empty designation: an MPC report cannot be generated."
    kind_l = (kind or "").strip().lower()
    if kind_l in ("pccp", "neocp"):
        packed = re.sub(r"[^A-Za-z0-9]", "", raw).upper()[:5]
        return packed, (
            f"PCCP '{raw}' is a candidate without a confirmed orbit: the "
            f"designation is emitted as-is as '{packed}'. Confirm it on the "
            "NEOCP/PCCP page before submitting (D15).")
    if raw.isdigit():
        packed = _pack_number(int(raw))
        if packed:
            return packed, ""
    elif (kind_l == "comet" or _COMET_RE.match(raw)
          or _COMET_NUMBERED_RE.match(raw)):
        packed, note = _pack_comet(raw)
        if packed:
            if len(packed) > 5:
                # The app's designation field is 5 chars; the real comet
                # packed form is 8. Keep the head and say it was cut.
                return packed[:5], (
                    f"Comet '{raw}' packed as '{packed}'; the app's "
                    f"designation field keeps '{packed[:5]}'. Confirm the "
                    "full packed form before submitting.")
            return packed, note
    # mpc_report's own packer first: reusing it keeps one source of truth
    # for the cases it does handle.
    packed = mpc_report._pack_desig(raw)
    if packed:
        return packed, ""
    packed = _pack_provisional(raw)
    if packed:
        if len(packed) > 5:
            return packed[:5], (
                f"Provisional '{raw}' packed as '{packed}'; the app's "
                f"designation field keeps '{packed[:5]}'. Confirm the full "
                "packed form before submitting.")
        return packed, ""
    fallback = re.sub(r"[^A-Za-z0-9]", "", raw).upper()[:5]
    return fallback, (
        f"Could not pack designation '{raw}' with certainty; '{fallback}' is "
        "a placeholder. Confirm the packed form before submitting.")


def _cfg_get(cfg, key, default):
    # @args: cfg - Config object, dict or None, key - setting, default
    # @return: the setting value
    if cfg is None:
        return default
    if hasattr(cfg, "get"):
        return cfg.get(key, default)
    if isinstance(cfg, dict):
        return cfg.get(key, default)
    return default


def _iso_time(mjd):
    # @args: mjd - UTC Modified Julian Date (T_mid)
    # @return: "YYYY-MM-DDTHH:MM:SS.ssssss" ISO 8601, UTC, no trailing Z
    year, month, day_f = _jd_to_ymdf(float(mjd) + _MJD_JD_OFFSET)
    day = int(math.floor(day_f))
    frac = day_f - day
    # Microseconds first, then decompose: rounding the seconds directly can
    # produce "60.000000", which is not a valid time.
    total_us = int(round(frac * 86400.0 * 1_000_000))
    hh, rem = divmod(total_us, 3600 * 1_000_000)
    mm, ss_us = divmod(rem, 60 * 1_000_000)
    if hh >= 24:                       # rounding at the day boundary
        day += 1
        hh -= 24
    return (f"{year:04d}-{month:02d}-{day:02d}T"
            f"{hh:02d}:{mm:02d}:{ss_us / 1_000_000:09.6f}")


def to_mpc80(points, obs_code, designation, cfg=None):
    # @args: points - measured observations, obs_code - MPC station code,
    #        designation - the object, cfg - Config (unused here, kept for
    #        a uniform signature)
    # @return: the 80-column block, one line per observation
    # Field positions are the ones core.mpc_report documents (_DESIG, _DATE,
    # _RA, _DEC, _MAG, _BAND, _STATION); a missing magnitude leaves the field
    # blank instead of writing a zero that would read as a measurement.
    packed, _note = pack_designation(designation, None)
    lines = []
    for point in points:
        ra, dec = _ra_dec(point)
        mjd = _point_get(point, "mjd")
        date = format_time_mpc80(float(mjd) + _MJD_JD_OFFSET)
        ra_s = format_ra_mpc80(ra)
        dec_s = format_dec_mpc80(dec)
        mag = _point_get(point, "mag")
        band = _point_get(point, "band")
        if mag is None:
            mag_s = " " * 5
            band_s = "  "
        else:
            mag_s = f"{float(mag):5.2f}"
            band_s = f"{band_code(band):<2}"
        line = (
            f"{packed[:5]:<5}"          # 0-4   packed designation
            f"{'':<10}"                 # 5-14  notes (blank)
            f"{date:<17}"               # 15-31 packed date (T_mid)
            f"{ra_s:<12}"               # 32-43 RA
            f"{dec_s:<12}"              # 44-55 Dec
            f"{'':<9}"                  # 56-64 blank
            f"{mag_s:<5}"               # 65-69 magnitude
            f"{band_s:<2}"              # 70-71 band
            f"{'':<5}"                  # 72-76 blank
            f"{str(obs_code).upper():<3}"  # 77-79 station
        )
        lines.append(line)
    return "\n".join(lines)


def to_ades_psv(points, obs_code, designation, cfg=None):
    # @args: points - measured observations, obs_code - MPC station code,
    #        designation - the object id, cfg - Config (astCat comes from it)
    # @return: the ADES PSV block, header + one row per observation
    # ADES carries what 80 columns cannot: the rmsRA/rmsDec and the
    # astrometric catalogue. Empty cells mark what was not measured; the
    # format itself makes those columns optional, so honesty costs nothing.
    astcat = _cfg_get(cfg, "astrometry_astcat", "Gaia2")
    lines = ["|".join(_ADES_FIELDS)]
    for point in points:
        ra, dec = _ra_dec(point)
        mjd = _point_get(point, "mjd")
        rms_ra = _point_get(point, "rms_ra") or 0.0
        rms_dec = _point_get(point, "rms_dec") or 0.0
        mag = _point_get(point, "mag")
        band = _point_get(point, "band")
        # The magnitude and its band travel together: a band without a
        # magnitude says nothing, and ADES rows stay readable either way.
        mag_s = f"{float(mag):.2f}" if mag is not None else ""
        band_s = band_code(band) if mag is not None else ""
        row = [
            str(designation),
            "CCD",
            str(obs_code).upper(),
            _iso_time(mjd),
            f"{ra:.6f}",
            f"{dec:.6f}",
            f"{float(rms_ra):.3f}",
            f"{float(rms_dec):.3f}",
            mag_s,
            band_s,
            str(astcat),
            "",
            "PSV",
        ]
        lines.append("|".join(row))
    return "\n".join(lines)


def submittable(points, cfg=None):
    # @args: points - measured observations, cfg - Config (submit SNR gate)
    # @return: (kept, dropped, notes): the observations that clear the MPC
    #          floor, the ones that do not, and why in plain language
    # The MPC recommends SNR >= 20 per observation and forbids marginal or
    # noisy detections, so a low-SNR point is dropped with a reason instead
    # of being emitted silently (D26). A point with no SNR cannot prove it
    # clears the floor, so it is dropped too.
    threshold = float(_cfg_get(cfg, "astrometry_submit_snr", 20.0))
    kept, dropped, notes = [], [], []
    for point in points:
        snr = _point_get(point, "snr")
        group = _point_get(point, "group_index", "?")
        if snr is None:
            dropped.append(point)
            notes.append(
                f"Group {group}: no SNR was measured, so it cannot be shown "
                f"to clear the MPC floor of SNR {threshold:.0f}; left out.")
            continue
        snr = float(snr)
        if snr < threshold:
            dropped.append(point)
            notes.append(
                f"Group {group}: SNR {snr:.1f} is below the MPC submission "
                f"floor of {threshold:.0f}. A marginal detection risks a "
                "false tracklet, so it is left out.")
        else:
            kept.append(point)
    return kept, dropped, notes


def _normalize_format(fmt):
    # @args: fmt - a format name, case-insensitive
    # @return: "mpc80" | "ades" | None
    key = (fmt or "").strip().lower()
    if key in ("mpc80", "80col", "80", "mpc"):
        return "mpc80"
    if key in ("ades", "psv", "ades_psv", "adespsv"):
        return "ades"
    return None


def validate_generated(text, obs_code, expected_obj):
    # @args: text - the generated block, obs_code - station, expected_obj -
    #        the object the report claims to be about
    # @return: mpc_report.validate's dict
    # Our own output goes through the same judge as the user's pasted text:
    # if the generator cannot pass its own validator, the bug is ours.
    return mpc_report.validate(text, obs_code, expected_obj)


def generate(points, fmt, obs_code, designation, cfg=None):
    # @args: points - measured observations, fmt - "mpc80" | "ades",
    #        obs_code - station, designation - the object, cfg - Config
    # @return: {"text", "format", "kept", "dropped", "notes", "validation"}
    # The order is deliberate: first the submission floor (D26), then the
    # format, then the round trip through the validator. A report that fails
    # validation is still returned so the caller can show why.
    resolved = _normalize_format(fmt)
    if resolved is None:
        raise ValueError(f"Unknown report format: {fmt!r}")
    kept, dropped, notes = submittable(points, cfg)
    if resolved == "mpc80":
        text = to_mpc80(kept, obs_code, designation, cfg)
    else:
        text = to_ades_psv(kept, obs_code, designation, cfg)
    validation = validate_generated(text, obs_code, designation)
    return {"text": text, "format": resolved, "kept": kept,
            "dropped": dropped, "notes": notes, "validation": validation}
