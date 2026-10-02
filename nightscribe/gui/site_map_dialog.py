############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Site picker dialog (Interfaz 1.5)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The map, as a dialog, for the places that cannot afford to embed it.

Settings is already a dense page of groups, so the Observatory group offers
a button that opens this window instead. The map itself is the very same
gui/widgets/site_map.py the Welcome step uses: one widget, one behaviour,
one place to fix.
"""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QDialog

from .ui_loader import adopt_ui, drop_in


class SiteMapDialog(QDialog):
    """Pick a point on the map and hand it back."""

    # @args: lat, lon - the starting point (0, 0 means "nothing yet");
    #        name - printed next to the marker; parent - the owner
    def __init__(self, lat=0.0, lon=0.0, name="", parent=None):
        super().__init__(parent)
        # adopt_ui: the .ui's own layout takes over this dialog and the
        # husk is hidden (ADR-005), so there is no nested widget to lay out
        self.ui = adopt_ui(self, "site_map_dialog")
        u = self.ui
        # Title and size live HERE, not in the .ui: adopt_ui only moves the
        # layout, so a windowTitle on the root would never arrive. Without
        # this the dialog opened at its sizeHint (332x440, a 300x150 map),
        # which is not enough to aim at anything.
        self.setWindowTitle(self.tr("Pick your observatory on the map"))
        self.setMinimumSize(760, 480)
        self.resize(self._default_size())

        from .widgets.site_map import SiteMap
        self._map = SiteMap()
        self._map.picked.connect(self._picked)
        drop_in(u.mapHost.parentWidget().layout(), u.mapHost, self._map)
        if lat or lon:
            self._map.set_site(lat, lon, name)
            self._show(lat, lon)

        # The map takes every spare pixel: the labels above and below it
        # keep their natural height instead of floating in the middle of a
        # half-empty dialog (the .ui's verstretch alone was not enough).
        self.layout().setStretch(2, 1)

        u.btn_map_cancel.clicked.connect(self.reject)
        u.btn_map_use.clicked.connect(self.accept)

    def _default_size(self):
        # @return: a QSize for the first show. The map IS the dialog, so it
        #          gets most of the screen instead of the cramped sizeHint
        #          Qt would pick; 72% of the available area, with a floor so
        #          it is usable on a small screen and a ceiling so it does
        #          not become a wall on a huge one. Around 1200 px wide the
        #          map area lands near 2:1, which is the world's own ratio:
        #          there the whole planet fits AND there are no side bands.
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QSize(1100, 700)
        avail = screen.availableGeometry()
        return QSize(max(820, min(1280, int(avail.width() * 0.72))),
                     max(520, min(820, int(avail.height() * 0.72))))

    def _picked(self, lat, lon):
        # @args: lat, lon - the point just clicked
        self._show(lat, lon)

    def _show(self, lat, lon):
        # The chosen point in plain words, and the "use it" button only
        # once there is something to use: an enabled button that would copy
        # nothing is a trap.
        self.ui.lbl_map_pick.setText(
            self.tr("Point chosen: {lat:.5f}, {lon:.5f}").format(
                lat=lat, lon=lon))
        self.ui.btn_map_use.setEnabled(True)

    def chosen(self):
        # @return: (lat, lon) of the point the observer accepted
        return self._map.site()
