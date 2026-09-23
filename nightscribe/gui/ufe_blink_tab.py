############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Blink tab (ADR-044, phase E)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The UFE's Blink tab (ADR-044, phase E): supernova / transient blinking
against a PanSTARRS DR1 g reference, on top of core/blink.prepare_pair +
BlinkWorker (the legacy ad-hoc dialog keeps living untouched).

How it fits the shared editor:

* The plate comes from the shared state (the common «Load FITS…»); the
  tab only asks for the target (SN name or manual RA/Dec) and prepares
  the aligned pair off the GUI thread.
* While the tab is on stage it owns the view's frame through
  set_frame_override: the obs frame stretches with the SHARED absolute
  DN controls (the histogram strip drives the blink), the PS1 reference
  keeps its own auto percentiles times the balance gain. Both honour the
  common gamma and invert.
* Mirrored plates: blink flips them to match the survey; the editor
  un-flips both frames back, so the blink shows the plate's true
  orientation and the marker (mapped through the plate's own WCS from
  the SN's sky position) always lands right.
* Exports (GIF / MP4 / side-by-side PNG) reuse BlinkExportWorker with
  the frames in DATA orientation, exactly like the legacy dialog; the
  zoom crop centres on the SN.
"""

import logging
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog,
                               QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QRadioButton,
                               QSlider, QSpinBox, QVBoxLayout, QWidget,
                               QGraphicsEllipseItem, QGraphicsLineItem,
                               QGraphicsSimpleTextItem)

from ..core import stretch

logger = logging.getLogger("nightscribe.gui.ufe_blink_tab")

_MARKER_COLOR = "#ffb347"   # the amber the legacy blink marker wears


class UfeBlinkTab(QWidget):
    # @args: state - the shared UfeImageState, lang - "es" | "en",
    #        view - the UfeImageView the blink frames and marker live on

    def __init__(self, state, lang="es", view=None, parent=None):
        super().__init__(parent)
        self._state = state
        self._lang = lang
        self._view = view
        self._active = False
        self._pair = None            # core/blink.prepare_pair dict
        self._ref8 = None            # reference frame, DATA orientation
        self._obs8 = None            # observed frame, DATA orientation
        self._phase = 0              # 0 = obs on screen, 1 = ref
        self._gain = 1.0             # balance: ref multiplier
        self._items = []             # the SN marker's scene items
        self._export_workers = []    # BlinkExportWorker refs in flight
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._build_ui()
        state.image_loaded.connect(self._on_image_loaded)
        state.stretch_changed.connect(self._on_stretch_changed)
        if view is not None:
            view.zoom_changed.connect(lambda _f: self._layout_marker())
        self._on_image_loaded()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("SN:")))
        self.edt_name = QLineEdit()
        self.edt_name.setPlaceholderText("SN 2026xyz")
        row.addWidget(self.edt_name, 1)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.chk_manual = QCheckBox(self.tr("Manual coordinates"))
        self.chk_manual.toggled.connect(self._on_manual_toggled)
        row.addWidget(self.chk_manual)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.edt_ra = QLineEdit()
        self.edt_ra.setPlaceholderText(self.tr("RA deg"))
        self.edt_dec = QLineEdit()
        self.edt_dec.setPlaceholderText(self.tr("Dec deg"))
        row.addWidget(self.edt_ra)
        row.addWidget(self.edt_dec)
        lay.addLayout(row)
        self.btn_prepare = QPushButton(self.tr("Prepare pair"))
        self.btn_prepare.clicked.connect(self._on_prepare)
        lay.addWidget(self.btn_prepare)
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        row = QHBoxLayout()
        self.chk_live = QCheckBox(self.tr("Live blink"))
        self.chk_live.setChecked(True)
        self.chk_live.toggled.connect(self._on_live_toggled)
        row.addWidget(self.chk_live)
        row.addWidget(QLabel(self.tr("Interval:")))
        self.spn_interval = QSpinBox()
        self.spn_interval.setRange(100, 5000)
        self.spn_interval.setValue(500)
        self.spn_interval.setSuffix(" ms")
        self.spn_interval.valueChanged.connect(self._on_interval_changed)
        row.addWidget(self.spn_interval)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.rdo_blink = QRadioButton(self.tr("Blink"))
        self.rdo_blink.setChecked(True)
        self.rdo_fade = QRadioButton(self.tr("Fade"))
        self.rdo_blink.toggled.connect(self._on_mode_changed)
        row.addWidget(self.rdo_blink)
        row.addWidget(self.rdo_fade)
        self.sld_fade = QSlider(Qt.Horizontal)
        self.sld_fade.setRange(0, 100)
        self.sld_fade.setValue(50)
        self.sld_fade.setEnabled(False)
        self.sld_fade.valueChanged.connect(self._render_frames)
        row.addWidget(self.sld_fade)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Balance:")))
        self.sld_balance = QSlider(Qt.Horizontal)
        self.sld_balance.setRange(25, 400)     # gain 0.25..4.0
        self.sld_balance.setValue(100)
        self.sld_balance.setToolTip(self.tr(
            "Multiplies the reference so its sky background matches the "
            "plate's (a blink that does not pump)"))
        self.sld_balance.valueChanged.connect(self._on_balance_changed)
        row.addWidget(self.sld_balance, 1)
        self.btn_balance_auto = QPushButton(self.tr("Auto"))
        self.btn_balance_auto.clicked.connect(self._on_balance_auto)
        row.addWidget(self.btn_balance_auto)
        lay.addLayout(row)

        # Fine alignment: the cross of half-pixel steps from the legacy
        # blink dialog (up adds to y, which reads up on screen).
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Fine alignment:")))
        grid = QGridLayout()
        grid.setSpacing(2)
        self.btn_up = QPushButton(self.tr("↑"))
        self.btn_up.clicked.connect(lambda: self._nudge_step(0.0, 0.5))
        grid.addWidget(self.btn_up, 0, 1)
        self.btn_left = QPushButton(self.tr("←"))
        self.btn_left.clicked.connect(lambda: self._nudge_step(-0.5, 0.0))
        grid.addWidget(self.btn_left, 1, 0)
        self.lbl_nudge = QLabel("(0.0, 0.0)")
        self.lbl_nudge.setAlignment(Qt.AlignCenter)
        grid.addWidget(self.lbl_nudge, 1, 1)
        self.btn_right = QPushButton(self.tr("→"))
        self.btn_right.clicked.connect(
            lambda: self._nudge_step(0.5, 0.0))
        grid.addWidget(self.btn_right, 1, 2)
        self.btn_down = QPushButton(self.tr("↓"))
        self.btn_down.clicked.connect(lambda: self._nudge_step(0.0, -0.5))
        grid.addWidget(self.btn_down, 2, 1)
        row.addLayout(grid)
        row.addStretch(1)
        lay.addLayout(row)

        row = QHBoxLayout()
        self.chk_marker = QCheckBox(self.tr("Marker"))
        self.chk_marker.setChecked(True)
        self.chk_marker.toggled.connect(self._refresh_marker)
        row.addWidget(self.chk_marker)
        row.addWidget(QLabel(self.tr("Size:")))
        self.sld_marker = QSlider(Qt.Horizontal)
        self.sld_marker.setRange(2, 30)
        self.sld_marker.setValue(10)
        self.sld_marker.valueChanged.connect(self._refresh_marker)
        row.addWidget(self.sld_marker, 1)
        lay.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Export zoom:")))
        self.cmb_zoom = QComboBox()
        for label, factor in (("1×", 1), ("2×", 2), ("4×", 4)):
            self.cmb_zoom.addItem(label, factor)
        row.addWidget(self.cmb_zoom)
        lay.addLayout(row)
        row = QHBoxLayout()
        self.btn_gif = QPushButton(self.tr("GIF…"))
        self.btn_gif.clicked.connect(lambda: self._export("gif"))
        row.addWidget(self.btn_gif)
        self.btn_video = QPushButton(self.tr("MP4…"))
        self.btn_video.clicked.connect(lambda: self._export("video"))
        row.addWidget(self.btn_video)
        self.btn_png = QPushButton(self.tr("PNG…"))
        self.btn_png.clicked.connect(lambda: self._export("png"))
        row.addWidget(self.btn_png)
        lay.addLayout(row)
        lay.addStretch(1)

    # ------------------------------------------------------- activation

    def set_active(self, flag):
        # Only the visible tab owns the view's frame and its overlays.
        self._active = bool(flag)
        if self._view is None:
            return
        if self._active and self._pair is not None:
            self._view.set_frame_override(self._display_frame)
            self._refresh_marker()
            self._sync_timer()
        else:
            self._timer.stop()
            self._view.set_frame_override(None)     # hand the plate back
            self._drop_marker_items()

    def shutdown(self):
        # Stops timers before the dialog dies (the shiboken trap).
        self._timer.stop()

    # ------------------------------------------------------------- state

    def _on_image_loaded(self):
        # A new plate stalemates the prepared pair; the observer prepares
        # again with one click (the target fields stay filled).
        self._pair = None
        self._obs8 = self._ref8 = None
        self._nudge = [0.0, 0.0]
        self.lbl_nudge.setText("(0.0, 0.0)")
        self._timer.stop()
        if self._view is not None:
            self._view.set_frame_override(None)
            self._drop_marker_items()
        has = self._state.has_image
        self.setEnabled(has)
        self.lbl_status.setText(
            "" if has else self.tr("Load a FITS plate first."))

    def _on_stretch_changed(self):
        # The shared histogram drives the blink: re-stretch both frames.
        if self._pair is not None:
            self._render_frames()

    # ------------------------------------------------------------ prepare

    def _on_manual_toggled(self, checked):
        self.edt_ra.setEnabled(checked)
        self.edt_dec.setEnabled(checked)

    # ------------------------------------------------- host integration

    def prefill(self, name=None, ra=None, dec=None):
        # The host app (a project) lands the blink with the target known:
        # name or manual coordinates filled, ready for one-click Prepare.
        if name is not None:
            self.edt_name.setText(name)
        if ra is not None and dec is not None:
            self.chk_manual.setChecked(True)
            self.edt_ra.setText(f"{ra:.5f}")
            self.edt_dec.setText(f"{dec:+.5f}")

    def _notify_saved(self, paths):
        # Files written while a host watches (a project) get registered
        # there; with no host this is a no-op.
        dlg = self.window()
        notify = getattr(dlg, "notify_saved", None)
        if callable(notify):
            notify(paths, "chart")

    def _manual_coords(self):
        # @return: (ra, dec) in degrees, or None when invalid/unchecked
        if not self.chk_manual.isChecked():
            return None
        try:
            ra = float(self.edt_ra.text().strip().replace(",", "."))
            dec = float(self.edt_dec.text().strip().replace(",", "."))
        except ValueError:
            return None
        if not (0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0):
            return None
        return ra, dec

    def _on_prepare(self):
        # Prepare pair: resolve the target and fetch the aligned PS1-g
        # reference on a worker (network stays off the GUI thread).
        if not self._state.has_image:
            self.lbl_status.setText(self.tr("Load a FITS plate first."))
            return
        name = self.edt_name.text().strip()
        ra = dec = None
        if self.chk_manual.isChecked():
            manual = self._manual_coords()
            if manual is None:
                self.lbl_status.setText(self.tr("Manual coordinates invalid"))
                return
            ra, dec = manual
        elif not name:
            self.lbl_status.setText(self.tr(
                "Type the supernova name or tick 'Manual coordinates'."))
            return
        from .workers import BlinkWorker
        self.btn_prepare.setEnabled(False)
        self.lbl_status.setText(self.tr("Preparing the blink pair…"))
        self._worker = BlinkWorker(self._state.path,
                                   sn_name=name or None, ra=ra, dec=dec)
        self._worker.progress.connect(
            lambda msg: self.lbl_status.setText(msg.get(self._lang, "")))
        self._worker.finished.connect(self._on_pair_ready)
        self._worker.start()

    def _on_pair_ready(self, pair, errors):
        # @args: pair - prepare_pair dict, errors - bilingual messages
        self.btn_prepare.setEnabled(True)
        if errors:
            self.lbl_status.setText("⚠ " + errors.get(self._lang, ""))
            return
        self._pair = pair
        self._nudge = [0.0, 0.0]
        self.lbl_nudge.setText("(0.0, 0.0)")
        self._gain = 1.0
        self.sld_balance.blockSignals(True)
        self.sld_balance.setValue(100)
        self.sld_balance.blockSignals(False)
        h, w = pair["obs"].shape
        self.lbl_status.setText(
            f"{pair['name']} @ ({pair['ra']:.5f}, {pair['dec']:+.5f}) · "
            f"{pair['ref_label']} · {w}×{h} px")
        self._render_frames()
        if self._active:
            self._view.set_frame_override(self._display_frame)
            self._refresh_marker()
            self._sync_timer()

    # ------------------------------------------------------------- frames

    def _unflip(self, arr):
        # Mirrored plates were flipped to match the survey; the editor
        # shows the plate's true orientation, so both frames un-flip.
        # @args: arr - a pair frame (work frame)
        # @return: the frame in the plate's true orientation
        if self._pair is not None and self._pair.get("flipped"):
            return np.ascontiguousarray(arr[:, ::-1])
        return arr

    def _render_frames(self):
        # Recomputes both blink frames with the shared stretch (obs gets
        # the absolute DN black/white of the histogram strip; the PS1
        # reference keeps its own auto percentiles times the balance
        # gain). DATA orientation; the display flip happens on paint.
        if self._pair is None:
            return
        gamma = self._state.gamma
        obs_f = stretch.apply_stretch(self._pair["obs"], self._state.black,
                                      self._state.white, gamma)
        ref_f = stretch.apply_gain(
            stretch.apply_stretch(self._pair["ref"],
                                  *stretch.auto_limits(self._pair["ref"]),
                                  gamma),
            self._gain)
        if self._state.inverted:
            obs_f = stretch.invert(obs_f)
            ref_f = stretch.invert(ref_f)
        self._obs8 = stretch.to_uint8(obs_f)
        self._ref8 = self._shift_ref(stretch.to_uint8(ref_f))
        if self._view is not None and self._active:
            self._view.refresh_frame()

    def _shift_ref(self, ref8):
        # Applies the observer's nudge to the reference frame (integer and
        # fractional shifts alike, via the affine PIL path the legacy
        # dialog uses). DATA orientation, y up.
        # @args: ref8 - the stretched reference, uint8
        # @return: the shifted frame
        dx, dy = self._nudge
        if dx == 0.0 and dy == 0.0:
            return ref8
        from PIL import Image
        im = Image.fromarray(ref8, mode="L")
        im = im.transform(im.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy),
                          fillcolor=0)
        return np.asarray(im)

    def _display_frame(self):
        # The frame the view paints right now, in SCREEN orientation:
        # obs and alternate ref when blinking, the blend when fading.
        # @return: uint8 array or None
        if self._obs8 is None:
            return None
        if self.rdo_fade.isChecked():
            a = self.sld_fade.value() / 100.0
            frame = (1.0 - a) * self._unflip(self._obs8) \
                + a * self._unflip(self._ref8)
            return np.ascontiguousarray(
                np.flipud(frame.astype(np.uint8)))
        current = self._obs8 if self._phase == 0 else self._ref8
        return np.ascontiguousarray(np.flipud(self._unflip(current)))

    # ------------------------------------------------------ blink timer

    def _sync_timer(self):
        # Runs the swap timer only when blinking live on stage.
        if self._active and self._pair is not None \
                and self.chk_live.isChecked() and self.rdo_blink.isChecked():
            self._timer.start(self.spn_interval.value())
        else:
            self._timer.stop()

    def _tick(self):
        # One blink phase: obs <-> ref, immediate repaint.
        self._phase = 1 - self._phase
        if self._view is not None:
            self._view.refresh_frame()

    def _on_live_toggled(self, _checked):
        self._sync_timer()

    def _on_interval_changed(self, _value):
        if self._timer.isActive():
            self._timer.start(self.spn_interval.value())

    def _on_mode_changed(self, _checked):
        # Blink swaps frames on the timer; fade is a static blend.
        self.sld_fade.setEnabled(self.rdo_fade.isChecked())
        self._sync_timer()
        if self._view is not None and self._active:
            self._view.refresh_frame()

    def _on_balance_changed(self, ticks):
        self._gain = ticks / 100.0
        self._render_frames()

    def _on_balance_auto(self):
        # Gain that matches the reference's sky background to the plate's.
        if self._pair is None:
            return
        obs_f = stretch.apply_stretch(self._pair["obs"], self._state.black,
                                      self._state.white, self._state.gamma)
        ref_f = stretch.apply_stretch(self._pair["ref"],
                                      *stretch.auto_limits(self._pair["ref"]),
                                      self._state.gamma)
        gain = stretch.auto_gain(ref_f, obs_f)
        self.sld_balance.setValue(round(gain * 100))   # drives the render

    def _nudge_step(self, dx, dy):
        # One fine-alignment step toward the pressed arrow.
        # @args: dx, dy - the half-pixel step in work-frame px (y up)
        if self._pair is None:
            return
        self._nudge[0] += dx
        self._nudge[1] += dy
        self.lbl_nudge.setText(
            f"({self._nudge[0]:+.1f}, {self._nudge[1]:+.1f})")
        self._render_frames()

    # ------------------------------------------------------------- marker

    def _sn_scene(self):
        # @return: the SN in scene (plate px) coordinates, mapped through
        #          the plate's own WCS from the resolved sky position;
        #          None when there is no pair or no WCS
        if self._pair is None or self._state.wcs is None:
            return None
        try:
            col, row = self._state.wcs.sky_to_pixel(self._pair["ra"],
                                                    self._pair["dec"])
            return self._state.data_to_scene(col, row)
        except Exception:
            return None

    def _refresh_marker(self):
        # Rebuilds the SN marker (circle + ticks + name), screen-sized
        # like the annotate one.
        self._drop_marker_items()
        if not self._active or self._view is None \
                or not self.chk_marker.isChecked():
            return
        pos = self._sn_scene()
        if pos is None:
            return
        x, y = pos
        scale = max(self._view.current_factor(), 1e-3)
        r = self.sld_marker.value() / scale
        pen = QPen(QColor(_MARKER_COLOR))
        pen.setWidthF(2.0)
        pen.setCosmetic(True)
        circle = QGraphicsEllipseItem(x - r, y - r, 2 * r, 2 * r)
        circle.setPen(pen)
        self._items.append(self._view.add_overlay(circle))
        for x0, y0, x1, y1 in ((x - 1.6 * r, y, x - 0.5 * r, y),
                               (x + 0.5 * r, y, x + 1.6 * r, y),
                               (x, y - 1.6 * r, x, y - 0.5 * r),
                               (x, y + 0.5 * r, x, y + 1.6 * r)):
            tick = QGraphicsLineItem(x0, y0, x1, y1)
            tick.setPen(pen)
            self._items.append(self._view.add_overlay(tick))
        name = self._pair.get("name") or ""
        if name:
            label = QGraphicsSimpleTextItem(name)
            f = QFont()
            f.setPointSizeF(max(0.5, 11.0 / scale))
            label.setFont(f)
            label.setBrush(QBrush(QColor("#ffffff")))
            label.setPos(x - label.boundingRect().width() / 2,
                         y + 1.9 * r)
            label.setZValue(60)
            self._items.append(self._view.add_overlay(label))

    def _layout_marker(self):
        # Zoom moved: rebuild the screen-sized marker (cheap, few items).
        if self._active and self._pair is not None:
            self._refresh_marker()

    def _drop_marker_items(self):
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

    def _export_sn_xy(self):
        # The SN in the EXPORT frame (data orientation of the un-flipped
        # work frames): the pair's sn_xy with the flip undone.
        sn = self._pair.get("sn_xy") if self._pair else None
        if sn is None:
            return None
        if self._pair.get("flipped"):
            w = self._pair["obs"].shape[1]
            return (w - 1 - sn[0], sn[1])
        return sn

    def _export(self, kind):
        # GIF / MP4 / side-by-side PNG of the pair, off the GUI thread.
        if self._pair is None or self._obs8 is None:
            return
        name = self._pair["name"]
        defaults = {"gif": (f"{name}_blink.gif", "GIF (*.gif)"),
                    "video": (f"{name}_blink.mp4", "MP4 video (*.mp4)"),
                    "png": (f"{name}_before_after.png", "PNG (*.png)")}
        fname, filt = defaults[kind]
        out, _sel = QFileDialog.getSaveFileName(
            self, self.tr("Export {0}").format(kind.upper()),
            str(Path(self._state.path).parent / fname), filt)
        if not out:
            return
        from .workers import BlinkExportWorker
        sn = self._export_sn_xy() if self.chk_marker.isChecked() else None
        effect = "blink" if self.rdo_blink.isChecked() else "fade"
        from ..config import config
        self.lbl_status.setText(self.tr("Rendering…"))
        w = BlinkExportWorker(
            kind, self._ref8, self._obs8, sn, out, effect=effect,
            name=name, ref_label=self._pair["ref_label"], lang=self._lang,
            observatory=config.get("observatory_name", ""),
            zoom=self.cmb_zoom.currentData(),
            marker_scale=self.sld_marker.value() / 10.0,
            interval_ms=self.spn_interval.value())
        w.finished.connect(self._on_exported)
        self._export_workers.append(w)
        w.start()

    def _on_exported(self, out, err):
        # @args: out - written path ("" on failure), err - error text
        if out:
            self.lbl_status.setText(self.tr("Written to {0}").format(out))
            self._notify_saved([out])
        else:
            self.lbl_status.setText(
                self.tr("Export failed: {0}").format(err))
        # prune finished workers (they hold big frames)
        self._export_workers = [w for w in self._export_workers
                                if w.isRunning()]
