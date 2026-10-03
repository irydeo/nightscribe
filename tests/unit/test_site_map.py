############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the site picker map (Interfaz 1.5)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Welcome map widget and its dialog.

No network and no window: the map is pure geometry plus one local ephemeris
call, and the click is synthesised with real mouse events so the whole
press/move/release path is what runs.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture()
def mapw(qapp):
    from nightscribe.gui.widgets.site_map import SiteMap
    m = SiteMap()
    m.resize(720, 260)
    return m


def _click(m, x, y):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        ev = QMouseEvent(kind, QPointF(x, y), Qt.LeftButton, Qt.LeftButton,
                         Qt.NoModifier)
        (m.mousePressEvent if kind == QEvent.MouseButtonPress
         else m.mouseReleaseEvent)(ev)


def test_projection_round_trip(mapw):
    for lon, lat in ((-3.70379, 40.41678), (151.2, -33.87),
                     (-70.6, -33.45), (0.0, 0.0), (179.9, 89.9)):
        x, y = mapw.to_px(lon, lat)
        back_lon, back_lat = mapw.to_geo(x, y)
        assert abs(back_lon - lon) < 1e-6
        assert abs(back_lat - lat) < 1e-6


def test_at_zoom_one_the_map_covers_the_box(mapw):
    # Cover, not contain: with contain the world is drawn at 2:1 inside a
    # 3:1 box and two black bands sit at the sides. The map opens filling
    # its box, and the poles are reached by zooming out on purpose.
    rect = mapw.map_rect()
    assert rect.width() >= mapw.width() - 0.5
    assert rect.height() >= mapw.height() - 0.5
    assert abs(rect.width() / rect.height() - 2.0) < 1e-6


def test_zooming_out_reveals_the_whole_world(mapw):
    _wheel(mapw, 360, 130, 40, up=False)
    assert mapw._zoom == 0.5
    rect = mapw.map_rect()
    assert rect.width() <= mapw.width() + 0.5
    assert rect.height() <= mapw.height() + 0.5


def test_a_click_picks_the_point_under_the_cursor(mapw):
    seen = []
    mapw.picked.connect(lambda lat, lon: seen.append((lat, lon)))
    x, y = mapw.to_px(-3.70379, 40.41678)
    _click(mapw, x, y)
    assert mapw.has_site()
    lat, lon = mapw.site()
    assert abs(lat - 40.41678) < 0.05
    assert abs(lon + 3.70379) < 0.05
    assert len(seen) == 1


def test_a_drag_pans_and_does_not_pick(mapw):
    seen = []
    mapw.picked.connect(lambda lat, lon: seen.append((lat, lon)))
    mapw._zoom = 6.0
    mapw._invalidate_base()
    before = (mapw._clat, mapw._clon)
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    mapw.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(300, 130),
                                     Qt.LeftButton, Qt.LeftButton,
                                     Qt.NoModifier))
    mapw.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, QPointF(240, 130),
                                    Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    mapw.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease,
                                       QPointF(240, 130), Qt.LeftButton,
                                       Qt.LeftButton, Qt.NoModifier))
    assert seen == []                       # a pan is not a pick
    assert (mapw._clat, mapw._clon) != before


def _wheel(m, x, y, steps, up=True):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    for _ in range(steps):
        m.wheelEvent(QWheelEvent(QPointF(x, y), QPointF(x, y),
                                 QPoint(0, 0), QPoint(0, 120 if up else -120),
                                 Qt.NoButton, Qt.NoModifier,
                                 Qt.ScrollUpdate, False))


def test_zoom_is_bounded_and_keeps_the_cursor_point(mapw):
    # From zoom 4 on the world is wider than the widget, so the clamp has
    # nothing to say and the point under the cursor must stay put.
    mapw._zoom = 4.0
    lon, lat = -3.7, 40.4
    x, y = mapw.to_px(lon, lat)
    _wheel(mapw, x, y, 40)
    assert mapw._zoom == 16.0
    back_lon, back_lat = mapw.to_geo(x, y)
    assert abs(back_lon - lon) < 0.02 and abs(back_lat - lat) < 0.02
    _wheel(mapw, x, y, 80, up=False)
    assert mapw._zoom == 0.5


