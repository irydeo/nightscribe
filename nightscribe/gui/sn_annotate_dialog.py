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

When the project has several registered stacks (several visits) the
observer first picks which one to annotate with the "Image" selector.
Then, before writing the annotated copy, the observer looks at the frame
(same stretch pipeline as the blink preview: black/white/gamma percent
points), places the marker (nudge by pixels or click on the preview),
edits the label, and fine-tunes the marker size and colour. The north
arrow and scale bar overlays are preview helpers: on disk the facts live
in the header (NS_SCALE, NS_NORTH) and AIJ does its own rendering of the
ANNOTATE card.

The preview size is the observer's call: Fit grows the plate to the
window (with a legibility floor) and Fit can be swapped for a 50/100/200
percent zoom; the area scrolls, it is never cropped on the software side
and the full-resolution FITS is what gets written.

The WCS is resolved from the header of the selected frame: the marker
starts at the SN sky position on that plate (each visit may sit on a
different one) and falls back to the field centre when the plate has no
WCS or the SN is out of field.

Save writes a copy (core.fits_annotate) to the chosen path, defaulting to
the project folder; the observer's original FITS is never touched. The
dialog stays on screen while it fails.
"""

import math
import os
import logging

from PySide6.QtCore import Qt, Signal, QSize, QPointF, QRectF, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)

from ..core import stretch

logger = logging.getLogger("nightscribe.gui.sn_annotate")

_MARKER_DEFAULT = "#ffb347"   # the same amber the blink marker uses
_FIT_MIN = (720, 480)         # Fit floor, keeps small plates legible
_RENDER_COALESCE_MS = 120     # slider drags collapse into a single render


class SnAnnotateDialog(QDialog):
    """Pick the frame, preview the annotated view, save the FITS copy."""

    saved = Signal(str)  # fired with the written path, then the dialog closes

    def __init__(self, parent, images, project, object_name, ra_deg=None,
                 dec_deg=None, default_notes=""):
        # @args: images - list of {fits_path, date_obs} (>= 1 plates),
        #        project - project dict or None (the save path then falls
        #        back to the projects folder),
        #        object_name - label text, ra_deg/dec_deg - J2000 sky of
        #        the SN or None (then the marker starts in the field
        #        centre of each plate),
        #        default_notes - pre-filled notes for the NS_NOTES card
        # @return: None
        super().__init__(parent)
        self._images = list(images or [])
        if not self._images:
            raise ValueError("At least one image is required")
        self._project = project
        self._object = object_name
        self._sky = ((float(ra_deg), float(dec_deg))
                     if ra_deg is not None and dec_deg is not None
                     else None)
        self._default_notes = default_notes

        self._xy = [0.0, 0.0]       # marker in image pixels (row 0 = top)
        self._data = None           # frame currently stretched
        self._img_h = 0
        self._img_w = 0
        self.scale = None           # image scale in arcsec/px, or None
        self.north_pa = None        # north position angle in deg, or None
        self._marker_color = QColor(_MARKER_DEFAULT)

        # stretch state in percentile points and gamma (0 = black point,
        # 100 = white point of the flat histogram)
        self._black_pct = 1.0
        self._white_pct = 99.5
        self._gamma = 1.0
        self._ui_sync = False       # guard while we mirror state into widgets

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render)

        self._build_ui(project, object_name, default_notes)
        self.setMinimumSize(780, 540)
        self.resize(1180, 820)
        self._on_image_changed(0)

    # ------------------------------------------------------------------ UI
    def _build_ui(self, project, object_name, default_notes):
        body = QVBoxLayout(self)

        # --- header row: pick the frame, then the label / notes
        top = QHBoxLayout()
        top.addWidget(QLabel(self.tr("Image:")))
        self.cmb_image = QComboBox()
        for it in self._images:
            d = it.get("date_obs") or it.get("obs_date") or "-"
            cap = d if len(str(d)) <= 12 else str(d)[:12]
            self.cmb_image.addItem(
                f"{object_name}  {cap}",
                None)  # the index already names the entry
        self.cmb_image.activated.connect(self._on_image_changed)
        top.addWidget(self.cmb_image, 1)
        body.addLayout(top)

        form = QGridLayout()
        form.addWidget(QLabel(self.tr("Label:")), 0, 0)
        self.edit_label = QLineEdit(object_name)
        form.addWidget(self.edit_label, 0, 1)
        self.edit_label.textChanged.connect(self._render)

        form.addWidget(QLabel(self.tr("Notes:")), 1, 0)
        self.edit_notes = QLineEdit(str(default_notes))
        form.addWidget(self.edit_notes, 1, 1)
        self.edit_notes.textChanged.connect(self._render)

        body.addLayout(form)

        # --- stretch: percentile points, the observer owns the frame
        stretch_box = QGroupBox(self.tr("Stretch"))
        sg = QGridLayout(stretch_box)
        row_black, self.sld_black, self.spin_black = self._stretch_row(
            0.0, 50.0,
            self.tr("Black point: percent of the flat below this floor (0–50)."))
        row_white, self.sld_white, self.spin_white = self._stretch_row(
            5.0, 100.0,
            self.tr("White point: percent of the flat at full white (5–100); "
                    "lower it to bring down a bright core."))
        self.sld_black.valueChanged.connect(self._on_black_slider)
        self.spin_black.valueChanged.connect(self._on_black_spin)
        self.sld_white.valueChanged.connect(self._on_white_slider)
        self.spin_white.valueChanged.connect(self._on_white_spin)
        sg.addWidget(QLabel(self.tr("Black point")), 0, 0)
        sg.addWidget(row_black, 0, 1, 1, 2)
        sg.addWidget(QLabel(self.tr("White point")), 1, 0)
        sg.addWidget(row_white, 1, 1, 1, 2)

        self.spin_gamma = QDoubleSpinBox()
        self.spin_gamma.setRange(0.2, 3.0)
        self.spin_gamma.setDecimals(2)
        self.spin_gamma.setSingleStep(0.05)
        self.spin_gamma.setToolTip(
            self.tr("Gamma of the stretch curve: below 1 brightens the mids, "
                    "above 1 darkens them."))
        self.spin_gamma.valueChanged.connect(self._on_gamma_spin)
        sg.addWidget(QLabel(self.tr("Gamma")), 2, 0)
        sg.addWidget(self.spin_gamma, 2, 1)

        btn_auto = QPushButton(self.tr("Auto stretch"))
        btn_auto.clicked.connect(self._auto_stretch)
        sg.addWidget(btn_auto, 3, 1, 1, 2)
        sg.setColumnStretch(1, 1)
        body.addWidget(stretch_box)

        # --- overlay toggles: north arrow and scale bar, preview only
        overlays = QHBoxLayout()
        self.chk_north = QPushButton(self.tr("North arrow"))
        self.chk_north.setCheckable(True)
        self.chk_north.toggled.connect(self._render)
        overlays.addWidget(self.chk_north)
        self.chk_scale = QPushButton(self.tr("Scale bar"))
        self.chk_scale.setCheckable(True)
        self.chk_scale.toggled.connect(self._render)
        overlays.addWidget(self.chk_scale)
        overlays.addStretch(1)

        overlays.addWidget(QLabel(self.tr("Marker size:")))
        self.sld_marker = QSlider(Qt.Horizontal)
        self.sld_marker.setRange(2, 30)
        self.sld_marker.setValue(10)
        self.sld_marker.valueChanged.connect(self._render_soon)
        overlays.addWidget(self.sld_marker)

        self.btn_color = QPushButton(_MARKER_DEFAULT)
        self.btn_color.setAccessibleName("marker color")
        self.btn_color.clicked.connect(self._pick_color)
        overlays.addWidget(self.btn_color)

        self.spin_dx = self._nudge_spinbox()
        self.spin_dy = self._nudge_spinbox()
        overlays.addWidget(self.spin_dx)
        overlays.addWidget(self.spin_dy)
        btn_nudge = QPushButton(self.tr("Nudge"))
        btn_nudge.setToolTip(self.tr(
            "Shift the marker by that many pixels (or click the preview)"))
        btn_nudge.clicked.connect(self._apply_nudge)
        overlays.addWidget(btn_nudge)
        body.addLayout(overlays)

        # --- preview: scrollable, the zoom level is the observer's call
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.lbl_image = QLabel()
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.mousePressEvent = self._image_clicked
        self.lbl_image.setToolTip(self.tr("Click to place the marker there"))
        self.scroll.setWidget(self.lbl_image)

        self.cmb_zoom = QComboBox()
        self.cmb_zoom.addItem(self.tr("Fit"), None)
        self.cmb_zoom.addItem("50 %", 0.5)
        self.cmb_zoom.addItem("100 %", 1.0)
        self.cmb_zoom.addItem("200 %", 2.0)
        self.cmb_zoom.currentIndexChanged.connect(self._zoom_changed)

        zoom_row = QHBoxLayout()
        zoom_row.addStretch(1)
        zoom_row.addWidget(QLabel(self.tr("Zoom:")))
        zoom_row.addWidget(self.cmb_zoom)

        preview_col = QWidget()
        pv = QVBoxLayout(preview_col)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.addWidget(self.scroll, 1)
        pv.addLayout(zoom_row)
        body.addWidget(preview_col, 1)

        self.lbl_image_caption = QLabel(self._image_caption())
        body.addWidget(self.lbl_image_caption)

        # --- save target + buttons
        save_row = QHBoxLayout()
        save_row.addWidget(QLabel(self.tr("Save to:")))
        self.edit_dest = QLineEdit(self._default_dest(project, object_name))
        save_row.addWidget(self.edit_dest, 1)
        self.btn_browse = QPushButton("...")
        self.btn_browse.setProperty("compact", True)   # see ufe_compare_tab
        self.btn_browse.setAccessibleName("browse")
        self.btn_browse.clicked.connect(self._browse_dest)
        save_row.addWidget(self.btn_browse)
        body.addLayout(save_row)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_cancel = QPushButton(self.tr("Cancel"))
        self.btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(self.btn_cancel)
        self.btn_save = QPushButton(self.tr("Save annotated FITS"))
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self._save)
        buttons.addWidget(self.btn_save)
        body.addLayout(buttons)

        # mirror the stretch state into the freshly built widgets
        self._push_stretch_ui(black=True, white=True, gamma=True)

    # ------------------------------------------------------------- stretch
    def _stretch_row(self, lo, hi, tip):
        # One percentile point as a single row: a slider in 0.1 % ticks
        # and a spinbox in plain percent, sharing the tooltip.
        # @args: lo, hi - percentile range of the point, tip - tooltip
        # @return: (row widget, slider, spinbox)
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        sld = QSlider(Qt.Horizontal)
        sld.setRange(int(lo * 10), int(hi * 10))
        sld.setPageStep(max(1, int((hi - lo) / 10)))
        sld.setToolTip(tip)
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(1)
        spin.setSingleStep(0.1)
        spin.setSuffix(" %")
        spin.setToolTip(tip)
        lay.addWidget(sld, 1)
        lay.addWidget(spin)
        return row, sld, spin

    def _on_black_slider(self, ticks):
        # @args: ticks - slider position in 0.1 % units
        # @return: None.
        if self._ui_sync:
            return
        self._set_black(ticks / 10.0)

    def _on_black_spin(self, pct):
        # @args: pct - black point in percent
        # @return: None.
        if self._ui_sync:
            return
        self._set_black(pct)

    def _on_white_slider(self, ticks):
        # @args: ticks - slider position in 0.1 % units
        # @return: None.
        if self._ui_sync:
            return
        self._set_white(ticks / 10.0)

    def _on_white_spin(self, pct):
        # @args: pct - white point in percent
        # @return: None.
        if self._ui_sync:
            return
        self._set_white(pct)

    def _on_gamma_spin(self, g):
        # @args: g - gamma from the spinbox (0.2–3.0)
        # @return: None.
        if self._ui_sync:
            return
        self._set_gamma(g)

    def _set_black(self, pct):
        # @args: pct - black point in percent of the flat (0–50)
        # @return: None. Clamped so white stays at least 1.0 above it;
        #          the black widgets snap to the result and re-draw soon.
        v = min(max(float(pct), 0.0), max(self._white_pct - 1.0, 0.0))
        if v == self._black_pct:
            return
        self._black_pct = v
        self._push_stretch_ui(black=True)
        self._render_soon()

    def _set_white(self, pct):
        # @args: pct - white point in percent of the flat (5–100)
        # @return: None. Clamped so it stays at least 1.0 above black;
        #          the white widgets snap to the result and re-draw soon.
        v = max(min(float(pct), 100.0), max(self._black_pct + 1.0, 5.0))
        if v == self._white_pct:
            return
        self._white_pct = v
        self._push_stretch_ui(white=True)
        self._render_soon()

    def _set_gamma(self, g):
        # @args: g - gamma of the stretch (0.2–3.0)
        # @return: None. Clamped into range and the preview re-draws.
        v = min(max(float(g), 0.2), 3.0)
        if v == self._gamma:
            return
        self._gamma = v
        self._push_stretch_ui(gamma=True)
        self._render_soon()

    def _auto_stretch(self):
        # @return: None. Restores the robust percentile points and
        #          gamma 1, a known-good starting view.
        self._set_black(1.0)
        self._set_white(99.5)
        self._set_gamma(1.0)

    def _push_stretch_ui(self, black=False, white=False, gamma=False):
        # @args: black, white, gamma - which widget pair to mirror into
        # @return: None. Writes the state into the sliders/spinboxes;
        #          the _ui_sync guard stops it echoing back in.
        self._ui_sync = True
        try:
            if black:
                self.sld_black.setValue(int(round(self._black_pct * 10)))
                self.spin_black.setValue(float(round(self._black_pct, 1)))
            if white:
                self.sld_white.setValue(int(round(self._white_pct * 10)))
                self.spin_white.setValue(float(round(self._white_pct, 1)))
            if gamma:
                self.spin_gamma.setValue(float(round(self._gamma, 2)))
        finally:
            self._ui_sync = False

    # --------------------------------------------------------------- render
    def _render_soon(self):
        # @return: None. Coalesces a burst of ticks into a single render.
        if not self._render_timer.isActive():
            self._render_timer.start(_RENDER_COALESCE_MS)

    def _zoom_changed(self, index):
        # @args: index - the freshly selected zoom level
        # @return: None. Re-fits or re-scales the preview soon.
        if self._data is not None:
            self._render_soon()

    def resizeEvent(self, ev):
        # @args: ev - the widget resize event
        # @return: None; Follows the Fit zoom while the dialog is sized.
        super().resizeEvent(ev)
        if (getattr(self, "cmb_zoom", None) is not None
                and getattr(self, "_data", None) is not None
                and self.cmb_zoom.currentData() is None):
            self._render_soon()

    def _scaled_for(self, base):
        # @args: base - full-resolution pixmap of the stretched frame.
        # @return: the display pixmap at the zoom level the observer
        #          chose; Fit grows to the viewport (with a legibility
        #          floor) and the percentages scale from full resolution.
        factor = self.cmb_zoom.currentData()
        if factor is None:
            vp = self.scroll.viewport().size()
            target = QSize(max(vp.width() - 24, _FIT_MIN[0]),
                           max(vp.height() - 24, _FIT_MIN[1]))
        else:
            target = QSize(max(1, round(base.width() * factor)),
                           max(1, round(base.height() * factor)))
        return base.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _render(self):
        # @return: None. Stretches the loaded frame and paints overlays.
        import numpy as np
        self.lbl_image_caption.setText(self._image_caption())
        if self._data is None:
            self.lbl_image.setPixmap(QPixmap())
            return
        black, white = stretch.auto_limits(
            self._data, self._black_pct, self._white_pct)
        img8 = np.ascontiguousarray(
            np.flipud(stretch.to_uint8(
                stretch.apply_stretch(
                    self._data, black, white, self._gamma))).
            astype(np.uint8))
        h, w = img8.shape
        if w == 0 or h == 0:
            self.lbl_image.setPixmap(QPixmap())
            return
        qimg = QImage(img8.data, w, h, w, QImage.Format_Grayscale8).copy()
        base = QPixmap.fromImage(qimg)
        scaled = self._scaled_for(base)
        self._disp_w = scaled.width()
        self._disp_h = scaled.height()
        self._paint_overlays(scaled)
        self.lbl_image.setMinimumSize(0, 0)
        self.lbl_image.setPixmap(scaled)
        self.lbl_image.setMinimumSize(scaled.size())

    def _paint_overlays(self, pix):
        # @args: pix - the display pixmap to draw marker and overlays onto
        #          (in place).
        if self._disp_w <= 0 or self._disp_h <= 0:
            return
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        color = self._marker_color
        disp = min(self._disp_w, self._disp_h)
        k = max(1.0, disp / 480.0)          # box and font grow with the view
        pen_w = max(2.0, disp / 400.0)      # marker and lines stay visible
        fnt = QFont(p.font())
        fnt.setPixelSize(int(max(12, round(disp / 45.0))))
        p.setFont(fnt)
        r = 0.06 * disp * (self.sld_marker.value() / 10.0)
        # image pixel -> display pixel (the image is flipped top to bottom)
        x = self._xy[0] * self._disp_w / max(self._img_w, 1)
        y = (self._img_h - 1 - self._xy[1]) * self._disp_h / max(self._img_h, 1)
        pen = QPen(color)
        pen.setWidthF(pen_w)
        p.setPen(pen)
        p.drawEllipse(QPointF(x, y), r, r)
        p.drawLine(QPointF(x - 1.6 * r, y), QPointF(x - 0.5 * r, y))
        p.drawLine(QPointF(x + 0.5 * r, y), QPointF(x + 1.6 * r, y))
        p.drawLine(QPointF(x, y - 1.6 * r), QPointF(x, y - 0.5 * r))
        p.drawLine(QPointF(x, y + 0.5 * r), QPointF(x, y + 1.6 * r))
        text = self.edit_label.text().strip()
        if text:
            p.setPen(QPen(QColor("#ffffff"), pen_w))
            bw, bh = int(round(260 * k)), int(round(18 * k))
            p.drawText(QRectF(x - bw / 2, y + 1.8 * r, bw, bh),
                       Qt.AlignHCenter, text)
        if self.chk_north.isChecked() and self.north_pa is not None:
            self._paint_north(p, disp, k, pen_w)
        if self.chk_scale.isChecked() and self.scale is not None:
            self._paint_scale(p, disp, k, pen_w)
        p.end()

    def _paint_north(self, p, disp, k, pen_w):
        # North arrow in the top-right corner, rotated by the plate PA.
        # @args: p - active QPainter, disp - display size in px, k and
        #         pen_w - growth factors shared with the rest of the view.
        cx = disp * 0.86
        cy = disp * 0.14
        length = max(22.0, 0.07 * disp)
        p.save()
        p.translate(cx, cy)
        p.rotate(self.north_pa)  # positive = east of north, clockwise
        p.setPen(QPen(QColor("#ffffff"), pen_w))
        p.drawLine(QPointF(0, length / 2), QPointF(0, -length / 2))
        arrow = length * 0.3
        p.drawLine(QPointF(0, -length / 2), QPointF(-arrow / 2, 0))
        p.drawLine(QPointF(0, -length / 2), QPointF(arrow / 2, 0))
        p.drawText(QRectF(-14 * k, length / 2 + 2 * k, 28 * k, 14 * k),
                   Qt.AlignHCenter, "N")
        p.restore()

    def _paint_scale(self, p, disp, k, pen_w):
        # Scale bar in the bottom-left corner: picks a round arcsec span
        # that lands at a comfortable length for this zoom.
        # @args: p - active QPainter, disp - display size in px, k and
        #         pen_w - growth factors shared with the rest of the view.
        per_disp = self.scale * self._img_w / max(self._disp_w, 1)
        target_arcsec = 90.0 * per_disp
        exp = math.floor(math.log10(max(target_arcsec, 1e-9)))
        m = min((1.0, 2.0, 5.0), key=lambda v:
                abs(math.log10(v * 10.0 ** exp) - math.log10(target_arcsec)))
        arcsec = m * 10.0 ** exp
        bar = min(max(arcsec / max(per_disp, 1e-9), 12.0), disp * 0.35)
        x0, y0 = disp * 0.06, disp * 0.90
        p.setPen(QPen(QColor("#ffffff"), pen_w))
        p.drawLine(x0, y0, x0 + bar, y0)
        p.drawLine(x0, y0 - 5 * k, x0, y0 + 5 * k)
        p.drawLine(x0 + bar, y0 - 5 * k, x0 + bar, y0 + 5 * k)
        label = f"{arcsec:g}\""
        p.drawText(QRectF(x0, y0 + 7 * k, bar + 12 * k, 16 * k),
                   Qt.AlignLeft | Qt.AlignBottom, label)

    def _image_clicked(self, ev):
        # @args: ev - mouse click on the preview label; places the
        #          marker where the observer clicked.
        # @return: None.
        pix = self.lbl_image.pixmap()
        if pix is None or pix.width() <= 0 or pix.height() <= 0:
            return
        # the label is usually bigger than the image (centered): strip
        # the offset so the click lands on the right plate pixel
        ox = max(0, (self.lbl_image.width() - pix.width()) // 2)
        oy = max(0, (self.lbl_image.height() - pix.height()) // 2)
        px = ev.position().x() - ox
        py = ev.position().y() - oy
        if px < 0 or py < 0 or px >= pix.width() or py >= pix.height():
            return  # outside the image: nothing to place on
        fx = px * self._img_w / pix.width()
        fy = (self._img_h - 1) - py * self._img_h / pix.height()
        self._xy = [min(max(fx, 0.0), self._img_w - 1.0),
                    min(max(fy, 0.0), self._img_h - 1.0)]
        self._render()

    # --------------------------------------------------------------- picker
    def _plate_state(self, path):
        # @args: path - FITS path to resolve.
        # @return: (2D float32 data, h, w, sn image pixel 0-based or None,
        #          arcsec/px or None, north PA or None); data is None on
        #          unreadable frames and the wcs slots stay None when the
        #          plate has no TAN grid.
        try:
            from ..core import fits_io, wcs as wcs_mod
            header, data = fits_io.read_fits(path)
        except Exception:
            logger.warning("plate unreadable, left blank: %s", path)
            return None, 0, 0, None, None, None
        h, w = int(data.shape[0]), int(data.shape[1])
        sn_xy = scale = north_pa = None
        try:
            wc = wcs_mod.Wcs.from_header(header)
        except Exception:
            wc = None
        if wc is not None:
            try:
                scale = wc.pixel_scale()
                north_pa = -wc.rotation()
            except Exception:
                scale = None
                north_pa = None
            if self._sky is not None:
                try:
                    px, py = wc.sky_to_pixel(self._sky[0], self._sky[1])
                    if 0.0 <= px < w and 0.0 <= py < h:
                        sn_xy = (float(px), float(py))
                except Exception:
                    pass  # out of field on this plate: centre below
        return data, h, w, sn_xy, scale, north_pa

    def _default_dest(self, project, object_name):
        # @args: project - project dict or None, object_name - label
        # @return: the destination FITS to suggest: the project folder
        #          when there is one, the ~/Nightscribe/projects folder
        #          when not.
        name = "".join(c for c in str(object_name) if c.isalnum() or c in "_-") or "obs"
        base = f"{name}_annotated.fits"
        try:
            from ..core import project as pj
            from .. import paths
            if project is not None:
                d = str(pj.storage_dir(project))
            else:
                d = str(paths.project_dir(
                    0, str(object_name)))
            from pathlib import Path
            return str(Path(d) / base)
        except Exception:
            return base

    # -------------------------------------------------------------- caption
    def _image_caption(self):
        # @return: a small line under the frame: plate name, WCS and SN
        #          pixel position when the plate carries them.
        parts = []
        if self._images:
            d = self._images[0].get("date_obs") or self._images[0].get("obs_date") or "-"
            parts.append(str(d))
        if self.scale is not None:
            parts.append(f"{self.scale:.3f} arcsec/px")
        if self.north_pa is not None:
            parts.append(self.tr("north PA {}")
                         .format(f"{self.north_pa:.1f}°"))
        if 0.0 <= self._xy[0] <= max(self._img_w, 1):
            parts.append(self.tr("marker {:.1f}, {:.1f}")
                         .format(self._xy[0], self._xy[1]))
        return "  •  ".join(parts)

    def _nudge_spinbox(self):
        # @return: one nudge field, in image pixels (y positive = up),
        #          freshly built.
        sb = QDoubleSpinBox()
        sb.setRange(-100.0, 100.0)
        sb.setDecimals(1)
        sb.setSingleStep(0.5)
        return sb

    def _apply_nudge(self):
        # @return: None. Shifts the marker by the two nudge fields,
        #          clamped to the frame, and re-draws right away.
        if self._data is None:
            return
        x = self._xy[0] + self.spin_dx.value()
        y = self._xy[1] + self.spin_dy.value()
        self._xy = [min(max(x, 0.0), self._img_w - 1.0),
                    min(max(y, 0.0), self._img_h - 1.0)]
        self._render()

    def _pick_color(self):
        # @return: None. Asks for the marker colour and re-draws.
        c = QColorDialog.getColor(self._marker_color, self)
        if c.isValid():
            self._marker_color = c
            self.btn_color.setStyleSheet(f"background: {c.name()};")
            self.btn_color.setText(c.name())
            self._render()

    def _browse_dest(self):
        # @return: None. File dialog to choose the save destination.
        p, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save annotated FITS as"), self.edit_dest.text(),
            "FITS (*.fits *.fit)")
        if p:
            self.edit_dest.setText(p)

    def _save(self):
        # @return: None. Writes the annotated copy; on failure explains
        #          and leaves the dialog open.
        dest = (self.edit_dest.text().strip()
                or self._default_dest(self._project, self._object))
        try:
            from ..core import fits_annotate
            fits_annotate.write_annotated_fits(
                self.fits_path, dest,
                sn_xy=(self._xy[0], self._xy[1]),
                scale=self.scale,
                north_pa=self.north_pa,
                obj_name=self.edit_label.text().strip() or self._object,
                ra_deg=self._sky[0] if self._sky is not None else None,
                dec_deg=self._sky[1] if self._sky is not None else None,
                notes=self.edit_notes.text().strip())
            logger.info("annotated FITS written to %s", dest)
            self.saved.emit(dest)
            self.accept()
        except Exception as exc:  # never crash, never touch the source
            logger.exception("annotated save failed: %s", exc)
            QMessageBox.critical(
                self, self.tr("Save failed"),
                self.tr("Could not write the annotated FITS to %1.\n%2")
                .format(dest, str(exc)))

    # ---------------------------------------------------------------- state
    def fits_path_for(self, idx):
        # @args: idx - combo index
        # @return: the FITS path of that entry (the selector owns it).
        return str(self._images[idx]["fits_path"])

    @property
    def fits_path(self):
        # @return: FITS path of the plate currently selected.
        return self.fits_path_for(self.cmb_image.currentIndex())

    def _on_image_changed(self, idx):
        # @args: idx - combo index of the freshly selected plate.
        # @return: None. Resolves the WCS of that frame (the marker can
        #         land elsewhere on each visit) and re-draws the preview.
        self._apply_plate(self.fits_path_for(idx))

    def _apply_plate(self, path):
        # @args: path - FITS of the plate to show and annotate.
        # @return: None. Sets the frame, the marker start position and
        #          the overlay defaults for that plate.
        state = self._plate_state(path)
        if state[0] is None:
            # unreadable frame: leave the preview empty but keep the
            # dialog usable, the observer can still pick another plate
            self._data = None
            self._img_h = 0
            self._img_w = 0
            self.scale = None
            self.north_pa = None
            self._xy = [40.0, 40.0]
            self.chk_north.setChecked(False)
            self.chk_north.setEnabled(False)
            self.chk_scale.setChecked(False)
            self.chk_scale.setEnabled(False)
            self._render()
            return
        data, h, w, sn_xy, scale, north_pa = state
        self._data = data
        self._img_h = h
        self._img_w = w
        self.scale = scale
        self.north_pa = north_pa
        if sn_xy is not None and 0 <= sn_xy[0] < w and 0 <= sn_xy[1] < h:
            self._xy = [float(sn_xy[0]), float(sn_xy[1])]
        else:
            self._xy = [w / 2.0, h / 2.0]
        # re-assert the toggle defaults without a double render in between
        self.chk_north.blockSignals(True)
        self.chk_scale.blockSignals(True)
        try:
            self.chk_north.setChecked(north_pa is not None)
            self.chk_north.setEnabled(north_pa is not None)
            self.chk_scale.setChecked(scale is not None)
            self.chk_scale.setEnabled(scale is not None)
        finally:
            self.chk_north.blockSignals(False)
            self.chk_scale.blockSignals(False)
        self._render()
