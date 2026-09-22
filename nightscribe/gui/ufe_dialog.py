############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor dialog (ADR-044)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Unified FITS Editor dialog (ADR-044): the single place where
NightScribe shows and works FITS images. The image owns most of the
window; the right column carries one tab per feature (Blink, Compare,
Annotate; phase A ships them as placeholders) and the bottom strip will
hold the visual histogram (phase B). The top bar carries the common
actions: load, invert, PNG export of the visible scene and zoom presets.

Extensibility rule: a new feature is a new tab. The tab widget receives
(state, lang) and subscribes to the state's signals; the dialog only
learns about it through add_feature_tab(). The legacy blink / annotate /
sequence-chart dialogs keep living untouched.
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QSplitter,
                               QTabWidget, QVBoxLayout, QWidget)

from ..core import fits_io
from .ufe_state import UfeImageState
from .widgets.histogram_widget import HistogramWidget
from .widgets.ufe_image_view import UfeImageView

logger = logging.getLogger("nightscribe.gui.ufe_dialog")

_ZOOM_PRESETS = ((None, "Fit"), (0.5, "50"), (1.0, "100"),
                 (2.0, "200"), (4.0, "400"))


class UfeDialog(QDialog):
    # @args: lang - "es" | "en" (feature tabs receive it), parent - widget

    def __init__(self, lang="es", parent=None):
        super().__init__(parent)
        self._lang = lang
        self._last_dir = ""
        self.state = UfeImageState(self)
        self.view = UfeImageView(self.state)
        self.setWindowTitle(self.tr("FITS editor"))
        self._build_ui()
        self._build_shortcuts()
        self.resize(1280, 860)
        self.setMinimumSize(900, 600)
        self.state.image_loaded.connect(self._on_image_loaded)
        self.state.stretch_changed.connect(self._sync_invert_button)
        self.view.zoom_changed.connect(self._on_zoom_changed)

    # ------------------------------------------------------------- layout

    def _build_ui(self):
        # Top bar + splitter (image | feature tabs) + histogram strip.
        lay = QVBoxLayout(self)
        lay.addLayout(self._build_topbar())
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.view)
        self.tabs = QTabWidget()
        self.splitter.addWidget(self.tabs)
        self.splitter.setStretchFactor(0, 1)     # the image dominates
        self.splitter.setStretchFactor(1, 0)
        self.tabs.setMinimumWidth(280)
        lay.addWidget(self.splitter, 1)
        self.histogram = HistogramWidget(self.state)
        lay.addWidget(self.histogram)
        self._add_placeholder_tabs()

    def _build_topbar(self):
        # @return: the common-actions row (load / invert / export / zoom)
        bar = QHBoxLayout()
        self.btn_load = QPushButton(self.tr("Load FITS…"))
        self.btn_load.setToolTip(self.tr("Open a FITS image (Ctrl+O)"))
        self.btn_load.clicked.connect(self._on_load)
        bar.addWidget(self.btn_load)
        self.btn_invert = QPushButton(self.tr("Invert"))
        self.btn_invert.setCheckable(True)
        self.btn_invert.setToolTip(self.tr(
            "Swap black for white: faint objects pop against the sky"))
        self.btn_invert.toggled.connect(self._on_invert_toggled)
        self.btn_invert.setEnabled(False)
        bar.addWidget(self.btn_invert)
        self.btn_export = QPushButton(self.tr("Export PNG…"))
        self.btn_export.setToolTip(self.tr(
            "Save the visible scene as a PNG (Ctrl+E)"))
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._on_export_png)
        bar.addWidget(self.btn_export)
        bar.addSpacing(16)
        bar.addWidget(QLabel(self.tr("Zoom:")))
        self.btn_zoom = {}
        for factor, label in _ZOOM_PRESETS:
            btn = QPushButton(label)
            btn.setToolTip(self.tr("Fit the plate to the window")
                           if factor is None else
                           self.tr("Zoom {0} % (1:1 at 100)").format(
                               int(factor * 100)))
            btn.clicked.connect(
                lambda _checked=False, f=factor: self._on_zoom_preset(f))
            bar.addWidget(btn)
            self.btn_zoom[label] = btn
        self.lbl_zoom = QLabel("–")
        self.lbl_zoom.setMinimumWidth(44)
        self.lbl_zoom.setToolTip(self.tr(
            "Current zoom: 100 % is one plate pixel per screen pixel"))
        bar.addWidget(self.lbl_zoom)
        bar.addStretch(1)
        return bar

    def _add_placeholder_tabs(self):
        # One placeholder per legacy feature not yet migrated (phases E/F
        # swap theirs in); the Annotate tab is real since phase D.
        for title, phase in ((self.tr("Blink"), "E"),
                             (self.tr("Compare"), "F")):
            page = QWidget()
            v = QVBoxLayout(page)
            lbl = QLabel(self.tr("Arrives in phase {0}").format(phase))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            v.addWidget(lbl)
            self.tabs.addTab(page, title)
        from .ufe_annotate_tab import UfeAnnotateTab
        self.tab_annotate = UfeAnnotateTab(self.state, self._lang,
                                           view=self.view)
        self.tabs.addTab(self.tab_annotate, self.tr("Annotate"))
        # only the current tab owns the view's clicks and overlays
        self.tabs.currentChanged.connect(self._on_feature_tab_changed)
        self._on_feature_tab_changed(self.tabs.currentIndex())

    def _on_feature_tab_changed(self, idx):
        # Hands the stage to the freshly selected tab (set_active) and
        # takes it from the others; placeholders carry no method.
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            setter = getattr(w, "set_active", None)
            if callable(setter):
                setter(i == idx)

    # -------------------------------------------------------- extension

    def add_feature_tab(self, title, widget):
        # The whole extension API: a new feature is a new tab whose widget
        # got (state, lang) at construction and subscribes to the state.
        # @args: title - tab label, widget - the feature's controls
        # @return: the index the tab landed on
        return self.tabs.addTab(widget, title)

    # ----------------------------------------------------------- actions

    def _on_load(self):
        # Load FITS… → file picker → state.load; errors surface in a box.
        path, _sel = QFileDialog.getOpenFileName(
            self, self.tr("Open FITS image"), self._last_dir,
            self.tr("FITS images (*.fits *.fit *.fts *.fz);;"
                    "All files (*)"))
        if not path:
            return
        try:
            self.state.load(path)
        except fits_io.FitsError as err:
            logger.warning("FITS load failed: %s", err)
            QMessageBox.warning(
                self, self.tr("FITS editor"),
                self.tr("Could not read the FITS file:") + f"\n{err}")
            return
        self._last_dir = str(Path(path).parent)

    def _on_invert_toggled(self, checked):
        # The button mirrors state.inverted (the state is the source of
        # truth; loading a plate resets both).
        if self.state.has_image and checked != self.state.inverted:
            self.state.toggle_invert()

    def _on_export_png(self):
        # Export PNG… → saves whatever the view is showing right now.
        if not self.state.has_image:
            return
        stem = Path(self.state.path).stem if self.state.path else "ufe"
        path, _sel = QFileDialog.getSaveFileName(
            self, self.tr("Export PNG"),
            str(Path(self._last_dir) / f"{stem}_ufe.png")
            if self._last_dir else f"{stem}_ufe.png",
            "PNG (*.png)")
        if not path:
            return
        out = self.view.export_png(path)
        logger.info("UFE PNG export: %s", out)

    def _on_zoom_preset(self, factor):
        # @args: factor - None for Fit, else the absolute scale (0.5..4)
        if not self.state.has_image:
            return
        if factor is None:
            self.view.fit_to_scene()
        else:
            self.view.fit_to_factor(factor)

    def _on_zoom_changed(self, factor):
        # The view reports the absolute scale after any zoom move (wheel,
        # presets, keys, double-click fit); the top bar mirrors it.
        # @args: factor - absolute scale, 1.0 = 100 %
        self.lbl_zoom.setText(f"{factor * 100:.0f} %")

    # --------------------------------------------------------- keyboard

    def _build_shortcuts(self):
        # Full keyboard control (ADR-044 phase C): F fit, 1 back to 1:1,
        # +/- zoom in wheel steps, arrows pan a quarter viewport, Ctrl+O
        # loads, Ctrl+E exports the visible scene. WidgetWithChildren so
        # the keys work wherever the focus sits inside the dialog.
        ctx = Qt.WidgetWithChildrenShortcut
        for key, fn in (
                (Qt.Key_F, lambda: self._key(self.view.fit_to_scene)),
                (Qt.Key_1, lambda: self._key(
                    lambda: self.view.fit_to_factor(1.0))),
                (Qt.Key_Plus, lambda: self._key(self.view.zoom_in)),
                (Qt.Key_Equal, lambda: self._key(self.view.zoom_in)),
                (Qt.Key_Minus, lambda: self._key(self.view.zoom_out)),
                (Qt.Key_Left, lambda: self._key(
                    lambda: self._pan_step(-1, 0))),
                (Qt.Key_Right, lambda: self._key(
                    lambda: self._pan_step(1, 0))),
                (Qt.Key_Up, lambda: self._key(
                    lambda: self._pan_step(0, -1))),
                (Qt.Key_Down, lambda: self._key(
                    lambda: self._pan_step(0, 1)))):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(ctx)
            sc.activated.connect(fn)
        for seq, fn in (("Ctrl+O", self._on_load),
                        ("Ctrl+E", self._on_export_png)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(ctx)
            sc.activated.connect(fn)

    def _key(self, fn):
        # Zoom/pan keys no-op on the empty state (never zoom the hint).
        if self.state.has_image:
            fn()

    def _pan_step(self, dx, dy):
        # Arrow-key pan: a quarter of the viewport per press, so the step
        # feels the same at any zoom level.
        # @args: dx, dy - step direction in {-1, 0, 1}
        hbar = self.view.horizontalScrollBar()
        vbar = self.view.verticalScrollBar()
        hbar.setValue(hbar.value()
                      + dx * max(1, self.view.viewport().width() // 4))
        vbar.setValue(vbar.value()
                      + dy * max(1, self.view.viewport().height() // 4))

    def _on_image_loaded(self):
        # A fresh plate resets the inversion (state already did its half)
        # and puts its file name in the title bar.
        self._sync_invert_button()
        self.btn_invert.setEnabled(self.state.has_image)
        self.btn_export.setEnabled(self.state.has_image)
        if self.state.has_image:
            self.setWindowTitle(
                self.tr("FITS editor") + " · " + Path(self.state.path).name)
        else:
            self.setWindowTitle(self.tr("FITS editor"))

    def _sync_invert_button(self):
        # The top-bar Invert mirrors state.inverted; the histogram strip
        # carries its own Invert and both follow the state, never each
        # other (the toggled handler no-ops when already in sync).
        self.btn_invert.blockSignals(True)
        self.btn_invert.setChecked(self.state.inverted)
        self.btn_invert.blockSignals(False)
