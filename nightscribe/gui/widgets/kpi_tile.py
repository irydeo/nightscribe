############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - KPI tile widget module (object card, ADR-057)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# One KPI tile of the object card's "tonight" strip: a big value over a
# small caption. The strip replaces the old capture-chips row: the same
# numbers, but with a hierarchy the eye can scan (value first, meaning
# under it) instead of a row of look-alike pills.

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

from .. import theme


class KpiTile(QFrame):
    # A value/caption card. The accent paints the value and the spine;
    # neutral tiles (no accent) keep the plain text colour.

    def __init__(self, value, caption, accent=None, tip="", parent=None):
        # @args: value - the big text ("19.5", "21:00–23:30", "×4.2"),
        #        caption - the small meaning under it ("Mag", "Window"),
        #        accent - hue for value + spine, or None for neutral,
        #        tip - the tooltip (the long explanation), parent - widget
        super().__init__(parent)
        self.setObjectName("kpiTile")
        self.setStyleSheet(theme.kpi_tile_style(accent))
        # a tile hugs its content; the strip's stretch absorbs the slack
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMinimumWidth(96)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(1)

        self.lbl_value = QLabel(value)
        font = QFont(self.font())
        font.setPixelSize(16)
        font.setBold(True)
        self.lbl_value.setFont(font)
        self.lbl_value.setStyleSheet(
            f"color: {accent or theme.C_TEXT};")
        lay.addWidget(self.lbl_value)

        self.lbl_caption = QLabel(caption)
        cap = QFont(self.font())
        cap.setPixelSize(10)
        # letter-spaced small caps read as a label, not as a sentence
        cap.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        self.lbl_caption.setFont(cap)
        self.lbl_caption.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        lay.addWidget(self.lbl_caption)

        if tip:
            # the tooltip lives on the frame AND the labels: the labels
            # cover most of the tile's surface, and a tip that only fires
            # on the 6 px margin is a tip nobody finds
            for w in (self, self.lbl_value, self.lbl_caption):
                w.setToolTip(tip)

    def texts(self):
        # @return: (value, caption) — the test-facing readout
        return self.lbl_value.text(), self.lbl_caption.text()

    def set_value(self, value):
        # Live update of the big number (the plan strip recomputes on every
        # spin change): a tile that cannot be updated would force a rebuild.
        # @args: value - the new value text
        self.lbl_value.setText(value)

    def set_caption(self, caption):
        # @args: caption - the new caption text
        self.lbl_caption.setText(caption)

    def set_accent(self, accent):
        # Repaints the tile in another hue (the verdict flips green/amber):
        # the spine and the value colour move together, as they do at birth.
        # @args: accent - a hex hue, or None for the neutral text colour
        self.setStyleSheet(theme.kpi_tile_style(accent))
        self.lbl_value.setStyleSheet(f"color: {accent or theme.C_TEXT};")
