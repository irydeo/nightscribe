############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Nearest-place lookup (site naming)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Give a coordinate a name.

A point clicked on the map has no name, and an observatory with no name
makes a poor report. This module answers the obvious question ("what is
near here?") from a bundled list of 1251 cities (Natural Earth 50m, public
domain): the nearest one within a sane distance, or nothing at all when the
click landed in the middle of an ocean.

Offline on purpose. A reverse geocoding service would be more precise, but
it costs a network round trip on a gesture the observer may repeat five
times while aiming, and it drags in a usage policy and an attribution for a
field that is free text anyway.
"""

import json
import math
from pathlib import Path

# Bundled data assets live next to moon_disk.png, resolved here the same way
# core/hads.py does it: core/ must not import gui/ (the CLI uses these
# modules with no Qt around).
ASSET = Path(__file__).resolve().parent.parent / "assets" / "world_places.json"

# Beyond this the "nearest" city says more about the emptiness of the
# landscape than about where you are: a click in the Sahara is nearer
# Tamanrasset than it is anywhere else, and calling it "Tamanrasset" would
# be confidently wrong.
MAX_KM = 250.0

# Mean Earth radius, kilometres.
_R = 6371.0

_CACHE = None


def _load():
    # @return: [(name, country, lon, lat), ...]; empty when the asset is
    #          missing, so a broken install degrades to coordinates
    global _CACHE
    if _CACHE is None:
        try:
            data = json.loads(ASSET.read_text(encoding="utf-8"))
            _CACHE = [tuple(row) for row in data.get("places", ())]
        except Exception:
            _CACHE = []
    return _CACHE


def distance_km(lat1, lon1, lat2, lon2):
    # Great-circle distance, haversine. Plain enough to be exact for this
    # use and far cheaper than anything fancier.
    # @args: two points in degrees
    # @return: kilometres
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = (math.sin(dp / 2.0) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2)
    return 2.0 * _R * math.asin(min(1.0, math.sqrt(a)))


def nearest(lat, lon, max_km=MAX_KM):
    # @args: lat, lon - the point to name; max_km - how far a city may be
    # @return: {"name": "Madrid, Spain", "lat", "lon", "km"} or None
    best = None
    for name, country, plon, plat in _load():
        km = distance_km(lat, lon, plat, plon)
        if best is None or km < best[0]:
            best = (km, name, country, plon, plat)
    if best is None or best[0] > max_km:
        return None
    km, name, country, plon, plat = best
    label = ", ".join(part for part in (name, country) if part)
    return {"name": label, "lat": plat, "lon": plon, "km": km}


def label(lat, lon, translate=None, max_km=MAX_KM):
    # @args: lat, lon - the point; translate - a callable like QObject.tr
    #          used for the hemisphere letters (west is W in English and O
    #          in Spanish, and a wrong letter sends the reader the wrong
    #          way); max_km - the search radius
    # @return: "Madrid, Spain" when there is a city close enough, or the
    #          coordinates written out, e.g. "40.4168° N, 3.7038° W"
    near = nearest(lat, lon, max_km)
    if near is not None:
        return near["name"]
    tr = translate or (lambda text: text)
    ns = tr("N") if lat >= 0 else tr("S")
    ew = tr("E") if lon >= 0 else tr("W")
    return "%s\u00b0 %s, %s\u00b0 %s" % (
        ("%.4f" % abs(lat)), ns, ("%.4f" % abs(lon)), ew)
