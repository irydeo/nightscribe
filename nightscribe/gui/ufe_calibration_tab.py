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
        self._recipe = None        # the resolved Recipe of the first frame
        self._status_hook = None   # the window's single line (U4)
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
        # ADR-061 rev: the library is FILLED from here. It used to be only in
        # Settings, so this tab could report what was missing and nothing
        # else; an observer with real flats (measured: 150 of them for one
        # night) had no way to put them in from where the recipe is read.
        self.cmb_master_kind = self._ui.cmb_master_kind
        self.btn_master_add = self._ui.btn_master_add
        self.lbl_master_status = self._ui.lbl_master_status
        from ..core import calibration
        for kind in calibration.KINDS:
            self.cmb_master_kind.addItem(self._master_kind_label(kind), kind)
        self.btn_master_add.clicked.connect(self._on_master_add)
        # D6: exporting calibrated copies is explicit; the checkbox's
        # default is the setting's, so the choice survives sessions
        self.chk_export.setChecked(bool(config.get("calib_export", False)))
        self.chk_export.toggled.connect(
            lambda on: config.set("calib_export", 1 if on else 0))
        # P5: the pseudo-flat is the calibration's OWN policy, and this tab is
        # its single home (the stack and every other pipeline read the same
        # key). The switch has to WRITE it: reading it and never saving it is
        # how the checkbox came to look like it did nothing.
        self.chk_pseudo_flat.setChecked(
            bool(config.get("calib_pseudo_flat", False)))
        self.chk_pseudo_flat.toggled.connect(self._on_pseudo_flat)
        self.btn_calibrate.clicked.connect(self._on_calibrate)
        self._btn_label = self.btn_calibrate.text()
        # ADR-069: the flat is written as a product of the visit and can be
        # opened in the editor's own viewer, because the observer's criterion
        # for "this is a flat" is looking at it and seeing no star in it.
        self.btn_flat = self._ui.btn_flat
        self.btn_flat.clicked.connect(self._on_see_flat)
        self._flat_file = None

    def _on_pseudo_flat(self, on):
        # @args: on - the new state of the policy switch
        # @return: None. The key is shared: the astrometry hint and the next
        #          stack read it, so the choice has to outlive the session.
        config.set("calib_pseudo_flat", 1 if on else 0)
        self._sync_context()      # the recipe line's flat row changes

    def _master_kind_label(self, kind):
        # @args: kind - one of core.calibration.KINDS
        # @return: its name in the observer's language: the four kinds are
        #          four different arithmetics, not synonyms.
        return {"bias": self.tr("Bias"), "dark": self.tr("Dark"),
                "dark_flat": self.tr("Dark of the flats"),
                "flat": self.tr("Flat")}.get(kind, kind)

    def _on_master_add(self):
        # @return: None. The host opens the file dialog and indexes what it
        #          gets (the tab never touches the database, like every other
        #          panel); the answer comes back as words and the recipe is
        #          re-resolved, so the line above says what changed.
        ask = getattr(host_of(self), "add_masters", None)
        if not callable(ask):
            self.lbl_master_status.setText(self.tr(
                "This window has no library to write to."))
            return
        kind = self.cmb_master_kind.currentData() or "dark"
        try:
            text = ask(kind)
        except Exception as err:
            logger.warning("adding masters failed: %s", err)
            text = self.tr("The masters could not be indexed:") + f" {err}"
        self.lbl_master_status.setText(text or "")
        self._sync_context()

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

    def set_status_hook(self, fn):
        # @args: fn - callable(text, level) the window's single line listens
        #        with (U4), or None
        # @return: None
        self._status_hook = fn if callable(fn) else None

    def _say(self, text):
        # @args: text - the status line's text ("" hides it)
        # @return: None. The panel keeps its own line as the record and the
        #          window's line gets it too (U4).
        self.lbl_status.setVisible(bool(text))
        self.lbl_status.setText(text or "")
        if self._status_hook is not None and text:
            self._status_hook(str(text),
                              "warn" if str(text).startswith("⚠") else "info")

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
            self._recipe = None
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
            self._recipe = None
            self.lbl_recipe.setText(
                self.tr("The first frame could not be read:") + f" {err}")
            self.lbl_warnings.setText("")
            return
        meta = calibration.meta_from_header(header)
        tol = float(config.get("calib_temp_tol_c", 3.0))
        recipe = calibration.resolve_recipe(db, meta, tol_c=tol)
        self._recipe = recipe
        self.lbl_recipe.setText(self._recipe_text(meta, recipe))
        self.lbl_warnings.setText("\n".join(
            "• " + self._warning_text(w) for w in recipe.warnings))

    def has_masters(self):
        # Whether the library has anything that MATCHES this visit, asked by
        # the astrometry tab to decide its calibration default (ADR-061 rev):
        # with a dark or a flat for this camera and filter, applying the
        # calibration is what the measurement needs.
        # @return: True / False, or None when the recipe is not known yet (no
        #          visit armed, or the first frame could not be read): the
        #          caller leaves the calibration off rather than promising
        #          one nobody verified.
        recipe = self._recipe
        if recipe is None:
            return None
        return bool(recipe.offset is not None or recipe.flat is not None)

    def short_recipe(self):
        # One line saying what the calibration will DO to the pixels, for the
        # pipelines that opt in (the astrometry hint). It is built from the
        # SAME resolved recipe the tab shows, so the hint and the recipe
        # cannot disagree about what is missing or what stands in for it.
        # @return: the one-liner, in the GUI's language
        recipe = self._recipe
        if recipe is None:
            return self.tr("The visit's recipe is not known")
        parts = []
        if recipe.offset is not None:
            parts.append(self.tr("dark") if recipe.offset_kind == "dark"
                         else self.tr("bias"))
        else:
            parts.append(self.tr("no dark/bias"))
        if recipe.flat is not None:
            parts.append(self.tr("flat: %1").replace(
                "%1", Path(recipe.flat.path).name))
        elif self.chk_pseudo_flat.isChecked():
            parts.append(self.tr("pseudo-flat from the frames"))
        else:
            parts.append(self.tr("no flat: the vignetting stays"))
        return " · ".join(parts)

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
        elif self.chk_pseudo_flat.isChecked():
            lines.append(self.tr(
                "Flat: none in the library; a pseudo-flat will be built "
                "from the frames"))
        else:
            lines.append(self.tr(
                "Flat: missing for this filter (the vignetting stays)"))
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
        flat_path = None
        from .. import paths as paths_mod
        folder = None
        getter = getattr(host_of(self), "export_folder", None)
        if callable(getter):
            try:
                folder = getter()
            except Exception:
                folder = None
        base = Path(folder or paths_mod.data_dir())
        if self.chk_export.isChecked():
            export_dir = base / "calibrados"
        # The flat is a product of the visit like any other, and the whole
        # point of writing it is being able to LOOK at it (ADR-069).
        if self.chk_pseudo_flat.isChecked():
            flat_path = str(base / "pseudo_flat.fits")
        from ..core.db import db
        from .workers import CalibrationWorker, hold
        self.prg_calib.setVisible(True)
        self.prg_calib.setRange(0, len(paths))
        self.prg_calib.setValue(0)
        self.btn_calibrate.setText(self.tr("Cancel"))
        self.btn_flat.setEnabled(False)
        self._flat_file = None
        self._worker = hold(CalibrationWorker(
            paths, db, export_dir, config,
            pseudo_flat=self.chk_pseudo_flat.isChecked(),
            flat_path=flat_path))
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
            # P5 rev (ADR-069): what the flat is made of, so the observer can
            # judge it instead of trusting it. The stars are masked before the
            # statistic and their pixels are filled from the sky around them;
            # the two numbers that say whether that worked are how much was
            # filled and how far the flat still deviates over those pixels.
            parts = []
            if info.get("n_sources") is not None:
                parts.append(self.tr("%1 sources masked").replace(
                    "%1", str(info["n_sources"])))
            if info.get("filled_pct") is not None:
                parts.append(self.tr("%1 % of the pixels filled").replace(
                    "%1", f"{float(info['filled_pct']):.2f}"))
            if info.get("hot_px"):
                parts.append(self.tr(
                    "%1 hot pixels kept in the flat (the division removes "
                    "them)").replace("%1", str(info["hot_px"])))
            if info.get("verify_pct") is not None:
                parts.append(self.tr(
                    "deviation over the masked ones: %1 %").replace(
                        "%1", f"{float(info['verify_pct']):.2f}"))
            if parts:
                note += " " + "; ".join(parts) + "."
            # The pedestal is not a detail: without a dark/bias the flat is
            # built from frames that carry it, its shape comes out compressed
            # and it corrects only part of the vignetting (measured: 44 % on
            # 1 s twilight frames). It is said, not hidden.
            off = info.get("offset") or {}
            if off.get("n_applied"):
                note += " " + self.tr(
                    "Built with the offset removed (%1).").replace(
                        "%1", ", ".join(off.get("applied") or []))
            elif off.get("n_missing"):
                note += " " + self.tr(
                    "No dark/bias master: the pedestal stays in the flat, so "
                    "its shape is compressed and only part of the vignetting "
                    "is corrected. Index a bias for this camera.")
            if info.get("note"):
                if info.get("kind") == "vignette_model":
                    # the smooth model is not a caveat, it is what was
                    # applied: it says what it is and what it does not
                    # correct (ADR-061 rev)
                    note += " " + info["note"]
                else:
                    note += " " + self.tr("Warning:") + " " + info["note"]
            self._say(note)
        # The flat is registered to the visit like any other product and the
        # door to look at it is opened (ADR-069).
        flat_file = payload.get("flat_file")
        self._flat_file = str(flat_file) if flat_file else None
        self.btn_flat.setEnabled(bool(self._flat_file))
        if self._flat_file:
            notify = getattr(host_of(self), "notify_saved", None)
            if callable(notify):
                try:
                    notify([self._flat_file], "fits")
                except Exception as err:                       # noqa: BLE001
                    logger.warning("flat register failed: %s", err)

    def _on_see_flat(self):
        # @return: None. Opens the flat in the editor's own viewer. The
        # observer's criterion for "this is a flat" is looking at it and
        # seeing that no star is in it, and that is not something a note can
        # replace.
        path = self._flat_file
        if not path:
            self._say(self.tr(
                "No flat has been built for this visit yet: run the "
                "calibration with the pseudo-flat box checked."))
            return
        opener = getattr(host_of(self), "open_plate", None)
        if callable(opener):
            opener(str(path))
        else:
            self._say(self.tr("The flat is at %1").replace(
                "%1", str(path)))
