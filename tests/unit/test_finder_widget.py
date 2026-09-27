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


def test_synthetic_sky_when_no_image(qapp):
    # No survey image (all downloads failed or answered flat tiles): the
    # catalog stars themselves are the background, one soft dot each, so
    # the chart never opens on an empty black pane.
    from PySide6.QtWidgets import QGraphicsEllipseItem
    chart = _chart(qapp)                     # _chart passes image=None
    dots = [it for it in chart.scene().items()
            if it.zValue() == -1
            and isinstance(it, QGraphicsEllipseItem)]
    assert len(dots) == len(chart._stars) == 4
    chart.close()


def test_real_image_replaces_the_synthetic_sky(qapp):
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import (QGraphicsEllipseItem,
                                   QGraphicsPixmapItem)
    from nightscribe.gui.widgets.finder_widget import FinderChart
    img = QImage(8, 8, QImage.Format_Grayscale8)
    img.fill(QColor(40, 40, 40))
    chart = FinderChart(lang="en")
    chart.set_field(_field(), target={"name": "V0001 Cyg", "ra": CENTER[0],
                                      "dec": CENTER[1]},
                    entries=[], image=img)
    items = chart.scene().items()
    assert any(isinstance(it, QGraphicsPixmapItem) for it in items)
    dots = [it for it in items if it.zValue() == -1
            and isinstance(it, QGraphicsEllipseItem)]
    assert dots == []
    chart.close()


def test_zoom_goes_to_pixel_level(qapp):
    # the finder overrides the base ceiling (8x) with pixel-level zoom
    chart = _chart(qapp)
    assert chart.ZOOM_MAX == 30.0
    for _ in range(60):
        chart._zoom_by(1.25)
    scale = chart.transform().m11()
    assert 8.0 < scale <= 30.0
    chart.close()


def test_wheel_zooms_with_the_bolder_finder_step(qapp):
    # one wheel notch must move visibly: the finder's 1.5 step, not the
    # base's shy 1.25
    from PySide6.QtCore import QPoint
    chart = _chart(qapp)
    seen = []
    chart._zoom_by = seen.append

    class Wheel:
        def angleDelta(self):
            return QPoint(0, 120)

        def accept(self):
            pass

        def ignore(self):
            pass

    chart.wheelEvent(Wheel())
    assert seen == [1.5]
    chart.close()


def test_pick_radius_is_screen_constant(qapp):
    # ~11 screen px at any zoom: a fixed scene radius would cover a third
    # of the view at deep zoom; a fixed screen radius stays precise
    chart = _chart(qapp)
    star = chart._stars[0]
    scale1 = chart.transform().m11()
    r1 = 11.0 / scale1               # the pick radius in scene units
    assert chart._nearest_star(star["_sx"] + r1 * 0.5, star["_sy"]) is star
    assert chart._nearest_star(star["_sx"] + r1 * 2.0, star["_sy"]) is None
    chart.scale(2.0, 2.0)            # the same scene distance is now
    # twice as many screen px: what was a hit becomes a miss, and the
    # precise pick needs half the scene distance
    assert chart._nearest_star(star["_sx"] + r1 * 0.75, star["_sy"]) is None
    assert chart._nearest_star(star["_sx"] + r1 * 0.25, star["_sy"]) is star
    chart.close()


def test_boxes_and_cross_marker_follow_the_config(qapp, monkeypatch):
    # ADR-046: with the settings on, the corner boxes land in the scene
    # and the target marker is the full-frame cross; off, nothing changes
    from nightscribe.config import config
    from PySide6.QtWidgets import (QGraphicsLineItem, QGraphicsRectItem,
                                   QGraphicsSimpleTextItem)
    monkeypatch.setitem(config._data, "chart_boxes", True)
    monkeypatch.setitem(config._data, "observer_name", "F. Calvo")
    monkeypatch.setitem(config._data, "mpc_code", "Z41")
    monkeypatch.setitem(config._data, "marker_style", "cross")
    chart = _chart(qapp)
    texts = [it.text() for it in chart.scene().items()
             if isinstance(it, QGraphicsSimpleTextItem)]
    assert any("Stn: Z41" in t for t in texts)          # site box
    assert any("RA: " in t for t in texts)              # position box
    assert any("PSc: " in t for t in texts)             # scale line
    # no top-left box: the title/name label already owns the object name
    assert not any(t.startswith("V0001 Cyg\n") for t in texts)
    # the cross: four long arms + a box, no amber ring
    arms = [it for it in chart.scene().items()
            if isinstance(it, QGraphicsLineItem)
            and it.pen().color().name().lower() == "#ffb347"]
    xs = [c for ln in arms for c in (ln.line().x1(), ln.line().x2())]
    assert len(arms) == 4 and min(xs) == 0.0 and max(xs) == 1000.0
    chart.deleteLater()
    # classic defaults: no boxes, the ring marker
    monkeypatch.setitem(config._data, "chart_boxes", False)
    monkeypatch.setitem(config._data, "marker_style", "ring")
    chart = _chart(qapp)
    texts = [it.text() for it in chart.scene().items()
             if isinstance(it, QGraphicsSimpleTextItem)]
    assert not any("Stn:" in t for t in texts)
    arms = [it for it in chart.scene().items()
            if isinstance(it, QGraphicsLineItem)
            and it.pen().color().name().lower() == "#ffb347"]
    assert len(arms) == 4
    assert max(ln.line().x2() - ln.line().x1() for ln in arms) < 100.0
    chart.deleteLater()
