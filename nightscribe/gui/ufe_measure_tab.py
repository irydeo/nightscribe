############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Measure tab (ADR-044, phase G2)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE's Measure tab (phase G of docs/PLANS/ufe-photometry.md):
calibrated single-plate photometry. One click on a star or supernova
measures it (core/photometry: centroid, aperture, sigma-clipped sky,
honest guards), measures the Compare tab's sequence on the same plate,
and calibrates against their catalog magnitudes: ZP by median with a
MAD-based error, the target's error from the CCD equation when the gain
is known, and a plain-language panel that says exactly what was used and
what was refused. One measurement is one click (D4); the exports are
files (CSV one row, AAVSO EFF), the plate on disk is never touched (D6).
"""

import logging
import math
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget,
                               QGraphicsEllipseItem)

from ..core import fits_meta, photometry, photometry_export

logger = logging.getLogger("nightscribe.gui.ufe_measure_tab")

_C_AP = "#ffb347"      # the amber marker family the UFE already wears
_C_ANN = "#6ec1ff"     # sky annulus rings in the cool accent
_C_COMP = "#4dd0e1"    # used comps ring in the compare tab's cyan


class UfeMeasureTab(QWidget):
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
        self._items = []             # aperture + comps overlays
        self._last = None            # the last measurement bundle
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
        for spn in (self.spn_rap, self.spn_rin, self.spn_rout):
            spn.setToolTip(tip)
        self.chk_sigmaclip = QCheckBox(self.tr("Sigma-clip the sky"))
        self.chk_sigmaclip.setChecked(True)
        self.chk_sigmaclip.setToolTip(self.tr(
            "Two 2.5-sigma rounds on the annulus: extra skin against hot "
            "pixels and crowded cores"))
        lay.addWidget(self.chk_sigmaclip)

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
        # Only the visible tab owns the view's clicks and its overlays.
        self._active = bool(flag)
        if not self._active:
            self._drop_items()
        elif self._last is not None:
            self._draw_measurement()

    # ------------------------------------------------------------- state

    def _on_image_loaded(self):
        # A fresh plate invalidates the measurement (and the sequence's
        # sky mapping): start clean, band list rebuilt on next measure.
        self._last = None
        self._drop_items()
        self.lbl_result.setText("–")
        self.btn_csv.setEnabled(False)
        self.btn_eff.setEnabled(False)
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
        col, row = self._state.scene_to_data(scene_pt.x(), scene_pt.y())
        sat = self._saturation_ceiling()
        result = photometry.measure_point(
            self._state.data, col, row, r_ap=self.spn_rap.value(),
            r_ann_in=self.spn_rin.value(),
            r_ann_out=self.spn_rout.value(),
            sigma_clip=self.chk_sigmaclip.isChecked(), sat_adu=sat)
        if not result["ok"]:
            reason = (result.get("reason") or {}).get(self._lang, "?")
            self.lbl_status.setText(reason)
            self._last = None
            self._drop_items()
            self.btn_csv.setEnabled(False)
            self.btn_eff.setEnabled(False)
            return
        self.lbl_status.setText("")
        self._finish_measurement(result, entries)

    def _sequence(self):
        # @return: the Compare tab's entries, or [] when absent/empty
        if self._compare is None:
            return []
        try:
            return self._compare.entries()
        except Exception:
            return []

    def _saturation_ceiling(self):
        # @return: the plate's saturation level in ADU, or None
        header = self._state.header or {}
        for key in ("SATURATE", "SATLEVEL"):
            try:
                v = header.get(key)
                if v is not None:
                    return float(v)
            except (TypeError, ValueError):
                continue
        return None

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

    def _finish_measurement(self, result, entries):
        # The target measured fine: measure the comps on the same plate,
        # calibrate, and fill the panel. Everything degraded is said.
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
        inst, cat, used_entries, derived_seen = [], [], [], False
        skipped = 0
        for e in entries:
            star = e["star"]
            try:
                col, row = self._state.wcs.sky_to_pixel(star["ra"],
                                                        star["dec"])
            except Exception:
                skipped += 1
                continue
            r = photometry.measure_point(
                self._state.data, col, row, r_ap=self.spn_rap.value(),
                r_ann_in=self.spn_rin.value(),
                r_ann_out=self.spn_rout.value(),
                sigma_clip=self.chk_sigmaclip.isChecked(), sat_adu=None)
            value, derived = self._band_of(star, band)
            if not r["ok"] or value is None:
                skipped += 1
                continue
            inst.append(-2.5 * math.log10(r["flux"]))
            cat.append(value)
            derived_seen = derived_seen or derived
            used_entries.append((e, r))
        zp = photometry.calibrate_zero_point(inst, cat)
        inst = photometry.header_instrument(self._state.header)
        flux_err = photometry.ccd_flux_error(
            result["flux"], result["sky_pp"], result["n_pix"],
            gain=inst["gain"], ron=inst["ron"], exptime=inst["exptime"])
        target_err = photometry.mag_error(result["flux"], flux_err)
        mag, err = photometry.calibrated_mag(inst_t, zp["zp"],
                                             zp["zp_err"], target_err)
        self._last = {"result": result, "zp": zp, "mag": mag, "err": err,
                      "band": band, "used": used_entries,
                      "derived": derived_seen, "inst_t": inst_t}
        self._fill_panel(result, zp, mag, err, band, len(entries),
                         len(used_entries), skipped, derived_seen,
                         gain_known=inst["gain"] is not None)
        self.btn_csv.setEnabled(mag is not None)
        self.btn_eff.setEnabled(mag is not None)
        self._draw_measurement()

    def _fill_panel(self, result, zp, mag, err, band, n_seq, n_used,
                    skipped, derived, gain_known):
        # The result block, in plain language and with every caveat that
        # applies (ADR-038: the panel says what was used and what was not).
        lines = []
        lines.append(self.tr("Pixel ({0:.1f}, {1:.1f}) · net flux {2:,.0f}")
                     .format(result["x"], result["y"], result["flux"]))
        lines.append(self.tr("Instrumental mag: {0:.3f}")
                     .format(self._last["inst_t"]))
        if zp["zp"] is None:
            lines.append(self.tr(
                "No comparison star could be used: no calibration."))
        else:
            lines.append(self.tr(
                "Zero point: {0:.3f} ± {1:.3f} ({2} comps, band {3})")
                .format(zp["zp"], zp["zp_err"], zp["n"], band))
            if mag is not None:
                lines.append(self.tr("Magnitude: {0:.3f} ± {1:.3f} ({2})")
                             .format(mag, err, band))
        notes = []
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
        if not gain_known:
            notes.append(self.tr(
                "No gain in the header: the error is the comps' scatter "
                "only"))
        lines.extend(f"· {n}" for n in notes)
        self.lbl_result.setText("\n".join(lines))

    # ---------------------------------------------------------- overlays

    def _draw_measurement(self):
        # Aperture + annulus on the measured point, thin rings on the
        # comps that calibrated it (all in plate px, cosmetic pens).
        self._drop_items()
        if not self._active or self._view is None or self._last is None:
            return
        result = self._last["result"]
        x, y = self._state.data_to_scene(result["x"], result["y"])
        for r, color, width in (
                (self.spn_rap.value(), _C_AP, 2.0),
                (self.spn_rin.value(), _C_ANN, 1.2),
                (self.spn_rout.value(), _C_ANN, 1.2)):
            ring = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
            pen = QPen(QColor(color))
            pen.setWidthF(width)
            pen.setCosmetic(True)
            ring.setPen(pen)
            ring.setZValue(55)
            self._items.append(self._view.add_overlay(ring))
        for e, _r in self._last["used"]:
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
            ra, dec = self._state.wcs.pixel_to_sky(result["x"],
                                                   result["y"])
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
