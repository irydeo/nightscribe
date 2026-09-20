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
plain words («measure T CrB tonight ⚡»).

The row's identity IS its cadence health, exactly like a project row's
identity is its kind (ADR-026, one saturated anchor per row): the left
band, the dots and the action all speak in that hue — green when the
cadence is kept, orange when observations are due, red when a detector
event is firing. Finished campaigns dim to grey; same visual language as
the project rows.
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
        self._finished = False
        self._has_event = False
        self._members = 0
        self._up_to_date = 0
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 10, 6)
        lay.setSpacing(8)
        # left: the health band — up to date / due / event / finished
        self._band = QFrame()
        self._band.setFixedWidth(4)
        lay.addWidget(self._band)
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

    def _health_color(self):
        # @return: the campaign's identity hue — the cadence state: red
        #          beats orange, orange beats green, and a finished or
        #          still-empty campaign rests in calm grey.
        if getattr(self, "_finished", False) \
                or not getattr(self, "_members", 0):
            return theme.C_TEXT_DIM
        if getattr(self, "_has_event", False):
            return theme.C_EVENT
        if getattr(self, "_up_to_date", 0) < self._members:
            return theme.C_WARN
        return theme.C_GOOD

    @staticmethod
    def _dots_html(up_to_date, members):
        # @args: how many members are up to date, over the total
        # @return: one coloured dot per member (● green up to date,
        #          ○ orange due); empty string when there are no members
        if not members:
            return ""
        spans = []
        for i in range(members):
            if i < up_to_date:
                ch, col = "●", theme.C_GOOD
            else:
                ch, col = "○", theme.C_WARN
            spans.append(f'<span style="color: {col}; font-size: 13px;">'
                         f"{ch}</span>")
        return "".join(spans)

    def set_campaign(self, *, name, group, finished, members, up_to_date,
                     next_text, has_event):
        # @args: members/up_to_date - member count and how many are not
        #        due; next_text - the campaign's next action in words;
        #        has_event - a member's detector event is firing
        # @return: None
        self._finished = bool(finished)
        self._has_event = bool(has_event)
        self._members = int(members or 0)
        self._up_to_date = int(up_to_date or 0)
        self.lbl_name.setText(name)
        self.lbl_group.setText(group or "")
        self.lbl_dots.setText(self._dots_html(self._up_to_date,
                                              self._members))
        self.lbl_cov.setText(
            self.tr("%1 of %2 up to date").replace("%1", str(up_to_date))
            .replace("%2", str(members)) if self._members else
            self.tr("no projects yet"))
        self.lbl_next.setText(("⚡ " if self._has_event else "") + next_text)
        # the action speaks in the campaign's health: red when an event
        # is firing, orange when observations are due, calm otherwise
        if self._has_event:
            nxt = f"color: {theme.C_EVENT}; font-weight: bold;"
        elif self._members and self._up_to_date < self._members:
            nxt = f"color: {theme.C_WARN}; font-weight: bold;"
        else:
            nxt = f"color: {theme.C_TEXT_DIM};"
        self.lbl_next.setStyleSheet(nxt)
        self._restyle()

    def set_selected(self, on):
        # @args: on - selected state (the row paints it itself: the item
        #        widget covers the list's own highlight)
        self._selected = bool(on)
        self._restyle()

    def _restyle(self):
        # @return: None — base/hover/selected skin; finished campaigns dim
        #          (disabled-grey labels, still readable, still clickable);
        #          a row with a firing event gets a faint red wash
        if self._selected:
            bg, edge = theme.C_SEL, theme.C_ACCENT
        elif not self._finished and self._has_event:
            # the red wash baked over a solid base — the card must stay
            # opaque, or the list's own item text ghosts through
            bg, edge = theme.composite(theme.C_EVENT, "20"), "transparent"
        else:
            bg, edge = theme.C_BASE, "transparent"
        self.setStyleSheet(theme.row_skin("campaignrow", bg, edge))
        self._band.setStyleSheet(
            f"background: {self._health_color()}; border-radius: 2px;")
        for lbl in (self.lbl_name, self.lbl_group, self.lbl_dots,
                    self.lbl_cov, self.lbl_next):
            lbl.setEnabled(not self._finished)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        self.context_menu.emit(event.globalPos())
