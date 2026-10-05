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
        self.lbl_notes = self._ui.lbl_notes
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
        self.lbl_check = self._ui.lbl_check
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
            "snr": self._wrap_section(
                "sec_snr_content", self.tr("Expected SNR per observation"),
                "trackstack_snr_open"),
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
                box.addWidget(widget)
            elif item.layout() is not None:
                box.addItem(item.layout())
        area = QScrollArea(self)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(inner)
        lay.addWidget(area)
        # the four combination methods of core/track_stack (D11), with the
        # setting's default on top
        self.cmb_method.addItem(self.tr("Sum"), "sum")
        self.cmb_method.addItem(self.tr("Mean"), "mean")
        self.cmb_method.addItem(self.tr("Median"), "median")
        self.cmb_method.addItem(self.tr("Sigma-clipped"), "sigma")
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
        # @return: None. The empty containers say nothing: an empty grid and
        #          a blank strip are noise in a 380 px column, so they
        #          appear WITH the result and go away with it.
        self.lbl_points_title.setVisible(flag)
        self.tbl_points.setVisible(flag)
        self._thumbs.setVisible(flag)

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
            return
        if not recipe:
            self.lbl_recipe.setText(self.tr(
                "Photometry recipe: the editor's defaults (open the "
                "Photometry tab to see or change them)."))
            return
        band = recipe.get("band") or self.tr("the comps' own band")
        self.lbl_recipe.setText(self.tr(
            "Photometry recipe: %1 · apertures %2 · sky %3").replace(
                "%1", str(band)).replace(
                "%2", self._recipe_radii_text(recipe)).replace(
                "%3", str(recipe.get("sky") or "median")))

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
        self.lbl_status.setText(text or "")

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
            self.lbl_notes.setVisible(False)
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
            phot_enabled=self.chk_brightness.isChecked())
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, stage, done, total):
        # @args: stage - the worker's stage key, done/total - inside that
        #        stage
        # @return: None. The human text is a literal self.tr() table (the
        #          way TonightWorker's phases do it, CONTRIBUTING rule 5).
        self.prg_stack.setRange(0, max(1, total))
        self.prg_stack.setValue(done)
        text = self._stage_text(stage)
        if text:
            self._say(text + (f" ({done}/{total})" if total > 1 else ""))

    def _stage_text(self, key):
        # @args: key - one of TrackStackWorker's stage keys
        # @return: the human text for the status line
        return {
            "solve": self.tr("Solving the reference frame…"),
            "register": self.tr("Registering the frames…"),
            "base": self.tr("Stacking the whole sequence…"),
            "detect": self.tr("Looking for the object…"),
            "sweep": self.tr("Sweeping the velocity…"),
            "groups": self.tr("Stacking each observation…"),
            "measure": self.tr("Measuring the positions…"),
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
            self._paint_not_detected()
            self._persist_run(self._result)
            return
        self._paint_run()
        self._persist_run(self._result)

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
        self.lbl_notes.setVisible(True)
        self.lbl_notes.setText(text)
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
        self.lbl_notes.setVisible(bool(notes))
        self.lbl_notes.setText("\n".join("• " + n for n in notes))
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
        failed = int(self._result.get("n_failed") or 0)
        note = self.tr("Sequence stacked: %1 observations measured."
                       ).replace("%1", str(n))
        if failed:
            note += " " + self.tr(
                "%1 frames could not be aligned and were left out."
                ).replace("%1", str(failed))
        self._say(note)

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
                "object", "track & stack: the stars are trails")
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

    def _stack_path(self, index):
        # @args: index - the group's index
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
        return base / self._stack_name(index)

    def _stack_name(self, index):
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
            ut = datetime(1858, 11, 17) + timedelta(days=float(mjd))
            stamp = "_" + ut.strftime("%Y%m%dT%H%M%S")
        return f"{slug}_obs{index + 1}{stamp}.fits"

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
        self.lbl_check.setText(text)
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
        self.lbl_notes.setVisible(bool(notes))
        if notes:
            self.lbl_notes.setText("\n".join("• " + n for n in notes))
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
