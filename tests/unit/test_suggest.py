############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: suggestion engine (synthetic targets)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import suggest


def _neo(neocp=True, score=8.0, mag=18.5, alt=65, hours=5, moid=0.01):
    # Synthetic NEO target with known-good properties
    return {"id": "T1", "kind": "neo", "name": "T1", "mag": mag,
            "max_alt": alt, "hours_up": hours, "nf_score": score,
            "neocp": neocp, "moid": moid, "nf_urgency": 50}


def test_neocp_beats_faint_numbered():
    # a bright NEOCP object must outscore a faint numbered asteroid
    good, _ = suggest.score_target(_neo())
    bad, _ = suggest.score_target(_neo(neocp=False, score=2.0, mag=21.0,
                                       alt=35, hours=2, moid=0.4))
    assert good > bad


def test_score_bounds():
    # score stays within 0-100 even with extreme values
    t = _neo(neocp=True, score=10, mag=10, alt=89, hours=12, moid=0.001)
    s, parts = suggest.score_target(t)
    assert 0 <= s <= 100
    for v in parts.values():
        assert v >= 0


def test_hook_rules():
    # potential impactors get the outreach hook
    t = _neo()
    t["impact"] = 0.001
    _, parts = suggest.score_target(t)
    assert parts["hook"] >= 8


def test_history_feedback(tmp_db, fake_cfg):
    # observed-but-unposted gains urgency; posted loses the hook
    t = _neo(neocp=False)
    t["impact"] = 0.01  # gives hook
    s0, p0 = suggest.score_target(t, fake_cfg, tmp_db)
    tmp_db.mark_observed("T1", "neo")
    s1, p1 = suggest.score_target(t, fake_cfg, tmp_db)
    assert p1["urgency"] >= p0["urgency"]
    tmp_db.mark_posted("T1")
    s2, p2 = suggest.score_target(t, fake_cfg, tmp_db)
    assert p2["hook"] == 0.0


def test_why_phrase_bilingual_and_specific():
    t = _neo()
    ph = suggest.why_phrase(t)
    assert "MPC" in ph["es"] and "MPC" in ph["en"]
    t2 = {"kind": "pccp", "pccp_score": 85, "id": "P1"}
    ph2 = suggest.why_phrase(t2)
    assert "85" in ph2["es"]


def test_top_n_sorted(fake_cfg):
    targets = [_neo(neocp=False, score=2.0, mag=21.0), _neo()]
    top, all_scored = suggest.top_n(targets, fake_cfg, None, 1)
    assert len(top) == 1
    assert top[0][1] >= all_scored[1][1]


def test_top_n_diversity(fake_cfg):
    # the Top N should mix kinds when possible (a comet next to the NEOs)
    targets = [_neo(), _neo(), _neo(),
               {"id": "C1", "kind": "comet", "name": "C1", "mag": 11.0,
                "max_alt": 55, "hours_up": 4, "perihelion_date": "2026-08-25"}]
    top, _ = suggest.top_n(targets, fake_cfg, None, 3)
    kinds = {t["kind"] for t, _s, _p, _ph in top}
    assert "comet" in kinds  # not three NEOs
