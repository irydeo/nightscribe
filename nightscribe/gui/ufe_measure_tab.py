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
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget,
                               QGraphicsEllipseItem)

from ..core import coords, fits_meta, photometry, photometry_export, \
    stretch

logger = logging.getLogger("nightscribe.gui.ufe_measure_tab")

_C_AP = "#ffb347"      # the amber marker family the UFE already wears
_C_ANN = "#6ec1ff"     # sky annulus rings in the cool accent
_C_COMP = "#4dd0e1"    # used comps ring in the compare tab's cyan


class UfeMeasureTab(QWidget):
    pick_clicks = True   # clicks mark things: the dialog hands us
                           # the pick cursor + snapping reticle on stage
    # @args: state - the shared UfeImageState, lang - "es" | "en",
    #        view - the UfeImageView, compare_tab - the Compare tab the
    #        sequence is read from (D5), go_compare - callable switching
    #        the dialog to that tab

    def __init__(self, state, lang="es", view=None, compare_tab=None,
                 go_compare=None, parent=None):
        super().__init__(parent)
        self._state = state
        self._lang = lang
        self._view = view
        self._compare = compare_tab
        self._go_compare = go_compare
        self._active = False
        self._project_attached = False     # point hook set on the dialog
        self._items = []             # aperture + comps overlays
        self._last = None            # the last measurement bundle
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

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        lay = QVBoxLayout(self)
        hint = QLabel(self.tr(
            "Click a star (or the target) to measure it against the "
            "Compare tab's sequence."))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)
        self.btn_go_compare = QPushButton(self.tr(
            "Open the Compare tab"))
        self.btn_go_compare.setVisible(False)
        if self._go_compare is not None:
            self.btn_go_compare.clicked.connect(self._go_compare)
        lay.addWidget(self.btn_go_compare)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Band:")))
        self.cmb_band = QComboBox()
        row.addWidget(self.cmb_band, 1)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Apertures:")))
        self.spn_rap = self._spin(photometry.R_AP, 1.0, 20.0)
        self.spn_rin = self._spin(photometry.R_ANN_IN, 2.0, 40.0)
        self.spn_rout = self._spin(photometry.R_ANN_OUT, 3.0, 60.0)
        for spn in (self.spn_rap, self.spn_rin, self.spn_rout):
            row.addWidget(spn)
        row.addStretch(1)
        lay.addLayout(row)
        tip = self.tr("Aperture radius, sky annulus inner and outer "
                      "radius (px)")
        self._radii_manual = False   # True once the observer edits a spin
        for spn in (self.spn_rap, self.spn_rin, self.spn_rout):
            spn.setToolTip(tip)
            spn.valueChanged.connect(self._on_radii_edited)
        row2 = QHBoxLayout()
        self.btn_suggest = QPushButton(self.tr("Suggest apertures"))
        self.btn_suggest.setToolTip(self.tr(
            "Propose the radii from this target's growth curve and its "
            "surroundings (crowding, background gradient), with the "
            "reasons in plain language"))
        self.btn_suggest.clicked.connect(self._on_suggest)
        row2.addWidget(self.btn_suggest)
        row2.addStretch(1)
        lay.addLayout(row2)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Sky:")))
        self.cmb_sky = QComboBox()
        self.cmb_sky.addItem(self.tr("Median (flat sky)"), "median")
        self.cmb_sky.addItem(self.tr("Plane (galactic cores)"), "plane")
        self.cmb_sky.setToolTip(self.tr(
            "How the annulus estimates the background: a flat median, or "
            "a tilted plane when the host galaxy tilts it"))
        row.addWidget(self.cmb_sky, 1)
        lay.addLayout(row)
        # every measuring control re-measures the live point at once
        self.cmb_sky.currentIndexChanged.connect(
            lambda _i: self._remeasure())

        self.chk_sigmaclip = QCheckBox(self.tr("Sigma-clip the sky"))
        self.chk_sigmaclip.setChecked(True)
        self.chk_sigmaclip.setToolTip(self.tr(
            "Two 2.5-sigma rounds on the annulus: extra skin against hot "
            "pixels and crowded cores"))
        lay.addWidget(self.chk_sigmaclip)
        self.chk_sigmaclip.toggled.connect(lambda _c: self._remeasure())
        self.chk_seeing = QCheckBox(self.tr("Aperture follows the seeing"))
        self.chk_seeing.setChecked(True)
        self.chk_seeing.setToolTip(self.tr(
            "Measure the FWHM of the comparison stars and size the "
            "aperture as 1.35 times the seeing (H3)"))
        lay.addWidget(self.chk_seeing)
        self.chk_seeing.toggled.connect(self._on_seeing_toggled)
        row = QHBoxLayout()
        self.chk_color = QCheckBox(self.tr("Colour term"))
        self.chk_color.setChecked(True)
        self.chk_color.setToolTip(self.tr(
            "Fit the zero point AND its slope against the comps' B−V "
            "(H1); needs at least 6 comps with colour spread"))
        self.chk_color.toggled.connect(lambda _c: self._remeasure())
        row.addWidget(self.chk_color)
        row.addWidget(QLabel(self.tr("B−V target:")))
        self.spn_target_bv = QDoubleSpinBox()
        self.spn_target_bv.setRange(-1.0, 3.0)
        self.spn_target_bv.setDecimals(2)
        self.spn_target_bv.setSingleStep(0.05)
        self.spn_target_bv.setValue(0.0)
        self.spn_target_bv.setToolTip(self.tr(
            "The target's B−V when known (variables: VSX). A supernova "
            "near peak is about 0; the panel warns when the colour term "
            "is applied with this assumption"))
        self.spn_target_bv.setKeyboardTracking(False)
        self.spn_target_bv.valueChanged.connect(
            lambda _v: self._remeasure())
        row.addWidget(self.spn_target_bv)
        lay.addLayout(row)
        self.chk_subtract = QCheckBox(self.tr(
            "Subtract host galaxy (PS1 reference)"))
        self.chk_subtract.setToolTip(self.tr(
            "Download the aligned PanSTARRS reference, scale it so the "
            "comparison stars vanish, and measure the target on the "
            "difference image (H2b; needs network once per field)"))
        self.chk_subtract.toggled.connect(self._on_subtract_toggled)
        lay.addWidget(self.chk_subtract)

        self.lbl_result = QLabel("–")
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.lbl_result)

        row = QHBoxLayout()
        self.btn_csv = QPushButton(self.tr("CSV…"))
        self.btn_csv.setEnabled(False)
        self.btn_csv.clicked.connect(lambda: self._export("csv"))
        row.addWidget(self.btn_csv)
        self.btn_eff = QPushButton(self.tr("AAVSO EFF…"))
        self.btn_eff.setEnabled(False)
        self.btn_eff.clicked.connect(lambda: self._export("eff"))
        row.addWidget(self.btn_eff)
        # ADR-044: the editor opened from a project registers the point
        # there (source “measure”); ad-hoc opens hide this button.
        self.btn_save_project = QPushButton(self.tr("Save in the project"))
        self.btn_save_project.setToolTip(self.tr(
            "Register this calibrated point in the project that opened "
            "the editor: it lands on the light curve and feeds the "
            "campaign summary (source “measure”)"))
        self.btn_save_project.setEnabled(False)
        self.btn_save_project.setVisible(False)
        self.btn_save_project.clicked.connect(self._on_save_project)
        row.addWidget(self.btn_save_project)
        lay.addLayout(row)
        lay.addStretch(1)

    def _spin(self, value, lo, hi):
        # @return: one aperture spinbox (px, half-pixel steps)
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setDecimals(1)
        sb.setSingleStep(0.5)
        sb.setValue(value)
        return sb

    # ------------------------------------------------------- activation

    def set_active(self, flag):
        # Only the visible tab owns the view's clicks and its overlays;
        # on stage it also gets the pick cursor and the snapping reticle.
        self._active = bool(flag)
        if not self._active:
            self._drop_items()
            if self._diff is not None and self._view is not None:
                self._view.set_frame_override(None)
        else:
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
        # Nothing timer-driven here; the subtraction worker may run.
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
        self.btn_go_compare.setVisible(False)

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
                "No comparison sequence yet: build one in the Compare "
                "tab (Generate field, then pick or propose)."))
            self.btn_go_compare.setVisible(True)
            return
        self.btn_go_compare.setVisible(False)
        self._last_suggestions = []     # a new target: stale reasons go
        col, row = self._state.scene_to_data(scene_pt.x(), scene_pt.y())
        self._measure(col, row, entries)

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
            try:
                self.spn_target_bv.setValue(float(bv))
            except (TypeError, ValueError):
                pass

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

    def _measure_star(self, data, col, row, radii, sat):
        # One measurement with the current UI's sky settings.
        # @return: core/photometry.measure_point's dict
        return photometry.measure_point(
            data, col, row, r_ap=radii[0], r_ann_in=radii[1],
            r_ann_out=radii[2], sigma_clip=self.chk_sigmaclip.isChecked(),
            sat_adu=sat,
            sky_mode=self.cmb_sky.currentData())

    def _measure(self, col, row, entries):
        # Full chain: seeing -> target -> comps -> calibration -> panel.
        from ..config import config
        sat = photometry.saturation_ceiling(self._state.header, config)
        radii, fwhm = self._apertures(entries)
        if self._diff is not None:
            # H2b: the target is measured on the difference image (work
            # frame, plate orientation); the comps keep calibrating on
            # the original plate (they vanish in the difference).
            wcol = col / self._diff_scale
            wrow = row / self._diff_scale
            result = self._measure_star(self._diff, wcol, wrow,
                                        tuple(r / self._diff_scale
                                              for r in radii), None)
        else:
            result = self._measure_star(self._state.data, col, row,
                                        radii, sat)
        if not result["ok"]:
            reason = (result.get("reason") or {}).get(self._lang, "?")
            self.lbl_status.setText(reason)
            self._last = None
            self._drop_items()
            self.btn_csv.setEnabled(False)
            self.btn_eff.setEnabled(False)
            self.btn_save_project.setEnabled(False)
            return
        self.lbl_status.setText("")
        self._calibrate_and_fill(result, col, row, entries, radii, fwhm,
                                 config)

    def _calibrate_and_fill(self, result, col, row, entries, radii, fwhm,
                            config):
        # Comps on the same plate, zero point (with the colour term when
        # there is spread), the error budget, the check semaphore, and
        # the panel.
        band = self.cmb_band.currentText() or "V"
        bands = self._available_bands(entries)
        if bands and band not in bands:
            band = bands[0]
        if bands:
            self.cmb_band.blockSignals(True)
            self.cmb_band.clear()
            self.cmb_band.addItems(bands)
            self.cmb_band.setCurrentText(band)
            self.cmb_band.blockSignals(False)
        inst_t = -2.5 * math.log10(result["flux"])
        inst, cat, bvs, used_entries = [], [], [], []
        skipped = 0
        for e in entries:
            star = e["star"]
            try:
                ccol, crow = self._state.wcs.sky_to_pixel(star["ra"],
                                                          star["dec"])
            except Exception:
                skipped += 1
                continue
            if self._diff is not None:
                # H2b: never mix flux scales: the comps are measured on
                # the work frame the difference lives in (the blink
                # downsamples big plates, and a DN is not a DN across
                # scales)
                r = self._measure_star(
                    self._pair_obs, ccol / self._diff_scale,
                    crow / self._diff_scale,
                    tuple(v / self._diff_scale for v in radii), None)
            else:
                r = self._measure_star(self._state.data, ccol, crow,
                                       radii, None)
            value, derived = self._band_of(star, band)
            if not r["ok"] or value is None:
                skipped += 1
                continue
            inst.append(-2.5 * math.log10(r["flux"]))
            cat.append(value)
            bvs.append(star.get("bv"))
            used_entries.append((e, r))
        derived_seen = any(self._band_of(e["star"], band)[1]
                           for e, _r in used_entries)
        target_bv = self.spn_target_bv.value()
        if self.chk_color.isChecked():
            zp = photometry.calibrate_with_color(inst, cat, bvs,
                                                 target_bv=target_bv)
        else:
            zp = photometry.calibrate_zero_point(inst, cat)
        zp.setdefault("color_used", False)   # the plain path carries none
        inst_header = photometry.header_instrument(self._state.header)
        gain = (inst_header["gain"] if inst_header["gain"] is not None
                else config.get("ccd_gain"))
        ron = (inst_header["ron"] if inst_header["ron"] is not None
               else config.get("ccd_read_noise"))
        flux_err = photometry.ccd_flux_error(
            result["flux"], result["sky_pp"], result["n_pix"],
            gain=gain, ron=ron, exptime=inst_header["exptime"])
        ccd_mag_err = photometry.mag_error(result["flux"], flux_err)
        scint = self._scintillation(config, col, row,
                                    inst_header["exptime"])
        flat_floor = config.get("flat_resid_mag", 0.007) or 0.007
        color_err = zp.get("target_color_err")
        err_total = photometry.combine_errors(
            ccd_mag_err, zp["zp_err"], scint, flat_floor, color_err)
        zp_for_mag = zp["zp"]
        if zp.get("color_used") and zp["k"] is not None:
            # the fit's zero point is at B−V = 0: move the target onto it
            zp_for_mag = zp["zp"] + zp["k"] * target_bv
        mag, _e = photometry.calibrated_mag(inst_t, zp_for_mag)
        check = self._check_verdict(entries, used_entries, band, zp,
                                    err_total)
        self._last = {"result": result, "zp": zp, "mag": mag,
                      "err": err_total, "err_internal": ccd_mag_err,
                      "band": band, "used": used_entries,
                      "derived": derived_seen, "inst_t": inst_t,
                      "fwhm": fwhm, "radii": radii, "scint": scint,
                      "check": check, "col": col, "row": row,
                      "sky_mode": self.cmb_sky.currentData(),
                      "sigma_clip": self.chk_sigmaclip.isChecked()}
        self._fill_panel(band, len(entries), len(used_entries), skipped,
                         derived_seen, gain)
        self.btn_csv.setEnabled(mag is not None)
        self.btn_eff.setEnabled(mag is not None)
        # the project save tracks the result: a point without a magnitude
        # (only a check ratio) has nothing to register
        self.btn_save_project.setEnabled(mag is not None)
        self._draw_measurement()

    def _scintillation(self, config, col, row, exptime):
        # H5: Young's formula with the site from Ajustes and the target's
        # altitude from the plate's WCS + DATE-OBS. None when it cannot
        # be computed (the combiner skips it).
        meta = fits_meta.meta_from_header(self._state.header or {})
        if meta["mjd"] is None:
            return None
        try:
            ra, dec = self._state.wcs.pixel_to_sky(col, row)
            jd = meta["mjd"] + 2400000.5
            lst = coords.lst_degrees(jd, float(config.get("lon")))
            alt, _az = coords.altaz(ra, dec, float(config.get("lat")),
                                    lst)
            return photometry.scintillation_mag(
                alt, exptime,
                float(config.get("aperture_inches", 10.0)) * 0.0254,
                float(config.get("height", 0) or 0.0))
        except Exception:
            return None

    def _check_verdict(self, entries, used_entries, band, zp, err_total):
        # H6: measure the check star on this same plate and compare with
        # its catalog value; beyond 2.5 sigma the night is not trusted.
        # @args: zp - the calibration dict (with the colour term when
        #        fitted: the check's OWN B-V moves its zero point)
        # @return: None or {"delta", "ok", "name", "mag", "catalog"}
        check = next((e for e in entries if e["kind"] == "check"), None)
        if check is None or zp.get("zp") is None or err_total is None:
            return None
        used = next((r for e, r in used_entries
                     if e["star"] is check["star"]), None)
        if used is None:
            return None
        catalog, _d = self._band_of(check["star"], band)
        if catalog is None:
            return None
        zp_check = zp["zp"]
        if zp.get("color_used") and zp.get("k") is not None \
                and check["star"].get("bv") is not None:
            zp_check = zp["zp"] + zp["k"] * check["star"]["bv"]
        measured = -2.5 * math.log10(used["flux"]) + zp_check
        delta = measured - catalog
        return {"delta": delta, "ok": abs(delta) <= 2.5 * err_total,
                "name": check["name"], "mag": measured,
                "catalog": catalog}

    def _band_of(self, star, band):
        # @return: (value, derived) of the star's band entry, or
        #          (None, False) when the star lacks it
        for item in star.get("bands", []):
            if item.get("label") == band and item.get("value") is not None:
                return item["value"], bool(item.get("derived"))
        return None, False

    def _available_bands(self, entries):
        # @return: the photometric bands present in the sequence (colour
        #          indices like B-V or BP-RP are not bands), V first
        labels = []
        for e in entries:
            for item in e["star"].get("bands", []):
                lab = item.get("label") or ""
                if item.get("value") is None or "-" in lab:
                    continue
                if lab not in labels:
                    labels.append(lab)
        return sorted(labels, key=lambda l: (l != "V", l))

    # ------------------------------------------------------------- panel

    def _fill_panel(self, band, n_seq, n_used, skipped, derived, gain):
        # The result block, in plain language and with every caveat that
        # applies (ADR-038: the panel says what was used and what was not).
        last = self._last
        result = last["result"]
        zp = last["zp"]
        lines = []
        lines.append(self.tr("Pixel ({0:.1f}, {1:.1f}) · net flux {2:,.0f}")
                     .format(last["col"], last["row"], result["flux"]))
        lines.append(self.tr("Instrumental mag: {0:.3f}")
                     .format(last["inst_t"]))
        if zp["zp"] is None:
            lines.append(self.tr(
                "No comparison star could be used: no calibration."))
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
        if skipped:
            notes.append(self.tr(
                "{0} of {1} sequence stars not usable (off the plate, "
                "saturated, or without the band)").format(skipped, n_seq))
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
            notes.append(self.tr(
                "Colour term applied with target B−V = {0:.2f}")
                .format(self.spn_target_bv.value()))
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
        if not self._active or self._view is None or self._last is None:
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
                value, _d = self._band_of(entry["star"],
                                          self._last["band"])
                return {"name": entry["name"], "mag": value}
            photometry_export.export_eff(
                [point], out, name, ra_deg=ra, dec_deg=dec,
                obscode=config.get("aavso_code", ""),
                comp=_nc(comp), check=_nc(check))
        logger.info("measurement exported (%s): %s", kind, out)
        self.lbl_status.setText(self.tr("Written to {0}").format(out))
