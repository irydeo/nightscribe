############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Annotate tab (ADR-044, phase D)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE's Annotate tab (ADR-044, phase D): click the plate to drop a
marker, nudge it to the pixel, give the annotation a label and night
notes, and save ANNOTATED COPIES (the observer's files are never
touched) through core/fits_annotate.write_annotated_fits, the same AIJ
compatible backend the legacy dialog uses. Extra plates can be listed so
one annotation lands on every visit (the marker maps through each
plate's own WCS when it has one).

The tab owns the view's clicks and overlays only while it is the current
tab; everything marker related is screen-sized (like the legacy preview)
and recomputed on zoom, while the saved position always comes from the
scene-to-data conversion, in original plate pixels.
"""

import logging
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QFileDialog, QMessageBox,
                               QGraphicsSimpleTextItem, QWidget)

from ..core import fits_annotate, fits_io, wcs as wcs_mod
from ..viz import palette
from .ui_loader import adopt_ui

logger = logging.getLogger("nightscribe.gui.ufe_annotate_tab")


class UfeAnnotateTab(QWidget):
    pick_clicks = True   # clicks mark things: the dialog hands us
                           # the pick cursor + snapping reticle on stage
    # @args: state - the shared UfeImageState, lang - "es" | "en",
    #        view - the UfeImageView the overlays and clicks live on

    def __init__(self, state, lang="es", view=None, parent=None):
        super().__init__(parent)
        self._state = state
        self._lang = lang
        self._view = view
        self._active = False
        self._marker = None          # (col, row) in data coords, or None
        self._marker_color = QColor(palette.ACCENT)
        self._items = []             # the marker's scene items
        self._build_ui()
        state.image_loaded.connect(self._on_image_loaded)
        state.wcs_changed.connect(self._update_readout)
        if view is not None:
            view.scene_clicked.connect(self._on_scene_clicked)
            view.zoom_changed.connect(lambda _f: self._refresh_marker())
        self._on_image_loaded()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # The structure is the Designer file's (ADR-005); this method
        # aliases the widgets and connects the signals.
        self._ui = adopt_ui(self, "ufe_annotate_tab")
                                            # over: no wrapper margins
        self.edit_label = self._ui.edit_label
        self.edit_label.textChanged.connect(self._refresh_marker)
        self.edit_notes = self._ui.edit_notes
        self.sld_marker = self._ui.sld_marker
        self.sld_marker.valueChanged.connect(self._refresh_marker)
        self.btn_color = self._ui.btn_color
        self.btn_color.setText(palette.ACCENT)      # data, not text
        self.btn_color.setAccessibleName("marker color")
        self.btn_color.clicked.connect(self._pick_color)
        self.spin_dx = self._ui.spin_dx
        self.spin_dy = self._ui.spin_dy
        self.btn_nudge = self._ui.btn_nudge
        self.btn_nudge.clicked.connect(self._apply_nudge)
        self.chk_marker = self._ui.chk_marker
        self.chk_marker.toggled.connect(self._refresh_marker)
        self.lbl_position = self._ui.lbl_position
        self.lst_extra = self._ui.lst_extra
        self.btn_add = self._ui.btn_add
        self.btn_add.clicked.connect(self._add_extras)
        self.btn_remove = self._ui.btn_remove
        self.btn_remove.clicked.connect(self._remove_extra)
        self.btn_save = self._ui.btn_save
        self.btn_save.clicked.connect(self._save)
        self.lbl_status = self._ui.lbl_status

    # ------------------------------------------------------- activation

    def set_active(self, flag):
        # The dialog calls this on tab switches: only the visible tab owns
        # the view's clicks and its overlays (ADR-044 extension rule); on
        # stage it also gets the pick cursor and the snapping reticle.
        self._active = bool(flag)
        if self._active:
            self._refresh_marker()
        elif self._view is not None:
            self._drop_marker_items()

    # ------------------------------------------------- host integration

    def prefill(self, label=None, notes=None, ra=None, dec=None,
                extra_paths=()):
        # The host app (a project) lands the editor halfway done: label,
        # notes, the marker on the object's sky position when the plate
        # carries a WCS, and the other visits queued for annotation.
        # @args: label - annotation label (the object name), notes -
        #        default notes, ra/dec - J2000 sky or None,
        #        extra_paths - more plates to annotate with the same marker
        if label is not None:
            self.edit_label.setText(label)
        if notes is not None:
            self.edit_notes.setText(notes)
        if ra is not None and dec is not None and self._state.wcs is not None:
            try:
                col, row = self._state.wcs.sky_to_pixel(ra, dec)
                w, h = self._state.plate_shape
                if 0 <= col < w and 0 <= row < h:
                    self._marker = [float(col), float(row)]
                    self._refresh_marker()
            except Exception:
                pass
        for p in extra_paths or ():
            existing = {self.lst_extra.item(i).text()
                        for i in range(self.lst_extra.count())}
            if p and str(p) not in existing:
                self.lst_extra.addItem(str(p))

    def _notify_saved(self, paths):
        # Files written while a host watches (a project) get registered
        # there; with no host this is a no-op.
        dlg = self.window()
        notify = getattr(dlg, "notify_saved", None)
        if callable(notify):
            notify(paths, "fits")

    # ------------------------------------------------------------- state

    def _on_image_loaded(self):
        # A fresh plate: marker back to the centre, extras kept (the list
        # is the observer's call), controls follow the empty state.
        has = self._state.has_image
        self.setEnabled(has)
        if has:
            w, h = self._state.plate_shape
            self._marker = [w / 2.0, h / 2.0]     # data coords
            self.lbl_status.setText("")
        else:
            self._marker = None
        self._refresh_marker()

    def _on_scene_clicked(self, scene_pt):
        # A click on the plate places the marker (only while the tab is
        # the current one: clicks belong to whoever is on stage).
        if not self._active or self._marker is None:
            return
        col, row = self._state.scene_to_data(scene_pt.x(), scene_pt.y())
        w, h = self._state.plate_shape
        self._marker = [min(max(col, 0.0), w - 1.0),
                        min(max(row, 0.0), h - 1.0)]
        self._refresh_marker()

    # ------------------------------------------------------------- marker

    def _refresh_marker(self):
        # Repositions every marker item for the current position, colour,
        # size, label and zoom. Marker geometry is screen-sized (constant
        # on the display, like the legacy preview); only the position is
        # real plate pixels.
        if self._view is None:
            return
        self._drop_marker_items()
        if not self._active or self._marker is None \
                or not self.chk_marker.isChecked():
            self._update_readout()
            return
        scale = max(self._view.current_factor(), 1e-3)
        r = self.sld_marker.value() / scale      # scene radius, screen px
        x, y = self._state.data_to_scene(*self._marker)
        # ADR-046: the marker has two looks (Settings); the cross spans
        # the plate with a box on the object, the ring is the classic.
        # Both draw through the shared helpers so every tab matches.
        from ..config import config
        from .widgets.ufe_image_view import (cross_marker_items,
                                             ring_marker_items)
        if config.get("marker_style", "ring") == "cross":
            w, h = self._state.plate_shape
            half = max(9.0, self.sld_marker.value() * 0.9) / scale
            for it in cross_marker_items(x, y, w, h, self._marker_color,
                                         half):
                self._items.append(self._view.add_overlay(it))
            r = half                    # the label anchors below the box
        else:
            for it in ring_marker_items(x, y, self._marker_color, r):
                self._items.append(self._view.add_overlay(it))
        text = self.edit_label.text().strip()
        if text:
            label = QGraphicsSimpleTextItem(text)
            f = QFont()
            f.setPointSizeF(max(0.5, 11.0 / scale))   # constant screen pt
            label.setFont(f)
            label.setBrush(QBrush(QColor("#ffffff")))
            br = label.boundingRect()
            label.setPos(x - br.width() / 2, y + 1.9 * r)
            label.setZValue(60)
            self._items.append(self._view.add_overlay(label))
        self._update_readout()

    def _drop_marker_items(self):
        # Removes the marker's scene items (they are registered overlays).
        if self._view is None:
            self._items = []
            return
        for it in self._items:
            try:
                self._view.scene().removeItem(it)
                if it in self._view._items_registered:
                    self._view._items_registered.remove(it)
            except RuntimeError:
                pass                    # the scene already dropped it
        self._items = []

    def _update_readout(self):
        # The position line under the controls: plate pixel + sky when
        # the plate carries a WCS.
        if self._marker is None:
            self.lbl_position.setText("–")
            return
        col, row = self._marker
        parts = [self.tr("marker {0:.1f}, {1:.1f}").format(col, row)]
        if self._state.wcs is not None:
            try:
                from ..core import coords
                ra, dec = self._state.wcs.pixel_to_sky(col, row)
                parts.append(f"{self.tr('RA')} {coords.ra_deg_to_hms(ra)}")
                parts.append(f"{self.tr('Dec')} {coords.dec_deg_to_dms(dec)}")
            except Exception:
                pass
        self.lbl_position.setText("  ·  ".join(parts))

    def _apply_nudge(self):
        # Shifts the marker by the two nudge fields, clamped to the plate.
        if self._marker is None:
            return
        w, h = self._state.plate_shape
        self._marker = [
            min(max(self._marker[0] + self.spin_dx.value(), 0.0), w - 1.0),
            min(max(self._marker[1] + self.spin_dy.value(), 0.0), h - 1.0)]
        self._refresh_marker()

    def _pick_color(self):
        # Asks for the marker colour and re-draws.
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(self._marker_color, self)
        if c.isValid():
            self._marker_color = c
            self.btn_color.setStyleSheet(f"background: {c.name()};")
            self.btn_color.setText(c.name())
            self._refresh_marker()

    # -------------------------------------------------------------- save

    def _add_extras(self):
        # Adds visit plates that will receive the same annotation.
        paths, _sel = QFileDialog.getOpenFileNames(
            self, self.tr("Plates to annotate with the same marker"),
            "", self.tr("FITS images (*.fits *.fit *.fts *.fz);;"
                        "All files (*)"))
        existing = {self.lst_extra.item(i).text()
                    for i in range(self.lst_extra.count())}
        for p in paths:
            if p and p not in existing:
                self.lst_extra.addItem(p)

    def _remove_extra(self):
        for item in self.lst_extra.selectedItems():
            self.lst_extra.takeItem(self.lst_extra.row(item))

    def _sky_of_marker(self):
        # @return: (ra_deg, dec_deg) of the marker through the plate's
        #          WCS, or (None, None)
        if self._state.wcs is None or self._marker is None:
            return None, None
        try:
            return self._state.wcs.pixel_to_sky(*self._marker)
        except Exception:
            return None, None

    def _save_one(self, input_path, output_path, ra_deg, dec_deg):
        # Writes one annotated copy; the marker maps through the plate's
        # own WCS when the sky position is known (visits land right).
        # The CURRENT plate uses the state's in-memory header, so an
        # astrometry solved this session counts even though the file on
        # disk is never modified.
        # @return: the Path written
        xy = None
        scale = north_pa = None
        if str(input_path) == str(self._state.path):
            wc = self._state.wcs
            header = self._state.header or {}
        else:
            try:
                header = fits_io.read_header(input_path)
                wc = wcs_mod.Wcs.from_header(header)
            except Exception:
                wc = None
        if wc is not None:
            try:
                scale = wc.pixel_scale()
                north_pa = -wc.rotation()
            except Exception:
                scale = north_pa = None
            if ra_deg is not None:
                try:
                    w2, h2 = int(header["NAXIS1"]), int(header["NAXIS2"])
                    px, py = wc.sky_to_pixel(ra_deg, dec_deg)
                    if 0.0 <= px < w2 and 0.0 <= py < h2:
                        xy = (float(px), float(py))
                except Exception:
                    xy = None             # off the field on this visit
        if str(input_path) == str(self._state.path) and xy is None:
            xy = tuple(self._marker)      # the current plate, no usable
                                          # WCS: mark where the observer
                                          # put it
        return fits_annotate.write_annotated_fits(
            input_path, output_path, sn_xy=xy, scale=scale,
            north_pa=north_pa,
            obj_name=self.edit_label.text().strip(),
            ra_deg=ra_deg, dec_deg=dec_deg,
            notes=self.edit_notes.text().strip())

    def _save(self):
        # Save annotated copy…: the current plate to the chosen path, the
        # listed visits next to themselves with the _annotated suffix.
        if self._marker is None:
            return
        src = Path(self._state.path)
        default = src.with_name(f"{src.stem}_annotated.fits")
        dest, _sel = QFileDialog.getSaveFileName(
            self, self.tr("Save annotated FITS as"), str(default),
            "FITS (*.fits *.fit)")
        if not dest:
            return
        ra_deg, dec_deg = self._sky_of_marker()
        try:
            self._save_one(src, dest, ra_deg, dec_deg)
            written = [dest]
            for i in range(self.lst_extra.count()):
                extra = Path(self.lst_extra.item(i).text())
                out = extra.with_name(f"{extra.stem}_annotated.fits")
                self._save_one(extra, out, ra_deg, dec_deg)
                written.append(str(out))
        except Exception as exc:      # never crash, never touch originals
            logger.exception("annotated save failed: %s", exc)
            QMessageBox.critical(
                self, self.tr("Save failed"),
                self.tr("Could not write the annotated FITS to {0}.\n{1}")
                .format(dest, str(exc)))
            return
        logger.info("annotated FITS written: %s", written)
        self._notify_saved(written)
        self.lbl_status.setText(
            self.tr("Saved {0} annotated copy(ies). Last: {1}")
            .format(len(written), written[-1]))
