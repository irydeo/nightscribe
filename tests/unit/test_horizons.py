############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: JPL Horizons robustness
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The ephemeris source must survive JPL having a bad moment. JPL returns
503 in bursts (the log of a real evening is full of them), and the stack used
to die with "no ephemeris" on the first one. What is proven here: a transient
failure is retried, a 4xx is not, an empty 200 is not left in the cache for
its whole TTL, the designation gets the space Horizons needs, and the failure
comes back with a REASON the caller can say out loud.
"""

import requests
import pytest

from nightscribe.core.sources import horizons


class _Db:
    # A cache that never hits and records what is deleted.
    def __init__(self):
        self.deleted = []

    def http_get(self, key, source, fetch_fn, force=False):
        return fetch_fn()

    def cache_delete(self, key):
        self.deleted.append(key)


def _resp(status, body=b"{}"):
    class _R:
        status_code = status
        content = body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"{self.status_code}", response=self)
    return _R()


def test_the_designation_gets_the_space_horizons_needs():
    # Horizons resolves "2026 PY9" and NOT "2026PY9" (it reads it as
    # DES= 2026PY9 and finds nothing). A hand-typed or imported name may
    # lack the space, and that alone made a valid object look unknown.
    assert horizons._normalize("2026PY9") == "2026 PY9"
    assert horizons._normalize("2026 PY9") == "2026 PY9"
    assert horizons._normalize("2026AB") == "2026 AB"
    # a comet, a packed code or an explicit clause is left alone
    assert horizons._normalize("P/2020 G1") == "P/2020 G1"
    assert horizons._normalize("K26A020") == "K26A020"
    assert horizons._normalize("DES= 10P; CAP;") == "DES= 10P; CAP;"
    assert horizons._normalize("") == ""


def test_transient_failures_are_told_from_our_own_mistakes():
    assert horizons._is_transient(
        requests.HTTPError(response=_resp(503))) is True
    assert horizons._is_transient(
        requests.HTTPError(response=_resp(429))) is True
    assert horizons._is_transient(
        requests.HTTPError(response=_resp(400))) is False
    assert horizons._is_transient(requests.Timeout()) is True
    assert horizons._is_transient(requests.ConnectionError()) is True


def test_a_503_is_retried_until_it_answers(monkeypatch):
    monkeypatch.setattr(horizons, "db", _Db())
    monkeypatch.setattr(horizons.time, "sleep", lambda _s: None)
    tries = {"n": 0}

    def fetch():
        tries["n"] += 1
        if tries["n"] < 3:
            raise requests.HTTPError(response=_resp(503))
        return b"ok", "application/json"

    body, _ = horizons._fetch_with_retry("k", "horizons", fetch)
    assert body == b"ok" and tries["n"] == 3


def test_a_400_is_not_retried(monkeypatch):
    monkeypatch.setattr(horizons, "db", _Db())
    monkeypatch.setattr(horizons.time, "sleep", lambda _s: None)
    tries = {"n": 0}

    def fetch():
        tries["n"] += 1
        raise requests.HTTPError(response=_resp(400))

    with pytest.raises(requests.HTTPError):
        horizons._fetch_with_retry("k", "horizons", fetch)
    assert tries["n"] == 1          # our request is wrong: trying again is waste


def test_an_empty_reply_is_not_left_in_the_cache(monkeypatch):
    # A 200 with no table is not worth keeping: left there it answers
    # "nothing" for the whole 12 h TTL.
    db = _Db()
    monkeypatch.setattr(horizons, "db", db)
    monkeypatch.setattr(horizons.requests, "get",
                        lambda *a, **k: _resp(200, b'{"result": ""}'))
    rows = horizons._raw_ephemeris("2026 PY9", "Z41", "2026-08-16",
                                   "2026-08-17", "1 m")
    assert rows == []
    assert db.deleted


def test_the_failure_comes_back_with_a_reason(monkeypatch):
    monkeypatch.setattr(horizons, "db", _Db())
    monkeypatch.setattr(horizons.time, "sleep", lambda _s: None)
    monkeypatch.setattr(horizons.requests, "get", lambda *a, **k: _resp(503))
    rows, reason = horizons.ephemeris_ex("2026 PY9", center="Z41",
                                         start="2026-08-16",
                                         stop="2026-08-17")
    assert rows == [] and reason == "http 503"


# ------------------------------------------------- the predicted magnitude

# A real reply (2026 PY9, QUANTITIES '9'): the row ends with the magnitude
# and the surface brightness, and the marker columns sit between the time and
# them. Reproduced verbatim so the parser is pinned to what JPL sends.
_MAG_ASTEROID = """
 Date__(UT)__HR:MN       APmag   S-brt
