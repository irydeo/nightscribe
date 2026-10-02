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

# Fixed row height, px (two readable lines). It was 74 with three lines,
# which put six projects in 400 px and left most of every row empty; the
# window chip moved up to line 2, so the row is shorter AND says more.
ROW_HEIGHT = 54

# The tile carries the kind hue; 34 px is enough to read the glyph without
# eating a tenth of a 360 px list.
_TILE = 34

# Below these widths the row drops its least important parts instead of
# squeezing them into an ellipsis. The list's width is the observer's to
# choose (the splitter), so the row has to live with both 300 and 600 px.
#
# The curve thumbnail rides on the FIRST line, next to the name: with it in
# its own right-hand column it stole 106 px from the second line, which is
# where the object's numbers live (measured: the numbers need ~110-165 px
# and the line only has ~318). On line 1 the two stop competing, and the
# curve is still the first thing the eye catches after the name.
_W_SPARK = 360        # the curve thumbnail fits
_W_CAMP = 560         # the campaign badge fits

# The thumbnail's size: 20 px tall so it sits on a text line without
# growing the row, and a touch narrower than the standalone default
# (110x26) to leave the name its room.
SPARK_W = 96
SPARK_H = 20

# What the row spends before the middle block starts (margins + icon tile +
# the gap after it) and after it ends (right margin). Used to work out how
# much room a line really has.
_CHROME = 8 + _TILE + 10 + 8
_GAP = 6              # the spacing between items of a line


