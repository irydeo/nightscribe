############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - SIMBAD (CDS) source for transients
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging
import re

import requests

from ..db import db

logger = logging.getLogger(__name__)

# CDS primary plus the Harvard mirror: heavy "query around" scripts often
# exceed the timeout on Strasbourg while the mirror answers 3x faster
# (measured 2026-09: 42s vs 13s for a 10' radius), so a failed primary is
# retried once against the mirror before giving up.
URLS = ("https://simbad.cds.unistra.fr/simbad/sim-script",
        "https://simbad.harvard.edu/simbad/sim-script")

TIMEOUT_ID_S = 40       # "query id" scripts are light
TIMEOUT_AROUND_S = 60   # "query around" scripts are heavy on the server


def _run_script(script, cache_key, timeout=TIMEOUT_ID_S):
    # @args: script - SIMBAD script text, cache_key - cache key,
    #        timeout - per-request read timeout (seconds)
    # @return: the ::data:: section lines as a list of strings
    def fetch():
        last = None
        for url in URLS:
            try:
                r = requests.post(url, data={"script": script},
                                  timeout=timeout)
                r.raise_for_status()
                return r.content, "text/plain"
            except requests.RequestException as err:
                last = err
                logger.info("SIMBAD mirror %s failed: %s", url, err)
        raise last
    try:
        body, _ = db.http_get(cache_key, "simbad", fetch)
        text = body.decode("utf-8", "replace")
        i = text.find("::data::")
        if i < 0:
            return []
        lines = [l.strip() for l in text[i:].splitlines()[1:]]
        return [l for l in lines if l]
    except requests.RequestException as err:
        logger.warning("SIMBAD script failed: %s", err)
        return []


def parse_rv_z(rv_field):
    # Extracts the redshift from a SIMBAD %RV field.
    # The field looks like: "z:spectroscopic 0.000811 (Opt) C [..] bibcode".
    # @args: rv_field - raw string
    # @return: redshift as float or None
    m = re.search(r"z\s*[:\s]\s*(?:spectroscopic\s+|photometric\s+)?([0-9.]+)",
                  rv_field or "")
    return float(m.group(1)) if m else None


def query_id(name):
    # Basic identity of a transient: type, coordinates, V magnitude, redshift.
    # @args: name - e.g. "SN2023ixf"
    # @return: dict or None if unknown
    script = ('format object "%IDLIST(1) | %OTYPE | %COO(A D) | %FLUXLIST(V)[%FLUX]'
              ' | %RV"\n'
              f"query id {name}\n")
    lines = _run_script(script, f"simbad:id:{name}")
    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        ident, otype, coo, vmag, rv = parts[:5]
        coo_parts = coo.split()
        if len(coo_parts) < 6:
            continue
        try:
            vmag_f = float(vmag)
        except ValueError:
            vmag_f = None
        return {
            "name": ident,
            "otype": otype,
            "ra": " ".join(coo_parts[:3]),
            "dec": " ".join(coo_parts[3:6]),
            "vmag": vmag_f,
            "z": parse_rv_z(rv),
        }
    return None


def query_around_galaxy(name, radius=None):
    # Looks for a host galaxy candidate near a transient, widening the
    # search until something with a redshift shows up.
    # @args: name - SIMBAD-resolvable name, radius - fixed radius (optional)
    # @return: dict with name, otype, z or None
    for r in ([radius] if radius else ["3m", "10m", "20m"]):
        script = ('format object "%IDLIST(1) | %OTYPE | %RV"\n'
                  f"query around {name} radius={r}\n")
        lines = _run_script(script, f"simbad:around:{name}:{r}",
                            timeout=TIMEOUT_AROUND_S)
        galaxies = []
        for line in lines:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            ident, otype, rv = parts[:3]
            if "Galaxy" in otype or "GinPair" in otype or otype.strip() == "G":
                galaxies.append({"name": ident, "otype": otype,
                                 "z": parse_rv_z(rv)})
        with_z = [g for g in galaxies if g["z"] is not None]
        if with_z:
            return with_z[0]
        if galaxies:
            return galaxies[0]
    return None
