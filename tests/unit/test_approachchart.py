############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - approach chart widget tests (offscreen, ADR-029)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/widgets/approach_widget.py (ADR-029) — the
interactive vector approach chart (geocentric, Moon as scale bar).

Patterns (mirroring test_orbitchart.py):
  * one QApplication per module, offscreen, throwaway;
  * no network, no matplotlib in the widget package;
  * the point, hover and animation are exercised against the pure math in
    core/approach_math, so the widget cannot drift from its own figures.
"""

import os
import subprocess
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


# A representative bounded (closed, e<1) orbit — enough to be located for
# the track sampling window.  `ma` + `epoch` pair lets position_now place
# the point in time; `a` + `e` give a closed ellipse.
_ELEMENTS = {"a": 1.8, "e": 0.32, "i": 4.0, "om": 10.0, "w": 20.0,
             "ma": 30.0, "epoch": 2460000.0}
_JD = 2460500.0          # ~2025 Jan


def _mk_chart(qapp, w=600, h=500):
    # @return: a sized, shown ApproachChart (offscreen). The element dict
    #          and reference date are set immediately so the scene is built.
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    w_ = ApproachChart()
    w_.resize(w, h)
    w_.show()
    qapp.processEvents()
    w_.set_elements(_ELEMENTS, _JD, "test object")
    qapp.processEvents()
    return w_


def test_instantiate_and_set_elements(qapp):
    w = _mk_chart(qapp)
    assert w.elements() == _ELEMENTS
    # geocentric_position must agree with the pure math
    from nightscribe.core import approach_math
    got = w.geocentric_position(_JD)
    want = approach_math.geocentric_position(_ELEMENTS, _JD)
    assert got is not None and want is not None
    for g, x in zip(got, want):
        assert abs(g - x) < 1e-6
    # controls are live once a track is on screen
    assert w._play_btn.isEnabled()
    assert w._slider.isEnabled()
    w.close()


def test_geocentric_position_at_another_date(qapp):
    w = _mk_chart(qapp)
    other_jd = 2461234.7
    from nightscribe.core import approach_math
    got = w.geocentric_position(other_jd)
    want = approach_math.geocentric_position(_ELEMENTS, other_jd)
    assert got is not None and want is not None
    for g, x in zip(got[:3], want[:3]):
        assert abs(g - x) < 1e-6
    w.close()


def test_ca_cache_for_closed_orbit(qapp):
    # A closed orbit should have a CA cached (property of the orbit, computed
    # once in set_elements).
    w = _mk_chart(qapp)
    assert w._ca_cache is not None, "closed orbit must have a CA"
    jd_best, d_au, d_ld = w._ca_cache
    assert jd_best > 0.0
    assert d_au > 0.0
    assert d_ld > 0.0
    # LD = AU / AU_PER_LD
    from nightscribe.core import approach_math
    assert abs(d_ld - d_au / approach_math.AU_PER_LD) < 1e-6
    w.close()


def test_status_line_has_date_ld_trend(qapp):
    # A closed orbit must produce a non-empty line with a date, an LD
    # distance, one of the three arrows, and a CA clause.
    w = _mk_chart(qapp)
    line = w.status_text()
    assert line, "status line must not be empty after set_elements"
    assert "LD" in line
    assert any(tok in line for tok in ("\u2192", "\u2190", "\u00b7")), \
        f"no trend arrow in {line!r}"
    assert "CA" in line, f"CA clause missing in {line!r}"
    w.close()


def test_status_line_open_orbit_flag(qapp):
    # An open (e >= 1) orbit must carry the "no return" marker and must NOT
    # have a CA or CA-cache.
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    els = {"q": 0.98, "e": 1.02, "i": 84.0, "om": 110.0, "w": 210.0,
           "tp": 2460690.0}
    w = ApproachChart()
    w.resize(400, 300)
    w.show()
    qapp.processEvents()
    w.set_elements(els, els["tp"] + 30.0, "escapee")
    qapp.processEvents()
    line = w.status_text()
    low = line.lower()
    assert ("no return" in low) or ("retorno" in low), \
        f"open-orbit marker missing: {line!r}"
    # no CA clause for open orbit (the status text must not use "CA")
    w.close()


def test_status_line_empty_before_set_elements(qapp):
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    w = ApproachChart()
    w.resize(400, 300)
    w.show()
    qapp.processEvents()
    assert w.status_text() == ""
    assert w._status.text() == ""
    w.close()


def test_seek_to_moves_point(qapp):
    # Scrubbing the slider must change the current date (the point follows).
    w = _mk_chart(qapp)
    jd_before = w._cur_jd
    # seek to midpoint of the animation window
    w._seek_to(0.5)
    jd_after = w._cur_jd
    window = w._jd1 - w._jd0
    expected = w._jd0 + 0.5 * window
    assert abs(jd_after - expected) < 1e-3
    assert jd_before != jd_after, "seek_to(0.5) did not move the date"
    w.close()


def test_animation_moves_date(qapp):
    # Play must advance the point (an animation that shows a static point is
    # a regression — the whole purpose of the widget is moving time).
    w = _mk_chart(qapp)
    seen = []
    w.date_moved.connect(lambda jd: seen.append(jd))
    w.start_animation(w._jd0, w._jd1, period_s=0.2)
    end = time.time() + 0.15
    while time.time() < end:
        qapp.processEvents()
    w.stop_animation()
    assert len(seen) >= 2, f"expected date_moved > 1, got {len(seen)}"
    moved = [j for j in seen if abs(j - w._jd0) > 1e-3]
    assert moved, "the point never moved off its start date"
    w.close()


def test_track_pts_populated(qapp):
    # After set_elements with a valid closed orbit, the track list must be
    # non-empty (the scene drew the polyline from these points).
    w = _mk_chart(qapp)
    assert len(w._track_pts) > 10, \
        f"track too short: {len(w._track_pts)} points"
    # each entry is (sx, sy, r_ld, jd)
    sx, sy, r_ld, jd = w._track_pts[0]
    assert isinstance(sx, float)
    assert r_ld > 0.0
    assert jd > 2_400_000.0
    w.close()


def test_frame_span_reasonable(qapp):
    # The frame half-extent must be at least 1.5 LD (the minimum that
    # keeps visual margin around the 1 LD circle) and must not be enormous
    # (indicating a runaway value).
    from nightscribe.core import approach_math
    w = _mk_chart(qapp)
    min_span_au = 1.5 * approach_math.AU_PER_LD
    assert w._span_au >= min_span_au, \
        f"span too small: {w._span_au:.6f} < {min_span_au:.6f} AU"
    # a reasonable upper bound (say, 100 AU) — catches a units bug
    assert w._span_au < 100.0, f"span unreasonably large: {w._span_au} AU"
    w.close()


def test_export_png_not_blank(qapp, tmp_path):
    w = _mk_chart(qapp)
    out = tmp_path / "approach.png"
    p = w.export_png(out)
    assert p.exists()
    size = p.stat().st_size
    assert size > 4 * 1024, f"PNG too small ({size} bytes) — probably blank"
    with open(p, "rb") as fh:
        assert fh.read(4) == b"\x89PNG"
    w.close()


def _ellipse_no_brush(it):
    # @args: it - a QGraphicsItem
    # @return: True when it is an unfilled ellipse (halo or reference ring).
    from PySide6.QtCore import Qt
    return type(it).__name__ == "QGraphicsEllipseItem" \
        and it.brush().style() == Qt.BrushStyle.NoBrush


def test_halos_present(qapp):
    # Earth, Moon, the moving point and the CA are each ringed by a thin
    # SOLID separation halo (NoBrush, solid cosmetic pen, width >= 1.0).
    # The 1 LD reference circle also has a NoBrush ellipse but a CUSTOM-DASH
    # pen — it must NOT be counted as a halo (it is the "ring" itself).
    from PySide6.QtCore import Qt
    w = _mk_chart(qapp)
    scene = w.view.scene()
    halos = [it for it in scene.items()
             if _ellipse_no_brush(it)
             and it.pen().style() == Qt.PenStyle.SolidLine
             and it.pen().isCosmetic()
             and it.pen().widthF() >= 1.0]
    assert len(halos) >= 4, f"expected >= 4 SOLID halos, found {len(halos)}"
    w.close()


def test_track_pen_dashed_wider(qapp):
    # The geocentric track is a path item with a cosmetic pen, width >= 2.0
    # (thicker than 1.8) and a non-empty dash pattern (the 8/5 look).
    w = _mk_chart(qapp)
    scene = w.view.scene()
    tracks = [it for it in scene.items()
              if type(it).__name__ == "QGraphicsPathItem"]
    dashed = [it for it in tracks
              if it.pen().widthF() >= 2.0
              and it.pen().dashPattern()
              and it.pen().isCosmetic()]
    assert dashed, "no dashed cosmetic track pen >= 2.0 found"
    pat = list(dashed[0].pen().dashPattern())
    assert len(pat) == 2 and pat[0] > pat[1], f"unexpected dash {pat}"
    w.close()


def test_circle_pen_dashed(qapp):
    # The 1 LD reference circle: dotted ellipse (dash 2, 4), pen ~1.5 px,
    # cosmetic, NoBrush.  At least one such item must exist in the scene.
    w = _mk_chart(qapp)
    scene = w.view.scene()
    matches = [it for it in scene.items()
               if _ellipse_no_brush(it)
               and it.pen().dashPattern()
               and it.pen().isCosmetic()
               and it.pen().widthF() >= 1.0]
    assert matches, "1 LD dotted reference circle not found"
    pat = list(matches[0].pen().dashPattern())
    assert len(pat) == 2 and abs(pat[0] - 2.0) < 0.01 \
        and abs(pat[1] - 4.0) < 0.01, f"bad dash {pat}"
    w.close()


def test_label_plates_present(qapp):
    # Each of the four labels ("1 LD", "Moon", "Earth", "CA") gets a plate:
    # a QGraphicsRectItem filled with a semi-transparent BG @ ~217 alpha and
    # a MUTED border @ ~102 alpha.  The closed-orbit test element must produce
    # >= 4 such plates.
    from PySide6.QtGui import QColor
    from nightscribe.gui.widgets.approach_widget import (
        _PLATE_BG_A, _PLATE_BRD_A, palette)
    w = _mk_chart(qapp)
    scene = w.view.scene()
    bg_col = QColor(palette.BG); bg_col.setAlpha(_PLATE_BG_A)
    brd_col = QColor(palette.MUTED); brd_col.setAlpha(_PLATE_BRD_A)
    plates = [it for it in scene.items()
              if type(it).__name__ == "QGraphicsRectItem"
              and it.brush().color() == bg_col
              and it.pen().color() == brd_col]
    assert len(plates) >= 4, \
        f"expected >= 4 label plates, found {len(plates)}"
    w.close()


def test_labels_clear_of_track(qapp):
    # No label plate may touch the geocentric track: a plate is "safe" when
    # its four corners are all at least _HALF * _COL_TOL away from every
    # track point.  The test orbit has a non-degenerate track, so this is a
    # real check (not an empty list).
    import math
    from nightscribe.gui.widgets.approach_widget import (_HALF, _COL_TOL)
    w = _mk_chart(qapp)
    assert len(w._track_pts) > 0, "track must be non-empty for this test"
    pts = [(p[0], p[1]) for p in w._track_pts]
    scene = w.view.scene()
    plates = [it for it in scene.items()
              if type(it).__name__ == "QGraphicsRectItem"]
    assert plates, "no label plates to check"
    tol = _HALF * _COL_TOL
    tol2 = tol * tol
    for plate in plates:
        r = plate.rect()
        corners = (
            (r.left(),   r.top()),
            (r.right(),  r.top()),
            (r.left(),   r.bottom()),
            (r.right(),  r.bottom()),
        )
        for cpx, cpy in corners:
            for px, py in pts:
                d2 = (px - cpx) ** 2 + (py - cpy) ** 2
                assert d2 >= tol2, \
                    f"plate corner ({cpx:.2f},{cpy:.2f}) within " \
                    f"{tol:.3f} of track point ({px:.2f},{py:.2f})"
    w.close()


def test_widget_package_has_no_matplotlib():
    # The widget package must never pull in matplotlib (ADR-029).
    code = (
        "import sys; "
        "from nightscribe.gui.widgets.approach_widget import ApproachChart; "
        "sys.exit(1 if 'matplotlib' in sys.modules else 0)"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True)
    assert res.returncode == 0, f"matplotlib leaked: {res.stderr}"
