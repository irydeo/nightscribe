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

Plate solution: the inits asks EXOTIC NOT to request one from
nova.astrometry.net ("Plate Solution? (y/n)" = "n"). With "y" EXOTIC uploads
the first frame and polls the public queue before looking at the frame's own
WCS: measured ~4 min per run, and it failed more often than not, which read
as a hang. With "n" EXOTIC uses the WCS already in the header, or aligns the
frames with astroalign when there is none (see make_inits for the detail).
"""

import datetime
import json
import logging
from pathlib import Path

from . import coords, exposure, fits_io

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


def _propagated_unc(ratio, num, num_err, den, den_err):
    # Rp/Rs and a/Rs are ratios of two archive values, so their relative
    # uncertainty is the quadrature sum of the two relative uncertainties
    # (HAT-P-32 b: Rp/Rs 0.1455 +- 0.0047 from pl_radj 1.98 +- 0.045 and
    # st_rad 1.367 +- 0.031; a/Rs 5.3436 +- 0.1454 from pl_orbsmax
    # 0.03397 +- 0.00051 and the same st_rad).
    # @args: ratio - the derived value; num/num_err, den/den_err - the two
    #        archive values and their uncertainties
    # @return: the propagated uncertainty, or None when a term is missing
    try:
        rel = ((float(num_err) / float(num)) ** 2
               + (float(den_err) / float(den)) ** 2) ** 0.5
        return abs(float(ratio)) * rel
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _obs_datetime(obs_jd, tr):
    # The date the inits carries ("Observation date"), and the one EXOTIC
    # names every output and figure with. The frames' own date is the honest
    # source (measured 2026-09-30: a December 2017 visit was handed over dated
    # 30-September-2026, and every product came out named that way).
    # @args: obs_jd - observation Julian date from the frames, or None,
    #        tr - the project's transit snapshot (may carry "mid")
    # @return: a timezone-aware datetime
    if obs_jd is not None:
        try:
            return coords.datetime_from_jd(float(obs_jd))
        except (TypeError, ValueError):
            logger.warning("ignoring an unusable observation JD: %r", obs_jd)
    when = tr.get("mid")
    if isinstance(when, str):
        try:
            when = datetime.datetime.fromisoformat(when)
        except ValueError:
            when = None
    if when is None:
        when = datetime.datetime.now(datetime.timezone.utc)
    return when


def frame_jd(path):
    # The observation time of a frame, for the inits' date anchor.
    # MJD-OBS first (MicroObservatory writes it), DATE-OBS as the fallback;
    # both are already UTC, so no timezone guessing is needed.
    # @args: path - one FITS frame of the visit
    # @return: the Julian date, or None when the frame has no usable date
    try:
        header = fits_io.read_header(path)
    except Exception as err:          # unreadable frame: not fatal here
        logger.warning("could not read the header of %s: %s", path, err)
        return None
    mjd = header.get("MJD-OBS")
    if mjd is not None:
        try:
            return float(mjd) + 2400000.5      # MJD -> JD
        except (TypeError, ValueError):
            pass
    date = header.get("DATE-OBS")
    if isinstance(date, str) and date.strip():
        try:
            return coords.jd_from_datetime(
                datetime.datetime.fromisoformat(date.strip()))
        except ValueError:
            return None
    return None


def make_inits(ctx, d, cfg, plan=None, out_dir=None, plate_solution=False,
               obs_jd=None):
    # Builds the EXOTIC inits dict pre-filled from what NightScribe knows.
    # @args: ctx - project context (carries the "transit" event snapshot:
    #        capture window, mid, t0...), d - enriched data (Exoplanet
    #        Archive row, with the planner event merged ADR-027-style),
    #        cfg - Config (site, camera profile, AAVSO code),
    #        plan - optional {"filter", "exp_s"} from the capture plan,
    #        out_dir - directory the inits.json is being written to (used
    #        for the plots directory and as the FITS-dir placeholder),
    #        plate_solution - ask nova.astrometry.net for a plate solution
    #        (default False: see the note on the inits field below),
    #        obs_jd - observation Julian date from the visit's frames (the
    #        anchor of "Observation date"; None: the transit snapshot, else
    #        today)
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

    # observation date: the frames' own night (the caller knows it), else
    # tonight's transit, else today
    when = _obs_datetime(obs_jd, tr)

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
        ps = exposure.plate_scale(cfg.get("pixel_um"), cfg.get("focal_mm"),
                                  cfg.get("pixel_binning"))
        scale = round(ps, 3) if ps else None

    def _f(x):
        # tolerant float-or-None for TAP values (some arrive as strings)
        try:
            return float(x) if x is not None else None
        except (TypeError, ValueError):
            return None

    def _mag(x):
        # The inits' "(+) / (-) Uncertainty" pair is a pair of magnitudes;
        # the archive reports the lower one negative (st_tefferr2 = -88) and
        # EXOTIC takes abs(uperr * lowerr) anyway, so store the magnitude.
        v = _f(x)
        return abs(v) if v is not None else None

    # Rp/Rs and a/Rs are ratios, so their uncertainty is propagated from the
    # two archive values (see _propagated_unc for the measured numbers).
    rprs = _ratio_rp_rs(d.get("pl_radj"), d.get("st_rad"))
    ars = _ratio_a_rs(d.get("pl_orbsmax"), d.get("st_rad"))
    rprs_unc = _propagated_unc(rprs, d.get("pl_radj"), d.get("pl_radjerr1"),
                               d.get("st_rad"), d.get("st_raderr1"))
    ars_unc = _propagated_unc(ars, d.get("pl_orbsmax"),
                              d.get("pl_orbsmaxerr1"),
                              d.get("st_rad"), d.get("st_raderr1"))

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
            # "Plate Solution? n" is deliberate (2026-09-30): "y" makes EXOTIC
            # upload the first frame to nova.astrometry.net and poll for a
            # solution BEFORE looking at the frame's own WCS. That public
            # queue cost ~4 min per run (tenacity: 10 tries per stage, waits
            # of 4 to 37 s) and failed more often than not: the run sat on
            # EXOTIC's "Thinking | ..." spinner and the observer read it as a
            # hang. With "n" EXOTIC uses the WCS already in the FITS header;
            # when the frame has none it aligns the frames with astroalign and
            # takes the image scale from IM_SCALE/PIXSCALE (or our
            # optional_info value) and the airmass from the target RA/Dec, so
            # the reduction still runs end to end, offline and at once.
            "Plate Solution? (y/n)": "y" if plate_solution else "n",
            "Add Comparison Stars from AAVSO? (y/n)": "y",
            "Target Star X & Y Pixel": None,
            "Comparison Star(s) X & Y Pixel": None,
            "Demosaic Format": None,
            "Demosaic Output": None,
        },
        "planetary_parameters": {
            # The uncertainties are filled on purpose (2026-09-30): EXOTIC
            # builds the window it fits the transit time in from them, and
            # with none it replaces them with 1 (exotic.py:1996-2002), which
            # makes the window so wide that the aperture/comparison search
            # cannot fit the time (measured on the HAT-P-32 b set: 3 distinct
            # tmid values in 3809 search fits with nulls against 1289 with
            # them, and the final T_mid went from +-0.0019 to +-0.0011 d,
            # 1 sigma to 0.5 sigma from the published value).
            "Target Star RA": _ra_hms(ra) if ra is not None else None,
            "Target Star Dec": _dec_dms(dec) if dec is not None else None,
            "Planet Name": name,
            "Host Star Name": host,
            "Orbital Period (days)": _f(d.get("pl_orbper")),
            "Orbital Period Uncertainty": _f(d.get("pl_orbpererr1")),
            "Published Mid-Transit Time (BJD-UTC)": _f(mid_bjd),
            "Mid-Transit Time Uncertainty": _f(d.get("pl_tranmiderr1")),
            "Ratio of Planet to Stellar Radius (Rp/Rs)": rprs,
            "Ratio of Planet to Stellar Radius (Rp/Rs) Uncertainty":
                rprs_unc,
            "Ratio of Distance to Stellar Radius (a/Rs)": ars,
            "Ratio of Distance to Stellar Radius (a/Rs) Uncertainty": ars_unc,
            "Orbital Inclination (deg)": _f(d.get("pl_orbincl")),
            "Orbital Inclination (deg) Uncertainty":
                _f(d.get("pl_orbinclerr1")),
            "Orbital Eccentricity (0 if null)": _f(d.get("pl_orbeccen")) or 0,
            # without it EXOTIC warns "omega is None" and models the transit
            # with omega = 0, which is wrong for an eccentric orbit (HAT-P-32 b
            # has e = 0.159 and omega = 50 deg in the archive)
            "Argument of Periastron (deg)": _f(d.get("pl_orblper")),
            "Star Effective Temperature (K)": _f(d.get("st_teff")),
            "Star Effective Temperature (+) Uncertainty":
                _f(d.get("st_tefferr1")),
            "Star Effective Temperature (-) Uncertainty":
                _mag(d.get("st_tefferr2")),
            "Star Metallicity ([FE/H])": _f(d.get("st_met",
                                                  d.get("st_metfe"))),
            "Star Metallicity (+) Uncertainty": _f(d.get("st_meterr1")),
            "Star Metallicity (-) Uncertainty": _mag(d.get("st_meterr2")),
            "Star Surface Gravity (log(g))": _f(d.get("st_logg")),
            "Star Surface Gravity (+) Uncertainty": _f(d.get("st_loggerr1")),
            "Star Surface Gravity (-) Uncertainty": _mag(d.get("st_loggerr2")),
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


def make_inits_for_visit(ctx, d, cfg, paths, target_xy, comps_xy,
                         plan=None, out_dir=None, pre_reduced=None,
                         plate_solution=False, obs_jd=None):
    # The inits.json for a project VISIT: it points EXOTIC at the visit's
    # frames and marks the target and comparison stars in pixels, so EXOTIC
    # runs without asking (verified 2026-09-27: see the orchestration plan).
    # @args: ctx, d, cfg, plan - as make_inits; paths - the visit's FITS
    #        paths; target_xy - (x, y) of the target; comps_xy - list of
    #        (x, y) comparisons; out_dir - plots folder (defaults to the
    #        frames' folder); pre_reduced - a pre-reduced curve path or None;
    #        plate_solution - ask astrometry.net (default False, see
    #        make_inits: the app hands the pixels over, so the public queue
    #        only adds minutes and failures); obs_jd - observation date
    #        (None: read it from the first frame)
    # @return: the inits dict
    folder = str(Path(paths[0]).parent) if paths else None
    if obs_jd is None and paths:
        obs_jd = frame_jd(paths[0])
    inits = make_inits(ctx, d, cfg, plan=plan,
                       out_dir=out_dir or folder,
                       plate_solution=plate_solution, obs_jd=obs_jd)
    ui = inits["user_info"]
    if folder:
        ui["Directory with FITS files"] = folder
        if out_dir is None:
            ui["Directory to Save Plots"] = folder
    # EXOTIC's own sample writes these as strings; keep that exact form
    ui["Target Star X & Y Pixel"] = str(
        [int(round(target_xy[0])), int(round(target_xy[1]))])
    comps = [[int(round(x)), int(round(y))] for x, y in (comps_xy or [])][:10]
    while len(comps) < 10:
        comps.append([])
    ui["Comparison Star(s) X & Y Pixel"] = str(comps)
    ui["Plate Solution? (y/n)"] = "y" if plate_solution else "n"
    # headless: the comparison stars are already given in pixels; asking
    # AAVSO makes EXOTIC crash when VSP returns HTML (plan phase 0)
    ui["Add Comparison Stars from AAVSO? (y/n)"] = "n"
    # the manual note of make_inits ("set the FITS folder yourself") is
    # wrong here: this inits already points at the visit's frames, so the
    # note only misleads. Say what is true instead.
    notes = (ui.get("Observing Notes") or "").replace(
        "Set 'Directory with FITS files' to your reduced frames folder"
        " before running EXOTIC.", "").strip()
    ui["Observing Notes"] = (notes + " Frames, target and comparisons are"
                             " set by NightScribe. No plate solution is"
                             " requested: EXOTIC uses the frame's own WCS.").strip()
    if pre_reduced:
        inits["optional_info"]["Pre-reduced File:"] = str(pre_reduced)
    return inits


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
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(inits, indent=4, ensure_ascii=False)
                         + "\n", encoding="utf-8")
    logger.info("EXOTIC inits written to %s", out)
    return str(out)
