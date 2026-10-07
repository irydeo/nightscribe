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
import time

import requests

from ..db import db

logger = logging.getLogger(__name__)

URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

# HTTP statuses that mean "JPL is having a bad moment", not "our request is
# wrong": worth another try. A 4xx is our fault and retrying only wastes the
# observer's time.
_TRANSIENT_STATUS = (429, 500, 502, 503, 504)


def _is_transient(err):
    # @args: err - a requests exception
    # @return: True when the failure is worth retrying
    if isinstance(err, requests.HTTPError) and err.response is not None:
        return err.response.status_code in _TRANSIENT_STATUS
    # timeouts and connection errors have no response: JPL unreachable
    return isinstance(err, (requests.Timeout, requests.ConnectionError))


def _fetch_with_retry(key, source, fetch, force=False, attempts=3,
                      backoff=(1.0, 3.0)):
    # One cached request, retried ONLY on a transient failure. db.http_get
    # does not store a failed fetch, so each attempt goes back to the network;
    # a success is cached and the next caller is instant.
    # @args: key/source/fetch/force - as db.http_get, attempts - tries,
    #        backoff - seconds to wait before the 2nd, 3rd... try
    # @return: (body bytes, content_type)
    last = None
    for attempt in range(max(1, int(attempts))):
        try:
            return db.http_get(key, source, fetch, force=force)
        except requests.RequestException as err:
            last = err
            if not _is_transient(err) or attempt >= attempts - 1:
                raise
            wait = backoff[min(attempt, len(backoff) - 1)]
            logger.info("Horizons transient failure (%s); retrying in %.0fs",
                        err, wait)
            time.sleep(wait)
    raise last


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


# The magnitude-only table (QUANTITIES '9') ends every row with the magnitude
# and the surface brightness (an asteroid: APmag, S-brt) or with the total and
# the nuclear magnitude (a comet: T-mag, N-mag). The MAGNITUDE is therefore
# the SECOND-TO-LAST token whatever the marker columns in between, and the
# header line says which figure it is.
_MAG_ROW_RE = re.compile(r"^\s*(\d{4}-\w{3}-\d{2}\s+\d{2}:\d{2})\b")
_MAG_COL_RE = re.compile(r"\b([A-Za-z]{1,2}-?mag)\b")


def _magnitude_band(column):
    # @args: column - the Horizons column name ("APmag", "Vmag", "T-mag"...)
    # @return: the band the figure is in: "V" for the apparent visual
    #          magnitude (Horizons computes it as V for an asteroid), "T" for
    #          a comet's total magnitude, else the column's own name.
    # The name is read from the reply instead of assumed: the same query
    # answers "APmag" for 2026 PY9 and "T-mag" for C/2023 A3, and a band
    # invented from the object's type would be a guess.
    c = str(column or "").strip().lower()
    if c in ("apmag", "vmag", "r-mag"):
        return "V"
    if c in ("t-mag", "tmag"):
        return "T"
    return str(column or "").strip() or None


def parse_magnitude(result_text):
    # The magnitude table of a Horizons OBSERVER reply with QUANTITIES '9'.
    # @args: result_text - the "result" field of the Horizons JSON
    # @return: (rows, band) with rows = [{"time", "mag"}] (mag None when
    #          Horizons answers "n.a.": it cannot compute it) and band = "V",
    #          "T" or the column's own name.
    rows = []
    band = None
    in_table = False
    for line in result_text.splitlines():
        if "$$SOE" in line:
            in_table = True
            continue
        if "$$EOE" in line:
            break
        if not in_table:
            if band is None and "Date__" in line:
                m = _MAG_COL_RE.search(line)
                if m:
                    band = _magnitude_band(m.group(1))
            continue
        if not _MAG_ROW_RE.match(line):
            continue
        toks = line.split()
        # date + time + the two magnitude columns, at least
        if len(toks) < 4:
            continue
        try:
            mag = float(toks[-2])
        except ValueError:
            mag = None                 # "n.a.": not a figure, not a zero
        rows.append({"time": f"{toks[0]} {toks[1]}", "mag": mag})
    return rows, band


