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
from dataclasses import dataclass

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
# lowercase letters are the SDSS filters (g, r, i, z). "G" is the Gaia band
# the app's comparisons come from and keeps its uppercase (the MPC lists both
# G and g). A primed filter ("r'") is SDSS, so the prime is kept as a 'p'
# marker before the other separators are stripped. An unknown filter NEVER
# gets an invented code: it falls to "C" (clear / unfiltered) with a warning,
# which is the honest answer when the band is unknown.
_BAND_EXACT = {
    "V": "V", "v": "V",
    "B": "B", "b": "B",
    "R": "R",
    "I": "I",
    "U": "U", "u": "U",
    "C": "C", "c": "C",
    "g": "g", "G": "G",
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

# ADES PSV columns, in order. The identifier column (permID/provID/trkSub)
# is chosen per object and goes first; the uncertainty and magnitude columns
# may be empty (ADES makes them optional, and an empty cell is the honest way
# to say "not measured" instead of writing a zero that looks like a
# measurement).
_ADES_COLUMNS = ("mode", "stn", "obsTime", "ra", "dec", "rmsRA", "rmsDec",
                 "astCat", "mag", "band")
# The ADES object-identifier columns; at least one must carry a value.
_ADES_ID_FIELDS = ("permID", "provID", "trkSub", "artSat", "objid")

# The instrument type the report declares (2026-10-07). The MPC keeps its own
# lists of allowed values and an unlisted one makes the whole batch be
# rejected, so the names are the MPC's and not ours:
# * ADES "mode": "CCD" or "CMO" (Complementary Metal Oxide Semiconductor).
#   The code is CMO, NOT "CMOS": the long word is the description in the
#   MPC's table, not the value.
# * MPC 1992 (80 columns), column 15: "C" for CCD, "B" for CMOS.
# A DSLR carries a CMOS sensor, so it reports as CMO / "B". The app's
# Settings ("Camera type") is the single source: before this the report
# hardcoded CCD and an sCMOS observer submitted a lie about their own
# detector.
_ADES_MODE = {"CCD": "CCD", "CMOS": "CMO", "DSLR": "CMO"}
_MPC80_MODE = {"CCD": "C", "CMOS": "B", "DSLR": "B"}


@dataclass
class ReportContext:
    # The observer's own details for the submission header (2026-10-11). One
    # place builds them from the settings and every format reads them, so the
    # MPC 1992 header, the ADES PSV context and the ADES XML context can never
    # disagree with one another.
    obs_code: str = ""
    observatory_name: str = ""
    observer: str = ""
    measurer: str = ""
    email: str = ""
    telescope: str = ""              # free text, used verbatim when given
    aperture_m: float | None = None
    focal_ratio: float | None = None
    telescope_type: str = ""
    detector: str = "CCD"
    astcat: str = "Gaia2"
    comment: str = ""

    def tel_body(self):
        # @return: the telescope ALONE, without the detector: "0.43-m f/4.9
        #          reflector", or the observer's free text verbatim
        if self.telescope:
            return self.telescope
        parts = []
        if self.aperture_m:
            parts.append(f"{self.aperture_m:.2f}-m")
        if self.focal_ratio:
            parts.append(f"f/{self.focal_ratio:g}")
        if self.telescope_type:
            parts.append(self.telescope_type)
        return " ".join(parts)

    def tel_mpc80(self):
        # @return: the TEL line body, e.g. "0.43-m f/4.9 reflector + CMO"
        # The observer's free text wins when it is there (it is what the chart
        # boxes already show); otherwise the line is BUILT from the aperture,
        # the focal ratio, the type and the detector, which is what the MPC's
        # TelescopeDetails page asks for and never mentions a brand.
        body = self.tel_body()
        if not body or self.telescope:
            return body
        return f"{body} + {self.detector}"

    def missing(self):
        # @return: the header fields a submission cannot be built without,
        #          named in plain language (the send dialog blocks on this)
        out = []
        if not self.obs_code:
            out.append("the observatory code")
        if not self.observer:
            out.append("the observer's name")
        if not self.tel_mpc80():
            out.append("the telescope")
        if not self.email:
            out.append("the contact email")
        return out


# The MPC 1992 NET line wants the catalogue's name, not the ADES code: the
# description column of the MPC's own astCat list is the translation
# (Birtwhistle's ADES->MPC1992 table documents it).
_NET_DESC = {
    "Gaia1": "Gaia DR 1", "Gaia2": "Gaia DR 2", "Gaia3": "Gaia DR 3",
    "Gaia3E": "Gaia EDR 3", "USNOB1": "USNO-B1.0", "USNOA2": "USNO-A2.0",
    "UCAC4": "UCAC4", "2MASS": "2MASS", "PS1_DR1": "PS1 DR1",
    "SkyMapper2": "SkyMapper DR2", "ATLAS2": "ATLAS2",
}


def _net_name(astcat):
    # @args: astcat - the ADES astCat code
    # @return: the catalogue name the MPC 1992 NET line wants
    key = str(astcat or "").strip()
    return _NET_DESC.get(key, key)


def report_context(cfg=None):
    # @args: cfg - Config, dict or None
    # @return: a ReportContext read from the settings
    def g(key, default=""):
        return _cfg_get(cfg, key, default)

    try:
        aperture_in = float(g("aperture_inches", 0) or 0)
    except (TypeError, ValueError):
        aperture_in = 0.0
    try:
        focal_mm = float(g("focal_mm", 0) or 0)
    except (TypeError, ValueError):
        focal_mm = 0.0
    aperture_m = round(aperture_in * 0.0254, 3) if aperture_in else None
    ratio = None
    raw_ratio = g("telescope_focal_ratio", None)
    if raw_ratio not in (None, "", 0):
        try:
            ratio = float(raw_ratio)
        except (TypeError, ValueError):
            ratio = None
    if ratio is None and aperture_m and focal_mm:
        # derived, never invented: focal length / aperture
        ratio = round(focal_mm / (aperture_m * 1000.0), 1)
    observer = str(g("observer_name", "") or "").strip()
    measurer = str(g("measurer_name", "") or "").strip() or observer
    mode, _code = instrument_mode(cfg)
    return ReportContext(
        obs_code=str(g("mpc_code", "") or "").strip().upper(),
        observatory_name=str(g("observatory_name", "") or "").strip(),
        observer=observer, measurer=measurer,
        email=str(g("observer_email", "") or "").strip(),
        telescope=str(g("telescope_desc", "") or "").strip(),
        aperture_m=aperture_m, focal_ratio=ratio,
        telescope_type=str(g("telescope_type", "") or "").strip(),
        detector="CMO" if mode == "CMO" else "CCD",
        astcat=str(g("astrometry_astcat", "Gaia2") or "Gaia2"),
        comment=str(g("mpc_report_comment", "") or "").strip())


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
    # @return: "YYYY MM DD.ddddd"
    year, month, day_f = _jd_to_ymdf(jd_utc)
    # 5 decimals of a day (~0.86 s) is the MPC's NORMAL precision; 6 is the
    # "extra precision" option, and filling the 17-char field with it leaves
    # no separating space before the RA (2026-10-11, seen against a real
    # report). The norm is what the field is sized for.
    return f"{year:04d} {month:02d} {day_f:08.5f}"


def format_ra_mpc80(ra_deg):
    # @args: ra_deg - right ascension in degrees
    # @return: "HH MM SS.ss"
    # 2 decimals of a second is the MPC's normal precision (0.001 s is the
    # "extra precision" the MPC does not allow most observatories to use).
    # Working in integer centiseconds carries the minute cleanly, so the
    # impossible "60.00" cannot come out.
    total_cs = int(round((float(ra_deg) % 360.0) * 240.0 * 100.0)) \
        % (24 * 3600 * 100)
    hh, rem = divmod(total_cs, 3600 * 100)
    mm, cs = divmod(rem, 60 * 100)
    return f"{hh:02d} {mm:02d} {cs / 100.0:05.2f}"


def format_dec_mpc80(dec_deg):
    # @args: dec_deg - declination in degrees
    # @return: "sDD MM SS.s" with an explicit sign
    # 1 decimal of an arcsecond is the MPC's normal precision (0.01" is the
    # "extra precision" option). The sign is always written: the MPC format
    # needs it even for +00.
    sign = "-" if float(dec_deg) < 0 else "+"
    total_ds = int(round(abs(float(dec_deg)) * 3600.0 * 10.0))
    dd, rem = divmod(total_ds, 3600 * 10)
    mm, ds = divmod(rem, 60 * 10)
    return f"{sign}{dd:02d} {mm:02d} {ds / 10.0:04.1f}"


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


def instrument_mode(cfg):
    # @args: cfg - Config object, dict or None
    # @return: (ades_mode, mpc80_code) for the configured camera type: the
    #          ADES "mode" value and the MPC 1992 column-15 code. An unknown
    #          type falls back to CCD/"C", which is what the report always
    #          wrote before the setting existed.
    raw = str(_cfg_get(cfg, "camera_type", "CCD") or "CCD").strip().upper()
    return (_ADES_MODE.get(raw, "CCD"), _MPC80_MODE.get(raw, "C"))


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


def _mpc80_designation(name, kind=None):
    # @args: name - the object designation, kind - hint (None lets the name
    #        decide: numbered | provisional | comet | neocp/pccp)
    # @return: (cols_1_5, cols_6_12, note): the two MPC 1992 designation
    #          fields, 5 and 7 characters wide, and a note for what needs
    #          confirming. A minor planet puts its packed NUMBER in columns
    #          1-5 and its packed PROVISIONAL in 6-12; a temporary
    #          designation (a NEOCP tag, the observer's own) goes in 6-12
    #          as-is. Before this the app wrote 5 chars of the provisional in
    #          the NUMBER field and lost the rest (2026-10-11).
    raw = (name or "").strip()
    if not raw:
        return " " * 5, " " * 7, (
            "Empty designation: an MPC report cannot be generated.")
    kind_l = (kind or "").strip().lower()
    if kind_l in ("neocp", "pccp"):
        tag = re.sub(r"[^A-Za-z0-9]", "", raw)[:7]
        return " " * 5, f"{tag:<7}", (
            f"'{raw}' is a temporary (NEOCP/PCCP) designation: it is emitted "
            f"as-is as '{tag}'. Confirm it before submitting.")
    if raw.isdigit():
        packed = _pack_number(int(raw))
        if packed:
            return packed, " " * 7, ""
    if (kind_l == "comet" or _COMET_RE.match(raw)
            or _COMET_NUMBERED_RE.match(raw)):
        packed, note = _pack_comet(raw)
        if packed:
            if len(packed) <= 5:
                return packed, " " * 7, note
            # provisional comet: columns 1-4 blank, column 5 = orbit type
            return f"    {packed[0]}", f"{packed[1:8]:<7}", note
    packed = _pack_provisional(raw)
    if packed:
        return " " * 5, f"{packed:<7}", ""
    # a temporary designation we cannot pack: columns 6-12, as-is
    tag = re.sub(r"[^A-Za-z0-9]", "", raw)[:7]
    return " " * 5, f"{tag:<7}", (
        f"Designation '{raw}' is not a packed number or provisional: it is "
        f"emitted as-is as '{tag}' in columns 6-12. Confirm it before "
        "submitting.")


def mpc80_header(ctx, submission=None, n_obs=0):
    # @args: ctx - ReportContext, submission - {"ack","obj_type"} or None,
    #        n_obs - how many observations the batch carries
    # @return: the header lines (COD..NUM), in the order the MPC reads them.
    #          Without them the MPC IGNORES the batch ("Observation batches
    #          that do not include an observational header will not be
    #          recognized", ObsDetails.html), which is what the report was
    #          missing (2026-10-11).
    sub = submission or {}
    lines = []
    if ctx.obs_code:
        lines.append(f"COD {ctx.obs_code}")
    if ctx.observer:
        lines.append(f"CON {ctx.observer}")
        if ctx.email:
            lines.append(f"CON [{ctx.email}]")
        lines.append(f"OBS {ctx.observer}")
    if ctx.measurer:
        lines.append(f"MEA {ctx.measurer}")
    tel = ctx.tel_mpc80()
    if tel:
        lines.append(f"TEL {tel}")
    if ctx.astcat:
        lines.append(f"NET {_net_name(ctx.astcat)}")
    if ctx.comment:
        lines.append(f"COM {ctx.comment}")
    ack = str(sub.get("ack") or "").strip()
    obj_type = str(sub.get("obj_type") or "").strip()
    # The target keyword MUST reach the MPC (ObsDetails.html): the ACK line is
    # its preferred carrier, so it is prepended when the observer's own text
    # does not already name it.
    if obj_type and obj_type.upper() not in ack.upper():
        ack = (obj_type + " " + ack).strip()
    if ack:
        lines.append(f"ACK {ack}")
    if ctx.email:
        lines.append(f"AC2 {ctx.email}")
    if n_obs:
        lines.append(f"NUM {int(n_obs)}")
    return lines


def to_mpc80(points, obs_code, designation, cfg=None, context=None,
             submission=None, kind=None):
    # @args: points - measured observations, obs_code - MPC station code,
    #        designation - the object, cfg - Config (the camera type),
    #        context - a ReportContext; when given, the FULL report is
    #        emitted (header + data + end marker), otherwise only the data
    #        lines, submission - {"ack","obj_type"} for the header, kind -
    #        the designation hint
    # @return: the 80-column block. Field positions follow ObsDetails.html:
    #          number 1-5, provisional/temporary 6-12, asterisk 13, note1 14,
    #          detector 15, date 16-32, RA 33-44, Dec 45-56, magnitude 66-70,
    #          band 71, station 78-80. A missing magnitude leaves the field
    #          blank instead of writing a zero that would read as a
    #          measurement.
    _mode, mode_char = instrument_mode(cfg)
    five, seven, _note = _mpc80_designation(designation, kind)
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
            band_s = " "
        else:
            # 1 decimal is the MPC's normal magnitude precision; 2 is the
            # "extra precision" option and would fill the field, eating the
            # separating space (2026-10-11).
            mag_s = f"{float(mag):.1f}"
            band_s = band_code(band)
        line = (
            f"{five:<5}"                # 0-4   packed number
            f"{seven:<7}"               # 5-11  packed provisional/temporary
            f" "                        # 12    discovery asterisk (blank)
            f" {mode_char}"             # 13-14 note1 blank + detector (15)
            f"{date:<17}"               # 15-31 packed date (T_mid)
            f"{ra_s:<12}"               # 32-43 RA
            f"{dec_s:<12}"              # 44-55 Dec
            f"{'':<9}"                  # 56-64 blank
            f"{mag_s:<5}"               # 65-69 magnitude
            f"{band_s:<1}"              # 70    band
            f"{'':<6}"                  # 71-76 blank
            f"{str(obs_code).upper():<3}"  # 77-79 station
        )
        lines.append(line)
    if context is None:
        return "\n".join(lines)
    header = mpc80_header(context, submission, n_obs=len(lines))
    return "\n".join(header + lines + ["----- end -----"])


def _ades_id(name, kind=None):
    # @args: name - the object designation, kind - hint
    # @return: (column, value): which ADES identifier column carries the
    #          object and its value. A number goes in permID, a provisional
    #          in provID, a temporary (NEOCP/PCCP) tag in trkSub. ADES uses
    #          these columns, NOT the legacy "objid" (2026-10-11).
    raw = (name or "").strip()
    kind_l = (kind or "").strip().lower()
    if kind_l in ("neocp", "pccp"):
        return "trkSub", re.sub(r"[^A-Za-z0-9]", "", raw)[:7]
    if raw.isdigit():
        return "permID", raw
    if _pack_provisional(raw):
        return "provID", raw
    if kind_l == "comet" or _COMET_RE.match(raw) or _COMET_NUMBERED_RE.match(raw):
        return "provID", raw
    return "trkSub", re.sub(r"[^A-Za-z0-9]", "", raw)[:7]


def ades_psv_context(ctx):
    # @args: ctx - ReportContext
    # @return: the ADES PSV context header lines ('#' sections, '!' elements),
    #          or [] when there is nothing to declare. ADES keeps PII OUT of
    #          the document (ADES.html), so the email is NOT here: it travels
    #          in the submission form (ac2).
    lines = ["# version=2017"]
    if ctx.obs_code or ctx.observatory_name:
        lines.append("# observatory")
        if ctx.obs_code:
            lines.append(f"! mpcCode {ctx.obs_code}")
        if ctx.observatory_name:
            lines.append(f"! name {ctx.observatory_name}")
    if ctx.observer:
        lines.append("# submitter")
        lines.append(f"! name {ctx.observer}")
    tel = []
    if ctx.aperture_m:
        tel.append(f"! aperture {ctx.aperture_m:g}")
    if ctx.focal_ratio:
        tel.append(f"! fRatio {ctx.focal_ratio:g}")
    if ctx.telescope_type:
        tel.append(f"! design {ctx.telescope_type}")
    if ctx.detector:
        tel.append(f"! detector {ctx.detector}")
    if tel:
        lines.append("# telescope")
        lines.extend(tel)
    if ctx.observer:
        lines.append("# observers")
        lines.append(f"! name {ctx.observer}")
    if ctx.measurer:
        lines.append("# measurers")
        lines.append(f"! name {ctx.measurer}")
    if ctx.comment:
        lines.append("# comment")
        lines.append(f"! line {ctx.comment}")
    return lines


def to_ades_psv(points, obs_code, designation, cfg=None, context=None,
                kind=None):
    # @args: points - measured observations, obs_code - MPC station code,
    #        designation - the object, cfg - Config, context - a ReportContext;
    #        when given, the obsContext header is prepended, kind - the
    #        designation hint
    # @return: the ADES PSV block. ADES carries what 80 columns cannot: the
    #          rmsRA/rmsDec and the astrometric catalogue. The "mode" cell is
    #          the instrument type from the camera setting (CCD / CMO).
    astcat = _cfg_get(cfg, "astrometry_astcat", "Gaia2")
    if context is not None:
        astcat = context.astcat or astcat
    mode, _code = instrument_mode(cfg)
    id_col, id_val = _ades_id(designation, kind)
    columns = (id_col,) + _ADES_COLUMNS
    lines = ["|".join(columns)]
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
        row = {
            id_col: id_val, "mode": mode, "stn": str(obs_code).upper(),
            "obsTime": _iso_time(mjd), "ra": f"{ra:.6f}",
            "dec": f"{dec:.6f}", "rmsRA": f"{float(rms_ra):.3f}",
            "rmsDec": f"{float(rms_dec):.3f}", "astCat": str(astcat),
            "mag": mag_s, "band": band_s,
        }
        lines.append("|".join(row[c] for c in columns))
    data = "\n".join(lines)
    if context is None:
        return data
    return "\n".join(ades_psv_context(context) + [data])


def to_ades_xml(points, obs_code, designation, cfg=None, context=None,
                kind=None):
    # @args: as to_ades_psv
    # @return: the ADES XML document (the MPC's preferred submission format),
    #          an <ades version="2017"> with one <obsBlock>.
    import xml.etree.ElementTree as ET

    astcat = _cfg_get(cfg, "astrometry_astcat", "Gaia2")
    if context is not None:
        astcat = context.astcat or astcat
    mode, _code = instrument_mode(cfg)
    id_col, id_val = _ades_id(designation, kind)
    root = ET.Element("ades", {"version": "2017"})
    block = ET.SubElement(root, "obsBlock")
    if context is not None:
        ctx = ET.SubElement(block, "obsContext")
        if context.obs_code or context.observatory_name:
            obs = ET.SubElement(ctx, "observatory")
            if context.obs_code:
                ET.SubElement(obs, "mpcCode").text = context.obs_code
            if context.observatory_name:
                ET.SubElement(obs, "name").text = context.observatory_name
        if context.observer:
            ET.SubElement(
                ET.SubElement(ctx, "submitter"), "name").text = context.observer
        tel = ET.SubElement(ctx, "telescope")
        if context.aperture_m:
            ET.SubElement(tel, "aperture").text = f"{context.aperture_m:g}"
        if context.focal_ratio:
            ET.SubElement(tel, "fRatio").text = f"{context.focal_ratio:g}"
        if context.telescope_type:
            ET.SubElement(tel, "design").text = context.telescope_type
        ET.SubElement(tel, "detector").text = context.detector
        if context.observer:
            ET.SubElement(
                ET.SubElement(ctx, "observers"), "name").text = context.observer
        if context.measurer:
            ET.SubElement(
                ET.SubElement(ctx, "measurers"), "name").text = context.measurer
        if context.comment:
            ET.SubElement(
                ET.SubElement(ctx, "comment"), "line").text = context.comment
    data = ET.SubElement(block, "obsData")
    for point in points:
        ra, dec = _ra_dec(point)
        mjd = _point_get(point, "mjd")
        rms_ra = _point_get(point, "rms_ra") or 0.0
        rms_dec = _point_get(point, "rms_dec") or 0.0
        mag = _point_get(point, "mag")
        band = _point_get(point, "band")
        opt = ET.SubElement(data, "optical")
        ET.SubElement(opt, id_col).text = id_val
        ET.SubElement(opt, "mode").text = mode
        ET.SubElement(opt, "stn").text = str(obs_code).upper()
        ET.SubElement(opt, "obsTime").text = _iso_time(mjd)
        ET.SubElement(opt, "ra").text = f"{ra:.6f}"
        ET.SubElement(opt, "dec").text = f"{dec:.6f}"
        ET.SubElement(opt, "rmsRA").text = f"{float(rms_ra):.3f}"
        ET.SubElement(opt, "rmsDec").text = f"{float(rms_dec):.3f}"
        ET.SubElement(opt, "astCat").text = str(astcat)
        if mag is not None:
            ET.SubElement(opt, "mag").text = f"{float(mag):.2f}"
            ET.SubElement(opt, "band").text = band_code(band)
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode")


def submittable(points, cfg=None):
    # @args: points - measured observations, cfg - Config (recommendation floor)
    # @return: (kept, excluded, warnings): the observations that go into the
    #          report, the ones the observer EXCLUDED by hand, and the
    #          advisories for the kept ones that sit below the floor
    # The floor no longer filters (2026-10-10): it RECOMMENDS. Every
    # observation goes into the report unless the observer excluded it, and a
    # low-SNR one goes in WITH a warning, so the report shows it and the app
    # can say it does not recommend sending it. The decision is the observer's;
    # the app never drops a point on its own. Only an explicit `user_excluded`
    # flag (set from the Astrometry tab, and reversible) takes one out.
    threshold = float(_cfg_get(cfg, "astrometry_submit_snr", 20.0))
    kept, excluded, warnings = [], [], []
    for point in points:
        group = _point_get(point, "group_index", "?")
        flags = _point_get(point, "flags") or []
        if "user_excluded" in flags:
            excluded.append(point)
            continue
        kept.append(point)
        snr = _point_get(point, "snr")
        if snr is None:
            warnings.append(
                f"Group {group}: no SNR was measured, so it cannot be shown "
                f"to clear the recommended floor of SNR {threshold:.0f}; the "
                "app does not recommend sending it.")
        elif float(snr) < threshold:
            warnings.append(
                f"Group {group}: SNR {float(snr):.1f} is below the recommended "
                f"floor of {threshold:.0f}. A marginal detection risks a false "
                "tracklet; the app does not recommend sending it.")
    return kept, excluded, warnings


def _normalize_format(fmt):
    # @args: fmt - a format name, case-insensitive
    # @return: "mpc80" | "ades" | "xml" | None
    key = (fmt or "").strip().lower()
    if key in ("mpc80", "80col", "80", "mpc", "mpc1992"):
        return "mpc80"
    if key in ("ades", "psv", "ades_psv", "adespsv"):
        return "ades"
    if key in ("xml", "ades_xml", "adesxml"):
        return "xml"
    return None


def validate_generated(text, obs_code, expected_obj):
    # @args: text - the generated block, obs_code - station, expected_obj -
    #        the object the report claims to be about
    # @return: mpc_report.validate's dict
    # Our own output goes through the same judge as the user's pasted text:
    # if the generator cannot pass its own validator, the bug is ours.
    return mpc_report.validate(text, obs_code, expected_obj)


def generate(points, fmt, obs_code, designation, cfg=None, context=None,
             submission=None, kind=None):
    # @args: points - measured observations, fmt - "mpc80" | "ades" | "xml",
    #        obs_code - station, designation - the object, cfg - Config,
    #        context - a ReportContext (the header is emitted when given),
    #        submission - {"ack","obj_type"} for the MPC 1992 header, kind -
    #        the designation hint
    # @return: {"text", "format", "kept", "excluded", "warnings", "validation"}
    # The order is deliberate: first the observer's own exclusions, then the
    # format, then the round trip through the validator. A report that fails
    # validation is still returned so the caller can show why. The floor only
    # WARNS now: a below-floor observation is kept and its advisory rides in
    # `warnings`, so the observer can still choose to send it.
    resolved = _normalize_format(fmt)
    if resolved is None:
        raise ValueError(f"Unknown report format: {fmt!r}")
    kept, excluded, warnings = submittable(points, cfg)
    if resolved == "mpc80":
        text = to_mpc80(kept, obs_code, designation, cfg, context=context,
                        submission=submission, kind=kind)
    elif resolved == "xml":
        text = to_ades_xml(kept, obs_code, designation, cfg, context=context,
                           kind=kind)
    else:
        text = to_ades_psv(kept, obs_code, designation, cfg, context=context,
                           kind=kind)
    if resolved == "xml":
        # Our validator reads the 80-column and ADES PSV shapes; the XML is
        # judged by the MPC's own schema at submission, so the round trip here
        # is a line count, not a format check.
        validation = {"format": "xml", "valid": bool(kept), "errors": [],
                      "warnings": [], "n_lines": len(kept)}
    else:
        validation = validate_generated(text, obs_code, designation)
    return {"text": text, "format": resolved, "kept": kept,
            "excluded": excluded, "warnings": warnings,
            "validation": validation}
