############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: orbital explorer
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import orbits


def test_classify_families():
    # canonical examples per family
    assert orbits.classify({"a": 0.92, "q": 0.746, "Q": 1.099, "e": 0.19}) == "Aten"
    assert orbits.classify({"a": 1.5, "q": 1.01, "e": 0.33}) == "Apollo"
    assert orbits.classify({"a": 1.9, "q": 1.08, "e": 0.43}) == "Amor"
    assert orbits.classify({"a": 0.7, "q": 0.3, "Q": 0.97, "e": 0.4}) == "Atira"
    assert orbits.classify({"a": 2.5, "q": 2.0, "e": 0.2}) == "Main Belt"
    assert orbits.classify({"a": 5.2, "q": 4.9, "e": 0.05}) == "Trojan"
    assert orbits.classify({"a": 15.0, "q": 8.0, "e": 0.3}) == "Centaur"
    assert orbits.classify({"a": 40.0, "q": 35.0, "e": 0.1}) == "TNO"
    assert orbits.classify({"a": 3.45, "q": 5.78, "e": 0.04}, "JFc") == "JFc"


def test_diameter_from_h():
    # H=19.09 with albedo 0.35 (Apophis-like) -> ~0.34 km
    d = orbits.diameter_from_h(19.09, 0.35)
    assert 0.3 < d < 0.4
    # darker means bigger for the same H
    assert orbits.diameter_from_h(19.09, 0.057) > d


def test_size_comparison_bilingual():
    for km in (0.01, 0.1, 0.34, 1.0, 10.0, 100.0):
        cmp_txt = orbits.size_comparison(km)
        assert "es" in cmp_txt and "en" in cmp_txt
        assert cmp_txt["es"] and cmp_txt["en"]


def test_comet_mag():
    # 29P at r~7.2, delta~7.2: should sit around mag 18 (matches live check)
    m = orbits.comet_expected_mag(10.1, 4.5, 7.18, 7.18)
    assert 17 < m < 19


def test_visual_mag_guard():
    assert orbits.visual_mag(None, 1, 1) is None
    assert orbits.visual_mag(19.09, 0.99, 1.74) > 15


def test_explain_elements():
    # Apophis-like elements must yield interpreted rows, both languages,
    # with basic/deep levels and bilingual parameter names
    els = {"a": 0.9224, "e": 0.1912, "i": 3.33, "q": 0.746, "Q": 1.099,
           "per": 324.0}
    phys = {"H": 19.09, "rot_per": 30.56}
    rows = orbits.explain_elements(els, phys, "Aten", moid=0.000254)
    assert rows
    for r in rows:
        assert r["es"] and r["en"] and r["value"]
        assert r.get("level") in ("basic", "deep")
        assert isinstance(r["param"], dict) and r["param"]["es"]
    basic = [r for r in rows if r["level"] == "basic"]
    assert basic and basic[0]["param"]["es"] == "Familia"
    moid_row = next(r for r in rows if "MOID" in r["param"]["es"])
    # the intuitive metaphor must be there, no dry jargon
    assert "carreteras" in moid_row["es"]
    assert "roads" in moid_row["en"]
    assert "PHA" in moid_row["es"]


def test_explain_neofixer():
    t = {"nf_score": 5.4, "nf_priority": "medium", "nf_cost_min": 12.0,
         "nobs": 14, "arc_days": "0.09", "moid": 0.01}
    rows = orbits.explain_neofixer(t)
    assert len(rows) >= 5
    assert all(r["es"] and r["en"] and isinstance(r["param"], dict)
               for r in rows)


