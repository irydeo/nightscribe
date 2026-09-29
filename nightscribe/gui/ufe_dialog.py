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

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, \
    QProgressDialog, QVBoxLayout, QWidget

from ..core import fits_io
from .ufe_state import UfeImageState
from .ui_loader import adopt_ui, drop_in, load_ui
from .widgets.histogram_widget import HistogramWidget
from .widgets.ufe_image_view import UfeImageView

logger = logging.getLogger("nightscribe.gui.ufe_dialog")

_ZOOM_PRESETS = ((None, "Fit"), (0.5, "50"), (1.0, "100"),
                 (2.0, "200"), (4.0, "400"))

# ADR-044 rev (2026-09-24): the top-bar button table for the bar style
# (icons-only vs icon + text). `base` is the asset stem in assets/;
# toggles flip the _on / _off glyphs with their checked state. `icon_only`
# means the label can go away in icon mode; Solve keeps its label in both
# modes because the action is long and the glyph only hints at it.
_BAR_BUTTONS = {
    "btn_load": {"base": "ufe_load", "icon_only": True},
    "btn_export": {"base": "ufe_export", "icon_only": True},
    "btn_north": {"base": "ufe_north", "icon_only": True, "toggle": True},
    "btn_scale": {"base": "ufe_scale", "icon_only": True, "toggle": True},
    "btn_annot": {"base": "ufe_annot", "icon_only": True, "toggle": True},
    "btn_boxes": {"base": "ufe_boxes", "icon_only": True, "toggle": True},
    "btn_mark": {"base": "ufe_mark", "icon_only": True, "toggle": True},
    "btn_solve": {"base": "ufe_solve", "icon_only": False},
}
_ZOOM_ICONS = {"Fit": "ufe_zoom_fit", "50": "ufe_zoom_50",
               "100": "ufe_zoom_100", "200": "ufe_zoom_200",
               "400": "ufe_zoom_400"}


