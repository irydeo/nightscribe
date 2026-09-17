############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: sky events engine (Track SC2, SC0)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""`core/skyevents.events` — the sky calendar's engine. Pure local maths,
no network: the tests pin the contract keys, the family invariants and a
regression table validated against almanacs + astropy (see
docs/PLANS/sky-calendar.md §Estado de la sesión).

The opposition/conjunction families are ECLIPTIC LONGITUDE crossings —
the regression tests below include Saturn 2026-10-04 (peak elongation
177.28 deg with beta=-2.7 deg: any elongation-gated implementation loses
it) and the absence of a Mars opposition in 2026 (its January event is
the 01-09 CONJUNCTION; the next opposition is 2027-02-19).
"""

import datetime

import pytest

from nightscribe.core import skyevents

# the author's observatory (Irydeo, MPC Z41) — same as config.DEFAULTS
LAT, LON = 40.55, -3.37


@pytest.fixture(scope="module")
def year2026():
    # One full-year scan shared by the regression tests (1.3 s once,
    # instead of per test).
    return skyevents.events(LAT, LON, from_date=datetime.date(2026, 1, 1),
                            days=365)


def _by_kind(events, kind, obj=None):
    # @return: the events of `kind` (and of object `obj` when given)
    return [e for e in events if e["kind"] == kind
            and (obj is None or obj in e["objects"])]


def _day(ev):
    # @return: the event's UTC date (day precision is the contract)
    return ev["date"].date()


# ---------------- contract ----------------

def test_contract_keys_and_sorting(year2026):
    assert year2026, "the engine found nothing in a whole year"
    for ev in year2026:
        for key in ("jd", "date", "kind", "icon", "objects", "mag",
                    "sep_deg", "alt_deg", "tonight"):
            assert key in ev, f"missing contract key {key}"
        assert ev["objects"], "every event names its object(s)"
    jds = [e["jd"] for e in year2026]
    assert jds == sorted(jds), "events must come sorted by jd"


def test_every_family_appears_in_a_year(year2026):
    # a full year must show every family at least once
    kinds = {e["kind"] for e in year2026}
    for kind in ("new_moon", "full_moon", "first_quarter", "last_quarter",
                 "perigee", "apogee", "moon_conjunction",
                 "planet_conjunction", "opposition", "max_elongation",
                 "sun_conjunction", "meteor_shower"):
        assert kind in kinds, f"family {kind} missing from a year scan"


# ---------------- regression table (validated 2026-09-17) ----------------

def test_jupiter_opposition_2026_01_10(year2026):
    opps = _by_kind(year2026, "opposition", "jupiter")
    assert len(opps) == 1
    assert abs((_day(opps[0]) - datetime.date(2026, 1, 10)).days) <= 1


def test_neptune_opposition_2026_09_26(year2026):
    opps = _by_kind(year2026, "opposition", "neptune")
    assert len(opps) == 1                     # no doubled event
    assert abs((_day(opps[0]) - datetime.date(2026, 9, 26)).days) <= 1


def test_uranus_opposition_2026_11_25(year2026):
    opps = _by_kind(year2026, "opposition", "uranus")
    assert len(opps) == 1                     # no doubled event
    assert abs((_day(opps[0]) - datetime.date(2026, 11, 25)).days) <= 1


def test_saturn_opposition_2026_10_04(year2026):
    # THE regression: beta=-2.7 deg caps the elongation peak at 177.28 deg,
    # so an elongation gate never fires; the longitude crossing does.
    opps = _by_kind(year2026, "opposition", "saturn")
    assert len(opps) == 1
    assert abs((_day(opps[0]) - datetime.date(2026, 10, 4)).days) <= 1
    # the reported elongation is the true value, not a failure
    assert 176.0 < opps[0]["elong_deg"] < 180.0


def test_no_mars_opposition_in_2026(year2026):
    # Mars's January event is the 01-09 CONJUNCTION (2.40 AU). The previous
    # opposition was 2025-01-16, the next 2027-02-19 — none in 2026.
    assert _by_kind(year2026, "opposition", "mars") == []
    conj = _by_kind(year2026, "sun_conjunction", "mars")
    assert len(conj) == 1
    assert abs((_day(conj[0]) - datetime.date(2026, 1, 9)).days) <= 1
    assert conj[0]["detail"] == "superior"


def test_oppositions_only_outer_planets(year2026):
    for ev in _by_kind(year2026, "opposition"):
        assert ev["objects"][0] in ("mars", "jupiter", "saturn",
                                    "uranus", "neptune")


# ---------------- family invariants ----------------

def test_moon_phase_spacing(year2026):
    # consecutive phase events of the same kind are one synodic month apart
    fulls = sorted(e["jd"] for e in _by_kind(year2026, "full_moon"))
    assert len(fulls) >= 12
    for a, b in zip(fulls, fulls[1:]):
        assert abs((b - a) - skyevents.SYNODIC) < 0.6


def test_apsides_alternate(year2026):
    # perigee and apogee alternate, an anomalistic half-month apart —
    # nominally ~13.9 d but the evection stretches it: the physical 2026
    # range is ~11.9–15.9 d (measured, not guessed)
    aps = [e for e in year2026 if e["kind"] in ("perigee", "apogee")]
    assert len(aps) >= 24
    for a, b in zip(aps, aps[1:]):
        assert a["kind"] != b["kind"], "apsides must alternate"
        assert 11.5 < (b["jd"] - a["jd"]) < 16.2


def test_max_elongation_bounds(year2026):
    for ev in _by_kind(year2026, "max_elongation"):
        name = ev["objects"][0]
        assert name in ("mercury", "venus")
        limit = 28.5 if name == "mercury" else 48.0
        assert skyevents.MAXEL_MIN_DEG <= ev["elong_deg"] <= limit
        assert ev["side"] in ("east", "west")


def test_sun_conjunctions_detail(year2026):
    for ev in _by_kind(year2026, "sun_conjunction"):
        assert ev["detail"] in ("inferior", "superior")
        # inferior only for the inner pair
        if ev["detail"] == "inferior":
            assert ev["objects"][0] in ("mercury", "venus")


def test_moon_conjunction_closeness(year2026):
    for ev in _by_kind(year2026, "moon_conjunction"):
        assert ev["sep_deg"] is not None
        assert ev["sep_deg"] <= skyevents.MOON_CONJ_DEG
        assert ev["objects"][0] == "moon"


def test_meteor_perseids_peak(year2026):
    p = _by_kind(year2026, "meteor_shower", "perseids")
    assert len(p) == 1
    assert abs((_day(p[0]) - datetime.date(2026, 8, 12)).days) <= 1
    assert p[0]["zhr"] == 100


# ---------------- eclipse anchors (approximate by design) ----------------

def test_lunar_eclipse_2026_03_03():
    # total lunar eclipse; the engine flags it within a day, no contacts
    evs = skyevents.events(LAT, LON, from_date=datetime.date(2026, 2, 15),
                           days=30)
    lun = _by_kind(evs, "lunar_eclipse")
    assert len(lun) == 1
    assert abs((_day(lun[0]) - datetime.date(2026, 3, 3)).days) <= 1
    assert lun[0]["detail"] in ("total", "partial")


def test_solar_eclipse_2026_08_12():
    # total solar eclipse (visible from Spain!); flagged within a day
    evs = skyevents.events(LAT, LON, from_date=datetime.date(2026, 7, 15),
                           days=40)
    sol = _by_kind(evs, "solar_eclipse")
    assert len(sol) == 1
    assert abs((_day(sol[0]) - datetime.date(2026, 8, 12)).days) <= 1
    assert sol[0]["detail"] in ("total", "annular", "partial")
