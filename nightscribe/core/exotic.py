############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - EXOTIC handoff (inits.json) module (Track D, subplan 4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""EXOTIC (rzellem/EXOTIC, NASA/JPL) integration by file handoff.

NightScribe never runs EXOTIC (it needs Python <=3.10 + astropy — ADR-004):
it writes a pre-filled ``inits.json`` and the observer reduces apart. The
structure here is fixed against the real sample in the EXOTIC repository
(``inits.json`` at the repository root, re-verified 2026-09-10): exact key
spelling, null conventions ("Target Star X & Y Pixel": null -> the wizard
asks), separate Flats/Darks/Biases directories and the English
"17-December-2017" observation-date format (a file format, not UI text).

Unit conventions: pscomppars gives the planet radius in Jupiter radii and
the stellar radius in Solar radii, so
``Rp/Rs = pl_radj * 0.10045 / st_rad`` and
``a/Rs  = pl_orbsmax / (st_rad * 0.00465047)`` (Rsun in AU).
"""

import datetime
import json
import logging
from pathlib import Path

from . import coords, exposure

logger = logging.getLogger(__name__)

_RJUP_IN_RSUN = 0.10045    # nominal equatorial R_jupiter / R_sun
_RSUN_IN_AU = 0.00465047   # R_sun in astronomical units

# NightScribe filter-wheel slot -> (AAVSO filter code, min nm, max nm).
# Codes from aavso.org/filters; only the photometric filters carry a clean
# effective-wavelength/FWHM pair — the rest stay null and EXOTIC treats
# the filter as custom (its guide: "enter in the FWHM in optional_info").
_FILTERS = {
    "L": ("CV", None, None),        # luminance ≈ clear reduced to V
    "R": ("R", 561.7, 719.7),       # Cousins R: 6407 Å, FWHM 1580 Å
    "V": ("V", 502.8, 586.8),       # Johnson V: 5448 Å, FWHM 840 Å
    "B": ("B", 391.6, 480.6),       # Johnson B: 4361 Å, FWHM 890 Å
    "G": ("TG", None, None),        # DSLR green
    "Ha": ("HA", None, None),       # H-alpha 6563 Å
}

_MONTHS = ("January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December")


def _ra_hms(ra_deg):
    # @args: ra_deg - right ascension in degrees
    # @return: "HH:MM:SS" (EXOTIC's mandatory sexagesimal format)
    total = (float(ra_deg) / 15.0) % 24.0
    h = int(total)
    m = int((total - h) * 60)
    s = ((total - h) * 60 - m) * 60
    return f"{h:02d}:{m:02d}:{s:05.2f}"


def _dec_dms(dec_deg):
    # @args: dec_deg - declination in degrees
    # @return: "+DD:MM:SS" (explicit leading sign, EXOTIC's format)
    sign = "+" if float(dec_deg) >= 0 else "-"
    total = abs(float(dec_deg))
    d = int(total)
    m = int((total - d) * 60)
    s = ((total - d) * 60 - m) * 60
    return f"{sign}{d:02d}:{m:02d}:{s:05.2f}"


def _obs_date(dt):
    # @args: dt - UTC datetime of the (mid-)transit
    # @return: "17-December-2017" — English month name on purpose: it is
    #          EXOTIC's file convention, not UI text (never localized)
    return f"{dt.day}-{_MONTHS[dt.month - 1]}-{dt.year}"


def _ratio_rp_rs(pl_radj, st_rad):
    # @return: Rp/Rs from the TAP fields, or None when either is missing
    try:
        if pl_radj is None or st_rad in (None, 0):
            return None
        return float(pl_radj) * _RJUP_IN_RSUN / float(st_rad)
    except (TypeError, ValueError):
        return None


def _ratio_a_rs(pl_orbsmax, st_rad):
    # @return: a/Rs from the TAP fields, or None when either is missing
    try:
        if pl_orbsmax is None or st_rad in (None, 0):
            return None
        return float(pl_orbsmax) / (float(st_rad) * _RSUN_IN_AU)
    except (TypeError, ValueError):
        return None


def make_inits(ctx, d, cfg, plan=None, out_dir=None):
    # Builds the EXOTIC inits dict pre-filled from what NightScribe knows.
    # @args: ctx - project context (carries the "transit" event snapshot:
    #        capture window, mid, t0...), d - enriched data (Exoplanet
    #        Archive row, with the planner event merged ADR-027-style),
    #        cfg - Config (site, camera profile, AAVSO code),
    #        plan - optional {"filter", "exp_s"} from the capture plan,
    #        out_dir - directory the inits.json is being written to (used
    #        for the plots directory and as the FITS-dir placeholder)
    # @return: the inits dict, EXOTIC structure (null where a datum is
    #          missing — EXOTIC's wizard then asks for it)
    tr = (ctx or {}).get("transit") or {}
    d = d or {}
    plan = plan or {}

    name = d.get("pl_name") or (ctx or {}).get("name") or ""
    host = d.get("hostname") or tr.get("star") or ""
    ra = d.get("ra", (ctx or {}).get("ra_deg"))
    dec = d.get("dec", (ctx or {}).get("dec_deg"))

    # published mid-transit: the Archive value, else the catalogue t0,
    # else tonight's mid-transit computed by the planner (all BJD-ish JD)
    mid_bjd = d.get("pl_tranmid") or tr.get("t0")
    if mid_bjd is None and tr.get("mid") is not None:
        mid = tr["mid"]
        if isinstance(mid, str):
            mid = datetime.datetime.fromisoformat(mid)
        mid_bjd = round(coords.jd_from_datetime(mid), 6)

    # observation date: tonight's transit (fallback: today)
    when = tr.get("mid")
    if isinstance(when, str):
        when = datetime.datetime.fromisoformat(when)
    if when is None:
        when = datetime.datetime.now(datetime.timezone.utc)

    camera = (cfg.get("camera_type", "CCD") if cfg else "CCD") or "CCD"
    notes = [f"NightScribe transit handoff: {name} on {_obs_date(when)}.",
             "Set 'Directory with FITS files' to your reduced frames folder"
             " before running EXOTIC."]
    if camera.upper() == "CMOS":
        # EXOTIC's own guide: CMOS cameras enter "CCD" and note the real
        # type in the observing notes
        notes.append("Camera is CMOS (entered as CCD per EXOTIC's guide).")
        camera = "CCD"

    filt_slot = (plan.get("filter") or "L").strip()
    filt_code, filt_min, filt_max = _FILTERS.get(filt_slot, ("O", None, None))
    scale = None
    if cfg:
        ps = exposure.plate_scale(cfg.get("pixel_um"), cfg.get("focal_mm"))
        scale = round(ps, 3) if ps else None

    def _f(x):
        # tolerant float-or-None for TAP values (some arrive as strings)
        try:
            return float(x) if x is not None else None
        except (TypeError, ValueError):
            return None

    height = (cfg.get("height") if cfg else None) or None
    return {
        "inits_guide": {
            "Title": "EXOTIC's Initialization File",
            "Comment": "Pre-filled by NightScribe (transit project handoff)."
                       " Check the FITS directory and run EXOTIC in your own"
                       " Python <=3.10 environment.",
        },
        "user_info": {
            "Directory with FITS files": str(out_dir) if out_dir else None,
            "Directory to Save Plots": str(out_dir) if out_dir else None,
            "Directory of Flats": None,
            "Directory of Darks": None,
            "Directory of Biases": None,
            "AAVSO Observer Code (blank if none)":
                (cfg.get("aavso_code", "") if cfg else ""),
            "Secondary Observer Codes (blank if none)": "",
            "Observation date": _obs_date(when),
            "Obs. Latitude": f"{float(cfg.get('lat', 0.0)):+.6f}" if cfg
                             else None,
            "Obs. Longitude": f"{float(cfg.get('lon', 0.0)):+.6f}" if cfg
                              else None,
            "Obs. Elevation (meters)": int(height) if height else None,
            "Camera Type (CCD or DSLR)": camera,
            "Pixel Binning": (cfg.get("pixel_binning", "1x1") if cfg
                              else "1x1"),
            "Filter Name (aavso.org/filters)": filt_code,
            "Observing Notes": " ".join(notes),
            "Plate Solution? (y/n)": "y",
            "Add Comparison Stars from AAVSO? (y/n)": "y",
            "Target Star X & Y Pixel": None,
            "Comparison Star(s) X & Y Pixel": None,
            "Demosaic Format": None,
            "Demosaic Output": None,
        },
        "planetary_parameters": {
            "Target Star RA": _ra_hms(ra) if ra is not None else None,
            "Target Star Dec": _dec_dms(dec) if dec is not None else None,
            "Planet Name": name,
            "Host Star Name": host,
            "Orbital Period (days)": _f(d.get("pl_orbper")),
            "Orbital Period Uncertainty": None,
            "Published Mid-Transit Time (BJD-UTC)": _f(mid_bjd),
            "Mid-Transit Time Uncertainty": None,
            "Ratio of Planet to Stellar Radius (Rp/Rs)":
                _ratio_rp_rs(d.get("pl_radj"), d.get("st_rad")),
            "Ratio of Planet to Stellar Radius (Rp/Rs) Uncertainty": None,
            "Ratio of Distance to Stellar Radius (a/Rs)":
                _ratio_a_rs(d.get("pl_orbsmax"), d.get("st_rad")),
            "Ratio of Distance to Stellar Radius (a/Rs) Uncertainty": None,
            "Orbital Inclination (deg)": _f(d.get("pl_orbincl")),
            "Orbital Inclination (deg) Uncertainty": None,
            "Orbital Eccentricity (0 if null)": _f(d.get("pl_orbeccen")) or 0,
            "Argument of Periastron (deg)": None,
            "Star Effective Temperature (K)": _f(d.get("st_teff")),
            "Star Effective Temperature (+) Uncertainty": None,
            "Star Effective Temperature (-) Uncertainty": None,
            "Star Metallicity ([FE/H])": _f(d.get("st_met",
                                                  d.get("st_metfe"))),
            "Star Metallicity (+) Uncertainty": None,
            "Star Metallicity (-) Uncertainty": None,
            "Star Surface Gravity (log(g))": _f(d.get("st_logg")),
            "Star Surface Gravity (+) Uncertainty": None,
            "Star Surface Gravity (-) Uncertainty": None,
            "Star Distance (pc)": _f(d.get("sy_dist")),
            "Star Proper Motion RA (mas/yr)": _f(d.get("sy_pmra")),
            "Star Proper Motion DEC (mas/yr)": _f(d.get("sy_pmdec")),
        },
        "optional_info": {
            "Filter Minimum Wavelength (nm)": filt_min,
            "Filter Maximum Wavelength (nm)": filt_max,
            "Image Scale (Ex: 5.21 arcsecs/pixel)": scale,
            "Exposure Time (s)": _f(plan.get("exp_s")),
        },
    }


def suggested_name(now=None):
    # EXOTIC's own naming convention for the file.
    # @args: now - datetime (default: now)
    # @return: "inits_MM_DD_YYYY__HH_MM_SS.json"
    now = now or datetime.datetime.now()
    return now.strftime("inits_%m_%d_%Y__%H_%M_%S.json")


def export_inits(inits, out):
    # Writes the inits dict as JSON (the handoff file EXOTIC loads).
    # @args: inits - make_inits dict, out - output path (.json)
    # @return: the output path
    Path(out).write_text(json.dumps(inits, indent=4, ensure_ascii=False)
                         + "\n", encoding="utf-8")
    logger.info("EXOTIC inits written to %s", out)
    return str(out)
