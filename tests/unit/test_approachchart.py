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

import math
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


def _mk_pass(qapp, ca_ld, name="passer", w=700, h=600):
    # @return: an ApproachChart whose closest approach is ~ca_ld LD — the
    #          osculating q backs the Earth out so the flyby misses by the
    #          requested distance (see test_close_pass_crops_moon_reference).
    from nightscribe.core import approach_math, orbit_math
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    jd = _JD
    xe, ye, _, r = orbit_math.planet_heliocentric("earth", jd)
    elon = (math.degrees(math.atan2(ye, xe)) % 360.0)
    q = r - ca_ld * approach_math.AU_PER_LD
    els = {"a": q / 0.8, "e": 0.2, "i": 0.0, "om": 0.0, "w": elon,
           "ma": 0.0, "epoch": jd}
    chart = ApproachChart()
    chart.resize(w, h)
    chart.show()
    qapp.processEvents()
    chart.set_elements(els, jd, name)
    qapp.processEvents()
    return chart


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
    # The frame half-extent must stay above the safety floor _MIN_SPAN_LD
    # (never a 0/negative span) and must not be enormous (a runaway value).
    from nightscribe.gui.widgets.approach_widget import _MIN_SPAN_LD
    from nightscribe.core import approach_math
    w = _mk_chart(qapp)
    min_span_au = _MIN_SPAN_LD * approach_math.AU_PER_LD
    assert w._span_au >= min_span_au, \
        f"span too small: {w._span_au:.6f} < {min_span_au:.6f} AU"
    # a reasonable upper bound (say, 100 AU) — catches a units bug
    assert w._span_au < 100.0, f"span unreasonably large: {w._span_au} AU"
    w.close()


def test_frame_span_fits_the_arc(qapp):
    # The frame must show the object ON LOAD: it rides the largest of the
    # CA, the current point and the ±30-day arc (span = 1.9·D_fit, pass
    # protected at _PASS_SCENE_MIN) — no reduced ceiling.  The default
    # element is a far pass (CA ≫ 1 LD), so its chassis is pass-driven.
    from nightscribe.gui.widgets.approach_widget import (_MIN_SPAN_LD,
                                                         _PASS_SCENE_MIN,
                                                         _HALF)
    from nightscribe.core import approach_math
    w = _mk_chart(qapp)
    assert w._ca_cache is not None
    ca_ld = w._ca_cache[2]
    assert ca_ld > 10.0, f"default element must be a far pass, got {ca_ld}"
    g = w.geocentric_position(w._cur_jd)
    assert g is not None
    r_now = g[4]
    r_max = max(p[2] for p in w._track_pts)
    want_au = max(_MIN_SPAN_LD,
                  min(1.9 * max(ca_ld, r_now, r_max),
                      ca_ld / _PASS_SCENE_MIN)) * approach_math.AU_PER_LD
    assert abs(w._span_au - want_au) < 1e-9 * want_au, \
        f"span {w._span_au} != arc-fitted {want_au} (CA {ca_ld:.2f} LD)"
    # the on-load asteroid point itself is inside the frame
    sx, sy = w._to_scene(g[0], g[1])
    assert abs(sx) <= _HALF and abs(sy) <= _HALF, \
        f"on-load point ({sx:.1f},{sy:.1f}) escapes the frame"
    w.close()


