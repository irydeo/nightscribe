############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - COBS comet database source
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

URL = "https://cobs.si/api/comet_list.api"


def active_comets(limit_mag=20.0):
    # Currently active comets brighter than a limit, brightest first.
    # @args: limit_mag - faintest magnitude to include
    # @return: list of dicts (name, fullname, mag, perihelion_date, type...)
    def fetch():
        r = requests.get(URL, timeout=40)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get("cobs:list", "cobs", fetch)
        objects = json.loads(body.decode("utf-8", "replace")).get("objects", [])
    except (requests.RequestException, ValueError) as err:
        logger.warning("COBS fetch failed: %s", err)
        return []
    result = []
    for o in objects:
        try:
            mag = float(o.get("current_mag") or 99)
        except (TypeError, ValueError):
            continue
        if not o.get("is_active") or mag > limit_mag:
            continue
        result.append({
            "name": o.get("name"),
            "fullname": o.get("fullname"),
            "mpc_name": o.get("mpc_name"),
            "type": o.get("type"),
            "mag": mag,
            "perihelion_date": o.get("perihelion_date"),
            "perihelion_mag": o.get("perihelion_mag"),
            "peak_mag": o.get("peak_mag"),
        })
    return sorted(result, key=lambda c: c["mag"])
