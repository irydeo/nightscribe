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
    # ADR-036 J3: the feedback reads PROJECT activity now (the old
    # manual marks were never written). Active/recent project -> the
    # novelty hook dies; long-finished project -> revisit urgency grows.
    import time
    from nightscribe.core import project as proj_mod
    t = _neo(neocp=False)
    t["impact"] = 0.01  # gives hook
    s0, p0 = suggest.score_target(t, fake_cfg, tmp_db)
    p = proj_mod.create(tmp_db, "neo", "T1", {})
    _s1, p1 = suggest.score_target(t, fake_cfg, tmp_db)
    assert p1["hook"] == 0.0                     # active project
    proj_mod.close(tmp_db, p["id"], "found")
    old = time.time() - 365 * 86400
    tmp_db.execute(
        "UPDATE projects SET created=?, updated=?, closed_at=?",
        (old, old, old))
    tmp_db.commit()
    _s2, p2 = suggest.score_target(t, fake_cfg, tmp_db)
    assert p2["hook"] > 0 or p2["urgency"] > p0["urgency"]
    assert p2["urgency"] >= p0["urgency"]        # the revisit boost


def test_commitment_rows_skip_the_novelty_decay(tmp_db, fake_cfg):
    # ADR-036 J3: campaign/vigil/AAVSO rows always carry a project — the
    # active project is their normal state, not a reason to shut up
    from nightscribe.core import project as proj_mod
    proj_mod.create(tmp_db, "variable", "T1", {})
    t = {"id": "T1", "kind": "variable", "name": "T1", "mag": 10.0,
         "variable": {"next_extremum": {"days": 2, "kind": "max"},
                      "amp": 2.5},
         "campaign": {"id": 1, "name": "C", "overdue_days": 2,
                      "cadence_nights": 1, "never_visited": False,
                      "event": None}}
    _s, parts = suggest.score_target(t, fake_cfg, tmp_db)
    assert parts["hook"] > 0


def test_why_phrase_bilingual_and_specific():
    t = _neo()
    ph = suggest.why_phrase(t)
    assert "MPC" in ph["es"] and "MPC" in ph["en"]
    t2 = {"kind": "pccp", "pccp_score": 85, "id": "P1"}
    ph2 = suggest.why_phrase(t2)
    assert "85" in ph2["es"]


def test_why_phrase_carries_priority_data():
    # the score's own inputs must surface in the phrase, in both languages
    t = {"id": "T1", "kind": "neo", "name": "T1", "mag": 18.5,
         "max_alt": 65, "hours_up": 5, "nf_score": 8.2, "neocp": False,
         "nf_urgency": 72, "arc_days": 14, "nobs": 6}
    ph = suggest.why_phrase(t)
    for lang in ("es", "en"):
        assert "8.2" in ph[lang]      # NEOfixer score
        assert "72" in ph[lang]       # urgency
        assert "14" in ph[lang]       # arc length
        assert "6" in ph[lang]        # observation count


def test_why_phrases_are_object_specific():
    # two generic NEOs with different follow-up data must read differently
    a = {"id": "A", "kind": "neo", "name": "A", "mag": 18.5,
         "nf_score": 3.0, "neocp": False, "nf_urgency": 10}
    b = {"id": "B", "kind": "neo", "name": "B", "mag": 18.5,
         "nf_score": 3.0, "neocp": False, "nf_urgency": 90,
         "rate_arcsec_min": 0.6, "arc_days": 12, "nobs": 4}
    assert suggest.why_phrase(a)["es"] != suggest.why_phrase(b)["es"]
    assert "90" in suggest.why_phrase(b)["es"]
    assert "90" not in suggest.why_phrase(a)["es"]


def test_why_phrase_is_data_driven():
    # every fragment must carry a real number, not a generic claim
    t = {"kind": "neo", "neocp": False, "nf_score": 3.0,
         "moid": 0.032, "rate_arcsec_min": 0.60, "nf_cost_min": 14.0}
    ph = suggest.why_phrase(t)
    for lang in ("es", "en"):
        assert "0.032" in ph[lang]  # MOID
        assert "0.60" in ph[lang]   # proper motion
        assert "14" in ph[lang]     # imaging cost
    comet = {"kind": "comet", "mag": 10.8, "delta_au": 0.98, "r_au": 1.42,
             "perihelion_date": "2030-01-01"}
    cph = suggest.why_phrase(comet)
    for lang in ("es", "en"):
        assert "10.8" in cph[lang]
        assert "0.98" in cph[lang]
        assert "1.42" in cph[lang]
    # arc/nobs/mag arrive as strings from the PCCP page; this is what used
    # to crash the home screen
    pcd = {"kind": "pccp", "pccp_score": 87.5, "arc_days": "12",
           "nobs": "4", "mag": "18.5"}
    pph = suggest.why_phrase(pcd)
    for lang in ("es", "en"):
        assert "88" in pph[lang] or "87" in pph[lang]  # score, rounded
        assert "18.5" in pph[lang]
        assert "12" in pph[lang]


