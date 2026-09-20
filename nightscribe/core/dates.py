############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Date helpers module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# One place for the discovery-date formats our sources use
# (object-card plan, subplan 5d): Rochester "2026/08/30.5", TNS/SBDB
# "2026-08-30", SBDB discovery "2004-Mar-15". Everything downstream
# (table column, freshness score, SN card) speaks ISO "YYYY-MM-DD".

import datetime

_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
           "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def normalize_date(s):
    # @args: s - date string in any of the source formats above
    # @return: "YYYY-MM-DD", or None when missing/unparseable
    if not s:
        return None
    txt = str(s).strip().split(".")[0].replace("/", "-")
    parts = txt.split("-")
    if len(parts) != 3:
        return None
    try:
        year, day = int(parts[0]), int(parts[2])
    except ValueError:
        return None
    try:
        month = int(parts[1])
    except ValueError:
        month = _MONTHS.get(parts[1][:3].lower())
        if month is None:
            return None
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return None


def days_since(date_str):
    # @args: date_str - any format normalize_date accepts
    # @return: whole days from that date to today, or None if unparseable
    iso = normalize_date(date_str)
    if iso is None:
        return None
    d = datetime.date.fromisoformat(iso)
    return (datetime.date.today() - d).days