def test_explain_elements_preliminary_sigmas():
    # A preliminary (NEOfixer) orbit must add three rows: the preliminary
    # banner, the per-element sigmas and the arc/observations summary.
    els = {"a": 2.056, "e": 0.515, "i": 9.65, "q": 0.997, "Q": 3.114,
           "om": 328.5, "w": 341.6}
    sigmas = {"a": 0.0131, "e": 0.00308, "i": 0.025}
    rows = orbits.explain_elements(els, {"H": 26.7}, "Apollo", moid=0.0023,
                                   sigmas=sigmas, n_resids=9, arc_days=0.47)
    texts = [r["param"]["es"] for r in rows]
    assert "Órbita preliminar" in texts
    assert any("σ" in (r["param"]["es"]) for r in rows)
    assert "Arco y observaciones" in texts
    banner = next(r for r in rows if r["param"]["es"] == "Órbita preliminar")
    assert banner["level"] == "basic"
    assert "NEOfixer" in banner["es"] and "NEOfixer" in banner["en"]
    arc = next(r for r in rows if r["param"]["es"] == "Arco y observaciones")
    assert "0.47" in arc["value"] and "9" in arc["value"]
    # without sigmas nothing changes (confirmed objects keep the old output)
    rows2 = orbits.explain_elements(els, {"H": 26.7}, "Apollo", moid=0.0023)
    assert "Órbita preliminar" not in [r["param"]["es"] for r in rows2]


def test_pick_language():
    pair = {"es": "hola", "en": "hello"}
    assert orbits.pick(pair, "es") == "hola"
    assert orbits.pick(pair, "en") == "hello"
    assert orbits.pick(pair, "fr") == "hello"  # falls back to English
    assert orbits.pick("plain", "es") == "plain"


def test_distance_text_units():
    near = orbits.distance_text(384400 * 5)
    assert "lunares" in near["es"] and "lunar" in near["en"]
    far = orbits.distance_text(150e6)
    assert "millones" in far["es"] and "million" in far["en"]


def test_tisserand_earth_sar2911():
    # Validated against the Find_Orb sample report (Sar2911 -> 2.97758).
    t = orbits.tisserand_earth(1.4624917, 0.2881631, 7.94982)
    assert abs(t - 2.97758) < 1e-4


def test_tisserand_earth_guards():
    assert orbits.tisserand_earth(None, 0.1, 10.0) is None
    assert orbits.tisserand_earth(-1.0, 0.1, 10.0) is None     # non-bounded
    assert orbits.tisserand_earth(1.4, 1.2, 10.0) is None      # e out of range
    # circular, coplanar orbit: T = 1/a + 2*sqrt(a) = 1 + 2 = 3.0
    assert abs(orbits.tisserand_earth(1.0, 0.0, 0.0) - 3.0) < 1e-9


def test_encounter_velocity():
    # Same velocity -> zero relative speed; a 3-4-5 offset -> 5 units.
    assert orbits.encounter_velocity((1, 2, 3), (1, 2, 3)) == 0.0
    assert abs(orbits.encounter_velocity((4, 4, 0), (1, 0, 0)) - 5.0) < 1e-9
    # incomplete input -> None
    assert orbits.encounter_velocity((1, 2), (1, 2, 3)) is None
    assert orbits.encounter_velocity(None, (1, 2, 3)) is None


def test_explain_hads_full():
    # every row carries the bilingual contract; the session maths rows lead
    d = {"hads": {"period_h": 1.89, "max": 10.4, "min": 11.0, "amp": 0.6,
                  "cycles": 3.5, "session_fits": True,
                  "priority": "period_change", "observed": False,
                  "multiperiodic": True, "non_radial": False}}
    rows = orbits.explain_hads(d)
    assert len(rows) >= 8
    for r in rows:
        assert r["es"] and r["en"] and r["value"] is not None
        assert r.get("level") in ("basic", "deep")
        assert isinstance(r["param"], dict) and r["param"]["es"]
    params = [r["param"]["es"] for r in rows]
    assert params[0] == "Periodo"
    assert "Ciclos esta noche" in params and "Prioridad del programa" in params
    assert "Aún no observada" in params and "Dato histórico" in params
    per = rows[0]
    assert per["value"] == "1.89 h"


def test_explain_hads_minimal_bundle_shape():
    # the offline bundle shape (no planner keys) still yields the core rows
    d = {"hads": {"period_h": 1.46, "max": 11.3, "min": 11.8,
                  "multiperiodic": False, "non_radial": False}}
    rows = orbits.explain_hads(d)
    params = [r["param"]["en"] for r in rows]
    assert "Period" in params and "Amplitude" in params
    assert "Brightness range" in params
    amp = next(r for r in rows if r["param"]["en"] == "Amplitude")
    assert amp["value"] == "Δ 0.5 mag"          # computed from Max/Min