class ProjectRow(QFrame):
    # One rich row in the projects hub list.
    clicked = Signal()
    double_clicked = Signal()
    context_menu = Signal(object)   # carries the global position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("projectrow")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(ROW_HEIGHT)
        self._selected = False
        self._kind_color = theme.C_TEXT_DIM
        self._detail_text = ""
        self._camp_name = ""
        self._window_text = ""
        self._has_spark = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lay.setSpacing(10)
        # left: the kind icon tile — the row's colour anchor (the old thin
        # band felt too quiet against the icon of the same hue)
        self.lbl_icon = QLabel()
        self.lbl_icon.setFixedSize(_TILE, _TILE)
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.lbl_icon)
        mid = QVBoxLayout()
        mid.setContentsMargins(0, 5, 0, 5)
        mid.setSpacing(2)
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
        # the curve of your own measurements: on this line, right after the
        # name, so the second line keeps the room for the object's numbers
        self.lbl_spark = QLabel()
        self.lbl_spark.setVisible(False)
        self.lbl_spark.setToolTip(self.tr("Your measurements so far"))
        line1.addWidget(self.lbl_spark, 0, Qt.AlignVCenter)
        self.lbl_star = QLabel("★")
        self.lbl_star.setStyleSheet(f"color: {theme.C_WARN};")
        self.lbl_star.setVisible(False)
        line1.addWidget(self.lbl_star)
        self.lbl_camp = QLabel()
        self.lbl_camp.setStyleSheet(f"color: {theme.C_GOOD};")
        self.lbl_camp.setVisible(False)
        line1.addWidget(self.lbl_camp)
        mid.addLayout(line1)
        # line 2: step dots + next action + what the object IS + the
        # tonight-visibility chip + the age. One line, filled left to right
        # by importance: what to do, what it is, whether it is up tonight.
        line2 = QHBoxLayout()
        line2.setSpacing(6)
        self.lbl_progress = QLabel()
        self.lbl_progress.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        line2.addWidget(self.lbl_progress)
        self.lbl_next = QLabel()
        line2.addWidget(self.lbl_next)
        # the context numbers (mag, rate, period...): the row's reason to
        # exist once you know the name
        self.lbl_detail = QLabel()
        self.lbl_detail.setStyleSheet(
            f"color: {theme.C_TEXT_DIM}; font-size: 11px;")
        self.lbl_detail.setVisible(False)
        line2.addWidget(self.lbl_detail)
        # the tonight-visibility chip (hidden when not up)
        self.lbl_window = QLabel()
        self.lbl_window.setStyleSheet(theme.chip_style(theme.C_OK))
        self.lbl_window.setVisible(False)
        line2.addWidget(self.lbl_window)
        line2.addStretch(1)
        self.lbl_activity = QLabel()
        self.lbl_activity.setStyleSheet(
            f"color: {theme.C_TEXT_DIM}; font-size: 11px;")
        line2.addWidget(self.lbl_activity)
        mid.addLayout(line2)
        self._restyle()

    # ---------------- population ----------------

    def set_project(self, *, kind_label, kind_color, name, favorite,
                    campaign_name, progress_text, next_text,
                    activity_text, window_text, sparkline, icon=None,
                    sparkline_text=None, detail_text=""):
        # @args: everything already rendered to words by the caller
        #        (kind_label/chips are plain text; sparkline is a QPixmap,
        #        null when there is nothing to draw; icon is the kind's
        #        QPixmap drawn by the caller — None leaves a flat colour wash
        #        that still anchors the hue; sparkline_text is the
        #        thumbnail's tooltip: what the curve is, in words)
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
        if window_text:
            self.lbl_window.setText(window_text)
        has_spark = sparkline is not None and not sparkline.isNull()
        if has_spark:
            self.lbl_spark.setPixmap(sparkline)
            # the thumbnail says WHAT it is: a curve of a project without a
            # tooltip is a squiggle
            self.lbl_spark.setToolTip(
                sparkline_text or self.tr("Your measurements so far"))
        # What is shown is decided by the WIDTH, not here: the list is as
        # wide as the observer drags it (the splitter), so the row keeps
        # its full text and reveals it as there is room.
        self._detail_text = detail_text or ""
        self.lbl_detail.setText(self._detail_text)
        self._camp_name = campaign_name or ""
        self._window_text = window_text or ""
        self._has_spark = has_spark
        self._apply_width_policy()
        self._restyle()

    def _apply_width_policy(self):
        # @return: None. A narrow list must still be readable, so the row
        #          shows what fits, in order of importance. The essentials
        #          (name, next action, kind, age) never go.
        w = self.width()
        self.lbl_spark.setVisible(self._has_spark and w >= _W_SPARK)
        self.lbl_camp.setVisible(bool(self._camp_name) and w >= _W_CAMP)
        self.lbl_window.setVisible(bool(self._window_text))
        self.lbl_detail.setVisible(self._detail_fits(w))
        self._sync_tooltip(self.lbl_detail.isVisible())

    def _detail_fits(self, width):
        # @args: width - the row's width in px
        # @return: True when the object's numbers fit on line 2 next to
        #          everything else. MEASURED with the real font instead of
        #          guessed with a fixed threshold: a guessed one is how the
        #          numbers ended up clipped mid-word, which reads as a bug.
        #          A project with no numbers says so by returning False,
        #          and a line that is too tight hides them (they are still
        #          one hover away, in the tooltip).
        if not self._detail_text:
            return False
        room = width - _CHROME
        used = (self.lbl_progress.sizeHint().width()
                + self.lbl_next.sizeHint().width()
                + self.lbl_activity.sizeHint().width())
        gaps = 3 * _GAP                       # dots|next|numbers|age
        if self._window_text:
            used += self.lbl_window.sizeHint().width()
            gaps += _GAP
        return self.lbl_detail.sizeHint().width() <= room - used - gaps

    def _sync_tooltip(self, detail_shown):
        # @args: detail_shown - whether the numbers are on screen
        # @return: None. When they are not, the row carries them in its
        #          tooltip: hiding information is fine, losing it is not.
        if detail_shown or not self._detail_text:
            self.setToolTip("")
        else:
            self.setToolTip(self._detail_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_width_policy()

    # ---------------- selection ----------------

    def set_selected(self, on):
        # The list owns the selection; the row just paints it (the item
        # widget covers the list's own highlight, so we do it ourselves).
        # @args: on - selected state
        self._selected = bool(on)
        self._restyle()

    def _restyle(self):
        # @return: None: base/hover/selected skin in the theme's voice.
        #   The selected row is tinted in its OWN kind hue, not in the
        #   global blue: with six projects on screen the old blue bar said
        #   "something here" while the hue says WHICH one, and it is the
        #   same vocabulary the Welcome cards use.
        if self._selected:
            bg = theme.composite(self._kind_color, "2e", over=theme.C_BASE)
            edge = self._kind_color
            spine = self._kind_color
        else:
            bg, edge = theme.C_BASE, "transparent"
            spine = theme.composite(self._kind_color, "80", over=theme.C_BASE)
        self.setStyleSheet(theme.row_skin("projectrow", bg, edge,
                                          spine=spine))

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
