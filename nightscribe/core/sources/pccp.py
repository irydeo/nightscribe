############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - MPC Possible Comet Confirmation Page source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging

import lxml.html as lh
import requests

from ..db import db

logger = logging.getLogger(__name__)

URL = "https://www.minorplanetcenter.net/iau/NEO/pccp_tabular.html"


def _parse_radec(ra_cell, dec_cell):
    # PCCP cells carry a decimal value plus sexagesimal, e.g.
    # "319.8709   21 19.5" and "087.6582   -02 20". We keep the sexagesimal
    # part (hours/minutes and degrees/minutes, no seconds).
    # @args: ra_cell, dec_cell - raw cell texts
    # @return: (ra_deg, dec_deg) or (None, None)
    try:
        ra_parts = ra_cell.split()[-2:]
        ra_deg = 15.0 * (float(ra_parts[0]) + float(ra_parts[1]) / 60.0)
        dec_parts = dec_cell.split()[-2:]
        sign = -1.0 if dec_parts[0].startswith("-") else 1.0
        dec_deg = sign * (abs(float(dec_parts[0])) + float(dec_parts[1]) / 60.0)
        return ra_deg, dec_deg
    except (ValueError, IndexError):
        return None, None


def parse_pccp(html_text):
    # Parses the PCCP tabular page. The main table has a "Temp Desig" header;
    # a second table lists already-confirmed objects with fewer columns
    # (we skip those: they are no longer candidates).
    # @args: html_text - page HTML
    # @return: list of dicts (desig, score, ra, dec, vmag, nobs, arc...)
    doc = lh.fromstring(html_text)
    result = []
    for table in doc.xpath("//table"):
        rows = table.xpath(".//tr")
        if not rows:
            continue
        header = [c.text_content().strip() for c in rows[0].xpath("./th|./td")]
        if "Temp Desig" not in header:
            continue
        for row in rows[1:]:
            cells = [c.text_content().replace("\xa0", " ").strip()
                     for c in row.xpath("./td")]
            if len(cells) < 10 or not cells[0]:
                continue
            try:
                score = float(cells[1].split()[0])
            except (ValueError, IndexError):
                score = None
            ra_deg, dec_deg = _parse_radec(cells[3], cells[4])
            result.append({
                "desig": cells[0].split()[0],
                "score": score,
                "discovery": cells[2],
                "ra_deg": ra_deg,
                "dec_deg": dec_deg,
                "vmag": cells[5].split()[-1] if cells[5].split() else None,
                "updated": cells[6],
                "note": cells[7],
                "nobs": cells[8],
                "arc": cells[9],
            })
        break  # only the first table with that header is the live PCCP
    return result


def candidates():
    # Current PCCP candidates, highest comet-score first.
    # @return: list of dicts (see parse_pccp)
    def fetch():
        r = requests.get(URL, timeout=40)
        r.raise_for_status()
        return r.content, "text/html"
    try:
        body, _ = db.http_get("pccp:page", "pccp", fetch)
        cands = parse_pccp(body.decode("utf-8", "replace"))
        return sorted(cands, key=lambda c: c["score"] or 0, reverse=True)
    except requests.RequestException as err:
        logger.warning("PCCP fetch failed: %s", err)
        return []
