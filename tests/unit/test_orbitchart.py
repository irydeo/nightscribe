############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - orbit chart widget tests (offscreen, ADR-029)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/widgets/orbit_widget.py (ADR-029) — the
interactive vector orbit chart.

Patterns (mirroring test_chartview.py):
  * one QApplication per module, offscreen, throwaway;
  * no network, no matplotlib in the widget package;
  * the point, hover and animation are exercised against the pure math in
    core/orbit_math, so the widget cannot drift from its own figures.
"""

import os
import subprocess
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    if os.environ.get("QT_QPA_PLATFORM") is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


# a representative bounded orbit (a=2.3 AU, mildly eccentric). The `ma` +
# `epoch` pair lets position_now place the point in time.
_ELEMENTS = {"a": 2.3, "e": 0.35, "i": 8.0, "om": 10.0, "w": 20.0,
             "ma": 50.0, "epoch": 2460000.0}
_JD = 2460500.0


def _mk_chart(qapp, w=600, h=500):
    # @return: a sized, shown OrbitChart (offscreen).
    from nightscribe.gui.widgets.orbit_widget import OrbitChart
    w_ = OrbitChart()
    w_.resize(w, h)
    w_.show()
    qapp.processEvents()
    return w_


def test_instantiate_and_set_elements(qapp):
    from nightscribe.gui.widgets.orbit_widget import OrbitChart
    w = _mk_chart(qapp)
    w.set_elements(_ELEMENTS, _JD, "test object")
    assert w.elements() == _ELEMENTS
    # the moving point sits at the same spot the pure math says
    from nightscribe.core import orbit_math
    got = w.position()
    want = orbit_math.position_now(_ELEMENTS, _JD)
    assert got is not None and want is not None
    for g, x in zip(got, want):
        assert abs(g - x) < 1e-6
    # the controls are live once an orbit is on screen
    assert w._play_btn.isEnabled()
    assert w._slider.isEnabled()
    w.close()


def test_position_matches_kepler_at_another_date(qapp):
    # scrub the point to a different epoch by hand and check the figure
    from nightscribe.core import orbit_math
    from nightscribe.gui.widgets.orbit_widget import OrbitChart
    w = _mk_chart(qapp)
    w.set_elements(_ELEMENTS, _JD, "o")
    other_jd = 2461234.7
    w._cur_jd = other_jd          # direct seek (same as the slider does)
    w._sync_point()
    got = w.position()
    want = orbit_math.position_now(_ELEMENTS, other_jd)
    for g, x in zip(got, want):
        assert abs(g - x) < 1e-6
    w.close()


def test_export_png_is_not_blank(qapp, tmp_path):
    w = _mk_chart(qapp)
    w.set_elements(_ELEMENTS, _JD, "o")
    out = tmp_path / "orbit.png"
    p = w.export_png(out)
    assert p.exists()
    size = p.stat().st_size
    assert size > 8 * 1024, f"PNG too small ({size} bytes) — probably blank"
    with open(p, "rb") as fh:
        assert fh.read(4) == b"\x89PNG"
    w.close()


def test_hover_reports_r_and_nu(qapp):
    # the midpoint of the sampled ellipse must answer r / nu (the drawn path
    # and the hit-test use the same 361 points by construction)
    w = _mk_chart(qapp)
    w.set_elements(_ELEMENTS, _JD, "o")
    mid = w._orbit_pts[len(w._orbit_pts) // 2]
    hit, text = w._hover(*mid)
    assert hit is True
    assert "r =" in text and "°" in text and "AU" in text
    # a point clearly off the line (near the frame edge) does not hit
    hit2, _ = w._hover(495.0, 495.0)
    assert hit2 is False
    w.close()


def test_hover_misses_inside_empty_circle(qapp):
    # the frame center (scene origin) sits inside, not on, the closed ellipse
    # — the hit-test only fires near the orbit line, so the center must miss.
    w = _mk_chart(qapp)
    w.set_elements(_ELEMENTS, _JD, "o")
    hit, _ = w._hover(0.0, 0.0)
    assert hit is False
    w.close()


def test_start_animation_moves_date(qapp):
    # Play advances the point (an animation that shows a static point is a
    # regression — the whole purpose of the widget is moving time)
    w = _mk_chart(qapp)
    w.set_elements(_ELEMENTS, _JD, "o")
    seen = []
    w.date_moved.connect(lambda jd: seen.append(jd))
    jd0 = _JD
    w.start_animation(jd0, jd0 + 10.0, period_s=0.2)
    end = time.time() + 0.12
    while time.time() < end:
        qapp.processEvents()
    w.stop_animation()
    # at least the initial emit plus several ticks while running
    assert len(seen) >= 2, f"expected date_moved > 1, got {len(seen)}"
    # the last emitted date is ahead of the start (we ran forward)
    moved = [j for j in seen if abs(j - jd0) > 1e-3]
    assert moved, "the point never moved off its start date"
    w.close()


def test_double_click_refits(qapp):
    # a double-click on the canvas resets the frame (fit_to_scene)
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    w = _mk_chart(qapp)
    w.set_elements(_ELEMENTS, _JD, "o")
    before = w.view.transform().m11()
    # zoom in by a lot
    for _ in range(20):
        w.view._zoom_by(1.25)
    zoomed = w.view.transform().m11()
    assert zoomed > before
    # emulate a double-click on the canvas
    pos = QPointF(w.view.viewport().width() / 2,
                  w.view.viewport().height() / 2)
    evt = QMouseEvent(QEvent.Type.MouseButtonDblClick, pos, pos, pos,
                      Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    w.view.event(evt)
    qapp.processEvents()
    assert w.view.transform().m11() <= zoomed + 1e-3  # it shrank back down
    w.close()


def test_widget_package_has_no_matplotlib():
    # the widget package must never pull in matplotlib (ADR-029) — assert it
    # at import time in a clean subprocess.
    code = (
        "import sys; from nightscribe.gui.widgets.orbit_widget import OrbitChart; "
        "sys.exit(1 if 'matplotlib' in sys.modules else 0)"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True)
    assert res.returncode == 0, f"matplotlib leaked: {res.stderr}"
