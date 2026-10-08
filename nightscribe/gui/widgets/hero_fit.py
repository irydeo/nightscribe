############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - The hero button always fits its panel
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Making a panel's ONE action fit the width the panel really has.

The hero button (ADR-038) is the action of a panel and it is painted big:
16 px type, a 22 px glyph and 16 px of padding each side. Measured on
2026-10-06, the Photometry panel's label ("Construir la secuencia
(comparsas)…") asks for 329 px, and the panel's column can be dragged down
to 280 px (its Designer minimum), where only 262 are left: the text ran
over the button's own edges and the label read half a word. Reported as
"este botón ha de ajustar su ancho al ancho disponible, ahora se sale".

A QPushButton does not wrap and does not elide: it just clips. So the
button is dressed here with the two things that make it behave:

* its width stops being decided by its text (`Ignored` policy + a minimum
  of zero), so a narrow panel narrows the BUTTON instead of growing a
  horizontal scrollbar;
* its label is ELIDED to the room it has, on every resize, and the whole
  label lives in the tooltip, which is the same bargain the project badge
  and the window's status line already make.

Nothing else changes: the text, the hue, the glyph and the slot are the
panel's.
"""

import logging

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QSizePolicy

logger = logging.getLogger("nightscribe.gui.widgets.hero_fit")

# What the stylesheet spends around the label: `padding: 12px 16px` in
# theme.hero_button_style (and hero_cancel_style, the same box), plus the
# glyph and the gap Qt leaves between the icon and the text. The 4 px is
# the border plus a hair, so an elided label never touches the rim.
_PADDING = 2 * 16
_ICON = 22 + 6
_SLACK = 4


class _HeroFitter(QObject):
    """Keeps one hero button's label inside the button."""

    # @args: button - the QPushButton to dress (it owns the fitter)

    def __init__(self, button):
        super().__init__(button)
        self._btn = button
        self._full = button.text()
        self._busy = False
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Ignored,
                             button.sizePolicy().verticalPolicy())
        button.installEventFilter(self)
        self._elide()

    def set_full_text(self, text):
        # @args: text - the label the button really means (the run's Cancel,
        #        a translated label after a language change)
        # @return: None. The caller keeps writing the button's text as
        #          always; this is what is elided and what the tooltip says.
        # The tooltip is only filled when the button carries none: both hero
        # buttons already explain in theirs WHAT the action does (which is
        # worth more than repeating the label), and clobbering that to paste
        # the label back would be a bad trade.
        self._full = str(text)
        if not self._btn.toolTip():
            self._btn.setToolTip(self._full)
        self._elide()

    def eventFilter(self, obj, event):
        # The button changed size (the panel was dragged, the window
        # maximized): what fits is painted again.
        if event.type() == QEvent.Resize:
            self._elide()
        return False

    def _elide(self):
        # @return: None. Only what is PAINTED is shortened; _full keeps the
        #          words and the tooltip keeps them too.
        if self._busy:
            return          # setText can resize us again: no ping-pong
        self._busy = True
        try:
            button = self._btn
            room = (button.width() - _PADDING - _SLACK
                    - (_ICON if not button.icon().isNull() else 0))
            if room <= 20:
                return      # not laid out yet: the next resize will do it
            metrics = QFontMetrics(button.font())
            if metrics.horizontalAdvance(self._full) <= room:
                if button.text() != self._full:
                    button.setText(self._full)
                return
            text = metrics.elidedText(self._full, Qt.ElideRight, room)
            if button.text() != text:
                button.setText(text)
        finally:
            self._busy = False


def install_hero_fit(button):
    # @args: button - the panel's hero QPushButton
    # @return: the fitter (kept on the button as `_hero_fit`, so the caller
    #          can hand it a new full label: see set_full_text)
    # The full label is captured INSIDE the fitter, before it elides
    # anything: reading button.text() again out here would read the already
    # elided text and the button would be stuck with "Build the …" for good
    # (measured 2026-10-06).
    if button is None:
        return None
    fitter = _HeroFitter(button)
    button._hero_fit = fitter
    return fitter


def set_hero_text(button, text):
    # @args: button - a button dressed by install_hero_fit, text - its new
    #        label (the run's Cancel, a new language)
    # @return: None. Safe on a button that was never dressed (it just sets
    #          the text), so no call site needs to know.
    fitter = getattr(button, "_hero_fit", None)
    if fitter is None:
        button.setText(text)
        return
    fitter.set_full_text(text)
