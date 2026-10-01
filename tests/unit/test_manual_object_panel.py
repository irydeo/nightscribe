############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Manual object panel tests (Interfaz 1.0, ADR-053)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The manual object form builds the same planner-target dict the rest of
the app already understands. These tests pin the mapping per kind and the
name/coords minimum, with no network and no database."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _panel():
    from nightscribe.gui.widgets.manual_object_panel import ManualObjectPanel
    return ManualObjectPanel()


def test_common_fields(qapp):
    p = _panel()
    p._ui.edt_mf_name.setText("2026 XY")
    p._ui.edt_mf_ra.setText("210.12345")
    p._ui.edt_mf_dec.setText("-3.5")
    p._ui.edt_mf_mag.setText("15.2")
    p._ui.edt_mf_notes.setText("discovered")
    p._ui.cmb_mf_kind.setCurrentIndex(1)     # NEO
    t = p.to_target()
    assert t["name"] == "2026 XY"
    assert t["kind"] == "neo"
    assert t["ra_deg"] == 210.12345
    assert t["dec_deg"] == -3.5
    assert t["mag"] == 15.2
    assert t["notes"] == "discovered"


def test_neo_specific_fields(qapp):
    p = _panel()
    p._ui.edt_mf_name.setText("A")
    p._ui.edt_mf_ra.setText("1")
    p._ui.edt_mf_dec.setText("2")
    p._ui.cmb_mf_kind.setCurrentIndex(1)     # NEO
    p._ui.edt_neo_rate.setText("2.5")
    p._ui.edt_neo_h.setText("20")
    p._ui.edt_neo_moid.setText("0.02")
    t = p.to_target()
    assert t["rate_arcsec_min"] == 2.5
    assert t["h"] == 20.0
    assert t["moid"] == 0.02


def test_pccp_shares_the_neo_page(qapp):
    p = _panel()
    p._ui.cmb_mf_kind.setCurrentIndex(3)     # PCCP
    assert p._ui.kind_stack.currentIndex() == 2
    assert p.to_target()["kind"] == "pccp"


def test_transit_and_variable_nested(qapp):
    p = _panel()
    p._ui.edt_mf_name.setText("TrES-1")
    p._ui.edt_mf_ra.setText("10")
    p._ui.edt_mf_dec.setText("20")
    p._ui.cmb_mf_kind.setCurrentIndex(4)     # transit
    p._ui.edt_tr_period.setText("3.03")
    p._ui.edt_tr_t0.setText("2460000.5")
    p._ui.edt_tr_dur.setText("2.5")
    t = p.to_target()
    assert t["transit"] == {"period_d": 3.03, "t0": 2460000.5,
                            "duration_h": 2.5}
    p._ui.cmb_mf_kind.setCurrentIndex(5)     # variable
    p._ui.edt_var_period.setText("0.5")
    p._ui.edt_var_amp.setText("0.8")
    p._ui.edt_var_sub.setText("RRAB")
    t2 = p.to_target()
    assert t2["variable"] == {"period_d": 0.5, "amplitude": 0.8,
                              "var_type": "RRAB"}


def test_create_needs_name_and_coords(qapp):
    p = _panel()
    seen = []
    p.created.connect(seen.append)
    # no name: nothing
    p._create()
    assert seen == []
    # name but no coords: still nothing
    p._ui.edt_mf_name.setText("X")
    p._create()
    assert seen == []
    # complete: emits the target
    p._ui.edt_mf_ra.setText("10")
    p._ui.edt_mf_dec.setText("20")
    p._create()
    assert seen and seen[0]["name"] == "X"
