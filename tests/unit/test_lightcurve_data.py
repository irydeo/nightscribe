############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: light-curve payload assembly (ADR-035)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from nightscribe.core import hads
from nightscribe.core import lightcurve_data


def _hads_entry(**over):
    # A typical HADS catalog entry: 12 h period, ~0.3 mag around 11.5
    e = {"name": "V339 Cen", "period_h": 12.0, "amp": 0.31,
         "max": 11.40, "min": 11.71}
    e.update(over)
    return e


def _var_entry(**over):
    # A long-period variable (VSX convention): 0.5 d period, known epoch
    e = {"name": "R CrB", "period_d": 0.5, "epoch_mjd": 60123.4,
         "amp": 0.5, "max": 11.3, "min": 11.8}
    e.update(over)
    return e


def test_payload_empty_fu():
    out = lightcurve_data.build_payload(None, sn_type_fallback="IIn")
    assert out["points"] == []
    assert out["sn_type"] == "IIn"        # fallback alone
    assert out["peak_mjd"] is None
    assert out["peak_mag"] is None
    # no catalog: no fold keys at all
    assert "fold_period_d" not in out
    assert "schematic" not in out
    assert "epoch_mjd" not in out


def test_payload_drops_points_missing_mjd_or_mag():
    fu = {"points": [
        {"mjd": None, "mag": 16.0},          # no date -> dropped
        {"mjd": 60600.0, "mag": None},       # no mag  -> dropped
        {"mag": 16.1},                       # no date -> dropped
        {"mjd": 60600.5, "mag": 16.2},       # good
        {"mjd": 60601.0, "mag": 16.4},       # good
    ]}
    out = lightcurve_data.build_payload(fu)
    assert [p["mjd"] for p in out["points"]] == [60600.5, 60601.0]


def test_payload_sn_type_priority():
    # the project's own sn_type wins over the caller's fallback
    out = lightcurve_data.build_payload(
        {"points": [], "sn_type": "Ia"}, sn_type_fallback="IIn")
    assert out["sn_type"] == "Ia"
    # ...and the fallback is used when the project has none
    out = lightcurve_data.build_payload(
        {"points": []}, sn_type_fallback="IIn")
    assert out["sn_type"] == "IIn"
    # neither: no template requested
    out = lightcurve_data.build_payload({"points": []})
    assert out["sn_type"] is None


def test_payload_peak_passthrough():
    fu = {"points": [], "peak_mjd": 60610.2, "peak_mag": 12.3}
    out = lightcurve_data.build_payload(fu)
    assert out["peak_mjd"] == 60610.2
    assert out["peak_mag"] == 12.3


def test_payload_hads_folds_by_period_and_schematics():
    h = _hads_entry()
    out = lightcurve_data.build_payload({"points": []}, hads=h)
    assert out["fold_period_d"] == 12.0 / 24.0
    # the schematic is the sawtooth with the stored amp/median
    med = (h["max"] + h["min"]) / 2.0
    assert out["schematic"] == hads.sawtooth_template(12.0, 0.31, med)
    # no variable epoch leaks in when HADS folded
    assert "epoch_mjd" not in out


def test_payload_amp_fallback_is_signed_min_minus_max():
    # no stored amp: the peak-to-peak span is min - max, kept signed
    # (NOT abs — the inverted magnitude axis is what makes the sawtooth
    # mirror the shape)
    e = _hads_entry(amp=None, max=11.4, min=11.8)
    out = lightcurve_data.build_payload({"points": []}, hads=e)
    med = (e["max"] + e["min"]) / 2.0
    assert out["schematic"] == hads.sawtooth_template(12.0, 0.4, med)
    # reversed convention would give a negative amp — still pass-through
    e2 = _hads_entry(amp=None, max=11.8, min=11.4)
    out2 = lightcurve_data.build_payload({"points": []}, hads=e2)
    assert out2["schematic"] == hads.sawtooth_template(12.0, -0.4, 11.6)


def test_payload_schematic_omitted_without_min_or_amp():
    # a catalog row with a period but an incomplete photometry block
    # must not crash the builders: no schematic, fold still set
    e = _hads_entry(amp=0.3, max=11.4, min=None)
    out = lightcurve_data.build_payload({"points": []}, hads=e)
    assert out["fold_period_d"] == 12.0 / 24.0
    assert "schematic" not in out
    # zero amplitude: degenerate shape, skip it too
    e2 = _hads_entry(amp=0, min=11.5)
    out2 = lightcurve_data.build_payload({"points": []}, hads=e2)
    assert "schematic" not in out2


def test_payload_hads_wins_over_variable():
    # both catalogs present: the HADS fold takes the axis, the VSX
    # period and its epoch must not be mixed in
    out = lightcurve_data.build_payload(
        {"points": []}, hads=_hads_entry(), variable=_var_entry())
    assert out["fold_period_d"] == 12.0 / 24.0
    assert "epoch_mjd" not in out
    assert out["schematic"] == hads.sawtooth_template(
        12.0, 0.31, (11.40 + 11.71) / 2.0)


def test_payload_variable_folds_with_epoch():
    v = _var_entry()
    out = lightcurve_data.build_payload({"points": []}, variable=v)
    assert out["fold_period_d"] == 0.5
    assert out["epoch_mjd"] == 60123.4
    # same sawtooth shape, with the period in days converted to hours
    med = (v["max"] + v["min"]) / 2.0
    assert out["schematic"] == hads.sawtooth_template(0.5 * 24.0, 0.5, med)


def test_payload_variable_without_epoch_or_period_fold():
    # no epoch in the VSX row: fold still applies, epoch stays absent
    # (the widget defaults the epoch to the first point)
    v = _var_entry(epoch_mjd=None)
    out = lightcurve_data.build_payload({"points": []}, variable=v)
    assert out["fold_period_d"] == 0.5
    assert "epoch_mjd" not in out
    # a variable without a period is just SN-like data: no fold at all
    out2 = lightcurve_data.build_payload(
        {"points": []}, variable=_var_entry(period_d=None))
    assert "fold_period_d" not in out2
    assert "schematic" not in out2
