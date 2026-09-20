############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: variable narrative (Track V, VD.8)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Hook, fact bullets and hashtags for variable stars, ES/EN."""

from nightscribe.core import narrative, post


def _e():
    return {"type": "variable", "name": "T CrB",
            "data": {"variable": {"var_type": "NR+ELL", "period_d": 227.55,
                                  "max": 2.0, "min": 10.8, "amp": 8.8,
                                  "next_extremum": {"kind": "max",
                                                    "mjd": 61250.0,
                                                    "days": 3.0}},
                     "campaign": {"name": "Campaña T CrB"}}}


def test_variable_hook_mentions_campaign_and_extremum():
    h = narrative.hook(_e())
    assert "Campaña T CrB" in h["es"] and "campaign" in h["en"]
    assert "máximo" in h["es"] and "3" in h["en"]


def test_variable_facts_bilingual_pairs():
    bullets = narrative.fact_bullets(_e())
    assert bullets
    for b in bullets:
        assert b["es"] and b["en"]
    joined = " ".join(b["es"] for b in bullets)
    assert "Nova recurrente" in joined
    assert "227.6 días" in joined


def test_variable_hashtags():
    assert "#VariableStars" in narrative.hashtags("variable")


def test_render_post_tells_the_variable_story(fake_cfg):
    out = post.render_post(_e(), cfg=fake_cfg)
    assert "T CrB" in out["es"] and "T CrB" in out["en"]
    assert len(out["tweet"]) <= 280
