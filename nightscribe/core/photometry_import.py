############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Photometry import parser (Track B, B3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Tolerant parser for pasted/file photometry data.

The observer's real workflow (AIJ, Tycho-Tracker) produces tables with
date, magnitude, filter — but the exact column layout varies. This parser
accepts free-form lines and extracts the fields it can recognise, tolerating:
  - separators: comma, tab, semicolon, whitespace (any mix)
  - decimal: comma or point (Spanish locale uses comma)
  - dates: "2020/09/08.853" (fractional day), "2020-09-08",
    "2020-09-08T22:30:00", or a bare MJD/JD float (>40000)
  - missing error → None
  - missing filter → default_filter
  - header/garbage lines → skipped (not an error: the user pastes a whole
    AIJ table and we pick the rows that look like data)

Never raises on bad input: it returns the good rows and a list of skipped
line numbers so the caller can show a preview ("line N looks odd").
"""

import datetime
import logging
import re

from . import coords

logger = logging.getLogger(__name__)


def _split_fields(line):
    # @args: line - a raw text line
    # @return: list of string fields, split on any common separator.
    # Priority: tab → semicolon → comma (with decimal rejoin) → whitespace.
    # Comma is checked before whitespace because a line like
    # "2020/09/08.853,16,557,C (Clear)" would otherwise split on the
    # space inside "(Clear)" and leave the comma-decimal unparsed.
    for sep in ("\t", ";"):
        if sep in line:
            return [f.strip() for f in line.split(sep) if f.strip()]
    # comma: split, then rejoin decimal-comma fragments ("16","557" → "16.557")
    if "," in line:
        raw = [f.strip() for f in line.split(",") if f.strip()]
        merged = []
        i = 0
        while i < len(raw):
            if (i + 1 < len(raw) and raw[i + 1].isdigit()
                    and len(raw[i + 1]) <= 4
                    and _to_float(raw[i]) is not None):
                merged.append(raw[i] + "." + raw[i + 1])
                i += 2
            else:
                merged.append(raw[i])
                i += 1
        return merged
    # whitespace fallback
    parts = line.split()
    return parts if parts else ([line.strip()] if line.strip() else [])


def _to_float(token):
    # @args: token - string
    # @return: float or None (tolerates comma decimal: "16,557" → 16.557)
    if token is None:
        return None
    cleaned = token.strip().replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date_to_mjd(token):
    # @args: token - a date string or a bare MJD/JD float
    # @return: (mjd_float, original_string) or (None, token) if unparseable
    # Tries: bare float (MJD if 40000-70000, JD if >2M), "YYYY/MM/DD.fff",
    # "YYYY-MM-DD[THH:MM:SS]", "DD/MM/YY"
    val = _to_float(token)
    if val is not None:
        if val > 2_400_000:
            return val - 2_400_000.5, token   # JD → MJD
        if 40000 < val < 80000:
            return val, token                 # already MJD
        return None, token                    # a small float — not a date
    s = token.strip()
    # fractional day: "2020/09/08.853" (day 8 + 0.853 of the day)
    m = re.match(r"(\d{4})/(\d{2})/(\d{2})\.(\d+)", s)
    if m:
        y, mo, d = int(m[1]), int(m[2]), int(m[3])
        frac = int(m[4]) / (10 ** len(m[4]))   # "853" → 0.853
        dt = datetime.datetime(y, mo, d, tzinfo=datetime.timezone.utc)
        return coords.jd_from_datetime(dt) + frac - 2_400_000.5, token
    # ISO: "2020-09-08" or "2020-09-08T22:30:00"
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return coords.jd_from_datetime(dt) - 2_400_000.5, token
        except ValueError:
            continue
    # legacy: "09/09/26" (DD/MM/YY)
    try:
        dt = datetime.datetime.strptime(s, "%d/%m/%y")
        dt = dt.replace(tzinfo=datetime.timezone.utc)
        return coords.jd_from_datetime(dt) - 2_400_000.5, token
    except ValueError:
        pass
    return None, token


def parse_photometry(text, default_filter="Clear"):
    # @args: text - raw pasted text or file contents, default_filter - band
    #        used when a line has no recognisable filter column
    # @return: (points, skipped) where points is a list of
    #         {mjd, mag, err, filter} and skipped is a list of line numbers
    #         (1-based) that didn't parse as a photometry row
    points = []
    skipped = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        fields = _split_fields(raw)
        if len(fields) < 2:
            skipped.append(lineno)
            continue
        # Try to identify which fields are date / mag / err / filter.
        # Strategy: the first field that parses as a date is the date; the
        # first field that parses as a float in a reasonable mag range
        # (-5..25) is the magnitude; a second float is the error; a
        # non-numeric field (or the last) is the filter.
        mjd = None
        mag = None
        err = None
        filt = None
        leftover = []
        for f in fields:
            if mjd is None:
                mjd, _orig = _parse_date_to_mjd(f)
                if mjd is not None:
                    continue
            val = _to_float(f)
            if val is not None and mag is None and -5 < val < 30:
                mag = val
                continue
            if val is not None and err is None and 0 <= val < 5:
                err = val
                continue
            if val is None and filt is None:
                filt = f
                continue
            leftover.append(f)
        # if we still don't have a filter, grab the first leftover non-number
        if filt is None:
            for f in leftover:
                if _to_float(f) is None:
                    filt = f
                    break
        if mjd is not None and mag is not None:
            points.append({
                "mjd": mjd, "mag": mag,
                "err": err,
                "filter": filt or default_filter,
            })
        else:
            skipped.append(lineno)
    return points, skipped
