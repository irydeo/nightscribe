############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Rochester Astronomy supernovae source (D. Bishop)
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

import lxml.html as lh
import requests

from ..db import db

logger = logging.getLogger(__name__)

URL = "https://www.rochesterastronomy.org/snimages/sndate.html"


def parse_sn_list(html_text):
    # Parses the "supernovae sorted by date" table, same column layout as
    # the legacy saas module used.
    # @args: html_text - page HTML
    # @return: list of dicts (name, ra, dec, date, host, type, mag)
    doc = lh.fromstring(html_text)
    result = []
    for t in doc.xpath('/html/body/table[2]//tr'):
        try:
            date = t[2].text_content().strip()
            mag = float(t[8].text_content())
            host = t[6].text_content().strip()
            ra = t[0].text_content().strip()
            dec = t[1].text_content().strip()
            sn_type = t[7].text_content().strip()
            name = t[10].text_content().strip()
            if re.match(r"\d\d\d\d/\d\d/\d\d", date) and name:
                result.append({
                    "name": name, "ra": ra, "dec": dec, "date": date,
                    "host": host, "type": sn_type, "mag": mag,
                })
        except (ValueError, IndexError):
            continue
    return result


def latest_sne(limit_mag=18.0):
    # Recent supernovae brighter than a limit.
    # @args: limit_mag - faintest magnitude to include
    # @return: list of dicts (see parse_sn_list), brightest first
    def fetch():
        r = requests.get(URL, timeout=40)
        r.raise_for_status()
        return r.content, "text/html"
    try:
        body, _ = db.http_get("rochester:sndate", "rochester", fetch)
        sne = parse_sn_list(body.decode("utf-8", "replace"))
        sne = [s for s in sne if s["mag"] < limit_mag]
        return sorted(sne, key=lambda s: s["mag"])
    except requests.RequestException as err:
        logger.warning("Rochester fetch failed: %s", err)
        return []
