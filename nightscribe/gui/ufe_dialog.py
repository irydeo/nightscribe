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
        self.resize(1280, 860)
        self.setMinimumSize(900, 600)
        self.state.image_loaded.connect(self._on_image_loaded)
        self.state.stretch_changed.connect(self._sync_invert_button)

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
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._on_export_png)
        bar.addWidget(self.btn_export)
        bar.addSpacing(16)
        bar.addWidget(QLabel(self.tr("Zoom:")))
        self.btn_zoom = {}
        for factor, label in _ZOOM_PRESETS:
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda _checked=False, f=factor: self._on_zoom_preset(f))
            bar.addWidget(btn)
            self.btn_zoom[label] = btn
        bar.addStretch(1)
        return bar

    def _add_placeholder_tabs(self):
        # One placeholder per legacy feature so the grid never changes
        # shape; phases D/E/F swap each for the real tab widget.
        for title, phase in ((self.tr("Blink"), "E"),
                             (self.tr("Compare"), "F"),
                             (self.tr("Annotate"), "D")):
            page = QWidget()
            v = QVBoxLayout(page)
            lbl = QLabel(self.tr("Arrives in phase {0}").format(phase))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            v.addWidget(lbl)
            self.tabs.addTab(page, title)

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

    def _on_image_loaded(self):
        # A fresh plate resets the inversion (state already did its half).
        self._sync_invert_button()
        self.btn_invert.setEnabled(self.state.has_image)
        self.btn_export.setEnabled(self.state.has_image)

    def _sync_invert_button(self):
        # The top-bar Invert mirrors state.inverted; the histogram strip
        # carries its own Invert and both follow the state, never each
        # other (the toggled handler no-ops when already in sync).
        self.btn_invert.blockSignals(True)
        self.btn_invert.setChecked(self.state.inverted)
        self.btn_invert.blockSignals(False)
