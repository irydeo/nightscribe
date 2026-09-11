############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: HADS scoring (subplan A.2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""HADS scoring mirrors the transit pattern: scientific weight from the
amplitude and brightness, observability bonus for complete cycles fitting
tonight (and a penalty when the 2-period session does not fit), urgency from
the programme legend (period change / unobserved / coverage — never stacked),
and the outreach hook for prototypes, big swings and multiperiodic stars.
"""

from nightscribe.core import suggest


def _hads(name="TEST One", mag=11.0, amp=0.6, period_h=1.9, cycles=3.0,
          session_fits=True, priority=None, observed=True,
          multiperiodic=False, covered=True, max_alt=70.0, hours_up=6.0):
    # Synthetic hads target as planner._hads_targets builds it (subplan A.1)
    return {"id": name, "kind": "hads", "name": name, "mag": mag,
            "max_alt": max_alt, "safe_max_alt": max_alt, "hours_up": hours_up,
            "hads": {"period_h": period_h, "max": mag - amp / 2,
                     "min": mag + amp / 2, "amp": amp, "cycles": cycles,
                     "cadence_s": 570.0, "session_req_h": 2 * period_h,
                     "session_fits": session_fits, "exp_s": 60,
                     "priority": priority, "observed": observed,
                     "multiperiodic": multiperiodic, "non_radial": False,
                     "covered_this_month": covered}}


class _Cfg:
    # config-like stub (moon constraint disabled by default)
    def get(self, k, d=None):
        return {"limit_mag": 20.0}.get(k, d)


# ---------------- scientific ----------------

def test_scientific_prefers_big_amplitudes_and_bright_stars():
    big = suggest._scientific(_hads(amp=0.9, mag=10.0))
    small = suggest._scientific(_hads(amp=0.3, mag=14.0))
    assert 0 < small < big <= 35


# ---------------- observability ----------------

def test_observability_bonus_grows_with_cycles():
    cfg = _Cfg()
    many = suggest._observability(_hads(cycles=5.0), cfg)
    few = suggest._observability(_hads(cycles=1.0), cfg)
    assert few < many


def test_observability_penalises_a_session_that_does_not_fit():
    cfg = _Cfg()
    # dim, low target: both scores stay below the 30-cap so the penalty shows
    base = dict(max_alt=35.0, mag=13.5, cycles=2.0, hours_up=4.0)
    fits = suggest._observability(_hads(session_fits=True, **base), cfg)
    nope = suggest._observability(_hads(session_fits=False, **base), cfg)
    assert fits - nope == 4.0


# ---------------- urgency (never stacked) ----------------

def test_urgency_period_change_beats_possible():
    red = suggest._urgency(_hads(priority="period_change"))
    orange = suggest._urgency(_hads(priority="period_change_possible"))
    assert red == 12 and orange == 8


def test_urgency_unobserved_and_coverage_gap():
    assert suggest._urgency(_hads(observed=False)) == 6
    assert suggest._urgency(_hads(covered=False)) == 10
    assert suggest._urgency(_hads()) == 0


def test_urgency_signals_do_not_stack():
    both = suggest._urgency(_hads(priority="period_change", covered=False))
    assert both == 12                       # max, not 12 + 10


# ---------------- hook ----------------

def test_hook_famous_amplitude_multiperiodic():
    famous = suggest._hook(_hads(name="CY Aqr", amp=0.4))
    big = suggest._hook(_hads(amp=0.6))
    multi = suggest._hook(_hads(multiperiodic=True, amp=0.4))
    plain = suggest._hook(_hads(amp=0.4))
    assert famous == 6 and big == 4 and multi == 3 and plain == 0


# ---------------- total ----------------

def test_score_target_total_and_caps():
    t = _hads(name="CY Aqr", amp=0.9, priority="period_change",
              multiperiodic=True)
    score, parts = suggest.score_target(t, _Cfg())
    assert 0 < score <= 100
    assert parts["scientific"] <= 35 and parts["observability"] <= 30
    assert parts["urgency"] <= 20 and parts["hook"] <= 15
