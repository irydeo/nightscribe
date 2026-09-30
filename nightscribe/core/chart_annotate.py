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


def format_exptime(exptime_s):
    # @args: exptime_s - exposure time in seconds
    # @return: "Exp: 10.0 s" ("600 s" past one minute of exposure)
    if exptime_s is None:
        return None
    if exptime_s >= 99.95:
        return f"Exp: {exptime_s:.0f} s"
    return f"Exp: {exptime_s:.1f} s"


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
ROLE_MAG = "mag"              # measured on THIS plate, and trustworthy
ROLE_MAG_DOUBT = "mag-doubt"  # measured, but the numbers say be careful
ROLE_MAG_CAT = "mag-cat"      # only a catalog value: not a measurement
ROLE_CONTEXT = "context"      # date, exposure, filter, kit, Stn, PSc, FOV

# The context fields, in the order they are DROPPED when the band runs out
# of room: the least report-critical first and the date last (a chart
# without a date is not a chart). The renderer walks this list, never a
# half-drawn field.
DROP_ORDER = ("fov", "psc", "equip", "filter", "stn", "date")
# ... and the identity line, when even that does not fit: the magnitude
# goes first, then the position, and only then is the name elided.
DROP_ORDER_NAME = ("mag", "pos")

# A measured magnitude whose total error passes this is shown as doubtful:
# the colour then says "look at this before you report it". 0.10 mag is the
# line between "a single plate's honest error" and "something is off".
ERR_DOUBT = 0.10


def magnitude_role(measured):
    # Which colour the magnitude deserves, from the measurement's own
    # numbers. Four honest signals, all of them things the recipe already
    # computes: the error it declares, how many comparisons hold the zero
    # point, what the check star said, and whether the target's core was
    # clipped on the plate.
    # @args: measured - {"mag", "err", "band", "used", "check", "result"}
    #        of a calibration of THIS plate, or None
    # @return: ROLE_MAG, ROLE_MAG_DOUBT, or None when nothing was measured
    if not measured or measured.get("mag") is None:
        return None
    err = measured.get("err")
    if err is not None and err > ERR_DOUBT:
        return ROLE_MAG_DOUBT
    if len(measured.get("used") or []) < 3:
        return ROLE_MAG_DOUBT         # the zero point rests on too little
    check = measured.get("check")
    if check and check.get("ok") is False:
        return ROLE_MAG_DOUBT         # the check star says the night is off
    if (measured.get("result") or {}).get("saturated"):
        return ROLE_MAG_DOUBT         # the target's own core is clipped
    return ROLE_MAG


# A header's camera name can be a 31-character serial
# ("QHY42PRO-1d74db4888698d84c-QHYCCD"): a chart does not need that, and it
# was eating the field of view out of the band. The full value is still in
# the header and in the other charts' boxes.
MAX_EQUIP_CHARS = 24


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
        text = text[:MAX_EQUIP_CHARS - 1].rstrip() + "…"
    return text or None


def _seg(text, role, field):
    # @args: text - what it says, role - the colour it wears, field - the
    #        name the drop order uses
    # @return: one band segment
    return {"text": text, "role": role, "field": field}


def build_band(name=None, meta=None, wcs_info=None, measured=None,
               catalog_mag=None, equipment=None, site=None, target=None):
    # The plate's heading, as two lines of segments.
    # @args: name - object name (always shown when known),
    #        meta - fits_meta.meta_from_header dict (date_obs, exptime_s,
    #        filter), wcs_info - {"ra_deg", "dec_deg",
    #        "scale_arcsec_px", "fov_arcmin": (w, h)} or None when the
    #        plate is not solved, measured - a calibration of this plate
    #        (see magnitude_role), catalog_mag - the project's/catalog
    #        magnitude or None, equipment - see equipment_from_header,
    #        site - see site_from_config (only the station is shown),
    #        target - (ra_deg, dec_deg) of the object, for the case where
    #        there is no solution to place it on the plate
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
    if ra is None and target is not None:
        ra, dec = target
    if ra is not None and dec is not None:
        text = (f"RA {coords.ra_deg_to_hms(float(ra))} · "
                f"Dec {coords.dec_deg_to_dms(float(dec))}")
        if solved:
            identity.append(_seg(text, ROLE_POS, "pos"))
        else:
            # the catalog's position: it is NOT this plate's, and the colour
            # and the word both say so
            identity.append(_seg(text + " (cat)", ROLE_POS_CAT, "pos"))
    role = magnitude_role(measured)
    if role is not None:
        identity.append(_seg(
            format_mag_value(measured["mag"], measured.get("err"),
                             measured.get("band")), role, "mag"))
    elif catalog_mag is not None:
        try:
            identity.append(_seg(format_mag_catalog(float(catalog_mag)),
                                 ROLE_MAG_CAT, "mag"))
        except (TypeError, ValueError):
            pass
    context = []
    date = format_date_ut(meta.get("date_obs"))
    if date:
        context.append(_seg(date, ROLE_CONTEXT, "date"))
    exp = format_exptime(meta.get("exptime_s"))
    if exp:
        context.append(_seg(exp.split(": ", 1)[1], ROLE_CONTEXT, "exp"))
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
    return {"lines": [identity, context]}