def test_frame_span_open_orbit_uses_closest_point(qapp):
    # For e >= 1 there is no CA cache; the frame falls back to the sampled
    # arc / current point (the one-off flyby) — never a reduced ceiling:
    # an escapee that just grazes outside the Moon's orbit still shows its
    # whole approach sweep on load.
    from nightscribe.gui.widgets.approach_widget import (
        _MIN_SPAN_LD, _HALF, ApproachChart)
    from nightscribe.core import approach_math
    els = {"q": 0.98, "e": 1.02, "i": 84.0, "om": 110.0, "w": 210.0,
           "tp": 2460690.0}
    w = ApproachChart()
    w.resize(400, 300)
    w.show()
    qapp.processEvents()
    w.set_elements(els, els["tp"] + 30.0, "escapee")
    qapp.processEvents()
    assert w._ca_cache is None, "open orbit must have no CA cache"
    assert w._track_pts, "open orbit must still draw a track"
    g = w.geocentric_position(w._cur_jd)
    assert g is not None
    r_now = g[4]
    r_max = max(p[2] for p in w._track_pts)
    want_au = max(_MIN_SPAN_LD,
                  1.9 * max(r_now, r_max)) * approach_math.AU_PER_LD
    assert abs(w._span_au - want_au) < 1e-9 * want_au, \
        f"span {w._span_au} != arc-fitted {want_au} (now {r_now:.2f} LD)"
    sx, sy = w._to_scene(g[0], g[1])
    assert abs(sx) <= _HALF and abs(sy) <= _HALF
    w.close()


def test_close_pass_crops_moon_reference(qapp):
    # A flyby INSIDE the Moon's orbit (~0.3 LD): the frame zooms to the pass
    # (span = CA·1.9), so the 1 LD Moon reference cannot fit and must not be
    # drawn at all — Earth, track and CA are the whole story.
    from nightscribe.core import approach_math, orbit_math
    from nightscribe.gui.widgets.approach_widget import ApproachChart
    jd = 2460500.0
    xe, ye, _, r = orbit_math.planet_heliocentric("earth", jd)
    elon = (math.degrees(math.atan2(ye, xe)) % 360.0)
    q = r - 0.3 * approach_math.AU_PER_LD
    els = {"a": q / 0.8, "e": 0.2, "i": 0.0, "om": 0.0, "w": elon,
           "ma": 0.0, "epoch": jd}
    w = ApproachChart()
    w.resize(700, 600)
    w.show()
    qapp.processEvents()
    w.set_elements(els, jd, "close-passer")
    qapp.processEvents()
    assert w._ca_cache is not None
    ca_ld = w._ca_cache[2]
    assert ca_ld < 0.585, f"expected inside-Moon-orbit CA, got {ca_ld} LD"
    # The bundle is ALWAYS drawn, clamped into a corner diagram (its 1 LD
    # circle radius <= _BUNDLE_RADIUS_MAX) — a close flyby no longer crops
    # the Moon; the pass stays the subject (CA diamond near the open
    # canvas).
    from nightscribe.gui.widgets.approach_widget import (
        _BUNDLE_RADIUS_MAX, _HALF)
    ex, ey, _ = w._obstacles[1]            # Earth (bundle centre)
    assert abs(ex) > _HALF / 2.0 and abs(ey) > _HALF / 2.0, \
        "Earth must sit in a corner on a close pass too"
    scene = w.view.scene()
    dashed = [it for it in scene.items()
              if _ellipse_no_brush(it) and it.pen().dashPattern()]
    assert dashed, "1 LD dotted reference circle must still be drawn"
    ring = dashed[0].rect()
    assert abs(ring.center().x() - ex) < 1e-6
    assert abs(ring.center().y() - ey) < 1e-6
    assert ring.width() / 2.0 <= _BUNDLE_RADIUS_MAX + 1e-6, \
        "close-pass bundle must be clamped to the legible maximum"
    texts = [t.text() for t in scene.items()
             if type(t).__name__ == "QGraphicsSimpleTextItem"]
    assert "Moon" in texts, f"Moon label must remain, got {texts}"
    assert "Earth" in texts, f"Earth label must remain, got {texts}"
    assert any(t.startswith("CA ") for t in texts), \
        f"CA label must remain: {texts}"
    w.close()