class UfeDialog(QDialog):
    # @args: lang - "es" | "en" (feature tabs receive it), parent - widget

    def __init__(self, lang="es", parent=None):
        super().__init__(parent)
        self._lang = lang
        self._last_dir = ""
        self._solve_worker = None   # UfeSolveWorker while a solve runs
        self._solve_wait = None     # the busy dialog shown while it runs
        self._save_hook = None      # fn(paths, kind, payload) when the
                                    # editor was opened from a project:
                                    # files written get registered there
        self._point_hook = None     # fn(payload: dict) when the editor
                                    # was opened from a project: the
                                    # Measure tab registers a calibrated
                                    # point there (no files involved)
        self._reset_state_hook = None   # fn() ADR-047: clear the open
                                        # plate's saved state block
        self._reset_points_hook = None  # fn() ADR-047: drop the plate's
                                        # measured points (confirmed in the
                                        # tab first)
        self._object = None         # {"name","ra","dec","mag"} when the
                                    # editor was opened from a project
        # series hooks (series plan, phase 5): the visit context (frames),
        # the batch writer (one run) and the per-run undo. All None on an
        # ad-hoc open, so the Measure tab hides its series block (D8).
        self._series_hook = None
        self._points_hook = None
        self._run_undo_hook = None
        self._exoclock_hook = None
        # the EXOTIC reduction block (transit projects opened from a
        # visit): the host arms both callables, ADR-048 follow-up
        self._exotic_reduce_hook = None
        self._exotic_export_hook = None
        # the host keeps the comparison sequence in the project so
        # reopening does not rebuild it
        self._sequence_hook = None
        # actions waiting for an automatic solve (request_wcs): they run
        # the moment the solution lands, or their on_fail on a failure
        self._wcs_pending = []
        self.state = UfeImageState(self)
        self.view = UfeImageView(self.state)
        self.setWindowTitle(self.tr("NightScribe Image Workbench"))
        # the workbench is meant to fill a big screen: give the window its
        # maximize/minimize buttons (a plain QDialog lacks them on Windows)
        self.setWindowFlags(self.windowFlags()
                            | Qt.WindowMaximizeButtonHint
                            | Qt.WindowMinimizeButtonHint)
        self._build_ui()
        self._build_shortcuts()
        self.resize(1440, 960)
        self.setMinimumSize(1000, 640)
        self.state.image_loaded.connect(self._on_image_loaded)
        self.state.wcs_changed.connect(self._sync_wcs_buttons)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        # ADR-046: the corner boxes always read the live state (solve,
        # measurement, attached object) through this provider
        self.view.set_boxes_provider(self._chart_boxes)

    def showEvent(self, event):
        # The configured defaults land at every show: the corner-boxes
        # state and the bar style (icons-only vs icon + text). The
        # observer's own toggles survive while the dialog stays open.
        from ..config import config
        self.btn_boxes.setChecked(bool(config.get("chart_boxes", False)))
        self._apply_bar_style()
        super().showEvent(event)

    def changeEvent(self, event):
        # Maximizing/restoring must use the whole screen: the image is
        # refitted once the new geometry lands. Only when the observer
        # has not zoomed by hand, so an inspection zoom is never lost.
        super().changeEvent(event)
        from PySide6.QtCore import QEvent, QTimer
        if event.type() == QEvent.Type.WindowStateChange \
                and getattr(self, "state", None) is not None:
            QTimer.singleShot(0, self._refit_on_state_change)

    def _refit_on_state_change(self):
        # @return: None. Refits the plate to the (new) viewport unless the
        # observer owns the current zoom.
        if self.state.has_image and not getattr(self.view, "_user_zoomed",
                                                False):
            self.view.fit_to_scene()

    # ------------------------------------------------------------- layout

    def _build_ui(self):
        # Top bar + object line + splitter (image | feature tabs) +
        # histogram strip. The structure is the Designer file's
        # (ADR-005); the custom widgets land in its placeholders.
        self.histogram = HistogramWidget(self.state)
        self._ui = adopt_ui(self, "ufe_dialog")
                                            # over: no wrapper margins
        self.splitter = self._ui.splitter
        # ph_series (0) | ph_view (1) | tabs (2): the series panel sits at
        # the left of the image; hidden unless a visit arms the series
        self.splitter.replaceWidget(1, self.view)
        # (after the adoption the layout answers to self, not the husk;
        # drop_in also hides the placeholder: QLayout.replaceWidget does
        # not, and a visible one eats the top bar's clicks)
        drop_in(self.layout(), self._ui.ph_histogram, self.histogram)
        self.splitter.setStretchFactor(0, 1)     # series: grows a bit
        self.splitter.setStretchFactor(1, 4)     # the image dominates
        self.splitter.setStretchFactor(2, 2)     # the tab column grows too
        self.tabs = self._ui.tabs
        self.lbl_object = self._ui.lbl_object
        from . import theme
        self.lbl_object.setStyleSheet(
            f"color: {theme.C_TEXT_DIM}; padding: 0 4px;")
        self._wire_topbar()
        self._build_feature_tabs()
        # the series block lives at the left of the image (its own pane,
        # hidden unless a visit arms it): the visit strip (frame navigator
        # + the EXOTIC reduction for transit projects) carries it in its
        # ph_series placeholder (ADR-005)
        self.series_pane = QWidget(self)
        series_lay = QVBoxLayout(self.series_pane)
        series_lay.setContentsMargins(0, 0, 0, 0)
        self.visit_panel = load_ui("ufe_visit_panel", self)
        grp = getattr(self.tab_measure, "grp_series", None)
        if grp is not None:
            drop_in(self.visit_panel.layout(), self.visit_panel.ph_series,
                    grp)
        series_lay.addWidget(self.visit_panel)
        self.series_pane.setMinimumWidth(300)
        self.splitter.replaceWidget(0, self.series_pane)
        self.series_pane.hide()
        self._frame_index = 0
        self._wire_frame_nav()

    def _wire_topbar(self):
        # Aliases and signal wiring for the Designer top bar (ADR-005).
        # The zoom buttons' texts and tooltips are set here ("Fit"
        # translates, the factors are data); the glyph skin then reads
        # them into _bar_labels, as always.
        self.btn_load = self._ui.btn_load
        self.btn_load.clicked.connect(self._on_load)
        self.btn_export = self._ui.btn_export
        self.btn_export.clicked.connect(self._on_export_png)
        self.btn_north = self._ui.btn_north
        self.btn_north.toggled.connect(
            lambda checked: self.view.set_hud(north=checked))
        self.btn_scale = self._ui.btn_scale
        self.btn_scale.toggled.connect(
            lambda checked: self.view.set_hud(scale=checked))
        self.btn_annot = self._ui.btn_annot
        self.btn_annot.toggled.connect(
            lambda checked: self.view.set_annotations_visible(checked))
        # ADR-046: the metadata corner boxes (object, date, position,
        # brightness, site, scale); the configured default lands at every
        # show, the toggle is the session's own choice
        self.btn_boxes = self._ui.btn_boxes
        self.btn_boxes.toggled.connect(
            lambda checked: self.view.set_hud(boxes=checked))
        # the global object mark: where the attached project's object
        # sits on the plate (its own layer, visible by default, it never
        # mixes with the feature tabs' markers)
        self.btn_mark = self._ui.btn_mark
        self.btn_mark.toggled.connect(
            lambda checked: self.view.set_object_mark_visible(checked))
        self.btn_solve = self._ui.btn_solve
        self.btn_solve.clicked.connect(self._on_solve)
        # ADR-044 rev (2026-09-24): the toggles' _on/_off glyphs follow
        # the checked state (icons-only mode)
        for name, base in (("btn_north", "ufe_north"),
                           ("btn_scale", "ufe_scale"),
                           ("btn_annot", "ufe_annot"),
                           ("btn_boxes", "ufe_boxes"),
                           ("btn_mark", "ufe_mark")):
            toggle = getattr(self, name)
            toggle.toggled.connect(
                lambda _checked, btn=toggle, b=base:
                self._bar_reskin_toggle(btn, b))
        self.lbl_zoom_hint = self._ui.lbl_zoom_hint
        self.btn_zoom = {}
        for factor, label in _ZOOM_PRESETS:
            btn = getattr(self._ui, "btn_zoom_"
                          + ("fit" if factor is None else label))
            btn.setText(self.tr("Fit") if factor is None else label)
            btn.setToolTip(self.tr("Fit the plate to the window")
                           if factor is None else
                           self.tr("Zoom {0} % (1:1 at 100)").format(
                               int(factor * 100)))
            btn.clicked.connect(
                lambda _checked=False, f=factor: self._on_zoom_preset(f))
            self.btn_zoom[label] = btn
        self.lbl_zoom = self._ui.lbl_zoom
        self.lbl_zoom.setText("–")
        # ADR-044 rev (2026-09-24): the original labels, kept here (not on
        # the buttons): the icons-only mode clears them, and the bar can
        # reskin between shows on the same cached dialog.
        self._bar_labels = {
            "btn_load": self.btn_load.text(),
            "btn_export": self.btn_export.text(),
            "btn_north": self.btn_north.text(),
            "btn_scale": self.btn_scale.text(),
            "btn_annot": self.btn_annot.text(),
            "btn_boxes": self.btn_boxes.text(),
            "btn_mark": self.btn_mark.text(),
            "btn_solve": self.btn_solve.text(),
        }
        for label, btn in self.btn_zoom.items():
            self._bar_labels["zoom_" + label] = btn.text()
        self._apply_bar_style()

    # -------------------------------------- top-bar style (ADR-044 rev)

    def _icon(self, name):
        # @args: name - the asset stem (e.g. "ufe_load"); the SVG lives in
        #        the bundled assets/ folder
        # @return: the QIcon, null when the asset is missing (the caller
        #          then keeps its text as the fallback)
        from . import theme
        path = theme.asset(name + ".svg")
        if not path.exists():
            return QIcon()
        return QIcon(path.as_posix())

    def _bar_icon_mode(self):
        # @return: True when the icons-only top bar is on (the default)
        from ..config import config
        return bool(config.get("ufe_bar_icons", True))

    def _apply_bar_style(self):
        # ADR-044 rev (2026-09-24): the top bar follows the "icons-only"
        # setting: compact glyphs instead of labels, with Solve and Move
        # marker keeping their text in both modes. Runs at build time and
        # at every show, so a settings change lands on the cached dialog's
        # next open. A missing asset degrades to the text-only button.
        icon_mode = self._bar_icon_mode()
        self.lbl_zoom_hint.setVisible(not icon_mode)
        for name, spec in _BAR_BUTTONS.items():
            btn = getattr(self, name)
            if name == "btn_solve" and self._solve_worker is not None:
                continue            # the worker owns the "Solving…" text
            key = spec["base"]
            if spec.get("toggle"):
                key += "_on" if btn.isChecked() else "_off"
            ic = self._icon(key)
            if ic.isNull():
                btn.setIcon(QIcon())
                btn.setText(self._bar_labels[name])
                continue
            btn.setIcon(ic)
            btn.setIconSize(QSize(16, 16))
            if spec["icon_only"] and icon_mode:
                btn.setText("")
            elif not icon_mode:
                btn.setText(self._bar_labels[name])
        for label, btn in self.btn_zoom.items():
            stem = _ZOOM_ICONS.get(label)
            ic = self._icon(stem) if stem else QIcon()
            if ic.isNull():
                btn.setIcon(QIcon())
                btn.setText(self._bar_labels["zoom_" + label])
                continue
            btn.setIcon(ic)
            btn.setIconSize(QSize(16, 16))
            btn.setText("" if icon_mode
                        else self._bar_labels["zoom_" + label])

    def _bar_reskin_toggle(self, btn, base):
        # @args: btn - a checkable bar toggle, base - its glyph stem
        #        (e.g. "ufe_north"): flips the _on/_off glyph when the
        #        state changes. Silently a no-op in text mode or when the
        #        asset is missing (the label is the fallback).
        if not self._bar_icon_mode():
            return
        ic = self._icon(base + ("_on" if btn.isChecked() else "_off"))
        if not ic.isNull():
            btn.setIcon(ic)
            btn.setIconSize(QSize(16, 16))

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
        # The blink timer must not fire into a closing dialog, and the
        # Measure tab's workers must not outlive it either: a series run
        # or a Live watch left behind keeps measuring and writing runs
        # into the DB forever (shutdown cancels both and waits).
        self.tab_blink.shutdown()
        try:
            self.tab_measure.shutdown()
        except Exception as err:      # a failed cleanup never blocks close
            logger.warning("measure tab shutdown failed: %s", err)
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
        self._sync_frame_nav()
        return True

    def show_tab(self, tab):
        # Brings one feature tab to the front (Blink / Photometry /
        # Annotate) so the host can deep-link a workflow into the
        # editor. The Photometry sections still accept the legacy names:
        # tab_compare / tab_measure by widget or "compare" / "measure"
        # by name; there are no modes anymore, they all land on the same
        # Photometry tab (ADR-044 rev 2026-09-25).
        # @args: tab - a top-level tab widget, an inner Photometry
        #        section widget, or "compare" / "measure"
        if tab in (self.tab_compare, self.tab_measure) \
                or tab in ("compare", "measure"):
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
        #        tab shows its «Save…» button only then.
        self._point_hook = fn
        tab = getattr(self, "tab_measure", None)
        if tab is not None:
            tab.set_project_attached(fn is not None)

    def point_hook(self):
        # @return: the point hook callable, or None when the editor was
        #          opened ad-hoc (Measure tab hides its save button)
        return self._point_hook

    def set_sequence_hook(self, fn):
        # @args: fn - callable(state) receiving the Compare tab's sequence
        #        (project context shape) whenever the observer changes it,
        #        or None. The host stores it so reopening the visit brings
        #        the comparison stars back.
        self._sequence_hook = fn if callable(fn) else None

    def notify_sequence(self, state, force=False):
        # The Compare tab reports its sequence here; without a hook it is a
        # no-op. An empty sequence is only stored when forced (an explicit
        # clear), never on a plate reset/restore.
        # @args: state - {"catalog", "catalog_name", "fov_arcmin",
        #        "target_mag", "entries"}, force - store even when empty
        if self._sequence_hook is None:
            return False
        if not state or (not force and not state.get("entries")):
            return False
        try:
            self._sequence_hook(state)
            return True
        except Exception as err:
            logger.warning("sequence hook failed: %s", err)
            return False

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

    # ---------------------------------------------------- plate state
    # (ADR-047: the working state of the open plate, as plain JSON the
    # host stores in the plate row's meta["ufe"])

    def capture_full_state(self):
        # ADR-047: the open plate's working state: the stretch knobs plus
        # the photometry tab's blocks (the measure recipe and the
        # sequence; None when no field has been built).
        # @args: none
        # @return: the {"stretch", "measure", "sequence"} dict
        return {
            "stretch": self.state.stretch_state(),
            **(self.tab_photometry.capture_state() or {}),
        }

    def apply_plate_state(self, st):
        # ADR-047: restore a plate's saved working state on top of the
        # open plate: the stretch first (the image already looks like it
        # did), then the recipe and the sequence. Missing blocks are
        # skipped (a state saved before the sequence existed restores
        # the recipe only).
        # @args: st - the meta["ufe"] dict, or None for a no-op
        # @return: None
        if not st or not self.state.has_image:
            return
        s = dict(st.get("stretch") or {})
        self.state.set_stretch(black=s.get("black"), white=s.get("white"),
                               gamma=s.get("gamma"))
        if bool(s.get("invert", False)) != self.state.inverted:
            self.state.toggle_invert()
        for axis, key in (("h", "flip_h"), ("v", "flip_v")):
            flipped = (self.state.flip_h if axis == "h"
                       else self.state.flip_v)
            if bool(s.get(key, False)) != flipped:
                self.state.toggle_flip(axis)
        self.tab_photometry.apply_state(st)

    def load_saved_sequence(self, seq):
        # ADR-047/048: when the open plate carries no sequence of its own,
        # the project's saved sequence fills the Compare tab, so measuring
        # or reducing with EXOTIC starts from what was already built
        # instead of asking for it again. The plate's own state always
        # wins (load_saved_sequence is only reached when it had none).
        # @args: seq - the project context's "sequence" dict, or None
        # @return: True when a sequence was restored
        if not seq or not seq.get("entries"):
            return False
        if self.tab_compare.entries():
            return False
        self.tab_photometry.apply_state({"sequence": seq})
        return True

    def reset_state_local(self):
        # ADR-047: the in-editor half of the state reset: the recipe back
        # to the editor's defaults, the stretch back to auto, the
        # sequence field cleared. The saved-state clear is the host's
        # job (notify_reset_state).
        # @args: none
        # @return: False when there is no plate, True when applied
        if not self.state.has_image:
            return False
        self.tab_measure.apply_state(self.tab_measure.ui_defaults())
        self.state.reset_stretch()
        self.tab_photometry.tab_compare.reset_state()
        return True

    # ---------------------------------------------------- reset hooks

    def set_reset_hooks(self, state_fn=None, points_fn=None):
        # ADR-047: the host's two plate resets. state_fn clears the open
        # plate's saved state block; points_fn drops the plate's measured
        # points. Both optional: opened ad-hoc, both are None and the
        # Measure tab hides its reset buttons (same rule as the save
        # button: not attached, not visible).
        # @args: state_fn - callable() or None, points_fn - callable() or None
        # @return: None
        self._reset_state_hook = state_fn if callable(state_fn) else None
        self._reset_points_hook = points_fn if callable(points_fn) else None
        if hasattr(self, "tab_measure"):
            self.tab_measure.set_reset_attached(
                self._reset_state_hook is not None)

    def notify_reset_state(self):
        # ADR-047: the Measure tab applied the editor's defaults and now
        # asks the host to clear the plate's saved state block.
        # @args: none
        # @return: True when the hook ran
        if self._reset_state_hook is None:
            return False
        try:
            self._reset_state_hook()
            return True
        except Exception as err:
            logger.warning("reset-state hook failed: %s", err)
            return False

    def notify_reset_points(self):
        # ADR-047: destructive (the light curve loses the points): the
        # Measure tab already asked the user before this fires.
        # @args: none
        # @return: True when the hook ran
        if self._reset_points_hook is None:
            return False
        try:
            self._reset_points_hook()
            return True
        except Exception as err:
            logger.warning("reset-points hook failed: %s", err)
            return False

    # ---------------------------------------------------- series hooks

    def set_series_hook(self, fn):
        # @args: fn - callable() -> {"pid", "session_id", "paths"} or None.
        #        The host arms it only when the editor was opened from a
        #        visit; the Measure tab shows its series block only then
        #        (D8: without a visit there is no series).
        self._series_hook = fn if callable(fn) else None
        if hasattr(self, "tab_measure"):
            self.tab_measure.set_series_attached(self._series_hook is not None)
        if hasattr(self, "series_pane"):
            self.series_pane.setVisible(self._series_hook is not None)
        self._sync_frame_nav()
        self._sync_exotic_block()

    def series_context(self):
        # @return: the visit context the host hooked, or None
        if self._series_hook is None:
            return None
        try:
            return self._series_hook()
        except Exception as err:
            logger.warning("series hook failed: %s", err)
            return None

    # ----------------------------------------------------- visit frames

    def _wire_frame_nav(self):
        # The frame navigator over the series block (ADR-048 follow-up):
        # the open frame is the reference the series and EXOTIC measure
        # in, so stepping frames is stepping the reference.
        vp = self.visit_panel
        vp.btn_frame_prev.clicked.connect(
            lambda: self._goto_frame(self._frame_index - 1))
        vp.btn_frame_next.clicked.connect(
            lambda: self._goto_frame(self._frame_index + 1))
        vp.btn_frame_first.clicked.connect(self._frame_first)
        vp.btn_exotic_reduce.clicked.connect(self._notify_exotic_reduce)
        vp.btn_exotic_export.clicked.connect(self._notify_exotic_export)
        self.tab_compare.sequence_changed.connect(self._sync_exotic_block)
        self._sync_frame_nav()

    def _visit_paths(self):
        # @return: the visit's sorted frame paths, or [] (no visit armed)
        ctx = self.series_context() or {}
        return list(ctx.get("paths") or [])

    def _sync_frame_nav(self):
        # The strip mirrors the open frame among the visit's frames.
        if not hasattr(self, "visit_panel"):
            return
        paths = self._visit_paths()
        n = len(paths)
        if n and self.state.path:
            try:
                self._frame_index = paths.index(str(self.state.path))
            except ValueError:
                self._frame_index = min(self._frame_index, n - 1)
        elif n:
            self._frame_index = min(self._frame_index, n - 1)
        else:
            self._frame_index = 0
        vp = self.visit_panel
        vp.lbl_frame.setText(
            self.tr("Frame {0}/{1}").format(self._frame_index + 1, n)
            if n else self.tr("Frame"))
        vp.lbl_frame_file.setText(self.tr("No visit frames")
                                  if not n else (
                                      Path(self.state.path).name
                                      if self.state.path else ""))
        vp.btn_frame_prev.setEnabled(n > 0 and self._frame_index > 0)
        vp.btn_frame_next.setEnabled(n > 0 and self._frame_index < n - 1)
        vp.btn_frame_first.setEnabled(n > 0 and self._frame_index > 0)

    def _goto_frame(self, index):
        # Loads another frame of the visit as the open plate. The Compare
        # tab's state (field + sequence) rides along: the stars are RA/Dec
        # and land again through the new plate's WCS.
        # @args: index - frame index in the visit's sorted paths
        paths = self._visit_paths()
        if not paths:
            return
        index = max(0, min(int(index), len(paths) - 1))
        path = paths[index]
        if str(path) != str(self.state.path):
            st = self.tab_photometry.capture_state() \
                if self.state.has_image else None
            if not self.open_plate(path):
                return
            if st:
                self.tab_photometry.apply_state(st)
        self._frame_index = index
        self._sync_frame_nav()

    def _frame_prev(self):
        self._goto_frame(self._frame_index - 1)

    def _frame_next(self):
        self._goto_frame(self._frame_index + 1)

    def _frame_first(self):
        self._goto_frame(0)

    # ------------------------------------------------ transit (EXOTIC)

    def set_exotic_hooks(self, reduce_fn=None, export_fn=None):
        # @args: reduce_fn - callable() that starts the host's EXOTIC
        #        reduction on the open frame and the loaded sequence, or
        #        None; export_fn - callable() for the inits.json handoff.
        #        Armed only for a transit project opened from a visit.
        self._exotic_reduce_hook = reduce_fn if callable(reduce_fn) else None
        self._exotic_export_hook = export_fn if callable(export_fn) else None
        self._sync_exotic_block()

    def sequence_entries(self):
        # @return: the sequence built in the Compare tab (for the host)
        if not hasattr(self, "tab_compare"):
            return []
        return list(self.tab_compare.entries())

    def current_frame_path(self):
        # @return: the open plate path, or None
        return self.state.path if self.state.has_image else None

    def _sync_exotic_block(self):
        # The EXOTIC block lives only in a transit visit; the reduction
        # waits for a comparison sequence and says why when it is missing.
        if not hasattr(self, "visit_panel"):
            return
        ctx = self.series_context() or {}
        armed = self._exotic_reduce_hook is not None \
            and ctx.get("kind") == "transit" and bool(ctx.get("paths"))
        grp = self.visit_panel.grp_exotic
        grp.setVisible(bool(armed))
        if not armed:
            return
        n = len(self.sequence_entries())
        self.visit_panel.btn_exotic_reduce.setEnabled(n > 0)
        self.visit_panel.btn_exotic_export.setEnabled(n > 0)
        self.visit_panel.lbl_exotic_status.setText(
            self.tr("Uses the open frame and the sequence above.")
            if n else self.tr(
                "Build the comparison sequence first (Photometry, "
                "«Build the sequence…»)."))

    def _notify_exotic_reduce(self):
        if self._exotic_reduce_hook is None:
            return
        try:
            self._exotic_reduce_hook()
        except Exception as err:
            logger.warning("exotic reduce hook failed: %s", err)

    def _notify_exotic_export(self):
        if self._exotic_export_hook is None:
            return
        try:
            self._exotic_export_hook()
        except Exception as err:
            logger.warning("exotic export hook failed: %s", err)

    def set_points_hook(self, fn):
        # @args: fn - callable(rows, cfg) -> run_id, or None. The Measure
        #        tab sends a whole series run so the host creates one run
        #        and writes its points in a batch (ADR-048, D9); cfg is
        #        the run echo and carries its status (D18).
        self._points_hook = fn if callable(fn) else None

    def set_run_undo_hook(self, fn):
        # @args: fn - callable(run_id) -> deleted count, or None. Backs
        #        the tab's "Undo this run" (D6).
        self._run_undo_hook = fn if callable(fn) else None

    def notify_points(self, rows, cfg):
        # @args: rows - point dicts of one run, cfg - JSON-safe run echo
        # @return: the new run id, or None when there is no hook / it failed
        if self._points_hook is None:
            return None
        try:
            return self._points_hook(rows or [], cfg or {})
        except Exception as err:
            logger.warning("points hook failed: %s", err)
            return None

    def undo_run(self, run_id):
        # @args: run_id - the run to undo
        # @return: the number of points deleted (0 with no hook)
        if self._run_undo_hook is None:
            return 0
        try:
            return int(self._run_undo_hook(run_id) or 0)
        except Exception as err:
            logger.warning("run-undo hook failed: %s", err)
            return 0

    def set_exoclock_hook(self, fn):
        # @args: fn - callable(payload) or None. Called after the ExoClock
        #        files are written so the host records the project outcome
        #        (ADR-049).
        self._exoclock_hook = fn if callable(fn) else None

    def notify_exoclock(self, payload):
        # @return: True when the hook ran
        if self._exoclock_hook is None:
            return False
        try:
            self._exoclock_hook(payload or {})
            return True
        except Exception as err:
            logger.warning("exoclock hook failed: %s", err)
            return False

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
        # the global object mark rides on the object's coordinates; the
        # view (re)places it on every plate load and solve by itself
        obj_dict = self._object or {}
        ra, dec = obj_dict.get("ra"), obj_dict.get("dec")
        self.view.set_object_mark(ra, dec)
        self.btn_mark.setEnabled(
            self.view._object_mark_radec is not None)
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

    # ------------------------------------------- chart boxes (ADR-046)

    def _chart_target_scene(self):
        # Where the chart calls the object: the measured centroid first
        # (the truth sits at the measurement), then the attached
        # object's coordinates; None when nothing says anything (no
        # plate, or no WCS and no measurement).
        # @return: (x, y) scene coordinates, or None
        if not self.state.has_image:
            return None
        last = self.tab_measure._last
        if last is not None:
            return self.state.data_to_scene(last["col"], last["row"])
        obj = self._object or {}
        if self.state.wcs is not None and obj.get("ra") is not None \
                and obj.get("dec") is not None:
            try:
                col, row = self.state.wcs.sky_to_pixel(float(obj["ra"]),
                                                       float(obj["dec"]))
                w, h = self.state.plate_shape
                if 0 <= col < w and 0 <= row < h:
                    return self.state.data_to_scene(col, row)
            except Exception:
                pass
        return None

    def _chart_boxes(self):
        # The view's boxes provider: assembles the corner-box content
        # from the live state, following core/chart_annotate's rules
        # (name always; position/scale only solved; brightness only when
        # measured this session).
        # @return: the boxes dict ({} when nothing can be said)
        from ..config import config
        from ..core import chart_annotate, fits_meta
        if not self.state.has_image:
            return {}
        obj = self._object or {}
        name = (obj.get("name") or "").strip()
        if not name:
            name = self.tab_compare.edt_target.text().strip()
        if not name and self.state.path:
            name = Path(self.state.path).stem
        meta = fits_meta.meta_from_header(self.state.header or {})
        wcs_info = None
        if self.state.wcs is not None:
            scale = self.state.wcs.pixel_scale()
            # the field of view of what is actually shown, clamped to
            # the plate (the fit leaves a relaxed margin around it)
            pw, ph = self.state.plate_shape
            tl = self.view.mapToScene(0, 0)
            br = self.view.mapToScene(self.view.viewport().width(),
                                      self.view.viewport().height())
            vis_w = min(abs(br.x() - tl.x()), float(pw))
            vis_h = min(abs(br.y() - tl.y()), float(ph))
            wcs_info = {"scale_arcsec_px": scale,
                        "fov_arcmin": (vis_w * scale / 60.0,
                                       vis_h * scale / 60.0)}
            pos = self._chart_target_scene()
            if pos is not None:
                col, row = self.state.scene_to_data(pos[0], pos[1])
                try:
                    ra, dec = self.state.wcs.pixel_to_sky(col, row)
                    wcs_info["ra_deg"], wcs_info["dec_deg"] = ra, dec
                except Exception:
                    pass
        measured = None
        last = self.tab_measure._last
        if last is not None and last.get("mag") is not None:
            measured = {"mag": last["mag"], "err": last.get("err"),
                        "band": last.get("band")}
        return chart_annotate.build_boxes(
            name=name, meta=meta, wcs_info=wcs_info,
            site=chart_annotate.site_from_config(config),
            measured=measured)

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
        # the visit's frame navigator (a no-op without a visit)
        for key, fn in ((Qt.Key_PageUp, self._frame_prev),
                        (Qt.Key_PageDown, self._frame_next)):
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
        # Solve astrometry…: blind-solve the current plate (the button).
        if not self.state.has_image:
            return
        self._start_solve()

    def request_wcs(self, after, on_fail=None):
        # An action needs a WCS before it can run: with a solved plate it
        # runs now; otherwise the same blind solve as the button starts
        # and the action is queued for the solution (never a dead end
        # telling the observer to solve by hand). ADR-051.
        # @args: after - callable() run on a usable WCS,
        #        on_fail - optional callable() when the solve fails
        if self.state.wcs is not None:
            after()
            return
        self._wcs_pending.append((after, on_fail))
        if self._solve_worker is not None and self._solve_worker.isRunning():
            return
        self._start_solve()

    def _start_solve(self):
        # The one solve path (the button and request_wcs share it) through
        # the ADR-051 dispatcher (auto: local ASTAP first, nova as the
        # fallback; subprocess and network off the GUI thread).
        if self._solve_worker is not None and self._solve_worker.isRunning():
            return                      # one solve at a time
        if not self.state.has_image:
            self._fail_wcs_pending()
            return
        if self._nova_key_needed():
            QMessageBox.information(
                self, self.tr("NightScribe Image Workbench"),
                self.tr("Set your Astrometry.net API key in Settings to "
                        "solve plates automatically, or solve them with "
                        "ASTAP, NINA, Ekos or PixInsight and save them "
                        "again."))
            self._fail_wcs_pending()
            return
        from .workers import UfeSolveWorker
        self._solve_worker = UfeSolveWorker(Path(self.state.path))
        self._solve_worker.progress.connect(self._on_solve_stage)
        self._solve_worker.finished.connect(self._on_solved)
        self.btn_solve.setEnabled(False)
        self._on_solve_stage("login")
        self._show_solve_wait()
        self._solve_worker.start()

    def _show_solve_wait(self):
        # Blind solving takes seconds (ASTAP) to minutes (nova): show it,
        # never a dead button. Indeterminate bar, non-modal, Cancel kills
        # the running solver (ADR-051 rev.).
        wait = QProgressDialog(self.tr("Solving the plate…"),
                               self.tr("Cancel"), 0, 0, self)
        wait.setWindowTitle(self.tr("NightScribe Image Workbench"))
        wait.setWindowModality(Qt.NonModal)
        wait.setMinimumDuration(0)
        wait.setAutoClose(False)
        wait.setAutoReset(False)
        wait.canceled.connect(self._cancel_solve)
        wait.show()
        self._solve_wait = wait

    def _close_solve_wait(self):
        wait = getattr(self, "_solve_wait", None)
        if wait is not None:
            # closing a QProgressDialog emits canceled(): block it, this
            # close is the solve landing, not the observer cancelling
            wait.blockSignals(True)
            wait.close()
            wait.deleteLater()
            self._solve_wait = None

    def _cancel_solve(self):
        # The observer cancelled: kill ASTAP (or let nova's worker land).
        if self._solve_worker is not None:
            self._solve_worker.cancel()
        self._close_solve_wait()
        self.btn_solve.setText(self.tr("Solve astrometry…"))
        self.btn_solve.setEnabled(self.state.has_image)

    def _drain_wcs_pending(self):
        # Runs the queued actions now that the plate has a WCS.
        pending, self._wcs_pending = self._wcs_pending, []
        for after, _fail in pending:
            try:
                after()
            except Exception as err:
                logger.warning("WCS continuation failed: %s", err)

    def _fail_wcs_pending(self):
        # The solve did not happen (no plate, no key, solver failure):
        # every queued action gets its own way out.
        pending, self._wcs_pending = self._wcs_pending, []
        for _after, fail in pending:
            if callable(fail):
                try:
                    fail()
                except Exception as err:
                    logger.warning("WCS failure continuation failed: %s", err)

    def _nova_key_needed(self):
        # The API-key guard only fires when the solve would actually go
        # to nova.astrometry.net (ADR-051): the solver is forced to
        # "astrometry", or "auto" finds no ASTAP binary to try first.
        # @return: True when the solve needs a nova key and none is set
        from ..config import config
        if (config.get("astrometry_key") or "").strip():
            return False
        solver = (config.get("solver") or "auto").lower()
        if solver == "astap":
            return False          # never touches nova
        if solver == "astrometry":
            return True
        # auto (also the dispatcher's default for unknown values): nova
        # is only reached when no ASTAP binary resolves
        from ..core.sources import astap
        return astap.resolve_binary(config.get("astap_path") or None) is None

    def _solver_names(self):
        # The backend(s) the dispatcher runs, named for the failure
        # message; the names themselves are product names, not translated.
        # @return: "ASTAP", "Astrometry.net" or both, for "auto"
        from ..config import config
        solver = (config.get("solver") or "auto").lower()
        if solver == "astap":
            return "ASTAP"
        if solver == "astrometry":
            return "Astrometry.net"
        return self.tr("ASTAP and Astrometry.net")

    def _on_solve_stage(self, stage):
        # @args: stage - the worker's stage text, mirrored on the button
        #        and on the busy dialog (astap -progress lines are long:
        #        cap them so the label stays readable)
        stage = (stage or "").strip()
        text = self.tr("Solving: {0}…").format(stage[:70]) if stage \
            else self.tr("Solving the plate…")
        self.btn_solve.setText(text)
        wait = getattr(self, "_solve_wait", None)
        if wait is not None:
            wait.setLabelText(text)

    def _on_solved(self, cards):
        # @args: cards - solved WCS cards, or {} when the solve failed
        cancelled = self._solve_worker is not None \
            and self._solve_worker.cancelled()
        self._close_solve_wait()
        self.btn_solve.setText(self.tr("Solve astrometry…"))
        self.btn_solve.setEnabled(self.state.has_image)
        self._solve_worker = None
        if cancelled:
            # the observer cancelled: the queued actions get their way out,
            # never the "could not solve" box
            self._fail_wcs_pending()
            return
        if not cards:
            QMessageBox.warning(
                self, self.tr("NightScribe Image Workbench"),
                self.tr("{0} could not solve the plate. Check the solver "
                        "in Settings (ASTAP path, Astrometry.net key) or "
                        "solve the plate with NINA, Ekos or PixInsight "
                        "and save it again.").format(self._solver_names()))
            self._fail_wcs_pending()
            return
        if self.state.set_wcs_cards(cards):
            logger.info("UFE: astrometry solved for %s", self.state.path)
            self._persist_solution(cards)
            self._drain_wcs_pending()
        else:
            QMessageBox.warning(
                self, self.tr("NightScribe Image Workbench"),
                self.tr("The Astrometry.net solution is not usable "
                        "(non-TAN WCS)."))
            self._fail_wcs_pending()

    def _persist_solution(self, cards):
        # ADR-051 rev: a solved plate is stored solved, so it is solved
        # for every program and next time needs no solve. The write is
        # atomic; a read-only file only costs a warning, the WCS stays in
        # memory for the session.
        from ..core import wcs_store
        _done, err = wcs_store.persist_solution(self.state.path, cards)
        if err:
            QMessageBox.warning(
                self, self.tr("NightScribe Image Workbench"),
                self.tr("The solved WCS could not be written into the file "
                        "({0}); it stays in memory for this session.")
                .format(err))