def test_terminator_is_sane_all_year(qapp):
    # The curve has to come out finite and in range at the solstices and,
    # above all, at the equinox, where it runs nearly straight up and down
    # and the naive formula divides by ~zero.
    from nightscribe.gui.widgets.site_map import terminator_points
    from nightscribe.core import coords
    import datetime as dt
    for date in (dt.date(2026, 3, 20), dt.date(2026, 6, 21),
                 dt.date(2026, 9, 23), dt.date(2026, 12, 21),
                 dt.date(2026, 10, 2)):
        jd = coords.jd_from_datetime(
            dt.datetime(date.year, date.month, date.day, 12,
                        tzinfo=dt.timezone.utc))
        pts, dec = terminator_points(jd)
        assert len(pts) == 181
        for lon, lat in pts:
            assert -180.0 <= lon <= 180.0
            assert -90.0 <= lat <= 90.0
        # at the equinox the Sun is over the equator: the dark cap flips
        assert -23.5 <= dec <= 23.5


def test_set_site_does_not_recentre_a_panned_view(mapw):
    # Editing a digit in the spin boxes runs this on every keystroke:
    # recentring each time would yank the map away from where the observer
    # had just put it.
    mapw._zoom = 8.0
    mapw.set_site(40.4, -3.7)          # first point: the view follows it
    assert mapw._clat == 40.4
    # pan somewhere nearby, then nudge the marker: the view stays put
    mapw._clat, mapw._clon = 41.0, -2.0
    mapw.set_site(40.5, -3.8)
    assert (mapw._clat, mapw._clon) == (41.0, -2.0)
    # but a marker that would fall off the view IS followed
    mapw.set_site(-40.0, 150.0)
    assert (mapw._clat, mapw._clon) != (41.0, -2.0)


def test_set_site_none_clears_the_marker(mapw):
    mapw.set_site(40.4, -3.7)
    assert mapw.has_site()
    mapw.set_site(None, None)
    assert not mapw.has_site()
    assert mapw.site() == (None, None)


def test_dialog_returns_the_chosen_point(qapp):
    from nightscribe.gui.site_map_dialog import SiteMapDialog
    dlg = SiteMapDialog(lat=40.0, lon=-3.0, name="Here")
    assert dlg.ui.btn_map_use.isEnabled()
    assert dlg.chosen() == (40.0, -3.0)
    x, y = dlg._map.to_px(-1.5, 38.5)
    _click(dlg._map, x, y)
    lat, lon = dlg.chosen()
    assert abs(lat - 38.5) < 0.05 and abs(lon + 1.5) < 0.05
    dlg.deleteLater()


def test_dialog_opens_big_enough_to_aim(qapp):
    # It used to open at its sizeHint (332x440, with a 300x150 map): the
    # title and the minimum size declared on the .ui root never arrived,
    # because adopt_ui transplants ONLY the layout. Both are set in code
    # now, and the default size is a share of the screen.
    from nightscribe.gui.site_map_dialog import SiteMapDialog
    dlg = SiteMapDialog(lat=40.0, lon=-3.0)
    assert dlg.windowTitle()
    assert dlg.width() > dlg.sizeHint().width()
    assert dlg.width() >= 760 and dlg.height() >= 480
    assert dlg.minimumWidth() >= 760
    dlg.deleteLater()


def test_dialog_without_a_point_cannot_be_used(qapp):
    from nightscribe.gui.site_map_dialog import SiteMapDialog
    dlg = SiteMapDialog()
    assert not dlg.ui.btn_map_use.isEnabled()
    assert dlg.chosen() == (None, None)
    dlg.deleteLater()
