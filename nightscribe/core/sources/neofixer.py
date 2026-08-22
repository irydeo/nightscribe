############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - NEOfixer source (NEO planning, Univ. of Arizona)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging

import requests

from ..db import db

logger = logging.getLogger(__name__)

BASE = "https://neofixerapi.arizona.edu"


def _get(method, params):
    # @args: method - API method (targets|ephem|report), params - dict
    # @return: decoded JSON dict
    r = requests.get(f"{BASE}/{method}/", params=params, timeout=40)
    r.raise_for_status()
    return r.json()


def targets(site, num=40):
    # Priority target list for a site, highest scoring first.
    # @args: site - MPC observatory code, num - max targets
    # @return: list of target dicts (packed, priority, score, cost, vmag...)
    def fetch():
        return requests.get(f"{BASE}/targets/", params={"site": site, "num": num},
                            timeout=40).content, "application/json"
    import json
    try:
        body, _ = db.http_get(f"neofixer:targets:{site}:{num}", "neofixer", fetch)
        result = json.loads(body.decode("utf-8", "replace")).get("result", {})
        objects = result.get("objects", {})
        return [objects[oid] for oid in result.get("ids", []) if oid in objects]
    except (requests.RequestException, ValueError) as err:
        logger.warning("NEOfixer targets failed for %s: %s", site, err)
        return []


def ephem(site, packed):
    # Site-specific ephemeris of an object for the coming days.
    # @args: site - MPC code, packed - packed designation (e.g. "6HJ1A21")
    # @return: list of ephemeris entry dicts (alt, az, mag, motion_rate...)
    import json
    params = {"site": site, "object": packed, "format": "json", "time-start": "now"}

    def fetch():
        return requests.get(f"{BASE}/ephem/", params=params, timeout=40).content, \
            "application/json"
    try:
        body, _ = db.http_get(f"neofixer:ephem:{site}:{packed}", "neofixer", fetch)
        result = json.loads(body.decode("utf-8", "replace")).get("result", {})
        return result.get("entries") or []
    except (requests.RequestException, ValueError) as err:
        logger.warning("NEOfixer ephem failed for %s: %s", packed, err)
        return []


def best_window(entries, min_alt=30.0):
    # Best observing window from an ephemeris entry list.
    # @args: entries - list from ephem(), min_alt - altitude threshold (deg)
    # @return: dict with max_alt, max_time, window_start, window_end, or None
    up = [e for e in entries if e.get("alt") is not None and e["alt"] >= min_alt]
    if not up:
        return None
    best = max(up, key=lambda e: e["alt"])
    return {
        "max_alt": round(best["alt"], 1),
        "max_time": best.get("ISO_time"),
        "window_start": up[0].get("ISO_time"),
        "window_end": up[-1].get("ISO_time"),
    }


def report(key, site, packed, status):
    # Reports an observing status to NEOfixer (community coordination).
    # @args: key - user API key, site - MPC code, packed - object,
    #        status - will_observe|observing|observed|found|reported|...
    # @return: True on success
    try:
        d = _get("report", {"key": key, "site": site, "object": packed,
                            "status": status})
        return bool(d.get("result"))
    except (requests.RequestException, ValueError) as err:
        logger.warning("NEOfixer report failed for %s: %s", packed, err)
        return False
