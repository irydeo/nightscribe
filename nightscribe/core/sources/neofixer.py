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


def orbit(packed):
    # Preliminary orbital elements for an (often unconfirmed) object,
    # computed by NEOfixer with Bill Gray's Find_Orb from MPC astrometry.
    # @args: packed - packed MPC designation (e.g. "6HJ1A21")
    # @return: normalised dict shaped like sbdb.parse_sbdb, or None
    import json

    def fetch():
        return requests.get(f"{BASE}/orbit/", params={"object": packed},
                            timeout=40).content, "application/json"
    try:
        body, _ = db.http_get(f"neofixer:orbit:{packed}", "neofixer-orbit",
                              fetch)
        data = json.loads(body.decode("utf-8", "replace"))
        return parse_neofixer_orbit(data, packed)
    except (requests.RequestException, ValueError) as err:
        logger.warning("NEOfixer orbit failed for %s: %s", packed, err)
        return None


def parse_neofixer_orbit(data, packed):
    # Normalises a raw /orbit/ reply into the same shape as sbdb.parse_sbdb,
    # so every downstream consumer (orbit chart, ephemeris, post)
    # works unchanged. Element naming follows SBDB: M->ma, arg_per->w,
    # asc_node->om, Tp->tp. Per-element sigmas are kept under "sigmas".
    # @args: data - decoded NEOfixer JSON, packed - designation requested
    # @return: dict or None if the object has no orbit
    objects = (data.get("result") or {}).get("objects") or {}
    obj = objects.get(packed)
    if not obj:
        return None
    raw = obj.get("elements") or {}
    if not raw.get("a") or raw.get("e") is None:
        return None
    elements = {
        "a": raw["a"], "e": raw["e"], "i": raw.get("i", 0.0),
        "om": raw.get("asc_node", 0.0), "w": raw.get("arg_per", 0.0),
        "ma": raw.get("M"), "tp": raw.get("Tp"), "epoch": raw.get("epoch"),
        "q": raw.get("q"), "Q": raw.get("Q"),
    }
    elements = {k: v for k, v in elements.items() if v is not None}
    sigmas = {k[:-6]: v for k, v in raw.items()
              if k.endswith(" sigma") and v is not None}
    moids = raw.get("MOIDs") or {}
    moid_earth = moids.get("Earth")
    obs = obj.get("observations") or {}
    arc_days = None
    if obs.get("earliest") and obs.get("latest"):
        arc_days = round(obs["latest"] - obs["earliest"], 2)
    return {
        "fullname": packed,
        "des": packed,
        "kind": None,                   # unknown until MPC confirms
        "neo": (raw.get("p_NEO") or 0) >= 50,
        "pha": moid_earth is not None and moid_earth < 0.05,
        "orbit_class": None,
        "orbit_code": None,
        "elements": elements,
        "sigmas": sigmas,
        "moid": moid_earth,
        "phys": {"H": raw.get("H"), "G": raw.get("G")},
        "rms_residual": raw.get("rms_residual"),
        "n_resids": raw.get("n_resids"),
        "arc_days": arc_days,
        "preliminary": True,            # flag for narrative/UI wording
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