**************************************
$$SOE
 2026-Oct-06 00:00      22.208    n.a.
 2026-Oct-06 06:00 Cm   22.216    n.a.
 2026-Oct-06 12:00 *m   22.225    n.a.
$$EOE
"""

# A comet (C/2023 A3): the same query answers T-mag / N-mag instead.
_MAG_COMET = """
 Date__(UT)__HR:MN       T-mag   N-mag
**************************************
$$SOE
 2026-Oct-06 00:00      18.764    n.a.
 2026-Oct-06 06:00 Cm   18.766    n.a.
$$EOE
"""

# And an object whose magnitude Horizons cannot compute.
_MAG_NONE = """
 Date__(UT)__HR:MN       APmag   S-brt
**************************************
$$SOE
 2026-Oct-06 00:00        n.a.    n.a.
 2026-Oct-06 06:00 Cm     n.a.    n.a.
$$EOE
"""


def test_the_magnitude_is_read_with_its_band():
    # The magnitude is the second-to-last token whatever the marker columns,
    # and the band is read from the reply's own header: the same query says
    # APmag (V) for an asteroid and T-mag for a comet, and a band invented
    # from the object's type would be a guess.
    rows, band = horizons.parse_magnitude(_MAG_ASTEROID)
    assert band == "V"
    assert [r["mag"] for r in rows] == [22.208, 22.216, 22.225]
    assert rows[1]["time"] == "2026-Oct-06 06:00"
    rows, band = horizons.parse_magnitude(_MAG_COMET)
    assert band == "T"
    assert [r["mag"] for r in rows] == [18.764, 18.766]


def test_a_magnitude_horizons_cannot_compute_is_not_a_zero():
    # Horizons answers "n.a." (and the surface brightness after it): the row
    # must come back with no figure, never with the surface brightness read
    # as if it were the magnitude.
    rows, band = horizons.parse_magnitude(_MAG_NONE)
    assert band == "V"
    assert [r["mag"] for r in rows] == [None, None]


def test_the_magnitude_is_cached_under_its_own_key(monkeypatch):
    # A separate call (QUANTITIES '9') and a key of its own: an entry written
    # before this call existed has no magnitude column at all, and parsing it
    # would report "the ephemeris has no magnitude" for a whole TTL.
    keys = []

    class _Cache(_Db):
        def http_get(self, key, source, fetch_fn, force=False):
            keys.append(key)
            return fetch_fn()

    monkeypatch.setattr(horizons, "db", _Cache())
    body = ('{"result": "' + _MAG_ASTEROID.replace("\n", "\\n")
            + '"}').encode()
    monkeypatch.setattr(horizons.requests, "get",
                        lambda *a, **k: _resp(200, body))
    rows, band, reason = horizons.magnitude_rows(
        "2026 PY9", center="Z41", start="2026-10-06", stop="2026-10-07",
        step="6 h")
    assert reason == "" and band == "V" and rows
    assert keys and keys[0].startswith("horizons:mag:2026 PY9:Z41:")


def test_the_magnitude_comes_back_with_its_reason(monkeypatch):
    # The same contract as the position: a failure is not a silent empty list.
    monkeypatch.setattr(horizons, "db", _Db())
    monkeypatch.setattr(horizons.time, "sleep", lambda _s: None)
    monkeypatch.setattr(horizons.requests, "get", lambda *a, **k: _resp(503))
    rows, band, reason = horizons.magnitude_rows("2026 PY9", center="Z41",
                                                 start="2026-10-06",
                                                 stop="2026-10-07")
    assert rows == [] and band is None and reason == "http 503"
