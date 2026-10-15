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
says which master each piece uses AND WHY a piece could not be found (the
criterion that failed and its numbers), runs gui/workers.CalibrationWorker
with progress and Cancel, and exports the calibrated copies only when the
checkbox says so (D6: calibration works in memory, writing hundreds of
FITS is explicit).

ADR-061 rev: the library and the policy (the vignetting model switch, the
temperature tolerance) live in SETTINGS, their single home; this tab only
READS them and applies them, and its "Calibration settings…" button is the
deep link there. The tab used to carry a second copy of the library and of
the switch, which is how the switch the observer touched came to be one the
stack never read.
"""

import logging
from pathlib import Path

from PySide6.QtWidgets import QWidget

from ..config import config
from . import theme
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
        self.chk_export = self._ui.chk_export
        self.btn_calibrate = self._ui.btn_calibrate
        self.prg_calib = self._ui.prg_calib
        # ADR-061 rev: the library and the policy are in Settings now; this
        # tab reads them and its button is the door there.
        self.btn_settings = self._ui.btn_settings
        self.btn_settings.clicked.connect(self._on_settings)
        # D6: exporting calibrated copies is explicit; the checkbox's
        # default is the setting's, so the choice survives sessions
        self.chk_export.setChecked(bool(config.get("calib_export", False)))
        self.chk_export.toggled.connect(
            lambda on: config.set("calib_export", 1 if on else 0))
        self.btn_calibrate.clicked.connect(self._on_calibrate)
        self._btn_label = self.btn_calibrate.text()
        # The model is written as a product of the visit and can be opened in
        # the editor's own viewer, because the observer's criterion for "this
        # is the vignetting and not a map of the stars" is looking at it.
        self.btn_model = self._ui.btn_model
        self.btn_model.clicked.connect(self._on_see_model)
        self._model_file = None
        # ADR-061 rev: this project's OWN masters. Building runs off the GUI
        # thread (a night of frames is a lot of pixels) and can delete the
        # originals once the masters exist; adopting links another project's
        # master into this one without copying the file.
        self.btn_build_masters = self._ui.btn_build_masters
        self.btn_build_masters.clicked.connect(self._on_build_masters)
        self.btn_adopt_master = self._ui.btn_adopt_master
        self.btn_adopt_master.clicked.connect(self._on_adopt_master)
        self.chk_build_delete = self._ui.chk_build_delete
        self.chk_build_share = self._ui.chk_build_share
        self._build_worker = None

    def _vignette_model_on(self):
        # @return: True when Settings asks for a vignetting model when the
        #          library has no flat for the filter. It is the SAME key
        #          the stack reads: one policy, one home (ADR-061 rev).
        return bool(config.get("calib_vignette_model", False))

    def _master_kind_label(self, kind):
        # @args: kind - one of core.calibration.KINDS
        # @return: its name in the observer's language: the kinds are
        #          different arithmetics, not synonyms.
        return {"bias": self.tr("Bias"), "dark": self.tr("Dark"),
                "flat": self.tr("Flat")}.get(kind, kind)

    @staticmethod
    def _num(value):
        # @args: value - a number from a note, or None
        # @return: it formatted for a sentence ("-" when it is not known)
        if value is None:
            return "–"
        try:
            return f"{float(value):g}"
        except (TypeError, ValueError):
            return str(value)

    def _on_settings(self):
        # @return: None. The library and the policy live in Settings
        #          (ADR-061 rev): this is the deep link, and it lands on the
        #          Measurement page, where the calibration library is.
        opener = getattr(host_of(self), "open_settings_page", None)
        if callable(opener):
            try:
                opener("page_measurement")
                return
            except Exception as err:                       # noqa: BLE001
                logger.warning("opening the settings failed: %s", err)
        self._say(self.tr(
            "The master library lives in Settings, under Measurement."))

    # ------------------------------------------------- this project's masters

    def _on_build_masters(self):
        # @return: None. Builds masters from a folder of calibration frames
        #          and files them under THIS project (or shared, if the box
        #          is checked). The build runs off the GUI thread; the
        #          originals go only when the box is checked and the run is
        #          confirmed, and only after each master is written AND
        #          indexed, so a failed build leaves them where they were.
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from ..core import calibration
        from ..core.db import db
        from .workers import CalibrationBuildWorker, hold
        project_id = (self._context() or {}).get("pid")
        if project_id is None:
            self._say(self.tr("Open the editor from a project to build its "
                              "masters."))
            return
        if self._build_worker is not None and self._build_worker.isRunning():
            return
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("Build masters from a folder of calibration "
                          "frames"), "")
        if not folder:
            return
        files = sorted(
            str(p) for p in Path(folder).rglob("*")
            if p.is_file() and p.suffix.lower() in (".fits", ".fit", ".fts"))
        if not files:
            self._say(self.tr("No FITS frames in that folder."))
            return
        delete = self.chk_build_delete.isChecked()
        shared = self.chk_build_share.isChecked()
        plan = self.tr("Build the masters from %1 frames?").replace(
            "%1", str(len(files)))
        if delete:
            plan += " " + self.tr(
                "The original frames will be DELETED once each master is "
                "written and indexed.")
        else:
            plan += " " + self.tr("The original frames are kept.")
        plan += " " + (self.tr("The masters will be shared with every "
                               "project.") if shared
                       else self.tr("The masters will belong to this "
                                    "project."))
        if QMessageBox.question(self, self.tr("Build masters"), plan) \
                != QMessageBox.Yes:
            return
        self._build_worker = hold(CalibrationBuildWorker(
            files, str(calibration.calib_root()), db, project_id=project_id,
            shared=shared, delete_sources=delete))
        self._build_worker.progress.connect(self._on_build_progress)
        self._build_worker.finished.connect(self._on_build_finished)
        self._build_worker.failed.connect(self._on_build_failed)
        self.btn_build_masters.setEnabled(False)
        self._say(self.tr("Building masters…"))
        self._build_worker.start()

    def _on_build_progress(self, done, total, kind):
        # @args: done/total - groups finished, kind - the one just built
        # @return: None
        self._say(self.tr("Building masters… %1 of %2").replace(
            "%1", str(done)).replace("%2", str(total)))

    def _on_build_finished(self, result):
        # @args: result - core.calibration.build_masters' dict
        # @return: None. A group with a SINGLE frame is called out: it is a
        #          copy of that frame, not an average. The recipe is re-read
        #          because a master the tab could not find may exist now.
        self.btn_build_masters.setEnabled(True)
        self._build_worker = None
        built = result.get("built", [])
        if built:
            bits = [self.tr("Built %1 masters.").replace(
                "%1", str(len(built)))]
            if any(item.get("single") for item in built):
                bits.append(self.tr(
                    "A group had a single frame, so its master is a copy of "
                    "that frame and not an average."))
            skipped = result.get("skipped", [])
            if skipped:
                bits.append(self.tr("%1 frames were left out: they are not "
                                    "calibration frames.").replace(
                                        "%1", str(len(skipped))))
            self._say("  ".join(bits))
        else:
            self._say(self.tr("Nothing was built."))
        for kind, why in result.get("errors", [])[:2]:
            self._say(f"✕ {kind}: {why}")
        self._sync_context()

    def _on_build_failed(self, message):
        # @args: message - the worker's error (internal English)
        # @return: None
        self.btn_build_masters.setEnabled(True)
        self._build_worker = None
        self._say(self.tr("The build failed:") + f" {message}")

    def _on_adopt_master(self):
        # @return: None. Links a master another project built into THIS
        #          project: a second row on the same file, never a copy. The
        #          list leaves out what this project can already use, so
        #          adopting the same master twice is not offered.
        from PySide6.QtWidgets import QInputDialog
        from ..core import calibration, project
        from ..core.db import db
        project_id = (self._context() or {}).get("pid")
        if project_id is None:
            self._say(self.tr("Open the editor from a project to use a "
                              "master."))
            return
        # What this project can already use, BY FILE: an adopted master is a
        # new ROW on the same file, so comparing ids would offer the same
        # master again and again.
        mine = {m.path for m in calibration.list_masters(
            db, project_id=project_id)}
        candidates = [m for m in calibration.list_masters(db)
                      if m.project_id is not None
                      and m.project_id != project_id and m.path not in mine]
        if not candidates:
            self._say(self.tr("There is no other project's master to use."))
            return
        owners, labels = {}, []
        for m in candidates:
            if m.project_id not in owners:
                p = project.get(db, m.project_id) or {}
                owners[m.project_id] = (p.get("object_name")
                                        or f"#{m.project_id}")
            labels.append(f"{Path(m.path).name}  ·  "
                          f"{self._master_kind_label(m.kind)}  ·  "
                          f"{owners[m.project_id]}")
        choice, ok = QInputDialog.getItem(
            self, self.tr("Use another project's master"),
            self.tr("The file is not copied: this project gets its own link "
                    "to it."), labels, 0, False)
        if not ok:
            return
        ref = candidates[labels.index(choice)]
        if calibration.adopt_master(db, ref.id, project_id) is not None:
            self._say(self.tr("Added %1 to this project.").replace(
                "%1", Path(ref.path).name))
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
        # between frames (the calibrate worker) or between groups (the
        # build) and wait() gives it a bounded time to land.
        # @return: None
        for attr in ("_worker", "_build_worker"):
            worker = getattr(self, attr, None)
            if worker is not None and worker.isRunning():
                worker.cancel()
                worker.wait(5000)
            setattr(self, attr, None)

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

    def _say(self, text, level=None):
        # @args: text - the status line's text ("" hides it), level - "info"
        #        | "warn" | "error" (None: inferred from the ⚠ the message
        #        already carries)
        # @return: None. The panel keeps its own line as the record and the
        #          window's line gets it too (U4), both in the level's
        #          colour. This tab also reports FAILURES, and "The
        #          calibration failed:" carries no ⚠, so it used to reach
        #          the window as plain news: the level is explicit here.
        text = str(text)
        if level is None:
            level = "warn" if text.startswith("⚠") else "info"
        self.lbl_status.setVisible(bool(text))
        self.lbl_status.setText(text)
        theme.paint_level(self.lbl_status, level)
        if self._status_hook is not None and text:
            self._status_hook(text, level)

    # ------------------------------------------------------------ recipe

    def clear_session(self):
        # A different project or visit is a different session (reported
        # 2026-10-15): the previous visit's recipe line must not travel to
        # the next one. The library is consulted live, so there is nothing
        # else to drop.
        # @return: None
        self._ctx_paths = None
        self._recipe = None
        self.lbl_recipe.setText(self.tr(
            "Open the editor from a visit to see its recipe."))
        self._set_concerns([])

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
            self._set_concerns([])
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
            self._set_concerns([])
            return
        meta = calibration.meta_from_header(header)
        tol = float(config.get("calib_temp_tol_c", 3.0))
        # The project's OWN masters are preferred and the shared ones are the
        # fallback; the recipe then SAYS when it used a shared one (ADR-061
        # rev), so "why is it not using my dark" has an answer.
        recipe = calibration.resolve_recipe(db, meta, tol_c=tol,
                                            project_id=ctx.get("pid"))
        self._recipe = recipe
        self.lbl_recipe.setText(self._recipe_text(meta, recipe))
        self._set_concerns(self._concern_lines(recipe))

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
        elif self._vignette_model_on():
            parts.append(self.tr("vignetting model from the frames"))
        else:
            parts.append(self.tr("no flat: the vignetting stays"))
        return " · ".join(parts)

    def _recipe_text(self, meta, recipe):
        # @args: meta - the light's metadata, recipe - the resolved Recipe
        # @return: the summary in plain language: which master each piece
        #          uses (by file name) or what is missing
        def _v(value):
            return "–" if value is None else str(value)

        def _mark(ref):
            # @args: ref - a chosen master
            # @return: its file name, with "(shared)" when the project that
            #          ASKED does not own it: those pixels come from the
            #          common library or from another project's nights, and
            #          the observer has to know which (ADR-061 rev).
            name = Path(ref.path).name
            if recipe.project_id is not None and ref.project_id is None:
                name += " " + self.tr("(shared)")
            return name

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
            lines.append(kind + ": " + _mark(recipe.offset))
        else:
            lines.append(self.tr(
                "Offset: missing (no dark or bias in the library)"))
        if recipe.flat is not None:
            line = self.tr("Flat:") + " " + _mark(recipe.flat)
            if recipe.flat_offset is not None:
                line += " " + self.tr("(offset removed: %1)").replace(
                    "%1", _mark(recipe.flat_offset))
            else:
                line += " " + self.tr(
                    "(no dark at its exposure or bias: the flat keeps its "
                    "own pedestal)")
            lines.append(line)
        elif self._vignette_model_on():
            lines.append(self.tr(
                "Flat: none in the library; a vignetting model will be "
                "built from the frames"))
        else:
            lines.append(self.tr(
                "Flat: missing for this filter (the vignetting stays)"))
        return "\n".join(lines)

    def _concern_lines(self, recipe):
        # @args: recipe - the resolved Recipe
        # @return: [(level, "• line")]: the warnings and the reasons, each
        #          WITH WHAT IT IS, translated and deduplicated. The
        #          warnings are the short, stable sentences (a piece is
        #          missing) and they are WARNINGS; the notes carry WHY a
        #          master that IS in the library was left out, with the
        #          numbers, and they are NOTES. The level is what lets the
        #          block be read by colour instead of sentence by sentence
        #          (ADR-061 rev).
        lines, seen = [], set()
        for warning in recipe.warnings:
            text = "• " + self._warning_text(warning)
            if text not in seen:
                seen.add(text)
                lines.append(("warn", text))
        for note in getattr(recipe, "notes", None) or []:
            text = self._note_text(note)
            if text and ("• " + text) not in seen:
                seen.add("• " + text)
                lines.append(("info", "• " + text))
        return lines

    def _set_concerns(self, pairs):
        # @args: pairs - [(level, "• line")] from _concern_lines or the run
        # @return: None. The block is painted with ONE COLOUR PER LINE, so a
        #          missing piece reads as a warning and a "why it was left
        #          out" as a note without reading the sentence (asked for
        #          2026-10-15: the text is long and hard to read). The plain
        #          text is kept beside the HTML in warnings_text(), so what
        #          the observer copies and the tests read is the same text
        #          it always was.
        import html as _html
        self._warnings_text = "\n".join(text for _level, text in pairs)
        if not pairs:
            self.lbl_warnings.setText("")
            return
        out = ['<span style="color:{0}">{1}</span>'.format(
            theme.level_colour(level), _html.escape(text))
            for level, text in pairs]
        self.lbl_warnings.setText("<br>".join(out))

    def warnings_text(self):
        # @return: the block's text, plain, with no markup ("" when there is
        #          nothing to say)
        return getattr(self, "_warnings_text", "")

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
        if text.startswith("already calibrated"):
            return self.tr(
                "The frame already carries NightScribe's calibration, so "
                "the recipe was not applied again (a second dark would be "
                "subtracted twice)")
        return text

    def _note_text(self, note):
        # @args: note - a core Recipe note dict (what, reason, master,
        #        value, wanted, tol, days)
        # @return: WHY that master was left out, with the numbers, in the
        #          observer's language, or None when the note is not one
        #          this tab knows (an unknown reason passes through the
        #          warning, never hidden)
        what = self._master_kind_label(note.get("what") or "")
        master = note.get("master") or ""
        reason = note.get("reason")
        if reason == "temperature":
            return self.tr(
                "There is a %1 (%2) in the library, but its sensor "
                "temperature is out of tolerance: %3 °C against %4 °C "
                "(tolerance %5 °C). A dark carries the thermal current, "
                "so one from another temperature is not the same dark."
            ).replace("%1", what).replace("%2", master).replace(
                "%3", self._num(note.get("value"))).replace(
                "%4", self._num(note.get("wanted"))).replace(
                "%5", self._num(note.get("tol")))
        if reason == "exposure":
            return self.tr(
                "There is a %1 (%2) in the library, but at %3 s: a dark is "
                "only valid at the light's own exposure (%4 s)."
            ).replace("%1", what).replace("%2", master).replace(
                "%3", self._num(note.get("value"))).replace(
                "%4", self._num(note.get("wanted")))
        if reason == "filter":
            return self.tr(
                "There is a %1 (%2) in the library, but for filter %3; "
                "these lights are in %4. A flat is per filter."
            ).replace("%1", what).replace("%2", master).replace(
                "%3", self._num(note.get("value"))).replace(
                "%4", self._num(note.get("wanted")))
        if reason == "camera":
            return self.tr(
                "There is a %1 (%2) in the library, but for another camera "
                "(%3); these lights are from %4."
            ).replace("%1", what).replace("%2", master).replace(
                "%3", self._num(note.get("value"))).replace(
                "%4", self._num(note.get("wanted")))
        if reason == "gain":
            return self.tr(
                "There is a %1 (%2) in the library, but at gain %3; these "
                "lights were taken at gain %4. A dark carries the level, "
                "so the gain is part of its match."
            ).replace("%1", what).replace("%2", master).replace(
                "%3", self._num(note.get("value"))).replace(
                "%4", self._num(note.get("wanted")))
        if reason == "age":
            return self.tr(
                "The flat (%1) is %2 days older than these lights: the "
                "train's dust moves, so a mote may have appeared or gone. "
                "It is used anyway."
            ).replace("%1", master).replace(
                "%2", self._num(note.get("days")))
        return None

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
        # The model is a product of the visit like any other, and the whole
        # point of writing it is being able to LOOK at it.
        want_model = self._vignette_model_on()
        if want_model:
            flat_path = str(base / "vignette_model.fits")
        from ..core.db import db
        from .workers import CalibrationWorker, hold
        self.prg_calib.setVisible(True)
        self.prg_calib.setRange(0, len(paths))
        self.prg_calib.setValue(0)
        self.btn_calibrate.setText(self.tr("Cancel"))
        self.btn_model.setEnabled(False)
        self._model_file = None
        self._worker = hold(CalibrationWorker(
            paths, db, export_dir, config,
            vignette_model=want_model,
            flat_path=flat_path,
            project_id=(self._context() or {}).get("pid")))
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
        self._say(self.tr("The calibration failed:") + f" {message}",
                  "error")

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
        # says nothing. The recipe's own notes (WHY a master was left out)
        # go with them, so the reason does not disappear after a run.
        pairs, seen = [], set()
        for _path, report in reports:
            for warning in (getattr(report, "warnings", None) or []):
                text = "• " + self._warning_text(warning)
                if text not in seen:
                    seen.add(text)
                    pairs.append(("warn", text))
        # the recipe's own NOTES come with them, so the reason a master was
        # left out does not disappear after a run (the warnings are already
        # in the reports, one per frame)
        if self._recipe is not None:
            for level, text in self._concern_lines(self._recipe):
                if level == "info" and text not in seen:
                    seen.add(text)
                    pairs.append((level, text))
        self._set_concerns(pairs)
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
        skipped = sum(1 for _p, r in reports
                      if getattr(r, "already", False))
        text = self.tr("Calibrated %1 frames (%2 exported).").replace(
            "%1", str(len(reports) - skipped)).replace(
            "%2", str(len(written)))
        if skipped:
            # A frame that already carried the marker was left alone: saying
            # "calibrated" for it would be a small lie the observer can act
            # on (the export was run twice over the same folder).
            text += " " + self.tr(
                "%1 already carried NightScribe's calibration and were "
                "left as they were.").replace("%1", str(skipped))
        self._say(text)
        # What the vignetting model was made of, so the observer can judge it
        # instead of trusting it: how many frames the sky was sampled from,
        # on what grid, and how many tiles the robust fit kept.
        info = payload.get("vignette_model") or {}
        if info.get("median_adu"):
            note = self.tr(
                "Vignetting model from %1 frames, %2-pixel tiles "
                "(%3 of %4 tiles kept).").replace(
                    "%1", str(info.get("n_frames"))).replace(
                    "%2", str(info.get("tile_px"))).replace(
                    "%3", str(info.get("n_kept"))).replace(
                    "%4", str(info.get("n_tiles")))
            # The pedestal is not a detail: without a dark/bias the model is
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
                    "No dark/bias master: the pedestal stays in the model, "
                    "so its shape is compressed and only part of the "
                    "vignetting is corrected. Index a bias for this camera.")
            if info.get("note"):
                note += " " + self.tr("Warning:") + " " + info["note"]
            # the model is a warning when its pedestal is missing (it then
            # corrects only part of the vignetting), a note otherwise
            self._say(note, "warn" if (off.get("n_missing")
                                       or info.get("note")) else "info")
        # The model is registered to the visit like any other product and the
        # door to look at it is opened.
        model_file = payload.get("model_file")
        self._model_file = str(model_file) if model_file else None
        self.btn_model.setEnabled(bool(self._model_file))
        if self._model_file:
            notify = getattr(host_of(self), "notify_saved", None)
            if callable(notify):
                try:
                    notify([self._model_file], "fits")
                except Exception as err:                       # noqa: BLE001
                    logger.warning("model register failed: %s", err)

    def _on_see_model(self):
        # @return: None. Opens the model in the editor's own viewer. The
        # observer's criterion for "this is the vignetting and not a map of
        # the stars" is looking at it and seeing a smooth surface, and that
        # is not something a note can replace.
        path = self._model_file
        if not path:
            self._say(self.tr(
                "No vignetting model has been built for this visit yet: run "
                "the calibration with the model box checked in Settings."))
            return
        opener = getattr(host_of(self), "open_plate", None)
        if callable(opener):
            opener(str(path))
        else:
            self._say(self.tr("The model is at %1").replace(
                "%1", str(path)))
