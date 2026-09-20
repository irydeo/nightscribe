############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Project row widget (Track UX-PC, U2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The rich project row for the hub list (Track UX-PC, U2).

One row answers, at a glance: WHAT it is (kind icon + chip + name), WHAT
IT NEEDS (the next action in plain words + the step dots) and WHEN (the
tonight-visibility chip, the days since the last activity, the sparkline
of your own measurements for follow-up kinds).

The row follows the Tonight vocabulary (ADR-026): one saturated anchor
per row — the kind hue on the icon tile, the chip, the step dots and the
sparkline — and nothing else competes for colour.

The widget is purely presentational: `MainWindow` computes every text and
passes them to `set_project`; row interactions are re-emitted as signals
(click / double-click / context menu) so the QListWidget machinery keeps
working underneath.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from .. import theme

_ROW_H = 74       # fixed row height, px (three readable lines)


class ProjectRow(QFrame):
    # One rich row in the projects hub list.
    clicked = Signal()
    double_clicked = Signal()
    context_menu = Signal(object)   # carries the global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("projectrow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(_ROW_H)
        self._selected = False
        self._kind_color = theme.C_TEXT_DIM
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)
        # left: the kind icon tile — the row's colour anchor (the old thin
        # band felt too quiet against the icon of the same hue)
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(44, 44)
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl_icon)
        mid = QVBoxLayout()
        mid.setContentsMargins(0, 6, 0, 6)
        mid.setSpacing(3)
        lay.addLayout(mid, 1)
        # line 1: kind chip + name + star + campaign
        line1 = QHBoxLayout()
        line1.setSpacing(6)
        self.lbl_kind = QLabel()
        line1.addWidget(self.lbl_kind)
        self.lbl_name = QLabel()
        self.lbl_name.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {theme.C_TEXT};")
        line1.addWidget(self.lbl_name, 1)
        self.lbl_star = QLabel("★")
        self.lbl_star.setStyleSheet(f"color: {theme.C_WARN};")
        self.lbl_star.setVisible(False)
        line1.addWidget(self.lbl_star)
        self.lbl_camp = QLabel()
        self.lbl_camp.setStyleSheet(f"color: {theme.C_GOOD};")
        self.lbl_camp.setVisible(False)
        line1.addWidget(self.lbl_camp)
        mid.addLayout(line1)
        # line 2: step dots + next action in words + activity age
        line2 = QHBoxLayout()
        line2.setSpacing(6)
        self.lbl_progress = QLabel()
        self.lbl_progress.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        line2.addWidget(self.lbl_progress)
        self.lbl_next = QLabel()
        line2.addWidget(self.lbl_next, 1)
        self.lbl_activity = QLabel()
        self.lbl_activity.setStyleSheet(
            f"color: {theme.C_TEXT_DIM}; font-size: 11px;")
        line2.addWidget(self.lbl_activity)
        mid.addLayout(line2)
        # line 3: the tonight-visibility chip (hidden when not up)
        self.lbl_window = QLabel()
        self.lbl_window.setStyleSheet(theme.chip_style(theme.C_OK))
        self.lbl_window.setVisible(False)
        mid.addWidget(self.lbl_window)
        # right: the sparkline of your own measurements (follow-up kinds)
        self.lbl_spark = QLabel()
        self.lbl_spark.setVisible(False)
        self.lbl_spark.setToolTip(self.tr("Your measurements so far"))
        lay.addWidget(self.lbl_spark, 0, Qt.AlignVCenter)
        self._restyle()

    # ---------------- population ----------------

    def set_project(self, *, kind_label, kind_color, name, favorite,
                    campaign_name, progress_text, next_text,
                    activity_text, window_text, sparkline, icon=None):
        # @args: everything already rendered to words by the caller
        #        (kind_label/chips are plain text; sparkline is a QPixmap,
        #        null when there is nothing to draw; icon is the kind's
        #        QPixmap drawn by the caller — None leaves a flat colour wash
        #        that still anchors the hue)
        # @return: None
        self._kind_color = kind_color
        self.lbl_kind.setText(kind_label)
        self.lbl_kind.setStyleSheet(theme.chip_style(kind_color))
        self.lbl_name.setText(name)
        # the icon tile carries the kind hue under the drawn glyph — a
        # solid wash (the tile stands over the list's own item text, so
        # it must stay opaque)
        if icon is not None and not icon.isNull():
            self.lbl_icon.setPixmap(icon)
        self.lbl_icon.setStyleSheet(
            f"background: {theme.composite(kind_color, '38')}; "
            "border-radius: 6px;")
        # the step dots speak in the row's hue like the icon does
        self.lbl_progress.setText(progress_text)
        self.lbl_progress.setStyleSheet(f"color: {kind_color};")
        self.lbl_star.setVisible(bool(favorite))
        self.lbl_camp.setVisible(bool(campaign_name))
        if campaign_name:
            self.lbl_camp.setText("⚑ " + campaign_name)
            self.lbl_camp.setToolTip(
                self.tr("Part of this observing campaign"))
        self.lbl_next.setText(next_text)
        self.lbl_activity.setText(activity_text)
        self.lbl_window.setVisible(bool(window_text))
        if window_text:
            self.lbl_window.setText(window_text)
        has_spark = sparkline is not None and not sparkline.isNull()
        self.lbl_spark.setVisible(has_spark)
        if has_spark:
            self.lbl_spark.setPixmap(sparkline)
        self._restyle()

    # ---------------- selection ----------------

    def set_selected(self, on):
        # The list owns the selection; the row just paints it (the item
        # widget covers the list's own highlight, so we do it ourselves).
        # @args: on - selected state
        self._selected = bool(on)
        self._restyle()

    def _restyle(self):
        # @return: None — base/hover/selected skin in the theme's voice
        if self._selected:
            bg, edge = theme.C_SEL, theme.C_ACCENT
        else:
            bg, edge = theme.C_BASE, "transparent"
        self.setStyleSheet(theme.row_skin("projectrow", bg, edge))

    # ---------------- mouse ----------------

    def mousePressEvent(self, event):
        # A click anywhere on the row selects the underlying item.
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        # Double-click = open at the current step (same gesture language
        # as every other list, UB).
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        # The item widget swallows the list's own context menu events, so
        # the row forwards them itself (one gesture language).
        self.context_menu.emit(event.globalPos())
