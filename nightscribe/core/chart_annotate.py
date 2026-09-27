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
