############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Sky bar widget (the night, always in sight)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The night in the navigation row: Moon, darkness, planets and events.

Why here and not in a band inside a view: it is the one piece of
information an observer wants whatever they are doing, and the navigation
row already had the room (its buttons are 28 px tall and a chip is 20).
Living here it is visible from EVERY view, and the projects view gets its
band's height back.

The Moon is drawn at tonight's real phase (gui/moon_icon composes the
bundled photo with the exact terminator), so the bar is not a decoration:
it is the almanac.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class SkyBar(QWidget):
    """Moon + darkness + planets + the sky-event chips."""

    calendar_clicked = Signal()

    # @args: parent - the navigation bar that hosts it
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        # the Moon: a pixmap, not a glyph, so it shows tonight's phase
        self.lbl_moon = QLabel()
        self.lbl_moon.setFixedSize(22, 22)
        self.lbl_moon.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl_moon)
        self.lbl_moon_txt = QLabel()
        self.lbl_moon_txt.setObjectName("skyMoon")
        lay.addWidget(self.lbl_moon_txt)
        self.lbl_when = QLabel()
        self.lbl_when.setObjectName("skyWhen")
        lay.addWidget(self.lbl_when)
        self.lbl_planets = QLabel()
        self.lbl_planets.setObjectName("skyPlanets")
        lay.addWidget(self.lbl_planets)
        # the event chips land here (the host fills them: they come from the
        # sky-calendar engine and carry their own tooltips and clicks)
        self.chips = QHBoxLayout()
        self.chips.setContentsMargins(0, 0, 0, 0)
        self.chips.setSpacing(6)
        lay.addLayout(self.chips)
        self.btn_calendar = QPushButton(self.tr("Sky calendar →"))
        self.btn_calendar.setObjectName("skyCalendar")
        self.btn_calendar.setFlat(True)
        self.btn_calendar.setCursor(Qt.PointingHandCursor)
        self.btn_calendar.setToolTip(self.tr("Everything the sky does in "
                                             "the next weeks"))
        self.btn_calendar.clicked.connect(self.calendar_clicked.emit)
        lay.addWidget(self.btn_calendar)
        self.set_empty()

    # ------------------------------------------------------------- filling

    def refresh(self, brief):
        # @args: brief - a core/night_brief.brief() dict (or None when the
        #        site is not set yet)
        from ...core import night_brief as nb
        if not brief or brief.get("window") is None:
            self.set_empty()
            return
        from ..moon_icon import moon_pixmap
        moon = brief.get("moon") or {}
        pm = moon_pixmap(moon.get("elong", 0.0), 22)
        self.lbl_moon.setPixmap(pm)
        self.lbl_moon.setToolTip(nb.moon_line(brief))
        self.lbl_moon_txt.setText(nb.moon_short(brief))
        dusk, dawn = brief["window"]
        self.lbl_when.setText("%s → %s" % (nb.local_hhmm(dusk),
                                           nb.local_hhmm(dawn)))
        self.lbl_when.setToolTip(nb.window_line(brief))
        planets = nb.planets_short(brief)
        self.lbl_planets.setText(planets)
        self.lbl_planets.setToolTip(nb.planets_line(brief))
        self.lbl_planets.setVisible(bool(planets))
        self.lbl_moon.setVisible(True)
        self.lbl_moon_txt.setVisible(True)
        self.lbl_when.setVisible(True)
        self.setToolTip(self.tr("Tonight from your observatory"))

    def set_empty(self):
        # No site yet: the bar says what it is waiting for instead of
        # showing zeros. The chips stay (they are events, not site data).
        from ...core import night_brief as nb
        self.lbl_moon.setVisible(False)
        self.lbl_moon_txt.setVisible(False)
        self.lbl_when.setText(nb.tr(nb.S_NO_SITE))
        self.lbl_when.setToolTip(self.tr(
            "The Moon, the darkness window and the planets need a site: "
            "set it in Welcome"))
        self.lbl_planets.setVisible(False)

    def clear_chips(self):
        # The chips are rebuilt on every sky refresh; the host owns their
        # content and their clicks.
        while self.chips.count():
            item = self.chips.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