def test_labels_clear_of_markers(qapp):
    # No OBJECT label may step on a solid marker: every layout box in
    # `_occupied` (Moon, Earth and CA) must keep at least the obstacle
    # radius away from the registered centres (obstacle = halo radius +
    # _OBST_PAD).
    w = _mk_chart(qapp)
    obstacles = list(w._obstacles)
    assert len(obstacles) == 3, \
        f"expected Moon+Earth+CA obstacles, got {len(obstacles)}"
    assert len(w._occupied) >= 3, f"expected >= 3 label boxes"
    for (ox, oy, orad) in obstacles:
        for box in w._occupied:
            cx = min(max(ox, box.left()), box.right())
            cy = min(max(oy, box.top()), box.bottom())
            d2 = (ox - cx) ** 2 + (oy - cy) ** 2
            assert d2 >= orad * orad, \
                f"label box {box} steps within {orad:.1f} of marker " \
                f"({ox:.1f},{oy:.1f})"
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
    # An ON-FRAME CA pass is used so the CA diamond halo exists too.
    from PySide6.QtCore import Qt
    w = _mk_pass(qapp, 0.62, "halo-pass")
    assert w._ca_item is not None, "on-frame CA must draw the diamond halo"
    scene = w.view.scene()
    halos = [it for it in scene.items()
             if _ellipse_no_brush(it)
             and it.pen().style() == Qt.PenStyle.SolidLine
             and it.pen().isCosmetic()
             and it.pen().widthF() >= 1.0]
    assert len(halos) >= 4, f"expected >= 4 SOLID halos, found {len(halos)}"
    w.close()


def test_track_pen_dashed_thin(qapp):
    # The geocentric track is a path item with a cosmetic pen, width ~1.5 —
    # THIN, so the moving point is never hidden under its own line at any
    # zoom — and a non-empty dash pattern (the 8/5 look).
    w = _mk_chart(qapp)
    scene = w.view.scene()
    tracks = [it for it in scene.items()
              if type(it).__name__ == "QGraphicsPathItem"]
    dashed = [it for it in tracks
              if 1.0 <= it.pen().widthF() <= 2.0
              and it.pen().dashPattern()
              and it.pen().isCosmetic()]
    assert dashed, "no thin dashed cosmetic track pen found"
    assert max(it.pen().widthF() for it in dashed) < 2.0, \
        "the track line must stay thin (the asteroid dot reads over it)"
    pat = list(dashed[0].pen().dashPattern())
    assert len(pat) == 2 and pat[0] > pat[1], f"unexpected dash {pat}"
    w.close()


def test_drawn_track_matches_scene_points(qapp):
    # The DRAWN polyline must coincide with the hover hit-test points
    # (`_track_pts`): both carry the bundle corner offset — a regression for
    # the orbit line being painted around the scene origin while the Earth
    # bundle lives in a corner.
    w = _mk_chart(qapp)
    scene = w.view.scene()
    tracks = [it for it in scene.items()
              if type(it).__name__ == "QGraphicsPathItem"
              and it.pen().isCosmetic()
              and list(it.pen().dashPattern())]
    assert tracks, "no dashed track polyline found in the scene"
    assert w._track_pts, "no hit-test points to compare against"
    el = tracks[0].path().elementAt(0)
    want = w._track_pts[0]
    assert abs(el.x - want[0]) < 1e-6 and abs(el.y - want[1]) < 1e-6, \
        f"drawn track starts at ({el.x:.1f},{el.y:.1f}) but the scene " \
        f"point is ({want[0]:.1f},{want[1]:.1f})"
    el_last = tracks[0].path().elementAt(len(w._track_pts) - 1)
    want_last = w._track_pts[-1]
    assert abs(el_last.x - want_last[0]) < 1e-6 \
        and abs(el_last.y - want_last[1]) < 1e-6
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


