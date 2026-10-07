############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - collapsible section widget
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from .. import theme


class CollapsibleSection(QFrame):
    # A CARD with a clickable header and a togglable content area: the card
    # paints the surface, the hairline border and the 3 px spine in the
    # object's hue (the same skin the object card's sections use), so an
    # expanded group has a visible beginning AND end (reported: without the
    # border you could not tell where the group stopped). Clicking the header
    # toggles the content; a small triangle indicates the state. A small
    # status chip may ride the header on the right (setHeaderBadge): the
    # project page uses it to mirror the step state (done / skipped /
    # pending) in the accordion header.

    # fired only from _toggle() — i.e. a real user click on the header —
    # with the NEW expanded state. setCollapsed() stays silent on purpose:
    # the step-accordion closing siblings is programmatic and must not
    # fire back (no recursion, no double scroll).
    sectionToggled = Signal(bool)

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._expanded = True
        self._title = title
        self._hue = None
        self._notice = None       # (text, level) while a closed group has news

        # the card: the object card's own section skin (one voice, one home)
        self.setObjectName("sectionCard")
        self.setStyleSheet(theme.block_card_style(None))

        # header button: transparent (the card paints the surface) and the
        # title in the card's accent, like a section title of the object card
        self._btn = QPushButton()
        self._btn.setFlat(True)
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        self._btn.setFont(font)
        self._btn.setStyleSheet(theme.block_header_style(None))
        self._btn.clicked.connect(self._toggle)
        self._update_arrow()

        # status chip on the right — hidden until a caller gives it text
        self._badge = QLabel()
        self._badge.setStyleSheet(theme.chip_style(theme.C_PANEL))
        self._badge.setVisible(False)

        # header row: [toggle button .........] [status chip]
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(self._btn, 1)
        header.addWidget(self._badge)

        # content container, indented so it never touches the card's border
        self._content = QFrame()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 0, 12, 10)
        self._content_layout.setSpacing(6)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(header)
        layout.addWidget(self._content)

        self._set_title(title)

    # @args: title - header text
    def _set_title(self, title):
        self._title = title
        self._update_arrow()

    # @return: None
    def _update_arrow(self):
        arrow = "\u25BC" if self._expanded else "\u25B6"
        self._btn.setText(f"  {arrow}  {self._title}")

    # @return: None
    def _toggle(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._update_arrow()
        # The observer is looking at it now: the notice is CONSUMED. A mark
        # that stays after the group was opened is a mark that lies.
        if self._expanded:
            self.clearNotice()
        self.sectionToggled.emit(self._expanded)

    # ----------------------------------------------------------- notices

    def setNotice(self, text="", level="info"):
        # @args: text - the short news ("3", "new", "⚠"), empty to clear it;
        #        level - "info" (the panel's own accent) | "warn" (the alert
        #        colour, which also paints the title)
        # @return: None. A CLOSED group that holds something marks itself:
        #          the header carries the news in a chip and, when it is a
        #          warning, the title wears the alert colour too (asked for
        #          2026-10-06: "los grupos, por defecto, siempre cerrados...
        #          si hay algún mensaje o notificación en alguno de ellos,
        #          podemos dar un mecanismo de aviso"). Opening the group
        #          consumes it, and while it is open there is nothing to
        #          announce.
        self._notice = (str(text), str(level)) if text else None
        self._apply_notice()

    def clearNotice(self):
        # @return: None. Puts the header back to its plain skin.
        self._notice = None
        self._apply_notice()

    def notice(self):
        # @return: (text, level) while there is one, else None
        return self._notice

    def _apply_notice(self):
        # @return: None. The chip carries the news; the title only changes
        #          colour when the news is a warning (an "info" title would
        #          be the same colour it already has).
        notice = getattr(self, "_notice", None)
        if not notice or self._expanded:
            self._badge.setVisible(False)
            self._badge.setText("")
            self._btn.setStyleSheet(theme.block_header_style(self._hue))
            return
        text, level = notice
        colour = theme.C_WARN if level == "warn" else (self._hue
                                                       or theme.C_ACCENT)
        self._badge.setText(text)
        self._badge.setStyleSheet(theme.chip_style(colour))
        self._badge.setVisible(True)
        self._btn.setStyleSheet(theme.block_header_style(
            theme.C_WARN if level == "warn" else self._hue))

    # @args: widget - the widget to show/hide inside the section
    def setContentWidget(self, widget):
        self._content_layout.addWidget(widget)

    # @return: the inner QLayout of the section (for extra buttons)
    def contentLayout(self):
        return self._content_layout

    # @args: collapsed - True to start collapsed
    def setCollapsed(self, collapsed):
        self._expanded = not collapsed
        self._content.setVisible(self._expanded)
        self._update_arrow()

    # @args: text - the chip label (an empty string hides the chip)
    def setHeaderBadge(self, text):
        self._badge.setText(text)
        self._badge.setVisible(bool(text))

    # @args: hue - the project's kind hue (a theme.KIND_COLORS value), or
    #        None to go back to the app's accent
    # @return: None. OPT-IN on purpose: the card's spine and its title wear
    #          the object's hue (the list grammar: the hue carries the
    #          meaning). Only the panels that speak for a project's object
    #          ask for it, so the project page and the analysis blocks keep
    #          the app's accent.
    def setAccent(self, hue):
        self._hue = hue
        self.setStyleSheet(theme.block_card_style(hue))
        self._btn.setStyleSheet(theme.block_header_style(hue))

    # @return: the current chip label ("" while hidden)
    def headerBadge(self):
        return self._badge.text()

    # @return: True while the section's content is shown
    def isExpanded(self):
        return self._expanded

    # @return: True while the section's content is hidden
    def isCollapsed(self):
        return not self._expanded
