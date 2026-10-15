############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Minor Planet Center orbits source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Orbital elements and the OFFICIAL orbit type from the MPC (ADR-088).

The MPC publishes an Orbits API (`get-orb`, verified 2026-10-14) that answers
the MPC_ORB JSON for one designation. It is the MPC's OWN classification, the
one the observer reads on the object's page, and it can disagree with JPL's
`orbit_code` and with our own q-based rule: on 2026 TG69 the MPC's API says
Apollo while its db_search page says Amor (JPL says Apollo). Showing the MPC's
value is the honest answer to "what does the MPC call this?".

Like get-obs, the request is a GET **with a JSON body** and answers a list
whose payload carries the data. Everything goes through ``core/db`` so a
designation is fetched once; network failures and unknown objects answer
None and the caller degrades (the local classification stands).
"""

import json
import logging

import requests

from ...config import config
from ..db import SOURCE_TTL, db

logger = logging.getLogger(__name__)

URL_ORB = "https://data.minorplanetcenter.net/api/get-orb"

# A confirmed orbit is refined slowly, so a day is fine; a designation is
# fetched once and kept.
SOURCE_TTL.setdefault("mpc_orbits", 24 * 3600)

# The NEO families the MPC names the way we do. The MPC's orbit type can be
# other things (Mars Crosser, Hungaria, Jupiter Trojan, ...) whose labels do
# not match our FAMILIES keys, so only these override the local rule: for the
# rest, our own classification stays.
NEO_FAMILIES = ("Atira", "Aten", "Apollo", "Amor")


def _get_json(desig, force):
    # @args: desig - the designation, force - True bypasses the cache read
    # @return: decoded JSON, or None on network/parse failure
    def fetch():
        r = requests.get(URL_ORB, json={"desig": desig}, timeout=60)
        r.raise_for_status()
        return r.content, "application/json"
    try:
        body, _ = db.http_get(f"mpcorb:{desig}", "mpc_orbits", fetch,
                              force=force)
    except requests.RequestException as err:
        logger.warning("MPC orbits request failed for %s: %s", desig, err)
        return None
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except ValueError as err:
        logger.warning("MPC orbits payload not parseable for %s: %s",
                       desig, err)
        return None


def _first_orb(data):
    # @args: data - the decoded envelope (a list of payload dicts, or one)
    # @return: the first mpc_orb dict, or None. The envelope carries the data
    #          in a list under "mpc_orb" (a list of orbits, usually one).
    blocks = data if isinstance(data, list) else [data]
    for block in blocks:
        if not isinstance(block, dict):
            continue
        orbs = block.get("mpc_orb")
        if isinstance(orbs, list) and orbs and isinstance(orbs[0], dict):
            return orbs[0]
        if isinstance(orbs, dict):
            return orbs
    return None


def parse_orb(orb):
    # @args: orb - one mpc_orb dict
    # @return: {"orbit_type", "object_type", "elements", "moid", "packed",
    #          "designation"}. The KEP block carries a, e, i, node, argperi
    #          and mean_anomaly as parallel name/value lists; q and Q are not
    #          given, so they are derived from a and e (q = a(1-e)).
    if not isinstance(orb, dict):
        return None
    cat = orb.get("categorization") or {}
    des = orb.get("designation_data") or {}
    kep = orb.get("KEP") or {}
    names = kep.get("coefficient_names") or []
    values = kep.get("coefficient_values") or []
    elements = {}
    if len(names) == len(values):
        elements = {str(n): v for n, v in zip(names, values)}
    a, e = elements.get("a"), elements.get("e")
    if a is not None and e is not None:
        elements.setdefault("q", a * (1.0 - e))
        elements.setdefault("Q", a * (1.0 + e))
    return {
        "orbit_type": str(cat.get("orbit_type_str") or ""),
        "object_type": str(cat.get("object_type_str") or ""),
        "elements": elements,
        "moid": dict(orb.get("moid_data") or {}),
        "packed": str(des.get("packed_primary_provisional_designation") or ""),
        "designation": str(des.get("iau_designation") or ""),
    }


def get_orb(desig, force=False):
    # @args: desig - the MPC designation ("2026 TG69", "99942"), force - True
    #        bypasses the cache read
    # @return: the parsed dict, or None when the object is unknown or offline
    name = str(desig or "").strip()
    if not name:
        return None
    data = _get_json(name, force)
    orb = _first_orb(data) if data is not None else None
    return parse_orb(orb) if orb else None
