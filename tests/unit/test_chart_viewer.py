############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Chart viewer tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for the chart viewer (fit/zoom/size memory).

Pattern of tests/unit/test_theme.py: throwaway QApplication on the
offscreen platform, a real chart PNG drawn with the own viz modules, no
network. The config singleton is pointed at a tmp file so "remember my
window" is exercised without touching the user's real settings file.
"""

import os

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


@pytest.fixture()
def chart(qapp, tmp_path):
    # A real panel-size chart PNG (the same one the overview panel shows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from nightscribe.viz import orbit_view
    out = tmp_path / "4443_Atlas_orbit.png"
    orbit_view.draw_orbit(
        {"a": 0.9224, "e": 0.1912, "i": 3.33,
         "q": 0.7182, "Q": 1.1266, "per": 80.0},
        obj_name="Atlas", out=str(out), fmt="panel")
    plt.close("all")
    return out


@pytest.fixture()
def cfg(tmp_path):
    # config.get/set would otherwise read/write the user's real json
    from nightscribe.config import config
    real_file, real_data = config._file, config._data
    config._file = tmp_path / "nightscribe.json"
    config._data = {}
    try:
        yield config
    finally:
        config._file, config._data = real_file, real_data


def _events():
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()


def test_default_view_fits_without_scrolling(qapp, chart, cfg):
    # the whole point: opening a chart fills the window, no scrollbars
    from nightscribe.gui.chart_viewer import ChartViewer
    v = ChartViewer(chart, title="orbit")
    v.show()
    _events()
    v._zoom_fit()  # the singleShot(0) fit, in a headless run
    pix = v._label.pixmap()
    assert pix is not None and not pix.isNull()
    vw = v._scroll.viewport().width()
    vh = v._scroll.viewport().height()
    assert vw > 20 and vh > 20
    assert v._label.width() <= vw + 2, "horizontal scrollbar by default"
    assert v._label.height() <= vh + 2, "vertical scrollbar by default"
    # the fitted image is large enough to read (not a tiny thumbnail)
    assert v._label.width() >= 0.6 * vw
    v.close()


def test_fit_follows_a_bigger_window(qapp, chart, cfg):
    from nightscribe.gui.chart_viewer import ChartViewer
    v = ChartViewer(chart)
    v.show()
    _events()
    v._zoom_fit()
    small = v._label.width()
    v.resize(1700, 1000)
    _events()
    v._zoom_fit()
    assert v._label.width() > small
    v.close()


def test_zoom_buttons_1to1_in_out(qapp, chart, cfg):
    from nightscribe.gui.chart_viewer import ChartViewer
    v = ChartViewer(chart)
    v.show()
    v._zoom_11()
    assert v._label.width() == v._pix.width()
    v._zoom_in()
    assert v._label.width() == int(v._pix.width() * 1.25)
    v._zoom_out()
    assert v._label.width() == v._pix.width()
    v.close()


_ELEMENT = {"a": 2.3, "e": 0.35, "i": 8.0, "om": 10.0, "w": 20.0,
            "ma": 50.0, "epoch": 2460000.0}


def _widget(qapp, w=600, h=500):
    # @return: a sized, populated OrbitChart (offscreen) for widget mode.
    from nightscribe.gui.widgets.orbit_widget import OrbitChart
    w_ = OrbitChart()
    w_.set_elements(_ELEMENT, 2460500.0, "test object")
    w_.resize(w, h)
    w_.show()
    qapp.processEvents()
    return w_


def test_widget_mode_embeds_the_chart(qapp, cfg):
    # widget mode: the live chart is inside the dialog, no scroll/pixmap
    from nightscribe.gui.chart_viewer import ChartViewer
    ch = _widget(qapp)
    v = ChartViewer(widget=ch, title="orbit live")
    assert v._mode == "widget"
    assert v._label is None and v._scroll is None
    assert ch.parent() == v
    assert v._view is ch.view
    # the canvas is fitted to the scene once the geometry lands
    v.resize(900, 700)
    _events()
    v._zoom_fit()
    sc = v._view.transform().m11()
    assert sc > 0
    v.close()


def test_widget_mode_zoom_buttons_drive_the_view(qapp, cfg):
    # Zoom + / − on the toolbar scale the ChartView (not a frozen pixmap)
    from nightscribe.gui.chart_viewer import ChartViewer
    v = ChartViewer(widget=_widget(qapp))
    v.show()
    _events()
    s0 = v._view.transform().m11()
    v._zoom_in()
    assert v._view.transform().m11() > s0
    v._zoom_out()
    v._zoom_out()
    assert v._view.transform().m11() <= s0 * 1.001
    # Fit brings the canvas back to its stable reference
    v._zoom_fit()
    assert v._view.transform().m11() > 0
    v.close()


def test_widget_mode_export_renders_the_scene(qapp, cfg, tmp_path):
    # widget-mode export renders what is on the canvas to a fresh PNG
    from nightscribe.gui.chart_viewer import ChartViewer
    from PySide6.QtWidgets import QFileDialog
    v = ChartViewer(widget=_widget(qapp), title="live")
    v.show()
    v.resize(900, 700)
    _events()
    v._zoom_fit()
    dest = tmp_path / "live_orbit.png"
    orig = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (str(dest), ""))
    try:
        v._export()
    finally:
        QFileDialog.getSaveFileName = orig
    import struct
    with open(dest, "rb") as f:
        data = f.read()
    assert len(data) > 1000
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", data[16:24])
    assert w > 100 and h > 100
    v.close()


def test_widget_mode_keeps_size_memory(qapp, cfg):
    # window-size memory is keyed by the title for widget mode too
    from nightscribe.gui.chart_viewer import ChartViewer
    v1 = ChartViewer(widget=_widget(qapp), title="mem")
    v1.resize(820, 540)
    v1.close()
    sizes = cfg.get("chart_viewer_sizes") or {}
    assert sizes.get("mem") == [820, 540]
    v2 = ChartViewer(widget=_widget(qapp), title="mem")
    assert (v2.size().width(), v2.size().height()) == (820, 540)
    v2.close()


def test_open_chart_widget_factory(qapp, cfg):
    # the factory opens without exec'ing the dialog in tests
    from unittest.mock import patch
    from nightscribe.gui import chart_viewer
    ch = _widget(qapp)
    with patch.object(chart_viewer.ChartViewer, "exec") as ex:
        chart_viewer.open_chart_widget(None, ch, title="factory")
        ex.assert_called_once()
    v = chart_viewer.ChartViewer(widget=ch, title="factory")
    assert v._widget is ch
    v.close()


def test_window_size_is_remembered_per_chart(qapp, chart, cfg):
    from nightscribe.gui.chart_viewer import ChartViewer

    # first open -> user resizes -> close -> size stored on the chart
    v1 = ChartViewer(chart)
    v1.show()
    _events()
    v1.resize(780, 520)
    v1.close()
    sizes = cfg.get("chart_viewer_sizes") or {}
    assert sizes.get(chart.name) == [780, 520]

    # second open: lands at the remembered size and closes it unchanged
    v2 = ChartViewer(chart)
    assert (v2.size().width(), v2.size().height()) == (780, 520)
    v2.close()
    assert (cfg.get("chart_viewer_sizes") or {})[chart.name] == [780, 520]

    # a chart name with no memory of its own gets the fitted size
    other = chart.with_name("other_orbit.png")
    chart.rename(other)
    v3 = ChartViewer(other)
    v3.close()
    os.replace(other, chart)
    assert (v3.size().width(), v3.size().height()) != (780, 520)
