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

from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    # A header + togglable content area. Clicking the header toggles
    # the content visibility; a small triangle indicates the state.

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

        # content container
        self._content = QFrame()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._btn)
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

    # @return: True while the section's content is shown
    def isExpanded(self):
        return self._expanded
