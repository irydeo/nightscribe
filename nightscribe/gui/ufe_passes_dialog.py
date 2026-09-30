############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - The passes of a visit module (one night, one curve)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The passes of a visit, in their own window.

A visit can hold several series runs: the observer measures again with
another band, with another sequence, or just to check something, and every
pass keeps its own points (that is what "undo this run" undoes, and the
trail is never silent). But the CHART of the night is ONE of them. Drawing
them all at once is the corruption that was reported on 2026-09-30: a visit
with four passes came back as 976 points at two levels (11.96-12.07 in G
and 12.70-12.81 in V) joined by a zigzag, while the live chart had drawn
one run.

So this window answers the question the observer asked back ("if we keep
the old passes, how do we get them back?"): it lists them, says which one
the chart is showing, and lets any of them be that one without deleting
anything. It owns no logic: the Measure tab holds the data and does the
work; this window only gives it a place where it can be read.
"""

import logging
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QTableWidgetItem

from .ui_loader import adopt_ui

logger = logging.getLogger(__name__)

# The states a pass can be in, in the observer's words (the run's status is
# the engine's: complete | incomplete | undone).
_STATE_TEXT = {
    "complete": "complete",
    "incomplete": "cancelled (its points are the ones measured so far)",
    "undone": "undone (its points are gone)",
}


class UfePassesDialog(QDialog):
    # The passes of the visit the editor is on.
    #
    # @args: parent - the owning window

    use_requested = Signal(object)      # make this pass the curve
    undo_requested = Signal(object)     # undo this pass

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ui = adopt_ui(self, "ufe_passes_dialog")
        self.tbl_passes = self._ui.tbl_passes
        self.lbl_passes_hint = self._ui.lbl_passes_hint
        self.lbl_passes_shown = self._ui.lbl_passes_shown
        self.lbl_passes_trail = self._ui.lbl_passes_trail
        self.btn_passes_use = self._ui.btn_passes_use
        self.btn_passes_undo = self._ui.btn_passes_undo
        self._ui.box_passes.rejected.connect(self.close)
        self.tbl_passes.itemSelectionChanged.connect(self._update_buttons)
        self.btn_passes_use.clicked.connect(self._on_use)
        self.btn_passes_undo.clicked.connect(self._on_undo)
        # the last column stretches: the state says the useful part
        # ("complete · the curve · part of a 3-night pass") and with the
        # columns fitted to their content it fell outside the window
        # (reported: "al abrirlo apenas se ve nada")
        self.tbl_passes.horizontalHeader().setStretchLastSection(True)
        self._runs = []
        self._curve_run_id = None
        self._update_buttons()

    # ------------------------------------------------------- the list

    def show_passes(self, payload):
        # Fills the list and shows the window. Non-modal on purpose: the
        # point of going back to a pass is to LOOK at the chart while
        # choosing, and the chart lives in the window behind this one.
        # @args: payload - {"runs": [{id, created, band, points, mjd0,
        #        mjd1, status}, ...], "curve_run_id": int or None}
        # @return: None
        self.set_passes(payload)
        # a window sized by its CONTENT, with a generous floor: the five
        # columns and the state need room, and a dialog that opens showing
        # three rows and half a column is a dialog nobody reads
        self.resize(max(900, self.sizeHint().width()),
                    max(460, self.sizeHint().height()))
        self.show()
        self.raise_()
        self.activateWindow()

    def set_passes(self, payload):
        # Fills the list WITHOUT showing or raising the window: a change
        # made while it is open (a pass undone, a pass chosen) has to
        # reach it without stealing the focus from the chart the observer
        # is watching.
        # @args: payload - as show_passes
        # @return: None
        data = payload or {}
        self._runs = list(data.get("runs") or [])
        self._curve_run_id = data.get("curve_run_id")
        self._trail = int(data.get("undone_empty") or 0)
        self._fill()

    def _fill(self):
        # @return: None; the table is rebuilt from the payload
        table = self.tbl_passes
        table.setRowCount(len(self._runs))
        current_row = -1
        for row, run in enumerate(self._runs):
            is_curve = run.get("id") == self._curve_run_id
            if is_curve:
                current_row = row
            cells = (self._when(run.get("created")),
                     run.get("band") or self.tr("No filter"),
                     str(run.get("points") or 0),
                     self._span(run),
                     self._state(run, is_curve))
            for col, text in enumerate(cells):
                item = table.item(row, col)
                if item is None:
                    item = QTableWidgetItem()
                    table.setItem(row, col, item)
                item.setText(text)
                # the curve's row is the answer to "which one am I looking
                # at": it is said in bold, not only in the state column
                font = item.font()
                font.setBold(is_curve)
                item.setFont(font)
        table.resizeColumnsToContents()
        if current_row >= 0:
            table.selectRow(current_row)
        self._say_shown()
        self._say_trail()
        self._update_buttons()

    def _when(self, created):
        # @args: created - epoch seconds of the pass
        # @return: the local date and time the pass was measured
        if not created:
            return ""
        try:
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(created))
        except (ValueError, OSError, TypeError):
            return ""

    def _span(self, run):
        # @return: the stretch of night the pass covers, in UTC
        #          ("20:52-21:33"), which is how the chart's axis reads
        mjd0, mjd1 = run.get("mjd0"), run.get("mjd1")
        if mjd0 is None or mjd1 is None:
            return ""
        return "{0}-{1}".format(self._clock(mjd0), self._clock(mjd1))

    def _clock(self, mjd):
        # @return: the civil UTC time of an MJD ("20:52"), the same unit
        #          the chart's own x axis uses
        try:
            from ..core import coords, variables
            dt = coords.datetime_from_jd(float(mjd) + variables.MJD0)
            return dt.strftime("%H:%M")
        except Exception:
            return ""

    def _state(self, run, is_curve):
        # @args: run - the pass, is_curve - whether the chart shows it
        # @return: the state in plain words, with the curve's own tag and,
        #          for a run of a multi-night pass, which pass it belongs
        #          to (that is what "undo this pass" will undo)
        status = (run.get("status") or "complete").lower()
        text = self.tr(_STATE_TEXT.get(status, status))
        if is_curve:
            text += " · " + self.tr("the curve")
        nights = self._pass_nights(run)
        if nights:
            text += " · " + self.tr("part of a {0}-night pass").format(nights)
        return text

    def _pass_nights(self, run):
        # @args: run - a pass row
        # @return: how many nights its pass covers, or 0 (a single night)
        series = (run.get("cfg") or {}).get("series") or {}
        return int((series.get("pass") or {}).get("nights") or 0)

    def _say_shown(self):
        # The line under the table: WHICH pass the chart is showing, in
        # words, so the list cannot be read two ways.
        # @return: None
        run = next((r for r in self._runs
                    if r.get("id") == self._curve_run_id), None)
        if run is None:
            self.lbl_passes_shown.setText(
                self.tr("This visit has no curve right now."))
            return
        self.lbl_passes_shown.setText(self.tr(
            "The chart is showing: the pass of {0} ({1}, {2} points).").format(
                self._when(run.get("created")),
                run.get("band") or self.tr("no filter"),
                run.get("points") or 0))

    # ---------------------------------------------------- the actions

    def _say_trail(self):
        # The passes that are not listed: the ones already undone, which
        # have no points left to draw. They are NOT deleted (the trail of
        # the project keeps every run), so the list says how many there are
        # instead of pretending they never existed. Measured on a real
        # visit: 26 of them, which as rows would have buried the four that
        # matter.
        # @return: None
        if not self._trail:
            self.lbl_passes_trail.setText("")
            return
        self.lbl_passes_trail.setText(self.tr(
            "The project's trail also keeps {0} undone pass(es) with no "
            "points left; they are not listed here and nothing was "
            "deleted.").format(self._trail))

    def selected_run_id(self):
        # @return: the run id of the selected row, or None
        rows = self.tbl_passes.selectionModel().selectedRows() \
            if self.tbl_passes.selectionModel() else []
        if not rows:
            return None
        index = rows[0].row()
        if 0 <= index < len(self._runs):
            return self._runs[index].get("id")
        return None

    def _selected_run(self):
        # @return: the selected pass dict, or None
        run_id = self.selected_run_id()
        return next((r for r in self._runs if r.get("id") == run_id), None)

    def _update_buttons(self):
        # "Make this the curve" is offered when the selection is not the
        # curve already (and has points to draw); "Undo" when it is not
        # undone already. A disabled button that explains nothing is how a
        # door looks broken.
        # @return: None
        run = self._selected_run()
        usable = bool(run) and (run.get("status") or "") != "undone"
        self.btn_passes_use.setEnabled(
            usable and run.get("id") != self._curve_run_id)
        self.btn_passes_undo.setEnabled(usable)

    def _on_use(self):
        # @return: None; the request travels to the tab (which owns the DB)
        run_id = self.selected_run_id()
        if run_id is not None:
            self.use_requested.emit(run_id)

    def _on_undo(self):
        # @return: None
        run_id = self.selected_run_id()
        if run_id is not None:
            self.undo_requested.emit(run_id)

    def keyPressEvent(self, event):
        # Esc closes the window: it is a reference list, not a form to
        # fill, and leaving it open while working is normal.
        # @return: None
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
