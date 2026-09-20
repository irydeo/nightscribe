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
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from .. import theme


class CollapsibleSection(QWidget):
    # A header + togglable content area. Clicking the header toggles
    # the content visibility; a small triangle indicates the state.
    # A small status chip may ride the header on the right
    # (setHeaderBadge): the project page uses it to mirror the step
    # state (done / skipped / pending) in the accordion header.

    # fired only from _toggle() — i.e. a real user click on the header —
    # with the NEW expanded state. setCollapsed() stays silent on purpose:
    # the step-accordion closing siblings is programmatic and must not
    # fire back (no recursion, no double scroll).
    sectionToggled = Signal(bool)

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._expanded = True
        self._title = title

        # header button
        self._btn = QPushButton()
        self._btn.setFlat(True)
        self._btn.setStyleSheet(
            "QPushButton { border: none; text-align: left; "
            "font-weight: bold; padding: 4px; }")
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

        # content container
        self._content = QFrame()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)

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
        self.sectionToggled.emit(self._expanded)

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

    # @return: the current chip label ("" while hidden)
    def headerBadge(self):
        return self._badge.text()

    # @return: True while the section's content is shown
    def isExpanded(self):
        return self._expanded

    # @return: True while the section's content is hidden
    def isCollapsed(self):
        return not self._expanded
