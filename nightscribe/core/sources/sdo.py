############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - NASA SDO latest images source
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

from ... import paths
from ..db import db

logger = logging.getLogger(__name__)

BASE = "https://sdo.gsfc.nasa.gov/assets/img/latest"

# Public-domain images (courtesy of NASA/SDO and the AIA, EVE and HMI teams)
CHANNELS = {
    "0193": "Corona 193 Å (Fe XII)",
    "0304": "Chromosphere 304 Å (He II)",
    "0171": "Corona 171 Å (Fe IX)",
    "HMII": "Visible light (continuum, sunspots)",
    "HMIB": "Magnetogram",
}


def latest_image(channel="0193", size=1024):
    # Downloads (or reuses from cache) the latest SDO image of a channel.
    # @args: channel - SDO channel code (see CHANNELS), size - px
    # @return: local Path to the JPEG, or None
    url = f"{BASE}/latest_{size}_{channel}.jpg"

    def fetch():
        r = requests.get(url, timeout=40)
        r.raise_for_status()
        return r.content, "image/jpeg"
    try:
        body, _ = db.http_get(f"sdo:{channel}:{size}", "sdo", fetch)
    except requests.RequestException as err:
        logger.warning("SDO fetch failed (%s): %s", channel, err)
        return None
    out = paths.image_cache_dir() / f"sdo_{channel}_{size}.jpg"
    try:
        out.write_bytes(body)
    except OSError as err:
        logger.error("Could not write %s: %s", out, err)
        return None
    return out
