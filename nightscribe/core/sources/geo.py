############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - IP geolocation source (wizard site detection)
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

# Two free IP geolocation providers, tried in order: one being down (or
# blocking data-centre traffic) must not defeat site detection.
_PROVIDERS = (
    "https://ipapi.co/json/",
    "https://ipwho.is/",
)

_ELEVATION = "https://api.open-meteo.com/v1/elevation"

# Privacy note (ADR-042): nothing in this module runs on its own. It is only
# called from the wizard's "Detect my location" button, i.e. after the user
# has explicitly asked for it. The calls go through the HTTP cache like any
# other source (see SOURCE_TTL in core/db.py).


def _parse(data):
    # Both providers answer in the same shape (latitude/longitude/city/
    # country_name), so one shared parser handles both.
    # @args: data - the provider's decoded JSON
    # @return: dict lat/lon (degrees) + name, or None when unparseable
    try:
        lat = float(data["latitude"])
        lon = float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    city = (data.get("city") or "").strip()
    # ipapi.co spells it "country_name", ipwho.is just "country": reading
    # only the first one silently dropped the country from the suggested
    # name ("Madrid" instead of "Madrid, Spain") on the fallback provider.
    country = (data.get("country_name") or data.get("country") or "").strip()
    name = ", ".join(part for part in (city, country) if part) or "your location"
    return {"lat": lat, "lon": lon, "name": name}


def ip_location(force=False):
    # Resolves this machine's public IP to a city and coordinates: the
    # starting guess for a new observatory site (ADR-042).
    # @args: force - True bypasses the per-provider cache (re-detect)
    # @return: dict lat/lon/name, or None if every provider failed
    for url in _PROVIDERS:
        def fetch(url=url):
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            return r.content, "application/json"
        try:
            body, _ = db.http_get(f"geo:{url}", "geo", fetch, force=force)
            data = json.loads(body.decode("utf-8", "replace"))
            out = _parse(data)
            if out:
                return out
        except (requests.RequestException, ValueError) as err:
            logger.info("ip_location: %s failed (%s)", url, err)
    return None


def elevation(lat, lon, force=False):
    # Terrain elevation at a point: a best-effort finishing touch on the
    # detected site (open-meteo answers per place, so a long TTL is safe).
    # @args: lat/lon - degrees, force - True bypasses the cache
    # @return: int meters above mean sea level, or None (offline is fine)
    def fetch():
        r = requests.get(_ELEVATION,
                         params={"latitude": lat, "longitude": lon},
                         timeout=15)
        r.raise_for_status()
        return r.content, "application/json"
    key = f"elevation:{lat:.5f}:{lon:.5f}"
    try:
        body, _ = db.http_get(key, "elevation", fetch, force=force)
        data = json.loads(body.decode("utf-8", "replace"))
        # open-meteo answers {"elevation": [666.0]}: a LIST, one value per
        # requested point. Reading it as a bare number raised a TypeError
        # that the old except list did not catch, so it escaped the button's
        # slot and left "Finding your observatory..." on screen forever
        # (seen 2026-10-02). Both shapes are accepted now.
        value = data["elevation"]
        if isinstance(value, (list, tuple)):
            value = value[0]
        return int(round(float(value)))
    except (requests.RequestException, ValueError, KeyError, TypeError,
            IndexError) as err:
        logger.info("elevation: failed (%s)", err)
        return None
