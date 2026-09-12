############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: variable post with folded light curve (Track V, VD.9)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import post


def _variable_e():
    return {"type": "variable", "name": "T CrB",
            "data": {"variable": {"var_type": "NR+ELL", "period_d": 227.55,
                                  "epoch_mjd": 55828.4, "max": 2.0,
                                  "min": 10.8, "amp": 8.8},
                     "campaign": {"name": "Campaña T CrB"},
                     "followup": {"points": [
                         {"mjd": 61000.0 + 5 * i,
                          "mag": 10.1 + 0.2 * (i % 3), "err": 0.02,
                          "filter": "V", "source": "file"}
                         for i in range(9)]}}}


def test_post_chart_folds_the_variable_curve(tmp_path, fake_cfg):
    charts = post.build_charts(_variable_e(), tmp_path, "", cfg=fake_cfg)
    lc = charts.get("lightcurve")
    assert lc is not None and lc.exists() and lc.stat().st_size > 1000


def test_post_mentions_the_campaign(tmp_path, fake_cfg):
    out = post.render_post(_variable_e(), cfg=fake_cfg)
    assert "Campaña T CrB" in out["es"]