def magnitude_rows(command, center="", start=None, stop=None, step="1 d",
                   force=False):
    # The object's predicted magnitude over a window, from JPL Horizons.
    # A call of its own (QUANTITIES '9') instead of squeezing the column into
    # the RA/Dec table: the position parser is delicate and adding a column
    # would renumber every field it matches. Two cached requests cost nothing
    # and the position path cannot break because of a magnitude.
    # @args: as ephemeris_ex
    # @return: (rows, band, reason) with reason "" on success
    center = center or "500"
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc)
    start = start or today.strftime("%Y-%m-%d")
    stop = stop or (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    name = _normalize(command)

    def one(clause):
        params = {
            "format": "json", "COMMAND": f"'{clause}'", "OBJ_DATA": "'NO'",
            "MAKE_EPHEM": "'YES'", "EPHEM_TYPE": "'OBSERVER'",
            "CENTER": f"'{center}'", "QUANTITIES": "'9'",
            "START_TIME": f"'{start}'", "STOP_TIME": f"'{stop}'",
            "STEP_SIZE": f"'{step}'",
        }

        def fetch():
            r = requests.get(URL, params=params, timeout=40)
            r.raise_for_status()
            return r.content, "application/json"
        # The key says WHICH quantity this cache entry holds: an entry written
        # before this call existed has no magnitude column at all, and parsing
        # it would report "the ephemeris has no magnitude" for 12 h.
        key = (f"horizons:mag:{clause}:{center}:{start}:{stop}:{step}")
        body, _ = _fetch_with_retry(key, "horizons", fetch, force=force)
        return parse_magnitude(
            json.loads(body.decode("utf-8", "replace")).get("result", ""))

    try:
        rows, band = _with_fallbacks(name, one)
        return rows, band, "" if rows else "unresolved"
    except requests.HTTPError as err:
        code = err.response.status_code if err.response is not None else "?"
        logger.warning("Horizons magnitude failed for %s: HTTP %s", name, code)
        return [], None, f"http {code}"
    except requests.RequestException as err:
        logger.warning("Horizons magnitude failed for %s: %s", name, err)
        return [], None, ("timeout" if isinstance(err, requests.Timeout)
                          else "network")
    except ValueError:
        return [], None, "bad reply"


def magnitude(command, center="", start=None, stop=None, step="1 d",
              force=False):
    # @return: the rows alone (see magnitude_rows)
    return magnitude_rows(command, center=center, start=start, stop=stop,
                          step=step, force=force)[0]


def _with_fallbacks(name, call):
    # @args: name - a normalised designation, call - callable(clause) -> rows
    # @return: the rows of the first clause that answers. A comet needs the
    #          CAP clause (the current apparition); an asteroid does NOT, and
    #          "DES= <asteroid>; CAP;" answers "no matches", so the plain DES
    #          clause goes first and CAP is the last resort.
    rows = call(name)
    if rows or "/" in name or "DES=" in name:
        return rows
    rows = call(f"DES= {name};")
    if rows:
        return rows
    return call(f"DES= {name}; CAP;")


def _normalize(command):
    # @args: command - a designation as stored or typed ("2026PY9",
    #        "2026 PY9", "P/2020 G1", "K26A020", "DES= 10P; CAP;")
    # @return: the designation with the space Horizons wants between the
    #          year and the letter code
    # Horizons resolves "2026 PY9" and does NOT resolve "2026PY9" (it reads
    # the latter as DES= 2026PY9 and finds nothing). The project stores the
    # spaced form, but a hand-typed name or an imported one may not, and that
    # alone made a valid object look unknown.
    s = str(command or "").strip()
    if not s or "/" in s or "=" in s or " " in s:
        return s               # a comet, a packed code or an explicit clause
    m = re.match(r"^(\d{4})([A-Za-z]{1,2}\d{0,3})$", s)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return s


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
    body, _ = _fetch_with_retry(key, "horizons", fetch, force=force)
    rows = parse_ephemeris(
        json.loads(body.decode("utf-8", "replace")).get("result", ""))
    if not rows:
        # A 200 with no table is not worth keeping: left in the cache it
        # answers "nothing" for the whole 12 h TTL, which is how a transient
        # bad reply turned into "no ephemeris" all evening.
        try:
            db.cache_delete(key)
        except Exception as err:      # a cache we cannot clean is not fatal
            logger.warning("could not drop the empty ephemeris cache: %s",
                           err)
    return rows


def ephemeris_ex(command, center="", start=None, stop=None, step="1 d",
                 force=False):
    # Observer ephemeris for a small body, with the REASON when it cannot be
    # had, so the caller can say what failed instead of a generic "no
    # ephemeris".
    # @args: command - Horizons target (designation), center - MPC code
    #        (empty means "no site": geocenter "500"), start/stop -
    #        'YYYY-MM-DD' strings, step - e.g. '1 d', force - True bypasses
    #        the cache read
    # @return: (rows, reason) with reason "" on success, else a short code:
    #          "http 503" | "timeout" | "network" | "bad reply" |
    #          "unresolved"
    center = center or "500"
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc)
    start = start or today.strftime("%Y-%m-%d")
    stop = stop or (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    name = _normalize(command)
    try:
        rows = _with_fallbacks(
            name, lambda clause: _raw_ephemeris(clause, center, start, stop,
                                                step, force=force))
        return rows, "" if rows else "unresolved"
    except requests.HTTPError as err:
        code = err.response.status_code if err.response is not None else "?"
        logger.warning("Horizons failed for %s: HTTP %s", name, code)
        return [], f"http {code}"
    except requests.RequestException as err:
        logger.warning("Horizons failed for %s: %s", name, err)
        return [], ("timeout" if isinstance(err, requests.Timeout)
                    else "network")
    except ValueError:
        return [], "bad reply"


def ephemeris(command, center="", start=None, stop=None, step="1 d",
              force=False):
    # The rows alone, for the callers that only want them.
    # @return: list of rows (see parse_ephemeris); empty on failure
    return ephemeris_ex(command, center=center, start=start, stop=stop,
                        step=step, force=force)[0]
