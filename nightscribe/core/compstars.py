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

from . import coords, phototrans
from .sources import vizier

logger = logging.getLogger(__name__)

VSX_MATCH_ARCSEC = 5.0     # a catalog star this close to a VSX entry is
                           # considered the same object (SecFot's value)
DEFAULT_MARGIN = 0.5       # comps should beat the target by this much
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


def inside_field(ra, dec, center, field_deg):
    # @args: ra, dec - degrees, center - (ra, dec) degrees,
    #        field_deg - square side in degrees
    # @return: True when the point falls inside the square field
    dra = ra - center[0]
    if dra > 180.0:
        dra -= 360.0
    elif dra < -180.0:
        dra += 360.0
    x_deg = dra * math.cos(math.radians(center[1]))
    return (abs(x_deg) <= field_deg / 2.0
            and abs(dec - center[1]) <= field_deg / 2.0)


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

def build_stars(rows, center, field_deg, catalog):
    # Builds the sorted star list of a field from raw VizieR rows.
    # @args: rows - vizier.cone_search rows, center - (ra, dec) degrees,
    #        field_deg - square side in degrees, catalog - "gaia"|"apass"
    # @return: list of star dicts sorted by label-band magnitude
    spec = vizier.CATALOGS[catalog]
    describe = _DESCRIBERS[catalog]
    stars = []
    for row in rows:
        ra = _num(row.get(spec["ra"]))
        dec = _num(row.get(spec["dec"]))
        if ra is None or dec is None:
            continue
        if not inside_field(ra, dec, center, field_deg):
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
    # @args: stars - build_stars list (mutated: "vsx" set on a match),
    #        variables - build_variables list (mutated: "star" set)
    # @return: the variables list, each with "star"/"distance" filled
    for var in variables:
        nearest, best = None, float("inf")
        for star in stars:
            dist = separation_arcsec(var, star)
            if dist < best:
                nearest, best = star, dist
        var["star"] = nearest if best <= tol_arcsec else None
        var["distance_arcsec"] = best
        if var["star"] is not None:
            var["star"]["vsx"] = var
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


def load_field(catalog, ra_deg, dec_deg, fov_arcmin, max_rows=12000,
               force=False):
    # Full field around a target: catalog stars + VSX variables matched.
    # The query radius covers the field corners plus a small margin
    # (SecFot's fov*sqrt(1/2) + 0.8').
    # @args: catalog - "gaia"|"apass", ra_deg/dec_deg - target J2000,
    #        fov_arcmin - square field side, max_rows - row cap,
    #        force - bypass the cache read
    # @return: {"stars", "variables", "catalog", "center", "fov_arcmin",
    #          "vsx_warning"} or None when the catalog query failed
    center = (float(ra_deg), float(dec_deg))
    radius = fov_arcmin * math.sqrt(0.5) + 0.8
    res = vizier.cone_search(catalog, center[0], center[1], radius,
                             max_rows=max_rows, force=force)
    if res is None:
        return None
    stars = build_stars(res[1], center, fov_arcmin / 60.0, catalog)
    vsx_res = vizier.cone_search("vsx", center[0], center[1], radius,
                                 max_rows=4000, force=force)
    variables = []
    if vsx_res is not None:
        variables = build_variables(vsx_res[1], center,
                                    fov_arcmin / 60.0)
        match_vsx(stars, variables)
    return {"stars": stars, "variables": variables, "catalog": catalog,
            "center": center, "fov_arcmin": float(fov_arcmin),
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


def _why(star, target_mag, target_bv, min_margin, color_tol):
    # The plain-language reason a star is proposed, in the spirit of the
    # "why tonight" phrases: brightness, colour match, non-variability.
    # @return: {"es":..., "en":...} bilingual string pair
    parts_es, parts_en = [], []
    if star["mag"] <= target_mag - min_margin:
        parts_es.append("más brillante que el objetivo")
        parts_en.append("brighter than the target")
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


def propose_comps(stars, target_mag, target_bv=None, n=8, check=True,
                  min_margin=DEFAULT_MARGIN, color_tol=COLOR_TOL,
                  isolation_arcsec=ISOLATION_ARCSEC, spread_arcmin=0.0):
    # Proposes a photometric sequence automatically. Criteria, in order:
    # not a known VSX variable, isolated in the catalog, ideally brighter
    # than the target by min_margin and of similar colour (|ΔB−V| within
    # color_tol when both are known); when the strict pool runs short the
    # brightness margin relaxes so the sequence never comes back empty.
    # Picked comps keep a spread_arcmin minimum mutual separation so the
    # sequence covers the field.
    # @args: stars - build_stars list, target_mag - target magnitude in
    #        the label band, target_bv - target B−V or None, n - comps,
    #        check - also pick one check star, spread_arcmin - minimum
    #        separation between comps (0 disables)
    # @return: {"comps": [{"name", "kind", "star", "why"}...],
    #          "check": entry or None}
    pool = [s for s in stars
            if s.get("vsx") is None
            and _is_isolated(s, stars, isolation_arcsec)]

    def color_rank(s):
        # @return: (colour outside tolerance?, |ΔB−V| or worst-case)
        if target_bv is None or s.get("bv") is None:
            return 0, 99.0
        delta = abs(s["bv"] - target_bv)
        return (delta > color_tol), delta

    def entry(s, name, kind):
        return {"name": name, "kind": kind, "star": s,
                "why": _why(s, target_mag, target_bv, min_margin,
                            color_tol)}

    picked = []
    strict = [s for s in pool if s["mag"] <= target_mag - min_margin]
    strict.sort(key=lambda s: (color_rank(s), s["mag"]))
    relaxed = [s for s in pool if target_mag - min_margin < s["mag"]]
    relaxed.sort(key=lambda s: (color_rank(s), s["mag"]))
    for cand in strict + relaxed:
        if len(picked) >= n:
            break
        if spread_arcmin > 0.0 and any(
                separation_arcsec(cand, p["star"]) < spread_arcmin * 60.0
                for p in picked):
            continue
        picked.append(entry(cand, f"Comp{len(picked) + 1}", "comp"))
    check_entry = None
    if check:
        for cand in strict + relaxed:
            if all(p["star"] is not cand for p in picked):
                check_entry = entry(cand, "Check", "check")
                break
    return {"comps": picked, "check": check_entry}


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
