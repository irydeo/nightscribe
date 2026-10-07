############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Chart annotation boxes module (ADR-046)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Assembles the metadata corner boxes stamped on the exported charts
(ADR-046): object name, epoch, position, brightness, exposure, observer,
station, equipment and plate scale, in the spirit of the classic tracker
charts without copying any layout.

This module is PURE: no Qt, no matplotlib, no network. Both rendering
stacks (the UFE's QPainter HUD/export and the matplotlib blink / finder
exports) consume the same dict of text lines, so the rules live once:

* the object name is always shown (when known);
* position, pixel scale and FOV only appear with an astrometric solution;
* the brightness only appears with a photometric calibration handed in
  (a catalog magnitude from the project is NOT a calibration of this
  plate);
* empty site/equipment fields simply omit their line.

Labels are the standard report abbreviations (RA, Dec, Date, Mag, Exp,
Obs, Msr, Stn, Tel, PSc, FOV, Cam): language-neutral by design, the same
text on ES and EN exports.
"""

import logging

from . import coords, fits_meta

logger = logging.getLogger(__name__)


def format_date_ut(date_obs):
    # @args: date_obs - raw FITS date string (ISO 8601 or the legacy
    #        dd/mm/yy), or None
    # @return: "2026-09-20 21:06 UT", "2026-09-20" when the card carries
    #          no time, the raw string when unparseable, or None
    if not date_obs:
        return None
    dt = fits_meta._parse_fits_date(date_obs)
    if dt is None:
        return str(date_obs).strip()[:24] or None
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0 \
            and "T" not in str(date_obs):
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d %H:%M UT")


def format_position(ra_deg, dec_deg):
    # @args: ra_deg, dec_deg - J2000 degrees
    # @return: ("RA: 22 02 16.4", "Dec: +39 49 46.6")
    return (f"RA: {coords.ra_deg_to_hms(ra_deg)}",
            f"Dec: {coords.dec_deg_to_dms(dec_deg)}")


def format_mag(mag, err=None, band=None):
    # @args: mag - calibrated magnitude, err - total error or None,
    #        band - photometric band or None
    # @return: "Mag: 16.39 ± 0.04 (V)" (the error and the band are
    #          dropped when absent)
    line = f"Mag: {mag:.2f}"
    if err is not None:
        line += f" ± {err:.2f}"
    if band:
        line += f" ({band})"
    return line


def format_mag_value(mag, err=None, band=None):
    # The same number without the label: the plate's band is positional
    # (the magnitude is what comes after the position), so it does not
    # repeat "Mag:" in every line.
    # @return: "16.39 ± 0.04 (V)"
    return format_mag(mag, err, band).split(": ", 1)[1]


def format_mag_catalog(mag):
    # A magnitude that is NOT a measurement of this plate: the catalogue's
    # or the project's value. It says so, because a reader cannot tell them
    # apart by looking, and the colour alone is not enough on a printout.
    # @args: mag - catalogue magnitude
    # @return: "12.00 cat"
    return f"{mag:.2f} cat"


def format_mag_ephemeris(mag, band=None):
    # A magnitude the EPHEMERIS predicts for this instant, not a measurement:
    # the same idea as the catalogue's "cat" and the motion's "eph", and the
    # word rides along because the colour is not there on a printout.
    # @args: mag - predicted magnitude, band - "V", "T" or None
    # @return: "22.21 V (eph)" / "18.76 T (eph)"
    text = f"{mag:.2f}" + (f" {band}" if band else "")
    return f"{text} (eph)"


def format_mag_measured(mag, err=None, band=None):
    # A magnitude MEASURED on this plate. It says so too: with the ephemeris'
    # and the catalogue's values both labelled, an unlabelled figure would be
    # the only one whose origin has to be guessed (asked for).
    # @return: "16.39 ± 0.04 (V) (measured)"
    return format_mag_value(mag, err, band) + " (measured)"


def format_exptime(exptime_s):
    # @args: exptime_s - exposure time in seconds
    # @return: "Exp: 10.0 s" ("600 s" past one minute of exposure)
    if exptime_s is None:
        return None
    if exptime_s >= 99.95:
        return f"Exp: {exptime_s:.0f} s"
    return f"Exp: {exptime_s:.1f} s"


def format_exposure(n_frames, exptime_s):
    # A stack is not "one 3 s frame": it is the sum of the frames it
    # combines, and saying only the exposure hides how much light there is.
    # @args: n_frames - how many frames the stack combines (or None),
    #        exptime_s - exposure time of each one, in seconds
    # @return: "8 × 3.0 s" for a stack, "3.0 s" for a single frame, or None
    single = format_exptime(exptime_s)
    if single is None:
        return None
    text = single.split(": ", 1)[1]
    try:
        n = int(n_frames)
    except (TypeError, ValueError):
        n = 0
    if n > 1:
        return f"{n} × {text}"
    return text


def format_rate(rate_arcsec_min):
    # @args: rate_arcsec_min - apparent sky rate in arcsec/min
    # @return: "1.23″/min". The band puts the rate and the PA as two
    #          segments so the renderer joins them with its own separator
    #          (the same dot as between the other data), instead of gluing
    #          them into one run of text.
    return f"{rate_arcsec_min:.2f}″/min"


def format_pa(pa_deg):
    # @args: pa_deg - position angle in degrees (north through east)
    # @return: "PA 245°"
    return f"PA {pa_deg:.0f}°"


def format_pixel_scale(arcsec_px):
    # @args: arcsec_px - plate scale in arcsec/pixel
    # @return: "PSc: 1.07″/px"
    return f"PSc: {arcsec_px:.2f}″/px"


def format_fov(fov_arcmin):
    # @args: fov_arcmin - (width, height) of the shown field in arcmin
    # @return: "FOV: 6.8 × 6.8′", switching to degrees past a degree
    #          and a half ("FOV: 2.1 × 1.4°")
    w, h = fov_arcmin
    if max(w, h) >= 90.0:
        return f"FOV: {w / 60.0:.1f} × {h / 60.0:.1f}°"
    return f"FOV: {w:.1f} × {h:.1f}′"


def site_lines(site):
    # The site/equipment block, omitting whatever is not configured.
    # @args: site - {"observer", "measurer", "station", "telescope",
    #        "camera"} (any may be empty/None); an empty measurer falls
    #        back to the observer (the usual case: same person)
    # @return: ["Obs: …", "Msr: …", "Stn: …", "Tel: …", "Cam: …"] minus
    #          the empty ones
    site = site or {}
    observer = (site.get("observer") or "").strip()
    measurer = (site.get("measurer") or "").strip() or observer
    lines = []
    if observer:
        lines.append(f"Obs: {observer}")
    if measurer:
        lines.append(f"Msr: {measurer}")
    if (site.get("station") or "").strip():
        lines.append(f"Stn: {site['station'].strip()}")
    if (site.get("telescope") or "").strip():
        lines.append(f"Tel: {site['telescope'].strip()}")
    if (site.get("camera") or "").strip():
        lines.append(f"Cam: {site['camera'].strip()}")
    return lines


def build_boxes(name=None, meta=None, wcs_info=None, site=None,
                measured=None):
    # The whole rule set in one place.
    # @args: name - object name (always shown when known),
    #        meta - fits_meta.meta_from_header dict (date_obs,
    #        exptime_s), wcs_info - {"ra_deg", "dec_deg",
    #        "scale_arcsec_px", "fov_arcmin": (w, h)} or None when the
    #        plate is not solved, site - see site_lines,
    #        measured - {"mag", "err", "band"} of a calibrated
    #        measurement, or None
    # @return: {"top_left": [lines], "top_right": [lines],
    #           "bottom_left": [lines]}; boxes without content are
    #           omitted, and with nothing at all the dict is empty
    meta = meta or {}
    top_left = [str(name).strip()] if name and str(name).strip() else []
    top_right = []
    date = format_date_ut(meta.get("date_obs"))
    if date:
        top_right.append(f"Date: {date}")
    bottom_left = site_lines(site)
    if wcs_info is not None:
        ra, dec = wcs_info.get("ra_deg"), wcs_info.get("dec_deg")
        if ra is not None and dec is not None:
            top_right.extend(format_position(ra, dec))
    if measured is not None and measured.get("mag") is not None:
        top_right.append(format_mag(measured["mag"], measured.get("err"),
                                    measured.get("band")))
    exp = format_exptime(meta.get("exptime_s"))
    if exp:
        top_right.append(exp)
    if wcs_info is not None:
        scale = wcs_info.get("scale_arcsec_px")
        if scale:
            bottom_left.append(format_pixel_scale(scale))
        fov = wcs_info.get("fov_arcmin")
        if fov:
            bottom_left.append(format_fov(fov))
    boxes = {}
    if top_left:
        boxes["top_left"] = top_left
    if top_right:
        boxes["top_right"] = top_right
    if bottom_left:
        boxes["bottom_left"] = bottom_left
    return boxes


def site_from_config(cfg):
    # @args: cfg - the app config (or any mapping with .get)
    # @return: the site dict build_boxes expects, from the config keys
    return {"observer": cfg.get("observer_name", ""),
            "measurer": cfg.get("measurer_name", ""),
            "station": cfg.get("mpc_code", ""),
            "telescope": cfg.get("telescope_desc", ""),
            "camera": cfg.get("camera_model", "")}


# --------------------------------------------------------------- the band
# The plate's own heading (ADR-046 rev. 2026-09-30): the corner boxes said
# it in three dark squares, in the spirit of the classic tracker charts.
# The UFE says it now in ONE band at the top of the image, two lines, with
# a COLOUR PER ROLE: the roles are decided here (pure) and the renderer only
# maps them to colours, so the same datum cannot come out in two colours and
# the meaning can be documented once.
#
# The band does not copy anyone's layout either: no box, no label column,
# and the context line drops whole fields instead of cutting words.

ROLE_NAME = "name"            # the object: whose plate this is
ROLE_POS = "pos"              # the target's position ON this plate (solved)
ROLE_POS_CAT = "pos-cat"      # its catalog position (no solution to place it)
ROLE_MAG = "mag"              # a CLEAN measurement of this plate (green)
ROLE_MAG_FAIR = "mag-fair"    # usable, but not clean (orange)
ROLE_MAG_DOUBT = "mag-doubt"  # not to report without looking (red)
ROLE_MAG_CAT = "mag-cat"      # only a catalog value: not a measurement (white)
ROLE_MAG_EPH = "mag-eph"      # only the ephemeris' prediction (dimmed)
ROLE_MOTION = "motion"        # the object's motion, MEASURED on this plate
ROLE_MOTION_EPH = "motion-eph"  # only the ephemeris' prediction, not measured
ROLE_CONTEXT = "context"      # date, exposure, filter, kit, Stn, PSc, FOV

# The context fields, in the order they are DROPPED when the band runs out
# of room: the least report-critical first and the date last (a chart
# without a date is not a chart). The renderer walks this list, never a
# half-drawn field.
DROP_ORDER = ("fov", "psc", "equip", "filter", "stn", "date")
# ... and the identity line, when even that does not fit: the motion goes
# first (it is the story, not the identity), then the magnitude, and only
# then is the position elided. The name is never dropped.
DROP_ORDER_NAME = ("motion", "mag", "pos")

# The two lines of the magnitude's colour code, in magnitudes of total
# error. A single plate's honest error sits around 0.03-0.08, so 0.05 keeps
# the green for what is really clean and 0.15 is the point where a number
# stops being worth reporting without looking at it. The observer asked for
# the three colours and these are the numbers behind them.
ERR_GOOD = 0.05
ERR_BAD = 0.15


def magnitude_role(measured):
    # Which colour the magnitude deserves: GREEN for a clean measurement,
    # ORANGE for a usable one that is not clean, RED for one that is not
    # worth reporting without looking, and WHITE for a value that is not a
    # measurement of this plate at all (the catalogue's).
    #
    # Everything is decided from the measurement's OWN numbers, all of them
    # things the recipe already computes: the error it declares, how many
    # comparisons hold the zero point, what the check star said, whether the
    # target's core was clipped, whether the magnitude came out of a colour
    # and the flags the point carries. A single plate's measurement and a
    # point of a series arrive in the same shape, so one curve and one plate
    # are coloured by the same rule.
    # @args: measured - {"mag", "err", "band", "comps", "check_ok",
    #        "no_check", "clipped", "derived", "below_gate", "flags"} of a
    #        measurement of THIS plate, or None. "check_ok" is the check
    #        star's verdict (True/False) and "no_check" says that the
    #        sequence carried none to begin with: a series has no check in
    #        its contract, and that is not the same as a night nobody
    #        verified. "below_gate" says the object never cleared the
    #        detection gate: the brightness was measured anyway (ADR-062
    #        rev), at the ephemeris' own position, and that is a number to
    #        look at, not one to publish.
    # @return: ROLE_MAG, ROLE_MAG_FAIR, ROLE_MAG_DOUBT, or None
    if not measured or measured.get("mag") is None:
        return None
    err = measured.get("err")
    comps = measured.get("comps")
    flags = list(measured.get("flags") or [])
    # FIRST WHAT MAKES A NUMBER UNREPORTABLE, then what makes it merely
    # imperfect: a serious caveat is not softened by a small error.
    if measured.get("below_gate") or "below_gate" in flags:
        return ROLE_MAG_DOUBT         # the object was never detected
    if err is not None and err > ERR_BAD:
        return ROLE_MAG_DOUBT
    if comps is not None and comps < 3:
        return ROLE_MAG_DOUBT         # the zero point rests on too little
    if measured.get("check_ok") is False:
        return ROLE_MAG_DOUBT         # the check star says the night is off
    if measured.get("clipped"):
        return ROLE_MAG_DOUBT         # the target's own core is clipped
    if err is not None and err > ERR_GOOD:
        return ROLE_MAG_FAIR          # usable, but not clean
    if comps == 3:
        return ROLE_MAG_FAIR          # the minimum that holds a zero point
    if measured.get("derived"):
        return ROLE_MAG_FAIR          # the magnitude came out of a colour
    if measured.get("no_check"):
        return ROLE_MAG_FAIR          # the sequence had no check star to say
    if flags:
        return ROLE_MAG_FAIR          # the point carries its own caveat
    return ROLE_MAG


# A header's camera name can be a 31-character serial
# ("QHY42PRO-1d74db4888698d84c-QHYCCD"): a chart needs the rig, not its
# serial number, and the long name was eating the field of view out of the
# band. Ten characters say SXV-H18, ASI2600 or QHY42PRO. The full value is
# still in the header and in the other charts' boxes.
MAX_EQUIP_CHARS = 10


def equipment_from_header(header, cfg=None):
    # The kit that took THIS plate, preferred over the observer's own
    # Settings: a colleague's frame says SXV-H18, and stamping the
    # observer's camera on it would be a lie. And the two are never MIXED
    # (his camera with my telescope would be a worse lie than either): if
    # the header names any of it, the header is the whole answer, and the
    # Settings are only the fallback for a frame that says nothing.
    # @args: header - the plate's FITS header dict, cfg - the app config
    # @return: "SXV-H18" / "SXV-H18 · 0.2 m SCT" / "ASI2600 · 0.25 m" / None
    header = header or {}
    cfg = cfg or {}

    def pick(keys):
        for key in keys:
            value = str(header.get(key) or "").strip()
            if value:
                return value
        return ""

    camera = pick(("INSTRUME", "CAMERA"))
    telescope = pick(("TELESCOP",))
    if not camera and not telescope:
        camera = str(cfg.get("camera_model") or "").strip()
        telescope = str(cfg.get("telescope_desc") or "").strip()
    parts = [p for p in (camera, telescope) if p]
    text = " · ".join(parts)
    if len(text) > MAX_EQUIP_CHARS:
        # cut at the cap and never leave a dangling separator: "ASI2600 ·…"
        # reads like a typo, "ASI2600…" reads like a cut name
        text = text[:MAX_EQUIP_CHARS - 1].rstrip(" ·") + "…"
    return text or None


def _seg(text, role, field):
    # @args: text - what it says, role - the colour it wears, field - the
    #        name the drop order uses
    # @return: one band segment
    return {"text": text, "role": role, "field": field}


def build_band(name=None, meta=None, wcs_info=None, measured=None,
               catalog_mag=None, equipment=None, site=None, target=None,
               motion=None, measured_pos=None, predicted_mag=None,
               detection=None):
    # The plate's heading, as two lines of segments.
    # @args: name - object name (always shown when known),
    #        meta - fits_meta.meta_from_header dict (date_obs, exptime_s,
    #        filter) plus "n_frames" for a stack, wcs_info - {"ra_deg",
    #        "dec_deg", "scale_arcsec_px", "fov_arcmin": (w, h)} or None
    #        when the plate is not solved, measured - a calibration of this
    #        plate (see magnitude_role), catalog_mag - the project's/catalog
    #        magnitude or None, equipment - see equipment_from_header,
    #        site - see site_from_config (only the station is shown),
    #        target - (ra_deg, dec_deg) of the object, for the case where
    #        there is no solution to place it on the plate, motion -
    #        {"rate_arcsec_min", "pa_deg", "measured"} of the object's
    #        apparent motion or None, measured_pos - (ra_deg, dec_deg) of
    #        the object MEASURED on this plate, which beats the catalogue's,
    #        predicted_mag - {"mag", "band"} the ephemeris predicts, used
    #        when nothing was measured here, detection - {"detected", "snr",
    #        "gate", "limit"} the detection made on THIS plate (the whole
    #        sequence's stack), or None
    # @return: {"lines": [[segment, ...], [segment, ...]]}: the identity
    #          line is never empty (when there is a name), the context line
    #          can be
    meta = meta or {}
    site = site or {}
    identity = []
    if name and str(name).strip():
        identity.append(_seg(str(name).strip(), ROLE_NAME, "name"))
    ra = dec = None
    solved = wcs_info is not None
    if solved:
        ra, dec = wcs_info.get("ra_deg"), wcs_info.get("dec_deg")
    if measured_pos is not None:
        # The position MEASURED on this plate (the astrometry's centroid):
        # it is this plate's own, so it wears the ink and not the (cat) of
        # a catalogue value placed by the solution.
        ra, dec = measured_pos
    elif ra is None and target is not None:
        ra, dec = target
    if ra is not None and dec is not None:
        text = (f"RA {coords.ra_deg_to_hms(float(ra))} · "
                f"Dec {coords.dec_deg_to_dms(float(dec))}")
        if solved or measured_pos is not None:
            identity.append(_seg(text, ROLE_POS, "pos"))
        else:
            # the catalog's position: it is NOT this plate's, and the colour
            # and the word both say so
            identity.append(_seg(text + " (cat)", ROLE_POS_CAT, "pos"))
    # The brightness, and WHERE IT COMES FROM: a measurement on this plate
    # (with its own quality colour), the ephemeris' prediction for this
    # instant, or the catalogue's value. Every case carries its word, so the
    # figure is never a number whose origin has to be guessed (asked for).
    role = magnitude_role(measured)
    if role is not None:
        identity.append(_seg(
            format_mag_measured(measured["mag"], measured.get("err"),
                                measured.get("band")), role, "mag"))
    elif predicted_mag is not None and predicted_mag.get("mag") is not None:
        try:
            identity.append(_seg(
                format_mag_ephemeris(float(predicted_mag["mag"]),
                                     predicted_mag.get("band")),
                ROLE_MAG_EPH, "mag"))
        except (TypeError, ValueError):
            pass
    elif catalog_mag is not None:
        try:
            identity.append(_seg(format_mag_catalog(float(catalog_mag)),
                                 ROLE_MAG_CAT, "mag"))
        except (TypeError, ValueError):
            pass
    # The object's motion: the velocity sweep's own answer when it was
    # measured (ink), the ephemeris' prediction otherwise (dimmed and with
    # the word, the same way a catalogue position says (cat)). The rate and
    # the PA are TWO segments, so the renderer joins them with the same
    # separator it puts between every other datum; the marker rides the last
    # one (the PA when there is one).
    if motion and motion.get("rate_arcsec_min") is not None:
        is_measured = bool(motion.get("measured"))
        role = ROLE_MOTION if is_measured else ROLE_MOTION_EPH
        parts = [format_rate(motion["rate_arcsec_min"])]
        if motion.get("pa_deg") is not None:
            parts.append(format_pa(motion["pa_deg"]))
        parts[-1] += " (measured)" if is_measured else " (eph)"
        for text in parts:
            identity.append(_seg(text, role, "motion"))
    context = []
    date = format_date_ut(meta.get("date_obs"))
    if date:
        context.append(_seg(date, ROLE_CONTEXT, "date"))
    exp = format_exposure(meta.get("n_frames"), meta.get("exptime_s"))
    if exp:
        context.append(_seg(exp, ROLE_CONTEXT, "exp"))
    filt = str(meta.get("filter") or "").strip()
    if filt:
        context.append(_seg(filt, ROLE_CONTEXT, "filter"))
    if equipment:
        context.append(_seg(str(equipment), ROLE_CONTEXT, "equip"))
    if (site.get("station") or "").strip():
        context.append(_seg(f"Stn {site['station'].strip()}", ROLE_CONTEXT,
                            "stn"))
    if solved:
        scale = wcs_info.get("scale_arcsec_px")
        if scale:
            context.append(_seg(f"{scale:.2f}″/px", ROLE_CONTEXT, "psc"))
        fov = wcs_info.get("fov_arcmin")
        if fov:
            context.append(_seg(format_fov(fov).split(": ", 1)[1],
                                ROLE_CONTEXT, "fov"))
    # The detection made on THIS plate (the whole-sequence stack): its SNR
    # against the gate it had to clear and the limit magnitude it reached.
    # Both are measurements of this image, so they wear the ink; the words
    # say what each figure is (a bare "3.1" teaches nothing).
    if detection:
        snr = detection.get("snr")
        if snr is not None:
            text = f"SNR {float(snr):.1f}"
            gate = detection.get("gate")
            if gate is not None:
                text += f" (gate {float(gate):.1f}σ)"
            context.append(_seg(text, ROLE_MOTION, "det"))
        limit = detection.get("limit")
        if limit is not None:
            context.append(_seg(f"limit {float(limit):.1f}", ROLE_CONTEXT,
                                "limit"))
    return {"lines": [identity, context]}
