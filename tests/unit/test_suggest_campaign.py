############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: campaign target scoring (Track V, VA.3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

from nightscribe.core import suggest


class _Cfg:
    def __init__(self, **kw):
        self._d = {"limit_mag": 20.0, "moon_limit_enabled": False}
        self._d.update(kw)

    def get(self, k, default=None):
        return self._d.get(k, default)


def _var(**over):
    t = {"id": "T CrB", "kind": "variable", "name": "T CrB", "mag": 10.1,
         "ra_deg": 239.9, "dec_deg": 25.9,
         "max_alt": 60.0, "safe_max_alt": 58.0, "hours_up": 6.0,
         "window_start": "2026-09-11T22:00", "window_end": "2026-09-12T04:00",
         "variable": {"var_type": "NR", "period_d": 227.55,
                      "epoch_mjd": 55828.4, "max": 2.0, "min": 10.8,
                      "amp": 8.8, "next_extremum": None},
          "campaign": {"id": 1, "name": "T CrB", "overdue_days": 0,
                       "cadence_nights": 1, "never_visited": False,
                       "event": None}}
    t.update(over)
    return t


def _parts(t):
    _score, parts = suggest.score_target(t, _Cfg())
    return parts


def test_variable_scientific_uses_amp_and_brightness():
    bright = _var()
    faint = _var(mag=15.0)
    no_amp = _var(variable={"amp": 0.0, "next_extremum": None})
    assert _parts(bright)["scientific"] > _parts(faint)["scientific"]
    assert _parts(bright)["scientific"] > _parts(no_amp)["scientific"]
    assert _parts(bright)["scientific"] <= 35


def test_campaign_urgency_grows_with_overdue_and_caps():
    c1 = dict(_var()["campaign"], overdue_days=1)
    c5 = dict(_var()["campaign"], overdue_days=5)
    c99 = dict(_var()["campaign"], overdue_days=99)
    assert _parts(_var(campaign=c5))["urgency"] > \
        _parts(_var(campaign=c1))["urgency"]
    assert _parts(_var(campaign=c99))["urgency"] == 20


def test_event_adds_urgency():
    c = dict(_var()["campaign"])
    c["event"] = {"direction": "drop", "delta_mag": 0.8, "filter": "V"}
    assert _parts(_var(campaign=c))["urgency"] == \
        _parts(_var())["urgency"] + 10


def test_extremum_hook():
    v = dict(_var()["variable"])
    v["next_extremum"] = {"kind": "max", "mjd": 61250.0, "days": 3.0}
    assert _parts(_var(variable=v))["hook"] > _parts(_var())["hook"]


def test_campaign_signals_stack_on_other_kinds():
    # a campaign SN keeps its own urgency AND wins the campaign boost (V-b)
    sn = {"id": "SN 2026abc", "kind": "sn", "name": "SN 2026abc",
          "mag": 14.0, "ra_deg": 10.0, "dec_deg": 20.0,
          "max_alt": 50.0, "safe_max_alt": 49.0, "hours_up": 4.0,
          "window_start": "2026-09-11T23:00", "window_end": "2026-09-12T03:00",
          "disc_date": None,
          "campaign": dict(_var()["campaign"], overdue_days=4)}
    plain = dict(sn)
    plain.pop("campaign")
    assert _parts(sn)["urgency"] > _parts(plain)["urgency"]


def _frags(t):
    return suggest._fragments(t, _Cfg())


def test_campaign_fragments_lead():
    t = _var(campaign=dict(_var()["campaign"], overdue_days=4))
    frags = _frags(t)
    assert frags and "Campaña T CrB" in frags[0][0]
    assert "4 noches sin medida" in frags[0][0]
    assert "Campaign T CrB" in frags[0][1]


def test_event_fragment_goes_first():
    c = dict(_var()["campaign"], overdue_days=4,
             event={"direction": "drop", "delta_mag": 0.8, "filter": "V"})
    frags = _frags(_var(campaign=c))
    assert frags[0][0].startswith("¡Posible descenso")
    assert frags[1][0].startswith("Campaña")


def test_never_visited_fragment():
    c = dict(_var()["campaign"], never_visited=True)
    assert "sin ninguna visita" in _frags(_var(campaign=c))[0][0]


def test_extremum_and_period_fragments():
    v = dict(_var()["variable"])
    v["next_extremum"] = {"kind": "max", "mjd": 61250.0, "days": 3.0}
    txt = " · ".join(f[0] for f in _frags(_var(variable=v)))
    assert "Máximo esperado en ~3 días" in txt
    assert "periodo de 227.6 días" in txt


def test_why_phrase_keeps_at_most_three_and_ends_with_period():
    c = dict(_var()["campaign"], overdue_days=4,
             event={"direction": "rise", "delta_mag": 1.2, "filter": "V"})
    v = dict(_var()["variable"])
    v["next_extremum"] = {"kind": "min", "mjd": 61252.0, "days": 5.0}
    phrase = suggest.why_phrase(_var(campaign=c, variable=v), _Cfg())
    assert phrase["es"].endswith(".") and phrase["en"].endswith(".")
    assert phrase["es"].count("·") <= 2
