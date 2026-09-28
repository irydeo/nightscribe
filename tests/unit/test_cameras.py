############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: camera presets (photometric profile)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import cameras


def test_preset_by_key_and_alias():
    assert cameras.preset("imx455")["sensor"].startswith("Sony IMX455")
    # by a camera alias
    assert cameras.preset("ASI2600")["key"] == "imx571"
    assert cameras.preset("QHY600")["key"] == "imx455"
    assert cameras.preset("qhy42pro")["key"] == "gsense400"
    assert cameras.preset("nope") is None
    assert cameras.preset(None) is None


def test_presets_have_the_expected_shape():
    for p in cameras.PRESETS:
        assert p["key"] and p["sensor"] and p["cameras"]
        assert p["pixel_um"] > 0
        assert p["regime"] in ("short", "normal")
        # every preset offers a suggested linearity (to be measured)
        assert p.get("linearity_adu")


def test_short_regime_only_for_the_scmos():
    assert cameras.preset("gsense400")["regime"] == "short"
    assert cameras.preset("imx455")["regime"] == "normal"
    assert cameras.preset("kaf16803")["regime"] == "normal"


def test_full_well_in_adu():
    p = cameras.preset("imx571")     # 51000 e-
    assert cameras.full_well_adu(p, 2.0) == 25500.0
    assert cameras.full_well_adu(p, 0) is None
    assert cameras.full_well_adu(None, 2.0) is None


def test_label_names_the_cameras():
    lab = cameras.label(cameras.preset("imx455"))
    assert "IMX455" in lab and "QHY600" in lab and "ASI6200" in lab
