############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: Explore-window hook prose (3 regressions)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offline regressions for the three broken "Explorar" hook texts.

Each test builds the very enriched dict the GUI receives (an enrich() output
with the planner target carried in), drives narrative.hook(), and asserts the
prose tells the right story — Spanish only, since the English mirror is built
from the same variables. No network, no GUI.
"""

from nightscribe.core import narrative


def _es(e):
    return narrative.hook(e)["es"]


def _en(e):
    return narrative.hook(e)["en"]


# ---- bug 1: an exoplanet transit must not read as an unconfirmed object ----

def test_hook_transit_from_exoplanet_kind():
    t = {"kind": "transit", "name": "55Cnce", "star": "55 Cnc",
         "transit": {"star": "55 Cnc", "depth_mmag": 800.0,
                     "duration_h": 12.0}}
    e = {"type": "exoplanet", "name": "55Cnce", "data": {"unconfirmed": t}}
    es = _es(e)
    assert "55Cnce" in es and "55 Cnc" in es and "transita" in es
    assert "sin confirmar" not in es.lower()
    assert "Objeto aún sin confirmar" not in es
    # the English line carries the numbers, not the Spanish placeholder
    assert "55 Cnce" not in _en(e) and "transits" in _en(e)


def test_hook_transit_from_compact_name_fallthrough():
    # A compact ExoClock name that detect_type could not recognise lands in
    # the small_body/comet unconfirmed block: it must still read as a transit.
    t = {"kind": "transit", "name": "TRAPPIST-1e", "star": "TRAPPIST-1",
         "transit": {"star": "TRAPPIST-1", "depth_mmag": 40.0,
                     "duration_h": 8.5}}
    e = {"type": "small_body", "name": "TRAPPIST-1e",
         "data": {"unconfirmed": t}}
    es = _es(e)
    assert "TRAPPIST-1e" in es and "TRAPPIST-1" in es and "transita" in es
    assert "candidato a cometa" not in es.lower() and "unconfirmed" not in _en(e)


# ---- bug 2: a named SN is confirmed; an AT transient is not ----

def test_hook_named_sn_is_a_supernova_not_unconfirmed():
    # "SN 2026abc" already is a supernova: we track it, we do not investigate it.
    # An optional host in parens must not break the SN/AT split.
    t = {"kind": "sn", "name": "SN 2026abc (NGC 1058)", "host": "NGC 1058",
         "sn_type": "II"}
    e = {"type": "sn", "name": "SN 2026abc (NGC 1058)",
         "data": {"unconfirmed": t}}
    es = _es(e)
    assert "supernova" in es.lower()
    assert "NGC 1058" in es and "tipo II" in es
    assert "Seguimos" not in es            # it is not an "object we follow"
    assert "aún por confirmar" not in es   # it is already a supernova
    assert "Estudiamos esta supernova" in es


def test_hook_at_transient_is_yet_unconfirmed():
    # "AT ####" is a transient awaiting confirmation: we investigate it.
    t = {"kind": "sn", "name": "AT2026yvy", "host": "NGC 5128",
         "sn_type": "II"}
    e = {"type": "sn", "name": "AT2026yvy", "data": {"unconfirmed": t}}
    es = _es(e)
    assert "supernova" in es.lower()
    assert "aún por confirmar" in es
    assert "Investigamos" in es
    assert "NGC 5128" in es and "tipo II" in es


# ---- bug 3: an unconfirmed NEO is not a comet candidate ----

def test_hook_neo_fallthrough_is_neo_not_comet():
    # An NEO with no SBDB entry lands in the small_body/comet unconfirmed
    # block: it is a near-Earth object, not a comet candidate.
    t = {"kind": "neo", "name": "P10x99x"}
    e = {"type": "neo", "name": "P10x99x", "data": {"unconfirmed": t}}
    es = _es(e)
    assert "P10x99x" in es
    assert "cercano a la Tierra" in es      # it is an NEO
    assert "candidato a cometa" not in es.lower() and "comet candidate" not in _en(e)
    assert "Objeto aún sin confirmar" not in es  # the NEO branch beat the generic


def test_hook_neo_generic_path_is_not_a_comet_either():
    # The type="neo" fallback (enrich returns kind as type, not small_body)
    # must read the same way — NEO, never comet.
    t = {"kind": "neo", "name": "2026 QK (443089)"}
    e = {"type": "neo", "name": "2026 QK (443089)", "data": {"unconfirmed": t}}
    es = _es(e)
    assert "2026 QK (443089)" in es and "cercano a la Tierra" in es
    assert "candidato a cometa" not in es.lower()


# ---- sanity: the comet candidate still reads as a comet candidate ----

def test_hook_comet_candidate_still_reads_as_comet():
    t = {"kind": "comet", "name": "C/2026 F1000 (example)"}
    e = {"type": "small_body", "name": "C/2026 F1000 (example)",
         "data": {"unconfirmed": t}}
    es = _es(e)
    assert "candidato a cometa" in es.lower() and "C/2026 F1000 (example)" in es
    assert "cercana a la Tierra" not in es  # it is not an NEO
