############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Night panel (the projects view at rest)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""What the projects view shows when nothing is selected.

An empty detail pane is a wasted pane. This one answers the question the
observer actually has while deciding what to open: what is the night like?
Same painted sky as the Welcome hero (so tonight's real Moon), the darkness
window, the planets at dusk and the way in to a new project.

The numbers come from core/night_brief, the very same source the navigation
sky bar and Welcome read: the three can never disagree.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..ui_loader import drop_in, load_ui


class NightPanel(QWidget):
    """The sky, tonight, and a way in to a new project."""

    create_project = Signal()
    open_calendar = Signal()

    # @args: parent - the detail pane that hosts it
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = load_ui("night_panel", self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.ui)
        u = self.ui
        u.btn_night_new.clicked.connect(self.create_project.emit)
        u.btn_night_new.setObjectName("nightCta")
        u.btn_night_new.setCursor(Qt.PointingHandCursor)
        # the same painted sky as the Welcome hero, in a shorter box
        from .welcome_sky import WelcomeSky
        self._sky = WelcomeSky()
        self._sky.setMinimumHeight(170)
        drop_in(u.nightSkyHost.parentWidget().layout(), u.nightSkyHost,
                self._sky)
        u.lbl_night_head.setObjectName("nightHead")
        for name in ("lbl_night_when", "lbl_night_moon",
                     "lbl_night_planets"):
            getattr(u, name).setObjectName("nightLine")
        # the invitation is painted ON the sky (ADR-055): it must not eat
        # the clicks meant for what is under it, and it is text, not a
        # control (the call to action is the button below)
        u.nightOverlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # drop_in() replaces the placeholder, and the replacement lands on
        # TOP of its siblings: without this the sky paints over the
        # invitation (the Welcome hero raises its own overlay for the same
        # reason)
        u.nightOverlay.raise_()
        u.lbl_resting_head.setObjectName("restingHead")
        u.lbl_resting_hint.setObjectName("restingHint")
        self.refresh()

    def refresh(self):
        # @return: None. Recomputes from the site; everything here is local
        #          ephemeris, so it can run on every entry into the view.
        from ...config import config
        from ...core import night_brief as nb
        try:
            lat = float(config.get("lat") or 0.0)
            lon = float(config.get("lon") or 0.0)
        except (TypeError, ValueError):
            lat = lon = 0.0
        u = self.ui
        if not (lat or lon):
            u.lbl_night_when.setText(self.tr(
                "Set your observatory and this becomes your sky: the "
                "darkness window, the Moon and the planets."))
            u.lbl_night_moon.setText("")
            u.lbl_night_planets.setText("")
            return
        b = nb.brief(lat, lon)
        u.lbl_night_when.setText(nb.window_line(b))
        u.lbl_night_moon.setText(nb.moon_line(b))
        u.lbl_night_planets.setText(nb.planets_line(b))

    def set_animations(self, on):
        # @args: on - the same motion preference the Welcome hero obeys
        self._sky.set_animations(on)

    def showEvent(self, event):
        # the sky may have aged while another view was on screen
        self._sky.refresh()
        self.refresh()
        super().showEvent(event)
