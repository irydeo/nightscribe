############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Track & Stack tab module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Track & Stack tab (astrometry plan, phase 7): the visit's sequence
becomes MPC observations. The structure, texts and tooltips live in
ui/ufe_trackstack_tab.ui (ADR-005); this module wires the signals, fills
the tables and runs the pipeline through gui/workers.TrackStackWorker.

The flow, top to bottom: how many observations the user wants (with the
expected SNR per group recalculated on every change, D22), the stacking
run with progress and Cancel, the group's stack in this tab's OWN viewer
(the dialog's plate is never touched), the measurement with its two ways
and the disagreement flag (D7/D16), the Find_Orb check with its verdict
(D25/D29) and the report that lands in the visit's MPC block, where the
ADR-022 validator has the last word.
"""

import logging
import math
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QScrollArea, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..config import config
from .ufe_state import UfeImageState
from .ufe_host import host_of
from .ui_loader import adopt_ui, drop_in
from .widgets.ufe_image_view import UfeImageView, cross_marker_items
from .widgets.stack_strip import StackStrip
from .widgets.collapsible_section import CollapsibleSection

logger = logging.getLogger("nightscribe.gui.ufe_trackstack_tab")


class UfeTrackStackTab(QWidget):
    # @args: state - the shared UfeImageState (the group's stack is loaded
    #        into it, so the histogram, stretch and marks work on it),
    #        lang - "es" | "en", view - the shared UfeImageView (the
    #        measured position is marked on it; None builds a private
    #        fallback, which is what the tests use), parent - widget

    def __init__(self, state, lang="es", view=None, parent=None):
        super().__init__(parent)
        self._state = state
        self._lang = lang
        self._view = view
        self._worker = None        # TrackStackWorker while it runs
        self._frames = None        # list[Frame] of the open visit
                                   # (headers only: no pixels live here)
        self._ctx_paths = None     # the paths _frames was loaded from
        self._base_snr = None      # SNR of the whole-sequence stack (the
                                   # first run turns the expected-SNR
                                   # column into a real projection, D22)
        self._result = None        # the last run's payload
        self._run_id = None        # its row in astrometry_runs (the Undo)
        self._build_ui()
        self._sync_context()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # The structure is the Designer file's (ADR-005); this method
        # aliases the widgets, fills the combos (labels through literal
        # tr() so lupdate sees them) and wires every signal.
        self._ui = adopt_ui(self, "ufe_trackstack_tab")
        self.lbl_object = self._ui.lbl_object
        self.spn_nobs = self._ui.spn_nobs
        self.tbl_snr = self._ui.tbl_snr
        self.cmb_method = self._ui.cmb_method
        self.btn_stack = self._ui.btn_stack
        self.prg_stack = self._ui.prg_stack
        self.lbl_status = self._ui.lbl_status
        self.txt_notes = self._ui.txt_notes
        self.cmb_group = self._ui.cmb_group
        self.tbl_points = self._ui.tbl_points
        # The headers are short because the column is 380 px wide: the long
        # name travels in the tooltip, where there is room for it.
        for col, tip in enumerate((
                self.tr("Which observation"),
                self.tr("Middle-of-exposure instant (UT)"),
                self.tr("Right ascension, from the stack's own centroid"),
                self.tr("Declination, from the stack's own centroid"),
                self.tr("Separation between the two measurements (″)"),
                self.tr("Signal-to-noise of the measured point"),
                self.tr("Calibrated magnitude"),
                self.tr("Warnings and flags of the point"))):
            header = self.tbl_points.horizontalHeaderItem(col)
            if header is not None:
                header.setToolTip(tip)
        self.txt_check = self._ui.txt_check
        self.chk_force = self._ui.chk_force
        self.cmb_format = self._ui.cmb_format
        self.btn_report = self._ui.btn_report
        self.btn_send_mpc = self._ui.btn_send_mpc
        self.btn_undo = self._ui.btn_undo
        self.txt_report = self._ui.txt_report
        # The group's stack is shown in the MAIN stage (the shared state),
        # so the histogram, the stretch and the marks work on it and the
        # other tabs can operate on top. The private viewer is only a
        # fallback for a host that gave no view (the tests).
        if self._view is None:
            self._stack_state = UfeImageState(self)
            self._stack_view = UfeImageView(self._stack_state)
            drop_in(self.layout(), self._ui.ph_stack_view, self._stack_view)
        else:
            self._stack_state = None
            self._stack_view = None
            placeholder = getattr(self._ui, "ph_stack_view", None)
            if placeholder is not None:
                placeholder.hide()
        # the strip of observation stacks: the same evidence the combo
        # lists, but visible and comparable at a glance, all at ONE
        # stretch (auto-stretching each panel would fake a faint one)
        self._thumbs = StackStrip()
        drop_in(self.layout(), self._ui.ph_thumbs, self._thumbs)
        self._thumbs.picked.connect(self._show_group)
        # the result area (the strip, the points table) starts HIDDEN: an
        # empty grid and a blank strip say nothing, and in a 380 px column
        # they are noise. It appears with the result and goes with it.
        self.lbl_points_title = self._ui.lbl_points_title
        self._thumbs.setVisible(False)
        self.btn_blink = self._ui.btn_blink
        self.btn_blink.clicked.connect(self._on_blink)
        # the brightness is measured with the recipe the Fotometria tab is
        # holding: one editor in the app, read live, shown before the run
        self.chk_brightness = self._ui.chk_brightness
        self.chk_starstack = self._ui.chk_starstack
        # ADR-061 where the faint object is: calibrating the frames is
        # OPTIONAL and off by default, because it costs a pass over the
        # visit and because the observer may already have calibrated
        # copies. Its default is the setting, so the choice survives
        self.chk_calibrate = self._ui.chk_calibrate
        self.chk_calibrate.setChecked(bool(config.get("calib_astrometry",
                                                      False)))
        self.lbl_recipe = self._ui.lbl_recipe
        self.btn_recipe = self._ui.btn_recipe
        self.btn_recipe.clicked.connect(self._on_edit_recipe)
        self.chk_brightness.toggled.connect(lambda _on: self._sync_recipe_row())
        self._sync_recipe_row()
        # ADR-038: three levels of prominence. The nightly flow stays in
        # the column (the object, the plan, the run, the result and the
        # report); the knobs most observers never touch go into collapsible
        # blocks whose titles say what they hold, and the occasional
        # ACTIONS go behind ⋯. The widgets keep their names, their tooltips
        # and their slots: only their container changes.
        self.btn_more = self._ui.btn_more
        self.lbl_snr_line = self._ui.lbl_snr_line
        self._sections = {
            # The SNR table is NOT a fold: it is the plan's own detail (the
            # frames and the T_mid of each observation) and it is read
            # BEFORE the run, to decide how many observations to ask for.
            # It was the only fold hiding something used before running.
            "advanced": self._wrap_section(
                "sec_advanced_content", self.tr("Stacking settings"),
                # a FRESH key on purpose: the block is open by default now
                # (the method, the field, the margin, the brightness and the
                # recipe are the planning decisions), and an old stored
                # "closed" from the previous design would keep it shut
                "trackstack_settings_open", open_by_default=True),
            "check": self._wrap_section(
                "sec_check_content",
                self.tr("Check against other observers"),
                "trackstack_check_open"),
            "report": self._wrap_section(
                "sec_report_content", self.tr("Report text"),
                "trackstack_report_open"),
        }
        self._check_section = self._sections["check"]
        from .widgets.door_menu import build_door
        build_door(self.btn_more, [self.btn_blink, self.btn_undo])
        # before a run this column is the PLAN: the result arrives whole or
        # not at all, and a check with no run is a paragraph about nothing
        self._show_result_area(False)
        self._make_scrollable()

    def _make_scrollable(self):
        # The column is taller than the panel on a laptop, and a label that
        # cannot be read is a label that does not exist: the content goes
        # into a scroll area, the way the Photometry tab's forms already do.
        # Every item moves into an inner widget (a layout does NOT drop its
        # item by itself, so they are taken out one by one) and the scroll
        # area takes the tab's only slot.
        inner = QWidget(self)
        box = QVBoxLayout(inner)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        lay = self.layout()
        while lay.count():
            item = lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                box.addWidget(widget)      # reparents it into the inner
                continue
            nested = item.layout()
            if nested is not None:
                # A ROW: addLayout (NOT addItem) is what reparents its
                # widgets into the inner widget. addItem moves the layout
                # alone and leaves the widgets as children of the tab,
                # where the scroll area's viewport paints OVER them: the
                # row went missing and the column looked empty exactly
                # where it should have been.
                box.addLayout(nested)
                continue
            # A SPACER: the trailing one collects the extra space at the
            # bottom. Dropping it handed that space to whatever could
            # grow, and the observations row came out 141 px tall in a
            # tall window, pushing the Stack button out of sight.
            box.addItem(item)
        area = QScrollArea(self)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(inner)
        lay.addWidget(area)
        # the combination methods of core/track_stack (D11), with the
        # setting's default on top
        self.cmb_method.addItem(self.tr("Sum"), "sum")
        self.cmb_method.addItem(self.tr("Mean"), "mean")
        self.cmb_method.addItem(self.tr("Median"), "median")
        self.cmb_method.addItem(self.tr("Sigma-clipped"), "sigma")
        # P1: the same clip, and then each frame counts by 1/sigma^2 of its
        # own sky. On a stable night it is the same as the sigma clip; on a
        # night with thin cloud or moon it is what keeps one bad frame from
        # dragging the stack, and it is the noise model the matched filter
        # will stand on.
        self.cmb_method.addItem(self.tr("Weighted (1/σ²)"), "weighted")
        self.cmb_method.setItemData(
            self.cmb_method.count() - 1,
            self.tr("Each frame counts by 1/σ² of its own sky: the same as "
                    "the sigma clip on a stable night, and what saves a "
                    "night with thin cloud or moon"), Qt.ToolTipRole)
        # D11: the FINAL stack's field (0 = the whole frame) and the
        # detection/sweep cutout's margin. The whole frame is what the
        # photometry wants; a smaller window is faster.
        self.cmb_final_size = self._ui.cmb_final_size
        self.spn_margin = self._ui.spn_margin
        self.cmb_final_size.addItem(self.tr("Whole frame"), 0)
        self.cmb_final_size.addItem(self.tr("1024 px"), 1024)
        self.cmb_final_size.addItem(self.tr("512 px"), 512)
        self.cmb_final_size.addItem(self.tr("256 px"), 256)
        self.cmb_final_size.setCurrentIndex(0)
        _mi = self.cmb_method.findData(
            config.get("astrometry_method", "sigma"))
        self.cmb_method.setCurrentIndex(_mi if _mi >= 0 else 3)
        self.cmb_format.addItem(self.tr("ADES PSV"), "ades")
        self.cmb_format.addItem(self.tr("MPC 80 columns"), "mpc80")
        self._btn_stack_label = self.btn_stack.text()
        self.spn_nobs.valueChanged.connect(lambda _v: self._refresh_preview())
        self.btn_stack.clicked.connect(self._on_stack)
        self.cmb_group.currentIndexChanged.connect(self._show_group)
        self.chk_force.toggled.connect(lambda _on: self._sync_report_buttons())
        self.btn_report.clicked.connect(self._on_report)
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_send_mpc.clicked.connect(self._on_send_mpc)
        self._sync_report_buttons()

    def _show_result_area(self, flag):
        # @args: flag - True when there is a result to show
        # @return: None. What belongs to the RESULT appears with a run and
        #          goes away with it: the strip, the table, the row that
        #          chooses which stack to look at, the check (a verdict that
        #          does not exist yet is a paragraph about nothing) and the
        #          report's text. The REPORT block itself stays: its buttons
        #          are disabled and it says what the flow will produce,
        #          which is part of planning.
        self.lbl_points_title.setVisible(flag)
        self.tbl_points.setVisible(flag)
        self._thumbs.setVisible(flag)
        self._ui.lbl_view.setVisible(flag)
        self.cmb_group.setVisible(flag)
        self._check_section.setVisible(flag)
        self._sections["report"].setVisible(flag)

    def _wrap_section(self, name, title, key, open_by_default=False):
        # @args: name - the .ui container's objectName, title - the block's
        #        title in plain language (it says WHAT it holds), key - the
        #        settings key that remembers whether it stays open,
        #        open_by_default - the state before the observer chooses
        # @return: the CollapsibleSection
        # The container comes OUT of the column and INTO the block, keeping
        # every widget inside it: the Designer file still owns the
        # structure, and the block only decides whether it is shown.
        content = getattr(self._ui, name)
        section = CollapsibleSection(title, self)
        self.layout().replaceWidget(content, section)
        content.setParent(None)
        section.contentLayout().addWidget(content)
        content.setVisible(True)
        section.setCollapsed(
            not bool(config.get(key, 1 if open_by_default else 0)))
        section.sectionToggled.connect(
            lambda opened, k=key: config.set(k, 1 if opened else 0))
        return section

    # ------------------------------------------------------- host wiring

    def set_active(self, flag):
        # @args: flag - True when the dialog hands this tab the stage
        # @return: None. The context is re-read on entering: the visit may
        #          have been armed (or changed) while the tab was hidden;
        #          on leaving, the measured-position mark is taken off the
        #          shared stage (it belongs to this tab).
        if flag:
            self._sync_context()
            self._sync_recipe_row()
        elif self._view is not None:
            self._view.clear_overlays()

    def refresh_context(self):
        # Called by the dialog when the host sets (or clears) the
        # astrometry hook, so the tab does not wait for a stage change.
        # @return: None
        self._sync_context()

    def shutdown(self):
        # The pipeline worker must not outlive the workbench: a QThread
        # destroyed while it runs aborts the whole application (the trap
        # every other tab documents). Cancel stops it at the next stage
        # boundary and wait() gives it a bounded time to land.
        # @return: None
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)
        self._worker = None

    def _context(self):
        # @return: the visit context {"pid", "session_id", "paths",
        #          "object_name"} the host hooked, or None (ad-hoc open:
        #          without a visit there is no sequence, D15)
        dlg = host_of(self)
        getter = getattr(dlg, "astrometry_context", None)
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception as err:
            logger.warning("astrometry hook failed: %s", err)
            return None

    def _recipe(self):
        # @return: the photometry recipe the Fotometria tab is holding right
        #          now (band, apertures, sky method, centroid, colour term),
        #          or None when there is no host to ask
        # There is deliberately NO second copy of the recipe: the tab that
        # has always edited it is the only editor, so the apertures the
        # brightness is measured with cannot drift away from the ones the
        # observer sees.
        ask = getattr(host_of(self), "photometry_recipe", None)
        if not callable(ask):
            return None
        try:
            return ask()
        except Exception as err:
            logger.warning("photometry recipe hook failed: %s", err)
            return None

    def _on_edit_recipe(self):
        # @return: None. The recipe is edited in the Photometry tab: this is
        #          the deep link to it, nothing more.
        show = getattr(host_of(self), "show_tab", None)
        if callable(show):
            show("measure")

    def _sync_recipe_row(self):
        # @return: None. The line says what the brightness WILL be measured
        #          with, before the run: a recipe read silently is a number
        #          nobody can question.
        recipe = self._recipe() or {}
        on = bool(self.chk_brightness.isChecked())
        self.lbl_recipe.setEnabled(on)
        self.btn_recipe.setEnabled(on)
        if not on:
            self.lbl_recipe.setText(self.tr(
                "The brightness is not measured: this run reports "
                "positions only."))
            self._fit_label(self.lbl_recipe)
            return
        if not recipe:
            self.lbl_recipe.setText(self.tr(
                "Photometry recipe: the editor's defaults (open the "
                "Photometry tab to see or change them)."))
            self._fit_label(self.lbl_recipe)
            return
        band = recipe.get("band") or self.tr("the comps' own band")
        self.lbl_recipe.setText(self.tr(
            "Photometry recipe: %1 · apertures %2 · sky %3").replace(
                "%1", str(band)).replace(
                "%2", self._recipe_radii_text(recipe)).replace(
                "%3", str(recipe.get("sky") or "median")))
        self._fit_label(self.lbl_recipe)

    def _recipe_radii_text(self, recipe):
        # @args: recipe - the photometry recipe
        # @return: how the aperture is sized, in words or in px
        # "From the seeing" is a CHOICE, not a number: the recipe hands the
        # radii to the measured FWHM, so there is no triple to print.
        if recipe.get("seeing") and not recipe.get("radii_manual"):
            return self.tr("from the seeing")
        vals = [recipe.get("rap"), recipe.get("rin"), recipe.get("rout")]
        if any(v is None for v in vals):
            return self.tr("the defaults")
        return " ".join(("/".join(f"{float(v):.1f}" for v in vals), "px"))

    def _say(self, text):
        # @args: text - the status line's text ("" hides it)
        # @return: None
        self.lbl_status.setVisible(bool(text))
        self._set_wrapped(self.lbl_status, text or "")

    def _set_wrapped(self, label, text):
        # @args: label - a QLabel with wordWrap, text - its new text
        # @return: None
        label.setText(text)
        self._fit_label(label)

    def _fit_label(self, label):
        # @args: label - a QLabel with wordWrap whose text just changed
        # @return: None. Setting the text is not enough for a wrapped label:
        #          it does not always ask for the height its text needs (the
        #          sizeHint is computed for a width that changes later), and
        #          then every line comes out clipped at the top and the
        #          bottom. Asking the label itself, at the width it has NOW,
        #          is the fix the measure tab and the manual window already
        #          carry. A few pixels is not a width: at 1 px a wrapped
        #          label would want one line per word.
        if label is None or label.width() < 50:
            return
        need = label.heightForWidth(label.width())
        if need and need > 0:
            label.setMinimumHeight(int(need))

    def resizeEvent(self, event):
        # @args: event - the resize event, passed on
        # @return: None. A wider or narrower column needs another number of
        #          lines, so the wrapped labels are refitted here, where
        #          the width is known.
        super().resizeEvent(event)
        for name in ("lbl_object", "lbl_status", "lbl_recipe"):
            label = getattr(self._ui, name, None)
            if label is not None and label.isVisible():
                self._fit_label(label)

    # ------------------------------------------------------------- visit

    def _sync_context(self):
        # The visit arms the tab (D15): with no visit the stack button
        # stays DISABLED and the object line says why (a dead button
        # teaches nobody). The frames' headers are read once per visit:
        # load_sequence never touches pixels, so this is cheap enough for
        # the GUI thread.
        # @return: None
        ctx = self._context() or {}
        paths = tuple(ctx.get("paths") or ())
        running = self._worker is not None and self._worker.isRunning()
        self.btn_stack.setEnabled(bool(paths) and not running)
        if not paths:
            self._frames = None
            self._ctx_paths = None
            self.spn_nobs.setEnabled(False)
            self.tbl_snr.setRowCount(0)
            self.lbl_object.setText(self.tr(
                "Object and frames: open the editor from a visit to arm "
                "the sequence."))
            self._fit_label(self.lbl_object)
            return
        if paths != self._ctx_paths:
            from ..core import track_stack
            self._frames = track_stack.load_sequence(list(paths), config)
            self._ctx_paths = paths
            # a different visit invalidates the last run: its stacks, its
            # check and its report belong to the other sequence
            self._base_snr = None
            self._result = None
            self.cmb_group.clear()
            self.cmb_group.setEnabled(False)
            self.txt_report.clear()
            self.txt_notes.setVisible(False)
            self._show_result_area(False)
            self._sync_report_buttons()
        n = len(self._frames)
        self.spn_nobs.setEnabled(True)
        self.spn_nobs.blockSignals(True)
        self.spn_nobs.setRange(1, max(1, n))
        self.spn_nobs.setValue(min(self.spn_nobs.value(), max(1, n)))
        self.spn_nobs.blockSignals(False)
        # the object line, read-only (it comes from the project and from
        # Horizons): name, frames and the visit's own time window
        name = ctx.get("object_name") or self.tr("(unnamed)")
        line = self.tr("Object: %1 · %2 frames").replace(
            "%1", name).replace("%2", str(n))
        stamps = [f.t_mid_jd for f in self._frames if f.t_mid_jd is not None]
        if stamps:
            from ..core import coords
            t0 = coords.datetime_from_jd(min(stamps))
            t1 = coords.datetime_from_jd(max(stamps))
            line += self.tr(" · window %1–%2 UT").replace(
                "%1", t0.strftime("%H:%M")).replace("%2", t1.strftime("%H:%M"))
        self.lbl_object.setText(line)
        self._fit_label(self.lbl_object)
        self._refresh_preview()

    def _refresh_preview(self):
        # D22: the SNR grows with sqrt(n), so asking for more observations
        # splits the signal, and the table says it BEFORE the user accepts.
        # Until the first run there is no measured base SNR and the column
        # stays "–": an estimate without a measurement would be invented.
        # @return: None
        from ..core import track_stack
        # the spinbox's floor is 1, but a tab whose visit was never armed
        # can still be repainted: a zero would divide inside split_groups
        rows = track_stack.preview_groups(self._frames or [],
                                          max(1, self.spn_nobs.value()),
                                          base_snr=self._base_snr)
        floor = float(config.get("astrometry_submit_snr", 20.0))
        tbl = self.tbl_snr
        tbl.setRowCount(len(rows))
        for i, row in enumerate(rows):
            cells = (str(i + 1), str(row["n_frames"]),
                     self._t_mid_text(row["t_mid"]),
                     self._snr_text(row["snr_est"], floor))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled)   # read-only: a preview
                if col == 3 and row["snr_est"] is not None \
                        and row["snr_est"] < floor:
                    item.setToolTip(self.tr(
                        "Below the MPC submission floor of %1: this "
                        "observation would be left out of the report"
                    ).replace("%1", f"{floor:.0f}"))
                tbl.setItem(i, col, item)
        # The plan row shows the same number in one line: the table is the
        # detail and it lives folded, but the decision (how many
        # observations) is taken from the row.
        parts = [self._snr_text(row["snr_est"], floor) for row in rows]
        self.lbl_snr_line.setText(
            self.tr("Expected SNR: %1").replace("%1", " · ".join(parts))
            if parts else "")

    def _snr_text(self, est, floor):
        # @args: est - the expected SNR or None, floor - the submission
        #        floor (D26)
        # @return: the cell text; the ⚠ marks a group below the floor, so
        #          it is seen before stacking, not after
        if est is None:
            return "–"
        return f"{est:.1f}" + (" ⚠" if est < floor else "")

    def _t_mid_text(self, jd):
        # @args: jd - the group's middle-of-exposure instant (JD) or None
        # @return: "HH:MM:SS" UTC, or "–"
        if jd is None:
            return "–"
        from ..core import coords
        return coords.datetime_from_jd(jd).strftime("%H:%M:%S")

    # -------------------------------------------------------------- run

    def _on_stack(self):
        # The run button, and its Cancel while the worker runs (a long
        # pipeline must have a way out, P1 #12). Everything heavy lives in
        # TrackStackWorker; the tab wires, paints and persists nothing:
        # the report goes to the visit's MPC block, which owns the
        # database round trip (ADR-022/045).
        # @return: None
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._say(self.tr(
                "Cancelling: the pipeline stops at the stage boundary it "
                "is at; nothing is kept from a cancelled run."))
            return
        ctx = self._context() or {}
        paths = ctx.get("paths") or []
        name = ctx.get("object_name") or ""
        if not paths:
            self._say(self.tr(
                "No visit with frames: open the editor from a visit to "
                "stack its sequence."))
            return
        if not name:
            self._say(self.tr(
                "The project has no object name: the ephemeris cannot be "
                "fetched, and without it there is no track."))
            return
        from .workers import TrackStackWorker
        self.prg_stack.setVisible(True)
        self.prg_stack.setRange(0, 0)          # busy until a stage counts
        self.btn_stack.setText(self.tr("Cancel"))
        # the previous run's evidence goes before the new one starts: a
        # stale strip next to a fresh run is a lie
        self._thumbs.clear()
        self.btn_blink.setEnabled(False)
        self._say("")
        self._worker = TrackStackWorker(
            paths, name, self.spn_nobs.value(),
            method=self.cmb_method.currentData() or "sigma", cfg=config,
            obs_code=str(config.get("mpc_code", "")),
            site=str(config.get("mpc_code", "")),
            final_size=int(self.cmb_final_size.currentData() or 0),
            margin=int(self.spn_margin.value()),
            comps=ctx.get("comps"), target_mag=ctx.get("target_mag"),
            recipe=self._recipe(),
            phot_enabled=self.chk_brightness.isChecked(),
            save_star_stack=self.chk_starstack.isChecked(),
            calibrate=self.chk_calibrate.isChecked())
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, stage, done, total):
        # @args: stage - the worker's stage key, done/total - inside that
        #        stage
        # @return: None. The human text is a literal self.tr() table (the
        #          way TonightWorker's phases do it, CONTRIBUTING rule 5).
        # A stage that is ONE long operation (the base stack, the comparison
        # windows, the check's round trip to the MPC and Find_Orb) has no
        # inside to count: a bar pinned at 0 reads as a freeze, so it goes
        # BUSY (indeterminate) and the status line says what is happening.
        if total > 1:
            self.prg_stack.setRange(0, total)
            self.prg_stack.setValue(done)
        else:
            self.prg_stack.setRange(0, 0)
        text = self._stage_text(stage)
        if text:
            self._say(text + (f" ({done}/{total})" if total > 1 else ""))

    def _stage_text(self, key):
        # @args: key - one of TrackStackWorker's stage keys
        # @return: the human text for the status line
        return {
            "calibrate": self.tr("Calibrating the frames…"),
            "pseudoflat": self.tr("Building a flat from the frames…"),
            "solve": self.tr("Solving the reference frame…"),
            "register": self.tr("Registering the frames…"),
            "base": self.tr("Stacking the whole sequence…"),
            "detect": self.tr("Looking for the object…"),
            "sweep": self.tr("Sweeping the velocity…"),
            "groups": self.tr("Stacking each observation…"),
            "measure": self.tr("Measuring the positions…"),
            "starstack": self.tr("Stacking the stars…"),
            "photometry": self.tr("Measuring the brightness…"),
            "check": self.tr("Checking against other observers…"),
        }.get(key, "")

    def _run_ended(self):
        # @return: None. The button comes back from Cancel and the bar
        #          hides; the button stays disabled without a visit.
        self.btn_stack.setText(self._btn_stack_label)
        self.prg_stack.setVisible(False)
        self.btn_stack.setEnabled(bool(self._ctx_paths))

    def _on_failed(self, message):
        # @args: message - the worker's error (internal English, like the
        #        other workers' failed signal)
        # @return: None
        self._run_ended()
        self._say(self.tr("The run failed:") + f" {message}")

    def _on_finished(self, payload):
        # @args: payload - TrackStackWorker's result dict
        # @return: None
        self._run_ended()
        self._result = payload if isinstance(payload, dict) else {}
        status = self._result.get("status")
        if status == "cancelled":
            self._say(self.tr("Cancelled: nothing was kept from this run."))
            return
        if status == "error":
            self._say(self.tr("The run could not finish:") + " "
                      + str(self._result.get("error") or ""))
            return
        if status == "not_detected":
            # the run is persisted FIRST: its id is what the stacks carry in
            # their NS_RUN card, and the stacks are written when the result
            # is painted
            self._persist_run(self._result)
            self._paint_not_detected()
            return
        self._persist_run(self._result)
        self._paint_run()

    def _persist_run(self, payload):
        # ADR-062, phase 8: the HOST writes the run (the tab never touches
        # the database) and hands back its id, which the "undo this run"
        # button needs. Without a host (an ad-hoc open) there is nothing to
        # persist and the button stays off.
        # @args: payload - the worker's result dict
        # @return: None
        host = host_of(self)
        persist = getattr(host, "persist_astrometry", None)
        self._run_id = persist(payload) if callable(persist) else None
        self._sync_report_buttons()

    def _on_undo(self):
        # The run's own undo (D14): its points and its frame manifest go,
        # the run row stays marked "undone", and nothing else is touched.
        # @return: None
        if self._run_id is None:
            return
        host = host_of(self)
        undo = getattr(host, "undo_astrometry", None)
        removed = undo(self._run_id) if callable(undo) else None
        self._run_id = None
        self._result = None
        self.cmb_group.clear()
        self.cmb_group.setEnabled(False)
        self.tbl_points.setRowCount(0)
        self.txt_report.clear()
        self._thumbs.clear()
        self.btn_blink.setEnabled(False)
        self._show_result_area(False)
        self._sync_report_buttons()
        self._say(self.tr("Run undone: %1 observations removed."
                          ).replace("%1", str(removed if removed is not None
                                             else 0)))

    def _paint_not_detected(self):
        # D10: below the gate there is no sweep and no measurement (the
        # sweep would measure noise); the limit magnitude is the useful
        # datum, because it says how deep the night reached.
        # @return: None
        det = self._result.get("detection")
        gate = float(config.get("astrometry_snr_sigma", 3.5))
        text = self.tr(
            "The object was not detected above the %1σ gate: the velocity "
            "sweep is not run, because measuring noise is how a false "
            "positive is manufactured.").replace("%1", f"{gate:.1f}")
        if det is not None and getattr(det, "mag_limit", None) is not None:
            text += " " + self.tr(
                "The stack's limit magnitude is %1: the night reached "
                "that deep.").replace("%1", f"{det.mag_limit:.2f}")
        self.txt_notes.setVisible(True)
        self.txt_notes.setPlainText(text)
        self.cmb_group.setEnabled(False)
        self._sync_report_buttons()
        self._say("")

    def _paint_run(self):
        # @return: None. The run's notes (dithering D27, WCS quality, the
        #          sweep's winner), the group viewer, the measurement
        #          table and the check's verdict.
        notes = []
        dither = self._result.get("dither")
        if dither is not None and not dither.dithered:
            # informative, never blocking (D27): pattern noise stacks and
            # manufactures phantom detections (the MPC's warning number one)
            notes.append(self.tr(
                "The sequence is not dithered: pattern noise may stack up"))
        qc = self._result.get("wcs_qc")
        if qc is not None and not qc.ok:
            notes.append(self.tr(
                "The composed WCS is off by up to %1″ against a direct "
                "solve: the field's distortion is biting").replace(
                    "%1", f"{qc.max_offset_arcsec:.2f}"))
        sweep = self._result.get("sweep")
        if sweep is not None and sweep.best is not None:
            notes.append(self.tr(
                "Velocity sweep: %1″/min at PA %2° (%3 velocities scored; "
                "the score is SNR × roundness, which penalises a smeared "
                "object)").replace("%1", f"{sweep.best['rate']:.2f}").replace(
                    "%2", f"{sweep.best['pa']:.0f}").replace(
                    "%3", str(len(sweep.grid))))
        det = self._result.get("detection")
        if det is not None:
            gate = float(config.get("astrometry_snr_sigma", 3.5))
            notes.append(self.tr(
                "Detected on the base stack with SNR %1 (the gate is %2σ: "
                "below it nothing is measured)").replace(
                    "%1", f"{det.snr:.1f}").replace("%2", f"{gate:.1f}"))
        phot = self._result.get("photometry")
        if phot is not None and phot.get("mag") is not None:
            # The magnitude comes from the STACKS (the object on its own,
            # the comps on a second one aligned on the stars) and one
            # measurement is made per observation, which is what the MPC
            # publishes. Saying where the comps came from matters: an
            # automatic proposal is a first guess, not the observer's own.
            origin = (self.tr("the project's sequence")
                      if phot.get("source") == "project"
                      else self.tr("an automatic proposal"))
            notes.append(self.tr(
                "Brightness %1 ± %2 %3 per observation (%4 observations, "
                "%5 frames each) from %6 comparison stars · %7").replace(
                    "%1", f"{phot['mag']:.3f}").replace(
                    "%2", f"{phot.get('err') or 0:.3f}").replace(
                    "%3", str(phot.get("band") or "")).replace(
                    "%4", str(phot.get("n_obs") or 0)).replace(
                    "%5", str(phot.get("n_frames") or 0)).replace(
                    "%6", str(phot.get("n_comps") or 0)).replace(
                    "%7", origin))
        elif self._result.get("phot_skipped"):
            notes.append(self.tr(
                "The brightness was not measured (the box is off): this "
                "run reports positions only"))
        self.txt_notes.setVisible(bool(notes))
        self.txt_notes.setPlainText("\n".join("• " + n for n in notes))
        # the viewer: one entry per observation, the first one on stage
        self.cmb_group.blockSignals(True)
        self.cmb_group.clear()
        for i, group in enumerate(self._result.get("groups") or []):
            self.cmb_group.addItem(
                self.tr("Observation %1 (%2 frames)").replace(
                    "%1", str(i + 1)).replace("%2", str(group[1] - group[0])),
                i)
        self.cmb_group.blockSignals(False)
        self.cmb_group.setEnabled(self.cmb_group.count() > 0)
        # the strip: the same stacks, visible side by side at ONE stretch,
        # so a faint observation cannot hide behind a bright one
        stacks = self._result.get("stacks") or []
        qs = self._result.get("qs") or []
        labels = [self.tr("Obs. %1").replace("%1", str(i + 1))
                  for i in range(len(stacks))]
        self._thumbs.set_stacks([s for s, _rep in stacks], qs, labels)
        self.btn_blink.setEnabled(any(s is not None for s, _rep in stacks))
        self._show_result_area(True)
        if self.cmb_group.count():
            self.cmb_group.setCurrentIndex(0)
            self._show_group(0)
        self._fill_points()
        self._fill_check()
        # the measured base SNR turns the expected-SNR column into a real
        # projection for the next choice of observations (D22)
        if det is not None and det.snr:
            self._base_snr = float(det.snr)
            self._refresh_preview()
        n = len(self._result.get("points") or [])
        # the report buttons FOLLOW the run (they were only refreshed at
        # init and on reset, so a successful run left them disabled)
        self._sync_report_buttons()
        note = self.tr("Sequence stacked: %1 observations measured."
                       ).replace("%1", str(n))
        extra = self._register_note(self._result.get("register_report"),
                                    self._result.get("n_off_frame") or 0)
        if extra:
            note += " " + extra
        shape = self._shape_note(self._result.get("photometry"))
        if shape:
            note += " " + shape
        diag = self._diag_note(self._result.get("photometry"))
        if diag:
            note += " " + diag
        cal = self._calibration_note(self._result.get("calibration"))
        if cal:
            note += " " + cal
        self._say(note)

    def _calibration_note(self, cal):
        # @args: cal - the run's calibration summary (or None)
        # @return: what the magnitude was measured with (or "")
        # ADR-061: a brightness never goes out without saying whether the
        # frames were calibrated and with which masters. The observer asked
        # for the calibration to be OPTIONAL, so the note also has to say
        # when it was not applied.
        cal = cal or {}
        if not cal:
            return ""
        bits = []
        if cal.get("offsets"):
            bits.append(self.tr("dark/bias: %1").replace(
                "%1", ", ".join(cal["offsets"])))
        if cal.get("flats"):
            bits.append(self.tr("flat: %1").replace(
                "%1", ", ".join(cal["flats"])))
        text = self.tr("Calibrated %1 frames").replace(
            "%1", str(cal.get("n") or 0))
        if bits:
            text += " (" + " · ".join(bits) + ")"
        else:
            text += " (" + self.tr("no master matched") + ")"
        info = cal.get("pseudo_flat") or {}
        if info.get("note"):
            text += ". " + self.tr("Warning:") + " " + info["note"]
        return text + "."

    def _shape_note(self, phot):
        # @args: phot - the run's photometry dict (or None)
        # @return: what the object's SHAPE says, in words (or "")
        # P2: the trail is the honest half of the exposure. A moving object
        # smears along its path, and the app says by how many pixels, so the
        # next exposure can be shortened instead of the loss being found
        # later as a low SNR. The matched filter's gain is said too: it is
        # what the pipeline could read on this very stack, and a number the
        # observer can compare with the SNR they got.
        phot = phot or {}
        parts = []
        trail = phot.get("trail_px")
        if trail:
            line = self.tr("The object is trailed by %1 px").replace(
                "%1", f"{float(trail):.1f}")
            pa = phot.get("trail_pa_deg")
            if pa is not None:
                line += self.tr(" along PA %1°").replace(
                    "%1", f"{float(pa):.0f}")
            parts.append(line + self.tr(
                ": shorten the exposure or expect a wider PSF."))
        gain = phot.get("snr_gain")
        if gain and float(gain) > 1.05:
            parts.append(self.tr(
                "The matched filter would read %1x the aperture's SNR on "
                "this stack.").replace("%1", f"{float(gain):.2f}"))
        return " ".join(parts)

    def _diag_note(self, phot):
        # @args: phot - the run's photometry dict (or None)
        # @return: the night's own diagnosis, in words (or "")
        # P3: two questions the observer asks after a run, both answered with
        # the stars of THIS stack. How faint the night went (the limiting
        # magnitude), and whether the plate solution is even across the field
        # (the median residual per cell of a 4x4 grid): one number for the
        # whole plate hides the corners, which is where a wrong scale or a
        # tilted chip shows up.
        phot = phot or {}
        parts = []
        limit = phot.get("limit") or {}
        if limit.get("ok") and limit.get("mag") is not None:
            line = self.tr("Limiting magnitude (5σ): %1").replace(
                "%1", f"{float(limit['mag']):.1f}")
            if not limit.get("sky_limited"):
                # the slope is the physics' own check: a field that is not
                # sky-limited gives a number nobody should quote
                line += self.tr(" (not sky-limited, do not trust it)")
            parts.append(line)
        grid = phot.get("grid") or {}
        if grid.get("ok") and grid.get("median") is not None:
            line = self.tr(
                "Solution residuals: %1″ median").replace(
                    "%1", f"{float(grid['median']):.2f}")
            worst = grid.get("worst")
            if worst is not None and float(worst) > 2.0 * max(
                    float(grid["median"]), 0.05):
                # a corner that is much worse than the middle is WHERE the
                # solution is bad, and that is the useful half of the answer
                line += self.tr(", up to %1″ in the worst cell").replace(
                    "%1", f"{float(worst):.2f}")
            parts.append(line)
        return " ".join(parts)

    def _register_note(self, report, off_frame=0):
        # @args: report - track_stack.registration_report output (or None)
        # @args: report - track_stack.registration_report output (or None),
        #        off_frame - how many registered frames do NOT contain the
        #        object (the worker counts them once the ephemeris is known)
        # @return: what the registration did, in plain language. This is the
        #          honest half of a run: a frame left out is a factor in the
        #          stack's SNR, and a visit that is really two runs is a
        #          fact the observer needs BEFORE believing the result. It
        #          replaces the old bare "N frames could not be aligned".
        report = report or {}
        parts = []
        n_rot = int(report.get("n_rotation") or 0)
        if n_rot:
            parts.append(self.tr(
                "%1 frames were saved by fitting the field's small rotation "
                "(they were being thrown away).").replace("%1", str(n_rot)))
        off = int(off_frame or 0)
        if off:
            # registered, but the object is not on the sensor: a shifted
            # field (the second run of a visit) leaves the object outside
            # the frame, and stacking those frames would only add noise
            # where the object is measured
            parts.append(self.tr(
                "%1 frames do not contain the object and were left out.").replace(
                    "%1", str(off)))
        failed = int(report.get("n_failed") or 0)
        if failed:
            line = self.tr("%1 frames could not be aligned").replace(
                "%1", str(failed))
            reasons = self._register_reasons(report.get("reasons") or {})
            if reasons:
                line += f" ({reasons})"
            parts.append(line + ".")
        blocks = report.get("blocks") or []
        if report.get("multi_run") and len(blocks) > 1:
            second = blocks[1]
            offset = (float(second.get("dx") or 0.0) ** 2
                      + float(second.get("dy") or 0.0) ** 2) ** 0.5
            text = self.tr(
                "The visit looks like %1 runs: the second one is %2 px away"
            ).replace("%1", str(len(blocks))).replace("%2", f"{offset:.0f}")
            gap = second.get("gap_s")
            if gap:
                text += self.tr(" and starts %1 min later").replace(
                    "%1", f"{float(gap) / 60.0:.0f}")
            parts.append(text + ".")
        return " ".join(parts)

    def _register_reasons(self, reasons):
        # @args: reasons - {internal code: count} from the report
        # @return: the reasons in words, or "" when there are none. The
        #          code is the core's English key; the words are here, one
        #          per language, and a code we do not know is passed through
        #          rather than hidden.
        words = {"rms": self.tr("their stars did not agree on the fit"),
                 "few_stars": self.tr("too few stars"),
                 "no_stars": self.tr("no stars detected"),
                 "no_fit": self.tr("no transform could be fitted")}
        if not reasons:
            return ""
        if len(reasons) == 1:
            key = next(iter(reasons))
            return words.get(key, key)
        return ", ".join(
            f"{words.get(key, key)}: {count}"
            for key, count in sorted(reasons.items(),
                                     key=lambda kv: -kv[1]))

    def _show_group(self, index):
        # The group's stack goes to the MAIN stage (the shared state), so
        # the histogram, the stretch and the marks work on it and the other
        # tabs can operate on top. It is SAVED in the project (kind
        # "stack") instead of a temp file that vanishes, and the measured
        # position is marked on the shared view while this tab is on stage.
        # @args: index - the group's index in the last run
        # @return: None
        result = self._result or {}
        stacks = result.get("stacks") or []
        if index is None or index < 0 or index >= len(stacks):
            return
        import numpy as np
        stack, _rep = stacks[index]
        if stack is None:
            return
        path = self._stack_path(index)
        try:
            from astropy.io import fits
            hdu = fits.PrimaryHDU(np.asarray(stack, dtype=np.float32))
            # The stack's own WCS, from the reference WCS shifted by the
            # cutout's origin: the plate is KNOWN, so nothing has to solve
            # it. On this stack the stars are trails (it follows the
            # object) and a blind solve finds no stars at all.
            wcss = result.get("wcs_by_group") or []
            if index < len(wcss) and wcss[index] is not None:
                hdu.header.update(wcss[index].to_header())
            # The app's own word about WHAT this file is. The stack follows
            # the object, so its stars are TRAILS: without this card the
            # Photometry tab would happily build a zero point out of
            # streaks, and with it the tab can say why it will not.
            hdu.header["NS_STACK"] = (
                "object", "the stars are trails")
            # The two stacks of an observation are a PAIR: the object's has
            # the light and the star's has the comps, and the Photometry tab
            # needs both to measure the brightness by hand. The link travels
            # in the header (a file name, same folder), so it survives
            # moving the project and there is no database to migrate.
            stars = result.get("star_stacks") or []
            if index < len(stars) and stars[index] is not None \
                    and stars[index][0] is not None:
                hdu.header["NS_PAIR"] = self._stack_name(index, stars=True)
            name = (self._context() or {}).get("object_name")
            if name:
                hdu.header["OBJECT"] = str(name)
            hdu.header["NS_NOBS"] = (int(index) + 1,
                                     "observation of the visit")
            groups = result.get("groups") or []
            if index < len(groups):
                hdu.header["NS_NFRAM"] = (
                    int(groups[index][1] - groups[index][0]),
                    "frames in this stack")
            # WHICH run this stack came from, so the Photometry tab can write
            # a brightness measured by hand back to the right observation
            if self._run_id is not None:
                hdu.header["NS_RUN"] = (int(self._run_id),
                                        "the astrometry run it belongs to")
            # The band's own data, written into the file: the frame's date,
            # exposure, filter and kit, and the run's motion and brightness,
            # so reopening this stack says the same as the day it was made.
            self._write_frame_meta(hdu.header, result, index)
            self._write_band_cards(hdu.header, result, index)
            hdu.writeto(str(path), overwrite=True)
        except Exception as err:     # a stack that cannot be written says so
            logger.warning("group stack write failed: %s", err)
            self._say(self.tr("The group's stack could not be written:")
                      + f" {err}")
            return
        state = self._state if self._view is not None else self._stack_state
        view = self._view if self._view is not None else self._stack_view
        try:
            state.load(str(path))
        except Exception as err:
            logger.warning("group stack view failed: %s", err)
            self._say(self.tr("The group's stack could not be shown:")
                      + f" {err}")
            return
        # the measured position, marked: scene coordinates are the state's
        # business (it is the only one that flips y), never the tab's
        view.clear_overlays()
        points = result.get("points") or []
        if index < len(points):
            sp = points[index][0]
            w, h = state.plate_shape
            sx, sy = state.data_to_scene(sp.x, sp.y)
            for item in cross_marker_items(sx, sy, float(w), float(h),
                                           "#ff5555", 10.0):
                view.add_overlay(item)
        # the stack belongs to the project: register it there (kind
        # "stack") so it shows in the visit and can be reopened
        if self._view is not None:
            notify = getattr(host_of(self), "notify_saved", None)
            if callable(notify):
                notify([str(path)], "stack")
        # The object's own position, annotated ON the stack: the editor
        # paints the marker (the same AIJ card the Annotate tab writes), so
        # in the Photometry tab you SEE where the object is and click it
        # instead of hunting a point among the stars' trails.
        self._annotate_object(path, index, result)
        # The star stack of the same observation, when the run kept one: it
        # is the plate the Photometry tab needs to measure the pair by hand
        # (on the object's stack the comps are trails). It is written when
        # the observation is shown, like the object's stack, and registered
        # in the visit with the same kind.
        self._write_star_stack(index, result)

    def _stack_path(self, index, stars=False):
        # @args: index - the group's index, stars - True for the star stack
        # @return: where the group's stack is written: the project's own
        #          folder when the host points at one (it lands next to the
        #          rest of the project and survives a restart), the system
        #          temp otherwise
        import tempfile
        folder = None
        ask = getattr(host_of(self), "export_folder", None)
        if callable(ask):
            try:
                folder = ask()
            except Exception:
                folder = None
        base = Path(folder) if folder else Path(tempfile.gettempdir())
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            base = Path(tempfile.gettempdir())
        return base / self._stack_name(index, stars=stars)

    def _stack_name(self, index, stars=False):
        # @args: index - the group's index
        # @return: a file name that says what the stack IS: the object, the
        #          observation number and its mid time. "stack_obs2.fits"
        #          said nothing once the run was forgotten, and a visit
        #          holds several of them.
        ctx = self._context() or {}
        raw = (ctx.get("object_name") or "object").strip() or "object"
        slug = "".join(ch if (ch.isalnum() or ch in "-_") else "_"
                       for ch in raw.replace(" ", "")) or "object"
        stamp = ""
        mids = (self._result or {}).get("mids") or []
        mjd = mids[index] if 0 <= index < len(mids) else None
        if mjd:
            from datetime import datetime, timedelta
            # The run's mids are JULIAN dates (the engine's own currency) and
            # the file name wants the UT, so the MJD offset comes off here.
            # Using the JD as if it were an MJD named the stacks year 8596:
            # the author's own files read 2025UR_obs1_85961010T094820.
            try:
                ut = datetime(1858, 11, 17) + timedelta(days=float(mjd)
                                                        - 2400000.5)
                stamp = "_" + ut.strftime("%Y%m%dT%H%M%S")
            except (OverflowError, ValueError, OSError):
                # a mid outside the calendar (a test fixture, a corrupt
                # header) must not cost the stack its name: the stamp is a
                # nicety, the object and the observation number are not
                stamp = ""
        return f"{slug}_obs{index + 1}{stamp}{'_stars' if stars else ''}.fits"

    def _annotate_object(self, path, index, result):
        # @args: path - the stack just written, index - the observation,
        #        result - the run's payload
        # @return: None. The measured position, written as the annotation the
        #          editor already knows how to paint. A failure here must
        #          never cost the stack: the marker is a help, the file is
        #          the work.
        points = result.get("points") or []
        if index >= len(points):
            return
        sp = points[index][0]
        if sp is None or sp.x is None or sp.y is None:
            return
        try:
            from ..core import astrometry, fits_annotate
            w0 = result.get("w0")
            scale = astrometry.pixel_scale_arcsec(w0) if w0 is not None \
                else None
            fits_annotate.write_annotated_fits(
                path, path, sn_xy=(float(sp.x), float(sp.y)), scale=scale,
                obj_name=(self._context() or {}).get("object_name") or "",
                ra_deg=(float(sp.ra) if sp.ra is not None else None),
                dec_deg=(float(sp.dec) if sp.dec is not None else None))
        except Exception as err:
            logger.warning("the stack could not be annotated: %s", err)

    # ------------------------------------------------------------ the band

    def band_facts(self, header):
        # What the plate's heading (ADR-046) says about one of THIS tab's
        # stacks. Everything comes from the stack's own header, written when
        # the stack was saved, so the band says the same right after the run
        # and when the file is reopened in another session (no run in
        # memory, no database round trip).
        # @args: header - the open plate's header dict
        # @return: {"measured", "measured_pos", "motion"} or None when the
        #          plate is not one of this run's stacks
        header = header or {}
        kind = str(header.get("NS_STACK") or "")
        if kind not in ("object", "stars") or header.get("NS_RUN") is None:
            return None
        stars = kind == "stars"
        facts = {}
        motion = self._motion_from_header(header)
        if motion is not None:
            facts["motion"] = motion
        if not stars:
            ra, dec = header.get("NS_RA"), header.get("NS_DEC")
            if ra is not None and dec is not None:
                # the position MEASURED on this plate (the astrometric
                # centroid): written with the stack and, again, by the
                # annotation pass
                facts["measured_pos"] = (float(ra), float(dec))
            measured = self._measured_from_header(header)
            if measured is not None:
                facts["measured"] = measured
        return facts or None

    def _motion_from_header(self, header):
        # @args: header - a stack's header
        # @return: {"rate_arcsec_min", "pa_deg", "measured"} or None. The
        #          word "measured" is what decides between the ink and the
        #          dimmed (eph) colour: the sweep measured it, or it is only
        #          the ephemeris' prediction.
        rate = header.get("NS_RATE")
        if rate is None:
            return None
        pa = header.get("NS_PA")
        return {"rate_arcsec_min": float(rate),
                "pa_deg": (float(pa) if pa is not None else None),
                "measured": str(header.get("NS_MOT") or "sweep") == "sweep"}

    def _measured_from_header(self, header):
        # @args: header - the object stack's header
        # @return: the brightness of this observation with the signals that
        #          colour it (see chart_annotate.magnitude_role), or None
        mag = header.get("NS_MAG")
        if mag is None:
            return None
        chk = header.get("NS_MAGOK")
        err = header.get("NS_MAGER")
        comps = header.get("NS_MAGNC")
        return {"mag": float(mag),
                "err": (float(err) if err is not None else None),
                "band": header.get("NS_MAGB"),
                "comps": (int(comps) if comps is not None else None),
                "check_ok": (bool(chk) if chk is not None else None),
                "no_check": chk is None}

    def _write_frame_meta(self, header, result, index):
        # A stack is a combination of frames and it must say what they were.
        # Without these cards the band over a stack had no date, no exposure
        # and no filter at all: the header was born with the WCS and the NS_*
        # cards only. Copying them is not a nicety, it is what lets the band
        # read "8 × 3.0 s" and the night's own date.
        # @args: header - the stack's header being built, result - the run's
        #        payload, index - the observation
        # @return: None
        try:
            frames = result.get("frames") or []
            groups = result.get("groups") or []
            ref = None
            if 0 <= index < len(groups):
                start, end = groups[index]
                for i in range(int(start), min(int(end), len(frames))):
                    if getattr(frames[i], "header", None):
                        ref = frames[i]
                        break
            if ref is None and frames:
                ref = frames[0]
            if ref is None:
                return
            for key in ("EXPTIME", "FILTER", "INSTRUME", "TELESCOP"):
                value = (ref.header or {}).get(key)
                if isinstance(value, (str, int, float)) \
                        and str(value).strip():
                    header[key] = value
            # the date is the observation's own middle instant, so a visit
            # that spans two hours is dated where it really happened
            mids = result.get("mids") or []
            jd = mids[index] if 0 <= index < len(mids) else None
            if jd is not None:
                from ..core import coords
                header["DATE-OBS"] = coords.datetime_from_jd(
                    float(jd)).strftime("%Y-%m-%dT%H:%M:%S")
            elif getattr(ref, "date_obs", None):
                header["DATE-OBS"] = str(ref.date_obs)
        except Exception as err:      # a missing card never costs the stack
            logger.warning("the stack's frame metadata failed: %s", err)

    def _write_band_cards(self, header, result, index, stars=False):
        # What the band says about this stack, written into the file so a
        # stack reopened months later says exactly the same. The motion is
        # the sweep's own answer when it was measured and the ephemeris'
        # prediction, marked as such, otherwise; the brightness and the
        # signals that colour it go only on the object's stack (on the
        # stars' one the object is a trail and was not measured).
        # @args: header - the stack's header being built, result - the run's
        #        payload, index - the observation, stars - True for the star
        #        stack
        # @return: None
        try:
            best = None
            sweep = result.get("sweep")
            if sweep is not None:
                best = getattr(sweep, "best", None)
            if best and best.get("rate") is not None:
                header["NS_RATE"] = (
                    float(best["rate"]),
                    "arcsec/min, measured by the velocity sweep")
                if best.get("pa") is not None:
                    header["NS_PA"] = (float(best["pa"]),
                                       "deg north through east")
                header["NS_MOT"] = ("sweep", "the sweep measured it")
            elif result.get("base_rate") is not None:
                header["NS_RATE"] = (
                    float(result["base_rate"]),
                    "arcsec/min, ephemeris prediction")
                if result.get("base_pa") is not None:
                    header["NS_PA"] = (float(result["base_pa"]),
                                       "deg north through east")
                header["NS_MOT"] = ("eph",
                                    "ephemeris prediction, not measured")
            if stars:
                return
            # the position MEASURED on this stack (the astrometric
            # centroid). It is the same pair the annotation pass writes, and
            # writing it here too means the band reads it right away, without
            # waiting for the annotate step that rewrites the file.
            points = result.get("points") or []
            sp = points[index][0] if 0 <= index < len(points) else None
            if sp is not None and sp.ra is not None and sp.dec is not None:
                header["NS_RA"] = float(sp.ra)
                header["NS_DEC"] = float(sp.dec)
            phot = result.get("photometry") or {}
            per_obs = phot.get("per_obs") or []
            one = per_obs[index] if 0 <= index < len(per_obs) else None
            if one is not None and one.get("mag") is not None:
                header["NS_MAG"] = (float(one["mag"]),
                                    "measured on this stack")
                if one.get("err") is not None:
                    header["NS_MAGER"] = (float(one["err"]),
                                          "total error, mag")
                if one.get("n_comps") is not None:
                    header["NS_MAGNC"] = (
                        int(one["n_comps"]),
                        "comparison stars holding the zero point")
                if one.get("check") is not None:
                    header["NS_MAGOK"] = (
                        1 if one["check"] else 0,
                        "the check star's verdict")
            elif phot.get("mag") is not None:
                header["NS_MAG"] = (float(phot["mag"]),
                                    "median brightness of the run")
                if phot.get("err") is not None:
                    header["NS_MAGER"] = (float(phot["err"]),
                                          "total error, mag")
                if phot.get("n_comps") is not None:
                    header["NS_MAGNC"] = (
                        int(phot["n_comps"]),
                        "comparison stars holding the zero point")
            if phot.get("band"):
                header["NS_MAGB"] = (
                    str(phot["band"]), "band of the comparison stars")
        except Exception as err:      # a missing card never costs the stack
            logger.warning("the stack's band cards failed: %s", err)

    def _write_star_stack(self, index, result):
        # @args: index - the observation, result - the run's payload
        # @return: the path written, or None when the run kept no star stack
        # The second alignment of the same frames, saved as its own file so
        # the Photometry tab can read the comps on it. It carries the same
        # WCS (same box, same grid) and says what it is, so opening it never
        # asks a solver for stars that are, on the other stack, trails.
        import numpy as np
        stacks = result.get("star_stacks") or []
        if index >= len(stacks) or stacks[index] is None:
            return None
        stack, _rep = stacks[index]
        if stack is None:
            return None
        path = self._stack_path(index, stars=True)
        try:
            from astropy.io import fits
            hdu = fits.PrimaryHDU(np.asarray(stack, dtype=np.float32))
            wcss = result.get("wcs_by_group") or []
            if index < len(wcss) and wcss[index] is not None:
                hdu.header.update(wcss[index].to_header())
            hdu.header["NS_STACK"] = (
                "stars", "the stars are points")
            # the other half of the pair: the object's stack, in the same
            # folder, so whichever one is opened the tab knows the other
            hdu.header["NS_PAIR"] = self._stack_name(index)
            name = (self._context() or {}).get("object_name")
            if name:
                hdu.header["OBJECT"] = str(name)
            hdu.header["NS_NOBS"] = (int(index) + 1,
                                     "observation of the visit")
            groups = result.get("groups") or []
            if index < len(groups):
                hdu.header["NS_NFRAM"] = (
                    int(groups[index][1] - groups[index][0]),
                    "frames in this stack")
            if self._run_id is not None:
                hdu.header["NS_RUN"] = (int(self._run_id),
                                        "the astrometry run it belongs to")
            # the same band data the object's stack carries (minus the
            # brightness: here the object is a trail), so the heading of the
            # star stack says the same date, "N × T s" and motion
            self._write_frame_meta(hdu.header, result, index)
            self._write_band_cards(hdu.header, result, index, stars=True)
            hdu.writeto(str(path), overwrite=True)
        except Exception as err:
            logger.warning("star stack write failed: %s", err)
            return None
        if self._view is not None:
            notify = getattr(host_of(self), "notify_saved", None)
            if callable(notify):
                notify([str(path)], "stack")
        return path

    def _on_blink(self):
        # @return: None. The figure is the honest way to look at a run
        #          whose observations do not agree: the eye catches a panel
        #          that is not the same sky far faster than a table. The
        #          menu picks the flavour; the work lives in _write_blink so
        #          it can be exercised without a modal menu.
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        act_gif = menu.addAction(self.tr("Blink (animated GIF)"))
        act_png = menu.addAction(self.tr("Montage (still PNG)"))
        chosen = menu.exec(self.btn_blink.mapToGlobal(
            self.btn_blink.rect().bottomLeft()))
        if chosen is None:
            return
        self._write_blink("gif" if chosen is act_gif else "png")

    def _write_blink(self, fmt):
        # @args: fmt - "gif" (blinking) or "png" (still montage)
        # @return: the written path, or None
        result = self._result or {}
        import numpy as np
        stacks = result.get("stacks") or []
        qs = result.get("qs") or []
        boxes = result.get("boxes") or []
        images, centers, labels = [], [], []
        for i, (stack, _rep) in enumerate(stacks):
            if stack is None or i >= len(qs):
                continue
            box = boxes[i] if i < len(boxes) else (0, 0, 0, 0)
            cx = qs[i][0] - box[0]
            cy = qs[i][1] - box[1]
            # the figure follows the app's screen orientation (data flipped
            # vertically): a blink that is upside down against the main
            # view is a blink nobody trusts
            images.append(np.flipud(np.asarray(stack, dtype=np.float32)))
            centers.append((cx, stack.shape[0] - 1 - cy))
            labels.append(self.tr("Obs. %1").replace("%1", str(i + 1)))
        if not images:
            return None
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from ..core.viz import sequence_view
        folder = None
        ask = getattr(host_of(self), "export_folder", None)
        if callable(ask):
            try:
                folder = ask()
            except Exception:
                folder = None
        import tempfile
        base = Path(folder) if folder else Path(tempfile.gettempdir())
        path = base / (self._stack_name(0).rsplit("_obs", 1)[0]
                       + "_observations." + fmt)
        try:
            sequence_view.centered_sequence(images, centers, path, fmt=fmt,
                                            label=labels)
        except Exception as err:
            logger.warning("blink figure failed: %s", err)
            self._say(self.tr("The blink figure could not be written:")
                      + f" {err}")
            return None
        if self._view is not None:
            notify = getattr(host_of(self), "notify_saved", None)
            if callable(notify):
                notify([str(path)], "sequence")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self._say(self.tr("Blink figure written:") + f" {path.name}")
        return path

    # ------------------------------------------------------ measurement

    def _fill_points(self):
        # The two ways per group (D7) and their contrast (D16): the Δ
        # column is the separation between the stack's position and the
        # per-frame one; a disagreement is flagged in its own column,
        # never chosen in silence.
        # @return: None
        from ..core import coords
        tbl = self.tbl_points
        points = self._result.get("points") or []
        mids = self._result.get("mids") or []
        tbl.setRowCount(len(points))
        for i, (sp, fp, flags) in enumerate(points):
            delta = ""
            if fp is not None and not math.isnan(fp.ra):
                cosd = max(math.cos(math.radians(sp.dec)), 1e-6)
                dra = (sp.ra - fp.ra) * cosd * 3600.0
                ddec = (sp.dec - fp.dec) * 3600.0
                delta = f"{math.hypot(dra, ddec):.2f}"
            warn = ", ".join(self._flag_text(f) for f in (flags or []))
            cells = (str(sp.group_index + 1),
                     self._t_mid_text(mids[i] if i < len(mids) else None),
                     coords.ra_deg_to_hms(sp.ra) if not math.isnan(sp.ra)
                     else "–",
                     coords.dec_deg_to_dms(sp.dec) if not math.isnan(sp.dec)
                     else "–",
                     delta,
                     f"{sp.snr:.1f}" if sp.snr else "–",
                     f"{sp.mag:.3f}" if sp.mag is not None else "–",
                     warn)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled)
                if col == 4:
                    item.setToolTip(self.tr(
                        "Separation between the stack measurement and the "
                        "per-frame one (the same centroid recipe on both)"))
                if col == 7 and text:
                    item.setToolTip(self.tr(
                        "The two measurements disagree: the point is "
                        "flagged, nothing is chosen in silence"))
                tbl.setItem(i, col, item)

    def _flag_text(self, flag):
        # @args: flag - a measurement flag from core/astrometry
        # @return: its human text (literal tr() strings so lupdate sees
        #          them; an unknown flag passes through, never hidden)
        if flag == "disagree":
            return self.tr("The two measurements disagree")
        if flag == "no_frame_centroid":
            return self.tr("No per-frame centroid")
        return str(flag)

    def _fill_check(self):
        # The verdict in plain language (D25/D29): available or not,
        # blocked or not, and the numbers behind it. Find_Orb missing is
        # SAID, never faked; without a reference nothing is blocked.
        # @return: None
        check = self._result.get("check")
        if check is None:
            return
        if not check.available:
            if str(check.note).startswith("Find_Orb is not configured"):
                text = self.tr(
                    "Find_Orb is not configured: the check is not "
                    "available. Set it up in Settings; meanwhile the "
                    "centred sequence and the submission floor are the "
                    "safety net.")
            else:
                text = self.tr("The check is not available:") \
                    + f" {check.note}"
        elif check.no_reference:
            text = self.tr(
                "No other observations to compare with: nothing is blocked "
                "(a real discovery has no reference); the centred sequence "
                "and the submission floor decide.")
        elif check.blocked:
            text = self.tr(
                "Our point is an outlier against the other observers: the "
                "report is blocked by default. Forcing it leaves the "
                "decision on record.")
        else:
            text = self.tr(
                "The check passes: our residual fits inside the published "
                "observations' dispersion.")
        if check.our_residual:
            text += " " + self.tr(
                "Our residual: %1″ / %2″ · %3 distinct observatories"
            ).replace("%1", f"{check.our_residual[0]:.2f}").replace(
                "%2", f"{check.our_residual[1]:.2f}").replace(
                "%3", str(check.n_stations))
        self.txt_check.setPlainText(text)
        # the verdict rides the block's header, so it is read WITHOUT
        # opening it (the block is folded by default)
        if not check.available:
            badge = self.tr("not available")
        elif check.no_reference:
            badge = self.tr("nothing to compare")
        elif check.blocked:
            badge = self.tr("blocked")
        else:
            badge = self.tr("passes")
        self._check_section.setHeaderBadge(badge)
        self.chk_force.setEnabled(bool(check.blocked))
        if not check.blocked and self.chk_force.isChecked():
            self.chk_force.setChecked(False)

    # ------------------------------------------------------------ report

    def _sync_report_buttons(self):
        # The report exists only after a complete run, and an outlier
        # blocks it unless the observer forces it (D25): the buttons SAY
        # that with their enabled state instead of failing on click.
        # @return: None
        result = self._result or {}
        ok = result.get("status") == "ok" and bool(result.get("points"))
        check = result.get("check")
        blocked = bool(check is not None and check.blocked
                       and not self.chk_force.isChecked())
        self.btn_report.setEnabled(ok and not blocked)
        self.btn_send_mpc.setEnabled(
            ok and not blocked
            and bool(self.txt_report.toPlainText().strip()))
        # the run's own undo (phase 8): enabled while there is a persisted
        # execution to take back. The door follows its buttons: a door that
        # opens onto a grey item is a lie (ADR-038).
        self.btn_undo.setEnabled(self._run_id is not None)
        from .widgets.door_menu import refresh_door
        refresh_door(self.btn_more)

    def _on_report(self):
        # The generator applies the submission floor itself (D26) and the
        # round trip through the validator (the generator that cannot pass
        # its own judge is our bug). The dropped groups are re-explained
        # here from the DATA, in the GUI's language: the core's notes are
        # internal English and never reach the user verbatim.
        # @return: None
        from ..core import mpc_astrometry
        ctx = self._context() or {}
        points = [sp for sp, _fp, _fl
                  in (self._result or {}).get("points") or []]
        if not points:
            self._say(self.tr("Measure the sequence first."))
            return
        fmt = self.cmb_format.currentData() or "ades"
        rep = mpc_astrometry.generate(points, fmt,
                                      str(config.get("mpc_code", "")),
                                      ctx.get("object_name") or "", config)
        self.txt_report.setPlainText(rep["text"])
        floor = float(config.get("astrometry_submit_snr", 20.0))
        notes = []
        for point in rep.get("dropped") or []:
            snr = getattr(point, "snr", None)
            g = str(getattr(point, "group_index", "?"))
            if snr is None:
                notes.append(self.tr(
                    "Observation %1 left out: no SNR was measured, so it "
                    "cannot be shown to clear the floor of %2").replace(
                        "%1", g).replace("%2", f"{floor:.0f}"))
            else:
                notes.append(self.tr(
                    "Observation %1 left out: SNR %2 is below the MPC "
                    "submission floor of %3 (a marginal detection risks a "
                    "false tracklet)").replace("%1", g).replace(
                        "%2", f"{float(snr):.1f}").replace(
                        "%3", f"{floor:.0f}"))
        validation = rep.get("validation") or {}
        if not validation.get("valid", True):
            notes.extend(str(e) for e in (validation.get("errors") or [])[:3])
        # The same notes BOX the run fills: the report's "left out and why"
        # is part of the same story, and a box has its own height and scroll
        # (a label grew or clipped). The pre-rename code shared it too; the
        # rename to txt_notes missed this spot and crashed on Generate.
        self.txt_notes.setVisible(bool(notes))
        if notes:
            self.txt_notes.setPlainText("\n".join("• " + n for n in notes))
        self._sync_report_buttons()
        kept = len(rep.get("kept") or [])
        self._say(self.tr("Report generated: %1 observations kept."
                          ).replace("%1", str(kept)))

    def _on_send_mpc(self):
        # The report lands in the visit's MPC paste box; ADR-022's
        # validator there has the last word (the round trip is the point:
        # our own output goes through the same judge as a pasted report).
        # @return: None
        text = self.txt_report.toPlainText().strip()
        if not text:
            self._say(self.tr("Generate the report first."))
            return
        dlg = host_of(self)
        send = getattr(dlg, "send_to_mpc_block", None)
        if callable(send) and send(text):
            self._say(self.tr(
                "Report sent to the visit's MPC block: its validator has "
                "the last word before saving."))
        else:
            self._say(self.tr(
                "The visit window is not open: open the visit to send the "
                "report to its MPC block."))
