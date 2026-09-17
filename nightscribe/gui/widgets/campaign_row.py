############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Campaign row widget (Track UX-PC, U5)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The campaign health card for the Campaigns tab list (Track UX-PC, U5).

A campaign is read at a glance: the name, the health of its cadence as
dots (● up to date / ○ due, over the member count) and its next action in
plain words («measure T CrB tonight ⚡»). Finished campaigns dim. Same
visual language as the project rows (ADR-026 theme).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from .. import theme

_ROW_H = 56       # fixed row height, px (two readable lines)


class CampaignRow(QFrame):
    # One rich row in the campaigns list.
    clicked = Signal()
    context_menu = Signal(object)   # carries the global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("campaignrow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(_ROW_H)
        self._selected = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)
        mid = QVBoxLayout()
        mid.setSpacing(3)
        lay.addLayout(mid, 1)
        # line 1: name + group + (finished)
        line1 = QHBoxLayout()
        line1.setSpacing(6)
        self.lbl_name = QLabel()
        self.lbl_name.setStyleSheet(
            f"font-weight: bold; color: {theme.C_TEXT};")
        line1.addWidget(self.lbl_name, 1)
        self.lbl_group = QLabel()
        self.lbl_group.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        line1.addWidget(self.lbl_group)
        mid.addLayout(line1)
        # line 2: health dots + coverage + next action
        line2 = QHBoxLayout()
        line2.setSpacing(6)
        self.lbl_dots = QLabel()
        line2.addWidget(self.lbl_dots)
        self.lbl_cov = QLabel()
        self.lbl_cov.setStyleSheet(
            f"color: {theme.C_TEXT_DIM}; font-size: 11px;")
        line2.addWidget(self.lbl_cov)
        self.lbl_next = QLabel()
        line2.addWidget(self.lbl_next, 1)
        mid.addLayout(line2)
        self._restyle()

    def set_campaign(self, *, name, group, finished, members, up_to_date,
                     next_text, has_event):
        # @args: members/up_to_date - member count and how many are not
        #        due; next_text - the campaign's next action in words;
        #        has_event - a member's detector event is firing
        # @return: None
        self._finished = finished
        self.lbl_name.setText(name)
        self.lbl_group.setText(group or "")
        dots = ("●" * up_to_date) + ("○" * max(members - up_to_date, 0)) \
            if members else ""
        self.lbl_dots.setText(dots)
        self.lbl_dots.setStyleSheet(
            f"color: {theme.C_GOOD};" if up_to_date == members and members
            else f"color: {theme.C_WARN};")
        self.lbl_cov.setText(
            self.tr("%1 of %2 up to date").replace("%1", str(up_to_date))
            .replace("%2", str(members)) if members else
            self.tr("no projects yet"))
        self.lbl_next.setText(("⚡ " if has_event else "") + next_text)
        self.lbl_next.setStyleSheet(
            f"color: {'#e05555' if has_event else theme.C_TEXT_DIM};")
        self._restyle()

    def set_selected(self, on):
        # @args: on - selected state (the row paints it itself: the item
        #        widget covers the list's own highlight)
        self._selected = bool(on)
        self._restyle()

    def _restyle(self):
        # @return: None — base/hover/selected skin; finished campaigns dim
        #          (disabled-grey labels, still readable, still clickable)
        if self._selected:
            bg, edge = theme.C_SEL, theme.C_ACCENT
        else:
            bg, edge = theme.C_BASE, "transparent"
        self.setStyleSheet(
            f"QFrame#campaignrow {{ background: {bg}; border-radius: 6px;"
            f" border: 1px solid {edge}; }}"
            f"QFrame#campaignrow:hover {{ background: #1a1f30; }}")
        for lbl in (self.lbl_name, self.lbl_group, self.lbl_dots,
                    self.lbl_cov, self.lbl_next):
            lbl.setEnabled(not getattr(self, "_finished", False))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu.emit(event.globalPos())