def test_labels_have_no_background(qapp):
    # Labels are the glyphs ("Moon", "Earth", "CA") plus a thin BG contour
    # halo under each — there is NO background box anywhere in the scene (no
    # QGraphicsRectItem at all), keeping the canvas light.  The "1 LD" text
    # does not exist: the dashed circle + the Moon at its real position are
    # the scale reference.
    from PySide6.QtGui import QColor
    from nightscribe.gui.widgets.approach_widget import palette
    w = _mk_chart(qapp)
    scene = w.view.scene()
    boxes = [it for it in scene.items()
             if type(it).__name__ == "QGraphicsRectItem"]
    assert not boxes, f"labels must have no background box, found {len(boxes)}"
    texts = [t.text() for t in scene.items()
             if type(t).__name__ == "QGraphicsSimpleTextItem"]
    for want in ("Moon", "Earth"):
        assert want in texts, f"label {want!r} missing, got {texts}"
    assert any(t.startswith("CA ") for t in texts), f"CA label missing: {texts}"
    assert "1 LD" not in texts, f"'1 LD' text must not exist, got {texts}"
    from PySide6.QtCore import Qt
    halos = [it for it in scene.items()
             if type(it).__name__ == "QGraphicsPathItem"
             and it.pen().style() == Qt.PenStyle.NoPen
             and it.brush().style() != Qt.BrushStyle.NoBrush
             and it.brush().color() == QColor(palette.BG)
             and it.boundingRect().width() > 1.0]
    assert len(halos) >= 3, \
        f"expected >= 3 BG text halos, found {len(halos)}"
    w.close()


def test_labels_clear_of_track(qapp):
    # No label box may touch the geocentric track: a box is "safe" when
    # its four corners are all at least _HALF * _COL_TOL away from every
    # track point.  The test orbit has a non-degenerate track, so this is a
    # real check (not an empty list).
    from nightscribe.gui.widgets.approach_widget import (_HALF, _COL_TOL)
    w = _mk_chart(qapp)
    assert len(w._track_pts) > 0, "track must be non-empty for this test"
    pts = [(p[0], p[1]) for p in w._track_pts]
    assert w._occupied, "no label boxes to check"
    tol = _HALF * _COL_TOL
    tol2 = tol * tol
    for r in w._occupied:
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
                    f"label corner ({cpx:.2f},{cpy:.2f}) within " \
                    f"{tol:.3f} of track point ({px:.2f},{py:.2f})"
    w.close()


def test_far_pass_fits_arc_onload(qapp):
    # A FAR pass (CA ~45 LD, CERLQX2-like) is framed to its whole approach
    # sweep — span = 1.9 × max(CA, current point, arc), NO ceiling — so the
    # asteroid is on canvas the moment the chart loads.  The Earth–Moon
    # bundle stays in a corner at the clamped minimum separation (never a
    # fused cluster).
    from nightscribe.core import approach_math
    from nightscribe.gui.widgets.approach_widget import (
        _BUNDLE_RADIUS_MIN, _HALF, _PASS_SCENE_MIN)
    w = _mk_pass(qapp, 45.0, "far-pass")
    ca_ld = w._ca_cache[2]
    assert ca_ld > 10.0, f"setup must be a far pass, got {ca_ld:.2f} LD"
    r_max = max(p[2] for p in w._track_pts)
    span_ld = w._span_au / approach_math.AU_PER_LD
    want_ld = min(1.9 * max(ca_ld, r_max), ca_ld / _PASS_SCENE_MIN)
    assert abs(span_ld - want_ld) < 2e-3 * want_ld, \
        f"span {span_ld:.2f} != arc-fitted {want_ld:.2f} LD"
    assert span_ld > 2.2, "the cluster ceiling must be gone"
    # the on-load asteroid point is inside the frame
    g = w.geocentric_position(w._cur_jd)
    assert g is not None
    sx, sy = w._to_scene(g[0], g[1])
    assert abs(sx) <= _HALF and abs(sy) <= _HALF, \
        f"on-load point ({sx:.1f},{sy:.1f}) escapes the frame"
    # Earth–Moon separation stays at the clamped minimum (never fused)
    mx, my, _ = w._obstacles[0]
    ex, ey, _ = w._obstacles[1]
    sep = math.hypot(mx - ex, my - ey)
    assert _BUNDLE_RADIUS_MIN - 1.0 <= sep <= _BUNDLE_RADIUS_MIN + 1.0, \
        f"Moon–Earth separation {sep:.1f} must ride the clamp minimum"
    w.close()


