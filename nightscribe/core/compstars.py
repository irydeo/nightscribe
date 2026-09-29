############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Comparison stars and photometric sequences module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Comparison-star field model and photometric sequence builder (ADR-042).

Answers the observer's first photometry question: "with what do I
compare?". A field is the list of catalog stars around the target with
their photometry normalised (Gaia EDR3 or APASS DR9 via core/sources/
vizier.py), cross-matched against AAVSO VSX so a known variable is never
proposed as a comparison star. propose_comps() suggests a sequence with
photometric criteria (brightness, similar colour, isolated, spread across
the field) and a plain-language reason per star, in the spirit of the
"why tonight" phrases of core/suggest.py. export_sequence_csv() writes
the sequence table.

Field building and VSX cross-match are ported from SecFot (González
Farfán & González Carballo 2026).
"""

import csv
import logging
import math
from pathlib import Path

import numpy as np

from . import coords, photometry, phototrans
from .sources import vizier

logger = logging.getLogger(__name__)

VSX_MATCH_ARCSEC = 5.0     # a catalog star this close to a VSX entry is
                           # considered the same object (SecFot's value)
DEFAULT_MARGIN = 0.5       # comps should beat the target by this much
# A comp needs this much clear around it at the field edges (arcsec): the
# drift of a night moves the field across the sky, so a star at the very
# edge is a star you will lose (quality plan, C2).
COMP_MARGIN_ARCSEC = 90.0
# The peak of a comp must clear the sky noise by this many sigmas for the
# centroid (and the photometry) to mean anything (C1).
MIN_COMP_PEAK_SNR = 12.0
# And the flux in the aperture must be this many times its own noise:
# below it, the comp is noise with a catalogue value attached.
MIN_COMP_FLUX_SNR = 30.0
BRIGHT_WINDOW = 2.0        # ...but by not much more than this: a comp
                           # many magnitudes brighter saturates real
                           # plates and calibrates nothing
COLOR_TOL = 0.4            # preferred |B-V difference| against the target
ISOLATION_ARCSEC = 10.0    # no catalog neighbour closer than this


# --------------------------- geometry ---------------------------

def separation_arcsec(first, second):
    # Great-circle separation between two (ra, dec) points.
    # @args: first, second - dicts or tuples with ra/dec in degrees
    # @return: separation in arcseconds
    ra1, dec1 = first["ra"], first["dec"]
    ra2, dec2 = second["ra"], second["dec"]
    dra = math.radians(ra1 - ra2)
    if dra > math.pi:
        dra -= 2 * math.pi
    elif dra < -math.pi:
        dra += 2 * math.pi
    cos_d = (math.sin(math.radians(dec1)) * math.sin(math.radians(dec2))
             + math.cos(math.radians(dec1)) * math.cos(math.radians(dec2))
             * math.cos(dra))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_d)))) * 3600.0


def inside_field(ra, dec, center, field_deg, field_dec_deg=None):
    # @args: ra, dec - degrees, center - (ra, dec) degrees,
    #        field_deg - square side in degrees (RA axis),
    #        field_dec_deg - the declination side when the sensor is NOT
    #        square (quality plan, C2): a 1663 x 1252 camera sees 43' x 32',
    #        and treating that as a 43' square proposes stars the sensor
    #        never shows
    # @return: True when the point falls inside the field
    dra = ra - center[0]
    height = field_dec_deg if field_dec_deg else field_deg
    if dra > 180.0:
        dra -= 360.0
    elif dra < -180.0:
        dra += 360.0
    x_deg = dra * math.cos(math.radians(center[1]))
    return (abs(x_deg) <= field_deg / 2.0
            and abs(dec - center[1]) <= height / 2.0)


def field_sides_deg(fov_arcmin, naxis1=None, naxis2=None):
    # The REAL rectangle of the sensor (quality plan, C2): with the frame
    # size in pixels and the field's long side, the short side follows the
    # pixel ratio. A square camera (or no frame size) keeps the old square.
    # @args: fov_arcmin - the field's long side in arcmin (the panel's
    #        FOV), naxis1/naxis2 - the frame size in pixels
    # @return: (ra_side_deg, dec_side_deg)
    long_deg = float(fov_arcmin) / 60.0
    if not naxis1 or not naxis2:
        return long_deg, long_deg
    if naxis1 >= naxis2:
        return long_deg, long_deg * float(naxis2) / float(naxis1)
    return long_deg * float(naxis1) / float(naxis2), long_deg


# --------------------------- band reading ---------------------------

def _num(value, zero_is_missing=False):
    # @return: float of a VizieR cell, or None when blank/non-numeric/zero
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).replace(",", "."))
    except ValueError:
        return None
    if zero_is_missing and number == 0.0:
        return None
    return number


def _band(row, label, keys, zero_is_missing=False):
    # Reads one band trying every known column alias, with its error.
    # @args: row - vizier row dict, label - display label, keys - column
    #        names in preference order
    # @return: {"label", "value", "err", "derived"} (value None when the
    #          band is absent)
    for key in keys:
        if key not in row:
            continue
        value = _num(row[key], zero_is_missing)
        if value is None:
            continue
        err = None
        for err_key in (f"e_{key}", f"d{key}"):
            if err_key in row:
                err = _num(row[err_key])
                if err is not None:
                    break
        return {"label": label, "value": value, "err": err,
                "derived": False}
    return {"label": label, "value": None, "err": None, "derived": False}


def _color_item(label, first, second):
    # @return: a band dict for a colour index (first - second)
    ok = first["value"] is not None and second["value"] is not None
    return {"label": label,
            "value": (first["value"] - second["value"]) if ok else None,
            "err": phototrans.combine_err(first["err"], second["err"])
            if ok else None,
            "derived": False}


def _derived(label, value):
    # @return: a band dict flagged as estimated (the "≈" of the UI)
    return {"label": label,
            "value": value if value is not None else None,
            "err": None, "derived": True}


def describe_gaia(row):
    # Normalises a Gaia EDR3 row: native bands plus the Johnson-Cousins
    # estimates from BP-RP (phototrans.gaia_to_johnson).
    # @return: (bands list, bv or None, color_origin) with color_origin
    #          "estimated" | None
    g = _band(row, "G", ("Gmag",))
    bp = _band(row, "BP", ("BPmag",))
    rp = _band(row, "RP", ("RPmag",))
    bp_rp = _color_item("BP-RP", bp, rp)
    jc = None
    if g["value"] is not None and bp_rp["value"] is not None:
        jc = phototrans.gaia_to_johnson(g["value"], bp_rp["value"])
    bands = [g, bp, rp, bp_rp]
    bv = None
    if jc:
        bv = jc["B"] - jc["V"]
        bands += [_derived("B", jc["B"]), _derived("V", jc["V"]),
                  _derived("Rc", jc.get("R")), _derived("Ic", jc.get("I")),
                  _derived("B-V", bv)]
    return bands, bv, "estimated" if bv is not None else None


def describe_apass(row):
    # Normalises an APASS DR9 row: direct Johnson B,V and Sloan bands.
    # @return: (bands list, bv or None, color_origin) with color_origin
    #          "direct" | None
    b = _band(row, "B", ("Bmag",))
    v = _band(row, "V", ("Vmag",))
    g = _band(row, "g'", vizier.APASS_G)
    r = _band(row, "r'", vizier.APASS_R)
    i = _band(row, "i'", vizier.APASS_I)
    bv = _color_item("B-V", b, v)
    bands = [b, v, bv, g, r, i, _color_item("g'-r'", g, r)]
    return bands, bv["value"], "direct" if bv["value"] is not None else None


_DESCRIBERS = {"gaia": describe_gaia, "apass": describe_apass}


# --------------------------- field building ---------------------------

def build_stars(rows, center, field_deg, catalog, field_dec_deg=None):
    # Builds the sorted star list of a field from raw VizieR rows.
    # @args: rows - vizier.cone_search rows, center - (ra, dec) degrees,
    #        field_deg - the RA side in degrees, catalog - "gaia"|"apass",
    #        field_dec_deg - the declination side when it differs
    # @return: list of star dicts sorted by label-band magnitude
    spec = vizier.CATALOGS[catalog]
    describe = _DESCRIBERS[catalog]
    stars = []
    for row in rows:
        ra = _num(row.get(spec["ra"]))
        dec = _num(row.get(spec["dec"]))
        if ra is None or dec is None:
            continue
        if not inside_field(ra, dec, center, field_deg, field_dec_deg):
            continue
        mag = _num(row.get(spec["mag"]))
        if mag is None:
            continue
        bands, bv, origin = describe(row)
        raw_id = (row.get(spec["id"]) or "").strip()
        stars.append({
            "id": raw_id or _jname(ra, dec), "name": None,
            "ra": ra, "dec": dec, "mag": mag, "band": spec["band"],
            "catalog": spec["name"], "bands": bands, "bv": bv,
            "color_origin": origin, "vsx": None,
        })
    stars.sort(key=lambda s: s["mag"])
    return stars


def build_variables(rows, center, field_deg):
    # The VSX entries inside the field, as plain dicts.
    # @args: rows - vizier.cone_search("vsx") rows
    # @return: list of {name, type, period_d, ra, dec} dicts
    variables = []
    for i, row in enumerate(rows):
        ra = _num(row.get("RAJ2000"))
        dec = _num(row.get("DEJ2000"))
        if ra is None or dec is None:
            continue
        if not inside_field(ra, dec, center, field_deg):
            continue
        variables.append({
            "oid": (row.get("OID") or "").strip() or f"VSX-{i}",
            "name": (row.get("Name") or "").strip() or "Variable",
            "type": (row.get("Type") or "").strip(),
            "period_d": _num(row.get("Period")),
            "ra": ra, "dec": dec,
        })
    return variables


def match_vsx(stars, variables, tol_arcsec=VSX_MATCH_ARCSEC):
    # Cross-matches VSX variables with catalog stars: a star within
    # tol_arcsec of a variable IS that variable, and can never be a comp.
    # The link is one-way on purpose: the star carries the full VSX dict
    # ("this star is V0001 Cyg") while the variable keeps only a light
    # counterpart snapshot {id, ra, dec, mag} — never the star itself. A
    # var<->star reference cycle recursed forever inside QVariant when the
    # field crossed a Signal(dict) emission and blew the C stack (SIGSEGV
    # at the follow-up's "Generate"); acyclic also keeps the field
    # JSON-serialisable.
    # @args: stars - build_stars list (mutated: "vsx" set on a match),
    #        variables - build_variables list (mutated: "star" snapshot)
    # @return: the variables list, each with "star"/"distance" filled
    for var in variables:
        nearest, best = None, float("inf")
        for star in stars:
            dist = separation_arcsec(var, star)
            if dist < best:
                nearest, best = star, dist
        if nearest is not None and best <= tol_arcsec:
            var["star"] = {"id": nearest["id"], "ra": nearest["ra"],
                           "dec": nearest["dec"], "mag": nearest["mag"]}
            nearest["vsx"] = var
        else:
            var["star"] = None
        var["distance_arcsec"] = best
    return variables


def _jname(ra, dec):
    # IAU-style positional name for sources without identifier,
    # e.g. J192527.90+424703.0 (SecFot's convention).
    # @return: the "Jhhmmss.ss±ddmmss.s" string
    total_ra = round(((ra % 360.0) / 15.0) * 3600.0 * 100.0) / 100.0
    h = int(total_ra // 3600)
    m = int((total_ra - h * 3600) // 60)
    s = total_ra - h * 3600 - m * 60
    total_dec = round(abs(dec) * 3600.0 * 10.0) / 10.0
    d = int(total_dec // 3600)
    dm = int((total_dec - d * 3600) // 60)
    ds = total_dec - d * 3600 - dm * 60
    return (f"J{h:02d}{m:02d}{s:05.2f}"
            f"{'-' if dec < 0 else '+'}{d:02d}{dm:02d}{ds:04.1f}")


def _stage(progress, es, en):
    # Reports a pipeline stage to the caller (GUI status line / CLI).
    if progress:
        progress({"es": es, "en": en})


def load_field(catalog, ra_deg, dec_deg, fov_arcmin, max_rows=12000,
               force=False, progress=None, naxis=None, margin_arcsec=0.0):
    # Full field around a target: catalog stars + VSX variables matched.
    # The query radius covers the field corners plus a small margin
    # (SecFot's fov*sqrt(1/2) + 0.8').
    # @args: catalog - "gaia"|"apass", ra_deg/dec_deg - target J2000,
    #        fov_arcmin - the field's LONG side in arcmin, max_rows - row
    #        cap, force - bypass the cache read, progress - optional stage
    #        callback, naxis - the frame size (naxis1, naxis2) in pixels so
    #        the field is the REAL sensor rectangle and not a square (C2),
    #        margin_arcsec - a safety ring shrunk from every side (the
    #        drift of a night, a dithering) that no comp may sit in
    # @return: {"stars", "variables", "catalog", "center", "fov_arcmin",
    #          "sides_deg", "vsx_warning"} or None when the query failed
    center = (float(ra_deg), float(dec_deg))
    radius = fov_arcmin * math.sqrt(0.5) + 0.8
    name = vizier.CATALOGS[catalog]["name"]
    _stage(progress, f"Consultando el catálogo {name}…",
           f"Querying the {name} catalog…")
    res = vizier.cone_search(catalog, center[0], center[1], radius,
                             max_rows=max_rows, force=force)
    if res is None:
        return None
    naxis1, naxis2 = (naxis or (None, None))
    ra_side, dec_side = field_sides_deg(fov_arcmin, naxis1, naxis2)
    # the safety ring: shrink BOTH sides (a drift moves the field, and the
    # original 43' square already proposed stars the sensor never saw)
    shrink = 2.0 * float(margin_arcsec or 0.0) / 3600.0
    ra_side = max(ra_side - shrink, ra_side * 0.2)
    dec_side = max(dec_side - shrink, dec_side * 0.2)
    stars = build_stars(res[1], center, ra_side, catalog,
                        field_dec_deg=dec_side)
    _stage(progress, "Comprobando variables conocidas (VSX)…",
           "Checking known variables (VSX)…")
    vsx_res = vizier.cone_search("vsx", center[0], center[1], radius,
                                 max_rows=4000, force=force)
    variables = []
    if vsx_res is not None:
        variables = build_variables(vsx_res[1], center, ra_side)
        match_vsx(stars, variables)
    return {"stars": stars, "variables": variables, "catalog": catalog,
            "catalog_name": vizier.CATALOGS[catalog]["name"],
            "band": vizier.CATALOGS[catalog]["band"],
            "center": center, "fov_arcmin": float(fov_arcmin),
            "sides_deg": (ra_side, dec_side),
            "vsx_warning": vsx_res is None}


# --------------------------- sequence proposal ---------------------------

def _is_isolated(star, stars, tol_arcsec):
    # @return: True when no other catalog star sits within tol_arcsec
    for other in stars:
        if other is star:
            continue
        if separation_arcsec(star, other) < tol_arcsec:
            return False
    return True


def _why(star, target_mag, target_bv, min_margin, color_tol,
         bright_window=BRIGHT_WINDOW):
    # The plain-language reason a star is proposed, in the spirit of the
    # "why tonight" phrases: brightness, colour match, non-variability.
    # @return: {"es":..., "en":...} bilingual string pair
    parts_es, parts_en = [], []
    if star["mag"] <= target_mag - min_margin - bright_window:
        parts_es.append("mucho más brillante que el objetivo (riesgo "
                        "de saturación en exposiciones cortas)")
        parts_en.append("much brighter than the target (saturation "
                        "risk on short exposures)")
    elif star["mag"] <= target_mag - min_margin:
        parts_es.append("más brillante que el objetivo y de brillo "
                        "cercano")
        parts_en.append("brighter than the target and close in "
                        "brightness")
    elif star["mag"] <= target_mag:
        parts_es.append("brillo parecido al del objetivo")
        parts_en.append("similar brightness to the target")
    else:
        parts_es.append("más débil que el objetivo")
        parts_en.append("fainter than the target")
    if target_bv is not None and star.get("bv") is not None:
        delta = abs(star["bv"] - target_bv)
        if delta <= color_tol:
            parts_es.append(f"color parecido (B−V {star['bv']:.2f})")
            parts_en.append(f"similar colour (B−V {star['bv']:.2f})")
        else:
            parts_es.append(f"color distinto (B−V {star['bv']:.2f})")
            parts_en.append(f"different colour (B−V {star['bv']:.2f})")
    else:
        parts_es.append("sin dato de color")
        parts_en.append("no colour data")
    parts_es.append("no es variable conocida")
    parts_en.append("not a known variable")
    return {"es": " · ".join(parts_es), "en": " · ".join(parts_en)}


def local_sky_sigma(plate, x, y, r_ap):
    # The local sky noise around a point, from pixel-to-pixel differences
    # (a smooth gradient barely moves it): the same recipe the series
    # engine uses, kept here so validating a candidate touches only its
    # own cutout and not the whole frame.
    # @args: plate - 2D ADU array, x/y - the star, r_ap - aperture radius
    # @return: sigma in ADU, or None when the cutout is too small
    h, w = plate.shape
    x0 = max(0, int(x - r_ap - 6))
    x1 = min(w, int(x + r_ap + 7))
    y0 = max(0, int(y - r_ap - 6))
    y1 = min(h, int(y + r_ap + 7))
    sub = np.asarray(plate[y0:y1, x0:x1], dtype=np.float64)
    if sub.size < 16:
        return None
    diffs = np.concatenate([np.diff(sub, axis=1).ravel(),
                            np.diff(sub, axis=0).ravel()])
    return 1.4826 * float(np.median(np.abs(diffs - np.median(diffs)))) \
        / math.sqrt(2.0)


def validate_on_plate(star, plate, wcs, radii=None, sat_adu=None,
                      linear_adu=None, gain=None, ron=None, shape=None,
                      margin_px=0.0):
    # Measures ONE candidate on the observer's own plate and says whether
    # it is usable (quality plan, C1). The catalogue cannot know this: it
    # does not see a saturated core, a sensor that stops being linear at
    # 53 000 ADU, a star sitting outside the frame, or one so faint that
    # its flux is noise.
    #
    # The 4 of 9 saturated and 1 off-sensor comps of the real V0526 Per
    # sequence are exactly what this returns.
    #
    # @args: star - {"ra", "dec"}, plate - the 2D ADU array, wcs - the
    #        plate's Wcs, radii - the aperture triple, sat_adu - the
    #        detector ceiling in ADU, linear_adu - the linearity limit,
    #        gain/ron - e-/ADU and e- (a real SNR when known, a proxy when
    #        not), shape - the frame's (h, w), margin_px - the ring kept
    #        clear at the edges
    # @return: None when the star is fine, else {"key", "es", "en"}
    if plate is None or wcs is None:
        return None
    try:
        x, y = wcs.sky_to_pixel(star["ra"], star["dec"])
    except Exception:
        return {"key": "off", "es": "no se puede situar en la placa",
                "en": "it cannot be placed on the plate"}
    h, w = shape if shape else plate.shape
    m = float(margin_px or 0.0)
    if not (m <= x <= w - 1 - m and m <= y <= h - 1 - m):
        return {"key": "outside",
                "es": "fuera del sensor (con el margen de seguridad)",
                "en": "outside the sensor (with the safety margin)"}
    r_ap, r_in, r_out = radii or (photometry.R_AP, photometry.R_ANN_IN,
                                  photometry.R_ANN_OUT)
    if x - r_out < 0 or x + r_out > w - 1 or y - r_out < 0 \
            or y + r_out > h - 1:
        return {"key": "edge",
                "es": "el anillo de cielo se sale del marco",
                "en": "its sky annulus falls off the frame"}
    r = photometry.measure_point(plate, x, y, r_ap=r_ap, r_ann_in=r_in,
                                 r_ann_out=r_out, sat_adu=None)
    if not r.get("ok"):
        return {"key": "unmeasurable",
                "es": "no se puede medir en esta placa",
                "en": "it cannot be measured on this plate"}
    peak = r.get("peak")
    if sat_adu and peak is not None and peak >= float(sat_adu):
        return {"key": "saturated",
                "es": "satura ({0:.0f} de {1:.0f} ADU)".format(
                    peak, float(sat_adu)),
                "en": "saturated ({0:.0f} of {1:.0f} ADU)".format(
                    peak, float(sat_adu))}
    if linear_adu and peak is not None and peak >= float(linear_adu):
        return {"key": "nonlinear",
                "es": "por encima de la linealidad ({0:.0f} de {1:.0f} "
                      "ADU)".format(peak, float(linear_adu)),
                "en": "above the linearity limit ({0:.0f} of {1:.0f} "
                      "ADU)".format(peak, float(linear_adu))}
    sky_pp = r.get("sky_pp")
    noise = local_sky_sigma(plate, x, y, r_ap)
    if noise and peak is not None and sky_pp is not None:
        snr_peak = (float(peak) - float(sky_pp)) / noise
        if snr_peak < MIN_COMP_PEAK_SNR:
            return {"key": "faint",
                    "es": "demasiado débil: el pico es {0:.1f}× el ruido "
                          "del cielo".format(snr_peak),
                    "en": "too faint: its peak is {0:.1f}x the sky "
                          "noise".format(snr_peak)}
    flux = r.get("flux")
    if flux is not None and flux > 0 and noise:
        n = max(1, int(r.get("n_pix") or 1))
        n_sky = max(1, int(r.get("n_sky") or 1))
        var = n * noise ** 2 * (1.0 + n / float(n_sky))
        if gain and ron is not None:
            var += float(sky_pp or 0.0) * n / float(gain)
            var += n * (float(ron) ** 2) / (float(gain) ** 2)
        snr_flux = float(flux) / math.sqrt(max(var, 1e-9))
        if snr_flux < MIN_COMP_FLUX_SNR:
            return {"key": "faint",
                    "es": "SNR {0:.0f} en la apertura: no calibra".format(
                        snr_flux),
                    "en": "SNR {0:.0f} in the aperture: it does not "
                          "calibrate".format(snr_flux)}
    return None


def propose_comps(stars, target_mag, target_bv=None, n=8, check=True,
                  min_margin=DEFAULT_MARGIN, color_tol=COLOR_TOL,
                  isolation_arcsec=ISOLATION_ARCSEC, spread_arcmin=0.0,
                  bright_window=BRIGHT_WINDOW, validator=None,
                  margin_arcsec=0.0):
    # Proposes a photometric sequence automatically. Criteria, in order:
    # not a known VSX variable, isolated in the catalog, brighter than
    # the target by min_margin but CLOSE to it (a comp much brighter than
    # the target saturates real plates and calibrates nothing — the
    # bright_window), and of similar colour (|ΔB−V| within color_tol when
    # both are known). When the windowed pool runs short the brightness
    # rules relax in tiers so the sequence never comes back empty.
    # Picked comps keep a spread_arcmin minimum mutual separation so the
    # sequence covers the field.
    #
    # Quality plan, C1: the catalogue alone cannot know whether a star
    # saturates, sits below the camera's linearity or falls outside the
    # real sensor. A `validator` is the observer's own plate saying so:
    # it is called per candidate with (star, role) and returns None (fine)
    # or {"key", "es", "en"} with the reason it is not usable. The core
    # stays free of Qt and of the plate; the caller owns the measuring.
    # @args: stars - build_stars list, target_mag - target magnitude in
    #        the label band, target_bv - target B−V or None, n - comps,
    #        check - also pick one check star, spread_arcmin - minimum
    #        separation between comps (0 disables), bright_window - how
    #        far brighter than (target - min_margin) a comp may sit and
    #        still be a first-class choice, validator - optional callable
    #        (star, role) -> None | {"key","es","en"}, margin_arcsec - a
    #        safety ring kept clear on every side (drift, dithering)
    # @return: {"comps": [{"name", "kind", "star", "why"}...],
    #          "check": entry or None, "rejected": [{name, key, es, en}]}
    pool = [s for s in stars
            if s.get("vsx") is None
            and _is_isolated(s, stars, isolation_arcsec)]
    rejected = []
    if validator is not None:
        kept = []
        for s in pool:
            verdict = validator(s, "comp")
            if verdict is None:
                kept.append(s)
            else:
                rejected.append({"name": s.get("name") or s.get("id"),
                                 "key": verdict.get("key"),
                                 "es": verdict.get("es"),
                                 "en": verdict.get("en")})
        pool = kept

    def color_rank(s):
        # @return: (colour outside tolerance?, |ΔB−V| or worst-case)
        if target_bv is None or s.get("bv") is None:
            return 0, 99.0
        delta = abs(s["bv"] - target_bv)
        return (delta > color_tol), delta

    def entry(s, name, kind):
        return {"name": name, "kind": kind, "star": s,
                "why": _why(s, target_mag, target_bv, min_margin,
                            color_tol, bright_window)}

    # Brightness tiers around the anchor (the dimmest a comp needs to
    # be): close-and-brighter first, then close-but-faint, then the
    # too-bright rest (last: they are the saturation risk). Every tier
    # sorts by colour match, then by closeness to the anchor.
    anchor = target_mag - min_margin

    def close(s):
        # @return: |mag - anchor|, the closeness ordering
        return abs(s["mag"] - anchor)

    near = sorted((s for s in pool
                   if anchor - bright_window <= s["mag"] <= anchor),
                  key=lambda s: (color_rank(s), close(s)))
    fainter = sorted((s for s in pool if s["mag"] > anchor),
                     key=lambda s: (color_rank(s), close(s)))
    brighter = sorted((s for s in pool if s["mag"] < anchor
                       - bright_window),
                      key=lambda s: (color_rank(s), close(s)))
    ordered = near + fainter + brighter
    picked = []
    for cand in ordered:
        if len(picked) >= n:
            break
        if spread_arcmin > 0.0 and any(
                separation_arcsec(cand, p["star"]) < spread_arcmin * 60.0
                for p in picked):
            continue
        picked.append(entry(cand, f"Comp{len(picked) + 1}", "comp"))
    check_entry = None
    if check:
        for cand in ordered:
            if all(p["star"] is not cand for p in picked):
                if validator is not None:
                    verdict = validator(cand, "check")
                    if verdict is not None:
                        rejected.append({"name": cand.get("name")
                                         or cand.get("id"),
                                         "key": verdict.get("key"),
                                         "es": verdict.get("es"),
                                         "en": verdict.get("en")})
                        continue
                check_entry = entry(cand, "Check", "check")
                break
    return {"comps": picked, "check": check_entry, "rejected": rejected}


# --------------------------- CSV export ---------------------------

CSV_FIXED = ("Name", "Type", "RA (h m s)", "Dec (d m s)", "RA (deg)",
             "Dec (deg)", "Catalog", "Identifier")


def _band_columns(entries):
    # @return: ordered union of the band labels present in the entries,
    #          derived ones marked " (est.)"
    labels = []
    for e in entries:
        for item in e["star"]["bands"]:
            key = item["label"] + (" (est.)" if item["derived"] else "")
            if key not in labels:
                labels.append(key)
    return labels


def export_sequence_csv(entries, out, target_name="", catalog_label=""):
    # The sequence table: one row per star, fixed identification columns
    # plus every photometric band present (derived columns marked).
    # @args: entries - propose_comps-style [{"name","kind","star"}] list,
    #        out - output path, target_name - for the header comment,
    #        catalog_label - for the header comment
    # @return: the output Path
    columns = _band_columns(entries)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        fh.write(f"# target: {target_name}\n"
                 f"# catalog: {catalog_label}\n"
                 f"# generated by NightScribe\n")
        writer = csv.writer(fh)
        writer.writerow(CSV_FIXED + tuple(columns))
        for e in entries:
            star = e["star"]
            values = {}
            for item in star["bands"]:
                key = item["label"] + (" (est.)" if item["derived"] else "")
                values[key] = ("" if item["value"] is None else
                               f"{item['value']:.2f}" if item["derived"]
                               else f"{item['value']:.3f}")
            writer.writerow([
                e["name"], "Check" if e["kind"] == "check" else "Comparison",
                coords.ra_deg_to_hms(star["ra"]),
                coords.dec_deg_to_dms(star["dec"]),
                f"{star['ra']:.6f}", f"{star['dec']:+.6f}",
                star["catalog"], star["id"],
                *[values.get(c, "") for c in columns]])
    logger.info("sequence CSV written: %s (%d stars)", out, len(entries))
    return Path(out)
