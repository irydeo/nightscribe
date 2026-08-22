############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Object enrichment orchestrator
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

from . import ephem_minor, orbits
from .sources import cad, exoplanet_archive, horizons, sbdb, simbad

logger = logging.getLogger(__name__)

# Detects the object kind and pulls everything the sources know about it,
# returning one flat dict that narrative/post/viz consume.


def detect_type(name):
    # @args: name - user-typed identifier
    # @return: "sun" | "transient" | "exoplanet" | "small_body"
    n = name.strip()
    if n.lower() in ("sol", "sun"):
        return "sun"
    if re.match(r"^(SN|AT)\s?\d{4}[a-zA-Z]{1,4}$", n, re.I):
        return "transient"
    if re.search(r"\s(b|c|d|e|f)$", n) and not re.match(r"^\d{4}", n):
        return "exoplanet"
    return "small_body"


def enrich(name, date=None, site="Z41", fallback_target=None):
    # Gathers every interesting fact about an object.
    # @args: name - identifier, date - reference date (today),
    #        site - MPC code, fallback_target - planner target dict used
    #        when SBDB does not know the object (unconfirmed NEOCP/PCCP)
    # @return: dict with "type" and a "data" section per type
    kind = detect_type(name)
    if kind == "sun":
        from . import solar
        return {"type": "sun", "name": "Sun", "data": solar.solar_now()}
    if kind == "transient":
        return {"type": "transient", "name": name, "data": _enrich_transient(name)}
    if kind == "exoplanet":
        return {"type": "exoplanet", "name": name,
                "data": exoplanet_archive.planet(name)}
    data = _enrich_small_body(name, date, site)
    if not data and fallback_target is not None:
        # unconfirmed object (packed designation): tell its story with
        # whatever the planner already knows (NEOfixer/PCCP fields)
        data = {"unconfirmed": fallback_target}
        return {"type": fallback_target.get("kind", "neo"), "name": name,
                "data": data}
    out = {"type": "small_body", "name": name, "data": data}
    # hashtag hint: comets are not asteroids (see sbdb kind)
    if data and (data.get("sbdb") or {}).get("kind") in ("cn", "cu"):
        out["type"] = "comet"
    return out


def _enrich_transient(name):
    # @args: name - transient id (SN..., AT...)
    # @return: dict with SIMBAD identity + host galaxy
    ident = simbad.query_id(name)
    host = simbad.query_around_galaxy(name)
    out = {"simbad": ident, "host": host}
    if host and host.get("z"):
        # light travel time from the host redshift (small z approximation)
        d_mpc = host["z"] * 299792.458 / 70.0
        out["dist_mly"] = round(d_mpc * 3.26156, 1)
    return out


def _enrich_small_body(name, date, site):
    # @args: name - designation, date - reference date, site - MPC code
    # @return: dict with SBDB data, ephemeris, next approach and extras
    body = sbdb.get(name)
    if not body:
        return None
    out = {"sbdb": body}
    eph = horizons.ephemeris(body["des"] or name, center=site)
    if eph:
        out["ephem"] = eph[0]
        h = body["phys"].get("H")
        out["mag_now"] = orbits.visual_mag(h, eph[0]["r"], eph[0]["delta"])
        out["dist_now_km"] = eph[0]["delta"] * orbits.AU_KM
    out["next_approach"] = cad.next_approach(body["des"] or name)
    elements = body.get("elements") or {}
    out["family"] = orbits.classify(elements, body.get("orbit_code"))
    # comet expected brightness (outburst detection feeds the narrative)
    m1, k1 = body["phys"].get("M1"), body["phys"].get("K1")
    if m1 and k1 and eph:
        out["mag_expected"] = orbits.comet_expected_mag(m1, k1, eph[0]["r"],
                                                        eph[0]["delta"])
    return out