def test_why_phrase_unknown_kind_falls_back():
    ph = suggest.why_phrase({"kind": "unknown", "id": "X"})
    assert ph["es"] and ph["en"]


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


def test_beyond_limit_helper():
    # predicted-mag kinds flag the delta; measured-mag kinds never do
    t = _neo(mag=21.5)
    assert suggest.beyond_limit(t) == (True, 1.5)
    assert suggest.beyond_limit(_neo(mag=18.5)) == (False, 0.0)
    assert suggest.beyond_limit(_neo(mag=None)) == (False, 0.0)
    sn = {"kind": "sn", "mag": 23.0}
    assert suggest.beyond_limit(sn) == (False, 0.0)
    pccp = {"kind": "pccp", "mag": 20.5}
    assert suggest.beyond_limit(pccp) == (True, 0.5)


def test_soft_penalty_lowers_score():
    # same NEO beyond the limit sinks below the identical one within it
    bright, _ = suggest.score_target(_neo(mag=18.5))
    faint, _ = suggest.score_target(_neo(mag=21.5))
    assert bright > faint
    # the penalty is bounded: roughly one extra point per mag past the limit
    within = suggest._observability(_neo(mag=18.5), None)
    beyond = suggest._observability(_neo(mag=21.5), None)
    assert within - beyond >= 1.5


def test_observability_prefers_reachable_altitude():
    # The score's observability must use the horizon-clipped altitude
    # (safe_max_alt) when the planner provides it; otherwise a high raw
    # peak hiding behind a local obstacle would outrank a freely-visible
    # object with the same raw peak but a lower reachable one.
    blocked = {"kind": "neo", "mag": 18, "hours_up": 4,
               "max_alt": 70, "safe_max_alt": 46}
    free = {"kind": "neo", "mag": 18, "hours_up": 4,
            "max_alt": 70, "safe_max_alt": 70}
    # raw max_alt alone would give both the same score -> no ranking
    a = suggest._observability(blocked, None)
    b = suggest._observability(free, None)
    assert b > a  # the free one scores higher
    # and a target with no safe_max_alt (transits/alerts) falls back
    only_raw = {"kind": "neo", "mag": 18, "hours_up": 4, "max_alt": 70}
    assert suggest._observability(only_raw, None) == b


def test_soft_limit_does_not_drop_neo_beyond_limit():
    # ADR-025: beyond-limit NEOs/PCCPs are warned, never cut out of Top N
    a = _neo(mag=21.0)
    b = _neo(neocp=False, score=3.0, mag=21.5)
    b["id"], b["name"] = "T2", "T2"
    top, _scored = suggest.top_n([a, b], None, None, 2)
    assert len(top) == 2  # both survive even though both are beyond mag 20
    assert {t["id"] for t, _s, _p, _ph in top} == {"T1", "T2"}


def _moon_cfg(enabled=True, min_sep=45.0, max_illum=0.5, limit_mag=20.0):
    # config-like object with the Moon constraint enabled
    class Cfg:
        _v = {"min_alt": 30.0, "limit_mag": limit_mag,
              "moon_limit_enabled": enabled, "moon_min_sep_deg": min_sep,
              "moon_max_illum": max_illum}
        def get(self, k, d=None):
            return self._v.get(k, d)
    return Cfg()


def test_moon_info_disabled_returns_none():
    t = _neo()
    t["ra_deg"], t["dec_deg"] = 100.0, 20.0
    t["max_time"] = "2026-08-21T22:00:00"
    assert suggest.moon_info(t, _moon_cfg(enabled=False)) is None


def test_moon_info_enabled_returns_fields():
    t = _neo()
    t["ra_deg"], t["dec_deg"] = 100.0, 20.0
    t["max_time"] = "2026-08-21T22:00:00"
    info = suggest.moon_info(t, _moon_cfg())
    assert info is not None
    assert {"sep_deg", "illum", "warning"} <= set(info.keys())
    assert 0 <= info["illum"] <= 1


def test_moon_penalty_lowers_observability():
    # a target near the Moon scores lower than the same target far from it:
    # we just check the penalty path runs and observability stays in [0,30]
    t = _neo()
    t["ra_deg"], t["dec_deg"] = 100.0, 20.0
    t["max_time"] = "2026-08-21T22:00:00"
    obs = suggest._observability(t, _moon_cfg())
    assert 0 <= obs <= 30
    # and without the constraint the penalty is zero
    assert suggest._moon_penalty(t, _moon_cfg(enabled=False), 20.0) == 0.0
