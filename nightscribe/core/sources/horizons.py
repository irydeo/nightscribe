############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - JPL Horizons ephemeris source
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
import re

import requests

from ..db import db

logger = logging.getLogger(__name__)

URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

# One ephemeris line, with or without the solar/lunar presence markers
# Horizons inserts between the time and the RA ("*" daylight, "C/N/A"
# twilights, "m" moonlight — glued or as separate columns).
_EPHEM_RE = re.compile(
    r"^\s*"
    r"(\d{4}-\w{3}-\d{2}\s+\d{2}:\d{2})"              # date + time (UTC)
    r"[\s*]*(?:[A-Za-z]+\s+)*"                        # optional markers
    r"(\d{1,2})\s+(\d{2})\s+(\d{2}(?:\.\d+)?)"        # RA h m s
    r"\s+([+-]?\d{1,2})\s+(\d{2})\s+(\d{2}(?:\.\d+)?)"  # Dec d m s
    r"\s+(-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)"          # r (AU)
    r"\s+(-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)"          # rdot
    r"\s+(-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)"          # delta (AU)
    r"\s+(-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?)")         # delta-dot


def parse_ephemeris(result_text):
    # Parses the table between $$SOE / $$EOE of a Horizons OBSERVER reply
    # with QUANTITIES '1,19,20' (RA/Dec, heliocentric range, observer range).
    # Marker columns (daylight/twilight/moonlight flags) are skipped.
    # @args: result_text - the "result" field of the Horizons JSON
    # @return: list of dicts with time, ra, dec, r, delta
    rows = []
    in_table = False
    for line in result_text.splitlines():
        if "$$SOE" in line:
            in_table = True
            continue
        if "$$EOE" in line:
            break
        if not in_table:
            continue
        m = _EPHEM_RE.match(line)
        if not m:
            continue
        rows.append({
            "time": m.group(1),
            "ra": f"{m.group(2)} {m.group(3)} {m.group(4)}",
            "dec": f"{m.group(5)} {m.group(6)} {m.group(7)}",
            "r": float(m.group(8)),
            "delta": float(m.group(10)),
        })
    return rows


def _raw_ephemeris(command, center, start, stop, step, force=False):
    # One Horizons call, verbatim command.
    # @args: force - True bypasses the cache read
    # @return: list of rows (see parse_ephemeris)
    params = {
        "format": "json", "COMMAND": f"'{command}'", "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'OBSERVER'",
        "CENTER": f"'{center}'", "QUANTITIES": "'1,19,20'",
        "START_TIME": f"'{start}'", "STOP_TIME": f"'{stop}'",
        "STEP_SIZE": f"'{step}'",
    }

    def fetch():
        r = requests.get(URL, params=params, timeout=40)
        r.raise_for_status()
        return r.content, "application/json"
    key = f"horizons:{command}:{center}:{start}:{stop}:{step}"
    body, _ = db.http_get(key, "horizons", fetch, force=force)
    text = json.loads(body.decode("utf-8", "replace")).get("result", "")
    return parse_ephemeris(text)


def ephemeris(command, center="Z41", start=None, stop=None, step="1 d",
              force=False):
    # Observer ephemeris for a small body. Periodic comets need the CAP
    # clause (current apparition), so we retry with it when the plain
    # designation finds nothing.
    # @args: command - Horizons target (designation), center - MPC code or
    #        '500@399', start/stop - 'YYYY-MM-DD' strings, step - e.g. '1 d',
    #        force - True bypasses the cache read
    # @return: list of rows (see parse_ephemeris); empty on failure
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc)
    start = start or today.strftime("%Y-%m-%d")
    stop = stop or (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        rows = _raw_ephemeris(command, center, start, stop, step,
                              force=force)
        if not rows and "/" not in command and "DES=" not in command:
            rows = _raw_ephemeris(f"DES= {command}; CAP;", center, start,
                                  stop, step, force=force)
        return rows
    except (requests.RequestException, ValueError) as err:
        logger.warning("Horizons failed for %s: %s", command, err)
        return []
