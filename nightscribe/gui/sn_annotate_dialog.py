############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - SN annotated FITS preview dialog
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Preview, then save, an annotated FITS (Track B, B10).

Before writing the annotated copy the observer looks at the frame (same
stretch pipeline as the blink preview: black/white/gamma), places the marker
(nudge by pixels or click on the preview), edits the label, and fine-tunes
the marker size and colour. The north arrow and scale bar overlays are
preview helpers: on disk the facts live in the header (NS_SCALE, NS_NORTH)
and AIJ does its own rendering of the ANNOTATE card.

Save writes a copy (core.fits_annotate) to the chosen path, defaulting to
the project folder; the observer's original FITS is never touched. The
dialog stays on screen while it fails.
"""

import math
import logging

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QDialog, QDoubleSpinBox, QFileDialog, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSlider, QVBoxLayout, QWidget)

from ..viz import blink_view

logger = logging.getLogger(__name__)

_MARKER_DEFAULT = "#ffb347"  # the same amber the blink marker uses
_MAX_PREVIEW = 560          # largest preview side, in pixels


class SnAnnotateDialog(QDialog):
    # Emitted once the annotated copy has been written successfully.
    saved = Signal(str)

    def __init__(self, parent, fits_path, project, label, sn_xy=None,
                 scale=None, north_pa=None, ra_deg=None, dec_deg=None,
                 default_notes=""):
        # @args: fits_path - the stacked FITS to preview and annotate,
        #        project - project dict (only needed for the default folder),
        #        label - SN name (ANNOTATE label + default file name),
        #        sn_xy - (x, y) 0-based pixel of the SN, or None,
        #        scale - arcsec/pixel, or None, north_pa - deg east of north,
        #        ra_deg/dec_deg - J2000 position of the SN, or None,
        #        default_notes - text for the NS_NOTES card
        super().__init__(parent)
        from ..core import fits_io, project as proj_mod
        self.fits_path = str(fits_path)
        self.scale = scale
        self.north_pa = north_pa
        self.ra_deg = ra_deg
        self.dec_deg = dec_deg

        # Load the frame once; the preview only ever stretches it.
        header, self._data = fits_io.read_fits(self.fits_path)
        h, w = self._data.shape
        self._img_h = int(h)
        self._img_w = int(w)
        if sn_xy is not None and 0 <= sn_xy[0] < w and 0 <= sn_xy[1] < h:
            self._xy = [float(sn_xy[0]), float(sn_xy[1])]
        else:
            self._xy = [w / 2.0, h / 2.0]

        self.setWindowTitle(self.tr("Annotate %1").replace("%1", label or "?"))
        self._build_ui(project, proj_mod, label, default_notes)
        self._render()

    # ---------------- UI ----------------

    def _build_ui(self, project, proj_mod, label, default_notes):
        self.edit_label = QLineEdit(label or "")
        self.edit_label.setToolTip(
            self.tr("Label of the ANNOTATE card (usually the SN name)"))

        self.spin_dx = self._nudge_spinbox()
        self.spin_dy = self._nudge_spinbox()
        btn_nudge = QPushButton(self.tr("Nudge"))
        btn_nudge.setToolTip(self.tr(
            "Shift the marker by that many pixels (or click the preview)"))
        btn_nudge.clicked.connect(self._apply_nudge)

        self.sld_marker = QSlider(Qt.Horizontal)
        self.sld_marker.setRange(5, 40)
        self.sld_marker.setValue(15)
        self.sld_marker.valueChanged.connect(self._render)

        self._marker_color = QColor(_MARKER_DEFAULT)
        self.btn_color = QPushButton(self.tr("Marker colour"))
        self.btn_color.clicked.connect(self._pick_color)

        self.chk_north = QPushButton(self.tr("North arrow"))
        self.chk_north.setCheckable(True)
        self.chk_north.setChecked(bool(self.north_pa is not None))
        self.chk_north.setEnabled(self.north_pa is not None)
        self.chk_north.toggled.connect(self._render)

        self.chk_scale = QPushButton(self.tr("Scale bar"))
        self.chk_scale.setCheckable(True)
        self.chk_scale.setChecked(bool(self.scale is not None))
        self.chk_scale.setEnabled(self.scale is not None)
        self.chk_scale.toggled.connect(self._render)

        def _stretch_slider(lo, hi, val, fmt, tip):
            box = QHBoxLayout()
            sld = QSlider(Qt.Horizontal)
            sld.setRange(lo, hi)
            sld.setValue(val)
            lbl = QLabel(fmt.replace("%1", str(val)))
            lbl.setMinimumWidth(44)
            box.addStretch(1)
            box.addWidget(sld, 1)
            box.addWidget(lbl)
            sld.valueChanged.connect(
                lambda v: lbl.setText(fmt.replace("%1", str(v))))
            sld.valueChanged.connect(self._render)
            return sld

        self.sld_black = _stretch_slider(0, 200, 10, "%1",
                                        self.tr("Black: %1%"))
        self.sld_white = _stretch_slider(0, 1000, 995, "%1",
                                        self.tr("White: %1%"))
        self.sld_gamma = _stretch_slider(20, 200, 100, "%1",
                                        self.tr("Gamma: %1"))

        # Preview image: click places the marker there.
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.mousePressEvent = self._image_clicked
        self.lbl_image.setToolTip(self.tr("Click to place the marker there"))

        # Default destination: the project folder.
        default_dest = project
        try:
            dest_dir = proj_mod.storage_dir(project)
            default_dest = str(dest_dir / f"{label or 'image'}_annotated.fits")
        except Exception:
            default_dest = str(f"{label or 'image'}_annotated.fits")
        self.edit_dest = QLineEdit(default_dest)
        btn_browse = QPushButton(self.tr("Browse"))
        btn_browse.clicked.connect(self._browse_dest)

        self.edit_notes = QLineEdit(default_notes or "")
        self.edit_notes.setToolTip(self.tr(
            "Free-text night notes (seeing, clouds), saved as NS_NOTES"))

        btn_save = QPushButton(self.tr("Save annotated FITS"))
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton(self.tr("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(btn_save)
        save_row.addWidget(btn_cancel)

        marker_box = QGroupBox(self.tr("Marker"))
        mg = QGridLayout(marker_box)
        tip = QLabel(self.tr("Click the preview to place the marker."))
        tip.setWordWrap(True)
        mg.addWidget(self.edit_label, 0, 0, 1, 3)
        mg.addWidget(tip, 1, 0, 1, 3)
        mg.addWidget(QLabel("x"), 2, 0)
        mg.addWidget(self.spin_dx, 2, 1)
        mg.addWidget(btn_nudge, 2, 2)
        mg.addWidget(QLabel("y"), 3, 0)
        mg.addWidget(self.spin_dy, 3, 1)
        mg.addWidget(QLabel(self.tr("Size")), 4, 0)
        mg.addWidget(self.sld_marker, 4, 1, 1, 2)
        mg.addWidget(self.btn_color, 5, 0, 1, 3)
        mg.addWidget(self.chk_north, 6, 0, 1, 3)
        mg.addWidget(self.chk_scale, 7, 0, 1, 3)

        stretch_box = QGroupBox(self.tr("Stretch"))
        sg = QGridLayout(stretch_box)
        sg.addWidget(QLabel(self.tr("Black")), 0, 0)
        sg.addWidget(self.sld_black, 0, 1, 0, 2)
        sg.addWidget(QLabel(self.tr("White")), 1, 0)
        sg.addWidget(self.sld_white, 1, 1, 1, 2)
        sg.addWidget(QLabel(self.tr("Gamma")), 2, 0)
        sg.addWidget(self.sld_gamma, 2, 1, 2, 2)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(marker_box)
        rl.addWidget(stretch_box)
        rl.addStretch(1)
        right.setMaximumWidth(300)

        body = QHBoxLayout()
        body.addWidget(self.lbl_image, 1)
        body.addWidget(right, 0)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel(self.tr("Save to")))
        dest_row.addWidget(self.edit_dest, 1)
        dest_row.addWidget(btn_browse)
        notes_row = QHBoxLayout()
        notes_row.addWidget(QLabel(self.tr("Notes")))
        notes_row.addWidget(self.edit_notes, 1)

        outer = QVBoxLayout(self)
        outer.addLayout(body)
        outer.addLayout(notes_row)
        outer.addLayout(dest_row)
        outer.addLayout(save_row)
        self.setMinimumSize(640, 520)

    def _nudge_spinbox(self):
        # A pixel nudge field: signed, half-pixel steps.
        sb = QDoubleSpinBox()
        sb.setRange(-100.0, 100.0)
        sb.setDecimals(1)
        sb.setSingleStep(0.5)
        return sb

    # ---------------- preview ----------------

    def _render(self):
        # @return: None. Stretches the loaded frame and paints the overlays.
        import numpy as np
        black = self.sld_black.value() / 10.0
        white = float(self.sld_white.value())
        gamma = self.sld_gamma.value() / 100.0
        img8 = np.ascontiguousarray(
            np.flipud(blink_view.to_uint8(
                blink_view.apply_stretch(self._data, black, white, gamma))).
            astype(np.uint8))
        h, w = img8.shape
        if w == 0 or h == 0:
            self.lbl_image.setPixmap(QPixmap())
            return
        qimg = QImage(img8.data, w, h, w, QImage.Format_Grayscale8).copy()
        pix = QPixmap.fromImage(qimg)
        target = min(_MAX_PREVIEW, self._img_w, self._img_h)
        scaled = pix.scaled(QSize(target, target), Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
        self._disp_w = scaled.width()
        self._disp_h = scaled.height()
        self._paint_overlays(scaled)
        self.lbl_image.setPixmap(scaled)

    def _paint_overlays(self, pix):
        # @args: pix - the display pixmap to draw the marker and
        #         overlays onto (in place).
        if self._disp_w <= 0 or self._disp_h <= 0:
            return
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        color = self._marker_color
        disp = min(self._disp_w, self._disp_h)
        r = 0.06 * disp * (self.sld_marker.value() / 10.0)
        # image pixel -> display pixel (the image is flipped top to bottom)
        x = self._xy[0] * self._disp_w / max(self._img_w, 1)
        y = (self._img_h - 1 - self._xy[1]) * self._disp_h / max(self._img_h, 1)
        pen = QPen(color)
        pen.setWidth(max(2, round(2 * (self.sld_marker.value() / 10.0))))
        p.setPen(pen)
        from PySide6.QtCore import QPointF, QRectF
        p.drawEllipse(QPointF(x, y), r, r)
        p.drawLine(QPointF(x - 1.6 * r, y), QPointF(x - 0.5 * r, y))
        p.drawLine(QPointF(x + 0.5 * r, y), QPointF(x + 1.6 * r, y))
        p.drawLine(QPointF(x, y - 1.6 * r), QPointF(x, y - 0.5 * r))
        p.drawLine(QPointF(x, y + 0.5 * r), QPointF(x, y + 1.6 * r))
        text = self.edit_label.text().strip()
        if text:
            p.setPen(QPen(QColor("#ffffff")))
            p.drawText(QRectF(x - 130, y + 1.8 * r, 260, 16),
                       Qt.AlignHCenter, text)
        if self.chk_north.isChecked() and self.north_pa is not None:
            self._paint_north(p, disp)
        if self.chk_scale.isChecked() and self.scale is not None:
            self._paint_scale(p, disp)
        p.end()

    def _paint_north(self, p, disp):
        # North arrow in the top-right corner, rotated by the plate PA.
        # @args: p - active QPainter, disp - display size in px.
        from PySide6.QtCore import QPointF
        cx = disp * 0.86
        cy = disp * 0.14
        length = max(22.0, 0.07 * disp)
        p.save()
        p.translate(cx, cy)
        p.rotate(self.north_pa)  # positive = east of north, clockwise
        pen = QPen(QColor("#ffffff"))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawLine(QPointF(0, length / 2), QPointF(0, -length / 2))
        arrow = length * 0.3
        p.drawLine(QPointF(0, -length / 2), QPointF(-arrow / 2, 0))
        p.drawLine(QPointF(0, -length / 2), QPointF(arrow / 2, 0))
        p.drawText(QRectF(-14, length / 2 + 2, 28, 14),
                   Qt.AlignHCenter, "N")
        p.restore()

    def _paint_scale(self, p, disp):
        # Scale bar in the bottom-left corner: picks a round arcsec span
        # that lands at a comfortable length for this zoom.
        # @args: p - active QPainter, disp - display size in px.
        per_disp = self.scale * self._img_w / max(self._disp_w, 1)
        target_arcsec = 90.0 * per_disp
        exp = math.floor(math.log10(max(target_arcsec, 1e-9)))
        m = min((1.0, 2.0, 5.0), key=lambda v:
                abs(math.log10(v * 10.0 ** exp) - math.log10(target_arcsec)))
        arcsec = m * 10.0 ** exp
        bar = min(max(arcsec / max(per_disp, 1e-9), 12.0), disp * 0.35)
        x0, y0 = disp * 0.06, disp * 0.90
        pen = QPen(QColor("#ffffff"))
        pen.setWidth(2)
        p.setPen(pen)
        p.drawLine(x0, y0, x0 + bar, y0)
        p.drawLine(x0, y0 - 5, x0, y0 + 5)
        p.drawLine(x0 + bar, y0 - 5, x0 + bar, y0 + 5)
        label = f"{arcsec:g}\""
        p.drawText(QRectF(x0, y0 + 7, bar + 12, 14),
                   Qt.AlignLeft | Qt.AlignBottom, label)

    # ---------------- interaction ----------------

    def _image_clicked(self, ev):
        # @args: ev - QMouseEvent on the preview label; places the marker.
        pix = self.lbl_image.pixmap()
        if pix is None or pix.width() <= 0 or pix.height() <= 0:
            return
        fx = ev.position().x() * self._img_w / pix.width()
        fy = (self._img_h - 1) - ev.position().y() * self._img_h / pix.height()
        self._xy = [min(max(fx, 0.0), self._img_w - 1.0),
                    min(max(fy, 0.0), self._img_h - 1.0)]
        self._render()

    def _apply_nudge(self):
        # @return: None. Shifts the marker by the nudge fields, clamped.
        x = self._xy[0] + self.spin_dx.value()
        y = self._xy[1] + self.spin_dy.value()
        self._xy = [min(max(x, 0.0), self._img_w - 1.0),
                    min(max(y, 0.0), self._img_h - 1.0)]
        self._render()

    def _pick_color(self):
        # @return: None. Colour picker for the marker.
        c = QColorDialog.getColor(self._marker_color, self,
                                  self.tr("Marker colour"))
        if c.isValid():
            self._marker_color = c
            self._render()

    def _browse_dest(self):
        # @return: None. Native save dialog, prefilled from the field.
        start = self.edit_dest.text().strip()
        dest = QFileDialog.getSaveFileName(
            self, self.tr("Annotated FITS"), start,
            self.tr("FITS files (*.fits *.fts);;All files (*)"))[0]
        if dest:
            self.edit_dest.setText(dest)

    # ---------------- save ----------------

    def _save(self):
        # @return: None. Writes the annotated copy; on success emits saved
        #          and closes, on failure stays open with the error.
        from ..core import fits_annotate
        dest = self.edit_dest.text().strip()
        if not dest:
            QMessageBox.warning(
                self, self.tr("Annotated FITS"),
                self.tr("Choose where to save the file."))
            return
        try:
            fits_annotate.write_annotated_fits(
                self.fits_path, dest, sn_xy=tuple(self._xy),
                scale=self.scale, north_pa=self.north_pa,
                obj_name=self.edit_label.text().strip(),
                ra_deg=self.ra_deg, dec_deg=self.dec_deg,
                notes=self.edit_notes.text().strip())
        except Exception as err:
            QMessageBox.warning(
                self, self.tr("Annotated FITS"),
                self.tr("Could not write the annotated FITS: %1")
                .replace("%1", str(err)))
            return
        self.saved.emit(dest)
        self.accept()