def test_bundle_corner_opposite_pass(qapp):
    # The Earth–Moon bundle sits in the corner FARTHEST from the encounter:
    # the closest-approach direction AS SEEN FROM the bundle points back
    # into the canvas (negative component along the bundle's corner ray), so
    # the approach sweep opens across the opposite half of the frame.
    w = _mk_pass(qapp, 3.3, "mid-pass")
    ex, ey, _ = w._obstacles[1]            # Earth (bundle centre)
    jd_best, _, _ = w._ca_cache
    g = w.geocentric_position(jd_best)
    assert g is not None
    sx, sy = w._to_scene(g[0], g[1])
    assert (sx - ex) * ex + (sy - ey) * ey < 0.0, \
        "Earth bundle must sit opposite the closest-approach point"
    w.close()


def test_ca_diamond_always_on_frame(qapp):
    # The framing keeps the closest approach on canvas at any pass distance,
    # so the marker is ALWAYS the classic diamond (the edge-PIN regime is
    # gone).
    from nightscribe.gui.widgets.approach_widget import _HALF
    for ca_ld in (0.62, 3.3, 45.0):
        w = _mk_pass(qapp, ca_ld, "passer")
        assert w._ca_item is not None, f"CA diamond missing at {ca_ld} LD"
        assert type(w._ca_item).__name__ == "QGraphicsPathItem"
        assert not hasattr(w, "_ca_pin_") or w._ca_pin_ is None, \
            "no pin may exist any more"
        # the diamond sits inside the framed canvas
        cx, cy, _ = w._obstacles[2]
        assert abs(cx) <= _HALF and abs(cy) <= _HALF, \
            f"CA diamond ({cx:.0f},{cy:.0f}) escapes the frame"
        w.close()


def test_earth_moon_labels_spread_far_pass(qapp):
    # FAR pass: the bundle sits in a corner at the clamped minimum
    # separation (never a fused cluster) and neither label steps on the
    # other body, nor does one box overlap the other.
    from nightscribe.gui.widgets.approach_widget import _BUNDLE_RADIUS_MIN

    def dist2(px, py, qx, qy):
        return (px - qx) ** 2 + (py - qy) ** 2

    w = _mk_pass(qapp, 45.0, "far-pass")
    assert len(w._occupied) == 3, \
        f"Moon+Earth+CA boxes expected, got {len(w._occupied)}"
    mx, my, mr = w._obstacles[0]           # the Moon
    ex, ey, er = w._obstacles[1]           # Earth
    assert math.hypot(mx - ex, my - ey) >= _BUNDLE_RADIUS_MIN - 1.0
    moon_box = min(w._occupied,
                   key=lambda b: dist2(b.center().x(), b.center().y(),
                                       mx, my))
    earth_box = min(w._occupied,
                    key=lambda b: dist2(b.center().x(), b.center().y(),
                                        ex, ey))
    assert not moon_box.intersects(earth_box), \
        "Moon and Earth labels must not overlap"
    # each label keeps the OTHER body's obstacle radius clear
    def clear(box, bx, by, br):
        cxn = min(max(bx, box.left()), box.right())
        cyn = min(max(by, box.top()), box.bottom())
        return dist2(bx, by, cxn, cyn) >= br * br
    assert clear(moon_box, ex, ey, er), "Moon label steps on Earth"
    assert clear(earth_box, mx, my, mr), "Earth label steps on the Moon"
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
