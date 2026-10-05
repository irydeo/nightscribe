############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Calibration tab module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Calibration tab (astrometry plan, phase 7 / ADR-061, D4): the
visit's recipe against the master library, in plain language. The
structure, texts and tooltips live in ui/ufe_calibration_tab.ui
(ADR-005); this module resolves the recipe for the visit's first frame,
says which master each piece uses (or what is missing), runs
gui/workers.CalibrationWorker with progress and Cancel, and exports the
calibrated copies only when the checkbox says so (D6: calibration works
in memory, writing hundreds of FITS is explicit).
"""

import logging
from pathlib import Path

from PySide6.QtWidgets import QWidget

from ..config import config
from .ui_loader import adopt_ui
from .ufe_host import host_of

logger = logging.getLogger("nightscribe.gui.ufe_calibration_tab")


class UfeCalibrationTab(QWidget):
    # @args: state - the shared UfeImageState (this tab never touches the
    #        plate's pixels: the visit calibrates from its own paths),
    #        lang - "es" | "en", parent - widget

    def __init__(self, state, lang="es", parent=None):
        super().__init__(parent)
        self._state = state
        self._lang = lang
        self._worker = None        # CalibrationWorker while it runs
        self._ctx_paths = None     # the visit's frames (or None)
        self._build_ui()
        self._sync_context()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # The structure is the Designer file's (ADR-005); this method
        # aliases the widgets and wires the signals.
        self._ui = adopt_ui(self, "ufe_calibration_tab")
        self.lbl_recipe = self._ui.lbl_recipe
        self.lbl_warnings = self._ui.lbl_warnings
        self.lbl_status = self._ui.lbl_status
        self.chk_pseudo_flat = self._ui.chk_pseudo_flat
        self.chk_export = self._ui.chk_export
        self.btn_calibrate = self._ui.btn_calibrate
        self.prg_calib = self._ui.prg_calib
        # D6: exporting calibrated copies is explicit; the checkbox's
        # default is the setting's, so the choice survives sessions
        self.chk_export.setChecked(bool(config.get("calib_export", False)))
        # P5: the pseudo-flat is opt-in, and the choice survives sessions
        self.chk_pseudo_flat.setChecked(
            bool(config.get("calib_pseudo_flat", False)))
        self.btn_calibrate.clicked.connect(self._on_calibrate)
        self._btn_label = self.btn_calibrate.text()

    # ------------------------------------------------------- host wiring

    def set_active(self, flag):
        # @args: flag - True when the dialog hands this tab the stage
        # @return: None. The recipe is re-read on entering: a master added
        #          in Settings (or a different visit) changes it.
        if flag:
            self._sync_context()

    def refresh_context(self):
        # Called by the dialog when the host sets (or clears) the
        # astrometry hook, so the tab does not wait for a stage change.
        # @return: None
        self._sync_context()

    def shutdown(self):
        # The worker must not outlive the workbench: a QThread destroyed
        # while it runs aborts the whole application. Cancel stops it
        # between frames and wait() gives it a bounded time to land.
        # @return: None
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)
        self._worker = None

    def _context(self):
        # @return: the visit context {"pid", "session_id", "paths",
        #          "object_name"} the host hooked, or None (ad-hoc open)
        dlg = host_of(self)
        getter = getattr(dlg, "astrometry_context", None)
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception as err:
            logger.warning("astrometry hook failed: %s", err)
            return None

    def _say(self, text):
        # @args: text - the status line's text ("" hides it)
        # @return: None
        self.lbl_status.setVisible(bool(text))
        self.lbl_status.setText(text or "")

    # ------------------------------------------------------------ recipe

    def _sync_context(self):
        # The recipe shown is the FIRST frame's: a visit is one camera,
        # one filter and one temperature, so its header speaks for all of
        # them. The library is consulted live (resolve_recipe never
        # raises: what is missing becomes a warning in plain language).
        # @return: None
        ctx = self._context() or {}
        paths = tuple(ctx.get("paths") or ())
        running = self._worker is not None and self._worker.isRunning()
        self.btn_calibrate.setEnabled(bool(paths) and not running)
        if not paths:
            self._ctx_paths = None
            self.lbl_recipe.setText(self.tr(
                "Open the editor from a visit to see its recipe."))
            self.lbl_warnings.setText("")
            return
        self._ctx_paths = paths
        from ..core import calibration
        from ..core.db import db
        try:
            header = calibration.read_header(paths[0])
        except Exception as err:
            self.lbl_recipe.setText(
                self.tr("The first frame could not be read:") + f" {err}")
            self.lbl_warnings.setText("")
            return
        meta = calibration.meta_from_header(header)
        tol = float(config.get("calib_temp_tol_c", 3.0))
        recipe = calibration.resolve_recipe(db, meta, tol_c=tol)
        self.lbl_recipe.setText(self._recipe_text(meta, recipe))
        self.lbl_warnings.setText("\n".join(
            "• " + self._warning_text(w) for w in recipe.warnings))

    def _recipe_text(self, meta, recipe):
        # @args: meta - the light's metadata, recipe - the resolved Recipe
        # @return: the summary in plain language: which master each piece
        #          uses (by file name) or what is missing
        def _v(value):
            return "–" if value is None else str(value)
        lines = [self.tr(
            "Camera %1 · gain %2 · %3 °C · exposure %4 s · filter %5"
        ).replace("%1", _v(meta.get("camera"))).replace(
            "%2", _v(meta.get("gain"))).replace(
            "%3", _v(meta.get("temp_c"))).replace(
            "%4", _v(meta.get("exptime_s"))).replace(
            "%5", _v(meta.get("filter")))]
        if recipe.offset is not None:
            kind = self.tr("Dark") if recipe.offset_kind == "dark" \
                else self.tr("Bias")
            lines.append(kind + ": " + Path(recipe.offset.path).name)
        else:
            lines.append(self.tr(
                "Offset: missing (no dark or bias in the library)"))
        if recipe.flat is not None:
            line = self.tr("Flat:") + " " + Path(recipe.flat.path).name
            if recipe.flat_offset is not None:
                line += " " + self.tr("(offset removed: %1)").replace(
                    "%1", Path(recipe.flat_offset.path).name)
            else:
                line += " " + self.tr(
                    "(no dark-flat: the flat keeps its own pedestal)")
            lines.append(line)
        else:
            lines.append(self.tr("Flat: missing for this filter"))
        return "\n".join(lines)

    def _warning_text(self, warning):
        # @args: warning - a core recipe warning (internal English)
        # @return: its GUI text. The known ones are re-said through
        #          literal tr() strings (lupdate cannot see a dynamic map,
        #          and the user reads their own language); an unknown one
        #          passes through rather than being hidden.
        text = str(warning)
        if text.startswith("no dark at this exposure"):
            return self.tr(
                "No dark at this exposure: the bias was subtracted, so "
                "the thermal current stays in the frame")
        if text.startswith("no dark or bias"):
            return self.tr(
                "No dark or bias in the library: the pedestal and the "
                "thermal current stay in the frame")
        if text.startswith("no flat for this filter"):
            return self.tr(
                "No flat for this filter: the flat residual is not "
                "corrected (it matters for the magnitude, little for the "
                "centroid)")
        return text

    # --------------------------------------------------------------- run

    def _on_calibrate(self):
        # The run button, and its Cancel while the worker runs. The
        # export folder is the project's (the dialog's export_folder
        # hook); without a hook the app data folder catches the copies.
        # @return: None
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._say(self.tr(
                "Cancelling: the calibration stops after the frame it is "
                "applying; the copies already exported are kept."))
            return
        paths = list(self._ctx_paths or ())
        if not paths:
            self._say(self.tr(
                "No visit with frames: open the editor from a visit."))
            return
        export_dir = None
        if self.chk_export.isChecked():
            from .. import paths as paths_mod
            folder = None
            getter = getattr(host_of(self), "export_folder", None)
            if callable(getter):
                try:
                    folder = getter()
                except Exception:
                    folder = None
            export_dir = Path(folder or paths_mod.data_dir()) / "calibrados"
        from ..core.db import db
        from .workers import CalibrationWorker
        self.prg_calib.setVisible(True)
        self.prg_calib.setRange(0, len(paths))
        self.prg_calib.setValue(0)
        self.btn_calibrate.setText(self.tr("Cancel"))
        self._worker = CalibrationWorker(
            paths, db, export_dir, config,
            pseudo_flat=self.chk_pseudo_flat.isChecked())
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, done, total):
        # @args: done/total - frames calibrated
        # @return: None
        self.prg_calib.setRange(0, max(1, total))
        self.prg_calib.setValue(done)

    def _run_ended(self):
        # @return: None. The button comes back from Cancel and the bar
        #          hides; the button stays disabled without a visit.
        self.btn_calibrate.setText(self._btn_label)
        self.prg_calib.setVisible(False)
        self.btn_calibrate.setEnabled(bool(self._ctx_paths))

    def _on_failed(self, message):
        # @args: message - the worker's error (internal English, like the
        #        other workers' failed signal)
        # @return: None
        self._run_ended()
        self._say(self.tr("The calibration failed:") + f" {message}")

    def _on_finished(self, payload):
        # @args: payload - CalibrationWorker's result dict
        # @return: None
        self._run_ended()
        payload = payload if isinstance(payload, dict) else {}
        reports = payload.get("reports") or []
        written = payload.get("written") or []
        if payload.get("status") == "cancelled":
            self._say(self.tr("Cancelled after %1 frames.").replace(
                "%1", str(len(reports))))
            return
        # the warnings of EVERY frame, deduplicated: a visit repeats its
        # recipe, and the same missing master said three hundred times
        # says nothing
        seen, lines = set(), []
        for _path, report in reports:
            for warning in (getattr(report, "warnings", None) or []):
                if warning not in seen:
                    seen.add(warning)
                    lines.append("• " + self._warning_text(warning))
        self.lbl_warnings.setText("\n".join(lines))
        if written:
            # the copies register to the visit like any other product
            # (the dialog's save hook owns the database)
            notify = getattr(host_of(self), "notify_saved", None)
            if callable(notify):
                try:
                    notify(written, "fits")
                except Exception as err:
                    logger.warning(
                        "calibrated export register failed: %s", err)
        self._say(self.tr("Calibrated %1 frames (%2 exported).").replace(
            "%1", str(len(reports))).replace("%2", str(len(written))))
        # P5: what the pseudo-flat was, and whether it could be trusted: a
        # flat built from frames that were not dithered still carries the
        # stars, and saying so beats leaving a wrong flat on the frames
        info = payload.get("pseudo_flat") or {}
        if info.get("median_adu"):
            note = self.tr(
                "Pseudo-flat built from %1 frames (median %2 ADU).").replace(
                    "%1", str(info.get("n_frames"))).replace(
                    "%2", f"{float(info['median_adu']):.0f}")
            if info.get("note"):
                note += " " + self.tr("Warning:") + " " + info["note"]
            self._say(note)
