############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - MPC observatory codes source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging
import math
import re

import requests

from ..db import db

logger = logging.getLogger(__name__)

OBSCODES_URL = "https://minorplanetcenter.net/iau/lists/ObsCodesF.html"

# WGS84 flattening, to convert the MPC parallax constants to geodetic latitude
F_WGS84 = 1 / 298.257223563


def parse_obscodes(text):
    # @args: text - raw ObsCodes list page
    # @return: dict code -> {"lon", "lat", "name"}
    result = {}
    # Lines look like: Z41 356.6264  0.76087  +0.64689  Irydeo Observatory...
    pattern = re.compile(
        r"^([0-9A-Z][0-9A-Z ][0-9A-Z])\s+([0-9.]+)\s+([0-9.]+)\s+"
        r"([+-][0-9.]+)\s{2,}(.+?)\s*$", re.M)
    for m in pattern.finditer(text):
        code, lon, rhocos, rhosin, name = m.groups()
        lon = float(lon)
        if lon > 180:  # MPC lists 0..360 east
            lon -= 360.0
        rhocos, rhosin = float(rhocos), float(rhosin)
        lat = math.degrees(math.atan2(rhosin, rhocos * (1 - F_WGS84) ** 2))
        result[code.strip()] = {
            "lon": round(lon, 5), "lat": round(lat, 5), "name": name.strip(),
        }
    return result


def _fetch():
    # @return: (body bytes, content_type) for the MPC observatory list
    r = requests.get(OBSCODES_URL, timeout=30)
    r.raise_for_status()
    return r.content, "text/html"


def lookup(code):
    # Resolves an MPC observatory code to coordinates and name.
    # @args: code - e.g. "Z41"
    # @return: {"lon", "lat", "name"} or None if unknown
    try:
        body, _ = db.http_get("obscodes:list", "obscodes", _fetch)
    except requests.RequestException as err:
        logger.warning("ObsCodes fetch failed: %s", err)
        return None
    return parse_obscodes(body.decode("utf-8", "replace")).get(code.strip().upper())
