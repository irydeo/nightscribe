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
Annotate) and the bottom strip is the visual histogram. The top bar
carries the common actions: load, PNG export of the visible scene, the
north arrow / scale bar HUD toggles, astrometric solving and zoom
presets. (Inversion lives in the histogram strip, with the other
stretch controls.)

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
        self._solve_worker = None   # UfeSolveWorker while a solve runs
        self._save_hook = None      # fn(paths, kind, payload) when the
                                    # editor was opened from a project:
                                    # files written get registered there
        self._point_hook = None     # fn(payload: dict) when the editor
                                    # was opened from a project: the
                                    # Measure tab registers a calibrated
                                    # point there (no files involved)
        self._object = None         # {"name","ra","dec","mag"} when the
                                    # editor was opened from a project
        self.state = UfeImageState(self)
        self.view = UfeImageView(self.state)
        self.setWindowTitle(self.tr("NightScribe Image Workbench"))
        self._build_ui()
        self._build_shortcuts()
        self.resize(1440, 960)
        self.setMinimumSize(1000, 640)
        self.state.image_loaded.connect(self._on_image_loaded)
        self.state.wcs_changed.connect(self._sync_wcs_buttons)
        self.view.zoom_changed.connect(self._on_zoom_changed)

    # ------------------------------------------------------------- layout

    def _build_ui(self):
        # Top bar + object line + splitter (image | feature tabs) +
        # histogram strip.
        lay = QVBoxLayout(self)
        lay.addLayout(self._build_topbar())
        self.lbl_object = QLabel("")
        self.lbl_object.setVisible(False)
        self.lbl_object.setToolTip(self.tr(
            "The object this editor was opened from"))
        from . import theme
        self.lbl_object.setStyleSheet(
            f"color: {theme.C_TEXT_DIM}; padding: 0 4px;")
        lay.addWidget(self.lbl_object)
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
        self._build_feature_tabs()

    def _build_topbar(self):
        # @return: the common-actions row (load / export / zoom)
        bar = QHBoxLayout()
        self.btn_load = QPushButton(self.tr("Load FITS…"))
        self.btn_load.setToolTip(self.tr("Open a FITS image (Ctrl+O)"))
        self.btn_load.clicked.connect(self._on_load)
        bar.addWidget(self.btn_load)
        self.btn_export = QPushButton(self.tr("Export PNG…"))
        self.btn_export.setToolTip(self.tr(
            "Save the visible scene as a PNG (Ctrl+E)"))
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self._on_export_png)
        bar.addWidget(self.btn_export)
        bar.addSpacing(16)
        self.btn_north = QPushButton(self.tr("N"))
        self.btn_north.setCheckable(True)
        self.btn_north.setChecked(True)
        self.btn_north.setToolTip(self.tr("North arrow (needs a WCS)"))
        self.btn_north.setEnabled(False)
        self.btn_north.toggled.connect(
            lambda checked: self.view.set_hud(north=checked))
        bar.addWidget(self.btn_north)
        self.btn_scale = QPushButton(self.tr("Scale"))
        self.btn_scale.setCheckable(True)
        self.btn_scale.setChecked(True)
        self.btn_scale.setToolTip(self.tr("Scale bar (needs a WCS)"))
        self.btn_scale.setEnabled(False)
        self.btn_scale.toggled.connect(
            lambda checked: self.view.set_hud(scale=checked))
        bar.addWidget(self.btn_scale)
        self.btn_annot = QPushButton(self.tr("A"))
        self.btn_annot.setCheckable(True)
        self.btn_annot.setChecked(True)
        self.btn_annot.setToolTip(self.tr(
            "Saved annotations (the marks stored on this plate)"))
        self.btn_annot.toggled.connect(
            lambda checked: self.view.set_annotations_visible(checked))
        bar.addWidget(self.btn_annot)
        self.btn_solve = QPushButton(self.tr("Solve astrometry…"))
        self.btn_solve.setToolTip(self.tr(
            "Blind-solve the plate with Astrometry.net (the file on disk "
            "is never modified)"))
        self.btn_solve.setEnabled(False)
        self.btn_solve.clicked.connect(self._on_solve)
        bar.addWidget(self.btn_solve)
        bar.addSpacing(16)
        bar.addWidget(QLabel(self.tr("Zoom:")))
        self.btn_zoom = {}
        for factor, label in _ZOOM_PRESETS:
            btn = QPushButton(self.tr("Fit") if factor is None else label)
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

    def _build_feature_tabs(self):
        # The feature tabs are real now (phases D, E, F, G2). Compare and
        # Measure share the Photometry tab (ADR-044 rev, 2026-09-24); the
        # tab_compare / tab_measure aliases keep the legacy deep links,
        # prefills and tests working.
        from .ufe_blink_tab import UfeBlinkTab
        self.tab_blink = UfeBlinkTab(self.state, self._lang,
                                     view=self.view)
        self.tabs.addTab(self.tab_blink, self.tr("Blink"))
        from .ufe_photometry_tab import UfePhotometryTab
        self.tab_photometry = UfePhotometryTab(
            self.state, self._lang, view=self.view)
        self.tabs.addTab(self.tab_photometry, self.tr("Photometry"))
        self.tab_compare = self.tab_photometry.tab_compare
        self.tab_measure = self.tab_photometry.tab_measure
        from .ufe_annotate_tab import UfeAnnotateTab
        self.tab_annotate = UfeAnnotateTab(self.state, self._lang,
                                           view=self.view)
        self.tabs.addTab(self.tab_annotate, self.tr("Annotate"))
        # only the current tab owns the view's clicks and overlays
        self.tabs.currentChanged.connect(self._on_feature_tab_changed)
        self._on_feature_tab_changed(self.tabs.currentIndex())

    def _on_feature_tab_changed(self, idx):
        # Hands the stage to the freshly selected tab (set_active) and
        # takes it from the others. The Photometry tab routes the handoff
        # to its Sequence / Measure section itself (the sequence's
        # overlays survive a section switch but not a full leave).
        # The pick cursor (crosshair + snapping reticle) follows the
        # stage from here: tabs declare `pick_clicks = True`.
        incoming = self.tabs.widget(idx)
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            setter = getattr(w, "set_active", None)
            if callable(setter):
                setter(i == idx)
        self.view.set_pick_cursor(
            bool(getattr(incoming, "pick_clicks", False)))

    def closeEvent(self, event):
        # The blink timer must not fire into a closing dialog.
        self.tab_blink.shutdown()
        super().closeEvent(event)

    # -------------------------------------------------------- extension

    def add_feature_tab(self, title, widget):
        # The whole extension API: a new feature is a new tab whose widget
        # got (state, lang) at construction and subscribes to the state.
        # @args: title - tab label, widget - the feature's controls
        # @return: the index the tab landed on
        return self.tabs.addTab(widget, title)

    # ---------------------------------------------- host-app integration

    def open_plate(self, path):
        # Loads a FITS by path (the host app's entry point; same error
        # box as the file picker).
        # @args: path - FITS file path
        # @return: True when the plate loaded
        try:
            self.state.load(path)
        except fits_io.FitsError as err:
            logger.warning("FITS load failed: %s", err)
            QMessageBox.warning(
                self, self.tr("NightScribe Image Workbench"),
                self.tr("Could not read the FITS file:") + f"\n{err}")
            return False
        self._last_dir = str(Path(path).parent)
        return True

    def show_tab(self, tab):
        # Brings one feature tab to the front (Blink / Photometry /
        # Annotate) so the host can deep-link a workflow into the
        # editor. The Photometry sections still accept the legacy names:
        # tab_compare / tab_measure by widget or "compare" / "measure"
        # by name, which also pick the right section on the way in.
        # @args: tab - a top-level tab widget, an inner Photometry
        #        section widget, or "compare" / "measure"
        if tab in (self.tab_compare, self.tab_measure) \
                or tab in ("compare", "measure"):
            self.tab_photometry.set_mode(
                "measure" if tab in (self.tab_measure, "measure")
                else "sequence")
            self.tabs.setCurrentWidget(self.tab_photometry)
            return
        self.tabs.setCurrentWidget(tab)

    def set_save_hook(self, fn):
        # @args: fn - callable(paths: list[str], kind: str, payload: dict)
        #        or None. The tabs call it after writing files, so a host
        #        that opened the editor from a project can register the
        #        outputs there. Cleared on every open path that does not
        #        set it (the dialog instance is shared and persistent).
        self._save_hook = fn

    def notify_saved(self, paths, kind, payload=None):
        # The tabs report written files here; without a hook it is a no-op.
        # @args: paths - files just written, kind - "fits" | "chart" |
        #        "sequence", payload - extra context for the host
        if self._save_hook is not None and paths:
            try:
                self._save_hook([str(p) for p in paths], kind,
                                payload or {})
            except Exception as err:      # the write already happened;
                logger.warning("save hook failed: %s", err)  # never break it

    def set_point_hook(self, fn):
        # @args: fn - callable(payload: dict) or None. When the editor was
        #        opened from a project (Main window) it sends a calibrated
        #        measurement ({"mjd", "filter", "mag", "err", ...}) to the
        #        host for registration. Cleared on every open path that
        #        does not set it, like the file save hook. The Measure
        #        tab shows its «Save in the project» button only then.
        self._point_hook = fn
        tab = getattr(self, "tab_measure", None)
        if tab is not None:
            tab.set_project_attached(fn is not None)

    def point_hook(self):
        # @return: the point hook callable, or None when the editor was
        #          opened ad-hoc (Measure tab hides its save button)
        return self._point_hook

    def notify_point(self, payload):
        # The Measure tab reports a calibrated point here; without a hook
        # it is a no-op (the button is hidden anyway).
        # @args: payload - {"mjd", "filter", "mag", "err"} plus context
        if self._point_hook is None:
            return False
        try:
            self._point_hook(payload or {})
        except Exception as err:      # the measurement already happened;
            logger.warning("point hook failed: %s", err)  # never break it
            return False
        return True

    # --------------------------------------------------- the object

    def set_object(self, obj):
        # The object the editor was opened from (a project): everything
        # that applies is shown and prefilled. It survives loading another
        # plate; only an ad-hoc open (the Tools menu) clears it.
        # @args: obj - {"name", "ra", "dec", "mag"} (all optional), or
        #        None to drop the object context (tabs keep their fields)
        self._object = obj or None
        self._update_object_line()
        self._update_title()
        if not self._object:
            return
        name = self._object.get("name")
        ra, dec = self._object.get("ra"), self._object.get("dec")
        mag = self._object.get("mag")
        self.tab_blink.prefill(name=name, ra=ra, dec=dec)
        self.tab_compare.prefill(target=name, mag=mag, ra=ra, dec=dec)
        self.tab_annotate.prefill(label=name, ra=ra, dec=dec)
        self.tab_measure.prefill(bv=self._object.get("bv"))

    def object(self):
        # @return: the current object dict, or None
        return self._object

    def _update_object_line(self):
        # The thin line under the top bar: name, RA/Dec, magnitude; only
        # visible while an object is attached.
        if not self._object:
            self.lbl_object.setVisible(False)
            return
        parts = []
        if self._object.get("name"):
            parts.append(self._object["name"])
        ra, dec = self._object.get("ra"), self._object.get("dec")
        if ra is not None and dec is not None:
            from ..core import coords
            try:
                parts.append(f"RA {coords.ra_deg_to_hms(float(ra))} · "
                             f"Dec {coords.dec_deg_to_dms(float(dec))}")
            except (TypeError, ValueError):
                pass
        if self._object.get("mag") is not None:
            try:
                parts.append(self.tr("mag {0:.2f}").format(
                    float(self._object["mag"])))
            except (TypeError, ValueError):
                parts.append(f"mag {self._object['mag']}")
        self.lbl_object.setText("   ·   ".join(parts))
        self.lbl_object.setVisible(bool(parts))

    def _update_title(self):
        # Brand · object (when attached) · plate file name (when loaded).
        parts = [self.tr("NightScribe Image Workbench")]
        if self._object and self._object.get("name"):
            parts.append(self._object["name"])
        if self.state.has_image:
            parts.append(Path(self.state.path).name)
        self.setWindowTitle(" · ".join(parts))

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
                self, self.tr("NightScribe Image Workbench"),
                self.tr("Could not read the FITS file:") + f"\n{err}")
            return
        self._last_dir = str(Path(path).parent)

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
        # ADR-045: the scene export registers like every other tab's
        # files (no-op when no project is watching)
        self.notify_saved([out], "chart")

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
        # A fresh plate re-arms the top-bar actions and puts its file
        # name in the title bar (the histogram strip re-arms itself).
        self.btn_export.setEnabled(self.state.has_image)
        self.btn_solve.setEnabled(self.state.has_image)
        self._sync_wcs_buttons()
        self._update_title()

    def _sync_wcs_buttons(self):
        # North arrow / scale bar need a WCS (present at load or after a
        # solve); the state reports both moments.
        has_wcs = self.state.has_image and self.state.wcs is not None
        self.btn_north.setEnabled(has_wcs)
        self.btn_scale.setEnabled(has_wcs)

    # --------------------------------------------------------- solving

    def _on_solve(self):
        # Solve astrometry…: blind-solve the current plate with
        # Astrometry.net on a worker (network off the GUI thread). The
        # solution lands in memory only; the file on disk stays untouched.
        if not self.state.has_image:
            return
        from ..config import config
        if not (config.get("astrometry_key") or "").strip():
            QMessageBox.information(
                self, self.tr("NightScribe Image Workbench"),
                self.tr("Set your Astrometry.net API key in Settings to "
                        "solve plates automatically, or solve them with "
                        "ASTAP, NINA, Ekos or PixInsight and save them "
                        "again."))
            return
        from .workers import UfeSolveWorker
        self._solve_worker = UfeSolveWorker(Path(self.state.path))
        self._solve_worker.progress.connect(self._on_solve_stage)
        self._solve_worker.finished.connect(self._on_solved)
        self.btn_solve.setEnabled(False)
        self._on_solve_stage("login")
        self._solve_worker.start()

    def _on_solve_stage(self, stage):
        # @args: stage - the worker's stage text, mirrored on the button
        self.btn_solve.setText(self.tr("Solving: {0}…").format(stage))

    def _on_solved(self, cards):
        # @args: cards - solved WCS cards, or {} when the solve failed
        self.btn_solve.setText(self.tr("Solve astrometry…"))
        self.btn_solve.setEnabled(self.state.has_image)
        self._solve_worker = None
        if not cards:
            QMessageBox.warning(
                self, self.tr("NightScribe Image Workbench"),
                self.tr("Astrometry.net could not solve the plate (or is "
                        "offline). Check the key in Settings or solve it "
                        "with ASTAP/NINA/Ekos/PixInsight."))
            return
        if self.state.set_wcs_cards(cards):
            logger.info("UFE: astrometry solved for %s", self.state.path)
        else:
            QMessageBox.warning(
                self, self.tr("NightScribe Image Workbench"),
                self.tr("The Astrometry.net solution is not usable "
                        "(non-TAN WCS)."))
