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
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (QFileDialog, QWidget, QMessageBox,
                               QGraphicsEllipseItem)

from ..core import chart_annotate, coords, fits_meta, host_subtract, \
    photometry, photometry_export, \
    series_measure, stretch
from ..config import config
from ..viz import palette
from . import theme
from .ufe_advanced_dialog import UfeAdvancedDialog
from .ufe_host import host_of
from .ufe_centre_dialog import UfeCentreDialog
from .ufe_series_dialog import UfeSeriesDialog
from .ufe_passes_dialog import UfePassesDialog
from .ui_loader import adopt_ui
from .widgets.collapsible_section import CollapsibleSection
from .widgets.lightcurve_widget import LightCurveChart

logger = logging.getLogger("nightscribe.gui.ufe_measure_tab")

_C_AP = palette.ACCENT   # the shared amber marker family the UFE wears
_C_ANN = "#6ec1ff"     # sky annulus rings in the cool accent
_C_COMP = "#4dd0e1"    # used comps ring in the compare tab's cyan


def _echo_report(report, limit=None):
    # A JSON-safe echo of a run report for the audit trail: the failure
    # list is capped (the count is what matters) and only plain values
    # travel.
    # @args: report - align_report / comp_report, limit - cap for lists
    # @return: a JSON-safe dict, or None
    if not report:
        return None
    out = {}
    for key, value in report.items():
        if isinstance(value, (int, float, str)) or value is None:
            out[key] = value
        elif isinstance(value, (list, tuple)):
            items = list(value)
            out[key] = items[:limit] if limit else items
            if limit and len(items) > limit:
                out[key + "_total"] = len(items)
        elif isinstance(value, dict):
            out[key] = {str(k): v for k, v in value.items()
                        if isinstance(v, (int, float, str)) or v is None}
    return out


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
        self._sub_report = None      # host_subtract.subtract's report
                                     # (alignment quality, for the panel)
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
        self._status_hook = None     # the window's single status line (U4)
        # ADR-038 rev: the recipe (band, apertures, manual centre, Suggest
        # and Advanced) lives in ONE block, closed on entry, because the
        # panel's hero button is what the observer came for and the defaults
        # are what most nights want. The block's container comes from the
        # Designer file, so the structure stays there (ADR-005).
        self._sections = {
            "recipe": self._wrap_section(
                "sec_recipe_content", self.tr("The photometry recipe"),
                "photometry_recipe_open"),
            # The measurement's own result (the panel with the numbers and
            # the ways out of it) is a group too, and it appears with the
            # first measurement: an empty box is furniture. It is CLOSED like
            # every other group (asked for 2026-10-06), with a fresh key
            # because the previous design opened it by default; the magnitude
            # announces itself on its header (see _draw_measurement), so the
            # observer knows there is something to read without opening it.
            "result": self._wrap_section(
                "sec_result_content", self.tr("Measurement"),
                "photometry_result_open2"),
        }
        self._sections["result"].setVisible(False)
        self.refresh_accent()
        self._curve_load = None      # fn() -> the visit's saved points (D)
        self._curve_clear = None     # fn() -> undo every series run (D)
        self._curve_from_visit = False   # the chart shows the visit's curve
        self.cmb_band = self._ui.cmb_band
        # THE BAND IS PART OF THE RECIPE: it picks the catalogue band of the
        # comparisons, so changing it changes the magnitude. It was the only
        # control of the tab that did NOT re-measure (reported: "if you
        # measure again, changing the band for instance, the magnitude does
        # not update").
        self.cmb_band.currentIndexChanged.connect(
            lambda _i: self._remeasure())

        # WHAT THE BAND REPORTS (2026-10-10): the brightness measured on the
        # stack, or the ephemeris' prediction for the same instant. It is
        # part of the recipe because it decides what a reader sees over the
        # image; the track & stack writes it into the stack's own band
        # (NS_MAGSR) and the astrometry's point keeps the measurement.
        self.cmb_report_mag = self._ui.cmb_report_mag
        self.cmb_report_mag.addItem(self.tr("Measured on this stack"),
                                    "measured")
        self.cmb_report_mag.addItem(self.tr("Ephemeris prediction"),
                                    "ephemeris")
        self.cmb_report_mag.setItemData(0, self.tr(
            "The brightness measured here (the object on its own stack, the "
            "comps on the star stack), with its own error and quality colour. "
            "It is what the MPC gets."), Qt.ToolTipRole)
        self.cmb_report_mag.setItemData(1, self.tr(
            "The ephemeris' predicted magnitude for this instant, labelled "
            "(eph). Use it when the measurement is not worth reporting (a "
            "zero point resting on too few comparisons, a trailed object): "
            "the measurement is kept in the run, only the band changes."),
            Qt.ToolTipRole)
        self.cmb_report_mag.currentIndexChanged.connect(
            lambda _i: self._remeasure())

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
        # Manual centre: the tab keeps only the checkbox; the arrows, the
        # readout and the reset live in their own small non-modal window
        # (UfeCentreDialog), shown while the box is checked. The observer
        # moves the centre by hand in 0.1 px steps and the measurement uses
        # EXACTLY that point (no centroid search): a very faint SN or a
        # galaxy core cannot drag it. Session-only: a new click or plate
        # starts at (0, 0).
        self._nudge = [0.0, 0.0]
        self._centre = UfeCentreDialog(self)
        self.lbl_nudge = self._centre.lbl_nudge
        self._centre.btn_up.clicked.connect(
            lambda: self._nudge_step(0.0, 0.1))
        self._centre.btn_left.clicked.connect(
            lambda: self._nudge_step(-0.1, 0.0))
        self._centre.btn_right.clicked.connect(
            lambda: self._nudge_step(0.1, 0.0))
        self._centre.btn_down.clicked.connect(
            lambda: self._nudge_step(0.0, -0.1))
        self._centre.btn_nudge_reset.clicked.connect(self._on_nudge_reset)
        # closing the window (its X) is the same as unchecking the box
        self._centre.rejected.connect(
            lambda: self.chk_manual_centre.setChecked(False))
        self.chk_manual_centre = self._ui.chk_manual_centre
        self.chk_manual_centre.toggled.connect(self._on_manual_centre)
        self.btn_advanced = self._ui.btn_advanced
        self.btn_advanced.clicked.connect(self._open_advanced)
        # the sequence IS the calibration: adding or removing a comparison
        # (or retyping it) moves the zero point, so the live point is
        # measured again (refresh_bands only keeps the combo in step)
        if self._compare is not None:
            self._compare.sequence_changed.connect(
                self._on_sequence_changed)
        # the public attributes the tests and the measure flow pin
        self.chk_sigmaclip = self._advanced.chk_sigmaclip
        self.chk_seeing = self._advanced.chk_seeing
        # The switch lives in the PANEL and not inside Advanced… (2026-10-07):
        # a knob that decides how the light is measured cannot be two clicks
        # away from the measurement. It was in the advanced window and the
        # observer looked for it and did not find it. It is the same recipe
        # field as always, so capture_state, the astrometry run and the series
        # read it from here and nothing else had to move.
        self.chk_matched = self._ui.chk_matched
        # It STARTS at the app's own default (Ajustes -> Photometry), read
        # here so that `ui_defaults()` and the state reset go back to that
        # default and not to a value baked into the .ui file
        self.chk_matched.setChecked(bool(config.get("phot_matched", True)))
        # And the recipe group's HEADER says the method while the group is
        # closed: the switch was invisible twice over (inside Advanced… and
        # inside a closed group), and a method that changes the published
        # magnitude cannot be a secret. The chip goes when the group opens,
        # because then the switch itself is there.
        self.chk_matched.toggled.connect(
            lambda _c: self._sync_method_notice())
        self._sync_method_notice()
        self.chk_color = self._advanced.chk_color
        self.chk_subtract = self._advanced.chk_subtract
        self.cmb_sky = self._advanced.cmb_sky
        self.spn_target_bv = self._advanced.spn_target_bv
        # every measuring control re-measures the live point at once
        self.cmb_sky.currentIndexChanged.connect(
            lambda _i: self._remeasure())
        self.chk_sigmaclip.toggled.connect(lambda _c: self._remeasure())
        self.chk_seeing.toggled.connect(self._on_seeing_toggled)
        # el metodo de medida cambia el numero: la medida viva se rehace
        self.chk_matched.toggled.connect(lambda _c: self._remeasure())
        self.chk_color.toggled.connect(lambda _c: self._remeasure())
        self.spn_target_bv.valueChanged.connect(self._on_bv_edited)
        self.chk_subtract.toggled.connect(self._on_subtract_toggled)
        # the saturation ceiling decides which comps are usable at all: it
        # is part of the recipe too (it was not wired either)
        self.spn_saturate = self._advanced.spn_saturate
        self.spn_saturate.valueChanged.connect(lambda _v: self._remeasure())
        self.spn_saturate.valueChanged.connect(
            lambda _v: self._update_saturate_hint())

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
        # U5: the ways out of a measurement, behind two doors. "Export" holds
        # the CSV and the AAVSO EFF report, "Reset" the plate's two resets:
        # four buttons that used to take two rows of the column. They are the
        # SAME widgets, moved one by one into their panel (a layout removed
        # from its parent is deleted by the binding), so every name the code
        # and the tests use is untouched, and their texts and tooltips keep
        # living in the Designer file (ADR-005). Same mechanism as the
        # window's doors (U2) and the series' one (U6).
        # The actions of a measurement belong to the RESULT (ADR-038 rev):
        # with nothing measured they are furniture, so they live in one
        # container that appears with the panel's lines.
        self.w_result_actions = self._ui.w_result_actions
        self.btn_export_more = self._ui.btn_export_more
        # D: the write-back of a magnitude measured by hand. The button only
        # lives when the plate is an astrometry stack that knows its run and
        # its observation (see _sync_manual_button).
        self.btn_manual_mag = self._ui.btn_manual_mag
        self.btn_manual_mag.clicked.connect(self._on_manual_magnitude)
        self.btn_reset_more = self._ui.btn_reset_more
        self._door(self.btn_export_more, (self.btn_csv, self.btn_eff))
        self._door(self.btn_reset_more, (self.btn_reset_state,
                                         self.btn_reset_points))
        # the door follows its contents: nothing measured yet, nothing to
        # export (the .ui ships the buttons disabled, and this is the one
        # place that turns them on and off from now on)
        self._set_export_enabled(False)

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
        self.btn_series_phase = self._ui.btn_series_phase
        self.btn_series_phase.clicked.connect(self._on_series_phase)
        self.btn_series_sci = self._ui.btn_series_sci
        self.btn_series_sci.clicked.connect(self._on_series_sci)
        self.btn_series_night = self._ui.btn_series_night
        self.btn_series_night.clicked.connect(self._on_series_night)
        self.lbl_series_frames = self._ui.lbl_series_frames
        self.lbl_series_cadence = self._ui.lbl_series_cadence
        self.prg_series = self._ui.prg_series
        # the quick "Group frames" in the series block mirrors the
        # Advanced… knob (one value, two views; ADR-048 follow-up)
        self.spn_group_quick = self._ui.spn_group_n_quick
        self.spn_group_quick.setValue(self._advanced.spn_group_n.value())
        self.spn_group_quick.valueChanged.connect(self._on_group_quick)
        self._advanced.spn_group_n.valueChanged.connect(
            self._on_group_advanced)
        self.chk_series_live = self._ui.chk_series_live
        self.chk_series_live.toggled.connect(self._on_series_live_toggled)
        self._live_worker = None
        self._live_points = []
        self._live_run_ids = []      # the live session's batches: one
                                     # undoable run (ADR-050, P2 #19)
        self._live_run_id = None     # the run those batches pile into (one
                                     # live session, one run: the curve
                                     # reloaded is the whole session)
        # U6: the chart's own controls (scale, error bars, binning, mean,
        # outliers, exclusions) live in their own non-modal window now: the
        # left panel had seventeen of them stacked in a 300 px column, and
        # they are knobs you touch while LOOKING at the curve, not while
        # measuring it. The widgets are the same ones, wired here.
        self._series_dlg = UfeSeriesDialog(self)
        # the passes of the visit, in their own window (one night, one
        # curve): the list is read-only and the actions travel to the tab
        self._passes_dlg = UfePassesDialog(self)
        self._passes_dlg.use_requested.connect(self._use_pass)
        self._passes_dlg.undo_requested.connect(self._undo_pass)
        self.chart_series = LightCurveChart()
        self.chart_series.setToolTip(self.tr(
            "Click a point to select it; drag to move the view; the wheel "
            "zooms BOTH axes around the cursor, Shift zooms the time only "
            "and Ctrl the magnitudes only; double-click frames the whole "
            "curve again"))
        # A click on a POINT selects it (quality plan, A); a click on the
        # empty space still opens the big view, and the double-click keeps
        # working too. The chart itself decides which is which, because
        # only it knows where the points are.
        self.chart_series.enlarge_requested.connect(self._on_series_enlarge)
        # the chart's own controls (quality plan, phase A): the magnitude
        # scale is robust by default, the error bars are the point's own
        # photons and the flagged points stay visible unless asked
        # what the vertical axis MEASURES (V1): a measured magnitude and a
        # differential one are different quantities, and drawing both on
        # one axis is what gave a curve of hundredths an axis from 2 to 14
        self.cmb_series_scale = self._series_dlg.cmb_series_scale
        self.cmb_series_scale.addItem(self.tr("Calibrated magnitude"),
                                      "calibrated")
        self.cmb_series_scale.addItem(self.tr("Δ magnitude (differential)"),
                                      "differential")
        self.cmb_series_scale.currentIndexChanged.connect(
            self._on_series_scale_changed)
        self.btn_series_robust = self._series_dlg.btn_series_robust
        self.btn_series_robust.toggled.connect(self.chart_series.set_robust)
        self.btn_series_robust.toggled.connect(
            lambda _on: self._refresh_chart_notes())
        self.btn_series_zoomfit = self._series_dlg.btn_series_zoomfit
        self.btn_series_zoomfit.clicked.connect(
            self.chart_series.reset_view)
        self.btn_series_errors = self._series_dlg.btn_series_errors
        self.btn_series_errors.toggled.connect(
            self.chart_series.set_errors_visible)
        self.btn_series_errors.toggled.connect(
            lambda _on: self._refresh_chart_notes())
        self.btn_series_hideflags = self._series_dlg.btn_series_hideflags
        self.btn_series_hideflags.toggled.connect(
            self.chart_series.set_hide_flagged)
        self.btn_series_hideflags.toggled.connect(
            lambda _on: self._refresh_chart_notes())
        # the points wear the quality code by default (the observer asked
        # for it): the button gives back the filter colours
        self.btn_series_quality = self._series_dlg.btn_series_quality
        self.btn_series_quality.toggled.connect(
            self.chart_series.set_quality_colours)
        self.btn_series_quality.toggled.connect(
            lambda _on: self._refresh_chart_notes())
        # --- the observer's decisions on the curve (quality plan, phase A)
        self.btn_series_fixaxis = self._series_dlg.btn_series_fixaxis
        self.spn_series_maglo = self._series_dlg.spn_series_maglo
        self.spn_series_maghi = self._series_dlg.spn_series_maghi
        self.btn_series_fixaxis.toggled.connect(self._on_fix_axis)
        self.spn_series_maglo.valueChanged.connect(self._on_fix_axis)
        self.spn_series_maghi.valueChanged.connect(self._on_fix_axis)
        self.cmb_series_bin = self._series_dlg.cmb_series_bin
        self.cmb_series_bin.addItem(self.tr("None (one point per frame)"),
                                    "off")
        self.cmb_series_bin.addItem(self.tr("Every N frames"), "frames")
        self.cmb_series_bin.addItem(self.tr("Every N minutes"), "minutes")
        self.cmb_series_bin.currentIndexChanged.connect(self._on_bin_changed)
        self.spn_series_binn = self._series_dlg.spn_series_binn
        self.spn_series_binn.valueChanged.connect(self._on_bin_changed)
        self.chk_series_mean = self._series_dlg.chk_series_mean
        self.spn_series_meanwin = self._series_dlg.spn_series_meanwin
        self.chk_series_mean.toggled.connect(self._on_bin_changed)
        self.spn_series_meanwin.valueChanged.connect(self._on_bin_changed)
        self.chk_series_outliers = self._series_dlg.chk_series_outliers
        self.spn_series_outsigma = self._series_dlg.spn_series_outsigma
        self.chk_series_outliers.toggled.connect(self._on_detect_outliers)
        self.spn_series_outsigma.valueChanged.connect(
            self._on_detect_outliers)
        self.btn_series_exclout = self._series_dlg.btn_series_exclout
        self.btn_series_exclout.clicked.connect(self._on_exclude_outliers)
        self.btn_series_exclsel = self._series_dlg.btn_series_exclsel
        self.btn_series_exclsel.clicked.connect(self._on_exclude_selected)
        self.btn_series_restore = self._series_dlg.btn_series_restore
        self.btn_series_restore.clicked.connect(self._on_restore_all)
        self.lbl_series_selection = self._series_dlg.lbl_series_selection
        # U6: two doors instead of the wall. "Chart…" opens the window above
        # (its label is short on purpose: the widest row of the block was
        # this button plus the door, 571 px with a 1.5x font, and it set the
        # block's floor; the tooltip and the window's title carry the rest);
        # "Series ▾" holds the six occasional actions that
        # used to be six more buttons in the column (the row is MOVED into
        # the menu's panel, so the widgets, their texts and their names are
        # the same ones).
        self.btn_series_chart = self._ui.btn_series_chart
        self.btn_series_chart.clicked.connect(self._open_series_chart)
        self.btn_series_discard = self._ui.btn_series_discard
        self.btn_series_discard.clicked.connect(self._on_discard_curve)
        self.btn_series_more = self._ui.btn_series_more
        # "Passes of this visit…": the night's passes, which one is drawn
        # and how to go back to another (it lands in the "Series ▾" menu
        # with the rest of the row, see below)
        self.btn_series_passes = getattr(self._ui, "btn_series_passes", None)
        if self.btn_series_passes is not None:
            self.btn_series_passes.clicked.connect(self._open_passes)
        # the scope: this visit (one night) or every visit of the project
        # (one pass, one run per night). The multi-night item is only
        # OFFERED when the project has more than one visit with frames.
        self.cmb_series_scope = getattr(self._ui, "cmb_series_scope", None)
        self.lbl_series_scope = getattr(self._ui, "lbl_series_scope", None)
        if self.cmb_series_scope is not None:
            self.cmb_series_scope.setItemData(0, "visit")
            self.cmb_series_scope.setItemData(1, "project")
            self.cmb_series_scope.currentIndexChanged.connect(
                self._on_series_scope_changed)
            self.cmb_series_scope.setVisible(False)
            if self.lbl_series_scope is not None:
                self.lbl_series_scope.setVisible(False)
        row_out = getattr(self._ui, "row_series_out", None)
        if row_out is not None:
            from .widgets.door_menu import build_door
            # EVERY widget the row holds goes into the door, not a list of
            # names: a hardcoded list forgot the button added later (the
            # "discard the visit's curve" one), which then stayed inside the
            # row while the row itself was removed from the column: a widget
            # with no layout to place it, floating over the rest of the form
            # (reported: "the delete button comes out broken and totally out
            # of place"). Reading the row means a new button in the Designer
            # file can never be orphaned again.
            #
            # The row is not dismantled: the buttons stay in it, hidden, and
            # the door is a plain menu that triggers them (see
            # gui/widgets/door_menu.py for why the panel of moved widgets is
            # gone: it crashed Windows while the dialog was being built).
            buttons = []
            for i in range(row_out.count()):
                item = row_out.itemAt(i)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    buttons.append(widget)
            # and one that lives in the RUN row, not in this one: "undo the
            # last run" sits beside "Measure the sequence" in the Designer
            # file but belongs with the other occasional actions (it is not
            # what you press every night). It is named here, on purpose: it
            # is the only exception, and the test pins it.
            buttons.append(getattr(self._ui, "btn_series_undo", None))
            build_door(self.btn_series_more, buttons)
            # the row keeps its (hidden) buttons, so nothing is left floating
            # and the names the code and the tests use are untouched
            section = getattr(self._ui, "vbox_series_actions", None)
            if section is not None:
                try:
                    section.removeItem(row_out)
                except RuntimeError:
                    pass
        self.chart_series.point_clicked.connect(self._on_point_clicked)
        # the chart belongs to this tab (the logic is here) but lives in
        # the CENTRE of the window (V2): ufe_dialog places it. The left
        # panel keeps only the controls.
        self._series_payload = []    # last drawn points
        self._series_worker = None
        self._series_run_id = None
        self._series_result = None
        self._series_cfg = None
        self._series_cfg_dict = None
        self._series_attached = False
        self._kind_defaults_done = False
        # the Advanced window stays a dumb container: its restore button
        # is wired here, where the defaults live
        self._advanced.btn_restore.clicked.connect(
            self._restore_advanced_defaults)

    def set_status_hook(self, fn):
        # The window takes the messages (U4): its bottom line is where a
        # reader looks. The tab's own label stays as a record (hidden), so
        # everything that reads it keeps working.
        # @args: fn - callable(text, level) or None
        # @return: None
        self._status_hook = fn

    def _say(self, text, level=None):
        # Says one thing: to this tab's record AND to the window.
        # @args: text - the message, level - "info" | "warn" | "error"
        #        (None: inferred from the ⚠ the message already carries)
        # @return: None
        text = str(text)
        if level is None:
            level = "warn" if text.startswith("⚠") else "info"
        self.lbl_status.setText(text)      # the tab's own record (hidden)
        if self._status_hook is not None:
            self._status_hook(text, level)

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

    def _sync_method_notice(self):
        # @return: None. The recipe group's header carries the method while
        #          the group is closed, so the observer sees which one will
        #          measure without opening anything (the chip is the group's
        #          own way of announcing itself: see CollapsibleSection).
        sec = self._sections.get("recipe")
        if sec is None:
            return
        sec.setHeaderBadge(self.tr("matched filter")
                           if self.chk_matched.isChecked()
                           else self.tr("aperture"))

    def _on_group_quick(self, value):
        # the series block's Group frames drives the Advanced… one
        if self._advanced.spn_group_n.value() != value:
            self._advanced.spn_group_n.blockSignals(True)
            self._advanced.spn_group_n.setValue(value)
            self._advanced.spn_group_n.blockSignals(False)

    def _on_group_advanced(self, value):
        # and the other way round (restore defaults, saved recipes)
        if self.spn_group_quick.value() != value:
            self.spn_group_quick.blockSignals(True)
            self.spn_group_quick.setValue(value)
            self.spn_group_quick.blockSignals(False)

    # ------------------------------------------------------- activation

    # -------------------------------------------------------- the block

    def _wrap_section(self, name, title, key, open_by_default=False):
        # @args: name - the .ui container's objectName, title - the block's
        #        title in plain language, key - the settings key that
        #        remembers whether it stays open, open_by_default - the state
        #        before the observer chooses
        # @return: the CollapsibleSection
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

    def refresh_accent(self):
        # @return: None. The recipe block wears the object's hue on its
        #          spine, like every other block of the panel.
        ask = getattr(host_of(self), "project_accent", None)
        hue = None
        if callable(ask):
            try:
                hue = (ask() or {}).get("hue")
            except Exception as err:
                logger.warning("the project accent could not be read: %s", err)
        for section in getattr(self, "_sections", {}).values():
            section.setAccent(hue or theme.C_ACCENT)

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

    # ------------------------------------------- the ways out (U5)

    def _door(self, tool, widgets):
        # Puts a set of existing buttons inside the dropdown hanging from a
        # QToolButton (U5): a plain menu whose items trigger those buttons
        # (see gui/widgets/door_menu.py for why the panel of moved widgets
        # is gone: it crashed Windows while the dialog was being built,
        # 2026-10-01).
        # @args: tool - the QToolButton, widgets - the buttons the door
        #        opens onto
        # @return: None
        from .widgets.door_menu import build_door
        build_door(tool, list(widgets))

    def _set_export_enabled(self, flag):
        # The CSV and the AAVSO EFF report are what the Export door opens
        # onto, so the door follows them: a door that opens onto two grey
        # buttons is a lie, and one that stays lit with nothing to export is
        # a trap (U5). One place decides for the three of them.
        # @args: flag - True when there is a calibrated magnitude to write
        # @return: None
        flag = bool(flag)
        self.btn_csv.setEnabled(flag)
        self.btn_eff.setEnabled(flag)
        self.btn_export_more.setEnabled(flag)
        # the manual write-back needs the same magnitude plus the run and the
        # observation in the stack's header
        self._sync_manual_button()
        # the door shows it at once, not only when it opens
        from .widgets.door_menu import refresh_door
        refresh_door(self.btn_export_more)

    def _manual_target(self):
        # @return: (run_id, group_index) when this plate is an astrometry
        #          stack that knows which observation it is, or None
        # The run's id and the observation travel in the stack's own header
        # (NS_RUN / NS_NOBS): the tab never guesses from a file name.
        header = getattr(self._state, "header", None) or {}
        run = header.get("NS_RUN")
        obs = header.get("NS_NOBS")
        if run is None or obs is None:
            return None
        try:
            return int(run), int(obs) - 1
        except (TypeError, ValueError):
            return None

    def _sync_manual_button(self):
        # @return: None. The button writes the measurement THIS plate shows
        #          into the observation the stack belongs to, so it needs all
        #          three: a calibrated measurement, the run and the
        #          observation in the header, and a host to write it.
        host = host_of(self)
        can = (self._last is not None and self._last.get("mag") is not None
               and self._manual_target() is not None
               and callable(getattr(host, "manual_magnitude", None)))
        self.btn_manual_mag.setEnabled(bool(can))

    def _on_manual_magnitude(self):
        # @return: None. The observer measured the brightness by hand and
        #          says the report should use it: the tab asks the host (it
        #          never touches the database) and says what happened.
        target = self._manual_target()
        if target is None or self._last is None:
            return
        write = getattr(host_of(self), "manual_magnitude", None)
        if not callable(write):
            return
        run_id, group = target
        mag = float(self._last.get("mag"))
        band = self._last.get("band") or self._band
        try:
            done = bool(write(run_id, group, mag, band))
        except Exception as err:
            logger.warning("the manual magnitude failed: %s", err)
            done = False
        if done:
            self._say(self.tr(
                "The report will use this measurement: %1 %2").replace(
                    "%1", f"{mag:.3f}").replace("%2", str(band or "")))
        else:
            self._say(self.tr(
                "The measurement could not be written to the observation."))

    # -------------------------------------------------- resets (ADR-047)

    def set_reset_attached(self, flag):
        # ADR-047: the dialog carries reset hooks (it was opened from a
        # project): the two plate resets show. Same rule as the save
        # button: not attached, not visible.
        # @args: flag - True when the dialog's state/points hooks are set
        # the door goes with them: the row must not keep a Reset button
        # that opens onto nothing
        self.btn_reset_more.setVisible(bool(flag))
        # The two resets live INSIDE the door: they stay hidden (the door is
        # the way in) and what changes is whether their items are live, which
        # the menu reads when it opens. Making them visible here put them
        # floating over the window, and the door's own item made them look
        # duplicated (reported 2026-10-01).
        self.btn_reset_state.setEnabled(bool(flag))
        self.btn_reset_points.setEnabled(bool(flag))
        from .widgets.door_menu import refresh_door
        refresh_door(self.btn_reset_more)

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
        dlg = host_of(self)
        f = getattr(dlg, "reset_state_local", None)
        if not callable(f) or not f():
            self._say(self.tr(
                "Load a plate first: there is no state to reset."))
            return
        if dlg.notify_reset_state():
            self._say(self.tr("Plate state reset."))
        else:
            self._say(self.tr(
                "Plate state reset locally: this plate is not "
                "registered in the project, so there was no saved "
                "state to clear."))

    def _on_reset_points(self):
        # ADR-047: destructive for the light curve: every measured point
        # saved on THIS plate is dropped. The plan requires a
        # confirmation here, and the hook fires only after a yes.
        dlg = host_of(self)
        if not dlg.state.has_image:
            self._say(self.tr(
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
            self._say(self.tr(
                "The plate's measurement points were deleted."))
        else:
            self._say(self.tr(
                "No measurement points saved on this plate."))

    def _on_save_project(self):
        # ADR-044: the host (Main window) set a point hook when it opened
        # us from a project; it saves this point under that project
        # (source “measure”, the visit attached) and refreshes the curve.
        # @return: None; the outcome shows in the status line.
        if self._last is None or self._last.get("mag") is None:
            self._say(
                self.tr("Nothing to save yet: measure a point first."))
            return
        meta = fits_meta.meta_from_header(self._state.header or {})
        mjd = meta.get("mjd")
        if mjd is None:
            self._say(self.tr(
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
        dlg = host_of(self)
        if not dlg or not dlg.notify_point(payload):
            self._say(
                self.tr("Could not save the point in the project."))
            return
        self._say(self.tr(
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
        # the old plate's summary goes with it: a later repaint (the chart's
        # own notes) must not bring a stale measurement back to the panel
        self._panel_summary = []
        self._drop_items()
        self._drop_subtraction()
        self.lbl_result.setText("–")
        # nothing measured on this plate: the group with the result and the
        # ways out of it is not there at all
        self._sections["result"].setVisible(False)
        self._set_export_enabled(False)
        self.btn_save_project.setEnabled(False)
        self.setEnabled(self._state.has_image)
        self._say("")
        self._update_saturate_hint()
        self._reset_nudge()
        self._sync_centre_dialog()

    # -------------------------------------------------------- measuring

    def _track_stack_plate(self):
        # @return: "object" | "stars" when the open plate is a track & stack
        #          (the astrometry tab writes NS_STACK when it saves one),
        #          or None for an ordinary plate
        header = getattr(self._state, "header", None) or {}
        kind = header.get("NS_STACK")
        return str(kind).strip().lower() if kind else None

    def _track_stack_blocks_measure(self):
        # @return: the reason this plate cannot set a zero point, or None
        # On an object's stack the stars are TRAILS: a circular aperture on
        # a 90 px streak measures a fraction of a flux, so the zero point
        # it would set is a lie. On a star stack the comps are points but
        # the OBJECT is the streak. Either way the measurement needs the
        # pair, and until it is there the honest answer is to say why.
        kind = self._track_stack_plate()
        if kind is None:
            return None
        header = getattr(self._state, "header", None) or {}
        if header.get("NS_PAIR"):
            return None            # the pair is here: it can be measured
        if kind == "object":
            return self.tr(
                "This plate is an object's track & stack: its stars are "
                "TRAILS, so the comparison stars cannot set a zero point "
                "here (a streak read with a circular aperture is not a "
                "flux). The brightness is measured in the Astrometry tab, "
                "which reads the comps on a second stack aligned on the "
                "stars. Here you can still adjust the RECIPE that tab "
                "uses: the apertures, the sky and the centroid.")
        if kind == "base":
            return self.tr(
                "This plate is the WHOLE-SEQUENCE stack of a track & stack: "
                "every frame combined with the object frozen, so the object "
                "is as deep as the visit goes and the stars are trails. The "
                "comparison stars cannot set a zero point here (a streak "
                "read with a circular aperture is not a flux): the "
                "brightness is measured in the Astrometry tab, on the "
                "observations' own stacks.")
        return self.tr(
            "This plate is the STAR stack of a track & stack: the comps are "
            "points here, but the OBJECT is a trail, so it cannot be "
            "measured on this plate. Open the object's stack and measure "
            "there. Here you can still adjust the RECIPE the Astrometry "
            "tab uses.")

    def _explain_no_wcs_measure(self):
        # The automatic solve did not land: the click cannot be measured.
        self._say(self.tr(
            "The plate has no WCS and it could not be solved: the "
            "comparison stars cannot be located."))

    def _explain_no_wcs_subtract(self):
        # The automatic solve did not land: no aligned reference, so the
        # checkbox goes back down with the reason on the status line.
        self._say(self.tr(
            "The plate has no WCS and it could not be solved: no aligned "
            "reference."))
        self.chk_subtract.blockSignals(True)
        self.chk_subtract.setChecked(False)
        self.chk_subtract.blockSignals(False)

    def _on_scene_clicked(self, scene_pt):
        if not self._active or not self._state.has_image:
            return
        # A track & stack cannot set a zero point out of its streaks (or
        # measure an object that is one): say it BEFORE the solve, because
        # the WCS is there and the measurement would otherwise proceed and
        # produce a magnitude nobody could trust.
        blocked = self._track_stack_blocks_measure()
        if blocked:
            self._say(blocked)
            return
        if self._state.wcs is None:
            # ADR-051: the plate is solved automatically and the click
            # lands; never a dead end asking for a manual solve
            self._say(self.tr(
                "The plate has no WCS: solving it to locate the "
                "comparison stars…"))
            dlg = host_of(self)
            req = getattr(dlg, "request_wcs", None)
            if callable(req):
                req(lambda: self._on_scene_clicked(scene_pt),
                    on_fail=self._explain_no_wcs_measure)
                return
            self._explain_no_wcs_measure()
            return
        entries = self._sequence()
        if not entries:
            self._say(self.tr(
                "No comparison sequence yet: build one above with "
                "«Build the sequence…»."))
            return
        self._last_suggestions = []     # a new target: stale reasons go
        self._reset_nudge()             # a new click starts at (0, 0)
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

    def refresh_bands(self):
        # The sequence changed (a manual band was typed in): keep the band
        # combo in step so the observer can pick it before measuring.
        entries = self._sequence()
        bands = photometry.available_bands(entries)
        if not bands:
            return
        current = self.cmb_band.currentText()
        self.cmb_band.blockSignals(True)
        self.cmb_band.clear()
        self.cmb_band.addItems(bands)
        self.cmb_band.setCurrentText(current if current in bands
                                     else bands[0])
        self.cmb_band.blockSignals(False)
        self._band = self.cmb_band.currentText() or self._band

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
            "manual_centre": bool(self.chk_manual_centre.isChecked()),
            "matched": bool(self.chk_matched.isChecked()),
            "report_mag": self.cmb_report_mag.currentData() or "measured",
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
                         (self.chk_color, "color"),
                         (self.chk_matched, "matched")):
            # A recipe that does not mention a knob does NOT move it: the
            # fallback is where the widget already is (the .ui's default, or
            # the app's own setting), so a plate saved before a key existed
            # inherits the default instead of silently turning it off. With
            # `False` as the fallback, the key added yesterday (matched)
            # unticked itself on every old plate.
            want = bool(st.get(key, chk.isChecked()))
            if chk.isChecked() != want:
                chk.setChecked(want)
        sky = st.get("sky")
        if sky:
            row = self.cmb_sky.findData(sky)
            if row >= 0:
                self.cmb_sky.setCurrentIndex(row)
        rep = st.get("report_mag")
        if rep:
            row = self.cmb_report_mag.findData(rep)
            if row >= 0:
                self.cmb_report_mag.blockSignals(True)
                self.cmb_report_mag.setCurrentIndex(row)
                self.cmb_report_mag.blockSignals(False)
        if st.get("target_bv") is not None:
            self.spn_target_bv.blockSignals(True)
            try:
                self.spn_target_bv.setValue(float(st["target_bv"]))
            except (TypeError, ValueError):
                pass
            self.spn_target_bv.blockSignals(False)
        self._bv_source = "assumed"
        self._radii_manual = bool(st.get("radii_manual", False))
        want_manual = bool(st.get("manual_centre", False))
        if self.chk_manual_centre.isChecked() != want_manual:
            self.chk_manual_centre.blockSignals(True)
            self.chk_manual_centre.setChecked(want_manual)
            self.chk_manual_centre.blockSignals(False)
        self._sync_centre_dialog()

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
            self._say(self.tr(
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

    def measured_facts(self, last=None):
        # The measurement of this plate in the shape the colour code reads
        # (core/chart_annotate.magnitude_role): the measurement's own numbers
        # and nothing else. The panel below and the window's band both use
        # it, so the two cannot disagree about what the measurement says.
        # @args: last - the measurement dict (default: the live one)
        # @return: the unified dict, or None when nothing is measured
        last = self._last if last is None else last
        if not last or last.get("mag") is None:
            return None
        check = last.get("check")
        return {"mag": last["mag"], "err": last.get("err"),
                "band": last.get("band"),
                "comps": len(last.get("used") or []) or None,
                "check_ok": (check or {}).get("ok") if check else None,
                "no_check": check is None,
                "clipped": bool(
                    (last.get("result") or {}).get("saturated")),
                "derived": bool(last.get("derived"))}

    def _on_sequence_changed(self):
        # The sequence moved under the live point: re-measure it with the
        # new zero point (a proposal or a hand edit both land here).
        # @return: None
        if self._last is not None:
            self._remeasure()

    def _remeasure(self):
        # Re-runs the current measurement with the current controls (the
        # aperture spins live-edit the result). The centre is the original
        # click plus the observer's nudge, NOT the refined centroid: adding
        # the offset to a value that already moved would double-count it.
        if self._last is None or not self._state.has_image:
            return
        entries = self._sequence()
        base = self._last.get("click") or (self._last["col"],
                                           self._last["row"])
        self._measure(base[0] + self._nudge[0], base[1] + self._nudge[1],
                      entries, click=base)

    def _nudge_step(self, dx, dy):
        # One 0.1 px step of the measurement centre. The pad is the only
        # way to move it, so the step is fine on purpose: the observer
        # places the centre by hand, and in manual mode the measurement
        # uses exactly that point.
        # @args: dx, dy - step in plate pixels
        if self._last is None:
            return
        self._nudge[0] += dx
        self._nudge[1] += dy
        self.lbl_nudge.setText(
            f"({self._nudge[0]:+.1f}, {self._nudge[1]:+.1f})")
        self._remeasure()

    def _reset_nudge(self):
        # Back to the clicked centre (no re-measure: the caller decides).
        self._nudge = [0.0, 0.0]
        self.lbl_nudge.setText("(0.0, 0.0)")

    def _on_nudge_reset(self):
        self._reset_nudge()
        self._remeasure()

    def _sync_centre_dialog(self):
        # The pad is visible only while the mode is on AND a plate is
        # loaded: the plate state may restore the box checked, and there is
        # nothing to place on an empty editor.
        show = bool(self.chk_manual_centre.isChecked()
                    and self._state.has_image)
        if show:
            self._centre.adjustSize()
        self._centre.setVisible(show)

    def _on_manual_centre(self, checked):
        # The checkbox owns the dialog: checking it opens the pad,
        # unchecking closes it, and both re-measure (the recipe changed).
        self._sync_centre_dialog()
        if checked and self._centre.isVisible():
            self._centre.raise_()
        self._remeasure()

    def _apertures(self, entries, image=None):
        # H3: when the seeing checkbox is on, measure the comps' FWHM on
        # the plate and scale the radii; the spins follow so the numbers
        # stay visible and tweakable. A hand edit wins until the next
        # plate (the observer's radii are never stomped).
        # @args: entries - the comparison sequence, image - where the seeing
        #        is measured (None: the plate itself; a track & stack passes
        #        its star stack, where the comps are points)
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
        fwhm = photometry.estimate_fwhm(
            image if image is not None else self._state.data, positions,
            sat_adu=sat)
        r_ap, r_in, r_out = photometry.aperture_for_fwhm(fwhm)
        if fwhm is not None:
            for spn, v in ((self.spn_rap, r_ap), (self.spn_rin, r_in),
                           (self.spn_rout, r_out)):
                spn.blockSignals(True)
                spn.setValue(v)
                spn.blockSignals(False)
        return (r_ap, r_in, r_out), fwhm

    def _saturation_override(self):
        # The Advanced «Saturation (ADU)» box is one knob for BOTH the
        # single measurement and a series: a positive value wins, 0 means
        # "use the config" (the header's SATURATE card, then ccd_saturate).
        # The camera profile's linearity gates separately and stays on.
        # @return: the ADU override, or None for auto
        try:
            value = float(self.spn_saturate.value())
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    def _update_saturate_hint(self):
        # Say what "0 = auto" resolves to, so the box never reads as if it
        # ignored the config: header SATURATE, then ccd_saturate, plus the
        # camera profile's linearity (the lower one gates first).
        from ..config import config
        lbl = getattr(self._advanced, "lbl_saturate_auto", None)
        if lbl is None:
            return
        override = self._saturation_override()
        if override is not None:
            lbl.setText(self.tr("override: {0} ADU").format(int(override)))
            return
        parts = []
        sat = photometry.saturation_ceiling(self._state.header or {}, config)
        if sat is not None:
            parts.append(self.tr("SATURATE/ccd_saturate {0} ADU")
                         .format(int(sat)))
        lin = photometry.linearity_ceiling(config)
        if lin is not None:
            parts.append(self.tr("camera linearity {0} ADU").format(int(lin)))
        lbl.setText(self.tr("auto: {0}").format(" · ".join(parts)) if parts
                    else self.tr("auto: no ceiling known (plateau only)"))

    def _pair_image(self):
        # @return: the star stack that goes with this plate, or None
        # A track & stack saves TWO files per observation: the object's stack
        # (its light, and the stars as TRAILS) and the star stack (the comps
        # as points, and the object as a trail). NS_PAIR carries the name of
        # the other one, so whichever is opened the tab knows its partner.
        # The comps read on the star stack and the target on the object's:
        # that is the only way a zero point means anything on this kind of
        # plate.
        header = getattr(self._state, "header", None) or {}
        name = header.get("NS_PAIR")
        if not name or not self._state.path:
            return None
        partner = Path(self._state.path).parent / str(name)
        if not partner.exists():
            return None
        try:
            from ..core import fits_io
            _header, data = fits_io.read_fits(str(partner))
            return np.ascontiguousarray(data, dtype=np.float32)
        except Exception as err:
            logger.warning("the pair %s could not be read: %s", partner, err)
            return None

    def _gain_measurement(self):
        # @return: (estimate, header) measured on the visit's own frames, or
        #          (None, None)
        # The same measurement the series engine makes (core/gain.py): two
        # frames of the same exposure say the conversion gain of the data
        # in hand. It costs two frame reads, so it is cached per visit and
        # only attempted when Ajustes carries no gain (the observer's
        # decision always wins, see core/gain.resolve). The header travels
        # with it because it is the header of the FRAMES (with their GAIN
        # card), not the stack's, and that is the key the store wants.
        from ..core import fits_io
        from ..core import gain as gain_mod
        ctx = self._series_context() or {}
        sid = ctx.get("session_id")
        paths = ctx.get("paths") or []
        if sid is None or not paths:
            return None, None
        cache = getattr(self, "_gain_est", None)
        if cache is None:
            cache = self._gain_est = {}
        if sid not in cache:
            header = None
            for path in paths[:3]:
                try:
                    header = fits_io.read_header(path)
                    break
                except Exception as err:            # never fatal
                    logger.warning("gain header failed: %s", err)
            try:
                estimate = gain_mod.estimate_from_paths(
                    paths, level_max=config.get("ccd_saturate"))
            except Exception as err:            # never fatal
                logger.warning("gain estimate failed: %s", err)
                estimate = None
            cache[sid] = (estimate, header)
        return cache[sid]

    def _resolve_gain(self):
        # @return: the resolved working gain {"gain", "ron", "source", ...}
        # The same chain the series walks (2026-10-08, ADR-072): Ajustes ->
        # the gain measured on the visit's frames -> the gain remembered for
        # this camera -> the header. The header is the LAST word and not the
        # first, because it can carry the camera's gain SETTING or a
        # placeholder (measured on the author's own frames: GAIN = 5,
        # EGAIN = 1.0, real gain 0.11 e-/ADU).
        from ..core import gain as gain_mod
        from ..core import gain_store
        from ..core.db import db
        estimate, frames_header = (None, None) \
            if config.get("ccd_gain") is not None else self._gain_measurement()
        remembered = None
        if config.get("ccd_gain") is None:
            try:
                remembered = gain_store.recall(db, self._state.header)
            except Exception as err:            # never fatal
                logger.warning("gain recall failed: %s", err)
        resolved = gain_mod.resolve(
            settings_gain=config.get("ccd_gain"),
            settings_ron=config.get("ccd_read_noise"),
            header=self._state.header, estimate=estimate,
            remembered=remembered)
        if resolved.get("source") == "remembered" and remembered is not None:
            resolved["remembered"] = remembered
        # a fresh measurement is worth remembering for the next plate, keyed
        # by the frames' own camera and setting (not the stack's)
        if resolved.get("source") == "frames" and frames_header is not None:
            try:
                gain_store.remember(db, frames_header, resolved)
            except Exception as err:            # never fatal
                logger.warning("gain remember failed: %s", err)
        return resolved

    def _measure(self, col, row, entries, click=None):
        # Build the recipe from the widgets and Ajustes, run the core
        # single-plate function (phase 1 of the series plan: one recipe,
        # shared with the series engine), and paint the outcome.
        from ..config import config
        # the star stack, when this plate is half of a track & stack pair:
        # the seeing is measured on IT too (there the comps are points, and
        # a FWHM taken from their trails would size the aperture with a
        # smear)
        pair = self._pair_image()
        radii, fwhm = self._apertures(entries, image=pair)
        if self._diff is not None:
            image, comp_image = self._diff, self._pair_obs
            comp_scale = self._diff_scale
        elif pair is not None:
            image, comp_image, comp_scale = self._state.data, pair, 1.0
            self._say(self.tr(
                "The comparison stars are read on the star stack of these "
                "same frames: on this plate they are trails."))
        else:
            image, comp_image, comp_scale = self._state.data, None, 1.0
        gain_report = self._resolve_gain()
        cfg = photometry.PlateConfig(
            target_xy=(col, row), entries=entries,
            header=self._state.header, wcs=self._state.wcs,
            band=self.cmb_band.currentText() or self._band,
            radii=radii, fwhm=fwhm,
            sigmaclip=self.chk_sigmaclip.isChecked(),
            # the measurement the LIVE tab shows follows the checkbox: the
            # default of the config is the filter, and a tab that ignored the
            # checkbox would measure with one method and say another
            matched=self.chk_matched.isChecked(),
            sky_mode=self.cmb_sky.currentData() or "median",
            color=self.chk_color.isChecked(),
            target_bv=self.spn_target_bv.value(),
            # the working gain: Ajustes -> measured on the visit's frames ->
            # header (2026-10-08); the header can lie, so it goes last
            gain=gain_report.get("gain"), ron=gain_report.get("ron"),
            gain_source=gain_report.get("source"),
            site_gain=config.get("ccd_gain"),
            site_ron=config.get("ccd_read_noise"),
            site_flat=config.get("flat_resid_mag", 0.007) or 0.007,
            site_saturate=(self._saturation_override()
                           or config.get("ccd_saturate")),
            centroid_mode=("none" if self.chk_manual_centre.isChecked()
                           else "gaussian"),
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
            self._say(reason)
            self._last = None
            self._drop_items()
            self._set_export_enabled(False)
            self.btn_save_project.setEnabled(False)
            return
        self._say("")
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
            "row": res.row,
            "click": click if click is not None else (col, row),
            "skipped": res.skipped,
            "bands_avail": res.bands_avail,
            "match": self._field_match(res.col, res.row),
            "sky_mode": res.sky_mode, "sigma_clip": res.sigma_clip,
            "gain_source": res.gain_source,
            "gain_remembered": gain_report.get("remembered"),
        }
        self._fill_panel(res.band, len(entries), len(res.used),
                         res.skipped, res.derived, res.gain)
        self._set_export_enabled(res.mag is not None)
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
        if self._series_attached:
            # which scopes this project offers (one visit, or all of them)
            self._sync_series_scope()
            self._fit_series_hint()
            # ... and once more when the layout has placed the block: the
            # width the label has at this instant is the one it had while
            # hidden, and a word-wrapped label asked for its height at the
            # wrong width comes out cut (measured in CI, 2026-10-01: 58 px
            # against the 118 its text needs).
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._fit_series_hint)
            self._update_series_counter(self._series_context() or {})
        if not self._series_attached and self._series_worker is not None:
            self._series_worker.cancel()
        if not self._series_attached and self._live_worker is not None:
            self._live_worker.cancel()
            self._live_worker = None
            self.chk_series_live.blockSignals(True)
            self.chk_series_live.setChecked(False)
            self.chk_series_live.blockSignals(False)

    def _fit_series_hint(self):
        # The block's header is a word-wrapped label, and a word-wrapped
        # QLabel does not always ask for the height its text needs: the
        # sizeHint is computed for a width that changes later. Measured in
        # the real panel: it reported 54 px for a text that needs four
        # lines, so the last one came out half cut ("...quality flags" with
        # the ")" missing). Asking the label itself, at its REAL width, is
        # the honest fix: the observer asked for that text to be readable.
        # @return: None
        lbl = getattr(self, "lbl_series_hint", None)
        # a width of a few pixels is not a width: a wrapped label asked for
        # its height at 1 px wants one line per word, which would blow the
        # block up. The resize event refits it once there is a real width.
        if lbl is None or not lbl.isVisible() or lbl.width() < 50:
            return
        need = lbl.heightForWidth(lbl.width())
        if need and need > 0:
            lbl.setMinimumHeight(int(need))

    def resizeEvent(self, event):
        # A wider or narrower panel needs another number of lines: the
        # header is refitted here, where the width is known.
        # @return: None
        super().resizeEvent(event)
        self._fit_series_hint()

    def _series_context(self, scope=None):
        # @args: scope - "visit" | "project" (None: the one the observer
        #        chose)
        # @return: the frames context {"paths", "session_id", ...} the host
        #          hooked, or None (ad-hoc open, or no frames for that
        #          scope)
        dlg = host_of(self)
        getter = getattr(dlg, "series_context", None)
        if not callable(getter):
            return None
        scope = scope or self._series_scope()
        try:
            return getter(scope)
        except TypeError:               # a host double with no scope
            return getter()

    def _series_scope(self):
        # @return: "visit" | "project" — which frames the series measures
        cmb = getattr(self, "cmb_series_scope", None)
        return (cmb.currentData() if cmb is not None else None) or "visit"

    def _sync_series_scope(self):
        # The selector is ALWAYS in the block: with one visit with frames
        # there is nothing to choose, so it stays there DISABLED and says
        # why (a control that disappears teaches nobody that the feature
        # exists, and the observer asked exactly that: "no veo lo del modo
        # multinoche, ¿dónde está?").
        # @return: None
        cmb = getattr(self, "cmb_series_scope", None)
        if cmb is None:
            return
        if not hasattr(self, "_scope_tip"):
            self._scope_tip = cmb.toolTip()
        ctx = self._series_context() or {}
        wide = int(ctx.get("visits") or 1) > 1
        cmb.setVisible(True)
        cmb.setEnabled(wide)
        cmb.setToolTip(self._scope_tip if wide else self.tr(
            "This project has one visit with frames, so there is nothing to "
            "choose yet: measure the next night and this becomes a choice "
            "between this visit and every visit of the project."))
        lbl = getattr(self, "lbl_series_scope", None)
        if lbl is not None:
            lbl.setVisible(True)
        if not wide and cmb.currentIndex() != 0:
            cmb.blockSignals(True)
            cmb.setCurrentIndex(0)
            cmb.blockSignals(False)
        self._sync_live_for_scope()

    def _on_series_scope_changed(self, _index):
        # A different scope is a different set of frames AND a different
        # curve: the chart follows, the counter says what will be measured,
        # and the live mode (which watches ONE folder) steps aside.
        # @return: None
        self._sync_live_for_scope()
        ctx = self._series_context() or {}
        self._update_series_counter(ctx)
        self._reload_visit_curve(say=False)
        if self._series_scope() == "project":
            self._say(self.tr(
                "All the visits: {0} night(s), {1} frames. One pass, one "
                "run per night; the chart shows the project's curve.").format(
                    ctx.get("nights") or 0, len(ctx.get("paths") or [])))
        else:
            self._say(self.tr(
                "This visit: {0} frame(s).").format(
                    len(ctx.get("paths") or [])))

    def _sync_live_for_scope(self):
        # Live mode watches the folder of ONE visit (tonight's): with the
        # whole project in scope it is turned off and disabled, saying why.
        # A disabled control that explains nothing is how a door looks
        # broken.
        # @return: None
        chk = getattr(self, "chk_series_live", None)
        if chk is None:
            return
        if not hasattr(self, "_live_tip"):
            self._live_tip = chk.toolTip()
        wide = self._series_scope() == "project"
        if wide and chk.isChecked():
            chk.setChecked(False)
        chk.setEnabled(not wide)
        chk.setToolTip(self.tr(
            "Live mode watches the folder of ONE visit (tonight's). With "
            "«all the visits» the frames come from every night, so live "
            "mode is off: choose «this visit» to watch tonight.")
            if wide else self._live_tip)
        btn = getattr(self, "btn_series_discard", None)
        if btn is not None:
            if not hasattr(self, "_discard_tip"):
                self._discard_tip = btn.toolTip()
            btn.setEnabled(not wide)
            btn.setToolTip(self.tr(
                "Discarding is per visit: open the visit whose curve you "
                "want to undo. With «all the visits» in scope there is no "
                "single night to undo.") if wide else self._discard_tip)

    def _series_target(self):
        # The target position on the open (reference) plate: the last
        # measured centroid, else the object's coordinates through the
        # plate's WCS (D17: no per-frame astrometry).
        # @return: (x, y) in plate pixels, or None
        if self._state.wcs is None:
            return None
        if self._last is not None and self._last.get("col") is not None:
            return (self._last["col"], self._last["row"])
        obj = getattr(host_of(self), "object", lambda: None)()
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
        # T3 (P2 #20): the per-night aperture sweep only runs when the
        # engine owns the radii, so the checkbox hands them over (radii
        # None) instead of pinning the spins on every night.
        auto = self._advanced.chk_auto_aperture.isChecked()
        return series_measure.SeriesConfig(
            wcs=self._state.wcs, target_xy=tuple(target_xy),
            comp_set=tuple(entries),
            band=self.cmb_band.currentText() or self._band,
            radii=None if auto else (self.spn_rap.value(),
                                     self.spn_rin.value(),
                                     self.spn_rout.value()),
            sigmaclip=self.chk_sigmaclip.isChecked(),
            matched=self.chk_matched.isChecked(),
            sky_mode=self.cmb_sky.currentData() or "median",
            color=self.chk_color.isChecked(),
            target_bv=self.spn_target_bv.value(),
            site_gain=config.get("ccd_gain"),
            site_ron=config.get("ccd_read_noise"),
            site_flat=config.get("flat_resid_mag", 0.007) or 0.007,
            site_saturate=self._saturation_override()
            or config.get("ccd_saturate"),
            site_lon=config.get("lon"), site_lat=config.get("lat"),
            site_aperture_m=float(config.get("aperture_inches", 10.0))
            * 0.0254,
            site_height_m=float(config.get("height", 0) or 0.0),
            site_linear=config.get("cam_linearity_adu"),
            site_dark=config.get("cam_dark_current_e_s"),
            group_n=int(self._advanced.spn_group_n.value()),
            auto_aperture=auto,
            seeing_aperture=self.chk_seeing.isChecked(),
            align=self._advanced.cmb_align.currentData() or "auto",
            detrend_policy=self._advanced.cmb_detrend.currentData()
            or "off")

    def _series_config_dict(self, cfg):
        # A JSON-safe echo of the config for the run row (audit trail).
        return {"band": cfg.band, "zp_mode": cfg.zp_mode,
                "detrend_policy": cfg.detrend_policy,
                "group_n": cfg.group_n,
                "auto_aperture": cfg.auto_aperture,
                "seeing_aperture": cfg.seeing_aperture,
                "align": cfg.align,
                "sigmaclip": cfg.sigmaclip, "sky_mode": cfg.sky_mode,
                "color": cfg.color, "target_bv": cfg.target_bv,
                "radii": list(cfg.radii) if cfg.radii else None,
                "target_xy": list(cfg.target_xy)}

    def _apply_kind_defaults(self):
        # D11: the type picks the parameters. A variable or a HADS star
        # gains from the honest airmass minimum; a transit must NOT be
        # detrended (the model and the trend are solved together in the
        # fit). Applied once, and only when the observer has not chosen.
        if self._kind_defaults_done:
            return
        self._kind_defaults_done = True
        if self._advanced.cmb_detrend.currentData() != "off":
            return
        kind = ((self._series_context() or {}).get("kind") or "").lower()
        if kind in ("variable", "hads"):
            self._advanced.cmb_detrend.setCurrentIndex(1)

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
            self._say(self.tr(
                "Cancelling the series: it stops after the frame it is "
                "measuring; the points measured so far are kept."))
            return
        ctx = self._series_context()
        if not ctx or not ctx.get("paths"):
            self._say(self.tr(
                "No visit with frames: open the editor from a visit to "
                "measure a series."))
            return
        entries = self._sequence()
        if not entries:
            self._say(self.tr(
                "No comparison sequence yet: build one above with "
                "«Build the sequence…»."))
            return
        if self._state.wcs is None:
            # ADR-051: solve the reference plate and start the series
            self._say(self.tr(
                "The plate has no WCS: solving it to place the series…"))
            dlg = host_of(self)
            req = getattr(dlg, "request_wcs", None)
            if callable(req):
                req(self._on_measure_series,
                    on_fail=lambda: self._say(self.tr(
                        "The plate has no WCS and it could not be solved: "
                        "the series cannot be placed.")))
                return
            self._say(self.tr(
                "The plate has no WCS and it could not be solved: the "
                "series cannot be placed."))
            return
        target = self._series_target()
        if target is None:
            self._say(self.tr(
                "Measure the target once (a click on it) so the series "
                "knows where to measure."))
            return
        self._apply_kind_defaults()
        self._series_cfg = self._series_config(entries, target)
        self._series_cfg_dict = self._series_config_dict(self._series_cfg)
        self._update_series_counter(ctx)
        self.prg_series.setRange(0, len(ctx["paths"]))
        self.prg_series.setValue(0)
        self._series_button_running(True)
        self.btn_series_undo.setEnabled(False)
        from .workers import SeriesWorker, hold
        self._series_worker = hold(SeriesWorker(ctx["paths"], self._series_cfg))
        self._series_worker.progress.connect(self._on_series_progress)
        self._series_worker.finished.connect(self._on_series_finished)
        self._series_worker.failed.connect(self._on_series_failed)
        self._series_worker.start()
        self._say(self.tr("Measuring the series…"))

    def _on_series_sci(self):
        # Save the curve AS YOU SEE IT (V3).
        #
        # It used to be a matplotlib figure drawn from the same points by
        # another renderer: the two could pick different windows (and they
        # did: the exported chart carried the 2 to 14 axis long after the
        # screen did not), and nothing the observer had framed on screen
        # survived into the file. A figure that disagrees with what you were
        # looking at is worse than no figure.
        #
        # The export renders the chart's own visible view, zoom included.
        # @return: None
        from PySide6.QtWidgets import QFileDialog
        from .. import paths as paths_mod
        # WHAT IS ON THE CHART is what this saves, whether it came from a
        # run of this session or from the visit's own curve (loaded from the
        # project's database): the button is "the chart IN THE VISIT". It
        # used to demand a run of this session, so with a loaded curve it
        # returned BEFORE opening the save dialog and the observer saw a
        # button that did nothing (reported: "the PNG export of the chart
        # does not work, the dialog does not even appear").
        if not self._series_payload:
            self._say(self.tr(
                "Measure the series first: the figure is the curve."))
            return
        name = ""
        window = host_of(self)
        obj = getattr(window, "object", None)
        if callable(obj):
            name = (obj() or {}).get("name") or ""
        start = paths_mod.data_dir()
        target, _sel = QFileDialog.getSaveFileName(
            self, self.tr("Save the chart"),
            str(start / "{0}_curva.png".format(
                (name or "series").replace(" ", "_"))),
            self.tr("PNG image (*.png)"))
        if not target:
            return
        try:
            out = self.chart_series.export_png(target)
        except Exception as err:                  # never a dead window
            logger.warning("chart export failed: %s", err)
            self._say(self.tr(
                "Could not write the chart: {0}").format(err))
            return
        self._say(self.tr(
            "Chart written as you see it: {0}").format(out))
        # ADR-045: the scene export registers like the other tabs' files
        dlg = host_of(self)
        notify = getattr(dlg, "notify_saved", None)
        if callable(notify):
            notify([out], "chart")

    def _series_subtitle(self, context):
        # The second line of the scientific figure: what a reader needs to
        # know about the night without asking.
        # @args: context - the visit context (paths, kind)
        # @return: the subtitle string
        n = len((context or {}).get("paths") or [])
        # the exposure can come from the run's own points (SeriesPoint) or
        # from the drawn payload (dicts, a curve loaded from the visit): a
        # curve on screen must be exportable without a run of this session
        points = (self._series_result.points if self._series_result
                  else self._series_payload)
        exps = []
        for p in points or []:
            exp = p.get("exptime") if isinstance(p, dict) \
                else getattr(p, "exptime", None)
            if exp:
                exps.append(exp)
                break
        bits = []
        if n:
            bits.append(self.tr("{0} frames").format(n))
        if exps:
            bits.append(self.tr("{0:g} s").format(exps[0]))
        band = (self.cmb_band.currentText() or "").strip()
        if band:
            bits.append(self.tr("band {0}").format(band))
        bits.append(self.tr("NightScribe"))
        return " · ".join(bits)

    def series_point_for(self, path, mjd=None, exptime=None):
        # The point of the curve measured on ONE frame: what the plate's
        # band shows as the measured magnitude, coloured by the point's own
        # numbers. Matched by the frame's path when the curve carries it
        # (a run of this session does), else by the time: the payload's mjd
        # is the MID exposure and the header's DATE-OBS is the start, so the
        # tolerance is one exposure.
        # @args: path - the open frame's path (str) or None, mjd - its
        #        mid-exposure MJD when known, exptime - its exposure in s
        # @return: the point dict ({"mag", "err", "filter", "comps",
        #          "flags"}) or None when this frame is not in the curve
        points = [p for p in (self._series_payload or [])
                  if p.get("source") == "measure" and p.get("mag") is not None]
        if not points:
            return None
        if path:
            for p in points:
                if p.get("path") and str(p["path"]) == str(path):
                    return p
        if mjd is not None:
            tol = max(float(exptime or 0.0) / 86400.0, 1.0 / 86400.0)
            best, dist = None, None
            for p in points:
                if p.get("mjd") is None:
                    continue
                d = abs(float(p["mjd"]) - float(mjd))
                if d <= tol and (dist is None or d < dist):
                    best, dist = p, d
            return best
        return None

    def _export_folder(self):
        # Where a series figure goes: the project's own folder, which the
        # HOST knows (the tab never touches the database: that is what this
        # file's other exports already do), and the app's data folder when
        # the editor was opened without a project.
        # @return: the folder (a Path), created if it did not exist
        from .. import paths as paths_mod
        folder = None
        ask = getattr(host_of(self), "export_folder", None)
        if callable(ask):
            try:
                folder = ask()
            except Exception as err:            # a hook never kills a tab
                logger.warning("export folder hook failed: %s", err)
        path = Path(folder) if folder else Path(paths_mod.data_dir())
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            logger.warning("could not create %s: %s", path, err)
            return Path(paths_mod.data_dir())
        return path

    def _on_series_night(self):
        # The two figures that explain the night (quality plan, A1): the
        # airmass and the measured position. They are written next to the
        # project and opened in the chart viewer, because a diagnosis the
        # observer cannot see is not a diagnosis.
        #
        # THEY NEED WHAT THE POINTS CARRY, not a run of this session: a
        # curve loaded from the visit brings them from the database (they
        # travel with the point since v14), and a point measured before
        # that has no airmass to draw. Each figure is written when its own
        # data is there, and what could not be drawn is said with its
        # reason instead of the button going quiet (reported: "the PNG
        # export of the chart does not work, the dialog does not even
        # appear": the guard demanded a run of this session and returned
        # before anything).
        points = (self._series_result.points if self._series_result
                  else self._series_payload)
        if not points:
            self._say(self.tr(
                "Measure the series first: the figures are its night."))
            return
        from ..viz import night_view

        def value(point, key):
            # @return: one field of a point, be it a SeriesPoint or a dict
            if isinstance(point, dict):
                return point.get(key)
            return getattr(point, key, None)

        has_air = any(value(p, "airmass") is not None for p in points)
        has_pos = any(value(p, "x") is not None and value(p, "y") is not None
                      for p in points)
        if not has_air and not has_pos:
            self._say(self.tr(
                "These points carry neither the airmass nor the measured "
                "position (they were measured before the app stored them): "
                "measure the series again to have the night figures."))
            return
        ctx = self._series_context() or {}
        # WHERE THE FIGURES GO, and the object's name: both asked of the
        # host, because THIS TAB NEVER TOUCHES THE DATABASE (every other
        # export here does the same). It used to call `project.get(db, pid)`
        # and `db` does not exist in this module: the button raised a
        # NameError inside its slot, Qt swallowed it and NOTHING happened
        # (reported: "el botón Night Conditions (PNG) no hace nada").
        folder = self._export_folder()
        name = "series"
        window = host_of(self)
        obj = getattr(window, "object", None)
        if callable(obj):
            name = (obj() or {}).get("name") or name
        stem = "".join(ch if ch.isalnum() or ch in "-_" else "_"
                       for ch in name)[:40]
        sub = self._series_subtitle(ctx)
        written = []
        try:
            if has_air:
                written.append(night_view.draw_airmass(
                    points, out=str(folder / "{0}_aire.png".format(stem)),
                    subtitle=sub, lang=self._lang))
            if has_pos:
                written.append(night_view.draw_drift(
                    points, out=str(folder / "{0}_deriva.png".format(stem)),
                    subtitle=sub, lang=self._lang))
        except Exception as err:                     # never a dead window
            logger.warning("night figures failed: %s", err)
            self._say(self.tr(
                "Could not write the night figures: {0}").format(err))
            return
        logger.info("night figures written: %s", ", ".join(written))
        text = self.tr("Night figures written: {0}").format(
            ", ".join(written))
        if not has_air:
            text += " " + self.tr(
                "The airmass figure is missing: these points do not carry "
                "it.")
        elif not has_pos:
            text += " " + self.tr(
                "The drift figure is missing: these points do not carry "
                "the measured position.")
        self._say(text)
        from .chart_viewer import open_chart
        for path in written:
            open_chart(self, path, title=self.tr("Night conditions"),
                       obj_name=name, chart_key="series-night")

    def _on_series_phase(self):
        # Quality plan (C): the period search opens from where the series
        # was measured too, on the PROJECT's curve (every visit), so the
        # observer does not have to hunt for the other door. The host arms
        # the hook when the editor came from a visit (ADR-045 rev).
        ctx = self._series_context() or {}
        pid = ctx.get("pid")
        dlg = host_of(self)
        opener = getattr(dlg, "open_phase", None)
        if pid and callable(opener) and opener(pid):
            return
        self._say(self.tr(
            "The period search works on a project's curve: open the "
            "editor from a project to reach it."))

    # ---------------- the chart's controls (quality plan, phase A) ------

    def _on_fix_axis(self, *_a):
        # The fixed magnitude range: the observer's own scale wins over
        # the robust automatic one, and it is what makes a hundredth of a
        # magnitude visible on a night.
        if not self.btn_series_fixaxis.isChecked():
            self.chart_series.clear_y_range()
            self._refresh_chart_notes()
            return
        lo = self.spn_series_maglo.value()
        hi = self.spn_series_maghi.value()
        if not self.chart_series.set_y_range(lo, hi):
            self.lbl_series_selection.setText(self.tr(
                "The fixed range is empty or inverted: the faintest "
                "magnitude must be larger than the brightest."))
            return
        self._update_selection_label()
        self._refresh_chart_notes()

    def _on_bin_changed(self, *_a):
        # The chart's binning and its mean curve (presentation only).
        self.chart_series.set_bin_mode(
            self.cmb_series_bin.currentData() or "off",
            self.spn_series_binn.value())
        self.chart_series.set_mean_curve(
            self.spn_series_meanwin.value()
            if self.chk_series_mean.isChecked() else 0)
        self._refresh_chart_notes()

    def _on_detect_outliers(self, *_a):
        # The detector runs on the plotted curve, with the threshold the
        # observer chooses; the candidates are only MARKED (never removed).
        if not self.chk_series_outliers.isChecked():
            self.chart_series.set_outliers([])
            self._update_selection_label()
            return
        from ..core import outliers as outliers_mod
        pts = self._series_measured()
        res = outliers_mod.outliers_in_points(
            pts, sigma=self.spn_series_outsigma.value())
        marked = [i for i, flag in enumerate(res["flags"]) if flag]
        self.chart_series.set_outliers(marked)
        self._update_selection_label()
        self._refresh_chart_notes()

    def _series_measured(self):
        # The measured points of the chart, in the same order the chart
        # holds them (so an index means the same thing in both places).
        # @return: [{"mjd", "mag", "err", "err_internal", "flags"}]
        return [p for p in (self._series_result.points
                            if self._series_result is not None else [])
                if p.mjd is not None and p.mag is not None]

    def _on_point_clicked(self, _idx):
        # The chart already toggled the selection; here we only refresh
        # the counter the observer reads.
        self._update_selection_label()

    def _on_exclude_outliers(self):
        # Excluding a marked point is a separate, explicit act: the mark
        # is red, this button takes it out of the curve and the file, and
        # «Restore all» puts it back.
        marked = self.chart_series.outliers()
        if not marked:
            self.lbl_series_selection.setText(self.tr(
                "No outlier is marked: switch the detector on first."))
            return
        self._set_excluded_pool(set(self.chart_series.excluded())
                                | set(marked))
        self._refresh_chart_notes()

    def _on_exclude_selected(self):
        chosen = self.chart_series.selected()
        if not chosen:
            self.lbl_series_selection.setText(self.tr(
                "No point selected: click one on the chart first."))
            return
        self._set_excluded_pool(set(self.chart_series.excluded())
                                | set(chosen))
        self._refresh_chart_notes()

    def _on_restore_all(self):
        self._set_excluded_pool(set())

    def _set_excluded_pool(self, pool):
        # Applies the exclusion to the CHART and to the points, flags it
        # (never deletes it) and redraws. The flag travels to the file, so
        # a curve shared with a colleague says what was left out and why.
        # @args: pool - set of indexes into _series_measured()
        pts = self._series_measured()
        for i, p in enumerate(pts):
            flags = [f for f in (p.flags or []) if f != "user_excluded"]
            if i in pool:
                flags.append("user_excluded")
            p.flags = flags
        self.chart_series.set_excluded(sorted(pool))
        self.chart_series.clear_selection()
        self._draw_series(self._series_result.points
                          if self._series_result is not None else [])
        self._update_selection_label()
        self._refresh_chart_notes()

    def set_visit_curve_hooks(self, load, clear):
        # The visit's curve, through its project (D): `load` answers with
        # the points this visit already has (read from the database, no
        # frames touched) and `clear` undoes every series run of the visit.
        # @args: load - callable() -> [point dicts] or None, clear -
        #        callable() -> (runs, points) or None
        # @return: None
        self._curve_load = load
        self._curve_clear = clear
        self.load_visit_curve()

    def load_visit_curve(self, say=True):
        # Draws the curve the visit ALREADY has, instead of an empty chart
        # (the observer's point: a light curve that was generated must not
        # be generated again). Measuring is still one click away, and a new
        # run replaces this one.
        #
        # Nothing is read from the frames and nothing is written: the points
        # come from the project's own database.
        # @args: say - whether to announce it in the status line (an action
        #        that has already said what it did passes False)
        # @return: the number of points drawn (0 when there were none)
        if self._curve_load is None or self._series_result is not None:
            return 0
        scope = self._series_scope()
        try:
            try:
                data = self._curve_load(scope) or []
            except TypeError:           # a host double with no scope
                data = self._curve_load() or []
        except Exception as err:                # a hook never kills a tab
            logger.warning("could not read the visit's curve: %s", err)
            return 0
        # The hook hands the points and, when it knows it, what the axis
        # measures. The run's own words are catalog/relative; the chart's
        # are calibrated/differential, so the translation lives here. The
        # plain list is the old shape: a host double may still send one.
        if isinstance(data, dict):
            points = data.get("points") or []
            mode = ("differential" if data.get("zp_mode") == "relative"
                    else "calibrated")
        else:
            points, mode = data, "calibrated"
        payload = [p for p in points if p.get("mjd") is not None
                   and p.get("mag") is not None]
        if not payload:
            return 0
        # the filter and the source come as the host shaped them: forcing
        # a "V" here made a curve calibrated in G say V in its legend, and
        # forcing the source dropped the detrended curve the run had
        own = [dict(p, source=p.get("source") or "measure")
               for p in payload]
        self._series_payload = own
        self._sync_series_scale(mode)
        self.chart_series.set_data(own, mag_mode=mode)
        self._apply_chart_presentation()
        self._curve_from_visit = True
        self._panel_summary = [self._visit_curve_line(len(own))]
        self._render_panel()
        self._update_selection_label()
        if say:
            self._say(self.tr(
                "Curve loaded from the visit: {0} points.").format(len(own)))
        return len(own)

    def _visit_passes_payload(self):
        # The passes of the visit, asked of the WINDOW (which owns the
        # project): the tab never touches the database. A host without the
        # hook (a test double, an ad-hoc open) simply has none.
        # @return: {"runs": [...], "curve_run_id": int|None} or {}
        ask = getattr(host_of(self), "visit_passes", None)
        if not callable(ask):
            return {}
        try:
            return dict(ask() or {})
        except Exception as err:
            logger.warning("could not read the visit's passes: %s", err)
            return {}

    def _visit_passes(self):
        # @return: the visit's passes, oldest first
        return list(self._visit_passes_payload().get("runs") or [])

    def _visit_curve_run_id(self):
        # @return: the run the visit is showing, or None
        return self._visit_passes_payload().get("curve_run_id")

    def _open_passes(self):
        # "Passes of this visit…": the night's passes and which one the
        # chart shows. The window is NON-modal: the point of going back to
        # a pass is to watch the chart change while choosing it.
        # @return: None
        payload = self._visit_passes_payload()
        if not payload:
            self._say(self.tr(
                "This chart does not belong to a visit: there are no passes "
                "to choose from."), "warn")
            return
        self._passes_dlg.show_passes(payload)

    def _use_pass(self, run_id):
        # "Make this the curve": the visit remembers which pass it shows.
        # Nothing is deleted and nothing is measured again, and the points
        # of the other passes stay in the project.
        # @args: run_id - the pass to draw
        # @return: None
        choose = getattr(host_of(self), "choose_visit_curve", None)
        if not callable(choose):
            return
        try:
            choose(run_id)
        except Exception as err:
            logger.warning("could not choose the curve's pass: %s", err)
            self._say(self.tr("Could not show that pass: {0}").format(err),
                      "error")
            return
        self._reload_visit_curve()

    def _undo_pass(self, run_id):
        # Undo ONE pass from the list (the same undo the button does, for
        # the pass the observer picked). Its points go, its row stays
        # marked undone and the chart falls back to the pass before it.
        # @args: run_id - the pass to undo
        # @return: None
        undo = getattr(host_of(self), "undo_run", None)
        count = 0
        if callable(undo):
            count = int(undo(run_id) or 0)
        self._say(self.tr("Pass undone: {0} points removed.").format(count))
        self._reload_visit_curve(say=False)

    def _reload_visit_curve(self, say=True):
        # Draws the visit's curve again after the passes changed: the chart
        # has to show what the visit shows NOW, not what it showed before.
        # @args: say - whether the reload announces itself (an action that
        #        has already said what it did keeps its own message)
        # @return: the number of points drawn
        self._series_result = None
        self._curve_from_visit = False
        self._series_payload = []
        self.btn_series_exoclock.setEnabled(False)
        n = self.load_visit_curve(say=say)
        if not n:
            self.chart_series.set_data([])
            self._panel_summary = []
            self._render_panel()
            self._update_selection_label()
        self._refresh_passes()
        return n

    def _refresh_passes(self):
        # The list, when it is open, follows every change (a pass undone,
        # a pass chosen): a window showing stale rows is worse than none.
        # @return: None
        if self._passes_dlg.isVisible():
            self._passes_dlg.set_passes(self._visit_passes_payload())

    def _visit_curve_line(self, n_points):
        # The line the panel shows for a curve that came from the project:
        # which pass it is AND how many other passes the visit holds. A
        # visit can hold several (measuring again with another band is
        # normal) and only one is drawn, so hiding the rest would make the
        # list of passes a secret. The door is named, because that is where
        # they are chosen.
        # @args: n_points - the points of the pass being drawn
        # @return: the panel's line
        runs = self._visit_passes()
        others = [r for r in runs
                  if r.get("id") != self._visit_curve_run_id()]
        if self._series_scope() == "project":
            return self.tr(
                "This chart is the WHOLE PROJECT: {0} points of every night "
                "(one pass per night). Choose «this visit» above to see the "
                "night you have open.").format(n_points)
        if not others:
            return self.tr(
                "This visit's curve: {0} points already measured with the "
                "sequence saved in the project (nothing was read from the "
                "frames). Measure the series again to build it from "
                "scratch, or discard it below.").format(n_points)
        points = sum(int(r.get("points") or 0) for r in others)
        return self.tr(
            "This visit's curve: {0} points, the pass the visit shows "
            "(nothing was read from the frames). The visit also holds {1} "
            "earlier pass(es) ({2} points) that are not drawn: choose "
            "another one in Series ▾ → Passes of this visit…").format(
                n_points, len(others), points)

    def _on_discard_curve(self):
        # "Discard this visit's curve, and build it again from scratch":
        # the SERIES runs of the visit are undone (their points go, their
        # run rows stay marked, the trail is never silent) and the chart
        # goes back to empty. Asked first: it is the night's work.
        # @return: None
        if self._curve_clear is None:
            self._say(self.tr(
                "This curve does not belong to a visit: there is nothing "
                "to discard."), "warn")
            return
        from PySide6.QtWidgets import QMessageBox
        answer = QMessageBox.question(
            self, self.tr("Discard the visit's curve"),
            self.tr("This undoes every series run of this visit: its "
                    "points go and the runs stay marked as undone. The "
                    "frames are untouched and you can measure again."),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        try:
            runs, points = self._curve_clear() or (0, 0)
        except Exception as err:
            logger.warning("could not discard the visit's curve: %s", err)
            self._say(self.tr("Could not discard the curve: {0}").format(
                err), "error")
            return
        self._series_result = None
        self._series_payload = []
        self._curve_from_visit = False
        self._panel_summary = []
        self.chart_series.set_data([])
        self.chart_series.set_outliers([])
        self.chart_series.set_excluded([])
        self.lbl_result.setText("–")
        self._update_selection_label()
        self._say(self.tr(
            "Curve discarded: {0} run(s) undone, {1} points removed. The "
            "frames are untouched.").format(runs, points))

    def clear_session(self):
        # A different project is a different session (issue report): the
        # previous series, its points, its panel and its undo must not
        # travel to the next one. Nothing is deleted: the points are in
        # their project.
        # @return: None
        if self._live_worker is not None:
            self._live_worker.cancel()
            self._live_worker = None
        self.chk_series_live.blockSignals(True)
        self.chk_series_live.setChecked(False)
        self.chk_series_live.blockSignals(False)
        self._series_result = None
        self._series_payload = []
        self._curve_from_visit = False
        self._live_points = []
        self._live_run_id = None
        self._live_run_ids = []
        self._panel_summary = []
        self._series_run_id = None
        self._last = None
        self._diff = None
        self._pair_obs = None
        self._sub_report = None
        self._last_suggestions = []
        self.chart_series.set_data([])
        self.chart_series.set_outliers([])
        self.chart_series.set_excluded([])
        self.chart_series.clear_selection()
        self.chart_series.reset_view()
        self.lbl_result.setText("–")
        self.btn_series_undo.setEnabled(False)
        self.btn_series_exoclock.setEnabled(False)
        self._update_selection_label()

    def _apply_chart_presentation(self):
        # What the CONTROLS say, the chart does, as soon as there is
        # something to draw.
        #
        # Each control is wired to its slot, but a slot only fires when the
        # control CHANGES: their initial state (the trend on by default, the
        # error bars, the flagged points, the binning) was never pushed, and
        # a freshly measured series came out with none of it (reported: "the
        # mean is ticked but it is not painted when the curve is
        # generated"). Pushing the whole state after every set_data makes
        # the chart and its controls say the same thing, always.
        # @return: None
        self.chart_series.set_robust(self.btn_series_robust.isChecked())
        self.chart_series.set_errors_visible(
            self.btn_series_errors.isChecked())
        self.chart_series.set_hide_flagged(
            self.btn_series_hideflags.isChecked())
        self.chart_series.set_quality_colours(
            self.btn_series_quality.isChecked())
        self.chart_series.set_bin_mode(
            self.cmb_series_bin.currentData() or "off",
            self.spn_series_binn.value())
        self.chart_series.set_mean_curve(
            self.spn_series_meanwin.value()
            if self.chk_series_mean.isChecked() else 0)
        if self.btn_series_fixaxis.isChecked():
            self._on_fix_axis()
        if self.chk_series_outliers.isChecked():
            self._on_detect_outliers()

    def _render_panel(self):
        # The panel's text, in one place: the run's summary and the chart's
        # OWN notes, rebuilt together.
        #
        # The notes (what the chart clipped, what it left out of this scale,
        # which series the axis is not showing, the mean curve...) used to be
        # written once, when the run finished. Marking outliers or excluding
        # points afterwards left them stale, and the observer read a panel
        # that described a chart they no longer had. A full rewrite on every
        # change is cheap and cannot accumulate.
        # @return: None
        lines = list(getattr(self, "_panel_summary", None) or [])
        notes = self.chart_series.notes()
        if notes:
            if lines:
                lines.append("")             # the chart's own block
            lines += ["· " + n for n in notes]
        if not lines:
            self.lbl_result.setText("–")
            # An empty box is furniture: with nothing measured the panel and
            # its actions are not there at all (ADR-038 rev: on entering, the
            # action is what the observer sees). They come back the moment
            # there is a line.
            self._sections["result"].setVisible(False)
            return
        self._sections["result"].setVisible(True)
        # the news rides the header of the (closed) group: the magnitude of
        # this plate, so the observer reads it without opening the panel
        # (asked for 2026-10-06: a group that holds something says so)
        self._sections["result"].setNotice(self._result_badge())
        # THE PANEL WEARS THE SAME COLOUR CODE AS THE BAND: the lines that
        # carry a magnitude keep their role (see _fill_panel) and the rest is
        # plain text. It goes out as HTML with everything escaped, so the
        # panel's plain text (what the observer copies and the tests read) is
        # exactly what it was.
        import html as _html
        roles = getattr(self, "_panel_roles", None) or {}
        out = []
        for line in lines:
            role = roles.get(line) or roles.get(line[2:].strip())
            colour = palette.MEASURE_COLOURS.get(role) if role else None
            if colour:
                out.append('<span style="color:{0}">{1}</span>'.format(
                    colour, _html.escape(line)))
            else:
                out.append(_html.escape(line))
        self.lbl_result.setHtml("<br>".join(out))

    def _refresh_chart_notes(self):
        # Called by every control that changes what the chart shows: the
        # panel must describe the chart that is on screen NOW.
        # @return: None
        self._render_panel()

    def _update_selection_label(self):
        # The counter under the chart: how many are selected, excluded and
        # marked, so nothing happens off-screen.
        n_sel = len(self.chart_series.selected())
        n_exc = len(self.chart_series.excluded())
        n_out = len(self.chart_series.outliers())
        self.lbl_series_selection.setText(self.tr(
            "{0} selected · {1} excluded · {2} marked").format(
                n_sel, n_exc, n_out))

    def _on_series_progress(self, done, total):
        self.prg_series.setRange(0, total)
        self.prg_series.setValue(done)

    def _on_series_finished(self, result):
        self._series_button_running(False)
        self._series_worker = None
        context = self._series_context() or {}
        self._update_series_counter(context, result.points)
        if result.status == "incomplete":
            self._say(self.tr(
                "Series cancelled: it stays “incomplete”; the points "
                "measured so far are kept."))
        else:
            self._say("")
        rows = self._series_rows(result.points)
        dlg = host_of(self)
        notify = getattr(dlg, "notify_points", None)
        self._series_run_id = None
        if callable(notify) and rows:
            # D18: the run's real status rides in the echo, so the host
            # stores a cancelled series as "incomplete", never "complete".
            echo = dict(self._series_cfg_dict or {})
            echo["status"] = result.status
            # the audit trail keeps how the frames were brought onto the
            # reference grid and what the comparison stars really did
            echo["alignment"] = _echo_report(result.align_report, 8)
            echo["comparisons"] = _echo_report(result.comp_report)
            echo["gain"] = _echo_report(result.gain_report)
            try:
                self._series_run_id = notify(rows, echo)
            except Exception as err:
                logger.warning("series save failed: %s", err)
        self.btn_series_undo.setEnabled(self._series_run_id is not None)
        self.btn_series_exoclock.setEnabled(
            result.status == "complete"
            and any(p.mag is not None for p in result.points))
        self._series_result = result
        self._draw_series(result.points)
        if result.points:
            # the curve in front, because this is the moment it is wanted
            # (and not on an empty or cancelled run: taking the observer's
            # place away with nothing to show would be rude)
            self._show_curve()
        self._fill_series_panel(result, context)
        # a new pass is the curve now: the list, if it is open, follows
        self._refresh_passes()

    def _night_label(self, night):
        # The engine keys its per-night blocks by the observing night
        # (ADR-048: the boundary sits at noon), and that key is a raw MJD;
        # the observer reads the evening's civil date instead. Anything
        # that is not an MJD (a date the engine already wrote, None) rides
        # through as it came.
        # @args: night - the engine's night key (an MJD, a string or None)
        # @return: the panel's label, e.g. "2026-09-20"
        try:
            mjd = float(night)
        except (TypeError, ValueError):
            return str(night)
        from ..core import variables
        # noon UTC of that night: the civil date the evening started on
        return coords.datetime_from_jd(
            mjd + 0.5 + variables.MJD0).strftime("%Y-%m-%d")

    def _fill_series_panel(self, result, context):
        # Plain-language summary (D13/D25/D35/D20): points and frames,
        # the flags, the aperture the sweep chose per night (T3), the
        # detrend coefficients per night, the cadence guard, the
        # multi-night zero-point / band warnings and the frames that
        # never made it onto the curve (P2 #22: nothing drops silently).
        # Nights are named by their civil date (P3), never by raw MJD.
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
        # T3 (P2 #20): the sweep's answer, one line per night, so the
        # observer sees the aperture the curve was actually measured with
        apertures = result.apertures or {}
        for night in sorted(apertures, key=lambda n: (n is None, n)):
            ap = apertures[night]
            if ap.get("fwhm") is None:
                lines.append(self.tr(
                    "Night {0}: aperture k = {1:.1f} (check-star scatter "
                    "{2:.4f} mag)").format(self._night_label(night),
                                           ap.get("k") or 0.0,
                                           ap.get("rms") or 0.0))
            else:
                lines.append(self.tr(
                    "Night {0}: aperture k = {1:.1f} (seeing {2:.1f} px, "
                    "check-star scatter {3:.4f} mag)").format(
                        self._night_label(night), ap.get("k") or 0.0,
                        ap["fwhm"], ap.get("rms") or 0.0))
        det = result.detrend
        if det:
            for n in det.get("nights", []):
                if n.get("fallback"):
                    lines.append(self.tr(
                        "Night {0}: no airmass range, offset only "
                        "({1} points); its level against the other "
                        "nights is lost").format(
                            self._night_label(n["night"]), n["n"]))
                else:
                    lines.append(self.tr(
                        "Night {0}: a1={1:.3f}, a2={2:+.3f}, a3={3:.3f} "
                        "(rms {4:.4f} → {5:.4f})").format(
                            self._night_label(n["night"]), n["a1"], n["a2"],
                            n["a3"], n["rms_before"] or 0.0,
                            n["rms_after"] or 0.0))
        ctxd = (context or {}).get("context") or {}
        transit = ctxd.get("transit") or {}
        guard = series_measure.cadence_guard(
            points, (context or {}).get("kind"),
            duration_h=ctxd.get("duration_h") or transit.get("duration_h"),
            period_h=ctxd.get("period_h"),
            period_d=ctxd.get("period_d") or ctxd.get("period"))
        qc = series_measure.night_qc(points)
        # D44: how the frames were brought onto the reference grid, in the
        # observer's language (a series that drifted is the rule, not the
        # exception, and it must not be silent)
        for m in series_measure.align_messages(result.align_report):
            lines.append("· " + m.get(self._lang, m.get("en", "")))
        for m in series_measure.comp_messages(result.comp_report,
                                              len(points)):
            lines.append("· " + m.get(self._lang, m.get("en", "")))
        for m in series_measure.seeing_messages(result.seeing_report,
                                                result.aperture_report):
            lines.append("· " + m.get(self._lang, m.get("en", "")))
        for m in result.model_notes or []:
            lines.append("· " + m.get(self._lang, m.get("en", "")))
        if guard["level"] == "red":
            lines.append("⚠ " + self.tr(
                "Cadence too short for the transit ingress"))
        for m in guard["messages"] + qc["messages"]:
            lines.append("⚠ " + m.get(self._lang, m.get("en", "")))
        # P2 #22: the frames that never reached the curve are named, never
        # dropped in silence (undated points and unreadable files)
        nodate = [p for p in points if p.mjd is None]
        if nodate:
            n_frames = sum(len(p.members or [p.path]) for p in nodate)
            lines.append("⚠ " + self.tr(
                "{0} frame(s) had no DATE-OBS and were not timed: they "
                "are not on the curve").format(n_frames))
        errors = result.errors or {}
        if errors:
            lines.append("⚠ " + self.tr(
                "{0} frame(s) could not be read: they are not on the "
                "curve").format(len(errors)))
            for path, err in sorted(errors.items())[:5]:
                lines.append("· " + self.tr(
                    "Frame {0} could not be read: {1}").format(
                        Path(path).name, self._plain_engine_error(err)))
        # the run's own summary is KEPT (not painted yet): the panel always
        # renders summary + the chart's current notes, so marking an outlier
        # cannot leave a stale line behind (see _render_panel)
        self._panel_summary = list(lines)
        self._render_panel()

    def _plain_engine_error(self, err):
        # The engine reports its read failures in technical English (core
        # has no tr()): the panel says them in the user's language. The
        # mapping is deliberately small and anything unknown rides through
        # as the engine wrote it.
        # @args: err - the engine's error string
        # @return: the plain message for the panel
        low = str(err or "").lower()
        if "empty" in low:
            return self.tr("the file is empty")
        if "truncat" in low:
            return self.tr("the file is truncated (was it still being "
                           "written?)")
        if "no image hdu" in low:
            return self.tr("the file has no image")
        if "bitpix" in low:
            return self.tr("the pixel format is not supported")
        if "cannot read" in low:
            return self.tr("the file could not be read")
        return str(err)

    def _on_series_failed(self, message):
        # A failed run is OVER: the button comes back, the progress bar goes
        # back to zero and the reason goes to the status line. Leaving the
        # bar frozen where the engine died (13 % of a real run) is what made
        # a plain failure look like a hang: the observer sees a stuck bar
        # and a log they do not read, and concludes the app died.
        # @args: message - the worker's own error text (technical on
        #        purpose: a crash is a bug report, and hiding it helps
        #        nobody)
        # @return: None
        self._series_button_running(False)
        self._series_worker = None
        self.prg_series.setValue(0)
        self._say(self.tr(
            "The series failed and stopped: {0}").format(message))

    def _series_rows(self, points):
        # The rows the host persists (one run, one batch). The shape belongs
        # to the engine: a pass writes the same one.
        #
        # Each row says WHICH VISIT its frame belongs to (the context knows:
        # the same frame can be registered in more than one visit, which is
        # what the observer's own project does), so a multi-night pass files
        # every night's points in that night's visit.
        # @args: points - the measured SeriesPoints
        # @return: the rows
        rows = series_measure.series_rows(points)
        by_path = (self._series_context() or {}).get("path_sessions") or {}
        for row in rows:
            visit = by_path.get(row.get("path"))
            if visit is not None:
                row["session_id"] = visit
        return rows

    def _draw_series(self, points):
        # Raw + detrended, flagged points as hollow diamonds (D13/T7).
        # the payload carries which frame each point came from and how many
        # comparisons hold it: the plate's band reads the point of the OPEN
        # frame from here (its measured magnitude and its own colour code)
        raw = [{"mjd": p.mjd, "mag": p.mag, "err": p.err,
                "filter": p.filter, "source": "measure",
                "path": p.path, "comps": p.n_comps, "exptime": p.exptime,
                "flags": list(p.flags),
                # the night travels with the point: the night figures and
                # the band's context read it from here (v14)
                "airmass": p.airmass, "x": p.x, "y": p.y,
                "fwhm": p.fwhm, "sky": p.sky}
               for p in points if p.mjd is not None and p.mag is not None]
        det = [{"mjd": p.mjd, "mag": p.mag_detrended, "err": p.err,
                "filter": p.filter, "source": "detrend",
                "path": p.path, "comps": p.n_comps, "exptime": p.exptime,
                "flags": list(p.flags),
                "airmass": p.airmass, "x": p.x, "y": p.y,
                "fwhm": p.fwhm, "sky": p.sky}
               for p in points if p.mjd is not None
               and p.mag_detrended is not None]
        self._series_payload = _decimate(raw) + _decimate(det)
        # which axis the measurement calls for: a calibrated run gives
        # absolute magnitudes, a relative one already gives differences
        result = self._series_result
        mode = ("differential" if result is not None
                and getattr(result, "zp_mode", "catalog") == "relative"
                else "calibrated")
        self._sync_series_scale(mode)
        self.chart_series.set_data(self._series_payload, mag_mode=mode)
        self._apply_chart_presentation()

    def _on_series_scale_changed(self, _index):
        # The observer changed what the axis measures. The chart rebuilds
        # itself; the only thing said out loud is a fixed range being
        # dropped, because a range written in magnitudes means nothing on a
        # differential axis and silently reinterpreting it would rescale
        # the chart into nonsense.
        mode = self.cmb_series_scale.currentData() or "calibrated"
        had_range = self.chart_series.is_y_range_fixed() is not None
        if not self.chart_series.set_mag_mode(mode):
            return
        self._refresh_chart_notes()
        if had_range:
            self.btn_series_fixaxis.setChecked(False)
            self._say(self.tr(
                "Fixed magnitude range cleared: the axis changed what it "
                "measures."))

    def _sync_series_scale(self, mode):
        # Mirrors the mode the measurement implies into the control,
        # without re-firing the handler.
        self.cmb_series_scale.blockSignals(True)
        idx = self.cmb_series_scale.findData(mode)
        if idx >= 0:
            self.cmb_series_scale.setCurrentIndex(idx)
        self.cmb_series_scale.blockSignals(False)

    def _on_series_enlarge(self):
        # "Show me this properly": the curve lives in the CENTRE of the
        # window now, so this only brings it to the front (V2). There is no
        # second copy in another window to disagree with this one.
        # @return: None
        if not self._series_payload:
            return
        self._show_curve()
        self.chart_series.fit_to_scene()

    def _open_series_chart(self):
        # The chart's controls, non-modal: the point of the window is to
        # keep looking at the curve while changing how it is drawn.
        # @return: None
        self._series_dlg.show_nonmodal()

    def _show_curve(self):
        # Asks the window for the centre's curve page. The tab does not
        # know the window's layout (a dialog is not always the parent, so
        # the guard is honest about it).
        # @return: True when the curve is in front
        show = getattr(host_of(self), "show_curve", None)
        if callable(show):
            show()
            return True
        return False

    def _on_series_exoclock(self):
        # D30/D41: prepare the manual ExoClock submission from the last
        # run, open the upload page and let the host record the outcome.
        from ..core import exoclock_export
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        result = self._series_result
        if result is None or not result.points:
            self._say(self.tr("Measure the series first."))
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
            self._say("⚠ " + " · ".join(lines))
        planet = ""
        obj = getattr(host_of(self), "object", lambda: None)()
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
        # the transit window (when the project carries one) selects the
        # out-of-transit points for the reference flux
        t0_mjd, dur_d = None, None
        ctxd = (self._series_context() or {}).get("context") or {}
        transit = ctxd.get("transit") or {}
        try:
            if transit.get("t0") is not None:
                from ..core import variables as _vars
                t0_mjd = float(transit["t0"]) - _vars.MJD0
                dur_d = float(transit.get("duration_h") or 0.0) / 24.0
        except (TypeError, ValueError):
            t0_mjd, dur_d = None, None
        # P2 #23b: the write can fail (permissions, a full disk, a file
        # held by another app); the observer reads why and nothing else
        # happens (no upload page, no run registered as saved)
        try:
            exoclock_export.write_submission(
                pts, out, planet or "target",
                self.cmb_band.currentText() or self._band or "", expt, note,
                t0_mjd=t0_mjd, duration_d=dur_d)
        except Exception as err:
            logger.warning("exoclock export failed: %s", err)
            self._say(self.tr(
                "The ExoClock files could not be written: {0}").format(err))
            return
        self._say(
            self.tr("ExoClock files written. Upload them at exoclock.space"))
        notify = getattr(host_of(self), "notify_saved", None)
        if callable(notify):
            notify([out], "report")
        hook = getattr(host_of(self), "notify_exoclock", None)
        if callable(hook):
            hook({"planet": planet, "points": len(pts)})
        QDesktopServices.openUrl(QUrl("https://exoclock.space/upload/"))

    def _on_series_undo(self):
        # D6: undo this run only; never the visit. A live session is one
        # run too (ADR-050, P2 #19): its batches are undone together.
        # @return: None; the outcome shows in the status line.
        run_ids = ([self._series_run_id]
                   if self._series_run_id is not None else [])
        run_ids += list(self._live_run_ids)
        if not run_ids:
            return
        dlg = host_of(self)
        undo = getattr(dlg, "undo_run", None)
        count = 0
        if callable(undo):
            for run_id in run_ids:
                count += int(undo(run_id) or 0)
        self._say(
            self.tr("Run undone: {0} points removed.").format(count))
        self._series_run_id = None
        self._live_run_id = None
        self._live_run_ids = []
        self._live_points = []
        self.btn_series_undo.setEnabled(False)
        self._series_result = None
        self.btn_series_exoclock.setEnabled(False)
        self._series_payload = []
        self.chart_series.set_data([])
        # the visit may hold earlier passes: undoing the last one has to
        # bring the previous curve back (that is what the passes list is
        # for, and what the observer asked for)
        self._reload_visit_curve()

    def _on_series_live_toggled(self, checked):
        # D21 (opt-in, off by default): watch the visit folder and measure
        # each new batch with the same engine; the curve grows live.
        if not checked:
            if self._live_worker is not None:
                self._live_worker.cancel()
                self._live_worker = None
            self._say(self.tr("Live mode off."))
            return
        ctx = self._series_context()
        entries = self._sequence()
        target = self._series_target()
        if not ctx or not ctx.get("paths") or not entries or target is None:
            self._say(self.tr(
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
        # a new session is a new undoable run (P2 #19), and its batches
        # pile into it
        self._live_run_id = None
        self._live_run_ids = []
        self.btn_series_undo.setEnabled(self._series_run_id is not None)
        from .workers import LiveSeriesWorker, hold
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
        self._live_worker = hold(LiveSeriesWorker(
            folder, self._series_cfg, batch_n=grp, batch_s=grp * exp_s))
        # every line the observer reads is translated here (the driver
        # reports stage keys and its errors, never wording: P2 #19)
        self._live_worker.progress.connect(self._on_live_progress)
        self._live_worker.batch.connect(self._on_live_batch)
        self._live_worker.batch_failed.connect(self._on_live_batch_failed)
        self._live_worker.failed.connect(self._on_live_failed)
        self._live_worker.start()
        self._say(self.tr(
            "Live mode on: watching the visit folder…"))

    def _on_live_batch(self, result):
        # A committed batch: persist it as a run and grow the curve. The
        # run ids pile up: the whole live session is undone as one run
        # (ADR-050, P2 #19), exactly like a normal series.
        # @args: result - the batch's SeriesResult
        # @return: None; the curve and the counter follow.
        rows = self._series_rows(result.points)
        dlg = host_of(self)
        notify = getattr(dlg, "notify_points", None)
        if callable(notify) and rows:
            echo = dict(self._series_cfg_dict or {})
            if self._live_run_id is not None:
                # one live session, ONE run: its batches pile into the run
                # the first one opened. Two reasons, both measured: the
                # whole session is undone with one click, and the curve
                # reloaded from the project is the whole session instead of
                # just its last batch.
                echo["append_run"] = self._live_run_id
            try:
                run_id = notify(rows, echo)
            except Exception as err:
                logger.warning("live save failed: %s", err)
                run_id = None
            if run_id is not None:
                self._live_run_id = run_id
                if run_id not in self._live_run_ids:
                    self._live_run_ids.append(run_id)
                self.btn_series_undo.setEnabled(True)
        self._live_points.extend(result.points)
        # live mode is watching the curve grow: put it in front
        self._show_curve()
        self._draw_series(self._live_points)
        self._update_series_counter(self._series_context() or {},
                                    self._live_points)
        self._refresh_passes()

    def _on_live_progress(self, key, frames):
        # The driver reports stage keys (core has no tr()): the panel owns
        # the wording, so every line the observer reads goes through tr().
        # @args: key - "added" | "stopped", frames - frames of the stage
        # @return: None; the outcome shows in the status line.
        if key == "added":
            self._say(self.tr(
                "Live: {0} new frame(s) in the folder").format(frames))
        elif key == "stopped":
            self._say(self.tr("Live mode stopped."))

    def _on_live_batch_failed(self, message, frames):
        # A batch the engine refused is lost: it is said out loud (P2 #19)
        # while the watch goes on with the next frames.
        # @args: message - the engine's error, frames - frames lost
        # @return: None; the outcome shows in the status line.
        logger.warning("live batch lost (%s frame(s)): %s", frames, message)
        self._say(self.tr(
            "Live batch lost: {0} frame(s) were not measured ({1})").format(
                frames, message))

    def _on_live_failed(self, message):
        # The watch itself died (the folder went away, the engine could
        # not be imported): the observer reads it, never a silent stop, and
        # the progress bar stops pretending the watch is still running.
        # @args: message - the worker's error text
        # @return: None; the outcome shows in the status line.
        self._live_worker = None
        # the checkbox goes back off, without re-firing its handler (the
        # watch is already dead; toggling it would try to stop it again)
        self.chk_series_live.blockSignals(True)
        self.chk_series_live.setChecked(False)
        self.chk_series_live.blockSignals(False)
        self.prg_series.setValue(0)
        self._say(
            self.tr("Live mode failed and stopped: {0}").format(message))

    def _open_series_docs(self):
        # D37: the "?" opens the sequences guide in the docs browser.
        from .. import paths as paths_mod
        from .doc_viewer import open_browser
        root = paths_mod.docs_dir()
        name = "SEQUENCES.es.md" if self._lang != "en" else "SEQUENCES.md"
        start = root / name if (root / name).exists() else None
        open_browser(root, host_of(self), start=start)

    def _restore_advanced_defaults(self):
        # D25: every knob back to the .ui's shipped default.
        self.cmb_sky.setCurrentIndex(0)
        self.chk_sigmaclip.setChecked(True)
        self.chk_seeing.setChecked(True)
        self.chk_color.setChecked(True)
        self.spn_target_bv.setValue(0.0)
        self.chk_subtract.setChecked(False)
        self._advanced.spn_group_n.setValue(1)
        self._advanced.cmb_align.setCurrentIndex(0)
        self._advanced.cmb_detrend.setCurrentIndex(0)
        self._advanced.chk_auto_aperture.setChecked(False)
        self._advanced.spn_saturate.setValue(0.0)
        self.chk_manual_centre.setChecked(False)
        self._say(self.tr("Advanced defaults restored."))

    # ------------------------------------------------------------- panel

    def _fill_panel(self, band, n_seq, n_used, skipped, derived, gain):
        # The result block, in plain language and with every caveat that
        # applies (ADR-038: the panel says what was used and what was not).
        self._panel_roles = {}       # line text -> the role that colours it
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
        # THE CEILING THE RULE COULD NOT ENFORCE (ADR-066): with the camera's
        # linearity unset, a star over it but under the plate's clip slips
        # through, and the observer has to know which limit is really being
        # applied. Said here, where the zero point is read.
        warning = photometry.ceiling_warning(self._state.header or {},
                                             config)
        if warning is not None:
            lines.append("⚠ " + warning.get(self._lang, warning["en"]))
        if last["mag"] is not None:
            err_txt = (self.tr("± {0:.3f}").format(last["err"])
                       if last["err"] is not None else "")
            text = self.tr("Magnitude: {0:.3f} {1} ({2})").format(
                last["mag"], err_txt, band)
            lines.append(text)
            # THE SAME COLOUR CODE AS THE PLATE'S BAND: the measured
            # magnitude of the target wears its role (green clean, orange
            # usable, red doubtful), from the same rule and the same palette
            role = chart_annotate.magnitude_role(self.measured_facts())
            if role:
                self._panel_roles[text] = role
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
            # the cross-matched magnitude IS a catalogue value: white, the
            # same role the band gives it
            notes.append(txt)
            self._panel_roles[txt] = chart_annotate.ROLE_MAG_CAT
        else:
            notes.append(self.tr(
                "No catalogued source within 8″ of the target "
                "(a new object?)"))
        click = last.get("click")
        if self.chk_manual_centre.isChecked():
            # In manual mode there is no centroid to report: the aperture
            # sits exactly where the observer put it.
            notes.append(self.tr(
                "manual centre: measured exactly where you placed it "
                "(no centroid)"))
        elif click is not None:
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
                "No gain anywhere (settings, your own frames or the "
                "header): the photon noise is not in the error"))
        else:
            from ..core import gain as gain_mod
            src = gain_mod.source_label(last.get("gain_source"), self._lang)
            if src:
                notes.append(self.tr("Gain {0} e-/ADU ({1})")
                             .format("{:.3g}".format(float(gain)), src))
            rec = last.get("gain_remembered")
            if rec:
                from ..core import gain_store
                said = gain_store.summary(rec, self._lang)
                if said:
                    notes.append(said.get(self._lang) or said["en"])
        if last["scint"] is not None:
            notes.append(self.tr(
                "Scintillation included ({0:.3f} mag)")
                .format(last["scint"]))
        if self._diff is not None:
            notes.append(self.tr(
                "Host galaxy subtracted (PS1 reference aligned on the "
                "frame's stars and scaled by the comps)"))
            rep = self._sub_report or {}
            if not rep.get("trusted", True):
                n = rep.get("n_stars") or 0
                rms = rep.get("rms_px")
                if rms is not None:
                    notes.append(self.tr(
                        "⚠ Reference alignment uncertain ({0} stars, "
                        "{1:.1f} px): the subtraction may leave star "
                        "residuals").format(n, rms))
                else:
                    notes.append(self.tr(
                        "⚠ Reference alignment uncertain: the subtraction "
                        "may leave star residuals"))
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
        # the run's own summary is KEPT (not painted yet): the panel always
        # renders summary + the chart's current notes, so marking an outlier
        # cannot leave a stale line behind (see _render_panel)
        self._panel_summary = list(lines)
        self._render_panel()

    # ---------------------------------------------------------- overlays

    def _result_badge(self):
        # @return: the short news for the "Measurement" group's header: the
        #          magnitude just measured (the number the observer came
        #          for), or "new" when there is a result without one.
        last = getattr(self, "_last", None) or {}
        mag = last.get("mag")
        if mag is not None:
            band = str(last.get("band") or "")
            return f"{float(mag):.3f} {band}".strip()
        return self.tr("new")

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
        if not self._state.has_image:
            self.chk_subtract.blockSignals(True)
            self.chk_subtract.setChecked(False)
            self.chk_subtract.blockSignals(False)
            return
        if self._state.wcs is None:
            # ADR-051: solve the plate, then the subtraction starts
            self._say(self.tr(
                "The plate has no WCS: solving it for the aligned "
                "reference…"))
            dlg = host_of(self)
            req = getattr(dlg, "request_wcs", None)
            if callable(req):
                req(lambda: self._on_subtract_toggled(True),
                    on_fail=self._explain_no_wcs_subtract)
                return
            self._explain_no_wcs_subtract()
            return
        from .workers import BlinkWorker, hold
        ra, dec = self._state.wcs.center()
        self._say(self.tr(
            "Fetching the reference and subtracting…"))
        self.chk_subtract.setEnabled(False)
        self._sub_worker = hold(BlinkWorker(self._state.path, ra=ra, dec=dec))
        # the pipeline stages (survey reference download) reach the status
        # line, as the Blink tab's prepare does (ADR-018 progress)
        self._sub_worker.progress.connect(
            lambda msg: self._say(msg.get(self._lang, "")))
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
            self._say("⚠ " + errors.get(self._lang, ""))
            self.chk_subtract.blockSignals(True)
            self.chk_subtract.setChecked(False)
            self.chk_subtract.blockSignals(False)
            return
        entries = self._sequence()
        diff = self._build_difference(pair, entries)
        if diff is None:
            self._say(self.tr(
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
        self._say(self.tr(
            "Host subtracted. The target now reads on the difference "
            "image; comps calibrate on the original plate."))

    def _build_difference(self, pair, entries):
        # Registers the survey reference to the frame, masks its holes and
        # subtracts it, scaled so the comparison stars vanish (H2b). The
        # alignment is done on the IMAGES (core/host_subtract), not trusted
        # to the WCS: the ignored SIP terms leave a dipole at every star,
        # which is the black dots the observer sees. Mirrored pairs are
        # un-flipped first (the editor's orientation).
        # @return: the difference image (work frame), or None
        obs = pair["obs"]
        ref = pair["ref"]
        if pair.get("flipped"):
            obs = np.ascontiguousarray(obs[:, ::-1])
            ref = np.ascontiguousarray(ref[:, ::-1])
        plate_w, plate_h = self._state.plate_shape
        fx = plate_w / obs.shape[1]
        fy = plate_h / obs.shape[0]
        comp_xy = []
        for e in entries:
            try:
                col, row = self._state.wcs.sky_to_pixel(e["star"]["ra"],
                                                        e["star"]["dec"])
            except Exception:
                continue
            comp_xy.append((col / fx, row / fy))
        # the seeing lives on the plate scale; the registration gate wants it
        # on the work frame the difference is built in
        fwhm = (self._last or {}).get("fwhm")
        logger.info("build difference: obs=%s ref=%s flipped=%s comps=%d "
                    "fwhm=%s", obs.shape, ref.shape, pair.get("flipped"),
                    len(comp_xy), fwhm)
        result = host_subtract.subtract(
            obs, ref, comp_xy,
            fwhm_px=(fwhm / fx if fwhm else None))
        logger.info("build difference: scale=%s rms=%s trusted=%s used=%d",
                    result["transform"].get("scale"),
                    result["transform"].get("rms_px"), result["trusted"],
                    result["used"])
        self._sub_report = result
        return result["diff"]

    def _display_diff(self):
        # The difference image as the view's frame (screen orientation).
        # Its sky sits at ~0, so the plate's black/white would show a
        # black screen: the difference gets its own auto percentiles
        # (gamma and invert stay shared). A pixel the survey never had
        # (a mask, or an edge the warp could not fill) arrives as NaN and
        # to_uint8 would paint it black: it is shown as the OBSERVATION
        # there (the un-subtracted star), never as a black dot nor as fake
        # sky, because filling it with the difference's median turns a
        # masked bright star into a black hole.
        if self._diff is None:
            return None
        data = self._diff
        finite = np.isfinite(data)
        if not finite.all():
            obs = self._pair_obs
            if obs is not None and obs.shape == data.shape:
                data = np.where(finite, data, obs)
            else:
                sky = (float(np.median(data[finite])) if finite.any()
                       else 0.0)
                data = np.where(finite, data, sky)
        # The observer's own black/white (the histogram strip) drive the
        # difference too, so the SN can be brought up the same way it is on
        # the plate. The difference's sky sits at the plate's level
        # (obs - gain*ref), so the observer's window usually applies; when it
        # misses (a subtraction that leaves a different pedestal) the
        # difference falls back to its own percentiles rather than clipping.
        st = self._state
        black, white = float(st.black), float(st.white)
        med = float(np.nanmedian(data))
        if not (black < med < white):
            black, white = stretch.auto_limits(data)
        img = stretch.apply_stretch(data, black, white, st.gamma)
        if st.inverted:
            img = stretch.invert(img)
        return np.ascontiguousarray(np.flipud(stretch.to_uint8(img)))

    def _drop_subtraction(self):
        # Back to the plain plate: no difference image, no override.
        self._diff = None
        self._pair_obs = None
        self._sub_report = None
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
        self._say(self.tr("Written to {0}").format(out))
        # ADR-045: the one-row report registers in the watching project
        # (the visit it was measured from), like every other UFE file
        dlg = host_of(self)
        notify = getattr(dlg, "notify_saved", None)
        if callable(notify):
            notify([out], "report")
