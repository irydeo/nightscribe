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

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFontMetrics, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox, QSizePolicy, \
    QProgressDialog, QVBoxLayout, QWidget

from ..config import config
from ..core import fits_io
from . import theme
from .ufe_state import UfeImageState
from .ui_loader import adopt_ui, drop_in, load_ui
from .widgets.collapsible_section import CollapsibleSection
from .widgets.histogram_widget import HistogramWidget
from .widgets.ufe_image_view import UfeImageView
from .widgets.ufe_project_badge import UfeProjectBadge

logger = logging.getLogger("nightscribe.gui.ufe_dialog")

# one glyph per level of the status line (U4), so a warning reads as a
# warning before it is read
_STATUS_GLYPH = {"info": "ⓘ", "warn": "⚠", "error": "✕"}

_ZOOM_PRESETS = ((None, "Fit"), (0.5, "50"), (1.0, "100"),
                 (2.0, "200"), (4.0, "400"))

# The three columns' widths: the sides get what they need, the plate gets
# the rest (a maximized window must widen the PICTURE, not the form).
# the solve's wait dialog appears only after this long (a fast local solve
# must not flash a window at the observer)
_SOLVE_SHOW_MS = 250

_SERIES_W = 300
_TABS_W = 380
_SERIES_MAX_W = 420
_TABS_MAX_W = 520

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
        self._visit_worker = None   # VisitSolveWorker: the visit's batch
        self._visit_wait = None     # its bar, with a real Cancel
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
        # ADR-046 rev.: the plate's band always reads the live state
        # (solve, measurement, attached object, zoom) through this
        # provider, consulted at paint time
        self.view.set_band_provider(self._chart_band)

    def showEvent(self, event):
        # The configured defaults land at every show: what the band says
        # about the plate and the bar style (icons-only vs icon + text).
        # The observer's own toggles survive while the dialog stays open.
        from ..config import config
        self.btn_boxes.setChecked(bool(config.get("chart_data", True)))
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
        # ph_series (0) | centre (1) | tabs (2): the series panel sits at
        # the left of the image; hidden unless a visit arms the series.
        #
        # The centre is a SWITCH (V2): the plate or the light curve, in the
        # same place and full size. The curve used to live in a small box
        # of the left panel and you had to click it to see it properly,
        # which is not a way to look at a curve.
        self.stack_centre = self._ui.stack_centre
        self.btn_page_image = self._ui.btn_page_image
        self.btn_page_curve = self._ui.btn_page_curve
        self._centre_page(0, self.view)
        # G: the project this window is open for, in the corner of the bar
        self.badge = UfeProjectBadge(self)
        drop_in(self._ui.topbar, self._ui.ph_badge, self.badge)
        self.btn_page_image.toggled.connect(
            lambda on: on and self.stack_centre.setCurrentIndex(0))
        self.btn_page_curve.toggled.connect(
            lambda on: on and self.stack_centre.setCurrentIndex(1))
        # (after the adoption the layout answers to self, not the husk;
        # drop_in also hides the placeholder: QLayout.replaceWidget does
        # not, and a visible one eats the top bar's clicks)
        #
        # U1: the histogram strip goes inside a foldable section with the
        # state remembered. It is the strip the observer needs while
        # stretching and forgets the rest of the time, and while it was
        # always open it kept 200 px of a 1000 px window (a fifth of it)
        # for two rows of controls.
        self.hist_section = CollapsibleSection(self.tr("Histogram"), self)
        self.hist_section.contentLayout().addWidget(self.histogram)
        self.hist_section.setCollapsed(
            bool(config.get("ufe_histogram_folded", 0)))
        self.hist_section.sectionToggled.connect(self._on_histogram_fold)
        drop_in(self.layout(), self._ui.ph_histogram, self.hist_section)
        # U1: WHO OWNS THE EXTRA HEIGHT. The Designer file carries the
        # stretch (0,0,1,0) but QUiLoader does NOT apply it, so every item
        # came out with stretch 0: nobody wanted the extra space and Qt
        # gave it to whatever could grow. That is why the top bar measured
        # 69 px in a tall window (its zoom label has a Preferred policy)
        # and 25 px in a short one, and why the work area was left with
        # 70 % of the window. Set here, explicitly, and the work area gets
        # everything the rest does not need.
        root = self.layout()
        for i in range(root.count()):
            root.setStretch(i, 0)
        # the splitter is found, not counted: this layout has already lost
        # a row (the object line is painted over the plate now) and a
        # hardcoded index would silently hand the stretch to whatever
        # happened to sit there
        for i in range(root.count()):
            if root.itemAt(i).widget() is self.splitter:
                root.setStretch(i, 1)    # the work area: image + tabs
                break
        # and nothing above or below the work area may grow on its own
        for w in (self._ui.lbl_zoom, self._ui.lbl_zoom_hint,
                  self._ui.lbl_status_bar):
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._status_text = ""
        self._status_level = "info"
        # the four bands of the window sit 4 px apart: the gaps between the
        # bar, the work area, the strip and the status line are not a place
        # to spend the plate's height
        root.setSpacing(4)
        # WHO GETS THE WIDTH. Maximizing the window used to grow the right
        # column (the tabs) by its own stretch factor, and the plate stayed
        # in the middle with two fat margins: the plate is what the window
        # is FOR. The sides keep the width they need and nothing more, the
        # centre takes every extra pixel.
        self.splitter.setStretchFactor(0, 0)     # the visit pane
        self.splitter.setStretchFactor(1, 1)     # the plate: everything else
        self.splitter.setStretchFactor(2, 0)     # the tab column
        self.tabs = self._ui.tabs

        self._wire_topbar()
        self._build_feature_tabs()
        self._place_light_curve()
        self._bar_doors()
        self._apply_bar_style()          # the doors' panels included
        self._wire_status()
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
        self._layout_widths()
        self._frame_index = 0
        self._wire_frame_nav()

    def _layout_widths(self):
        # The sides' width, once every column exists (the tab column and
        # the visit pane are built further down than the splitter).
        # @return: None
        # the tab column is capped (a form does not need to grow with a
        # 4K window) and the visit pane is NOT: that was decided before
        # (its content must never be clipped on a wide font) and it does
        # not need a cap, because with no stretch factor it keeps its width
        self.tabs.setMaximumWidth(_TABS_MAX_W)
        self.splitter.setSizes([_SERIES_W, 900, _TABS_W])

    def _centre_page(self, index, widget):
        # Puts a real widget inside one of the centre's pages. The pages are
        # .ui containers (the Designer file owns the structure, the code
        # fills it, ADR-005); the widget is not a page of its own because a
        # custom canvas has no business living in a Designer file.
        # @args: index - 0 image | 1 curve, widget - the real widget
        # @return: None
        page = self.stack_centre.widget(index)
        lay = page.layout()
        if lay is None:
            lay = QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget)

    def begin_session(self, key):
        # The workbench is PERSISTENT on purpose (the observer's plate and
        # stretch survive a close), and that is exactly why it has to know
        # when the session changed: opening it on another project kept the
        # previous one's plate, sequence, series and target (reported, and
        # the same when opening it from Tools).
        #
        # A key of (project id, visit id) names a session; None is the
        # ad-hoc open from the Tools menu. When it changes, the plate and
        # every tab's per-project state go: nothing is lost, because all of
        # it lives in its project.
        # @args: key - the session's key, or None
        # @return: True when a reset happened
        if key == getattr(self, "_session_key", "unset"):
            return False
        self._session_key = key
        self.state.clear()         # the previous project's plate
        self.set_object(None)      # and its object's line over the plate
        for tab in (getattr(self, "tab_measure", None),
                    getattr(self, "tab_compare", None),
                    getattr(self, "tab_annotate", None),
                    getattr(self, "tab_blink", None)):
            clear = getattr(tab, "clear_session", None)
            if callable(clear):
                try:
                    clear()
                except Exception as err:        # never a dead window
                    logger.warning("session reset failed for %s: %s",
                                   type(tab).__name__, err)
        self.set_status("")
        return True

    def _bar_doors(self):
        # U2: the bar keeps what a visit needs (open, export, solve, the two
        # zooms that are used all the time and the current factor) and puts
        # the rest behind two doors. They are not deletions: the view
        # switches (north, scale, annotations, boxes, mark) and the three
        # occasional zoom factors are the SAME widgets, moved one by one
        # into their panel (a layout removed from its parent is deleted by
        # the binding). Their texts and tooltips keep living in the Designer
        # file (ADR-005), and every name the code and the tests use is
        # untouched.
        # @return: None
        self.btn_view = self._ui.btn_view
        self.btn_zoom_more = self._ui.btn_zoom_more
        self._bar_menu(self.btn_view,
                       ("btn_north", "btn_scale", "btn_annot", "btn_boxes",
                        "btn_mark"))
        self._bar_menu(self.btn_zoom_more,
                       ("btn_zoom_50", "btn_zoom_200", "btn_zoom_400"))

    def _bar_menu(self, tool, names):
        # Puts a set of existing buttons inside a dropdown panel hanging
        # from a QToolButton.
        # @args: tool - the QToolButton, names - the attributes to move
        # @return: None
        from PySide6.QtWidgets import (QMenu, QToolButton, QVBoxLayout,
                                       QWidget, QWidgetAction)
        panel = QWidget(self)
        box = QVBoxLayout(panel)
        box.setContentsMargins(6, 6, 6, 6)
        for name in names:
            w = getattr(self._ui, name, None)
            if w is None:
                w = getattr(self, name, None)
            if w is None:
                continue
            # inside a panel an icon with no text would be a riddle: the
            # icon-only skin must leave these ones their label
            w.setProperty("in_panel", True)
            w.setParent(panel)
            box.addWidget(w)
        action = QWidgetAction(tool)
        action.setDefaultWidget(panel)
        menu = QMenu(tool)
        menu.addAction(action)
        tool.setMenu(menu)
        tool.setPopupMode(QToolButton.InstantPopup)

    def _wire_status(self):
        # Every tab reports to the window's single line (U4). The tabs keep
        # their own label (hidden) as a record, so nothing that read it had
        # to change.
        # @return: None
        for tab in (getattr(self, "tab_measure", None),
                    getattr(self, "tab_compare", None),
                    getattr(self, "tab_annotate", None),
                    getattr(self, "tab_blink", None)):
            hook = getattr(tab, "set_status_hook", None)
            if callable(hook):
                hook(self._on_status_hook)

    def _place_light_curve(self):
        # The light curve, in the centre's second page. The Measure tab
        # OWNS it (all the logic is there: data, selection, outliers,
        # binning) and this window only gives it a proper home.
        # @return: None
        chart = getattr(self.tab_measure, "chart_series", None)
        if chart is None:
            return
        self._centre_page(1, chart)

    def show_curve(self):
        # Puts the measured series in front (V2). Called by the Measure tab
        # when a run ends, because that is the moment you want to look at
        # it, and by the chart's own "show me this big" click.
        # @return: None
        self.btn_page_curve.setChecked(True)
        self.stack_centre.setCurrentIndex(1)
        chart = getattr(self.tab_measure, "chart_series", None)
        if chart is not None and getattr(chart, "_points", None):
            chart.fit_to_scene()

    def show_image(self):
        # Back to the plate.
        # @return: None
        self.btn_page_image.setChecked(True)
        self.stack_centre.setCurrentIndex(0)

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
        # ADR-046 rev.: what the plate's band says about the plate
        # (position, magnitude, date, exposure, kit, station, scale, field).
        # The object's name is the heading and stays. The configured
        # default lands at every show; the toggle is the session's choice.
        self.btn_boxes = self._ui.btn_boxes
        self.btn_boxes.toggled.connect(
            lambda checked: self.view.set_hud(data=checked))
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
            if spec["icon_only"] and icon_mode \
                    and not btn.property("in_panel"):
                btn.setText("")      # in the bar an icon and its tooltip
            else:
                # with text, or inside a panel: there an icon with no
                # label would be a riddle (see _bar_doors)
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
            # the same rule as the other bar buttons: an icon with no label
            # is for the BAR; inside a panel the label stays (see _bar_doors)
            btn.setText("" if (icon_mode and not btn.property("in_panel"))
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
        stop = getattr(self.tab_compare, "shutdown", None)
        if callable(stop):
            stop()
        try:
            self.tab_measure.shutdown()
        except Exception as err:      # a failed cleanup never blocks close
            logger.warning("measure tab shutdown failed: %s", err)
        # and the visit's batch: a QThread destroyed while it runs aborts
        # the whole application (the same trap the tabs document)
        worker = getattr(self, "_visit_worker", None)
        if worker is not None and worker.isRunning():
            worker.cancel()
            worker.wait(5000)
        self._visit_worker = None
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

    def set_project_badge(self, payload):
        # The project behind this window, in the list's own language (G).
        # The host builds the payload with the same function the project
        # rows use, so the badge cannot drift from what the observer just
        # left; None hides it (the Tools menu opens with no project).
        # @args: payload - the project row's kwargs, or None
        # @return: None
        badge = getattr(self, "badge", None)
        if badge is not None:
            badge.set_badge(payload)

    def set_visit_curve_hooks(self, load, clear):
        # The visit's curve, through the project (D): the Measure tab draws
        # what the visit already has and can discard it. Setting them asks
        # the tab to load, so the curve is there the moment the visit opens.
        # @args: load - callable() -> [point dicts] or None,
        #        clear - callable() -> (runs, points) or None
        # @return: None
        hook = getattr(self.tab_measure, "set_visit_curve_hooks", None)
        if callable(hook):
            hook(load, clear)

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
        vp.btn_solve_visit.clicked.connect(self._on_solve_visit)
        # the .ui owns the wording; the disabled case needs its own reason
        self._visit_solve_tip = vp.btn_solve_visit.toolTip()
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
        self._sync_visit_solve()

    def _visit_running(self):
        # @return: True while the visit's batch is solving frames
        worker = getattr(self, "_visit_worker", None)
        return worker is not None and worker.isRunning()

    def _sync_visit_solve(self):
        # The visit's own button: it needs frames and the write option. A
        # batch that leaves 35 solutions in memory only would die with the
        # session, so with solve_save off the button says WHY instead of
        # doing a useless job (the observer's own decision, ADR-051).
        # @return: None
        btn = getattr(self.visit_panel, "btn_solve_visit", None)
        if btn is None:
            return
        from ..config import config
        frames = bool(self._visit_paths())
        saving = bool(config.get("solve_save", True))
        btn.setEnabled(frames and saving and not self._visit_running())
        btn.setToolTip(self._visit_solve_tip if (frames and saving) else
                       self.tr("Solving the visit writes the solution into "
                               "every frame: turn on “Save the solved WCS in "
                               "the FITS” in Settings first."))

    def _visit_pointing(self):
        # Where the visit's field is: the object the editor was opened from
        # (a project's target), or the project's own context, which the
        # visit hook carries. Either way it is in degrees, so there is no
        # ambiguity to guess about.
        # @return: (ra_deg, dec_deg) or None
        point = self._pointing()
        if point:
            return point
        ctx = (self.series_context() or {}).get("context") or {}
        ra, dec = ctx.get("ra_deg"), ctx.get("dec_deg")
        try:
            if ra is None or dec is None:
                return None
            return (float(ra), float(dec))
        except (TypeError, ValueError):
            return None

    def _on_solve_visit(self):
        # Solve every frame of the visit (ADR-051). A visit is one field, so
        # the project's coordinates point the solver at it: measured, 0.13 s
        # per frame against 66 s of sky sweep. Without coordinates the first
        # frame is solved blind and the rest follow its field (a minute once
        # instead of an hour), which is said before starting.
        # @return: None
        paths = list(self._visit_paths())
        if not paths:
            self.set_status(self.tr(
                "This editor was not opened from a visit: there are no "
                "frames to solve."))
            return
        if self._visit_running():
            return
        from ..config import config
        if not bool(config.get("solve_save", True)):
            self.set_status(self.tr(
                "Solving the visit writes the solution into every frame: "
                "turn on “Save the solved WCS in the FITS” in Settings "
                "first."))
            return
        pointing = self._visit_pointing()
        if pointing is None:
            self.set_status(self.tr(
                "This project has no coordinates: the first frame will be "
                "solved blind and the rest will follow its field."))
        else:
            self.set_status(self.tr(
                "Solving the visit's {0} frames…").format(len(paths)))
        from .workers import VisitSolveWorker
        self._visit_worker = VisitSolveWorker(
            paths, pointing=pointing, open_path=self.state.path)
        self._visit_worker.progress.connect(self._on_visit_progress)
        self._visit_worker.finished.connect(self._on_visit_solved)
        self._visit_worker.failed.connect(self._on_visit_failed)
        self._sync_visit_solve()
        self._show_visit_wait(len(paths))
        self._visit_worker.start()

    def _show_visit_wait(self, total):
        # A batch is long by nature (35 frames), so this one is shown at
        # once and with a real bar: how many are done, which one is running
        # and a Cancel that stops it.
        # @args: total - the visit's frame count
        # @return: None
        wait = QProgressDialog(self.tr("Solving the visit…"),
                               self.tr("Cancel"), 0, max(int(total), 1), self)
        wait.setWindowTitle(self.tr("NightScribe Image Workbench"))
        wait.setWindowModality(Qt.NonModal)
        wait.setMinimumDuration(0)
        wait.setAutoClose(False)
        wait.setAutoReset(False)
        wait.canceled.connect(self._cancel_visit_solve)
        wait.show()
        self._visit_wait = wait

    def _close_visit_wait(self):
        # @return: None. Closing is the batch landing, not a Cancel: the
        # signals are blocked so it does not stop what already ended.
        wait = getattr(self, "_visit_wait", None)
        if wait is not None:
            self._visit_wait = None
            wait.blockSignals(True)
            wait.close()
            wait.deleteLater()

    def _cancel_visit_solve(self):
        # @return: None. The batch stops between frames and the running one
        # is killed right away.
        worker = getattr(self, "_visit_worker", None)
        if worker is not None:
            worker.cancel()

    def _on_visit_progress(self, done, total, name):
        # @args: done - frames finished, total - the visit's count, name -
        #        the frame being solved now
        wait = getattr(self, "_visit_wait", None)
        if wait is None:
            return
        wait.setValue(int(done))
        if name:
            wait.setLabelText(self.tr("Solving frame {0} of {1}: {2}")
                              .format(done + 1, total, name[:48]))
        else:
            wait.setLabelText(self.tr("Solving the visit…"))

    def _on_visit_solved(self, out):
        # The batch's outcome in the observer's words, and the open frame's
        # WCS into the editor (it was written into the file by the worker:
        # this is the in-memory half).
        # @args: out - the worker's summary dict
        # @return: None
        self._close_visit_wait()
        self._visit_worker = None
        self._sync_visit_solve()
        out = out or {}
        if out.get("cancelled"):
            self.set_status(self.tr(
                "Solving the visit was cancelled: {0} frames solved, {1} "
                "already had a WCS.").format(out.get("solved", 0),
                                             out.get("skipped", 0)))
        else:
            text = self.tr(
                "Visit solved: {0} frames solved, {1} already had a WCS"
            ).format(out.get("solved", 0), out.get("skipped", 0))
            if out.get("failed"):
                names = ", ".join((out.get("failures") or [])[:3])
                text += self.tr(", {0} failed ({1})").format(out["failed"],
                                                             names)
            if out.get("not_written"):
                text += self.tr(", {0} could not be written into the file"
                                ).format(out["not_written"])
            self.set_status(text)
        cards = out.get("cards")
        if cards and self.state.set_wcs_cards(cards):
            self._drain_wcs_pending()

    def _on_visit_failed(self, message):
        # @args: message - the worker's error text (English, for the log)
        # @return: None
        self._close_visit_wait()
        self._visit_worker = None
        self._sync_visit_solve()
        logger.warning("visit solve failed: %s", message)
        self.set_status(self.tr("The visit could not be solved: {0}").format(
            message), "error")

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
        # the plate's band reads the object through its provider: a
        # repaint is all it takes (ADR-046 rev.)
        self.view.viewport().update()
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

    def _chart_band(self):
        # The view's band provider (ADR-046 rev.): assembles what the plate
        # says about itself from the live state, following
        # core/chart_annotate's rules (the object's name always; the
        # position placed by the plate's own solution, marked as the
        # catalogue's when there is none; the magnitude only when it was
        # measured HERE, and coloured by its own numbers; the frame's date,
        # exposure, filter and kit; the station; the scale and the field of
        # what is shown, which need the solution).
        # @return: the band dict ({"lines": []} when nothing can be said)
        from ..config import config
        from ..core import chart_annotate, fits_meta
        if not self.state.has_image:
            return {"lines": []}
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
        # WHAT HAS BEEN MEASURED ON THIS PLATE, in the order that tells the
        # truth: the visit's curve for THIS frame (the normal flow: a series
        # is measured, not one plate), then a single-plate measurement of
        # this plate, and only then the catalogue (which is not a
        # measurement and wears white). The caveats travel with it: they are
        # what decides between green, orange and red.
        measured = None
        point = None
        ask = getattr(self.tab_measure, "series_point_for", None)
        if callable(ask):
            meta_ = fits_meta.meta_from_header(self.state.header or {})
            point = ask(self.state.path, meta_.get("mjd"),
                        meta_.get("exptime_s"))
        if point is not None:
            measured = {"mag": point["mag"], "err": point.get("err"),
                        "band": point.get("filter"),
                        "comps": point.get("comps"),
                        "flags": point.get("flags")}
        else:
            last = self.tab_measure._last
            if last is not None and last.get("mag") is not None:
                check = last.get("check")
                measured = {"mag": last["mag"], "err": last.get("err"),
                            "band": last.get("band"),
                            "comps": len(last.get("used") or []) or None,
                            "check_ok": (check or {}).get("ok")
                            if check else None,
                            "no_check": check is None,
                            "clipped": bool(
                                (last.get("result") or {}).get("saturated")),
                            "derived": bool(last.get("derived"))}
        catalog_mag = None
        try:
            if obj.get("mag") is not None:
                catalog_mag = float(obj["mag"])
        except (TypeError, ValueError):
            catalog_mag = None
        target = None
        if obj.get("ra") is not None and obj.get("dec") is not None:
            try:
                target = (float(obj["ra"]), float(obj["dec"]))
            except (TypeError, ValueError):
                target = None
        return chart_annotate.build_band(
            name=name, meta=meta, wcs_info=wcs_info, measured=measured,
            catalog_mag=catalog_mag, target=target,
            equipment=chart_annotate.equipment_from_header(
                self.state.header or {}, config),
            site=chart_annotate.site_from_config(config))

    def set_status(self, text, level="info"):
        # The window's ONE line of status (U4).
        #
        # The messages used to live in each tab, in labels of their own
        # that wrapped and grew: the same kind of news in four places, and
        # none of them where an observer looks. There is one line now, at
        # the bottom, fixed in height, with a glyph for the level and the
        # whole text in the tooltip (it is ELIDED, never wrapped: a message
        # that eats the plate's height costs more than it says).
        # @args: text - the message, level - "info" | "warn" | "error"
        # @return: None
        from ..viz import palette as viz_palette
        self._status_text = str(text or "")
        self._status_level = level if level in ("info", "warn", "error") \
            else "info"
        glyph = _STATUS_GLYPH[self._status_level]
        self._status_glyph = glyph
        bar = self._ui.lbl_status_bar
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if getattr(self, "_status_shown", None) != self._status_level:
            # a stylesheet forces a full re-layout: set it when the LEVEL
            # changes, never on every message
            # a compact line on purpose: at the window's own font size the
            # status bar measured 25 px and took them from the plate, which
            # is the whole point of U1. 12 px is the same size the chart's
            # ticks use, and it is a footnote, not a headline.
            colour = {"info": theme.C_TEXT_DIM, "warn": "#e0c060",
                      "error": viz_palette.DANGER}[self._status_level]
            bar.setStyleSheet(f"color: {colour}; font-size: 12px;")
            self._status_shown = self._status_level
        self._elide_status()

    def _elide_status(self):
        # Fits the message to the line, never to the layout: the elided
        # text is written only when it CHANGES, and the whole routine is
        # guarded against re-entrance, because a label that changes its
        # text re-lays the window out and can call us back from the resize
        # (an unguarded version of this looped until the process was
        # killed by memory).
        # @return: None
        if getattr(self, "_status_eliding", False):
            return
        bar = self._ui.lbl_status_bar
        text = getattr(self, "_status_text", "")
        if not text:
            if bar.text():
                bar.setText("")
            bar.setToolTip("")
            return
        self._status_eliding = True
        try:
            fm = QFontMetrics(bar.font())
            room = max(120, bar.width() - 12)
            elided = fm.elidedText(
                f"{getattr(self, '_status_glyph', 'ⓘ')} {text}",
                Qt.ElideRight, room)
            if bar.text() != elided:
                bar.setText(elided)
            bar.setToolTip(text)
        finally:
            self._status_eliding = False

    def status_text(self):
        # @return: the status line's whole text ("" when silent)
        return getattr(self, "_status_text", "")

    def _on_status_hook(self, text, level="info"):
        # What a tab says lands here (U4): the tabs keep their own label as
        # a record (the tests and the old code read it) but they are hidden,
        # and the observer reads this line.
        # @return: None
        self.set_status(text, level)

    def resizeEvent(self, event):
        # The status line is elided to the window: a resize must re-elide
        # it or the message stays cut where the old width was. It is a
        # cheap, guarded, idempotent call (see _elide_status).
        super().resizeEvent(event)
        self._elide_status()

    def _on_histogram_fold(self, expanded):
        # The observer's choice is remembered: the strip comes back as it
        # was left (a real click only: setCollapsed stays silent).
        # @args: expanded - the new state
        # @return: None
        config.set("ufe_histogram_folded", 0 if expanded else 1)

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

    def _pointing(self):
        # Where the plate looks, when the app knows it: the object the
        # editor was opened from (a project's target, in degrees). It is
        # what decides between a tenth of a second and a minute of ASTAP
        # sweeping the sky (ADR-051), because the frames of a real visit
        # carry no position at all: the V0526 Per ones have FOCALLEN=0 and
        # no RA/DEC, while the project knows its field.
        # @return: (ra_deg, dec_deg) or None when there is nothing to say
        obj = self._object or {}
        ra, dec = obj.get("ra"), obj.get("dec")
        try:
            if ra is None or dec is None:
                return None
            return (float(ra), float(dec))
        except (TypeError, ValueError):
            return None

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
        self._solve_worker = UfeSolveWorker(Path(self.state.path),
                                            pointing=self._pointing())
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
        # a local ASTAP solve can land in a couple of hundred milliseconds,
        # and a window that appears and disappears reads as a failure: it is
        # shown only if the solve really takes a moment (the same rule the
        # sequence's busy dialog follows)
        wait._show_timer = QTimer(wait)
        wait._show_timer.setSingleShot(True)
        wait._show_timer.timeout.connect(wait.show)
        wait._show_timer.start(_SOLVE_SHOW_MS)
        self._solve_wait = wait

    def _close_solve_wait(self):
        wait = getattr(self, "_solve_wait", None)
        if wait is not None:
            timer = getattr(wait, "_show_timer", None)
            if timer is not None:
                timer.stop()
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
        # @args: stage - the worker's stage text: a key of the solver's own
        #        vocabulary ("astap:blind", "login"…) or a line of the
        #        solver's output (its verdict and its warnings, which are
        #        shown as they come)
        stage = (stage or "").strip()
        # the solver's keys are its own vocabulary: the ASTAP ones carry
        # their prefix ("astap:blind"), the nova ones are single words
        key = stage if stage.startswith("astap:") else stage.split(" ")[0]
        text = self._solve_stage_text(key)
        if text is None:
            text = stage[:70] if stage else self.tr("Solving the plate…")
        else:
            text = self.tr("Solving: {0}…").format(text)
        self.btn_solve.setText(text)
        wait = getattr(self, "_solve_wait", None)
        if wait is not None:
            wait.setLabelText(text)

    def _solve_stage_text(self, key):
        # The solver's stages in the observer's words. The raw output used
        # to be poured into this line ("Search 75939, [99,138]…"), which is
        # a wall of noise and made a solve that was WORKING look like a
        # loop (reported); the solver's warnings still come through, but
        # they are its own words and are shown as they are.
        # @args: key - the stage key the solver sent
        # @return: the translated stage, or None when it is not one of ours
        return {
            "login": self.tr("signing in to Astrometry.net"),
            "upload": self.tr("uploading the plate"),
            "solving": self.tr("Astrometry.net is solving"),
            "astap:pointed": self.tr("ASTAP is solving at the project's "
                                     "field"),
            "astap:solving": self.tr("ASTAP is solving"),
            "astap:blind": self.tr("this plate carries no position, so ASTAP "
                                   "is sweeping the sky (this can take a "
                                   "minute)"),
        }.get(key)

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
            msg = self.tr("{0} could not solve the plate. Check the solver "
                          "in Settings (ASTAP path, Astrometry.net key) or "
                          "solve the plate with NINA, Ekos or PixInsight "
                          "and save it again.").format(self._solver_names())
            if self._pointing() is None:
                # the honest reason it may have taken a minute: nothing told
                # the solver where to look, so it searched the whole sky
                msg += "\n\n" + self.tr(
                    "This plate carries no position of its own and the "
                    "editor was not opened from a project, so the solver "
                    "had to search the whole sky. Opening it from its "
                    "project tells it where the field is, and the solve "
                    "takes a moment.")
            QMessageBox.warning(self, self.tr("NightScribe Image Workbench"),
                                msg)
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
