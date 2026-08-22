############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - TNS (Transient Name Server) source: object resolution
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

# The public object page carries the J2000 position both sexagesimal and in
# decimal degrees (the "alter-value" block). One cached fetch per object —
# be a good citizen (see DATA_SOURCES). TODO: official TNS bot API once the
# user's bot credentials (tns_bot_name/tns_bot_key) are wired in.
URL = "https://www.wis-tns.org/object/"


def short_name(name):
    # TNS URLs use the bare designation: "SN2026zji" -> "2026zji".
    # @args: name - any SN/AT designation
    # @return: short name (digits + letters) or the stripped input
    m = re.match(r"^\s*(?:SN|AT)?\s*(\d{4}[a-zA-Z]{1,4})\s*$", name or "",
                 re.I)
    return m.group(1).lower() if m else (name or "").strip().lower()


def parse_object_page(html_text):
    # Extracts position and basic data from a TNS object page.
    # @args: html_text - page HTML
    # @return: dict {"name", "ra", "dec", "type", "mag", "disc_date"}
    #          (ra/dec in decimal degrees) or None if no position found
    doc = lh.fromstring(html_text)
    # note: lxml nests alter-value inside the wrapping <b>, so use
    # descendant rather than child
    radec = doc.xpath('//div[contains(@class, "field-radec")]'
                      '//div[@class="alter-value"]')
    if not radec:
        return None
    parts = radec[0].text_content().split()
    if len(parts) < 2:
        return None
    try:
        ra, dec = float(parts[0]), float(parts[1])
    except ValueError:
        return None

    def _field(cls):
        # @return: <b> text of a field-<cls> block, or ""
        node = doc.xpath(f'//div[contains(@class, "field-{cls}")]'
                         '//div[@class="value"]/b')
        return node[0].text_content().strip() if node else ""

    title = doc.xpath('//h1[@class="title"]')
    name = title[0].text_content().strip().replace(" ", "")
    try:
        mag = float(_field("discoverymag"))
    except ValueError:
        mag = None
    sn_type = _field("type") or None
    if sn_type == "---":
        sn_type = None  # unclassified AT
    return {"name": name or None, "ra": ra, "dec": dec, "type": sn_type,
            "mag": mag, "disc_date": _field("discoverydate") or None}


def resolve(name):
    # Resolves a transient designation to its TNS position.
    # @args: name - e.g. "2026zji", "SN2023ixf", "AT2024abc"
    # @return: dict (see parse_object_page) or None if unknown/offline
    short = short_name(name)
    if not short:
        return None

    def fetch():
        r = requests.get(URL + short, timeout=40,
                         headers={"User-Agent": "NightScribe blink resolver"})
        r.raise_for_status()
        return r.content, "text/html"
    try:
        body, _ = db.http_get(f"tns:object:{short}", "tns", fetch)
    except requests.RequestException as err:
        logger.info("TNS object %s not reachable: %s", short, err)
        return None
    info = parse_object_page(body.decode("utf-8", "replace"))
    if info is None:
        logger.info("TNS object %s not found or has no position", short)
    return info
