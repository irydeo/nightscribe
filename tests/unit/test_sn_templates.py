############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: SN light-curve templates (Track B, B4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import sn_templates


def test_template_ia():
    tpl = sn_templates.template("SN Ia")
    assert tpl is not None
    assert len(tpl) > 10
    # peak is at day 0, delta_mag = 0
    peak = [pt for pt in tpl if pt[0] == 0]
    assert len(peak) == 1
    assert peak[0][1] == 0.0


def test_template_ii_p():
    tpl = sn_templates.template("SN II-P")
    assert tpl is not None
    # plateau: there should be points near day 50 with ~1.0 delta_mag
    plateau = [pt for pt in tpl if 40 <= pt[0] <= 100]
    assert all(0.5 <= dm <= 1.5 for _, dm in plateau)


def test_template_ii_l():
    tpl = sn_templates.template("SN II-L")
    assert tpl is not None
    # no plateau: monotonically increasing after peak
    after = [dm for d, dm in tpl if d > 0]
    assert all(after[i] <= after[i + 1]
               for i in range(len(after) - 1))


def test_template_ib_c():
    tpl = sn_templates.template("SN Ib/c")
    assert tpl is not None


def test_template_unclassified():
    tpl = sn_templates.template("")
    assert tpl is not None
    # generic reference: monotonically increasing after peak
    after = [dm for d, dm in tpl if d > 0]
    assert all(after[i] <= after[i + 1]
               for i in range(len(after) - 1))


def test_template_none():
    assert sn_templates.template(None) is not None


def test_template_unknown_falls_back():
    # An unrecognised type falls back to the generic template, not None
    tpl = sn_templates.template("SN XYZ")
    assert tpl is not None


def test_template_normalisation():
    # "SN Ia" and "Ia" both resolve to the same template
    assert sn_templates.template("SN Ia") == sn_templates.template("Ia")
    assert sn_templates.template("SN II") == sn_templates.template("II")


def test_all_templates_peak_at_zero():
    # Every template's peak is at (0, 0) — the alignment anchor
    for t in ["Ia", "II-P", "II-L", "Ib/c", ""]:
        tpl = sn_templates.template(t)
        peak = [pt for pt in tpl if pt[0] == 0]
        assert len(peak) == 1
        assert peak[0][1] == 0.0
