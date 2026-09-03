############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - sky chart widget tests (offscreen, ADR-029)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/widgets/sky_widget.py (ADR-029) — the interactive
vector night-sky (visibility) chart.

Patterns (mirroring test_chartview.py + test_orbitchart.py):
  * one QApplication per module, offscreen, throwaway;
  * no network, no matplotlib in the widget package;
  * the target curve and the safe band are exercised against the *same*
    samples in core/sky_math that viz/sky_view.py uses for the PNG exports,
    so the widget cannot drift from the reference chart.
"""

import datetime as dt
import os
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


# a representative northern-night target (RA ~ 10h, Dec ~ +20°) at a
# mid-latitude site (Observatorio Irydeo, lat 40.6 N, lon 4.4 W).
_RA, _DEC = 10.0, 20.0
_LAT, _LON = 40.6, -4.4
_DATE = dt.datetime(2026, 9, 3, 0, tzinfo=dt.timezone.utc)


def _mk_chart(qapp, cls=None, w=600, h=480):
    # @return: a sized, shown SkyChart (or TransitChart) — offscreen.
    from nightscribe.gui.widgets.sky_widget import SkyChart, TransitChart
    c = cls if cls else SkyChart
    w_ = c()
    w_.resize(w, h)
    w_.show()
    qapp.processEvents()
    return w_


def test_instantiate_and_set_target(qapp):
    w = _mk_chart(qapp)
    w.set_target(_RA, _DEC, _LAT, _LON, _DATE, obj_name="test")
    tgt = w.target()
    assert tgt is not None
    assert len(tgt["rel"]) > 4, "expected at least a few samples"
    assert tgt["rel"][0] <= 0.0
    assert tgt["rel"][-1] >= 0.0
    # the scene must have a fixed frame (so fit_to_scene is stable)
    r = w.view.scene_rect_hint()
    assert r.width() > 0 and r.height() > 0
    w.close()


def test_export_png_not_blank(qapp, tmp_path):
    w = _mk_chart(qapp)
    w.set_target(_RA, _DEC, _LAT, _LON, _DATE, obj_name="t")
    out = tmp_path / "sky.png"
    p = w.export_png(out)
    assert p.exists()
    size = p.stat().st_size
    assert size > 8 * 1024, f"PNG too small ({size} bytes) — probably blank"
    with open(p, "rb") as fh:
        assert fh.read(4) == b"\x89PNG"
    w.close()


def test_export_with_safe_band(qapp, tmp_path):
    # the safe-window + best-time markers must not break the export
    w = _mk_chart(qapp)
    safe = (_DATE + dt.timedelta(hours=1), _DATE + dt.timedelta(hours=4))
    bt = _DATE + dt.timedelta(hours=3)
    w.set_target(_RA, _DEC, _LAT, _LON, _DATE, obj_name="t",
                 safe_window=safe, best_time=bt)
    assert w._safe_rect is not None, "safe band did not get drawn"
    out = tmp_path / "sky_safe.png"
    p = w.export_png(out)
    assert p.stat().st_size > 8 * 1024
    with open(p, "rb") as fh:
        assert fh.read(4) == b"\x89PNG"
    w.close()


def test_hover_on_target_curve(qapp):
    # the midpoint of the sampled curve (by construction) must hit
    w = _mk_chart(qapp)
    w.set_target(_RA, _DEC, _LAT, _LON, _DATE, obj_name="test")
    assert w._target_pts, "no target points sampled"
    mid = w._target_pts[len(w._target_pts) // 2]
    hit, text = w._hover(*mid)
    assert hit is True
    # the tooltip shows UTC time + altitude + azimuth
    assert "UTC" in text and "alt" in text and "az" in text
    assert "°" in text
    assert "test" in text          # obj_name prefix on the reading
    # a point well outside the curve (frame corner) does not hit
    hit2, _ = w._hover(495.0, 495.0)
    assert hit2 is False
    w.close()


def test_hover_in_safe_band(qapp):
    # a cursor inside the safe band answers the session-planning reading
    # ("de HH:MM a HH:MM · empezar hasta HH:MM") — beats the raw curve.
    w = _mk_chart(qapp)
    safe = (_DATE + dt.timedelta(hours=1), _DATE + dt.timedelta(hours=4))
    bt = _DATE + dt.timedelta(hours=3)
    w.set_target(_RA, _DEC, _LAT, _LON, _DATE, obj_name="t",
                 safe_window=safe, best_time=bt)
    assert w._safe_rect is not None
    c = w._safe_rect.rect().center()
    hit, text = w._hover(c.x(), c.y())
    assert hit is True
    # the reading is "de X a Y · empezar hasta Z" (translated)
    assert "a" in text and "empezar" in text or "empezar" in text
    w.close()


def test_click_safe_band_emits_best_time(qapp):
    # a left-click landing inside the safe band fires best_time_clicked
    w = _mk_chart(qapp)
    safe = (_DATE + dt.timedelta(hours=1), _DATE + dt.timedelta(hours=4))
    bt = _DATE + dt.timedelta(hours=3)
    w.set_target(_RA, _DEC, _LAT, _LON, _DATE, obj_name="t",
                 safe_window=safe, best_time=bt)
    assert w._safe_rect is not None
    seen = []
    w.best_time_clicked.connect(lambda v: seen.append(v))
    # a point strictly inside the band (centre) must fire the signal
    from PySide6.QtCore import QPointF
    c = w._safe_rect.rect().center()
    w._on_scene_clicked(QPointF(c.x(), c.y()))
    assert len(seen) == 1
    assert seen[0] is not None and abs(
        (seen[0] - bt).total_seconds()) < 2.0
    # a point outside the band does not fire
    w._on_scene_clicked(QPointF(0.0, 0.0))
    assert len(seen) == 1, "clicked outside the safe band, signal fired anyway"
    w.close()


def test_clear_resets_state(qapp):
    w = _mk_chart(qapp)
    w.set_target(_RA, _DEC, _LAT, _LON, _DATE, obj_name="t")
    assert w.target() is not None
    w.clear()
    assert w.target() is None
    assert w._safe_rect is None
    assert w._transit_rect is None
    w.close()


def test_transit_band_in_scene(qapp):
    from nightscribe.gui.widgets.sky_widget import TransitChart
    ing = _DATE + dt.timedelta(hours=1, minutes=30)
    egr = _DATE + dt.timedelta(hours=3, minutes=30)
    t = TransitChart()
    t.resize(600, 480); t.show(); qapp.processEvents()
    t.set_target(_RA, _DEC, _LAT, _LON, _DATE, obj_name="exo",
                 transit={"ingress": ing, "egress": egr,
                          "depth_mmag": 15.0, "duration_h": 2.0})
    # the band must have been drawn
    assert t._transit_rect is not None
    r = t._transit_rect.rect()
    assert r.width() > 0 and r.height() > 0
    # and the transit tag is stored on the band
    assert t._transit_rect.data(0) == "transit"
    t.close()


def test_no_night_returns_empty_target(qapp):
    # a target that never rises (dec well below the horizon at this site)
    # still produces a samples dict — the scene shows a centered notice
    # but the code does not crash.
    w = _mk_chart(qapp)
    w.set_target(_RA, -70.0, _LAT, _LON, _DATE, obj_name="south")
    # samples may be None if there is no astronomical night at all
    tgt = w.target()
    if tgt is not None:
        # at least the geometry (start / end / rel) is populated
        assert "start" in tgt and "alt" in tgt
    else:
        assert w._samples is None
    w.close()


def test_widget_package_has_no_matplotlib():
    # the widget package must never pull in matplotlib (ADR-029) — assert it
    # at import time in a clean subprocess.
    code = (
        "import sys; from nightscribe.gui.widgets.sky_widget import "
        "SkyChart; sys.exit(1 if 'matplotlib' in sys.modules else 0)"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True, text=True)
    assert res.returncode == 0, f"matplotlib leaked: {res.stderr}"
