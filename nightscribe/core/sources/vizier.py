############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - VizieR catalog cone-search source module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""VizieR cone searches (CDS `asu-tsv` service) for photometric catalogs.

One entry point: cone_search(catalog_key, ra, dec, radius) against the
catalog specs below (Gaia EDR3, APASS DR9, AAVSO VSX). Rows come back as
raw string dicts; interpreting the photometry is core/phototrans.py and
core/compstars.py business. All traffic goes through the db cache (TTL
30 days, "vizier") and a network failure returns None, never an exception,
so the caller can tell "source down" apart from "empty field".

The parser follows the tolerant approach of SecFot (González Farfán &
González Carballo 2026): the explicit field list is requested first, and
when a probed column is missing from the answer the query is repeated with
-out.all, so a renamed VizieR column does not break anything.
"""

import logging

import requests

from ..db import db

logger = logging.getLogger(__name__)

VIZIER_URL = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
TIMEOUT_S = 55

# APASS Sloan column names have a history of changing shape ("g'mag" vs
# "gmag"); every band lists its known aliases so the probe can check them.
APASS_G = ("g'mag", "g′mag", "gmag", "g_mag")
APASS_R = ("r'mag", "r′mag", "rmag", "r_mag")
APASS_I = ("i'mag", "i′mag", "imag", "i_mag")

VSX_FIELDS = ("OID", "Name", "RAJ2000", "DEJ2000", "Type", "l_max", "max",
              "u_max", "n_max", "f_min", "min", "u_min", "n_min", "Epoch",
              "Period", "Sp")

CATALOGS = {
    "gaia": {
        "name": "Gaia EDR3", "source": "I/350/gaiaedr3", "band": "G",
        "ra": "RAJ2000", "dec": "DEJ2000", "mag": "Gmag", "id": "Source",
        "required": "Gmag", "sort": "Gmag",
        "fields": ("Source", "RAJ2000", "DEJ2000", "Gmag", "e_Gmag",
                   "BPmag", "e_BPmag", "RPmag", "e_RPmag"),
        "probe": (("Gmag",), ("BPmag",), ("RPmag",)),
    },
    "apass": {
        "name": "APASS DR9", "source": "II/336/apass9", "band": "V",
        "ra": "RAJ2000", "dec": "DEJ2000", "mag": "Vmag", "id": "recno",
        "required": "Vmag", "sort": "Vmag",
        "fields": ("recno", "RAJ2000", "DEJ2000", "Vmag", "e_Vmag", "Bmag",
                   "e_Bmag", "g'mag", "e_g'mag", "r'mag", "e_r'mag",
                   "i'mag", "e_i'mag"),
        "probe": (("Vmag",), ("Bmag",), APASS_G, APASS_R, APASS_I),
    },
    "vsx": {
        "name": "AAVSO VSX", "source": "B/vsx/vsx", "band": "max",
        "ra": "RAJ2000", "dec": "DEJ2000", "mag": "max", "id": "Name",
        "required": "Name", "sort": "_r",
        "fields": VSX_FIELDS,
        "probe": (("max",), ("min",), ("Type",), ("Period",)),
        "variable_catalog": True,
    },
}


def _catalog_url(spec, ra, dec, radius_arcmin, fields, max_rows):
    # @args: spec - CATALOGS entry, ra/dec - degrees J2000, fields - tuple
    #        of column names or the string "all", max_rows - row cap
    # @return: the asu-tsv query URL
    params = [
        ("-source", spec["source"]),
        ("-c", f"{ra} {dec}"),
        ("-c.eq", "J2000"),
        ("-c.r", f"{radius_arcmin}"),
        ("-c.u", "arcmin"),
        ("-out.max", str(max_rows)),
    ]
    if spec.get("sort"):
        params.append(("-sort", spec["sort"]))
    if fields == "all":
        params.append(("-out.all", "1"))
    else:
        params.append(("-out", ",".join(fields)))
    return VIZIER_URL + "?" + "&".join(
        f"{k}={requests.utils.quote(str(v))}" for k, v in params)


def parse_tsv(text, required_column, ra_column="RAJ2000",
              dec_column="DEJ2000"):
    # Tolerant asu-tsv parser: comments start with '#', the header is the
    # first line carrying the required column, and rows without numeric
    # coordinates are dropped (VizieR pads answers with blank lines and
    # metadata blocks).
    # @args: text - raw TSV answer, required_column - marks the header,
    #        ra_column/dec_column - coordinate columns that must be numeric
    # @return: (headers list, rows list of column->value dicts)
    lines = [ln for ln in text.splitlines()
             if ln.strip() and not ln.startswith("#")]
    header_index = None
    for i, line in enumerate(lines):
        if required_column in [c.strip() for c in line.split("\t")]:
            header_index = i
            break
    if header_index is None:
        return [], []
    headers = [c.strip() for c in lines[header_index].split("\t")]
    rows = []
    for line in lines[header_index + 1:]:
        values = line.split("\t")
        row = {h: (values[j].strip() if j < len(values) else "")
               for j, h in enumerate(headers)}
        try:
            float(row[ra_column])
            float(row[dec_column])
        except (TypeError, ValueError, KeyError):
            continue
        rows.append(row)
    return headers, rows


def _coverage(headers, probe):
    # @return: how many probe groups have at least one alias in the headers
    return sum(1 for aliases in probe
               if any(name in headers for name in aliases))


def _fetch(url, label):
    # @return: (body bytes, content_type); raises RequestException
    r = requests.get(url, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.content, "text/tab-separated-values"


def cone_search(catalog, ra_deg, dec_deg, radius_arcmin, max_rows=12000,
                force=False):
    # Cone search against one of the CATALOGS specs, through the db cache.
    # The explicit field list is asked first; when a probed column is
    # missing the query is repeated with -out.all and the richer answer
    # wins (SecFot's safeguard against renamed columns).
    # @args: catalog - "gaia"|"apass"|"vsx", ra_deg/dec_deg - J2000
    #        degrees, radius_arcmin - search radius, max_rows - row cap,
    #        force - bypass the cache read
    # @return: (headers, rows) on success (rows may be empty), or None
    #          when VizieR could not be reached / answered an error
    spec = CATALOGS.get(catalog)
    if spec is None:
        logger.warning("unknown VizieR catalog: %s", catalog)
        return None
    ra, dec = float(ra_deg), float(dec_deg)
    key_base = (f"vizier:{spec['source']}:{ra:.4f}:{dec:.4f}"
                f":{float(radius_arcmin):.2f}")

    def fetch_fields():
        return _fetch(_catalog_url(spec, ra, dec, radius_arcmin,
                                   spec["fields"], max_rows), spec["name"])
    try:
        body, _ = db.http_get(key_base, "vizier", fetch_fields, force=force)
    except requests.RequestException as err:
        logger.warning("VizieR %s query failed: %s", spec["name"], err)
        return None
    headers, rows = parse_tsv(body.decode("utf-8", "replace"),
                              spec["required"], spec["ra"], spec["dec"])
    probe = spec.get("probe") or ()
    if probe and _coverage(headers, probe) < len(probe):
        # A probed column came back missing: retry asking for everything
        # and keep the wider answer when it is actually richer.
        def fetch_all():
            return _fetch(_catalog_url(spec, ra, dec, radius_arcmin,
                                       "all", max_rows), spec["name"])
        try:
            wide_body, _ = db.http_get(key_base + ":all", "vizier",
                                       fetch_all, force=force)
            w_headers, w_rows = parse_tsv(wide_body.decode("utf-8",
                                                           "replace"),
                                          spec["required"], spec["ra"],
                                          spec["dec"])
            if _coverage(w_headers, probe) > _coverage(headers, probe):
                logger.info("VizieR %s: -out.all retry recovered columns",
                            spec["name"])
                return w_headers, w_rows
        except requests.RequestException:
            pass  # the first answer stays
    return headers, rows
