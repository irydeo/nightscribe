############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: HADS post/tweet rendering (subplan C.3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The post/tweet builders are kind-agnostic on top of narrative: once the
HADS hook/facts/hashtags exist (C.2), render_post must tell the pulsating
story in both languages with no post.py change.
"""

from nightscribe.core import post


def _hads_e():
    return {"type": "hads", "name": "CY Aqr",
            "data": {"hads": {"period_h": 1.46, "max": 11.3, "min": 11.8,
                              "amp": 0.5, "cycles": 4.2, "session_fits": True,
                              "priority": "period_change", "observed": True,
                              "multiperiodic": True, "non_radial": False},
                     "safe_window": "2026-09-12T00:30:00|2026-09-12T04:10:00"}}


def test_render_post_tells_the_hads_story_bilingually(fake_cfg):
    out = post.render_post(_hads_e(), cfg=fake_cfg)
    for lang in ("es", "en"):
        assert "1.46" in out[lang]
        assert "CY Aqr" in out[lang]
    assert "pulsa" in out["es"] and "pulsat" in out["en"]
    assert "Wils" in out["es"]


def test_render_post_tweet_fits_and_carries_the_tags(fake_cfg):
    out = post.render_post(_hads_e(), cfg=fake_cfg)
    assert len(out["tweet"]) <= 280
    assert "#VariableStars" in out["tweet"] or "#VariableStars" in out["es"]
