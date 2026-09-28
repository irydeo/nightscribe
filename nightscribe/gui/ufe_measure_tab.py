############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Measure tab (ADR-044, phases G2+H)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE's Measure tab: calibrated single-plate photometry. One click
on a star or supernova measures it (core/photometry: centroid, aperture,
sigma-clipped sky, honest guards), measures the Compare tab's sequence
on the same plate, and calibrates against their catalog magnitudes: ZP
by median with a MAD-based error, optionally with a colour term fitted
on the comps' B-V (H1), the target's error from the CCD equation when
the gain is known plus scintillation, the colour fit and the flat
residual in an honest total (H5), and a plain-language panel that says
exactly what was used and what was refused.

Phase H extras (docs/PRECISION.es.md): sky by median or by a fitted
plane on cores (H2a), apertures that follow the measured seeing (H3),
the real saturation ceiling from SATURATE or the ccd_saturate setting
(H4), the check star as the measurement's own traffic light (H6), and
optional host-galaxy subtraction through the blink's aligned PS1
reference, comp-scaled so the stars vanish (H2b). One measurement is one
click (D4); the exports are files (CSV one row, AAVSO EFF), the plate on
disk is never touched (D6).
"""

import logging
import math
from pathlib import Path

import numpy as np
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (QFileDialog, QWidget, QMessageBox,
                               QGraphicsEllipseItem)

from ..core import coords, fits_meta, photometry, photometry_export, \
    series_measure, stretch
from ..viz import palette
from .ufe_advanced_dialog import UfeAdvancedDialog
from .ui_loader import adopt_ui, drop_in
from .widgets.lightcurve_widget import LightCurveChart

logger = logging.getLogger("nightscribe.gui.ufe_measure_tab")

_C_AP = palette.ACCENT   # the shared amber marker family the UFE wears
_C_ANN = "#6ec1ff"     # sky annulus rings in the cool accent
_C_COMP = "#4dd0e1"    # used comps ring in the compare tab's cyan


def _decimate(points, max_points=1500):
    # Display-only decimation (D36): a huge series must not stall the
    # chart. A stride keeps the shape; flagged points are never dropped.
    # @args: points - chart point dicts, max_points - display budget
    # @return: the (possibly shortened) list
    if len(points) <= max_points:
        return points
    step = len(points) / float(max_points)
    out = [points[int(i * step)] for i in range(max_points)]
    seen = {id(p) for p in out}
    out += [p for p in points if p.get("flags") and id(p) not in seen]
    return out


class UfeMeasureTab(QWidget):
    pick_clicks = True   # clicks mark things: the dialog hands us
                           # the pick cursor + snapping reticle on stage
    # @args: state - the shared UfeImageState, lang - "es" | "en",
    #        view - the UfeImageView, compare_tab - the Compare tab the
    #        sequence is read from (D5)

    def __init__(self, state, lang="es", view=None, compare_tab=None,
                 parent=None):
        super().__init__(parent)
        self._state = state
        self._lang = lang
        self._view = view
        self._compare = compare_tab
        self._active = False         # owns the view's clicks right now
        self._on_stage = False       # the Photometry tab is on stage and
                                     # this section is visible (armed or
                                     # not): its overlays may be drawn
        self._project_attached = False     # point hook set on the dialog
        self._items = []             # aperture + comps overlays
        self._last = None            # the last measurement bundle
        self._band = None            # the band of the last plate (the
                                     # combo is refilled per measurement,
                                     # ADR-047 keeps a stable pick across
                                     # plate re-opens)
        # where the target B-V came from: "assumed" (the 0.00 default),
        # "catalog" (the field star under the click), "project" (the host
        # record), "manual" (a hand edit, which wins until the next click)
        self._bv_source = "assumed"
        self._sub_worker = None      # BlinkWorker while subtracting
        self._diff = None            # difference image (work frame,
                                     # plate orientation) or None
        self._diff_scale = 1.0       # plate px per diff-frame px
        self._pair_obs = None        # the work-frame observed frame
                                     # (comps calibrate on it while
                                     # subtracting: never mix scales)
        self._last_suggestions = []  # the Suggest button's reasons
        self._build_ui()
        state.image_loaded.connect(self._on_image_loaded)
        if view is not None:
            view.scene_clicked.connect(self._on_scene_clicked)
        self._on_image_loaded()
        # ADR-047: the recipe as the .ui shipped it, captured once the
        # widgets exist: what the state reset applies back (.ui = the
        # single source of the defaults, no mirror in Python).
        self._ui_defaults = self.capture_state()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # The structure is the Designer file's (ADR-005); this method
        # aliases the widgets, sizes the aperture spins from
        # core/photometry's defaults and wires every signal.
        self._ui = adopt_ui(self, "ufe_measure_tab")
                                            # over: no wrapper margins
        self.lbl_status = self._ui.lbl_status
        self.cmb_band = self._ui.cmb_band

        # The recipe knobs live one click open (ADR-044 rev): the daily
        # flow is band, apertures, Suggest; the rest (sky model,
        # sigma-clip, seeing, colour term, host subtraction) opens in
        # its own small non-modal window; the tab keeps the public
        # attributes and wires every signal itself.
        self._advanced = UfeAdvancedDialog(self)
        self.btn_suggest = self._ui.btn_suggest
        self.btn_suggest.clicked.connect(self._on_suggest)
        self.spn_rap = self._spin(self._ui.spn_rap, photometry.R_AP,
                                  1.0, 20.0)
        self.spn_rin = self._spin(self._ui.spn_rin, photometry.R_ANN_IN,
                                  2.0, 40.0)
        self.spn_rout = self._spin(self._ui.spn_rout,
                                   photometry.R_ANN_OUT, 3.0, 60.0)
        self._radii_manual = False   # True once the observer edits a spin
        for spn in (self.spn_rap, self.spn_rin, self.spn_rout):
            spn.valueChanged.connect(self._on_radii_edited)
        self.btn_advanced = self._ui.btn_advanced
        self.btn_advanced.clicked.connect(self._open_advanced)
        # the public attributes the tests and the measure flow pin
        self.chk_sigmaclip = self._advanced.chk_sigmaclip
        self.chk_seeing = self._advanced.chk_seeing
        self.chk_color = self._advanced.chk_color
        self.chk_subtract = self._advanced.chk_subtract
        self.cmb_sky = self._advanced.cmb_sky
        self.spn_target_bv = self._advanced.spn_target_bv
        # every measuring control re-measures the live point at once
        self.cmb_sky.currentIndexChanged.connect(
            lambda _i: self._remeasure())
        self.chk_sigmaclip.toggled.connect(lambda _c: self._remeasure())
        self.chk_seeing.toggled.connect(self._on_seeing_toggled)
        self.chk_color.toggled.connect(lambda _c: self._remeasure())
        self.spn_target_bv.valueChanged.connect(self._on_bv_edited)
        self.chk_subtract.toggled.connect(self._on_subtract_toggled)

        # The result log is plain text in a scrollable editor: a long
        # report (comps, guards, verdict) must never squash the tab.
        self.lbl_result = self._ui.lbl_result

        self.btn_csv = self._ui.btn_csv
        self.btn_csv.clicked.connect(lambda: self._export("csv"))
        self.btn_eff = self._ui.btn_eff
        self.btn_eff.clicked.connect(lambda: self._export("eff"))
        # ADR-044: the editor opened from a project registers the point
        # there (source “measure”); ad-hoc opens hide this button.
        self.btn_save_project = self._ui.btn_save_project
        self.btn_save_project.clicked.connect(self._on_save_project)
        # ADR-047: the plate's two resets, visible only when the dialog
        # is opened from a project (same rule as the save button).
        self.btn_reset_state = self._ui.btn_reset_state
        self.btn_reset_state.clicked.connect(self._on_reset_state)
        self.btn_reset_points = self._ui.btn_reset_points
        self.btn_reset_points.clicked.connect(self._on_reset_points)

        # series block (series plan, phase 5): hidden unless the dialog was
        # opened from a visit (D8). The compact curve is our custom widget
        # (ADR-005: a .ui placeholder swapped for the real one).
        self.grp_series = self._ui.grp_series
        self.lbl_series_hint = self._ui.lbl_series_hint
        self.btn_series = self._ui.btn_series
        # P1 #12: the run button doubles as the Cancel while a series is
        # measuring; the .ui ships the run label (ADR-047: no mirror of it
        # in Python) and it comes back to it when the run ends.
        self._btn_series_label = self.btn_series.text()
        self.btn_series.clicked.connect(self._on_measure_series)
        self.btn_series_undo = self._ui.btn_series_undo
        self.btn_series_undo.clicked.connect(self._on_series_undo)
        self.btn_series_exoclock = self._ui.btn_series_exoclock
        self.btn_series_exoclock.clicked.connect(self._on_series_exoclock)
        self.btn_series_help = self._ui.btn_series_help
        self.btn_series_help.clicked.connect(self._open_series_docs)
        self.lbl_series_frames = self._ui.lbl_series_frames
        self.lbl_series_cadence = self._ui.lbl_series_cadence
        self.prg_series = self._ui.prg_series
        self.chk_series_live = self._ui.chk_series_live
        self.chk_series_live.toggled.connect(self._on_series_live_toggled)
        self._live_worker = None
        self._live_points = []
        self.chart_series = LightCurveChart()
        drop_in(self.grp_series.layout(), self._ui.wgt_series_chart,
                self.chart_series)
        self._series_worker = None
        self._series_run_id = None
        self._series_result = None
        self._series_cfg = None
        self._series_cfg_dict = None
        self._series_attached = False
        # the Advanced window stays a dumb container: its restore button
        # is wired here, where the defaults live
        self._advanced.btn_restore.clicked.connect(
            self._restore_advanced_defaults)

    def _spin(self, sb, value, lo, hi):
        # Sizes one aperture spin (px, half-pixel steps) from
        # core/photometry's defaults: the widget itself is the .ui's.
        # @return: the given spin, configured
        sb.setRange(lo, hi)
        sb.setValue(value)
        return sb

    def _open_advanced(self):
        # @return: the recipe window rises, non-modal, so measuring
        # keeps going while it is open
        self._advanced.show()
        self._advanced.raise_()
        self._advanced.activateWindow()

    # ------------------------------------------------------- activation

    def set_active(self, flag, keep_overlays=False):
        # Only the section that owns the stage takes the clicks, and on
        # stage it also gets the pick cursor and the snapping reticle.
        # The OVERLAYS follow the Photometry tab's stage instead
        # (self._on_stage): both sections stay visible, so a disarmed
        # Measure half keeps its rings and a re-measure still paints.
        # @args: keep_overlays - the Sequence section is taking over the
        #        stage: our markers and result stay on the chart (with
        #        the clicks disarmed), they are dropped on a full leave
        self._active = bool(flag)
        if not self._active:
            if keep_overlays:
                # disarmed but on stage (the visit deep link can land
                # here without this section ever being armed)
                self._on_stage = True
                return
            self._on_stage = False
            self._drop_items()
            if self._diff is not None and self._view is not None:
                self._view.set_frame_override(None)
        else:
            self._on_stage = True
            if self._diff is not None and self._view is not None:
                self._view.set_frame_override(self._display_diff)
            if self._last is not None:
                self._draw_measurement()

    def set_project_attached(self, flag):
        # The dialog exposes it: the host opened the editor from a project
        # and will register the calibrated point. The button shows only
        # then, and its enabled state still follows the measurement.
        # @args: flag - True when a point hook is set on the dialog
        self._project_attached = bool(flag)
        self.btn_save_project.setVisible(self._project_attached)
        if not self._project_attached:
            self.btn_save_project.setEnabled(False)
        elif self._last is not None and self._last.get("mag") is not None:
            self.btn_save_project.setEnabled(True)

    # -------------------------------------------------- resets (ADR-047)

    def set_reset_attached(self, flag):
        # ADR-047: the dialog carries reset hooks (it was opened from a
        # project): the two plate resets show. Same rule as the save
        # button: not attached, not visible.
        # @args: flag - True when the dialog's state/points hooks are set
        self.btn_reset_state.setVisible(bool(flag))
        self.btn_reset_points.setVisible(bool(flag))

    def ui_defaults(self):
        # ADR-047: the recipe the .ui shipped with, for the state reset
        # (the dialog applies it back on the tab).
        # @args: none
        # @return: a copy of the captured defaults dict
        return dict(self._ui_defaults)

    def _on_reset_state(self):
        # ADR-047: the working state back to the editor's defaults: the
        # recipe, the stretch, the sequence. No confirmation: nothing on
        # disk is lost, the saved state is just overwritable.
        dlg = self.window()
        f = getattr(dlg, "reset_state_local", None)
        if not callable(f) or not f():
            self.lbl_status.setText(self.tr(
                "Load a plate first: there is no state to reset."))
            return
        if dlg.notify_reset_state():
            self.lbl_status.setText(self.tr("Plate state reset."))
        else:
            self.lbl_status.setText(self.tr(
                "Plate state reset locally: this plate is not "
                "registered in the project, so there was no saved "
                "state to clear."))

    def _on_reset_points(self):
        # ADR-047: destructive for the light curve: every measured point
        # saved on THIS plate is dropped. The plan requires a
        # confirmation here, and the hook fires only after a yes.
        dlg = self.window()
        if not dlg.state.has_image:
            self.lbl_status.setText(self.tr(
                "Load a plate first: there are no plate points to reset."))
            return
        box = QMessageBox.question(
            self, self.tr("Reset the points of this plate"),
            self.tr(
                "Delete every measurement point saved on this plate?\n"
                "They leave the light curve; the CSV files on disk are\n"
                "not touched."),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if box != QMessageBox.Yes:
            return
        if dlg.notify_reset_points():
            self.lbl_status.setText(self.tr(
                "The plate's measurement points were deleted."))
        else:
            self.lbl_status.setText(self.tr(
                "No measurement points saved on this plate."))

    def _on_save_project(self):
        # ADR-044: the host (Main window) set a point hook when it opened
        # us from a project; it saves this point under that project
        # (source “measure”, the visit attached) and refreshes the curve.
        # @return: None; the outcome shows in the status line.
        if self._last is None or self._last.get("mag") is None:
            self.lbl_status.setText(
                self.tr("Nothing to save yet: measure a point first."))
            return
        meta = fits_meta.meta_from_header(self._state.header or {})
        mjd = meta.get("mjd")
        if mjd is None:
            self.lbl_status.setText(self.tr(
                "This plate has no observation date in its header: the "
                "point cannot be dated, so it cannot be saved."))
            return
        payload = {
            "mjd": float(mjd),
            "filter": (meta.get("filter")
                       or self._last.get("band") or "V"),
            "mag": self._last["mag"],
            "err": self._last.get("err"),
            "name": meta.get("object"),
            # ADR-047: the plate this point belongs to, so the host ties
            # it to its project_files row and saves the plate's state.
            "path": self._state.path,
        }
        dlg = self.window()
        if not dlg or not dlg.notify_point(payload):
            self.lbl_status.setText(
                self.tr("Could not save the point in the project."))
            return
        self.lbl_status.setText(self.tr(
            "Point saved in the project: it is on the light curve and "
            "counts for the campaign summary."))

    def shutdown(self):
        # Nothing timer-driven here; the subtraction worker may run, and a
        # running series is asked to stop (its points stay, D18).
        if self._series_worker is not None \
                and self._series_worker.isRunning():
            self._series_worker.cancel()
            self._series_worker.wait(3000)
        if self._live_worker is not None and self._live_worker.isRunning():
            self._live_worker.cancel()
            self._live_worker.wait(3000)
        self._series_worker = None
        self._live_worker = None
        self._sub_worker = None

    # ------------------------------------------------------------- state

    def _on_image_loaded(self):
        # A fresh plate invalidates the measurement and any subtraction
        # (the aligned reference belongs to the old plate); the seeing
        # auto-scale is free to size the apertures for this plate again.
        self._radii_manual = False
        self._last = None
        self._drop_items()
        self._drop_subtraction()
        self.lbl_result.setText("–")
        self.btn_csv.setEnabled(False)
        self.btn_eff.setEnabled(False)
        self.btn_save_project.setEnabled(False)
        self.setEnabled(self._state.has_image)
        self.lbl_status.setText("")

    # -------------------------------------------------------- measuring

    def _on_scene_clicked(self, scene_pt):
        if not self._active or not self._state.has_image:
            return
        if self._state.wcs is None:
            self.lbl_status.setText(self.tr(
                "The plate has no WCS: the comparison stars cannot be "
                "located. Solve it with «Solve astrometry…»."))
            return
        entries = self._sequence()
        if not entries:
            self.lbl_status.setText(self.tr(
                "No comparison sequence yet: build one above with "
                "«Build the sequence…»."))
            return
        self._last_suggestions = []     # a new target: stale reasons go
        col, row = self._state.scene_to_data(scene_pt.x(), scene_pt.y())
        self._prefill_bv_from_field(col, row)
        self._measure(col, row, entries)

    def _field_match(self, col, row):
        # The cross-match behind the panel's field line and the B-V
        # pre-fill: the Compare tab's field star nearest the plate point.
        # @args: col, row - plate pixels
        # @return: (star, separation in arcsec), or (None, None)
        if self._compare is None or self._state.wcs is None:
            return None, None
        getter = getattr(self._compare, "nearest_field_star", None)
        if not callable(getter):
            return None, None
        try:
            ra, dec = self._state.wcs.pixel_to_sky(col, row)
            return getter(ra, dec)
        except Exception:
            return None, None

    def _prefill_bv_from_field(self, col, row):
        # A click that lands on a catalogued field star IS that star:
        # its B-V pre-fills the colour term (an assumed 0.00 silently
        # biases red stars when the term matters). No match: the spin
        # keeps whatever it had (project, hand edit, or the default).
        star, _sep = self._field_match(col, row)
        if star is None or star.get("bv") is None:
            return
        self.spn_target_bv.blockSignals(True)
        try:
            self.spn_target_bv.setValue(float(star["bv"]))
        except (TypeError, ValueError):
            pass
        self.spn_target_bv.blockSignals(False)
        self._bv_source = "catalog"

    def _on_bv_edited(self, _value):
        # A hand edit owns the colour until the next catalogued click.
        self._bv_source = "manual"
        self._remeasure()

    def _sequence(self):
        # @return: the Compare tab's entries, or [] when absent/empty
        if self._compare is None:
            return []
        try:
            return self._compare.entries()
        except Exception:
            return []

    def prefill(self, bv=None):
        # The host object carries data the Measure tab uses: for now the
        # target's B-V when the record knows it (variables from VSX), so
        # the colour term applies with the right colour out of the box.
        # @args: bv - B-V of the target, or None to leave the spin alone
        if bv is not None:
            self.spn_target_bv.blockSignals(True)
            try:
                self.spn_target_bv.setValue(float(bv))
                self._bv_source = "project"
            except (TypeError, ValueError):
                pass
            self.spn_target_bv.blockSignals(False)

    # ----------------------------------------------------- state (ADR-047)

    def capture_state(self):
        # The recipe, as plain JSON (ADR-047): band, the aperture
        # triple, the manual flag, the advanced switches, the sky
        # method and the target B-V. Read-only: nothing here moves a
        # widget.
        # @return: the dict the dialog stores alongside the plate
        return {
            "band": self.cmb_band.currentText() or None,
            "rap": float(self.spn_rap.value()),
            "rin": float(self.spn_rin.value()),
            "rout": float(self.spn_rout.value()),
            "radii_manual": bool(self._radii_manual),
            "sigmaclip": bool(self.chk_sigmaclip.isChecked()),
            "seeing": bool(self.chk_seeing.isChecked()),
            "color": bool(self.chk_color.isChecked()),
            "sky": self.cmb_sky.currentData() or "median",
            "target_bv": float(self.spn_target_bv.value()),
        }

    def apply_state(self, st):
        # Restores a saved recipe (ADR-047). Signals are blocked while
        # the widgets move: re-measures cannot fire there is no
        # point yet, and the seeing toggle must not reset the manual
        # radii we restore right after.
        # @args: st - capture_state dict (empty/None is a no-op)
        if not st:
            return
        band = st.get("band")
        if band:
            self.cmb_band.setCurrentText(str(band))
        for spn, key in ((self.spn_rap, "rap"),
                         (self.spn_rin, "rin"),
                         (self.spn_rout, "rout")):
            if st.get(key) is None:
                continue
            spn.blockSignals(True)
            spn.setValue(float(st[key]))
            spn.blockSignals(False)
        self._radii_manual = False
        for chk, key in ((self.chk_sigmaclip, "sigmaclip"),
                         (self.chk_seeing, "seeing"),
                         (self.chk_color, "color")):
            want = bool(st.get(key, False))
            if chk.isChecked() != want:
                chk.setChecked(want)
        sky = st.get("sky")
        if sky:
            row = self.cmb_sky.findData(sky)
            if row >= 0:
                self.cmb_sky.setCurrentIndex(row)
        if st.get("target_bv") is not None:
            self.spn_target_bv.blockSignals(True)
            try:
                self.spn_target_bv.setValue(float(st["target_bv"]))
            except (TypeError, ValueError):
                pass
            self.spn_target_bv.blockSignals(False)
        self._bv_source = "assumed"
        self._radii_manual = bool(st.get("radii_manual", False))

    def _on_seeing_toggled(self, checked):
        # Re-arming the checkbox hands the radii back to the seeing
        # measurement; disarming freezes them where they are.
        if checked:
            self._radii_manual = False
            self._remeasure()

    def _on_radii_edited(self, _value):
        # A hand edit wins over the seeing auto-scale until the next plate
        # (or until the checkbox is re-armed), and re-measures the current
        # point on the spot so the overlay and the panel never lag.
        self._radii_manual = True
        if self._last is not None:
            self._remeasure()

    def _on_suggest(self):
        # The Suggest button: proposes the radii for the current target
        # from its growth curve and its surroundings, applies them (the
        # click IS the observer's consent, so a manual setup yields), and
        # explains the reasons in the panel.
        if self._last is None or not self._state.has_image:
            self.lbl_status.setText(self.tr(
                "Measure the target first (a click on it)."))
            return
        data = self._state.data
        col, row = self._last["col"], self._last["row"]
        sug = photometry.suggest_apertures(data, col, row)
        # the suggestion is an explicit choice of radii: the seeing
        # auto-scale steps aside (the checkbox visibly turns off) and the
        # manual flag stays clear - this is not a hand edit either
        self.chk_seeing.setChecked(False)
        self._radii_manual = False
        for spn, v in ((self.spn_rap, sug["r_ap"]),
                       (self.spn_rin, sug["r_ann_in"]),
                       (self.spn_rout, sug["r_ann_out"])):
            spn.blockSignals(True)
            spn.setValue(round(v * 2) / 2)
            spn.blockSignals(False)
        self._last_suggestions = [r.get(self._lang, r["en"])
                                  for r in sug["reasons"]]
        self._remeasure()

    # --------------------------------------------------------- seeing

    def _remeasure(self):
        # Re-runs the current measurement with the current controls (the
        # aperture spins live-edit the result).
        if self._last is None or not self._state.has_image:
            return
        entries = self._sequence()
        self._measure(self._last["col"], self._last["row"], entries)

    def _apertures(self, entries):
        # H3: when the seeing checkbox is on, measure the comps' FWHM on
        # the plate and scale the radii; the spins follow so the numbers
        # stay visible and tweakable. A hand edit wins until the next
        # plate (the observer's radii are never stomped).
        if not self.chk_seeing.isChecked() or self._radii_manual:
            return (self.spn_rap.value(), self.spn_rin.value(),
                    self.spn_rout.value()), None
        positions = []
        for e in entries:
            try:
                col, row = self._state.wcs.sky_to_pixel(e["star"]["ra"],
                                                        e["star"]["dec"])
                positions.append((col, row))
            except Exception:
                continue
        sat = photometry.saturation_ceiling(self._state.header)
        fwhm = photometry.estimate_fwhm(self._state.data, positions,
                                        sat_adu=sat)
        r_ap, r_in, r_out = photometry.aperture_for_fwhm(fwhm)
        if fwhm is not None:
            for spn, v in ((self.spn_rap, r_ap), (self.spn_rin, r_in),
                           (self.spn_rout, r_out)):
                spn.blockSignals(True)
                spn.setValue(v)
                spn.blockSignals(False)
        return (r_ap, r_in, r_out), fwhm

    def _measure(self, col, row, entries):
        # Build the recipe from the widgets and Ajustes, run the core
        # single-plate function (phase 1 of the series plan: one recipe,
        # shared with the series engine), and paint the outcome.
        from ..config import config
        radii, fwhm = self._apertures(entries)
        if self._diff is not None:
            image, comp_image = self._diff, self._pair_obs
            comp_scale = self._diff_scale
        else:
            image, comp_image, comp_scale = self._state.data, None, 1.0
        cfg = photometry.PlateConfig(
            target_xy=(col, row), entries=entries,
            header=self._state.header, wcs=self._state.wcs,
            band=self.cmb_band.currentText() or self._band,
            radii=radii, fwhm=fwhm,
            sigmaclip=self.chk_sigmaclip.isChecked(),
            sky_mode=self.cmb_sky.currentData() or "median",
            color=self.chk_color.isChecked(),
            target_bv=self.spn_target_bv.value(),
            site_gain=config.get("ccd_gain"),
            site_ron=config.get("ccd_read_noise"),
            site_flat=config.get("flat_resid_mag", 0.007) or 0.007,
            site_saturate=config.get("ccd_saturate"),
            site_lon=config.get("lon"), site_lat=config.get("lat"),
            site_aperture_m=float(config.get("aperture_inches", 10.0))
            * 0.0254,
            site_height_m=float(config.get("height", 0) or 0.0),
            linear_adu=config.get("cam_linearity_adu"),
            site_dark=config.get("cam_dark_current_e_s"),
            comp_image=comp_image, comp_scale=comp_scale)
        res = photometry.measure_plate(image, cfg)
        if not res.ok:
            reason = (res.reason or {}).get(self._lang, "?")
            self.lbl_status.setText(reason)
            self._last = None
            self._drop_items()
            self.btn_csv.setEnabled(False)
            self.btn_eff.setEnabled(False)
            self.btn_save_project.setEnabled(False)
            return
        self.lbl_status.setText("")
        # keep the band combo in step with what the sequence carries
        if res.bands_avail:
            self.cmb_band.blockSignals(True)
            self.cmb_band.clear()
            self.cmb_band.addItems(res.bands_avail)
            self.cmb_band.setCurrentText(res.band)
            self.cmb_band.blockSignals(False)
        self._band = res.band
        self._last = {
            "result": res.target, "zp": res.zp, "mag": res.mag,
            "err": res.err_total, "err_internal": res.err_internal,
            "band": res.band, "used": res.used, "derived": res.derived,
            "inst_t": res.inst_t, "fwhm": res.fwhm, "radii": res.radii,
            "scint": res.scint, "check": res.check, "col": res.col,
            "row": res.row, "click": (col, row), "skipped": res.skipped,
            "bands_avail": res.bands_avail,
            "match": self._field_match(res.col, res.row),
            "sky_mode": res.sky_mode, "sigma_clip": res.sigma_clip,
        }
        self._fill_panel(res.band, len(entries), len(res.used),
                         res.skipped, res.derived, res.gain)
        self.btn_csv.setEnabled(res.mag is not None)
        self.btn_eff.setEnabled(res.mag is not None)
        # the project save tracks the result: a point without a magnitude
        # (only a check ratio) has nothing to register
        self.btn_save_project.setEnabled(res.mag is not None)
        self._draw_measurement()

    # ------------------------------------------------------------ series

    def set_series_attached(self, flag):
        # The dialog arms a series context hook only when the editor was
        # opened from a visit (D8): without a visit the whole block stays
        # hidden, and a running worker is cancelled on a detach.
        self._series_attached = bool(flag)
        self.grp_series.setVisible(self._series_attached)
        if not self._series_attached and self._series_worker is not None:
            self._series_worker.cancel()
        if not self._series_attached and self._live_worker is not None:
            self._live_worker.cancel()
            self._live_worker = None
            self.chk_series_live.blockSignals(True)
            self.chk_series_live.setChecked(False)
            self.chk_series_live.blockSignals(False)

    def _series_context(self):
        # @return: the visit context {"paths", "session_id", ...} the host
        #          hooked, or None (ad-hoc open)
        dlg = self.window()
        getter = getattr(dlg, "series_context", None)
        return getter() if callable(getter) else None

    def _series_target(self):
        # The target position on the open (reference) plate: the last
        # measured centroid, else the object's coordinates through the
        # plate's WCS (D17: no per-frame astrometry).
        # @return: (x, y) in plate pixels, or None
        if self._state.wcs is None:
            return None
        if self._last is not None and self._last.get("col") is not None:
            return (self._last["col"], self._last["row"])
        obj = getattr(self.window(), "object", lambda: None)()
        if obj and obj.get("ra") is not None and obj.get("dec") is not None:
            try:
                return self._state.wcs.sky_to_pixel(float(obj["ra"]),
                                                    float(obj["dec"]))
            except Exception:
                return None
        return None

    def _series_config(self, entries, target_xy):
        # Builds the engine config from the tab's widgets and Ajustes.
        from ..config import config
        sat = self._advanced.spn_saturate.value()
        return series_measure.SeriesConfig(
            wcs=self._state.wcs, target_xy=tuple(target_xy),
            comp_set=tuple(entries),
            band=self.cmb_band.currentText() or self._band,
            radii=(self.spn_rap.value(), self.spn_rin.value(),
                   self.spn_rout.value()),
            sigmaclip=self.chk_sigmaclip.isChecked(),
            sky_mode=self.cmb_sky.currentData() or "median",
            color=self.chk_color.isChecked(),
            target_bv=self.spn_target_bv.value(),
            site_gain=config.get("ccd_gain"),
            site_ron=config.get("ccd_read_noise"),
            site_flat=config.get("flat_resid_mag", 0.007) or 0.007,
            site_saturate=float(sat) if sat and sat > 0
            else config.get("ccd_saturate"),
            site_lon=config.get("lon"), site_lat=config.get("lat"),
            site_aperture_m=float(config.get("aperture_inches", 10.0))
            * 0.0254,
            site_height_m=float(config.get("height", 0) or 0.0),
            site_linear=config.get("cam_linearity_adu"),
            site_dark=config.get("cam_dark_current_e_s"),
            group_n=int(self._advanced.spn_group_n.value()),
            auto_aperture=self._advanced.chk_auto_aperture.isChecked(),
            detrend_policy=self._advanced.cmb_detrend.currentData()
            or "off")

    def _series_config_dict(self, cfg):
        # A JSON-safe echo of the config for the run row (audit trail).
        return {"band": cfg.band, "zp_mode": cfg.zp_mode,
                "detrend_policy": cfg.detrend_policy,
                "group_n": cfg.group_n,
                "auto_aperture": cfg.auto_aperture,
                "sigmaclip": cfg.sigmaclip, "sky_mode": cfg.sky_mode,
                "color": cfg.color, "target_bv": cfg.target_bv,
                "radii": list(cfg.radii) if cfg.radii else None,
                "target_xy": list(cfg.target_xy)}

    def _update_series_counter(self, context, points=None):
        n = len((context or {}).get("paths", []))
        txt = self.tr("Frames: {0}").format(n)
        if points is not None:
            txt = self.tr("Frames: {0} · points: {1}").format(
                n, len(points))
        self.lbl_series_frames.setText(txt)
        grp = int(self._advanced.spn_group_n.value())
        self.lbl_series_cadence.setText(
            self.tr("group {0} · cadence from the frames").format(grp))

    def _series_button_running(self, running):
        # P1 #12: while the worker measures, the run button IS the Cancel
        # (a long series must have a way out); it comes back to the .ui's
        # label when the run ends, cancelled or not.
        # @args: running - True while the series worker runs
        self.btn_series.setText(self.tr("Cancel") if running
                                else self._btn_series_label)
        self.btn_series.setEnabled(True)

    def _on_measure_series(self):
        # D8: from the visit's files; with no visit (or no sequence, or no
        # target) the status line says exactly what is missing. While the
        # worker runs this same button is the Cancel (P1 #12): the engine
        # stops between frames and answers "incomplete" with the points
        # measured so far (D18).
        if self._series_worker is not None \
                and self._series_worker.isRunning():
            self._series_worker.cancel()
            self.lbl_status.setText(self.tr(
                "Cancelling the series: it stops after the frame it is "
                "measuring; the points measured so far are kept."))
            return
        ctx = self._series_context()
        if not ctx or not ctx.get("paths"):
            self.lbl_status.setText(self.tr(
                "No visit with frames: open the editor from a visit to "
                "measure a series."))
            return
        entries = self._sequence()
        if not entries:
            self.lbl_status.setText(self.tr(
                "No comparison sequence yet: build one above with "
                "«Build the sequence…»."))
            return
        target = self._series_target()
        if target is None:
            self.lbl_status.setText(self.tr(
                "Measure the target once (a click on it) so the series "
                "knows where to measure."))
            return
        self._series_cfg = self._series_config(entries, target)
        self._series_cfg_dict = self._series_config_dict(self._series_cfg)
        self._update_series_counter(ctx)
        self.prg_series.setRange(0, len(ctx["paths"]))
        self.prg_series.setValue(0)
        self._series_button_running(True)
        self.btn_series_undo.setEnabled(False)
        from .workers import SeriesWorker
        self._series_worker = SeriesWorker(ctx["paths"], self._series_cfg)
        self._series_worker.progress.connect(self._on_series_progress)
        self._series_worker.finished.connect(self._on_series_finished)
        self._series_worker.failed.connect(self._on_series_failed)
        self._series_worker.start()
        self.lbl_status.setText(self.tr("Measuring the series…"))

    def _on_series_progress(self, done, total):
        self.prg_series.setRange(0, total)
        self.prg_series.setValue(done)

    def _on_series_finished(self, result):
        self._series_button_running(False)
        self._series_worker = None
        context = self._series_context() or {}
        self._update_series_counter(context, result.points)
        if result.status == "incomplete":
            self.lbl_status.setText(self.tr(
                "Series cancelled: it stays “incomplete”; the points "
                "measured so far are kept."))
        else:
            self.lbl_status.setText("")
        rows = self._series_rows(result.points)
        dlg = self.window()
        notify = getattr(dlg, "notify_points", None)
        self._series_run_id = None
        if callable(notify) and rows:
            try:
                self._series_run_id = notify(rows, self._series_cfg_dict)
            except Exception as err:
                logger.warning("series save failed: %s", err)
        self.btn_series_undo.setEnabled(self._series_run_id is not None)
        self.btn_series_exoclock.setEnabled(
            result.status == "complete"
            and any(p.mag is not None for p in result.points))
        self._series_result = result
        self._draw_series(result.points)
        self._fill_series_panel(result, context)

    def _fill_series_panel(self, result, context):
        # Plain-language summary (D13/D25/D35/D20): points and frames,
        # the flags, the detrend coefficients per night, the cadence
        # guard and the multi-night zero-point / band warnings.
        points = result.points
        lines = [self.tr("Series: {0} points from {1} frames").format(
            len(points), len((context or {}).get("paths", [])))]
        nflag = sum(1 for p in points if p.flags)
        if nflag:
            counts = {}
            for p in points:
                for f in p.flags:
                    counts[f] = counts.get(f, 0) + 1
            lines.append(self.tr("Flagged points: {0} ({1})").format(
                nflag, ", ".join(f"{k} × {v}"
                                 for k, v in sorted(counts.items()))))
        det = result.detrend
        if det:
            for n in det.get("nights", []):
                if n.get("fallback"):
                    lines.append(self.tr(
                        "Night {0}: no airmass range, offset only "
                        "({1} points)").format(n["night"], n["n"]))
                else:
                    lines.append(self.tr(
                        "Night {0}: a1={1:.3f}, a2={2:+.3f}, a3={3:.3f} "
                        "(rms {4:.4f} → {5:.4f})").format(
                            n["night"], n["a1"], n["a2"], n["a3"],
                            n["rms_before"] or 0.0,
                            n["rms_after"] or 0.0))
        ctxd = (context or {}).get("context") or {}
        transit = ctxd.get("transit") or {}
        guard = series_measure.cadence_guard(
            points, (context or {}).get("kind"),
            duration_h=ctxd.get("duration_h") or transit.get("duration_h"),
            period_h=ctxd.get("period_h"),
            period_d=ctxd.get("period_d") or ctxd.get("period"))
        qc = series_measure.night_qc(points)
        if guard["level"] == "red":
            lines.append("⚠ " + self.tr(
                "Cadence too short for the transit ingress"))
        for m in guard["messages"] + qc["messages"]:
            lines.append("⚠ " + m.get(self._lang, m.get("en", "")))
        self.lbl_result.setText("\n".join(lines))

    def _on_series_failed(self, message):
        self._series_button_running(False)
        self._series_worker = None
        self.lbl_status.setText(self.tr("The series failed: {0}")
                                .format(message))

    def _series_rows(self, points):
        # @return: the rows the host persists (one run, one batch)
        rows = []
        for p in points:
            if p.mjd is None:
                continue
            rows.append({"mjd": p.mjd, "filter": p.filter, "mag": p.mag,
                         "err": p.err, "mag_raw": p.inst, "path": p.path,
                         "flags": list(p.flags), "source": "measure"})
        return rows

    def _draw_series(self, points):
        # Raw + detrended, flagged points as hollow diamonds (D13/T7).
        raw = [{"mjd": p.mjd, "mag": p.mag, "err": p.err,
                "filter": p.filter, "source": "measure",
                "flags": list(p.flags)}
               for p in points if p.mjd is not None and p.mag is not None]
        det = [{"mjd": p.mjd, "mag": p.mag_detrended, "err": p.err,
                "filter": p.filter, "source": "detrend",
                "flags": list(p.flags)}
               for p in points if p.mjd is not None
               and p.mag_detrended is not None]
        self.chart_series.set_data(_decimate(raw) + _decimate(det))

    def _on_series_exoclock(self):
        # D30/D41: prepare the manual ExoClock submission from the last
        # run, open the upload page and let the host record the outcome.
        from ..core import exoclock_export
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        result = self._series_result
        if result is None or not result.points:
            self.lbl_status.setText(self.tr("Measure the series first."))
            return
        pts = [{"mjd": p.mjd, "jd_start": p.jd_start,
                "mag": p.mag_detrended if p.mag_detrended is not None
                else p.mag, "err": p.err, "exptime": p.exptime,
                "flags": list(p.flags)}
               for p in result.points if p.mjd is not None]
        check = exoclock_export.checklist(pts)
        if check["level"] != "ok":
            lines = [m.get(self._lang, m.get("en", ""))
                     for m in check["messages"]]
            self.lbl_status.setText("⚠ " + " · ".join(lines))
        planet = ""
        obj = getattr(self.window(), "object", lambda: None)()
        if obj and obj.get("name"):
            planet = obj["name"]
        else:
            planet = self._state.path and Path(self._state.path).stem or ""
        default = str(Path(self._state.path).with_suffix(".txt")) \
            if self._state.path else "exoclock.txt"
        out, _sel = QFileDialog.getSaveFileName(
            self, self.tr("ExoClock submission"), default,
            "Text (*.txt)")
        if not out:
            return
        exptimes = [p["exptime"] for p in pts if p["exptime"]]
        expt = exptimes[0] if exptimes else None
        det = result.detrend
        note = self.tr(
            "NightScribe series: {0} points, group {1}, detrend {2}").format(
                len(pts), result.group_n,
                (det or {}).get("policy", "off"))
        exoclock_export.write_submission(
            pts, out, planet or "target",
            self.cmb_band.currentText() or self._band or "", expt, note)
        self.lbl_status.setText(
            self.tr("ExoClock files written. Upload them at exoclock.space"))
        notify = getattr(self.window(), "notify_saved", None)
        if callable(notify):
            notify([out], "report")
        hook = getattr(self.window(), "notify_exoclock", None)
        if callable(hook):
            hook({"planet": planet, "points": len(pts)})
        QDesktopServices.openUrl(QUrl("https://exoclock.space/upload/"))

    def _on_series_undo(self):
        # D6: undo this run only; never the visit.
        if self._series_run_id is None:
            return
        dlg = self.window()
        undo = getattr(dlg, "undo_run", None)
        count = undo(self._series_run_id) if callable(undo) else 0
        self.lbl_status.setText(
            self.tr("Run undone: {0} points removed.").format(count))
        self._series_run_id = None
        self.btn_series_undo.setEnabled(False)
        self.chart_series.set_data([])

    def _on_series_live_toggled(self, checked):
        # D21 (opt-in, off by default): watch the visit folder and measure
        # each new batch with the same engine; the curve grows live.
        if not checked:
            if self._live_worker is not None:
                self._live_worker.cancel()
                self._live_worker = None
            self.lbl_status.setText(self.tr("Live mode off."))
            return
        ctx = self._series_context()
        entries = self._sequence()
        target = self._series_target()
        if not ctx or not ctx.get("paths") or not entries or target is None:
            self.lbl_status.setText(self.tr(
                "Live mode needs a visit with frames, a sequence and a "
                "measured target."))
            self.chk_series_live.blockSignals(True)
            self.chk_series_live.setChecked(False)
            self.chk_series_live.blockSignals(False)
            return
        folder = str(Path(ctx["paths"][0]).parent)
        self._series_cfg = self._series_config(entries, target)
        self._series_cfg_dict = self._series_config_dict(self._series_cfg)
        self._live_points = []
        from .workers import LiveSeriesWorker
        # the live batch is the group: N frames (or the same time with the
        # real exposure), so a few-second sCMOS cadence still groups
        grp = max(1, int(self._advanced.spn_group_n.value()))
        exp_s = 10.0
        try:
            from ..core import fits_meta
            _m = fits_meta.read_meta(ctx["paths"][0])
            exp_s = float(_m.get("exptime_s") or 10.0)
        except Exception:
            pass
        self._live_worker = LiveSeriesWorker(
            folder, self._series_cfg, batch_n=grp, batch_s=grp * exp_s)
        self._live_worker.progress.connect(
            lambda m: self.lbl_status.setText(m))
        self._live_worker.batch.connect(self._on_live_batch)
        self._live_worker.failed.connect(
            lambda m: self.lbl_status.setText(m))
        self._live_worker.start()
        self.lbl_status.setText(self.tr(
            "Live mode on: watching the visit folder…"))

    def _on_live_batch(self, result):
        # A committed batch: persist it as a run and grow the curve.
        rows = self._series_rows(result.points)
        dlg = self.window()
        notify = getattr(dlg, "notify_points", None)
        if callable(notify) and rows:
            try:
                notify(rows, self._series_cfg_dict or {})
            except Exception as err:
                logger.warning("live save failed: %s", err)
        self._live_points.extend(result.points)
        self._draw_series(self._live_points)
        self._update_series_counter(self._series_context() or {},
                                    self._live_points)

    def _open_series_docs(self):
        # D37: the "?" opens the sequences guide in the docs browser.
        from .. import paths as paths_mod
        from .doc_viewer import open_browser
        root = paths_mod.docs_dir()
        name = "SEQUENCES.es.md" if self._lang != "en" else "SEQUENCES.md"
        start = root / name if (root / name).exists() else None
        open_browser(root, self.window(), start=start)

    def _restore_advanced_defaults(self):
        # D25: every knob back to the .ui's shipped default.
        self.cmb_sky.setCurrentIndex(0)
        self.chk_sigmaclip.setChecked(True)
        self.chk_seeing.setChecked(True)
        self.chk_color.setChecked(True)
        self.spn_target_bv.setValue(0.0)
        self.chk_subtract.setChecked(False)
        self._advanced.spn_group_n.setValue(1)
        self._advanced.cmb_detrend.setCurrentIndex(0)
        self._advanced.chk_auto_aperture.setChecked(False)
        self._advanced.spn_saturate.setValue(0.0)
        self.lbl_status.setText(self.tr("Advanced defaults restored."))

    # ------------------------------------------------------------- panel

    def _fill_panel(self, band, n_seq, n_used, skipped, derived, gain):
        # The result block, in plain language and with every caveat that
        # applies (ADR-038: the panel says what was used and what was not).
        last = self._last
        result = last["result"]
        zp = last["zp"]
        # the skip breakdown, computed once: with no calibration the
        # causes ARE the answer, so they ride right under the headline
        # instead of drowning at the bottom of the notes
        n_skip = sum(skipped.values()) if isinstance(skipped, dict) else 0
        parts = []
        if isinstance(skipped, dict):
            if skipped.get("sat"):
                parts.append(self.tr("{0} saturated/clipped")
                             .format(skipped["sat"]))
            if skipped.get("nonlinear"):
                parts.append(self.tr("{0} above your camera's linearity limit")
                             .format(skipped["nonlinear"]))
            if skipped.get("off"):
                parts.append(self.tr("{0} off the plate")
                             .format(skipped["off"]))
            if skipped.get("band"):
                parts.append(self.tr("{0} without the {1} band")
                             .format(skipped["band"], band))
            if skipped.get("other"):
                parts.append(self.tr("{0} not measurable")
                             .format(skipped["other"]))
        lines = []
        lines.append(self.tr("Pixel ({0:.1f}, {1:.1f}) · net flux {2:,.0f}")
                     .format(last["col"], last["row"], result["flux"]))
        lines.append(self.tr("Instrumental mag: {0:.3f}")
                     .format(last["inst_t"]))
        if zp["zp"] is None:
            lines.append(self.tr(
                "No comparison star could be used: no calibration."))
            if n_skip:
                lines.append(self.tr(
                    "Why: {0} (of {1} sequence stars).")
                    .format(", ".join(parts), n_seq))
                if isinstance(skipped, dict) and skipped.get("sat"):
                    lines.append(self.tr(
                        "The proposed comps are too bright for this "
                        "plate: re-propose with a fainter target "
                        "magnitude, or check the saturation ceiling."))
        elif zp.get("color_used"):
            lines.append(self.tr(
                "Zero point: {0:.3f} ± {1:.3f}, colour slope {2:+.3f} "
                "({3} comps, band {4})")
                .format(zp["zp"], zp["zp_err"], zp["k"], zp["n"], band))
        else:
            lines.append(self.tr(
                "Zero point: {0:.3f} ± {1:.3f} ({2} comps, band {3})")
                .format(zp["zp"], zp["zp_err"], zp["n"], band))
        if last["mag"] is not None:
            err_txt = (self.tr("± {0:.3f}").format(last["err"])
                       if last["err"] is not None else "")
            lines.append(self.tr("Magnitude: {0:.3f} {1} ({2})")
                         .format(last["mag"], err_txt, band))
        notes = []
        # the cross-match first: which catalogued source this light is
        # (and how far from it) answers half the "is this right?" by
        # itself; no match within reach is the supernova case
        star, sep = last.get("match") or (None, None)
        if star is not None:
            cmag, _d = photometry.band_of(star, band)
            mband = band
            if cmag is None:
                cmag, mband = star["mag"], star["band"]
            txt = self.tr("Field: {0} {1} at {2:.1f}″ · {3} = {4:.2f}") \
                .format(star["catalog"], star["id"], sep, mband, cmag)
            if last["mag"] is not None and cmag is not None:
                txt += self.tr(" · Δ {0:+.2f}").format(last["mag"] - cmag)
            notes.append(txt)
        else:
            notes.append(self.tr(
                "No catalogued source within 8″ of the target "
                "(a new object?)"))
        click = last.get("click")
        if click is not None:
            moved = math.hypot(last["col"] - click[0],
                               last["row"] - click[1])
            if moved > 1.0:
                notes.append(self.tr(
                    "the centroid landed {0:.1f} px from the click")
                    .format(moved))
        if last["result"].get("cen_ok") is False:
            notes.append(self.tr(
                "no source could be locked: measured where you clicked"))
        if "V" not in last.get("bands_avail", []) and band != "V":
            notes.append(self.tr(
                "The sequence carries no Johnson V: calibrating in "
                "catalog {0} (for red stars it can differ from V by more "
                "than 1 mag)").format(band))
        if last["fwhm"] is not None:
            r = last["radii"]
            notes.append(self.tr(
                "seeing FWHM {0:.1f} px → apertures {1:.1f}/{2:.1f}/{3:.1f}"
                " px").format(last["fwhm"], r[0], r[1], r[2]))
        if self._radii_manual:
            notes.append(self.tr(
                "apertures set by hand (the seeing auto-scale is paused)"))
        for reason in self._last_suggestions:
            notes.append(reason)
        if n_skip and zp["zp"] is not None:
            notes.append(self.tr(
                "{0} of {1} sequence stars not usable: {2}")
                .format(n_skip, n_seq, ", ".join(parts)))
            if skipped.get("sat"):
                notes.append(self.tr(
                    "⚠ comps at the plate's clipping level: a zero point "
                    "built on compressed cores lies LOW (faint targets "
                    "read too bright). Propose fainter comps or shorten "
                    "the exposure"))
            if skipped.get("nonlinear"):
                from ..config import config as _cfg
                _lin = _cfg.get("cam_linearity_adu")
                notes.append(self.tr(
                    "⚠ comps above your camera's linearity limit "
                    "(≈{0:.0f} ADU, per gain): their flux is not "
                    "proportional, so they calibrate nothing. Propose "
                    "fainter comps or shorten the exposure").format(
                        float(_lin or 0)))
        if zp["n"] and zp["n"] < 3:
            notes.append(self.tr(
                "Few comparisons: the scatter dominates the error"))
        if derived:
            notes.append(self.tr(
                "Band {0} estimated from Gaia (Riello 2021)").format(band))
        if self.chk_color.isChecked() and not zp.get("color_used") \
                and zp["zp"] is not None:
            notes.append(self.tr(
                "Colour term not fitted (too few comps or too little "
                "colour spread): plain zero point"))
        if self.chk_color.isChecked() and zp.get("color_used"):
            src_txt = {"assumed": self.tr("assumed"),
                       "catalog": self.tr("from the field star"),
                       "project": self.tr("from the project"),
                       "manual": self.tr("by hand")}.get(self._bv_source,
                                                         "")
            notes.append(self.tr(
                "Colour term applied with target B−V = {0:.2f} ({1})")
                .format(self.spn_target_bv.value(), src_txt))
            k = zp.get("k")
            if self._bv_source == "assumed" and k is not None \
                    and abs(k) >= 0.1:
                notes.append(self.tr(
                    "⚠ B−V assumed: with k = {0:+.2f}, a red star "
                    "(B−V ≈ 1.5) would read ≈{1:.2f} mag too bright; "
                    "enter its real B−V").format(k, abs(k) * 1.5))
        if gain is None:
            notes.append(self.tr(
                "No gain in the header or settings: the photon noise is "
                "not in the error"))
        if last["scint"] is not None:
            notes.append(self.tr(
                "Scintillation included ({0:.3f} mag)")
                .format(last["scint"]))
        if self._diff is not None:
            notes.append(self.tr(
                "Host galaxy subtracted (PS1 reference scaled by the "
                "comps)"))
        if last["err"] is not None and last["err_internal"] is not None:
            notes.append(self.tr(
                "Error: {0:.3f} internal · {1:.3f} total")
                .format(last["err_internal"], last["err"]))
        chk = last["check"]
        if chk is not None:
            if chk["ok"]:
                notes.append(self.tr(
                    "Check star {0}: measured {1:.2f} vs catalog {2:.2f} "
                    "(Δ {3:+.2f}, OK)").format(chk["name"], chk["mag"],
                                               chk["catalog"],
                                               chk["delta"]))
            else:
                notes.append(self.tr(
                    "Check star {0} is off by {1:+.2f} mag: this "
                    "measurement is NOT reliable").format(
                        chk["name"], chk["delta"]))
        lines.extend(f"· {n}" for n in notes)
        self.lbl_result.setText("\n".join(lines))

    # ---------------------------------------------------------- overlays

    def _draw_measurement(self):
        # Aperture + annulus on the measured point, thin rings on the
        # comps that calibrated it (all in plate px, cosmetic pens).
        self._drop_items()
        if not self._on_stage or self._view is None or self._last is None:
            return
        last = self._last
        x, y = self._state.data_to_scene(last["col"], last["row"])
        for r, color, width in (
                (last["radii"][0], _C_AP, 2.0),
                (last["radii"][1], _C_ANN, 1.2),
                (last["radii"][2], _C_ANN, 1.2)):
            ring = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
            pen = QPen(QColor(color))
            pen.setWidthF(width)
            pen.setCosmetic(True)
            ring.setPen(pen)
            ring.setZValue(55)
            self._items.append(self._view.add_overlay(ring))
        for e, _r in last["used"]:
            pos = self._state.data_to_scene(
                *self._state.wcs.sky_to_pixel(e["star"]["ra"],
                                              e["star"]["dec"]))
            ring = QGraphicsEllipseItem(pos[0] - 6, pos[1] - 6, 12, 12)
            pen = QPen(QColor(_C_COMP))
            pen.setWidthF(1.4)
            pen.setCosmetic(True)
            ring.setPen(pen)
            self._items.append(self._view.add_overlay(ring))

    def _drop_items(self):
        if self._view is None:
            self._items = []
            return
        for it in self._items:
            try:
                self._view.scene().removeItem(it)
                if it in self._view._items_registered:
                    self._view._items_registered.remove(it)
            except RuntimeError:
                pass
        self._items = []

    # --------------------------------------------- host subtraction (H2b)

    def _on_subtract_toggled(self, checked):
        # Builds (or drops) the difference image against the aligned PS1
        # reference. Network stays off the GUI thread (BlinkWorker); the
        # reference is fetched once per plate and cached by core/blink.
        if not checked:
            self._drop_subtraction()
            return
        if not self._state.has_image or self._state.wcs is None:
            self.lbl_status.setText(self.tr(
                "The plate needs a WCS for the aligned reference."))
            self.chk_subtract.blockSignals(True)
            self.chk_subtract.setChecked(False)
            self.chk_subtract.blockSignals(False)
            return
        from .workers import BlinkWorker
        ra, dec = self._state.wcs.center()
        self.lbl_status.setText(self.tr(
            "Fetching the reference and subtracting…"))
        self.chk_subtract.setEnabled(False)
        self._sub_worker = BlinkWorker(self._state.path, ra=ra, dec=dec)
        # the pipeline stages (survey reference download) reach the status
        # line, as the Blink tab's prepare does (ADR-018 progress)
        self._sub_worker.progress.connect(
            lambda msg: self.lbl_status.setText(msg.get(self._lang, "")))
        self._sub_worker.finished.connect(self._on_pair_for_subtraction)
        self._sub_worker.start()

    def _on_pair_for_subtraction(self, pair, errors):
        # @args: pair - the blink pair (obs at work size + aligned ref)
        self.chk_subtract.setEnabled(True)
        self._sub_worker = None
        # the observer may have toggled off while the reference flew
        if not self.chk_subtract.isChecked():
            return
        if errors:
            self.lbl_status.setText("⚠ " + errors.get(self._lang, ""))
            self.chk_subtract.blockSignals(True)
            self.chk_subtract.setChecked(False)
            self.chk_subtract.blockSignals(False)
            return
        entries = self._sequence()
        diff = self._build_difference(pair, entries)
        if diff is None:
            self.lbl_status.setText(self.tr(
                "The subtraction found no usable comparison star to "
                "scale the reference."))
            self.chk_subtract.blockSignals(True)
            self.chk_subtract.setChecked(False)
            self.chk_subtract.blockSignals(False)
            return
        self._diff = diff
        obs = pair["obs"]
        if pair.get("flipped"):
            obs = np.ascontiguousarray(obs[:, ::-1])
        self._pair_obs = obs
        plate_w, _plate_h = self._state.plate_shape
        self._diff_scale = plate_w / pair["obs"].shape[1]
        if self._active and self._view is not None:
            self._view.set_frame_override(self._display_diff)
        self.lbl_status.setText(self.tr(
            "Host subtracted. The target now reads on the difference "
            "image; comps calibrate on the original plate."))

    def _build_difference(self, pair, entries):
        # Scales the reference so the comparison stars vanish (least
        # squares through the origin on their net fluxes) and subtracts.
        # Mirrored pairs are un-flipped first (the editor's orientation).
        # @return: the difference image (work frame), or None
        obs = pair["obs"]
        ref = pair["ref"]
        if pair.get("flipped"):
            obs = np.ascontiguousarray(obs[:, ::-1])
            ref = np.ascontiguousarray(ref[:, ::-1])
        plate_w, plate_h = self._state.plate_shape
        fx = plate_w / obs.shape[1]
        fy = plate_h / obs.shape[0]
        num = den = 0.0
        used = 0
        for e in entries:
            try:
                col, row = self._state.wcs.sky_to_pixel(e["star"]["ra"],
                                                        e["star"]["dec"])
            except Exception:
                continue
            wx, wy = col / fx, row / fy
            ro = photometry.measure_point(obs, wx, wy)
            rr = photometry.measure_point(ref, wx, wy)
            if not ro["ok"] or not rr["ok"] or rr["flux"] <= 0:
                continue
            num += ro["flux"] * rr["flux"]
            den += rr["flux"] ** 2
            used += 1
        if used < 2 or den <= 0:
            return None
        gain = num / den
        return obs - gain * ref

    def _display_diff(self):
        # The difference image as the view's frame (screen orientation).
        # Its sky sits at ~0, so the plate's black/white would show a
        # black screen: the difference gets its own auto percentiles
        # (gamma and invert stay shared).
        if self._diff is None:
            return None
        black, white = stretch.auto_limits(self._diff)
        img = stretch.apply_stretch(self._diff, black, white,
                                    self._state.gamma)
        if self._state.inverted:
            img = stretch.invert(img)
        return np.ascontiguousarray(np.flipud(stretch.to_uint8(img)))

    def _drop_subtraction(self):
        # Back to the plain plate: no difference image, no override.
        self._diff = None
        self._sub_worker = None
        if self._view is not None:
            self._view.set_frame_override(None)
        if hasattr(self, "chk_subtract"):
            self.chk_subtract.blockSignals(True)
            self.chk_subtract.setChecked(False)
            self.chk_subtract.blockSignals(False)

    # ------------------------------------------------------------- export

    def _export(self, kind):
        # The measured point as a one-row CSV or an EFF line (D6: files;
        # the project flows stay with the Follow-up tab).
        if self._last is None or self._last["mag"] is None:
            return
        name = ""
        if self._compare is not None:
            name = self._compare.edt_target.text().strip()
        name = name or (Path(self._state.path).stem
                        if self._state.path else "measure")
        meta = fits_meta.meta_from_header(self._state.header or {})
        result = self._last["result"]
        try:
            ra, dec = self._state.wcs.pixel_to_sky(self._last["col"],
                                                   self._last["row"])
        except Exception:
            ra = dec = None
        point = {"mjd": meta["mjd"], "filter": self._last["band"],
                 "mag": self._last["mag"], "err": self._last["err"]}
        src = Path(self._state.path)
        if kind == "csv":
            default = src.with_name(f"{src.stem}_medida.csv")
            out, _sel = QFileDialog.getSaveFileName(
                self, self.tr("Export measurement"), str(default),
                "CSV (*.csv)")
            if not out:
                return
            comps = [e["name"] for e, _r in self._last["used"]]
            photometry_export.export_csv([point], out, name, ra_deg=ra,
                                         dec_deg=dec, comp_stars=comps)
        else:
            default = src.with_name(f"{src.stem}_medida.txt")
            out, _sel = QFileDialog.getSaveFileName(
                self, self.tr("Export measurement (AAVSO EFF)"),
                str(default), "EFF (*.txt *.eff)")
            if not out:
                return
            from ..config import config
            comp = next((e for e, _r in self._last["used"]
                         if e["kind"] == "comp"),
                        self._last["used"][0][0]
                        if self._last["used"] else None)
            check = next((e for e, _r in self._last["used"]
                          if e["kind"] == "check"), None)

            def _nc(entry):
                # @return: {"name", "mag"} for the EFF cells, or None
                if entry is None:
                    return None
                value, _d = photometry.band_of(entry["star"],
                                          self._last["band"])
                return {"name": entry["name"], "mag": value}
            photometry_export.export_eff(
                [point], out, name, ra_deg=ra, dec_deg=dec,
                obscode=config.get("aavso_code", ""),
                comp=_nc(comp), check=_nc(check))
        logger.info("measurement exported (%s): %s", kind, out)
        self.lbl_status.setText(self.tr("Written to {0}").format(out))
        # ADR-045: the one-row report registers in the watching project
        # (the visit it was measured from), like every other UFE file
        dlg = self.window()
        notify = getattr(dlg, "notify_saved", None)
        if callable(notify):
            notify([out], "report")
