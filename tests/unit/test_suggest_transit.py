############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: transit card & why-phrase (Track D, subplan 1)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The transit selection card leads with the observer's real decision:
"fits entirely in your night (baselines included): start capturing at
HH:MM" and "detectable with your telescope"; the ExoClock priority is
explained didactically. A transit whose full capture window overflows the
night is warned about and penalised in the score.
"""

import datetime

from nightscribe.core import suggest

_MID = datetime.datetime(2026, 8, 22, 0, 20, tzinfo=datetime.timezone.utc)


def _transit(baseline_fits=True, priority="high", min_scope=8.0,
             with_window=True):
    # Synthetic transit target with the Track-D enrichment fields.
    tr = {"star": "WASP-999", "depth_mmag": 100.0, "duration_h": 2.0,
          "v_mag": 11.5, "priority": priority, "min_telescope_in": min_scope,
          "ingress": _MID - datetime.timedelta(hours=1),
          "mid": _MID,
          "egress": _MID + datetime.timedelta(hours=1),
          "baseline_fits": baseline_fits}
    if with_window:
        tr["capture_start"] = _MID - datetime.timedelta(hours=1, minutes=30)
        tr["capture_end"] = _MID + datetime.timedelta(hours=1, minutes=30)
        tr["cadence_max_s"] = 360
        tr["exp_recommended_s"] = 60
    return {"id": "WASP-999 b", "kind": "transit", "name": "WASP-999 b",
            "mag": 11.5, "max_alt": 70.0, "transit": tr}


class _Cfg:
    # config-like stub with the telescope aperture set
    def __init__(self, aperture_inches):
        self._v = {"limit_mag": 20.0, "aperture_inches": aperture_inches}

    def get(self, k, d=None):
        return self._v.get(k, d)


# ---------------- capture-start phrase ----------------

def test_phrase_leads_with_capture_start_time():
    ph = suggest.why_phrase(_transit())
    assert "22:50" in ph["es"]
    assert "empieza a capturar" in ph["es"].lower()
    assert "Cabe entero en tu noche" in ph["es"]
    assert "22:50" in ph["en"]
    assert "start capturing" in ph["en"].lower()
    assert "fits entirely in your night" in ph["en"].lower()


def test_phrase_warns_when_baseline_overflows():
    ph = suggest.why_phrase(_transit(baseline_fits=False))
    assert "⚠" in ph["es"] and "no cabe" in ph["es"]
    assert "⚠" in ph["en"] and "does not fit" in ph["en"]


def test_phrase_without_window_falls_back_to_depth():
    # synthetic/old targets without the Track-D fields keep the classic
    # depth-led phrase
    ph = suggest.why_phrase(_transit(with_window=False))
    assert "10.0%" in ph["es"]


# ---------------- score penalty ----------------

def test_score_penalty_when_baseline_overflows():
    ok, parts_ok = suggest.score_target(_transit(baseline_fits=True))
    bad, parts_bad = suggest.score_target(_transit(baseline_fits=False))
    assert parts_ok["observability"] - parts_bad["observability"] >= 3.9
    assert bad < ok


# ---------------- detectable verdict ----------------

def test_detectable_with_own_telescope():
    ph = suggest.why_phrase(_transit(min_scope=8.0), _Cfg(10.0))
    assert "Detectable con tu telescopio de 10″" in ph["es"]
    assert "Detectable with your 10-inch telescope" in ph["en"]


def test_not_detectable_warns():
    ph = suggest.why_phrase(_transit(min_scope=12.0), _Cfg(8.0))
    assert "⚠" in ph["es"] and "12″" in ph["es"] and "8″" in ph["es"]
    assert "⚠" in ph["en"]


def test_no_aperture_no_verdict():
    # without the user's aperture there is no verdict (never a guess)
    ph = suggest.why_phrase(_transit(), None)
    assert "Detectable" not in ph["es"]


# ---------------- didactic priority ----------------

def test_priority_explained_didactically():
    # not the bare word "high": what ExoClock is and what the measurement
    # is for (the Ariel mission schedule)
    ph = suggest.why_phrase(_transit(priority="high"))
    assert "ExoClock" in ph["es"] and "Ariel" in ph["es"]
    assert "ExoClock" in ph["en"] and "Ariel" in ph["en"]


def test_medium_priority_skips_didactic_fragment():
    ph = suggest.why_phrase(_transit(priority="medium", min_scope=None))
    assert "Prioridad alta" not in ph["es"]
