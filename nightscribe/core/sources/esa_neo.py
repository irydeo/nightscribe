############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - ESA NEOCC close approaches source
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

URL = "https://neo.ssa.esa.int/PSDB-portlet/download"


def parse_close_approaches(text):
    # Parses the ESA upcoming close approaches fixed-width list.
    # Data lines are pipe-separated; a date in field 2 marks a data row.
    # @args: text - raw list text
    # @return: list of dicts (name, date, dist_ld, dist_km, diameter_m, mag, vel)
    result = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 10:
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", parts[1]):
            continue
        name = parts[0].split()[0]
        try:
            result.append({
                "name": name,
                "date": parts[1],
                "dist_km": float(parts[2]),
                "dist_au": float(parts[3]),
                "dist_ld": float(parts[4]),
                "diameter_m": float(parts[5]),
                "h": parts[7] or None,
                "mag_max": float(parts[8]),
                "vel_kms": float(parts[9]),
            })
        except (ValueError, IndexError):
            continue
    return result


def close_approaches(max_ld=20.0):
    # Upcoming close approaches within a lunar-distance limit.
    # @args: max_ld - maximum miss distance in lunar distances
    # @return: list of dicts (see parse_close_approaches), nearest first
    def fetch():
        r = requests.get(URL, params={"file": "esa_upcoming_close_app"},
                         timeout=40)
        r.raise_for_status()
        return r.content, "text/plain"
    try:
        body, _ = db.http_get("esa_neo:close_app", "esa_neo", fetch)
        rows = parse_close_approaches(body.decode("utf-8", "replace"))
        rows = [r for r in rows if r["dist_ld"] <= max_ld]
        return sorted(rows, key=lambda r: r["dist_ld"])
    except requests.RequestException as err:
        logger.warning("ESA NEOCC fetch failed: %s", err)
        return []
