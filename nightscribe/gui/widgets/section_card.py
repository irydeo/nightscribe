############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Parameter section card widget module (object card, ADR-057)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# One themed section of the object card's parameters ("Orbit", "The
# planet", "The pulsation"...): a titled card with definition-list rows,
# name + value, and the "what it means" sentence under them, dim and
# wrapped.
#
# This replaces the single QTableWidget the card used before ADR-057.
# The table needed ~90 lines of manual row-fitting because Qt does not
# auto-size a wrapped cell that SPANS columns (the explanation row); a
# label-based definition list wraps and sizes itself, so the whole
# fitting machinery (and its resize-event hooks) is simply gone.

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout

from .. import theme


class PanelCard(QFrame):
    # The generic sibling of SectionCard: a titled card whose body holds
    # ARBITRARY content (forms, button rows, custom widgets), not only
    # definition-list rows. Capture groups its control blocks in these
    # (ADR-059) so the page reads as cards instead of a wall of QGroupBox
    # chrome; the skin is the same, so the dossier and the console share
    # one voice.

    def __init__(self, title, accent, parent=None):
        # @args: title - the card's translated title, accent - the project
        #        kind hue (spine + title), parent - widget
        super().__init__(parent)
        self.setObjectName("sectionCard")
        self.setStyleSheet(theme.section_card_style(accent))
        self._accent = accent

        lay = QVBoxLayout(self)
        # Capture must stay scroll-free at 1360x860 with CCDciel connected
        # (the Interfaz 1.8 contract): a 6/6/4 rhythm is what fits four
        # cards plus the summary strip in that viewport (measured).
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(4)

        self.lbl_title = QLabel(title)
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        self.lbl_title.setFont(font)
        self.lbl_title.setStyleSheet(f"color: {accent};")
        lay.addWidget(self.lbl_title)

        # the caller adds its widgets/layouts here
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 2, 0, 0)
        self.body.setSpacing(5)
        lay.addLayout(self.body)


class SectionCard(QFrame):
    # A titled card holding one group of parameter rows.

    def __init__(self, title, accent, parent=None):
        # @args: title - the section's translated title, accent - the
        #        object's kind hue (spine + title), parent - widget
        super().__init__(parent)
        self.setObjectName("sectionCard")
        self.setStyleSheet(theme.section_card_style(accent))
        self._accent = accent
        self.rows_text = []      # (param, value, explanation), for tests

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 10)
        lay.setSpacing(4)

        self.lbl_title = QLabel(title)
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        self.lbl_title.setFont(font)
        self.lbl_title.setStyleSheet(f"color: {accent};")
        lay.addWidget(self.lbl_title)

        # param | value, with the explanation spanning both under them;
        # the value column takes the slack so long values never starve it
        self._grid = QGridLayout()
        self._grid.setContentsMargins(0, 2, 0, 0)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(2)
        self._grid.setColumnStretch(0, 0)
        self._grid.setColumnStretch(1, 1)
        lay.addLayout(self._grid)

    def add_row(self, param, value, explanation):
        # @args: param - the parameter name, value - its value,
        #        explanation - the "what it means" sentence (may be "")
        # @return: None
        row = self._grid.rowCount()
        lbl_param = QLabel(param)
        lbl_param.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        # Both wrap. A QGridLayout's minimum width is the SUM of its
        # columns' minimums, and an unwrapped label's minimum is its whole
        # text: one long name ("MOID (minimo acercamiento de orbitas)") next
        # to one long value pushed the card's floor to 448 px, which is what
        # kept the parameters/charts row from being the 50/50 it is meant to
        # be (ADR-057 rev.). Wrapping drops the floor to the longest word.
        lbl_param.setWordWrap(True)
        lbl_value = QLabel(str(value))
        lbl_value.setWordWrap(True)
        lbl_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # a definition list reads top-aligned: a tall explanation must not
        # push the next name/value pair off its own baseline
        self._grid.addWidget(lbl_param, row, 0, Qt.AlignTop)
        self._grid.addWidget(lbl_value, row, 1, Qt.AlignTop)
        if explanation:
            lbl_exp = QLabel(explanation)
            lbl_exp.setWordWrap(True)
            font = QFont(self.font())
            font.setPixelSize(11)
            lbl_exp.setFont(font)
            lbl_exp.setStyleSheet(f"color: {theme.C_TEXT_DIM};"
                                  f" margin-bottom: 4px;")
            self._grid.addWidget(lbl_exp, row + 1, 0, 1, 2)
        self.rows_text.append((param, str(value), explanation))

    def row_count(self):
        # @return: how many parameter rows the card shows
        return len(self.rows_text)
