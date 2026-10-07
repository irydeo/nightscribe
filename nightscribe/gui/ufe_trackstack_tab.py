############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unified FITS Editor: Track & Stack tab module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Track & Stack tab (astrometry plan, phase 7): the visit's sequence
becomes MPC observations. The structure, texts and tooltips live in
ui/ufe_trackstack_tab.ui (ADR-005); this module wires the signals, fills
the tables and runs the pipeline through gui/workers.TrackStackWorker.

The flow, top to bottom: how many observations the user wants (with the
expected SNR per group recalculated on every change, D22), the stacking
run with progress and Cancel, the group's stack in this tab's OWN viewer
(the dialog's plate is never touched), the measurement with its two ways
and the disagreement flag (D7/D16), the Find_Orb check with its verdict
(D25/D29) and the report that lands in the visit's MPC block, where the
ADR-022 validator has the last word.
"""

import logging
import math
import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (QFrame, QScrollArea, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ..config import config
from . import theme
from .ufe_state import UfeImageState
from .ufe_host import host_of
from .ui_loader import adopt_ui, drop_in
from .widgets.ufe_image_view import (UfeImageView, cross_marker_items,
                                     mark_cross_items)
from ..viz import palette
from .widgets.stack_strip import StackStrip
from ..core import photometry, track_stack
from .widgets.collapsible_section import CollapsibleSection
from .widgets.hero_fit import install_hero_fit, set_hero_text
from .widgets.kind_glyph import kind_glyph_pixmap

logger = logging.getLogger("nightscribe.gui.ufe_trackstack_tab")

# The observation number inside a stack's file name ("2026PY9_obs2_....fits"):
# the restore matches a saved stack to its observation with this, so the
# order of the visit's file list cannot put observation 2 in slot 1.
_OBS_RE = re.compile(r"_obs(\d+)")


class UfeTrackStackTab(QWidget):
    # @args: state - the shared UfeImageState (the group's stack is loaded
    #        into it, so the histogram, stretch and marks work on it),
    #        lang - "es" | "en", view - the shared UfeImageView (the
    #        measured position is marked on it; None builds a private
    #        fallback, which is what the tests use), parent - widget

    def __init__(self, state, lang="es", view=None, parent=None):
        super().__init__(parent)
        self._state = state
        self._lang = lang
        self._view = view
        self._worker = None        # TrackStackWorker while it runs
        self._frames = None        # list[Frame] of the open visit
                                   # (headers only: no pixels live here)
        self._ctx_paths = None     # the paths _frames was loaded from
        self._base_snr = None      # SNR of the whole-sequence stack (the
                                   # first run turns the expected-SNR
                                   # column into a real projection, D22)
        self._result = None        # the last run's payload
        self._run_id = None        # its row in astrometry_runs (the Undo)
        self._hue = theme.C_ACCENT  # the object's hue (the hero button)
        self._accent = None        # {"hue", "kind", "label"} or None
        self._build_ui()
        self._sync_context()
        self.refresh_accent()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # The structure is the Designer file's (ADR-005); this method
        # aliases the widgets, fills the combos (labels through literal
        # tr() so lupdate sees them) and wires every signal.
        self._ui = adopt_ui(self, "ufe_trackstack_tab")
        self.lbl_object = self._ui.lbl_object
        self.spn_nobs = self._ui.spn_nobs
        self.lbl_snr_line = self._ui.lbl_snr_line
        self.lbl_plan_line = self._ui.lbl_plan_line
        self.tbl_snr = self._ui.tbl_snr
        self.cmb_method = self._ui.cmb_method
        self.cmb_warp_order = self._ui.cmb_warp_order
        self.btn_stack = self._ui.btn_stack
        self.prg_stack = self._ui.prg_stack
        self.lbl_status = self._ui.lbl_status
        self.txt_notes = self._ui.txt_notes
        self.cmb_group = self._ui.cmb_group
        self.tbl_points = self._ui.tbl_points
        # The headers are short because the column is 380 px wide: the long
        # name travels in the tooltip, where there is room for it.
        for col, tip in enumerate((
                self.tr("Which observation"),
                self.tr("Middle-of-exposure instant (UT)"),
                self.tr("Right ascension, from the stack's own centroid"),
                self.tr("Declination, from the stack's own centroid"),
                self.tr("Separation between the two measurements (″)"),
                self.tr("Signal-to-noise of the measured point"),
                self.tr("Calibrated magnitude"),
                self.tr("Warnings and flags of the point"))):
            header = self.tbl_points.horizontalHeaderItem(col)
            if header is not None:
                header.setToolTip(tip)
        self.txt_check = self._ui.txt_check
        self.chk_force = self._ui.chk_force
        self.cmb_format = self._ui.cmb_format
        self.btn_report = self._ui.btn_report
        self.btn_send_mpc = self._ui.btn_send_mpc
        self.btn_undo = self._ui.btn_undo
        self.txt_report = self._ui.txt_report
        self.lbl_report_note = self._ui.lbl_report_note
        self._report_kept = None      # observations the last report carried
        # The group's stack is shown in the MAIN stage (the shared state),
        # so the histogram, the stretch and the marks work on it and the
        # other tabs can operate on top. The private viewer is only a
        # fallback for a host that gave no view (the tests).
        if self._view is None:
            self._stack_state = UfeImageState(self)
            self._stack_view = UfeImageView(self._stack_state)
            self._drop_view(self._ui.ph_stack_view, self._stack_view)
        else:
            self._stack_state = None
            self._stack_view = None
            placeholder = getattr(self._ui, "ph_stack_view", None)
            if placeholder is not None:
                placeholder.hide()
        # the strip of observation stacks: the same evidence the combo
        # lists, but visible and comparable at a glance, all at ONE
        # stretch (auto-stretching each panel would fake a faint one)
        self._thumbs = StackStrip()
        self._drop_view(self._ui.ph_thumbs, self._thumbs)
        self._thumbs.picked.connect(self._show_group)
        # the result area (the strip, the points table) starts HIDDEN: an
        # empty grid and a blank strip say nothing, and in a 380 px column
        # they are noise. It appears with the result and goes with it.
        self.lbl_points_title = self._ui.lbl_points_title
        self._thumbs.setVisible(False)
        self.btn_blink = self._ui.btn_blink
        self.btn_blink.clicked.connect(self._on_blink)
        # the brightness is measured with the recipe the Fotometria tab is
        # holding: one editor in the app, read live, shown before the run
        self.chk_brightness = self._ui.chk_brightness
        self.chk_starstack = self._ui.chk_starstack
        # ADR-061 where the faint object is: applying the calibration to the
        # stack is OPTIONAL, and the DEFAULT follows the library: with a dark
        # or a flat that matches this visit's camera and filter, applying it
        # is what the measurement needs (measured on a real visit: the smooth
        # vignetting alone was worth 0.087 mag of systematic error). The
        # stored key is therefore three-state: absent = automatic, 0/1 = what
        # the observer chose. The recipe, the library and the pseudo-flat
        # policy are NOT here: they live in the Calibration tab, their single
        # home, and this tab only decides whether to apply them.
        self.chk_calibrate = self._ui.chk_calibrate
        self.chk_calibrate.setChecked(bool(config.get("calib_astrometry",
                                                      False)))
        self.chk_calibrate.toggled.connect(self._on_calibrate_toggled)
        self.btn_calibration = self._ui.btn_calibration
        self.btn_calibration.clicked.connect(self._on_calibration_settings)
        self.lbl_calibration_hint = self._ui.lbl_calibration_hint
        self._sync_calibration_hint()
        self.lbl_recipe = self._ui.lbl_recipe
        self.btn_recipe = self._ui.btn_recipe
        self.btn_recipe.clicked.connect(self._on_edit_recipe)
        self.chk_brightness.toggled.connect(lambda _on: self._sync_recipe_row())
        self._sync_recipe_row()
        # ADR-038: three levels of prominence. What the observer SEES on
        # entering is the object, the ONE action of the panel (the hero
        # button, painted in the object's hue) and a line saying what that
        # action will do with the current defaults. Every knob lives in a
        # collapsible block, ALL OF THEM CLOSED, whose title says what it
        # holds; the occasional ACTIONS go behind ⋯. The widgets keep their
        # names, their tooltips and their slots: only their container
        # changes.
        self.btn_more = self._ui.btn_more
        self._sections = {
            # --- the DECISIONS: always there, closed -------------------
            "plan": self._wrap_section(
                "sec_plan_content", self.tr("How many observations"),
                "trackstack_plan_open"),
            "advanced": self._wrap_section(
                "sec_advanced_content", self.tr("Stacking settings"),
                # a FRESH key on purpose, in the other direction this time:
                # the block opened by default in the previous design, and a
                # stored "open" would keep it open against the new rule
                "trackstack_settings_open2"),
            # --- the RESULT: appears with the run, CLOSED --------------
            # Everything the run produces lives in a group too (asked for:
            # nothing outside a group), and EVERY group is closed by default
            # (asked for 2026-10-06): the observer opens what they want to
            # read, and a group that holds news SAYS SO with a notice on its
            # header (setNotice: a chip with the news and, for a warning,
            # the title in the alert colour). The keys are fresh because the
            # previous design opened these by default: a stored "open"
            # would keep them open against the new rule.
            "notes": self._wrap_section(
                "sec_notes_content", self.tr("What the run found"),
                "trackstack_notes_open2"),
            "view": self._wrap_section(
                "sec_view_content", self.tr("The observations"),
                "trackstack_view_open2"),
            "points": self._wrap_section(
                "sec_points_content", self.tr("Measurement per observation"),
                "trackstack_points_open2"),
            "manual": self._wrap_section(
                "chk_manual", self.tr("Manual mark"),
                "trackstack_manual_open2"),
            "check": self._wrap_section(
                "sec_check_content",
                self.tr("Check against other observers"),
                "trackstack_check_open3"),
            # The report is a RESULT whose text only exists when it is
            # generated, so it appears with the run and stays closed until
            # there is something to read in it.
            "report": self._wrap_section(
                "grp_report", self.tr("Report"), "trackstack_report_open"),
        }
        self._check_section = self._sections["check"]
        # MANUAL MODE (faint object): the tab keeps only the checkbox; the
        # message, the Show button, the arrows and the Measure button live in
        # their own small non-modal window (UfeManualStackDialog), shown
        # while the box is checked, the way the Photometry tab does with its
        # manual centre.
        from .ufe_manual_stack_dialog import UfeManualStackDialog
        self._manual = UfeManualStackDialog(self)
        self.chk_manual = self._ui.chk_manual
        self.lbl_manual_mark = self._manual.lbl_manual_mark
        self.btn_manual_show = self._manual.btn_manual_show
        self.btn_manual_measure = self._manual.btn_manual_measure
        self.lbl_nudge = self._manual.lbl_nudge
        self._nudge = [0.0, 0.0]
        self._manual_base = None       # the snapped centroid, base-stack px
        self._manual_armed = False     # the next click marks the object
        self._shown_group = None      # the observation whose stack is on stage
        self._shown_stack_path = None  # its file, to tell the plate apart
        self._restore_asked = False   # the visit's saved run was looked for
        self._n_unreadable = 0        # frames of the visit that could not be read
        self._status_hook = None      # the window's single line (U4)
        self._base_saved = False      # the whole-sequence stack went to disk
        self.btn_manual_show.clicked.connect(self._on_manual_show)
        self.btn_manual_measure.clicked.connect(self._on_manual_measure)
        self._manual.btn_left.clicked.connect(
            lambda: self._nudge_step(-0.1, 0.0))
        self._manual.btn_right.clicked.connect(
            lambda: self._nudge_step(0.1, 0.0))
        self._manual.btn_up.clicked.connect(
            lambda: self._nudge_step(0.0, 0.1))
        self._manual.btn_down.clicked.connect(
            lambda: self._nudge_step(0.0, -0.1))
        self._manual.btn_nudge_reset.clicked.connect(self._reset_nudge)
        self._manual.chk_show_cross.toggled.connect(
            lambda _on: self._draw_marks())
        # closing the window (its X) is the same as unchecking the box
        self._manual.rejected.connect(
            lambda: self.chk_manual.setChecked(False))
        self.chk_manual.toggled.connect(self._sync_manual_dialog)
        # the mark is a CLICK on the shared stage: same signal the Measure
        # and Annotate tabs use
        mark_view = self._view if self._view is not None else self._stack_view
        if mark_view is not None:
            mark_view.scene_clicked.connect(self._on_manual_click)
        # the measured cross is anchored to the SKY, so a new plate of the
        # visit (or a solve) has to place it again: the tab repaints it on
        # every load, like the Photometry tab repaints its measurement
        mark_state = self._state if self._view is not None else self._stack_state
        if mark_state is not None:
            mark_state.image_loaded.connect(self._draw_marks)
        # the manual window follows the stage: leaving the tab hides it
        # without unchecking the box, so coming back shows it again
        self._sync_manual_dialog(self.chk_manual.isChecked())
        from .widgets.door_menu import build_door
        build_door(self.btn_more, [self.btn_blink, self.btn_undo])
        # before a run this column is the PLAN: the result arrives whole or
        # not at all, and a check with no run is a paragraph about nothing
        self._show_result_area(False)
        self._make_scrollable()

    def _drop_view(self, placeholder, widget):
        # @args: placeholder - the .ui marker widget, widget - the real one
        # @return: None. The placeholder's OWN layout is used: since the
        #          result lives in groups (ADR-038 rev) the viewer's and the
        #          strip's markers sit inside a container, not in the tab's
        #          top layout, and replacing them in the wrong layout left
        #          the real widget parentless (silently: QLayout.replaceWidget
        #          just returns None when the placeholder is not there).
        parent = placeholder.parentWidget()
        layout = parent.layout() if parent is not None else self.layout()
        drop_in(layout, placeholder, widget)

    def _make_scrollable(self):
        # The column is taller than the panel on a laptop, and a label that
        # cannot be read is a label that does not exist: the content goes
        # into a scroll area, the way the Photometry tab's forms already do.
        # Every item moves into an inner widget (a layout does NOT drop its
        # item by itself, so they are taken out one by one) and the scroll
        # area takes the tab's only slot.
        inner = QWidget(self)
        box = QVBoxLayout(inner)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        lay = self.layout()
        while lay.count():
            item = lay.takeAt(0)
            widget = item.widget()
            if widget is not None:
                box.addWidget(widget)      # reparents it into the inner
                continue
            nested = item.layout()
            if nested is not None:
                # A ROW: addLayout (NOT addItem) is what reparents its
                # widgets into the inner widget. addItem moves the layout
                # alone and leaves the widgets as children of the tab,
                # where the scroll area's viewport paints OVER them: the
                # row went missing and the column looked empty exactly
                # where it should have been.
                box.addLayout(nested)
                continue
            # A SPACER: the trailing one collects the extra space at the
            # bottom. Dropping it handed that space to whatever could
            # grow, and the observations row came out 141 px tall in a
            # tall window, pushing the Stack button out of sight.
            box.addItem(item)
        area = QScrollArea(self)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(inner)
        lay.addWidget(area)
        # the combination methods of core/track_stack (D11), with the
        # setting's default on top
        self.cmb_method.addItem(self.tr("Sum"), "sum")
        self.cmb_method.addItem(self.tr("Mean"), "mean")
        self.cmb_method.addItem(self.tr("Median"), "median")
        self.cmb_method.addItem(self.tr("Sigma-clipped"), "sigma")
        # P1: the same clip, and then each frame counts by 1/sigma^2 of its
        # own sky. On a stable night it is the same as the sigma clip; on a
        # night with thin cloud or moon it is what keeps one bad frame from
        # dragging the stack, and it is the noise model the matched filter
        # will stand on.
        self.cmb_method.addItem(self.tr("Weighted (1/σ²)"), "weighted")
        self.cmb_method.setItemData(
            self.cmb_method.count() - 1,
            self.tr("Each frame counts by 1/σ² of its own sky: the same as "
                    "the sigma clip on a stable night, and what saves a "
                    "night with thin cloud or moon"), Qt.ToolTipRole)
        # D11: the FINAL stack's field (0 = the whole frame) and the
        # detection/sweep cutout's margin. The whole frame is what the
        # photometry wants; a smaller window is faster.
        self.cmb_final_size = self._ui.cmb_final_size
        self.spn_margin = self._ui.spn_margin
        self.cmb_final_size.addItem(self.tr("Whole frame"), 0)
        self.cmb_final_size.addItem(self.tr("1024 px"), 1024)
        self.cmb_final_size.addItem(self.tr("512 px"), 512)
        self.cmb_final_size.addItem(self.tr("256 px"), 256)
        self.cmb_final_size.setCurrentIndex(0)
        _mi = self.cmb_method.findData(
            config.get("astrometry_method", "sigma"))
        self.cmb_method.setCurrentIndex(_mi if _mi >= 0 else 3)
        # THE RESAMPLING (2026-10-07): the warp's interpolation order, and it
        # is a knob for the EYE, not for the limit. Measured on the 2025 FG18
        # visit: orders 1 and 3 tie in depth (magnitude 18.20 against 18.21 by
        # injection and recovery) while the pixel noise differs by 29 %, so the
        # bilinear is the default because the image looks cleaner at no cost.
        self.cmb_warp_order.addItem(self.tr("Bilinear (cleaner)"), 1)
        self.cmb_warp_order.addItem(self.tr("Cubic (sharper)"), 3)
        self.cmb_warp_order.addItem(self.tr("Quintic (sharpest)"), 5)
        _wo = self.cmb_warp_order.findData(
            config.get("astrometry_warp_order", track_stack.WARP_ORDER))
        self.cmb_warp_order.setCurrentIndex(_wo if _wo >= 0 else 0)
        # BOTH choices are PERSISTED (2026-10-07). They used to be read from
        # the settings and never written back, so a run combined with the
        # median left no trace: that is exactly how an afternoon went into
        # telling two stacks of the same frames apart. What the observer picks
        # is what the next visit starts with.
        self.cmb_method.currentIndexChanged.connect(
            lambda _i: config.set("astrometry_method",
                                  self.cmb_method.currentData() or "sigma"))
        self.cmb_warp_order.currentIndexChanged.connect(
            lambda _i: config.set("astrometry_warp_order",
                                  int(self.cmb_warp_order.currentData() or 1)))
        self.cmb_format.addItem(self.tr("ADES PSV"), "ades")
        self.cmb_format.addItem(self.tr("MPC 80 columns"), "mpc80")
        self._btn_stack_label = self.btn_stack.text()
        # the hero fits the width the panel really has: a 380 px column can
        # be dragged down to 280 and the label used to run over the button's
        # own edges (asked for 2026-10-06)
        install_hero_fit(self.btn_stack)
        self.spn_nobs.valueChanged.connect(lambda _v: self._refresh_preview())
        self.btn_stack.clicked.connect(self._on_stack)
        self.cmb_group.currentIndexChanged.connect(self._show_group)
        self.chk_force.toggled.connect(lambda _on: self._sync_report_buttons())
        self.btn_report.clicked.connect(self._on_report)
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_send_mpc.clicked.connect(self._on_send_mpc)
        self._sync_report_buttons()

    def _show_result_area(self, flag):
        # @args: flag - True when there is a result to show
        # @return: None. What belongs to the RESULT appears with a run and
        #          goes away with it: the notes, the observations (the strip,
        #          the viewer and the row that chooses which stack to look
        #          at), the measurement table with the manual door, the check
        #          (a verdict that does not exist yet is a paragraph about
        #          nothing) and the report. Each of them is a GROUP like any
        #          other (asked for: nothing outside a group), and the
        #          widgets inside keep their own visibility rules.
        for key in ("notes", "view", "points", "manual", "check", "report"):
            self._sections[key].setVisible(flag)
        # THE WIDGETS INSIDE THOSE GROUPS. The refactor to collapsible
        # sections dropped this and left three of them hidden for good
        # (reported 2026-10-06: "Measurement per observation" came out empty
        # and the per-observation previews were gone): the section appeared
        # with its title and nothing inside it. They are the measurement
        # table, its title and the strip of observation stacks, and they
        # belong to the result like everything else here.
        self.lbl_points_title.setVisible(flag)
        self.tbl_points.setVisible(flag)
        self._thumbs.setVisible(flag)

    def _wrap_section(self, name, title, key, open_by_default=False):
        # @args: name - the .ui container's objectName, title - the block's
        #        title in plain language (it says WHAT it holds), key - the
        #        settings key that remembers whether it stays open,
        #        open_by_default - the state before the observer chooses
        # @return: the CollapsibleSection
        # The container comes OUT of the column and INTO the block, keeping
        # every widget inside it: the Designer file still owns the
        # structure, and the block only decides whether it is shown.
        content = getattr(self._ui, name)
        section = CollapsibleSection(title, self)
        self.layout().replaceWidget(content, section)
        content.setParent(None)
        section.contentLayout().addWidget(content)
        content.setVisible(True)
        section.setAccent(self._hue)
        section.setCollapsed(
            not bool(config.get(key, 1 if open_by_default else 0)))
        section.sectionToggled.connect(
            lambda opened, k=key: config.set(k, 1 if opened else 0))
        return section

    # ----------------------------------------------------------- the panel

    def refresh_accent(self):
        # @return: None. The panel speaks in the object's hue, the same
        #          grammar the masthead's active tab already uses: the hero
        #          button, the progress bar and the block spines. With no
        #          project (an ad-hoc open from Tools) the app's own accent
        #          is used and there is no kind glyph to draw.
        ask = getattr(host_of(self), "project_accent", None)
        accent = None
        if callable(ask):
            try:
                accent = ask()
            except Exception as err:
                logger.warning("the project accent could not be read: %s", err)
        self._accent = accent
        self._hue = (accent or {}).get("hue") or theme.C_ACCENT
        self._apply_hero()
        for section in getattr(self, "_sections", {}).values():
            section.setAccent(self._hue)
        self.prg_stack.setStyleSheet(theme.progress_style(self._hue))

    def _apply_hero(self):
        # @return: None. The ONE action of the panel, in the object's hue,
        #          carrying the kind's glyph. The glyph is drawn in the
        #          button's own text colour: on a surface of the kind's hue
        #          the glyph's hue would vanish (measured: every kind hue
        #          takes the dark text, chip_text_for).
        self.btn_stack.setStyleSheet(theme.hero_button_style(self._hue))
        kind = (self._accent or {}).get("kind")
        if kind:
            colour = theme.chip_text_for(self._hue)
            self.btn_stack.setIcon(
                QIcon(kind_glyph_pixmap(kind, 22, color=colour)))
            self.btn_stack.setIconSize(QSize(22, 22))
        else:
            self.btn_stack.setIcon(QIcon())

    # ------------------------------------------------------- host wiring

    def set_active(self, flag):
        # @args: flag - True when the dialog hands this tab the stage
        # @return: None. The context is re-read on entering: the visit may
        #          have been armed (or changed) while the tab was hidden;
        #          on leaving, the manual window goes but the MARKS stay: the
        #          measured cross is anchored to the sky and belongs to the
        #          result, not to the tab being on stage (reported: it used
        #          to be dropped here and never repainted).
        if flag:
            self._sync_context()
            self._sync_recipe_row()
            # the object's hue may have arrived after this tab was armed
            # (the badge is the last hook the host sets): repaint with it
            self.refresh_accent()
            # the manual window follows the stage: back on it, the box still
            # checked means the window is shown again (like the Photometry
            # tab's manual centre)
            self._sync_manual_dialog(self.chk_manual.isChecked())
            # The plate may have been cleared while the result stayed in
            # memory (a session change drops the plate, not the run): the
            # observation on stage is shown again, so the marks are not left
            # floating over nothing.
            st = self._state if self._view is not None else self._stack_state
            if self._result is not None and st is not None \
                    and not st.has_image and self._shown_group is not None:
                self._show_group(self._shown_group)
            self._draw_marks()
        else:
            self._manual.setVisible(False)

    def refresh_context(self):
        # Called by the dialog when the host sets (or clears) the
        # astrometry hook, so the tab does not wait for a stage change.
        # @return: None
        self._sync_context()

    def shutdown(self):
        # The pipeline worker must not outlive the workbench: a QThread
        # destroyed while it runs aborts the whole application (the trap
        # every other tab documents). Cancel stops it at the next stage
        # boundary and wait() gives it a bounded time to land.
        # @return: None
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)
        self._worker = None

    def _context(self):
        # @return: the visit context {"pid", "session_id", "paths",
        #          "object_name"} the host hooked, or None (ad-hoc open:
        #          without a visit there is no sequence, D15)
        dlg = host_of(self)
        getter = getattr(dlg, "astrometry_context", None)
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception as err:
            logger.warning("astrometry hook failed: %s", err)
            return None

    def _recipe(self):
        # @return: the photometry recipe the Fotometria tab is holding right
        #          now (band, apertures, sky method, centroid, colour term),
        #          or None when there is no host to ask
        # There is deliberately NO second copy of the recipe: the tab that
        # has always edited it is the only editor, so the apertures the
        # brightness is measured with cannot drift away from the ones the
        # observer sees.
        ask = getattr(host_of(self), "photometry_recipe", None)
        if not callable(ask):
            return None
        try:
            return ask()
        except Exception as err:
            logger.warning("photometry recipe hook failed: %s", err)
            return None

    def _on_edit_recipe(self):
        # @return: None. The recipe is edited in the Photometry tab: this is
        #          the deep link to it, nothing more.
        show = getattr(host_of(self), "show_tab", None)
        if callable(show):
            show("measure")

    # ------------------------------------------------------- calibration

    def _on_calibrate_toggled(self, on):
        # @args: on - the new state of "apply the calibration to the stack"
        # @return: None. The choice is saved (it used to reset on every
        #          rebuild) and the hint follows it. Saving it is also what
        #          turns the AUTOMATIC default off for good: from here on the
        #          checkbox is the observer's, not the library's.
        config.set("calib_astrometry", 1 if on else 0)
        self._sync_calibration_hint()

    def _auto_calibrate(self):
        # @return: None. The calibration's DEFAULT follows the library: with
        #          a dark or a flat that matches this visit's camera and
        #          filter, applying it is what the measurement needs (0.087
        #          mag of smooth vignetting, measured). The stored key is
        #          three-state: absent means nobody has chosen yet, so the
        #          library decides; 0/1 is the observer's own choice and is
        #          never overridden.
        if config.get("calib_astrometry", None) is not None:
            return
        ask = getattr(host_of(self), "calibration_masters", None)
        has = None
        if callable(ask):
            try:
                has = ask()
            except Exception as err:
                logger.warning("the calibration masters could not be read: %s",
                               err)
        # an unknown answer leaves it OFF: turning it on without knowing
        # would promise a calibration nobody verified
        self.chk_calibrate.blockSignals(True)
        self.chk_calibrate.setChecked(bool(has))
        self.chk_calibrate.blockSignals(False)
        self._sync_calibration_hint()

    def _on_calibration_settings(self):
        # @return: None. The recipe, the library and the pseudo-flat policy
        #          are edited in the Calibration tab: this is the deep link,
        #          like the one the photometry recipe has.
        show = getattr(host_of(self), "show_tab", None)
        if callable(show):
            show("calibration")

    def _sync_calibration_hint(self):
        # @return: None. One line saying what will happen to the pixels
        #          BEFORE running: without it the vignetting's fate was
        #          hidden in another tab. The recipe itself is NOT resolved
        #          here: the Calibration tab owns it, and the host hands its
        #          one-liner over, so the two cannot disagree.
        if not self.chk_calibrate.isChecked():
            text = self.tr(
                "The calibration is not applied: the train's dust and the "
                "sensor's vignetting stay in the frames.")
        else:
            ask = getattr(host_of(self), "calibration_summary", None)
            summary = None
            if callable(ask):
                try:
                    summary = ask()
                except Exception as err:
                    logger.warning("calibration summary failed: %s", err)
            text = self.tr("Applied to the stack: %1").replace(
                "%1", summary or self.tr("the recipe of the Calibration tab"))
        self._set_wrapped(self.lbl_calibration_hint, text)
        self._sync_plan_line()

    def _sync_plan_line(self):
        # @return: None. The subtitle of the hero button: what the run will
        #          DO with the current values, in one line, built from the
        #          same sources the blocks show (so it cannot disagree with
        #          them). It is what makes hiding every knob safe: the
        #          observer knows what is about to happen without opening
        #          anything (ADR-038, the app speaks first).
        ctx = self._context() or {}
        if not (ctx.get("paths") or ()):
            self._set_wrapped(self.lbl_plan_line, "")
            return
        parts = []
        n = len(self._frames or [])
        if n:
            parts.append(self.tr("%1 frames").replace("%1", str(n)))
        n_obs = max(1, self.spn_nobs.value())
        parts.append((self.tr("%1 observation") if n_obs == 1
                      else self.tr("%1 observations")).replace(
                          "%1", str(n_obs)))
        recipe = self._recipe() or {}
        if not self.chk_brightness.isChecked():
            parts.append(self.tr("positions only"))
        else:
            band = recipe.get("band")
            radii = self._recipe_radii_text(recipe)
            if band:
                parts.append(self.tr("brightness with %1").replace(
                    "%1", f"{band} · {radii}"))
            elif recipe.get("seeing") and not recipe.get("radii_manual"):
                # the radii are not a number here: they follow the measured
                # FWHM, so the phrase has to read as a choice
                parts.append(self.tr("brightness from the seeing"))
            else:
                parts.append(self.tr("brightness with %1").replace(
                    "%1", radii))
        if self.chk_calibrate.isChecked():
            ask = getattr(host_of(self), "calibration_summary", None)
            summary = None
            if callable(ask):
                try:
                    summary = ask()
                except Exception:
                    summary = None
            parts.append(self.tr("calibration: %1").replace(
                "%1", summary or self.tr("on")))
        else:
            parts.append(self.tr("no calibration"))
        if bool(config.get("astrometry_check_enabled", True)):
            parts.append(self.tr("check against other observers"))
        self._set_wrapped(self.lbl_plan_line, " · ".join(parts))

    def _sync_recipe_row(self):
        # @return: None. The line says what the brightness WILL be measured
        #          with, before the run: a recipe read silently is a number
        #          nobody can question.
        recipe = self._recipe() or {}
        on = bool(self.chk_brightness.isChecked())
        self.lbl_recipe.setEnabled(on)
        self.btn_recipe.setEnabled(on)
        if not on:
            self.lbl_recipe.setText(self.tr(
                "The brightness is not measured: this run reports "
                "positions only."))
            self._fit_label(self.lbl_recipe)
            self._sync_plan_line()
            return
        if not recipe:
            self.lbl_recipe.setText(self.tr(
                "Photometry recipe: the editor's defaults (open the "
                "Photometry tab to see or change them)."))
            self._fit_label(self.lbl_recipe)
            self._sync_plan_line()
            return
        band = recipe.get("band") or self.tr("the comps' own band")
        # The METHOD is said too, and not only the apertures: it decides how
        # the light is measured, and a run launched from here has to say it
        # BEFORE it runs (a recipe read silently is a number nobody can
        # question). A plate saved before the key existed falls back to the
        # app's own setting, which is the same fallback the run uses.
        method = (self.tr("matched filter")
                  if recipe.get("matched",
                                config.get("phot_matched", True))
                  else self.tr("aperture"))
        self.lbl_recipe.setText(self.tr(
            "Photometry recipe: %1 · apertures %2 · sky %3 · %4").replace(
                "%1", str(band)).replace(
                "%2", self._recipe_radii_text(recipe)).replace(
                "%3", str(recipe.get("sky") or "median")).replace(
                "%4", method))
        self._fit_label(self.lbl_recipe)
        self._sync_plan_line()

    def _recipe_radii_text(self, recipe):
        # @args: recipe - the photometry recipe
        # @return: how the aperture is sized, in words or in px
        # "From the seeing" is a CHOICE, not a number: the recipe hands the
        # radii to the measured FWHM, so there is no triple to print.
        if recipe.get("seeing") and not recipe.get("radii_manual"):
            return self.tr("from the seeing")
        vals = [recipe.get("rap"), recipe.get("rin"), recipe.get("rout")]
        if any(v is None for v in vals):
            return self.tr("the defaults")
        return " ".join(("/".join(f"{float(v):.1f}" for v in vals), "px"))

    def set_status_hook(self, fn):
        # @args: fn - callable(text, level) the window's single line listens
        #        with (U4), or None
        # @return: None. The panel was NOT wired to the window's line until
        #          2026-10-06: a run that said "the report is blocked" said
        #          it here and nowhere else.
        self._status_hook = fn if callable(fn) else None

    def _say(self, text):
        # @args: text - the status line's text ("" hides it)
        # @return: None. The messages that belong to no group live under the
        #          action they belong to (asked for 2026-10-06) and they
        #          WRAP, up to three lines, so they are read and not guessed
        #          from a tooltip (asked for: "los mensajes de la derecha se
        #          cortan"). What the panel must never do again is grow
        #          without a stop: the paragraph that used to be built here
        #          measured 204 px of a 380 px column and pushed the groups
        #          off the screen. Three lines is a ceiling; the whole text is
        #          in the tooltip and in the window's own line too (U4, via
        #          set_status_hook). What the run FOUND is not here: it lives
        #          in its own group, with room and a scroll.
        self._status_text = text or ""
        self.lbl_status.setVisible(bool(text))
        self.lbl_status.setToolTip(self._status_text)
        self.lbl_status.setText(self._status_text)
        self._fit_status()
        if self._status_hook is not None and text:
            self._status_hook(str(text),
                              "warn" if str(text).startswith("⚠") else "info")

    def _fit_status(self):
        # @return: None. The line's own height, capped at three lines: the
        #          sizeHint of a word-wrapped QLabel is computed for a width
        #          that changes later, so it is asked at the width it has.
        label = self.lbl_status
        if not getattr(self, "_status_text", ""):
            label.setMinimumHeight(0)
            return
        from PySide6.QtGui import QFontMetrics
        cap = QFontMetrics(label.font()).height() * 3 + 8
        label.setMaximumHeight(cap)
        if label.width() < 50:
            return
        need = label.heightForWidth(label.width())
        if need and need > 0:
            label.setMinimumHeight(min(int(need), cap))

    def _set_wrapped(self, label, text):
        # @args: label - a QLabel with wordWrap, text - its new text
        # @return: None. For the labels that DO wrap (the object line, the
        #          plan line and the calibration hint): the status line under
        #          the button does not wrap, it elides (see _say).
        label.setText(text)
        self._fit_label(label)

    def _fit_label(self, label):
        # @args: label - a QLabel with wordWrap whose text just changed
        # @return: None. Setting the text is not enough for a wrapped label:
        #          it does not always ask for the height its text needs (the
        #          sizeHint is computed for a width that changes later), and
        #          then every line comes out clipped at the top and the
        #          bottom. Asking the label itself, at the width it has NOW,
        #          is the fix the measure tab and the manual window already
        #          carry. A few pixels is not a width: at 1 px a wrapped
        #          label would want one line per word.
        if label is None or label.width() < 50:
            return
        need = label.heightForWidth(label.width())
        if need and need > 0:
            label.setMinimumHeight(int(need))

    def resizeEvent(self, event):
        # @args: event - the resize event, passed on
        # @return: None. A wider or narrower column needs another number of
        #          lines, so the wrapped labels are refitted here, where
        #          the width is known, and the status line is elided again.
        super().resizeEvent(event)
        for name in ("lbl_object", "lbl_recipe", "lbl_calibration_hint"):
            label = getattr(self._ui, name, None)
            if label is not None and label.isVisible():
                self._fit_label(label)
        self._fit_status()

    # ------------------------------------------------------------- visit

    def _sync_context(self):
        # The visit arms the tab (D15): with no visit the stack button
        # stays DISABLED and the object line says why (a dead button
        # teaches nobody). The frames' headers are read once per visit:
        # load_sequence never touches pixels, so this is cheap enough for
        # the GUI thread.
        # @return: None
        ctx = self._context() or {}
        paths = tuple(ctx.get("paths") or ())
        running = self._worker is not None and self._worker.isRunning()
        self.btn_stack.setEnabled(bool(paths) and not running)
        if not paths:
            self._frames = None
            self._ctx_paths = None
            self.spn_nobs.setEnabled(False)
            self.tbl_snr.setRowCount(0)
            self._hide_manual()
            self.lbl_object.setText(self.tr(
                "Object and frames: open the editor from a visit to arm "
                "the sequence."))
            self._fit_label(self.lbl_object)
            return
        if paths != self._ctx_paths:
            from ..core import track_stack
            self._frames = track_stack.load_sequence(list(paths), config)
            self._ctx_paths = paths
            # A frame that could not be read is left out by load_sequence:
            # the visit is not lost, but the count has to say so (a real
            # capture ends with a half-written file).
            self._n_unreadable = max(0, len(paths) - len(self._frames))
            # a different visit invalidates the last run: its stacks, its
            # check and its report belong to the other sequence
            self._base_snr = None
            self._result = None
            self.cmb_group.clear()
            self.cmb_group.setEnabled(False)
            self.txt_report.clear()
            self.txt_notes.setVisible(False)
            self._hide_manual()
            self._show_result_area(False)
            self._sync_report_buttons()
            # a different visit may hold its own saved run: ask again
            self._restore_asked = False
            # and the calibration's automatic default follows THIS visit's
            # frames (camera, filter, temperature): a library that matches
            # turns it on, and only while nobody has chosen
            self._auto_calibrate()
        n = len(self._frames)
        self.spn_nobs.setEnabled(True)
        self.spn_nobs.blockSignals(True)
        self.spn_nobs.setRange(1, max(1, n))
        self.spn_nobs.setValue(min(self.spn_nobs.value(), max(1, n)))
        self.spn_nobs.blockSignals(False)
        # the object line, read-only (it comes from the project and from
        # Horizons): name, frames and the visit's own time window
        name = ctx.get("object_name") or self.tr("(unnamed)")
        line = self.tr("Object: %1 · %2 frames").replace(
            "%1", name).replace("%2", str(n))
        stamps = [f.t_mid_jd for f in self._frames if f.t_mid_jd is not None]
        if stamps:
            from ..core import coords
            t0 = coords.datetime_from_jd(min(stamps))
            t1 = coords.datetime_from_jd(max(stamps))
            line += self.tr(" · window %1–%2 UT").replace(
                "%1", t0.strftime("%H:%M")).replace("%2", t1.strftime("%H:%M"))
        if self._n_unreadable:
            # said, never silent: a frame that is not there is a hole in the
            # stack, and the observer has to know how big
            line += self.tr(" · %1 could not be read (left out)").replace(
                "%1", str(self._n_unreadable))
        self.lbl_object.setText(line)
        self._fit_label(self.lbl_object)
        self._sync_calibration_hint()
        self._refresh_preview()
        # The visit may ALREADY hold a run (asked for): show it instead of
        # an empty column, from what was saved. The ask is retried until it
        # is answered, because the host sets its astrometry hook BEFORE the
        # hook that reads the saved run.
        self._restore_result()

    def _refresh_preview(self):
        # D22: the SNR grows with sqrt(n), so asking for more observations
        # splits the signal, and the table says it BEFORE the user accepts.
        # Until the first run there is no measured base SNR and the column
        # stays "–": an estimate without a measurement would be invented.
        # @return: None
        from ..core import track_stack
        # the spinbox's floor is 1, but a tab whose visit was never armed
        # can still be repainted: a zero would divide inside split_groups
        rows = track_stack.preview_groups(self._frames or [],
                                          max(1, self.spn_nobs.value()),
                                          base_snr=self._base_snr)
        floor = float(config.get("astrometry_submit_snr", 20.0))
        tbl = self.tbl_snr
        tbl.setRowCount(len(rows))
        for i, row in enumerate(rows):
            cells = (str(i + 1), str(row["n_frames"]),
                     self._t_mid_text(row["t_mid"]),
                     self._snr_text(row["snr_est"], floor))
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled)   # read-only: a preview
                if col == 3 and row["snr_est"] is not None \
                        and row["snr_est"] < floor:
                    item.setToolTip(self.tr(
                        "Below the MPC submission floor of %1: this "
                        "observation would be left out of the report"
                    ).replace("%1", f"{floor:.0f}"))
                tbl.setItem(i, col, item)
        # The plan row shows the same number in one line: the table is the
        # detail and it lives folded, but the decision (how many
        # observations) is taken from the row.
        parts = [self._snr_text(row["snr_est"], floor) for row in rows]
        self.lbl_snr_line.setText(
            self.tr("Expected SNR: %1").replace("%1", " · ".join(parts))
            if parts else "")
        self._sync_plan_line()

    def _snr_text(self, est, floor):
        # @args: est - the expected SNR or None, floor - the submission
        #        floor (D26)
        # @return: the cell text; the ⚠ marks a group below the floor, so
        #          it is seen before stacking, not after
        if est is None:
            return "–"
        return f"{est:.1f}" + (" ⚠" if est < floor else "")

    def _t_mid_text(self, jd):
        # @args: jd - the group's middle-of-exposure instant (JD) or None
        # @return: "HH:MM:SS" UTC, or "–"
        if jd is None:
            return "–"
        from ..core import coords
        return coords.datetime_from_jd(jd).strftime("%H:%M:%S")

    # -------------------------------------------------------------- run

    def _on_stack(self):
        # The run button, and its Cancel while the worker runs (a long
        # pipeline must have a way out, P1 #12). Everything heavy lives in
        # TrackStackWorker; the tab wires, paints and persists nothing:
        # the report goes to the visit's MPC block, which owns the
        # database round trip (ADR-022/045).
        # @return: None
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._say(self.tr(
                "Cancelling: the pipeline stops at the stage boundary it "
                "is at; nothing is kept from a cancelled run."))
            return
        self._start_run(manual_ref=None)

    def _start_run(self, manual_ref=None):
        # @args: manual_ref - (x, y) of the observer's mark in the REFERENCE
        #        grid, or None for a normal run
        # @return: None. The worker construction, shared by the Stack button
        #          and the manual mode's "Measure at the mark".
        ctx = self._context() or {}
        paths = ctx.get("paths") or []
        name = ctx.get("object_name") or ""
        if not paths:
            self._say(self.tr(
                "No visit with frames: open the editor from a visit to "
                "stack its sequence."))
            return
        if not name:
            self._say(self.tr(
                "The project has no object name: the ephemeris cannot be "
                "fetched, and without it there is no track."))
            return
        from .workers import TrackStackWorker
        # A run invalidates the mark: the manual window closes with it (a mark
        # over a stack that is being rebuilt is a mark over nothing). The
        # caller that came FROM the mark has already taken what it needs.
        self._hide_manual()
        self.prg_stack.setVisible(True)
        self.prg_stack.setRange(0, 0)          # busy until a stage counts
        # The hero stops being the action and becomes the way out: same size
        # and weight, quiet and outlined, and without the kind's glyph (the
        # run is what is happening now, not the project's identity).
        set_hero_text(self.btn_stack, self.tr("Cancel"))
        self.btn_stack.setIcon(QIcon())
        self.btn_stack.setStyleSheet(theme.hero_cancel_style())
        # the previous run's evidence goes before the new one starts: a
        # stale strip next to a fresh run is a lie
        self._thumbs.clear()
        self.btn_blink.setEnabled(False)
        self._say("")
        self._worker = TrackStackWorker(
            paths, name, self.spn_nobs.value(),
            method=self.cmb_method.currentData() or "sigma", cfg=config,
            obs_code=str(config.get("mpc_code", "")),
            site=str(config.get("mpc_code", "")),
            final_size=int(self.cmb_final_size.currentData() or 0),
            margin=int(self.spn_margin.value()),
            comps=ctx.get("comps"), target_mag=ctx.get("target_mag"),
            recipe=self._recipe(),
            phot_enabled=self.chk_brightness.isChecked(),
            save_star_stack=self.chk_starstack.isChecked(),
            calibrate=self.chk_calibrate.isChecked(),
            manual_ref=manual_ref)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, stage, done, total):
        # @args: stage - the worker's stage key, done/total - inside that
        #        stage
        # @return: None. The human text is a literal self.tr() table (the
        #          way TonightWorker's phases do it, CONTRIBUTING rule 5).
        # A stage that is ONE long operation (the base stack, the comparison
        # windows, the check's round trip to the MPC and Find_Orb) has no
        # inside to count: a bar pinned at 0 reads as a freeze, so it goes
        # BUSY (indeterminate) and the status line says what is happening.
        if total > 1:
            self.prg_stack.setRange(0, total)
            self.prg_stack.setValue(done)
        else:
            self.prg_stack.setRange(0, 0)
        text = self._stage_text(stage)
        if text:
            self._say(text + (f" ({done}/{total})" if total > 1 else ""))

    def _stage_text(self, key):
        # @args: key - one of TrackStackWorker's stage keys
        # @return: the human text for the status line
        return {
            "calibrate": self.tr("Calibrating the frames…"),
            "pseudoflat": self.tr("Building a flat from the frames…"),
            "solve": self.tr("Solving the reference frame…"),
            "register": self.tr("Registering the frames…"),
            "base": self.tr("Stacking the whole sequence…"),
            "detect": self.tr("Looking for the object…"),
            "sweep": self.tr("Sweeping the velocity…"),
            "groups": self.tr("Stacking each observation…"),
            "measure": self.tr("Measuring the positions…"),
            "starstack": self.tr("Stacking the stars…"),
            "photometry": self.tr("Measuring the brightness…"),
            "check": self.tr("Checking against other observers…"),
        }.get(key, "")

    def _run_ended(self):
        # @return: None. The button comes back from Cancel (its label, its
        #          hue and its glyph) and the bar hides; the button stays
        #          disabled without a visit.
        set_hero_text(self.btn_stack, self._btn_stack_label)
        self._apply_hero()
        self.prg_stack.setVisible(False)
        self.btn_stack.setEnabled(bool(self._ctx_paths))

    def _on_failed(self, message):
        # @args: message - the worker's error (internal English, like the
        #        other workers' failed signal)
        # @return: None
        self._run_ended()
        self._say(self.tr("The run failed:") + f" {message}")

    def _on_finished(self, payload):
        # @args: payload - TrackStackWorker's result dict
        # @return: None
        self._run_ended()
        self._result = payload if isinstance(payload, dict) else {}
        status = self._result.get("status")
        if status == "cancelled":
            self._say(self.tr("Cancelled: nothing was kept from this run."))
            return
        if status == "error":
            self._say(self.tr("The run could not finish:") + " "
                      + str(self._result.get("error") or ""))
            return
        if status == "not_detected":
            # the run is persisted FIRST: its id is what the stacks carry in
            # their NS_RUN card, and the stacks are written when the result
            # is painted
            self._persist_run(self._result)
            self._paint_not_detected()
            return
        self._persist_run(self._result)
        self._paint_run()

    def _persist_run(self, payload):
        # ADR-062, phase 8: the HOST writes the run (the tab never touches
        # the database) and hands back its id, which the "undo this run"
        # button needs. Without a host (an ad-hoc open) there is nothing to
        # persist and the button stays off.
        # @args: payload - the worker's result dict
        # @return: None
        host = host_of(self)
        persist = getattr(host, "persist_astrometry", None)
        self._run_id = persist(payload) if callable(persist) else None
        self._sync_report_buttons()

    def _on_undo(self):
        # The run's own undo (D14): its points and its frame manifest go,
        # the run row stays marked "undone", and nothing else is touched.
        # @return: None
        if self._run_id is None:
            return
        host = host_of(self)
        undo = getattr(host, "undo_astrometry", None)
        removed = undo(self._run_id) if callable(undo) else None
        self._run_id = None
        self._result = None
        self.cmb_group.clear()
        self.cmb_group.setEnabled(False)
        self.tbl_points.setRowCount(0)
        self.txt_report.clear()
        self._thumbs.clear()
        self.btn_blink.setEnabled(False)
        self._hide_manual()
        self._show_result_area(False)
        self._sync_report_buttons()
        self._say(self.tr("Run undone: %1 observations removed."
                          ).replace("%1", str(removed if removed is not None
                                             else 0)))

    # -------------------------------------------------------- the restore

    def _restore_result(self):
        # @return: None. The visit may already hold an astrometry run: the
        #          tab then shows it instead of an empty column, the way the
        #          Photometry tab shows the visit's curve (asked for). It is
        #          rebuilt from what was SAVED: the run's own summary in the
        #          database, its points and the stack files in the project.
        #          Nothing is recomputed and nothing is invented: a stack
        #          that is no longer on disk is said, not faked.
        ask = getattr(host_of(self), "astrometry_result", None)
        if not callable(ask):
            return
        if self._restore_asked or self._result is not None \
                or not self._ctx_paths:
            return
        try:
            data = ask()
        except Exception as err:
            logger.warning("the astrometry result could not be read: %s", err)
            return
        if not data or not data.get("run"):
            return
        result = self._restored_payload(data)
        if result is None:
            return
        self._restore_asked = True
        self._result = result
        self._run_id = data["run"].get("id")
        self._sync_report_buttons()
        if result.get("status") == "not_detected":
            self._paint_not_detected()
            # The manual mark is still there for the observer (the base stack
            # is saved with the run): the notes say how deep the night
            # reached and the door says what it needs if the stack is gone.
            self.chk_manual.setEnabled(bool(self._ctx_paths))
            return
        self._paint_run()
        # The report is rebuilt from the points, which are the same ones the
        # run measured: the generator is local and deterministic, so the text
        # is the one the run's own points give, in the format the combo is on
        # (asked for: reopening the visit shows the run WITH its report). It
        # is not sent anywhere: that is a button.
        if result.get("points"):
            self._on_report(quiet=True)

    def _restored_payload(self, data):
        # @args: data - {"run", "points", "stacks"} from the host
        # @return: the payload `_paint_run` knows how to paint, rebuilt from
        #          the saved run, or None when there is nothing to show.
        # What a run cannot bring back (the reference WCS, the in-memory
        # pixels of the base stack, the per-frame points) is simply absent:
        # the painting only uses what a restored run can honestly have. The
        # stacks are files and the mark's arithmetic (box_all) rides in the
        # run's own summary, so both the strip and the manual mode work.
        from ..core import track_stack
        from ..core.findorb import CheckReport
        run = data.get("run") or {}
        summary = ((run.get("cfg") or {}).get("result") or {})
        rows = data.get("points") or []
        status = run.get("status")
        if status == "complete" and not rows:
            return None
        # the stacks: the files the run wrote and the visit registered, one
        # per observation, matched by their observation number (their names
        # carry "obs<N>", which survives a reordering of the visit's list)
        files = [p for p in (data.get("stacks") or [])
                 if not str(p).endswith("_stars.fits")]
        by_obs = {}
        for path in files:
            m = _OBS_RE.search(Path(str(path)).name)
            if m:
                by_obs[int(m.group(1))] = str(path)
        # the two ways of an observation, paired by its group, and the stack
        # that goes with it: the file's number is the group's (index + 1),
        # NOT the position in this list (an observation that failed to
        # measure must not shift the others onto the wrong file)
        by_group = {}
        for row in rows:
            gi = int(row.get("group_index") or 0)
            by_group.setdefault(gi, {})[row.get("source") or "stack"] = row
        points, groups, mids, qs = [], [], [], []
        stacks, stack_paths, boxes = [], [], []
        start = 0
        for gi in sorted(by_group):
            entry = by_group[gi]
            sp = self._restored_point(entry.get("stack")
                                      or entry.get("frames"))
            fp = (self._restored_point(entry["frames"])
                  if entry.get("frames") else None)
            if sp is None:
                continue
            flags = list((entry.get("stack") or {}).get("flags") or [])
            # A magnitude written by hand in the Photometry tab is the
            # EFFECTIVE one (it is what the report would use), and the saved
            # point carries it: the run's own value stays in mag_auto. The
            # table must say so, or the figure would look like the run's.
            if (entry.get("stack") or {}).get("mag_source") == "manual":
                flags.append("mag_manual")
            points.append((sp, fp, flags))
            n = int(getattr(sp, "n_frames", 0) or 0) or 1
            groups.append((start, start + n))
            start += n
            mids.append((sp.mjd or 0.0) + 2400000.5)
            # the object's position in the STACK's own pixels: the saved x/y
            # were measured on that very stack, so they need no conversion
            qs.append((float(sp.x), float(sp.y)))
            path = by_obs.get(gi + 1)
            arr = self._load_stack(path) if path else None
            stacks.append((arr, None))
            stack_paths.append(path)
            boxes.append((0, 0, arr.shape[1] if arr is not None else 0,
                          arr.shape[0] if arr is not None else 0))
        if status == "complete" and not points:
            return None
        det = summary.get("detection") or {}
        dither = summary.get("dither") or {}
        qc = summary.get("wcs_qc") or {}
        sweep = summary.get("sweep") or {}
        check = summary.get("check") or {}
        return {
            "status": "ok" if status == "complete" else "not_detected",
            "restored": True, "stack_paths": stack_paths,
            "stacks": stacks, "boxes": boxes, "qs": qs, "mids": mids,
            "groups": groups, "points": points,
            "method": summary.get("method") or run.get("method"),
            "ephem_source": summary.get("ephem_source"),
            "n_failed": summary.get("n_failed"),
            "n_off_frame": summary.get("n_off_frame"),
            # the mark's arithmetic and the band's figures come back with the
            # run: without box_all the manual mode could not be used on a
            # reopened run, and without the ephemeris' magnitude the band
            # would fall back to the catalogue
            "box_all": (tuple(int(v) for v in summary["box_all"])
                        if summary.get("box_all") else None),
            "base_rate": summary.get("base_rate"),
            "base_pa": summary.get("base_pa"),
            "ephem_mag": summary.get("ephem_mag"),
            "ephem_band": summary.get("ephem_band"),
            "ephem_mag_source": summary.get("ephem_mag_source"),
            "register_report": summary.get("register_report") or {},
            "calibration": summary.get("calibration") or {},
            "photometry": summary.get("photometry"),
            "phot_skipped": summary.get("phot_skipped"),
            "detection": track_stack.DetectionReport(
                detected=bool(det.get("detected")), snr=float(det.get("snr")
                                                             or 0.0),
                x=float(det.get("x") or 0.0), y=float(det.get("y") or 0.0),
                fwhm=det.get("fwhm"), roundness=float(det.get("roundness")
                                                      or 0.0),
                mag_limit=det.get("mag_limit")),
            "dither": track_stack.DitherReport(
                dithered=bool(dither.get("dithered", True)),
                spread_px=float(dither.get("spread_px") or 0.0)),
            "wcs_qc": track_stack.WcsQCReport(
                checked=int(qc.get("checked") or 0),
                max_offset_arcsec=float(qc.get("max_offset_arcsec") or 0.0),
                ok=bool(qc.get("ok", True))),
            "sweep": track_stack.SweepResult(best=sweep.get("best"),
                                             grid=sweep.get("grid") or []),
            "check": CheckReport(
                available=bool(check.get("available", True)),
                blocked=bool(check.get("blocked")),
                no_reference=bool(check.get("no_reference")),
                our_residual=(tuple(check["our_residual"])
                              if check.get("our_residual") else None),
                n_stations=int(check.get("n_stations") or 0),
                note=str(check.get("note") or "")),
        }

    def _restored_point(self, row):
        # @args: row - an astrometry_points row (a dict), or None
        # @return: an AstrometryPoint, or None. The numbers are the saved
        #          ones, verbatim: a restored point is a record, not a new
        #          measurement.
        if not row:
            return None
        from ..core import astrometry
        return astrometry.AstrometryPoint(
            ra=row.get("ra"), dec=row.get("dec"),
            rms_ra=row.get("rms_ra"), rms_dec=row.get("rms_dec"),
            x=row.get("x"), y=row.get("y"), snr=row.get("snr"),
            mag=row.get("mag"), band=row.get("band"),
            mjd=row.get("mjd"), n_frames=row.get("n_frames"),
            source=row.get("source") or "stack",
            group_index=row.get("group_index"), flags=list(row.get("flags")
                                                           or []))

    def _load_stack(self, path):
        # @args: path - a stack file in the project
        # @return: its pixels as float32, or None when it cannot be read.
        #          The restore needs the ARRAYS and not only the path: the
        #          strip, the blink and the group viewer all work on pixels.
        if not path:
            return None
        try:
            from ..core import fits_io
            import numpy as np
            _header, arr = fits_io.read_fits(str(path))
            return np.ascontiguousarray(arr, dtype=np.float32)
        except Exception as err:
            logger.warning("a saved stack could not be read (%s): %s",
                           path, err)
            return None

    def _paint_not_detected(self):
        # D10: below the gate there is no sweep and no measurement (the
        # sweep would measure noise); the limit magnitude is the useful
        # datum, because it says how deep the night reached.
        # @return: None
        det = self._result.get("detection")
        gate = float(config.get("astrometry_snr_sigma", 3.5))
        text = self.tr(
            "The object was not detected above the %1σ gate: the velocity "
            "sweep is not run, because measuring noise is how a false "
            "positive is manufactured.").replace("%1", f"{gate:.1f}")
        if det is not None and getattr(det, "mag_limit", None) is not None:
            text += " " + self.tr(
                "The stack's limit magnitude is %1: the night reached "
                "that deep.").replace("%1", f"{det.mag_limit:.2f}")
        self.txt_notes.setVisible(True)
        self.txt_notes.setPlainText(text)
        self.cmb_group.setEnabled(False)
        self._sync_report_buttons()
        self._say("")
        # The base stack is saved here too: it is the image the manual mark
        # is placed on, and a visit reopened tomorrow must be able to do the
        # same (asked for). Below the gate it is the ONLY product of the run.
        self._save_base_stack(self._result)
        # Below the gate the run has TWO groups to show and no others: what
        # it found (the notes, with the night's limit magnitude) and the
        # manual mark, because there IS a whole-sequence stack to mark on
        # even though there is no strip and no table to show.
        self._sections["notes"].setVisible(True)
        self._sections["manual"].setVisible(True)
        self.chk_manual.setEnabled(bool(self._ctx_paths))
        self.chk_manual.setChecked(False)

    # ------------------------------------------------------- manual mode

    def _hide_manual(self):
        # @return: None. The manual mark is CLOSED (unchecked, dialog away) by
        #          a new run, a new visit or an undo, but the door itself is
        #          never locked: it is useful on any run, to place the centroid
        #          of a faint object by eye (asked for: it used to open only
        #          after a run that found nothing).
        self.chk_manual.blockSignals(True)
        self.chk_manual.setChecked(False)
        self.chk_manual.blockSignals(False)
        self._sync_manual_enabled()
        self._manual.setVisible(False)
        self._manual_armed = False
        self._manual_base = None
        self._draw_marks()

    def _sync_manual_enabled(self):
        # @return: None. The manual mark needs a visit: with frames on disk
        #          the pipeline can be run again from the observer's mark, so
        #          the door is open whenever there is one (asked for).
        self.chk_manual.setEnabled(bool(self._ctx_paths))

    # ------------------------------------------------------ the marks

    def _draw_marks(self):
        # @return: None. Repaints the tab's marks on the stage: the MEASURED
        #          position of the shown observation and, in manual mode, the
        #          observer's mark with its cross. The measured cross is
        #          anchored to the SKY (the point's RA/Dec) and placed with
        #          the open plate's own WCS, so it survives loading another
        #          image of the series and leaving/returning to the tab
        #          (reported: it was a stack-pixel overlay, dropped on both).
        view = self._view if self._view is not None else self._stack_view
        state = self._state if self._view is not None else self._stack_state
        if view is None or state is None:
            return
        view.clear_overlays()
        if not state.has_image:
            return
        scene = self._point_scene(state, self._shown_point())
        if scene is not None:
            w, h = state.plate_shape
            for item in cross_marker_items(scene[0], scene[1], float(w),
                                           float(h), "#ff5555", 10.0):
                view.add_overlay(item)
        if self._manual_armed and self._manual_base is not None \
                and self._manual.chk_show_cross.isChecked():
            sx, sy = state.data_to_scene(
                self._manual_base[0] + self._nudge[0],
                self._manual_base[1] + self._nudge[1])
            for item in mark_cross_items(sx, sy, palette.ACCENT):
                view.add_overlay(item)

    def _shown_point(self):
        # @return: the measured point of the observation on stage, or None
        if self._shown_group is None:
            return None
        points = (self._result or {}).get("points") or []
        if not (0 <= self._shown_group < len(points)):
            return None
        return points[self._shown_group][0]

    def _point_scene(self, state, sp):
        # @args: state - the image state, sp - the measured point
        # @return: (x, y) in the open plate's scene, or None. The sky
        #          position is the anchor; the plate's WCS places it. Without
        #          a WCS only the observation's OWN stack can speak, in its
        #          own pixels.
        if sp is None:
            return None
        ra, dec = getattr(sp, "ra", None), getattr(sp, "dec", None)
        if state.wcs is not None and ra is not None and dec is not None \
                and math.isfinite(ra) and math.isfinite(dec):
            try:
                col, row = state.wcs.sky_to_pixel(float(ra), float(dec))
                w, h = state.plate_shape
                if 0 <= col < w and 0 <= row < h:
                    return state.data_to_scene(col, row)
            except Exception:
                pass
        if self._is_shown_stack(state) and getattr(sp, "x", None) is not None \
                and getattr(sp, "y", None) is not None:
            return state.data_to_scene(sp.x, sp.y)
        return None

    def _is_shown_stack(self, state):
        # @return: True when the open plate IS the observation's own stack
        if not self._shown_stack_path or not state.path:
            return False
        return Path(str(state.path)).name == Path(
            str(self._shown_stack_path)).name

    def _sync_manual_dialog(self, checked):
        # @args: checked - the checkbox's state
        # @return: None. The window appears while the box is checked, the way
        #          the Photometry tab shows its manual centre. The box is
        #          enabled with any armed visit (ADR-065, second revision):
        #          the mark is useful on any run, not only below the gate.
        if checked:
            self._manual.adjustSize()
        self._manual.setVisible(bool(checked))

    def _on_manual_show(self):
        # @return: None. Brings the whole-sequence stack to the main view and
        #          arms the mark (writing the stack only when it is missing:
        #          the run writes it, see _save_base_stack).
        result = self._result or {}
        path = self._ensure_base_stack(result)
        if path is None:
            self._say(self.tr(
                "There is no whole-sequence stack to mark on: stack the "
                "sequence first."))
            return
        state = self._state if self._view is not None else self._stack_state
        view = self._view if self._view is not None else self._stack_view
        try:
            state.load(str(path))
        except Exception as err:
            self._say(self.tr("The stack could not be shown:") + f" {err}")
            return
        view.clear_overlays()
        self._manual_armed = True
        self._manual_base = None
        self._reset_nudge()
        self.btn_manual_measure.setEnabled(False)
        self.lbl_manual_mark.setText(self.tr("Mark: click the object."))
        view.set_pick_cursor(True)
        self._draw_marks()
        self._say(self.tr(
            "Click the object on the stack; the click is refined to its "
            "centroid."))

    def _ensure_base_stack(self, result):
        # @args: result - the run's payload
        # @return: the path of the whole-sequence stack, or None when there
        #          is none. A run writes it when it ends (see _save_base_stack),
        #          so both a fresh run and a reopened one find it on disk; it
        #          is only written here when it is missing (an old run, or a
        #          file the observer deleted), and never twice: rewriting it
        #          would register a duplicate in the visit.
        path = self._base_stack_path()
        if path.exists():
            return path
        if result.get("base_stack") is not None:
            return self._save_base_stack(result)
        return None

    def _base_stack_path(self):
        # @return: where the whole-sequence stack is written for the mark:
        #          the project's own folder when the host points at one, the
        #          system temp otherwise
        import tempfile
        folder = None
        ask = getattr(host_of(self), "export_folder", None)
        if callable(ask):
            try:
                folder = ask()
            except Exception:
                folder = None
        base = Path(folder) if folder else Path(tempfile.gettempdir())
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            base = Path(tempfile.gettempdir())
        return base / self._base_stack_name()

    def _base_stack_name(self):
        # @return: "<object>_base.fits"
        ctx = self._context() or {}
        raw = (ctx.get("object_name") or "object").strip() or "object"
        slug = "".join(ch if (ch.isalnum() or ch in "-_") else "_"
                       for ch in raw.replace(" ", "")) or "object"
        return f"{slug}_base.fits"

    def _write_provenance_cards(self, header, result, report=None):
        # HOW THIS IMAGE WAS MADE, written into the file (2026-10-07).
        #
        # This was asked for the hard way: an afternoon went into telling two
        # stacks of the same 207 frames apart, and the saved file did not say
        # which combination had built it. The method is worth a quarter of a
        # magnitude (measured on that visit: the sigma-clipped mean reaches
        # magnitude 18.23 where the median reaches 17.97), so a stack that
        # does not say how it was combined is a stack nobody can audit a month
        # later. The rule the app already applies to a brightness (NS_MAGSR: a
        # figure never arrives without its origin) applies to the image too.
        # @args: header - the FITS header being built, result - the run's
        #        payload, report - the stack's own report when the caller has
        #        it (it carries how many frames were really combined)
        # @return: None
        from ..core import track_stack
        header["NS_COMB"] = (str(result.get("method") or "sigma"),
                             "how the frames were combined")
        header["NS_ORDER"] = (int(track_stack.WARP_ORDER),
                              "interpolation order of the warp")
        left = result.get("n_failed")
        if left is not None:
            header["NS_LEFT"] = (int(left),
                                 "frames the registration left out")
        used = getattr(report, "n_frames", None)
        if used:
            header["NS_NUSED"] = (int(used), "frames actually combined")

    def _save_base_stack(self, result):
        # @args: result - the run's payload
        # @return: the path of the whole-sequence stack, or None when it
        #          could not be written.
        # The base stack is a PRODUCT of the run (the deepest image of the
        # visit: every frame, the object frozen) and it is written with the
        # same care as an observation's stack: its own WCS, what it is, the
        # run it belongs to, the frame metadata, the motion and the brightness
        # WITH THEIR SOURCE, and the detection that was made on it. Without
        # those cards the band over it said nothing about the object (asked
        # for), and the file is also what the manual mode marks on after the
        # visit is reopened.
        import numpy as np
        stack = result.get("base_stack")
        if stack is None:
            return None
        path = self._base_stack_path()
        try:
            from astropy.io import fits
            from .workers import _shift_wcs
            hdu = fits.PrimaryHDU(np.asarray(stack, dtype=np.float32))
            w0, box = result.get("w0"), result.get("box_all")
            if w0 is not None and box is not None:
                hdu.header.update(_shift_wcs(w0, box).to_header())
            # The stack follows the OBJECT, so its stars are trails, exactly
            # like an observation's stack: NS_STACK says "base" and the
            # Photometry tab reads that (its message says why the comps
            # cannot set a zero point here).
            hdu.header["NS_STACK"] = ("base",
                                      "the whole sequence, object frozen")
            hdu.header["NS_WHOLE"] = (1, "all the frames, no split")
            name = (self._context() or {}).get("object_name")
            if name:
                hdu.header["OBJECT"] = str(name)
            frames = result.get("frames") or []
            hdu.header["NS_NFRAM"] = (int(len(frames)),
                                      "frames in this stack")
            # the base stack's own provenance: it is the deepest image of the
            # visit and the one the eye reads, so it has to say how it was
            # built as well (see _write_provenance_cards)
            self._write_provenance_cards(hdu.header, result)
            if self._run_id is not None:
                hdu.header["NS_RUN"] = (int(self._run_id),
                                        "the astrometry run it belongs to")
            self._write_frame_meta(hdu.header, result, None)
            self._write_band_cards(hdu.header, result, None)
            self._write_detect_cards(hdu.header, result)
            hdu.writeto(str(path), overwrite=True)
        except Exception as err:
            logger.warning("base stack write failed: %s", err)
            self._say(self.tr("The whole-sequence stack could not be "
                              "written:") + f" {err}")
            return None
        if self._view is not None:
            notify = getattr(host_of(self), "notify_saved", None)
            if callable(notify):
                notify([str(path)], "stack")
        return path

    def _write_detect_cards(self, header, result):
        # @args: header - the base stack's header, result - the run's payload
        # @return: None. The detection the run made ON THIS IMAGE: its SNR,
        #          the gate it had to clear and the limit magnitude it
        #          reached. It is the base stack's own measurement, and the
        #          band over it says it (asked for: the stacked image carries
        #          its measurements).
        det = result.get("detection")
        if det is None:
            return
        gate = float(config.get("astrometry_snr_sigma", 3.5))
        header["NS_FOUND"] = (1 if det.detected else 0,
                               "the object cleared the gate on this stack")
        header["NS_SNR"] = (float(det.snr or 0.0), "SNR of the detection")
        header["NS_GATE"] = (gate, "the gate it had to clear (sigma)")
        if getattr(det, "mag_limit", None) is not None:
            header["NS_LIMIT"] = (float(det.mag_limit),
                                   "limit magnitude (5 sigma) of this stack")

    def _on_manual_click(self, scene_pt):
        # @args: scene_pt - the click in scene coordinates (the shared
        #        view's scene_clicked)
        # @return: None. Only while the mark is armed: the click becomes the
        #          object's position, refined to the local centroid.
        if not self._manual_armed:
            return
        state = self._state if self._view is not None else self._stack_state
        if not state.has_image:
            return
        col, row = state.scene_to_data(scene_pt.x(), scene_pt.y())
        snapped = self._snap_centroid(state, col, row)
        self._manual_base = snapped or (float(col), float(row))
        self._reset_nudge()
        self.btn_manual_measure.setEnabled(True)
        self.lbl_manual_mark.setText(self.tr("Mark: (%1, %2) px").replace(
            "%1", f"{self._manual_base[0]:.1f}").replace(
            "%2", f"{self._manual_base[1]:.1f}"))
        self._draw_marks()

    def _snap_centroid(self, state, col, row):
        # @args: state - the image state, col/row - the clicked pixel
        # @return: (x, y) of the nearest local source's centroid, or None
        # The same refinement the pick reticle uses: a click is approximate,
        # a centroid is not.
        data = state.data
        if data is None:
            return None
        h, w = data.shape
        half = 24
        y0, y1 = max(0, int(row) - half), min(h, int(row) + half)
        x0, x1 = max(0, int(col) - half), min(w, int(col) + half)
        sub = data[y0:y1, x0:x1]
        if not sub.size:
            return None
        best, best_d = None, 1e18
        for sx, sy, _pk in photometry.local_sources(sub, k=4.0, min_sep=6,
                                                    max_sources=20):
            gx, gy = sx + x0, sy + y0
            d = (gx - col) ** 2 + (gy - row) ** 2
            if d < best_d:
                best, best_d = (gx, gy), d
        if best is None:
            return None
        cen = photometry.gaussian_centroid(data, best[0], best[1])
        if cen.get("ok"):
            return (float(cen["x"]), float(cen["y"]))
        return (float(best[0]), float(best[1]))

    def _nudge_step(self, dx, dy):
        # @args: dx/dy - one 0.1 px step toward the pressed arrow
        # @return: None. Session-only: a new click starts at (0, 0).
        if self._manual_base is None:
            return
        self._nudge[0] += dx
        self._nudge[1] += dy
        self.lbl_nudge.setText(
            f"({self._nudge[0]:+.1f}, {self._nudge[1]:+.1f})")
        self._draw_marks()

    def _reset_nudge(self):
        # @return: None. Back to the marked centroid.
        self._nudge = [0.0, 0.0]
        self.lbl_nudge.setText("(0.0, 0.0)")

    def _on_manual_measure(self):
        # @return: None. The mark (centroid + nudge) becomes the reference
        #          point of a new run: the gate is bypassed and the velocity
        #          sweep is not run.
        if self._manual_base is None:
            return
        box = (self._result or {}).get("box_all")
        if box is None:
            return
        ref = (box[0] + self._manual_base[0] + self._nudge[0],
               box[1] + self._manual_base[1] + self._nudge[1])
        self._manual_armed = False
        view = self._view if self._view is not None else self._stack_view
        if view is not None:
            view.set_pick_cursor(False)
        self._manual.setVisible(False)
        self.chk_manual.blockSignals(True)
        self.chk_manual.setChecked(False)
        self.chk_manual.blockSignals(False)
        self._draw_marks()
        self._start_run(manual_ref=ref)

    def _paint_run(self):
        # @return: None. The run's notes (dithering D27, WCS quality, the
        #          sweep's winner), the group viewer, the measurement
        #          table and the check's verdict.
        self._hide_manual()     # a fresh run closes the manual mark, not the door
        notes = []
        if self._result.get("manual"):
            # The position did not come from the detection gate: it came from
            # a human mark on the whole-sequence stack (manual mode). That is
            # the first thing the observer has to read, because the reported
            # position is still MEASURED on the plate, but the decision that
            # there was something to measure was theirs (ADR-065).
            notes.append(self.tr(
                "The position came from a HUMAN MARK on the whole-sequence "
                "stack (manual mode): the detection is yours, the gate was "
                "bypassed and the velocity sweep was not run. The reported "
                "position is measured on the plate from that mark."))
        ephem_source = self._result.get("ephem_source")
        if ephem_source and ephem_source.startswith("kepler"):
            # JPL did not answer (503, timeout) or does not know the object,
            # and the position came from a LOCAL orbit: the run still works,
            # but the observer has to know the prediction is two-body and
            # approximate (the reported position is measured, not predicted).
            notes.append(self.tr(
                "The position came from a LOCAL orbit (%1), not from JPL: "
                "two-body and approximate, so the search box is wider. The "
                "reported position is measured on the plate, not this "
                "prediction.").replace(
                    "%1", self.tr("local elements") if ephem_source
                    == "kepler:sbdb" else self.tr("a preliminary orbit")))
        dither = self._result.get("dither")
        if dither is not None and not dither.dithered:
            # informative, never blocking (D27): pattern noise stacks and
            # manufactures phantom detections (the MPC's warning number one)
            notes.append(self.tr(
                "The sequence is not dithered: pattern noise may stack up"))
        qc = self._result.get("wcs_qc")
        if qc is not None and not qc.ok:
            notes.append(self.tr(
                "The composed WCS is off by up to %1″ against a direct "
                "solve: the field's distortion is biting").replace(
                    "%1", f"{qc.max_offset_arcsec:.2f}"))
        sweep = self._result.get("sweep")
        if sweep is not None and sweep.best is not None:
            notes.append(self.tr(
                "Velocity sweep: %1″/min at PA %2° (%3 velocities scored; "
                "the score is SNR × roundness, which penalises a smeared "
                "object)").replace("%1", f"{sweep.best['rate']:.2f}").replace(
                    "%2", f"{sweep.best['pa']:.0f}").replace(
                    "%3", str(len(sweep.grid))))
        det = self._result.get("detection")
        if det is not None:
            gate = float(config.get("astrometry_snr_sigma", 3.5))
            if self._result.get("below_gate"):
                # ADR-062 rev: the run no longer stops here. The object was
                # not detected above the gate, so the position is the
                # ephemeris' prediction and the brightness is measured AT it
                # and marked: a number to look at, never one to publish.
                notes.append(self.tr(
                    "The object did NOT clear the %1σ gate (SNR %2 on the "
                    "base stack): the velocity sweep was not run, the "
                    "position is the ephemeris' prediction and the brightness "
                    "was measured there and is marked as not to be published "
                    "without looking at it. The stack's limit magnitude is "
                    "%3.").replace(
                        "%1", f"{gate:.1f}").replace(
                        "%2", f"{det.snr:.1f}").replace(
                        "%3", (f"{det.mag_limit:.2f}"
                               if getattr(det, "mag_limit", None) is not None
                               else self.tr("not available"))))
            else:
                notes.append(self.tr(
                    "Detected on the base stack with SNR %1 (the gate is "
                    "%2σ)").replace(
                        "%1", f"{det.snr:.1f}").replace("%2", f"{gate:.1f}"))
        sweep = self._result.get("sweep")
        if sweep is not None and sweep.best is not None \
                and not getattr(sweep, "significant", True):
            # The winner did not beat the ephemeris' own prediction by more
            # than the grid's scatter: on a faint object that is noise, and
            # the run keeps the ephemeris' motion. Saying it matters: the
            # band's rate and PA are then a PREDICTION, and the observer
            # comparing with another tool has to know which one they are
            # looking at (reported: PA 33 against the ephemeris' 41.8 on
            # 2025 HL5, and 37 against 46.2 on 2025 FG18).
            notes.append(self.tr(
                "The velocity sweep did not improve on the ephemeris (its "
                "best candidate is inside the grid's own scatter): the "
                "reported rate and PA are the ephemeris' prediction, not a "
                "measurement."))
        elif sweep is not None and sweep.best is not None:
            seed = getattr(sweep, "seed_score", None)
            if seed is not None:
                notes.append(self.tr(
                    "The velocity sweep improved on the ephemeris' "
                    "prediction (score %1 against %2) and its answer was "
                    "refined: the reported rate and PA are measured on this "
                    "sequence.").replace(
                        "%1", f"{sweep.best.get('score', 0):.0f}").replace(
                        "%2", f"{seed:.0f}"))
        phot = self._result.get("photometry")
        if phot is not None and phot.get("mag") is not None:
            # The magnitude comes from the STACKS (the object on its own,
            # the comps on a second one aligned on the stars) and one
            # measurement is made per observation, which is what the MPC
            # publishes. Saying where the comps came from matters: an
            # automatic proposal is a first guess, not the observer's own.
            origin = (self.tr("the project's sequence")
                      if phot.get("source") == "project"
                      else self.tr("an automatic proposal"))
            notes.append(self.tr(
                "Brightness %1 ± %2 %3 per observation (%4 observations, "
                "%5 frames each) from %6 comparison stars · %7").replace(
                    "%1", f"{phot['mag']:.3f}").replace(
                    "%2", f"{phot.get('err') or 0:.3f}").replace(
                    "%3", str(phot.get("band") or "")).replace(
                    "%4", str(phot.get("n_obs") or 0)).replace(
                    "%5", str(phot.get("n_frames") or 0)).replace(
                    "%6", str(phot.get("n_comps") or 0)).replace(
                    "%7", origin))
        elif self._result.get("phot_skipped"):
            notes.append(self.tr(
                "The brightness was not measured (the box is off): this "
                "run reports positions only"))
        self.txt_notes.setVisible(bool(notes))
        # A group with nothing to say is not shown: "What the run found" with
        # an empty box would be a title about nothing
        self._sections["notes"].setVisible(bool(notes))
        self.txt_notes.setPlainText("\n".join("• " + n for n in notes))
        # EVERY observation's stack is written to the project NOW, not when
        # the observer happens to open it: the visit's result has to survive
        # closing the editor (asked for: reopening showed an empty strip and
        # a lost blink). The cost is one file per observation, and it is the
        # price of a result that can be RESTORED instead of recomputed. A
        # restored run does NOT write: its files are already there.
        stacks = self._result.get("stacks") or []
        if not self._result.get("restored") \
                and any(s is not None for s, _rep in stacks):
            # One full-frame stack per observation is real disk work, and it
            # happens on the GUI thread (the run already ended): say it before
            # it starts and let the line paint, instead of freezing with no
            # explanation.
            from PySide6.QtWidgets import QApplication
            self._say(self.tr("Saving the stacks in the project…"))
            QApplication.processEvents()
            # the whole-sequence stack first: it is the image the manual mark
            # is placed on, and the deepest one of the visit
            base = self._save_base_stack(self._result)
            for i in range(len(stacks)):
                self._save_group_stack(i, self._result)
            self._base_saved = bool(base)
        # the viewer: one entry per observation, the first one on stage
        self.cmb_group.blockSignals(True)
        self.cmb_group.clear()
        for i, group in enumerate(self._result.get("groups") or []):
            self.cmb_group.addItem(
                self.tr("Observation %1 (%2 frames)").replace(
                    "%1", str(i + 1)).replace("%2", str(group[1] - group[0])),
                i)
        self.cmb_group.blockSignals(False)
        self.cmb_group.setEnabled(self.cmb_group.count() > 0)
        # the strip: the same stacks, visible side by side at ONE stretch,
        # so a faint observation cannot hide behind a bright one
        qs = self._result.get("qs") or []
        boxes = self._result.get("boxes") or []
        # The strip crops AROUND the object, so it wants the object's
        # position in the STACK's own pixels. The payload's qs are in the
        # reference grid (that is what the stacking needs); subtracting the
        # box origin is the conversion. Passing the reference position
        # straight in only worked while the final stack was the whole frame
        # (box origin 0,0): with a cutout the strip was cropped around a
        # point that is not in the image at all.
        qs_local = [(float(q[0]) - float(b[0]), float(q[1]) - float(b[1]))
                    if q is not None and b is not None else q
                    for q, b in zip(qs, boxes)]
        labels = [self.tr("Obs. %1").replace("%1", str(i + 1))
                  for i in range(len(stacks))]
        self._thumbs.set_stacks([s for s, _rep in stacks], qs_local, labels)
        self.btn_blink.setEnabled(any(s is not None for s, _rep in stacks))
        self._show_result_area(True)
        if self.cmb_group.count():
            self.cmb_group.setCurrentIndex(0)
            self._show_group(0)
        self._fill_points()
        self._fill_check()
        # the measured base SNR turns the expected-SNR column into a real
        # projection for the next choice of observations (D22)
        if det is not None and det.snr:
            self._base_snr = float(det.snr)
            self._refresh_preview()
        n = len(self._result.get("points") or [])
        # the report buttons FOLLOW the run (they were only refreshed at
        # init and on reset, so a successful run left them disabled)
        self._sync_report_buttons()
        # THE HEADLINE goes under the button; THE DETAILS go to the group.
        # Asked for (2026-10-06): the messages that belong to no group live
        # under the hero button, and the paragraph that used to be built here
        # (the unreadable frames, the saved stacks, the registration, the
        # shape, the diagnosis and the calibration, all in one line) grew to
        # 204 px of a 380 px column and pushed the groups out of the panel.
        # What the run FOUND is what the "What the run found" group is for,
        # and there it has room and a scroll.
        note = self.tr("Sequence stacked: %1 observations measured."
                       ).replace("%1", str(n))
        if self._result.get("restored"):
            # The observer must know WHY the tab is full before pressing
            # anything: this is the run the visit already held, rebuilt from
            # what was saved, not a fresh computation (asked for).
            note = self.tr(
                "This visit already held a run: shown again from what was "
                "saved (its stacks, its points and its notes). Stack again "
                "to redo it.") + " " + note
        self._say(note)
        details = []
        unreadable = int(self._result.get("n_unreadable") or 0)
        if unreadable:
            # a frame that is not there is a hole in the stack: it is said,
            # with the count, and never discovered later by surprise
            details.append(self.tr(
                "%1 frames could not be read and were left out.").replace(
                    "%1", str(unreadable)))
        # The stacks are in the project now, and the observer should know:
        # it is what makes the strip, the blink and the manual mark come back
        # when the visit is reopened (and what it costs in disk).
        saved_n = sum(1 for s, _rep in stacks if s is not None)
        if saved_n:
            details.append(self.tr(
                "%1 stacks saved in the project (the whole sequence and one "
                "per observation), so reopening the visit shows them "
                "again.").replace("%1", str(saved_n + (1 if self._base_saved
                                                       else 0))))
        extra = self._register_note(self._result.get("register_report"),
                                    self._result.get("n_off_frame") or 0)
        if extra:
            details.append(extra)
        shape = self._shape_note(self._result.get("photometry"))
        if shape:
            details.append(shape)
        diag = self._diag_note(self._result.get("photometry"))
        if diag:
            details.append(diag)
        cal = self._calibration_note(self._result.get("calibration"))
        if cal:
            details.append(cal)
        method = self._method_note(self._result.get("photometry"))
        if method:
            details.append(method)
        # THE CEILING THE RULE COULD NOT ENFORCE (ADR-066): without the
        # camera's linearity the brightness is measured with the SATURATE
        # card or the plate's own clip, and a star over the (unknown)
        # linearity slips through. Said with the run's news, never in silence.
        warn = photometry.ceiling_warning(
            (self._frames[0].header if self._frames else {}) or {}, config)
        if warn is not None:
            details.append("⚠ " + warn.get(self._lang, warn["en"]))
        if details:
            # the group was written BEFORE the stacks were saved (that is
            # where its first notes come from): the news that arrives after
            # is appended and the box rewritten, so nothing is lost and the
            # order the observer reads is the order it happened
            notes = list(notes) + details
            self.txt_notes.setPlainText("\n".join("• " + x for x in notes))
            self.txt_notes.setVisible(True)
            self._sections["notes"].setVisible(True)
        # THE FRAMES THE RUN COULD NOT REGISTER go to the preview list of the
        # visit (2026-10-06): the editor owns that list, the tab owns the
        # report, and a bad frame is worth seeing in the night, not only in a
        # sentence here.
        dlg = host_of(self)
        mark = getattr(dlg, "mark_unregistered_frames", None)
        if callable(mark):
            try:
                mark(self._result.get("failed_frames") or [])
            except Exception as err:
                logger.warning("the previews could not be marked: %s", err)
        # A CLOSED group that holds news says so (asked for 2026-10-06): the
        # observer opens what they want to read, and the panel marks where
        # the news is. A run that left frames out or could not register them
        # marks it as a warning, which also paints the title.
        trouble = bool(unreadable) or bool(self._result.get("n_failed"))
        self._notify("notes", self.tr("new"),
                     level="warn" if trouble else "info")
        if self.cmb_group.count():
            self._notify("view", str(self.cmb_group.count()))
        if n:
            self._notify("points", str(n))

    def _notify(self, key, text, level="info"):
        # @args: key - the section, text - the news in a word or a number,
        #        level - "info" | "warn"
        # @return: None. Only a COLLAPSED group gets marked, and the mark is
        #          consumed when the observer opens it (setNotice knows).
        section = self._sections.get(key)
        if section is not None:
            section.setNotice(text, level=level)

    def _method_note(self, phot):
        # @args: phot - the run's photometry dict (or None)
        # @return: which method measured the brightness and what the other
        #          one would say (or "")
        # The matched filter is the app's DEFAULT, and that is a measured
        # decision (the Photometry tab's tooltip carries the numbers and the
        # risks). It MOVES the magnitude that gets published, so the run has
        # to say which method it used and keep the other value beside it: a
        # curve that steps by a tenth of a magnitude can then be explained
        # instead of being a mystery.
        phot = phot or {}
        if "matched" not in phot:
            return ""
        text = (self.tr("Brightness measured with the matched filter")
                if phot.get("matched")
                else self.tr("Brightness measured with the aperture"))
        # The aperture's value is NOT a second run of the aperture (that
        # would need its own zero point): it is the aperture's flux with the
        # SAME zero point, so it is the difference between the two methods.
        # Said, so the number is not read as something it is not.
        other = phot.get("mag_aperture") if phot.get("matched") else None
        if other is not None:
            text += self.tr(
                " (the aperture, with the same zero point, would give %1)"
            ).replace("%1", f"{float(other):.3f}")
            band = phot.get("band")
            if band:
                text += f" {band}"
        text += "."
        # The recipe asked for the filter and the plate could not apply it
        # (no seeing measured on this stack): silence here would leave a run
        # claiming a method it did not use.
        if phot.get("matched_requested") and not phot.get("matched"):
            text += self.tr(
                " The matched filter was asked for but the seeing could not "
                "be measured on this stack: the aperture measured.")
        return text

    def _calibration_note(self, cal):
        # @args: cal - the run's calibration summary (or None)
        # @return: what the magnitude was measured with (or "")
        # ADR-061: a brightness never goes out without saying whether the
        # frames were calibrated and with which masters. The observer asked
        # for the calibration to be OPTIONAL, so the note also has to say
        # when it was not applied.
        cal = cal or {}
        if not cal:
            return ""
        bits = []
        if cal.get("offsets"):
            bits.append(self.tr("dark/bias: %1").replace(
                "%1", ", ".join(cal["offsets"])))
        if cal.get("flats"):
            bits.append(self.tr("flat: %1").replace(
                "%1", ", ".join(cal["flats"])))
        text = self.tr("Calibrated %1 frames").replace(
            "%1", str(cal.get("n") or 0))
        if bits:
            text += " (" + " · ".join(bits) + ")"
        else:
            text += " (" + self.tr("no master matched") + ")"
        info = cal.get("pseudo_flat") or {}
        if info.get("note"):
            if info.get("kind") == "vignette_model":
                # the smooth model is not a caveat, it is what was applied:
                # it says what it is and what it does not correct
                text += ". " + info["note"]
            else:
                text += ". " + self.tr("Warning:") + " " + info["note"]
        return text + "."

    def _shape_note(self, phot):
        # @args: phot - the run's photometry dict (or None)
        # @return: what the object's SHAPE says, in words (or "")
        # P2: the trail is the honest half of the exposure. A moving object
        # smears along its path, and the app says by how many pixels, so the
        # next exposure can be shortened instead of the loss being found
        # later as a low SNR. The matched filter's gain is said too: it is
        # what the pipeline could read on this very stack, and a number the
        # observer can compare with the SNR they got.
        phot = phot or {}
        parts = []
        trail = phot.get("trail_px")
        if trail:
            line = self.tr("The object is trailed by %1 px").replace(
                "%1", f"{float(trail):.1f}")
            pa = phot.get("trail_pa_deg")
            if pa is not None:
                line += self.tr(" along PA %1°").replace(
                    "%1", f"{float(pa):.0f}")
            parts.append(line + self.tr(
                ": shorten the exposure or expect a wider PSF."))
        gain = phot.get("snr_gain")
        if gain and float(gain) > 1.05:
            # The two SNRs of the BRIGHTNESS measurement, and not the
            # detection's: that one is the astrometry's own aperture and the
            # filter does not change it, which is exactly what the author
            # compared (5.41 bit for bit, box on and off) and read as "the
            # filter does nothing". It does: the magnitude moves, and this
            # says by how much.
            pair = ""
            snr_ap, snr_mf = phot.get("snr_ap"), phot.get("snr_mf")
            if snr_ap and snr_mf:
                pair = self.tr(
                    " (SNR %1 against %2 on the brightness measurement)"
                ).replace("%1", f"{float(snr_mf):.1f}").replace(
                    "%2", f"{float(snr_ap):.1f}")
            if phot.get("matched"):
                parts.append(self.tr(
                    "The brightness is measured with the matched filter, "
                    "which reads %1x the aperture's SNR on this stack%2"
                ).replace("%1", f"{float(gain):.2f}").replace("%2", pair))
            else:
                parts.append(self.tr(
                    "The matched filter would read %1x the aperture's SNR on "
                    "this stack%2: its switch is in the Photometry panel, "
                    "next to the apertures").replace(
                        "%1", f"{float(gain):.2f}").replace("%2", pair))
        return " ".join(parts)

    def _diag_note(self, phot):
        # @args: phot - the run's photometry dict (or None)
        # @return: the night's own diagnosis, in words (or "")
        # P3: two questions the observer asks after a run, both answered with
        # the stars of THIS stack. How faint the night went (the limiting
        # magnitude), and whether the plate solution is even across the field
        # (the median residual per cell of a 4x4 grid): one number for the
        # whole plate hides the corners, which is where a wrong scale or a
        # tilted chip shows up.
        phot = phot or {}
        parts = []
        limit = phot.get("limit") or {}
        if limit.get("ok") and limit.get("mag") is not None:
            line = self.tr("Limiting magnitude (5σ): %1").replace(
                "%1", f"{float(limit['mag']):.1f}")
            if not limit.get("sky_limited"):
                # the slope is the physics' own check: a field that is not
                # sky-limited gives a number nobody should quote
                line += self.tr(" (not sky-limited, do not trust it)")
            parts.append(line)
        grid = phot.get("grid") or {}
        if grid.get("ok") and grid.get("median") is not None:
            line = self.tr(
                "Solution residuals: %1″ median").replace(
                    "%1", f"{float(grid['median']):.2f}")
            worst = grid.get("worst")
            if worst is not None and float(worst) > 2.0 * max(
                    float(grid["median"]), 0.05):
                # a corner that is much worse than the middle is WHERE the
                # solution is bad, and that is the useful half of the answer
                line += self.tr(", up to %1″ in the worst cell").replace(
                    "%1", f"{float(worst):.2f}")
            parts.append(line)
        return " ".join(parts)

    def _register_note(self, report, off_frame=0):
        # @args: report - track_stack.registration_report output (or None)
        # @args: report - track_stack.registration_report output (or None),
        #        off_frame - how many registered frames do NOT contain the
        #        object (the worker counts them once the ephemeris is known)
        # @return: what the registration did, in plain language. This is the
        #          honest half of a run: a frame left out is a factor in the
        #          stack's SNR, and a visit that is really two runs is a
        #          fact the observer needs BEFORE believing the result. It
        #          replaces the old bare "N frames could not be aligned".
        report = report or {}
        parts = []
        n_rot = int(report.get("n_rotation") or 0)
        if n_rot:
            parts.append(self.tr(
                "%1 frames were saved by fitting the field's small rotation "
                "(they were being thrown away).").replace("%1", str(n_rot)))
        off = int(off_frame or 0)
        if off:
            # registered, but the object is not on the sensor: a shifted
            # field (the second run of a visit) leaves the object outside
            # the frame, and stacking those frames would only add noise
            # where the object is measured
            parts.append(self.tr(
                "%1 frames do not contain the object and were left out.").replace(
                    "%1", str(off)))
        failed = int(report.get("n_failed") or 0)
        if failed:
            line = self.tr("%1 frames could not be aligned").replace(
                "%1", str(failed))
            reasons = self._register_reasons(report.get("reasons") or {})
            if reasons:
                line += f" ({reasons})"
            parts.append(line + ".")
        blocks = report.get("blocks") or []
        if report.get("multi_run") and len(blocks) > 1:
            second = blocks[1]
            offset = (float(second.get("dx") or 0.0) ** 2
                      + float(second.get("dy") or 0.0) ** 2) ** 0.5
            text = self.tr(
                "The visit looks like %1 runs: the second one is %2 px away"
            ).replace("%1", str(len(blocks))).replace("%2", f"{offset:.0f}")
            gap = second.get("gap_s")
            if gap:
                text += self.tr(" and starts %1 min later").replace(
                    "%1", f"{float(gap) / 60.0:.0f}")
            parts.append(text + ".")
        return " ".join(parts)

    def _register_reasons(self, reasons):
        # @args: reasons - {internal code: count} from the report
        # @return: the reasons in words, or "" when there are none. The
        #          code is the core's English key; the words are here, one
        #          per language, and a code we do not know is passed through
        #          rather than hidden.
        words = {"rms": self.tr("their stars did not agree on the fit"),
                 "few_stars": self.tr("too few stars"),
                 "no_stars": self.tr("no stars detected"),
                 "no_fit": self.tr("no transform could be fitted")}
        if not reasons:
            return ""
        if len(reasons) == 1:
            key = next(iter(reasons))
            return words.get(key, key)
        return ", ".join(
            f"{words.get(key, key)}: {count}"
            for key, count in sorted(reasons.items(),
                                     key=lambda kv: -kv[1]))

    def _show_group(self, index):
        # The group's stack goes to the MAIN stage (the shared state), so
        # the histogram, the stretch and the marks work on it and the other
        # tabs can operate on top. The file lives in the project (kind
        # "stack"), not in a temp folder that vanishes, and the measured
        # position is marked on the shared view while this tab is on stage.
        # @args: index - the group's index in the last run
        # @return: None
        result = self._result or {}
        stacks = result.get("stacks") or []
        if index is None or index < 0 or index >= len(stacks):
            return
        if stacks[index][0] is None:
            return
        path = self._group_stack_path(index, result)
        if path is None:
            return
        state = self._state if self._view is not None else self._stack_state
        try:
            state.load(str(path))
        except Exception as err:
            logger.warning("group stack view failed: %s", err)
            self._say(self.tr("The group's stack could not be shown:")
                      + f" {err}")
            return
        # the measured position, marked: the observation on stage is
        # remembered so the mark can be repainted later (a new plate of the
        # visit, a return to the tab), and the mark itself is drawn from the
        # SKY position with this plate's WCS (_draw_marks)
        self._shown_group = index
        self._shown_stack_path = str(path)
        self._draw_marks()

    def _group_stack_path(self, index, result):
        # @args: index - the observation, result - the run's payload
        # @return: the file holding this observation's stack, or None when
        #          it cannot be had. A RESTORED run finds it already on disk
        #          (written and registered the day of the run); a fresh run
        #          writes it here.
        paths = result.get("stack_paths") or []
        if result.get("restored") and index < len(paths) and paths[index]:
            return Path(paths[index])
        return self._save_group_stack(index, result)

    def _save_group_stack(self, index, result):
        # @args: index - the observation, result - the run's payload
        # @return: the path of the stack just written, or None when it
        #          could not be written.
        # The stack is written ONCE per run (the whole set, at the end:
        # see _paint_run), annotated with the measured position and paired
        # with its star stack when the run kept one. Writing the stacks is
        # what makes a run RESTORABLE: a result whose stacks only lived in
        # memory was a result nobody could reopen (asked for: reopening the
        # visit showed an empty strip and lost the blink).
        import numpy as np
        stacks = result.get("stacks") or []
        if index < 0 or index >= len(stacks) or stacks[index][0] is None:
            return None
        stack = stacks[index][0]
        path = self._stack_path(index)
        try:
            from astropy.io import fits
            hdu = fits.PrimaryHDU(np.asarray(stack, dtype=np.float32))
            # The stack's own WCS, from the reference WCS shifted by the
            # cutout's origin: the plate is KNOWN, so nothing has to solve
            # it. On this stack the stars are trails (it follows the
            # object) and a blind solve finds no stars at all.
            wcss = result.get("wcs_by_group") or []
            if index < len(wcss) and wcss[index] is not None:
                hdu.header.update(wcss[index].to_header())
            # The app's own word about WHAT this file is. The stack follows
            # the object, so its stars are TRAILS: without this card the
            # Photometry tab would happily build a zero point out of
            # streaks, and with it the tab can say why it will not.
            hdu.header["NS_STACK"] = ("object", "the stars are trails")
            # The two stacks of an observation are a PAIR: the object's has
            # the light and the star's has the comps, and the Photometry tab
            # needs both to measure the brightness by hand. The link travels
            # in the header (a file name, same folder), so it survives
            # moving the project and there is no database to migrate.
            stars = result.get("star_stacks") or []
            if index < len(stars) and stars[index] is not None \
                    and stars[index][0] is not None:
                hdu.header["NS_PAIR"] = self._stack_name(index, stars=True)
            name = (self._context() or {}).get("object_name")
            if name:
                hdu.header["OBJECT"] = str(name)
            hdu.header["NS_NOBS"] = (int(index) + 1,
                                     "observation of the visit")
            groups = result.get("groups") or []
            if index < len(groups):
                hdu.header["NS_NFRAM"] = (
                    int(groups[index][1] - groups[index][0]),
                    "frames in this stack")
            # HOW the frames were combined, and how many really went in: a
            # stack that does not say it cannot be audited (see
            # _write_provenance_cards)
            _report = None
            _stacks = result.get("stacks") or []
            if index < len(_stacks) and _stacks[index] is not None:
                _report = _stacks[index][1]
            self._write_provenance_cards(hdu.header, result, _report)
            # WHICH run this stack came from, so the Photometry tab can write
            # a brightness measured by hand back to the right observation
            if self._run_id is not None:
                hdu.header["NS_RUN"] = (int(self._run_id),
                                        "the astrometry run it belongs to")
            # so reopening this stack says the same as the day it was made.
            self._write_frame_meta(hdu.header, result, index)
            self._write_band_cards(hdu.header, result, index)
            hdu.writeto(str(path), overwrite=True)
        except Exception as err:     # a stack that cannot be written says so
            logger.warning("group stack write failed: %s", err)
            self._say(self.tr("The group's stack could not be written:")
                      + f" {err}")
            return None
        # the stack belongs to the project: register it there (kind
        # "stack") so it shows in the visit and can be reopened
        if self._view is not None:
            notify = getattr(host_of(self), "notify_saved", None)
            if callable(notify):
                notify([str(path)], "stack")
        # The object's own position, annotated ON the stack: the editor
        # paints the marker (the same AIJ card the Annotate tab writes), so
        # in the Photometry tab you SEE where the object is and click it
        # instead of hunting a point among the stars' trails.
        self._annotate_object(path, index, result)
        # The star stack of the same observation, when the run kept one: it
        # is the plate the Photometry tab needs to measure the pair by hand
        # (on the object's stack the comps are trails).
        self._write_star_stack(index, result)
        return path

    def _stack_path(self, index, stars=False):
        # @args: index - the group's index, stars - True for the star stack
        # @return: where the group's stack is written: the project's own
        #          folder when the host points at one (it lands next to the
        #          rest of the project and survives a restart), the system
        #          temp otherwise
        import tempfile
        folder = None
        ask = getattr(host_of(self), "export_folder", None)
        if callable(ask):
            try:
                folder = ask()
            except Exception:
                folder = None
        base = Path(folder) if folder else Path(tempfile.gettempdir())
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            base = Path(tempfile.gettempdir())
        return base / self._stack_name(index, stars=stars)

    def _stack_name(self, index, stars=False):
        # @args: index - the group's index
        # @return: a file name that says what the stack IS: the object, the
        #          observation number and its mid time. "stack_obs2.fits"
        #          said nothing once the run was forgotten, and a visit
        #          holds several of them.
        ctx = self._context() or {}
        raw = (ctx.get("object_name") or "object").strip() or "object"
        slug = "".join(ch if (ch.isalnum() or ch in "-_") else "_"
                       for ch in raw.replace(" ", "")) or "object"
        stamp = ""
        mids = (self._result or {}).get("mids") or []
        mjd = mids[index] if 0 <= index < len(mids) else None
        if mjd:
            from datetime import datetime, timedelta
            # The run's mids are JULIAN dates (the engine's own currency) and
            # the file name wants the UT, so the MJD offset comes off here.
            # Using the JD as if it were an MJD named the stacks year 8596:
            # the author's own files read 2025UR_obs1_85961010T094820.
            try:
                ut = datetime(1858, 11, 17) + timedelta(days=float(mjd)
                                                        - 2400000.5)
                stamp = "_" + ut.strftime("%Y%m%dT%H%M%S")
            except (OverflowError, ValueError, OSError):
                # a mid outside the calendar (a test fixture, a corrupt
                # header) must not cost the stack its name: the stamp is a
                # nicety, the object and the observation number are not
                stamp = ""
        return f"{slug}_obs{index + 1}{stamp}{'_stars' if stars else ''}.fits"

    def _annotate_object(self, path, index, result):
        # @args: path - the stack just written, index - the observation,
        #        result - the run's payload
        # @return: None. The measured position, written as the annotation the
        #          editor already knows how to paint. A failure here must
        #          never cost the stack: the marker is a help, the file is
        #          the work.
        points = result.get("points") or []
        if index >= len(points):
            return
        sp = points[index][0]
        if sp is None or sp.x is None or sp.y is None:
            return
        try:
            from ..core import astrometry, fits_annotate
            w0 = result.get("w0")
            scale = astrometry.pixel_scale_arcsec(w0) if w0 is not None \
                else None
            fits_annotate.write_annotated_fits(
                path, path, sn_xy=(float(sp.x), float(sp.y)), scale=scale,
                obj_name=(self._context() or {}).get("object_name") or "",
                ra_deg=(float(sp.ra) if sp.ra is not None else None),
                dec_deg=(float(sp.dec) if sp.dec is not None else None))
        except Exception as err:
            logger.warning("the stack could not be annotated: %s", err)

    # ------------------------------------------------------------ the band

    def band_facts(self, header):
        # What the plate's heading (ADR-046) says about one of THIS tab's
        # stacks. Everything comes from the stack's own header, written when
        # the stack was saved, so the band says the same right after the run
        # and when the file is reopened in another session (no run in
        # memory, no database round trip).
        # @args: header - the open plate's header dict
        # @return: {"measured", "predicted", "measured_pos", "motion",
        #          "detection"} or None when the plate is not one of this
        #          run's stacks
        header = header or {}
        kind = str(header.get("NS_STACK") or "")
        if kind not in ("object", "stars", "base") \
                or header.get("NS_RUN") is None:
            return None
        stars = kind == "stars"
        facts = {}
        motion = self._motion_from_header(header)
        if motion is not None:
            facts["motion"] = motion
        if stars:
            return facts or None
        if kind == "base":
            det = self._detection_from_header(header)
            if det is not None:
                facts["detection"] = det
        ra, dec = header.get("NS_RA"), header.get("NS_DEC")
        if ra is not None and dec is not None:
            # the position MEASURED on this plate (the astrometric
            # centroid): written with the stack and, again, by the
            # annotation pass
            facts["measured_pos"] = (float(ra), float(dec))
        # The brightness, and WHO wrote it: NS_MAGSR says it (a stack
        # written before that card existed carries a measurement, which is
        # what all of them were). A prediction is NOT a measurement and must
        # not wear the quality colours of one.
        source = str(header.get("NS_MAGSR") or "measured")
        if source == "ephemeris":
            mag = header.get("NS_MAG")
            if mag is not None:
                facts["predicted"] = {"mag": float(mag),
                                      "band": header.get("NS_MAGB")}
        else:
            measured = self._measured_from_header(header)
            if measured is not None:
                facts["measured"] = measured
        return facts or None

    def _detection_from_header(self, header):
        # @args: header - the base stack's header
        # @return: {"detected", "snr", "gate", "limit"} of the detection the
        #          run made ON THIS IMAGE, or None when the cards are not
        #          there (a stack written before they existed)
        if header.get("NS_SNR") is None:
            return None
        gate = header.get("NS_GATE")
        limit = header.get("NS_LIMIT")
        return {"detected": bool(header.get("NS_FOUND")),
                "snr": float(header["NS_SNR"]),
                "gate": (float(gate) if gate is not None else None),
                "limit": (float(limit) if limit is not None else None)}

    def _motion_from_header(self, header):
        # @args: header - a stack's header
        # @return: {"rate_arcsec_min", "pa_deg", "measured"} or None. The
        #          word "measured" is what decides between the ink and the
        #          dimmed (eph) colour: the sweep measured it, or it is only
        #          the ephemeris' prediction.
        rate = header.get("NS_RATE")
        if rate is None:
            return None
        pa = header.get("NS_PA")
        return {"rate_arcsec_min": float(rate),
                "pa_deg": (float(pa) if pa is not None else None),
                "measured": str(header.get("NS_MOT") or "sweep") == "sweep"}

    def _measured_from_header(self, header):
        # @args: header - the object stack's header
        # @return: the brightness of this observation with the signals that
        #          colour it (see chart_annotate.magnitude_role), or None
        mag = header.get("NS_MAG")
        if mag is None:
            return None
        chk = header.get("NS_MAGOK")
        err = header.get("NS_MAGER")
        comps = header.get("NS_MAGNC")
        return {"mag": float(mag),
                "err": (float(err) if err is not None else None),
                "band": header.get("NS_MAGB"),
                "comps": (int(comps) if comps is not None else None),
                "check_ok": (bool(chk) if chk is not None else None),
                "no_check": chk is None}
    def _write_frame_meta(self, header, result, index):
        # A stack is a combination of frames and it must say what they were.
        # Without these cards the band over a stack had no date, no exposure
        # and no filter at all: the header was born with the WCS and the NS_*
        # cards only. Copying them is not a nicety, it is what lets the band
        # read "8 × 3.0 s" and the night's own date.
        # @args: header - the stack's header being built, result - the run's
        #        payload, index - the observation, or None for the base stack
        #        (the whole sequence)
        # @return: None
        try:
            frames = result.get("frames") or []
            groups = result.get("groups") or []
            ref = None
            if index is not None and 0 <= index < len(groups):
                start, end = groups[index]
                for i in range(int(start), min(int(end), len(frames))):
                    if getattr(frames[i], "header", None):
                        ref = frames[i]
                        break
            if ref is None and frames:
                ref = frames[0]
            if ref is None:
                return
            for key in ("EXPTIME", "FILTER", "INSTRUME", "TELESCOP"):
                value = (ref.header or {}).get(key)
                if isinstance(value, (str, int, float)) \
                        and str(value).strip():
                    header[key] = value
            # the date is the observation's own middle instant, so a visit
            # that spans two hours is dated where it really happened. The
            # base stack covers the whole sequence, so its date is the
            # sequence's own middle instant.
            mids = result.get("mids") or []
            jd = None
            if index is None:
                stamps = [f.t_mid_jd for f in frames
                          if getattr(f, "t_mid_jd", None) is not None]
                if stamps:
                    jd = sorted(stamps)[len(stamps) // 2]
            elif 0 <= index < len(mids):
                jd = mids[index]
            if jd is not None:
                from ..core import coords
                header["DATE-OBS"] = coords.datetime_from_jd(
                    float(jd)).strftime("%Y-%m-%dT%H:%M:%S")
            elif getattr(ref, "date_obs", None):
                header["DATE-OBS"] = str(ref.date_obs)
        except Exception as err:      # a missing card never costs the stack
            logger.warning("the stack's frame metadata failed: %s", err)

    def _write_band_cards(self, header, result, index, stars=False):
        # What the band says about this stack, written into the file so a
        # stack reopened months later says exactly the same. The motion is
        # the sweep's own answer when it was measured and the ephemeris'
        # prediction, marked as such, otherwise; the brightness and the
        # signals that colour it go only on the object's stack (on the
        # stars' one the object is a trail and was not measured).
        # @args: header - the stack's header being built, result - the run's
        #        payload, index - the observation, or None for the base stack,
        #        stars - True for the star stack
        # @return: None
        try:
            best = None
            sweep = result.get("sweep")
            if sweep is not None:
                best = getattr(sweep, "best", None)
                # A sweep whose winner did NOT beat the ephemeris by more than
                # the grid's scatter is not a measurement: the run keeps the
                # ephemeris' motion (the worker did not move the frames) and
                # the band must say `(eph)`, not `sweep`.
                if not getattr(sweep, "significant", True):
                    best = None
            if best and best.get("rate") is not None:
                header["NS_RATE"] = (
                    float(best["rate"]),
                    "arcsec/min, measured by the velocity sweep")
                if best.get("pa") is not None:
                    header["NS_PA"] = (float(best["pa"]),
                                       "deg north through east")
                header["NS_MOT"] = ("sweep", "the sweep measured it")
            elif result.get("base_rate") is not None:
                header["NS_RATE"] = (
                    float(result["base_rate"]),
                    "arcsec/min, ephemeris prediction")
                if result.get("base_pa") is not None:
                    header["NS_PA"] = (float(result["base_pa"]),
                                       "deg north through east")
                header["NS_MOT"] = ("eph",
                                    "ephemeris prediction, not measured")
            if stars:
                return
            # the position MEASURED on this stack (the astrometric
            # centroid). It is the same pair the annotation pass writes, and
            # writing it here too means the band reads it right away, without
            # waiting for the annotate step that rewrites the file. The base
            # stack has no measured position of its own (it is the whole
            # sequence, not an observation), so it does not carry one.
            if index is not None:
                points = result.get("points") or []
                sp = points[index][0] if 0 <= index < len(points) else None
                if sp is not None and sp.ra is not None \
                        and sp.dec is not None:
                    header["NS_RA"] = float(sp.ra)
                    header["NS_DEC"] = float(sp.dec)
            self._write_mag_cards(header, result, index)
        except Exception as err:      # a missing card never costs the stack
            logger.warning("the stack's band cards failed: %s", err)

    def _write_mag_cards(self, header, result, index):
        # The brightness, and WHO wrote it: the run's own measurement (this
        # observation's, or the run's median on the base stack), the
        # ephemeris' prediction when the run did not measure it, and nothing
        # when nobody can say. NS_MAGSR is the word the band prints, so a
        # figure never arrives without its origin (asked for).
        # @args: header - the stack's header being built, result - the run's
        #        payload, index - the observation, or None for the base stack
        # @return: None
        phot = result.get("photometry") or {}
        one = None
        if index is not None:
            per_obs = phot.get("per_obs") or []
            one = per_obs[index] if 0 <= index < len(per_obs) else None
        if one is not None and one.get("mag") is not None:
            header["NS_MAG"] = (float(one["mag"]),
                                "measured on this stack")
            if one.get("err") is not None:
                header["NS_MAGER"] = (float(one["err"]), "total error, mag")
            if one.get("n_comps") is not None:
                header["NS_MAGNC"] = (
                    int(one["n_comps"]),
                    "comparison stars holding the zero point")
            if one.get("check") is not None:
                header["NS_MAGOK"] = (1 if one["check"] else 0,
                                      "the check star's verdict")
            header["NS_MAGSR"] = ("measured", "measured by this run")
        elif phot.get("mag") is not None:
            header["NS_MAG"] = (
                float(phot["mag"]),
                "median brightness of the run" if index is not None
                else "run's median, measured on the observations' stacks")
            if phot.get("err") is not None:
                header["NS_MAGER"] = (float(phot["err"]), "total error, mag")
            if phot.get("n_comps") is not None:
                header["NS_MAGNC"] = (
                    int(phot["n_comps"]),
                    "comparison stars holding the zero point")
            header["NS_MAGSR"] = ("measured", "measured by this run")
        elif result.get("ephem_mag") is not None:
            # Nobody measured it here: the figure is what the ephemeris
            # predicts, and the band says so instead of showing nothing
            header["NS_MAG"] = (float(result["ephem_mag"]),
                                "predicted by the ephemeris, not measured")
            header["NS_MAGSR"] = ("ephemeris", "a prediction, not measured")
        if phot.get("band"):
            header["NS_MAGB"] = (str(phot["band"]),
                                 "band of the comparison stars")
        elif result.get("ephem_band"):
            header["NS_MAGB"] = (str(result["ephem_band"]),
                                 "band of the ephemeris' prediction")

    def _write_star_stack(self, index, result):
        # @args: index - the observation, result - the run's payload
        # @return: the path written, or None when the run kept no star stack
        # The second alignment of the same frames, saved as its own file so
        # the Photometry tab can read the comps on it. It carries the same
        # WCS (same box, same grid) and says what it is, so opening it never
        # asks a solver for stars that are, on the other stack, trails.
        import numpy as np
        stacks = result.get("star_stacks") or []
        if index >= len(stacks) or stacks[index] is None:
            return None
        stack, _rep = stacks[index]
        if stack is None:
            return None
        path = self._stack_path(index, stars=True)
        try:
            from astropy.io import fits
            hdu = fits.PrimaryHDU(np.asarray(stack, dtype=np.float32))
            wcss = result.get("wcs_by_group") or []
            if index < len(wcss) and wcss[index] is not None:
                hdu.header.update(wcss[index].to_header())
            hdu.header["NS_STACK"] = (
                "stars", "the stars are points")
            # the other half of the pair: the object's stack, in the same
            # folder, so whichever one is opened the tab knows the other
            hdu.header["NS_PAIR"] = self._stack_name(index)
            name = (self._context() or {}).get("object_name")
            if name:
                hdu.header["OBJECT"] = str(name)
            hdu.header["NS_NOBS"] = (int(index) + 1,
                                     "observation of the visit")
            groups = result.get("groups") or []
            if index < len(groups):
                hdu.header["NS_NFRAM"] = (
                    int(groups[index][1] - groups[index][0]),
                    "frames in this stack")
            # the star stack says the same as its pair (see
            # _write_provenance_cards): same frames, same combination
            _report = None
            _stars = result.get("star_stacks") or []
            if index < len(_stars) and _stars[index] is not None:
                _report = _stars[index][1]
            self._write_provenance_cards(hdu.header, result, _report)
            if self._run_id is not None:
                hdu.header["NS_RUN"] = (int(self._run_id),
                                        "the astrometry run it belongs to")
            # the same band data the object's stack carries (minus the
            # brightness: here the object is a trail), so the heading of the
            # star stack says the same date, "N × T s" and motion
            self._write_frame_meta(hdu.header, result, index)
            self._write_band_cards(hdu.header, result, index, stars=True)
            hdu.writeto(str(path), overwrite=True)
        except Exception as err:
            logger.warning("star stack write failed: %s", err)
            return None
        if self._view is not None:
            notify = getattr(host_of(self), "notify_saved", None)
            if callable(notify):
                notify([str(path)], "stack")
        return path

    def _on_blink(self):
        # @return: None. The figure is the honest way to look at a run
        #          whose observations do not agree: the eye catches a panel
        #          that is not the same sky far faster than a table. The
        #          menu picks the flavour; the work lives in _write_blink so
        #          it can be exercised without a modal menu.
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        act_gif = menu.addAction(self.tr("Blink (animated GIF)"))
        act_png = menu.addAction(self.tr("Montage (still PNG)"))
        chosen = menu.exec(self.btn_blink.mapToGlobal(
            self.btn_blink.rect().bottomLeft()))
        if chosen is None:
            return
        self._write_blink("gif" if chosen is act_gif else "png")

    def _write_blink(self, fmt):
        # @args: fmt - "gif" (blinking) or "png" (still montage)
        # @return: the written path, or None
        result = self._result or {}
        import numpy as np
        stacks = result.get("stacks") or []
        qs = result.get("qs") or []
        boxes = result.get("boxes") or []
        images, centers, labels = [], [], []
        for i, (stack, _rep) in enumerate(stacks):
            if stack is None or i >= len(qs):
                continue
            box = boxes[i] if i < len(boxes) else (0, 0, 0, 0)
            cx = qs[i][0] - box[0]
            cy = qs[i][1] - box[1]
            # the figure follows the app's screen orientation (data flipped
            # vertically): a blink that is upside down against the main
            # view is a blink nobody trusts
            images.append(np.flipud(np.asarray(stack, dtype=np.float32)))
            centers.append((cx, stack.shape[0] - 1 - cy))
            labels.append(self.tr("Obs. %1").replace("%1", str(i + 1)))
        if not images:
            return None
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from ..core.viz import sequence_view
        folder = None
        ask = getattr(host_of(self), "export_folder", None)
        if callable(ask):
            try:
                folder = ask()
            except Exception:
                folder = None
        import tempfile
        base = Path(folder) if folder else Path(tempfile.gettempdir())
        path = base / (self._stack_name(0).rsplit("_obs", 1)[0]
                       + "_observations." + fmt)
        try:
            sequence_view.centered_sequence(images, centers, path, fmt=fmt,
                                            label=labels)
        except Exception as err:
            logger.warning("blink figure failed: %s", err)
            self._say(self.tr("The blink figure could not be written:")
                      + f" {err}")
            return None
        if self._view is not None:
            notify = getattr(host_of(self), "notify_saved", None)
            if callable(notify):
                notify([str(path)], "sequence")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self._say(self.tr("Blink figure written:") + f" {path.name}")
        return path

    # ------------------------------------------------------ measurement

    def _fill_points(self):
        # The two ways per group (D7) and their contrast (D16): the Δ
        # column is the separation between the stack's position and the
        # per-frame one; a disagreement is flagged in its own column,
        # never chosen in silence.
        # @return: None
        from ..core import coords
        tbl = self.tbl_points
        points = self._result.get("points") or []
        mids = self._result.get("mids") or []
        tbl.setRowCount(len(points))
        for i, (sp, fp, flags) in enumerate(points):
            delta = ""
            if fp is not None and not math.isnan(fp.ra):
                cosd = max(math.cos(math.radians(sp.dec)), 1e-6)
                dra = (sp.ra - fp.ra) * cosd * 3600.0
                ddec = (sp.dec - fp.dec) * 3600.0
                delta = f"{math.hypot(dra, ddec):.2f}"
            warn = ", ".join(self._flag_text(f) for f in (flags or []))
            cells = (str(sp.group_index + 1),
                     self._t_mid_text(mids[i] if i < len(mids) else None),
                     coords.ra_deg_to_hms(sp.ra) if not math.isnan(sp.ra)
                     else "–",
                     coords.dec_deg_to_dms(sp.dec) if not math.isnan(sp.dec)
                     else "–",
                     delta,
                     f"{sp.snr:.1f}" if sp.snr else "–",
                     f"{sp.mag:.3f}" if sp.mag is not None else "–",
                     warn)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled)
                if col == 4:
                    item.setToolTip(self.tr(
                        "Separation between the stack measurement and the "
                        "per-frame one (the same centroid recipe on both)"))
                if col == 5:
                    # The number the observer compares with the floor, and
                    # the one they compare with the box on and off: it is the
                    # DETECTION's signal-to-noise, measured with the
                    # astrometry's own aperture, so the matched filter does
                    # not change it (it changes the brightness, whose own
                    # pair of SNRs the run's notes give).
                    item.setToolTip(self.tr(
                        "Signal-to-noise of the detection, measured with the "
                        "astrometry's own aperture: it is what the detection "
                        "gate, the position's error and the MPC floor use. "
                        "The matched filter does not change it; the "
                        "brightness measurement has its own pair, in the "
                        "notes"))
                if col == 6:
                    # The magnitude wears its role (core/chart_annotate): the
                    # same colour code as the plate's band and the curve, so
                    # green/orange/red mean the same thing everywhere. A run
                    # below the detection gate is measured anyway (ADR-062
                    # rev) and it comes out RED: it is a number to look at.
                    role = self._mag_role(i, sp.mag)
                    colour = palette.MEASURE_COLOURS.get(role) if role else None
                    if colour:
                        item.setForeground(QColor(colour))
                        item.setToolTip(self.tr(
                            "Green: a clean measurement. Orange: usable, but "
                            "not clean. Red: not to be published without "
                            "looking at it (see the notes)."))
                if col == 7 and text:
                    item.setToolTip(self.tr(
                        "The two measurements disagree: the point is "
                        "flagged, nothing is chosen in silence"))
                tbl.setItem(i, col, item)

    def _mag_role(self, index, mag):
        # @args: index - the observation, mag - the magnitude it shows
        # @return: the role that colours it (see chart_annotate.magnitude_role)
        #          or None when there is no measurement to colour.
        # The facts come from the run's own photometry (its per-observation
        # error, how many comparisons held the zero point and what the check
        # star said) plus the run's verdict, so the table cannot disagree
        # with the notes about whether the number is to be trusted.
        from ..core import chart_annotate
        if mag is None:
            return None
        phot = self._result.get("photometry") or {}
        per = phot.get("per_obs") or []
        info = per[index] if 0 <= index < len(per) and per[index] else {}
        return chart_annotate.magnitude_role({
            "mag": mag,
            "err": info.get("err"),
            "comps": info.get("n_comps"),
            "check_ok": info.get("check_ok"),
            "flags": (["below_gate"] if self._result.get("below_gate")
                      else [])})

    def _flag_text(self, flag):
        # @args: flag - a measurement flag from core/astrometry
        # @return: its human text (literal tr() strings so lupdate sees
        #          them; an unknown flag passes through, never hidden)
        if flag == "disagree":
            return self.tr("The two measurements disagree")
        if flag == "no_frame_centroid":
            return self.tr("No per-frame centroid")
        if flag == "mag_manual":
            return self.tr("Brightness written by hand in the Photometry tab")
        if flag == "manual":
            return self.tr(
                "Measured from the observer's mark (manual mode)")
        if flag == "below_gate":
            return self.tr(
                "The object did not clear the detection gate: it was "
                "measured at the ephemeris' position and is not to be "
                "published without looking at it")
        return str(flag)

    def _fill_check(self):
        # The verdict in plain language (D25/D29): available or not,
        # blocked or not, and the numbers behind it. Find_Orb missing is
        # SAID, never faked; without a reference nothing is blocked.
        # @return: None
        check = self._result.get("check")
        if check is None:
            return
        if not check.available:
            if str(check.note).startswith("Find_Orb is not configured"):
                text = self.tr(
                    "Find_Orb is not configured: the check is not "
                    "available. Set it up in Settings; meanwhile the "
                    "centred sequence and the submission floor are the "
                    "safety net.")
            else:
                text = self.tr("The check is not available:") \
                    + f" {check.note}"
        elif check.no_reference:
            text = self.tr(
                "No other observations to compare with: nothing is blocked "
                "(a real discovery has no reference); the centred sequence "
                "and the submission floor decide.")
        elif check.blocked:
            text = self.tr(
                "Our point is an outlier against the other observers: the "
                "report is blocked by default. Forcing it leaves the "
                "decision on record.")
        else:
            text = self.tr(
                "The check passes: our residual fits inside the published "
                "observations' dispersion.")
        if check.our_residual:
            text += " " + self.tr(
                "Our residual: %1″ / %2″ · %3 distinct observatories"
            ).replace("%1", f"{check.our_residual[0]:.2f}").replace(
                "%2", f"{check.our_residual[1]:.2f}").replace(
                "%3", str(check.n_stations))
        self.txt_check.setPlainText(text)
        # the verdict rides the block's header, so it is read WITHOUT
        # opening it (the block is folded by default)
        if not check.available:
            badge = self.tr("not available")
        elif check.no_reference:
            badge = self.tr("nothing to compare")
        elif check.blocked:
            badge = self.tr("blocked")
        else:
            badge = self.tr("passes")
        self._check_section.setNotice(
            badge, level="warn" if check.blocked else "info")
        self.chk_force.setEnabled(bool(check.blocked))
        if not check.blocked and self.chk_force.isChecked():
            self.chk_force.setChecked(False)

    # ------------------------------------------------------------ report

    def _sync_report_buttons(self):
        # The report exists only after a complete run, and an outlier
        # blocks it unless the observer forces it (D25): the buttons SAY
        # that with their enabled state instead of failing on click.
        # @return: None
        result = self._result or {}
        ok = result.get("status") == "ok" and bool(result.get("points"))
        check = result.get("check")
        blocked = bool(check is not None and check.blocked
                       and not self.chk_force.isChecked())
        self.btn_report.setEnabled(ok and not blocked)
        # A report with no observations is NOT a report: the box carries the
        # format's own header even then, so the text alone would enable the
        # button and the observer could paste an empty report into the visit
        # (measured 2026-10-06).
        self.btn_send_mpc.setEnabled(
            ok and not blocked and bool(self._report_kept))
        # the run's own undo (phase 8): enabled while there is a persisted
        # execution to take back. The door follows its buttons: a door that
        # opens onto a grey item is a lie (ADR-038).
        self.btn_undo.setEnabled(self._run_id is not None)
        from .widgets.door_menu import refresh_door
        refresh_door(self.btn_more)

    def _on_report(self, quiet=False):
        # The generator applies the submission floor itself (D26) and the
        # round trip through the validator (the generator that cannot pass
        # its own judge is our bug). The dropped groups are re-explained
        # here from the DATA, in the GUI's language: the core's notes are
        # internal English and never reach the user verbatim.
        # @args: quiet - True when the report is rebuilt while a visit is
        #        reopened: the text belongs in the box, but it is not news
        #        (the restore already said where the run came from)
        # @return: None
        from ..core import mpc_astrometry
        ctx = self._context() or {}
        points = [sp for sp, _fp, _fl
                  in (self._result or {}).get("points") or []]
        if not points:
            if not quiet:
                self._say(self.tr("Measure the sequence first."))
            return
        fmt = self.cmb_format.currentData() or "ades"
        rep = mpc_astrometry.generate(points, fmt,
                                      str(config.get("mpc_code", "")),
                                      ctx.get("object_name") or "", config)
        self.txt_report.setPlainText(rep["text"])
        floor = float(config.get("astrometry_submit_snr", 20.0))
        kept_n = len(rep.get("kept") or [])
        total_n = kept_n + len(rep.get("dropped") or [])
        self._report_kept = kept_n
        # WHAT CAME OUT, where the observer is looking (measured 2026-10-06:
        # a visit whose two observations were both below the floor produced a
        # report with the header and NOTHING else, and the reason was in a
        # group that is closed by default: it read as "the app generates
        # nothing").
        if kept_n:
            self.lbl_report_note.setText(self.tr(
                "%1 of %2 observations are in the report.").replace(
                    "%1", str(kept_n)).replace("%2", str(total_n)))
        else:
            self.lbl_report_note.setText(self.tr(
                "None of the %1 observations clears the submission floor "
                "you have set (SNR %2, in Settings → Astrometry; the MPC "
                "recommends 20): the report has no lines to send. Lower it "
                "there if you take the risk of a marginal detection.").replace(
                    "%1", str(total_n)).replace("%2", f"{floor:.0f}"))
        notes = []
        for point in rep.get("dropped") or []:
            snr = getattr(point, "snr", None)
            g = str(getattr(point, "group_index", "?"))
            if snr is None:
                notes.append(self.tr(
                    "Observation %1 left out: no SNR was measured, so it "
                    "cannot be shown to clear the floor of %2").replace(
                        "%1", g).replace("%2", f"{floor:.0f}"))
            else:
                notes.append(self.tr(
                    "Observation %1 left out: SNR %2 is below the MPC "
                    "submission floor of %3 (a marginal detection risks a "
                    "false tracklet)").replace("%1", g).replace(
                        "%2", f"{float(snr):.1f}").replace(
                        "%3", f"{floor:.0f}"))
        validation = rep.get("validation") or {}
        if not validation.get("valid", True):
            notes.extend(str(e) for e in (validation.get("errors") or [])[:3])
        # The same notes BOX the run fills: the report's "left out and why"
        # is part of the same story, and a box has its own height and scroll
        # (a label grew or clipped). The pre-rename code shared it too; the
        # rename to txt_notes missed this spot and crashed on Generate.
        # A QUIET rebuild (the visit was reopened) leaves that box alone: the
        # run's own notes are the run's story, and the report's notes are
        # news only when the observer asks for the report.
        if not quiet:
            self.txt_notes.setVisible(bool(notes))
            # the group appears when the report has something to say: its
            # "left out and why" is news, and news outside a group is what
            # the panel no longer does
            self._sections["notes"].setVisible(bool(notes))
            if notes:
                self.txt_notes.setPlainText("\n".join("• " + n for n in notes))
                # the group is closed by default: it says it holds something
                self._notify("notes", self.tr("⚠"), level="warn")
        # and the report's own group opens: there IS something to read in it
        self._sections["report"].setCollapsed(False)
        self._sync_report_buttons()
        kept = len(rep.get("kept") or [])
        if not quiet:
            self._say(self.tr("Report generated: %1 observations kept."
                              ).replace("%1", str(kept)))

    def _on_send_mpc(self):
        # The report lands in the visit's MPC paste box; ADR-022's
        # validator there has the last word (the round trip is the point:
        # our own output goes through the same judge as a pasted report).
        # @return: None
        text = self.txt_report.toPlainText().strip()
        if not text:
            self._say(self.tr("Generate the report first."))
            return
        dlg = host_of(self)
        send = getattr(dlg, "send_to_mpc_block", None)
        if callable(send) and send(text):
            self._say(self.tr(
                "Report sent to the visit's MPC block: its validator has "
                "the last word before saving."))
        else:
            self._say(self.tr(
                "The visit window is not open: open the visit to send the "
                "report to its MPC block."))
