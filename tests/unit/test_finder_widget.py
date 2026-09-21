############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: interactive finder widget (ADR-042, phase 4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/widgets/finder_widget.py: scene build from a
synthetic field, the hover probe, and the click-to-toggle sequence logic.
No network, no matplotlib (ADR-029 is asserted by test_chartview).
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

CENTER = (291.366, 42.784)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _star(ra, dec, mag, vsx=None):
    return {"id": f"J{ra:.4f}{dec:+.4f}", "name": None, "ra": ra,
            "dec": dec, "mag": mag, "band": "G", "catalog": "Gaia EDR3",
            "bands": [{"label": "G", "value": mag, "err": 0.003,
                       "derived": False}],
            "bv": 0.6, "color_origin": "estimated", "vsx": vsx}


def _field():
    return {"stars": [_star(291.366, 42.790, 12.0),
                      _star(291.300, 42.780, 12.5),
                      _star(291.340, 42.750, 13.0,
                            vsx={"name": "V9 Cyg", "type": "EA"}),
                      _star(291.400, 42.800, 13.5)],
            "variables": [], "catalog": "gaia", "catalog_name": "Gaia EDR3",
            "band": "G", "center": CENTER, "fov_arcmin": 18.0,
            "vsx_warning": False}


def _chart(qapp):
    from nightscribe.gui.widgets.finder_widget import FinderChart
    chart = FinderChart(lang="en")
    chart.set_field(_field(), target={"name": "V0001 Cyg", "ra": CENTER[0],
                                      "dec": CENTER[1]},
                    entries=[])
    return chart


def test_scene_builds_with_overlays(qapp):
    chart = _chart(qapp)
    # frame, ticks, scale, compass, target, catalog labels... and the
    # scene rect is the synthetic canvas
    assert chart.scene_rect_hint().width() == pytest.approx(1000.0)
    assert len(chart.scene().items()) > 20
    # stars carry scene coordinates
    assert all("_sx" in s and "_sy" in s for s in chart._stars)


def test_hover_probe_reports_the_star(qapp):
    chart = _chart(qapp)
    star = chart._stars[0]
    hit, lines = chart._probe_star(star["_sx"], star["_sy"])
    assert hit
    text = "\n".join(lines)
    assert star["id"] in text and f"{star['mag']:.2f}" in text
    assert "B−V" in text
    # far from any star: no hit
    hit, _ = chart._probe_star(5.0, 995.0)
    assert not hit


def test_hover_marks_variables_as_not_comparable(qapp):
    chart = _chart(qapp)
    var_star = next(s for s in chart._stars if s.get("vsx"))
    hit, lines = chart._probe_star(var_star["_sx"], var_star["_sy"])
    assert hit
    assert any("VSX" in ln for ln in lines)
    assert any("cannot be comparisons" in ln for ln in lines)


def test_click_toggles_comp_and_check(qapp):
    chart = _chart(qapp)
    fired = []
    chart.sequence_changed.connect(lambda: fired.append(True))
    star = chart._stars[0]
    from PySide6.QtCore import QPointF
    chart._toggle_at(QPointF(star["_sx"], star["_sy"]))
    assert len(chart.entries()) == 1
    assert chart.entries()[0]["kind"] == "comp"
    assert chart.entries()[0]["name"] == "Comp1"
    # clicking the same star removes it
    chart._toggle_at(QPointF(star["_sx"], star["_sy"]))
    assert chart.entries() == []
    # check kind via set_pick_kind
    chart.set_pick_kind("check")
    chart._toggle_at(QPointF(star["_sx"], star["_sy"]))
    assert chart.entries()[0]["kind"] == "check"
    assert chart.entries()[0]["name"] == "Check"
    assert len(fired) == 3


def test_click_never_adds_a_variable(qapp):
    chart = _chart(qapp)
    var_star = next(s for s in chart._stars if s.get("vsx"))
    from PySide6.QtCore import QPointF
    chart._toggle_at(QPointF(var_star["_sx"], var_star["_sy"]))
    assert chart.entries() == []


def test_names_stay_unique_after_removals(qapp):
    from PySide6.QtCore import QPointF
    chart = _chart(qapp)
    for s in chart._stars[:2]:
        chart._toggle_at(QPointF(s["_sx"], s["_sy"]))
    assert [e["name"] for e in chart.entries()] == ["Comp1", "Comp2"]
    # remove Comp1; the next addition (a non-variable star) reuses the
    # free name
    chart._toggle_at(QPointF(chart._stars[0]["_sx"], chart._stars[0]["_sy"]))
    chart._toggle_at(QPointF(chart._stars[3]["_sx"], chart._stars[3]["_sy"]))
    names = [e["name"] for e in chart.entries()]
    assert len(names) == len(set(names)) == 2
