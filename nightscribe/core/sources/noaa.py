############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - NOAA Space Weather Prediction Center source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import json
import logging

import requests

from ..db import db

logger = logging.getLogger(__name__)

BASE = "https://services.swpc.noaa.gov"


def _get_json(url, cache_key):
    # @args: url - NOAA JSON endpoint, cache_key - cache key
    # @return: decoded JSON or None
    def fetch():
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(cache_key, "noaa", fetch)
        return json.loads(body.decode("utf-8", "replace"))
    except (requests.RequestException, ValueError) as err:
        logger.warning("NOAA fetch failed (%s): %s", cache_key, err)
        return None


def solar_indices():
    # Latest observed solar-cycle indices.
    # @return: dict with ssn, f107, time_tag or None
    data = _get_json(f"{BASE}/json/solar-cycle/observed-solar-cycle-indices.json",
                     "noaa:indices")
    if not data:
        return None
    last = data[-1]
    return {
        "time_tag": last.get("time-tag"),
        "ssn": last.get("ssn"),
        "f107": last.get("f10.7"),
    }


def kp_index():
    # Latest planetary K index.
    # @return: dict with kp, time_tag or None
    data = _get_json(f"{BASE}/products/noaa-planetary-k-index.json", "noaa:kp")
    if not data or len(data) < 2:
        return None
    last = data[-1]
    try:
        # the feed is a list of dicts: {"time_tag": ..., "Kp": ...}
        return {"kp": float(last["Kp"]), "time_tag": last["time_tag"]}
    except (ValueError, KeyError, TypeError):
        return None


def active_regions():
    # Active solar regions from the last days.
    # @return: list of dicts (region, location, ...) newest last
    data = _get_json(f"{BASE}/json/solar_regions.json", "noaa:regions")
    if not data:
        return []
    return data[-30:]


def max_flare_7d():
    # Strongest X-ray flux of the last 7 days as a flare class letter + value.
    # @return: dict with class (A/B/C/M/X) and flux, or None
    data = _get_json(f"{BASE}/json/goes/primary/xrays-7-day.json", "noaa:xray")
    if not data:
        return None
    try:
        fluxes = [float(d["flux"]) for d in data if d.get("flux") is not None]
        peak = max(fluxes)
    except (ValueError, KeyError, TypeError):
        return None
    cls = "A"
    for letter, threshold in (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7)):
        if peak >= threshold:
            cls = letter
            break
    # flare class magnitude, e.g. M3.2
    scale = {"A": 1e-8, "B": 1e-7, "C": 1e-6, "M": 1e-5, "X": 1e-4}[cls]
    return {"class": cls, "value": round(peak / scale, 1), "flux": peak}
