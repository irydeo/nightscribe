############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - JPL Small-Body Database source
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

from .. import dates
from ..db import db

logger = logging.getLogger(__name__)

URL = "https://ssd-api.jpl.nasa.gov/sbdb.api"


def parse_sbdb(data):
    # Normalises a raw SBDB reply into a flat, handy dict.
    # @args: data - decoded SBDB JSON
    # @return: dict or None if the object was not found
    obj = data.get("object")
    if not obj:
        return None
    elements = {e["name"]: float(e["value"])
                for e in data.get("orbit", {}).get("elements", [])
                if e.get("value") is not None}
    phys = {}
    for p in data.get("phys_par", []):
        try:
            phys[p["name"]] = float(p["value"])
        except (KeyError, TypeError, ValueError):
            phys[p.get("name")] = p.get("value")  # keep strings (e.g. spectral class)
    # discovery date ("2004-Mar-15") when asked for it, else the first
    # observation of the orbit solution — both normalised to ISO
    disc = (data.get("discovery") or {}).get("date")
    first_obs = (data.get("orbit") or {}).get("first_obs")
    return {
        "fullname": obj.get("fullname") or obj.get("des"),
        "des": obj.get("des"),
        "kind": obj.get("kind"),          # au|an|cu|cn... (asteroid/comet)
        "neo": bool(obj.get("neo")),
        "pha": bool(obj.get("pha")),
        "orbit_class": (obj.get("orbit_class") or {}).get("name"),
        "orbit_code": (obj.get("orbit_class") or {}).get("code"),
        "elements": elements,
        "moid": elements.get("moid") or data.get("orbit", {}).get("moid"),
        "phys": phys,
        "disc_date": dates.normalize_date(disc)
        or dates.normalize_date(first_obs),
    }


def get(name):
    # Fetches a small body (asteroid or comet) from JPL SBDB.
    # @args: name - any designation ("Apophis", "2021EQ3", "29P")
    # @return: normalised dict or None
    def fetch():
        r = requests.get(URL, params={"sstr": name, "phys-par": "1",
                                      "discovery": "1"}, timeout=30)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(f"sbdb:{name}", "sbdb", fetch)
        return parse_sbdb(json.loads(body.decode("utf-8", "replace")))
    except (requests.RequestException, ValueError) as err:
        logger.warning("SBDB lookup failed for %s: %s", name, err)
        return None
