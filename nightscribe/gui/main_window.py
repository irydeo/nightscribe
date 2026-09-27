############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Main window module (UX v3.1, ADR-019)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import logging
from pathlib import Path

from PySide6 import Shiboken
from PySide6.QtCore import (QCoreApplication, QSize, Qt, Signal,
                            QPropertyAnimation, QEasingCurve, QTimer)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
                                QFormLayout, QGroupBox, QHBoxLayout,
                                QInputDialog, QLabel, QLineEdit,
                                QListWidget, QListWidgetItem, QMainWindow,
                                QMessageBox, QProgressBar, QProgressDialog,
                                QPushButton, QScrollArea,
                                QSpinBox, QDoubleSpinBox, QComboBox,
                                QCheckBox, QDialogButtonBox, QTextEdit,
                                QVBoxLayout, QWidget, QTableWidgetItem)

from .. import paths
from ..config import config
from ..version import full_version
from ..core import (attention, dates, ephemeris, kinds, mpc_report, orbits,
                    project, sequence, suggest)
from ..core.db import db
from . import pretty, theme
from .overview import ObjectPanel
from .skeleton import ShimmerRow
from .widgets.passive_wheel import (PassiveDoubleSpinBox, PassiveList,
                                    PassiveSpinBox)
from .widgets.campaign_row import CampaignRow
from .widgets.project_row import ProjectRow
from .widgets.sparkline import sparkline_pixmap
from .workers import (BlinkExportWorker, BlinkWorker, CcdcielWorker,
                      ExploreWorker, MpcResolveWorker, PostWorker, SunWorker,
                      TonightWorker)

logger = logging.getLogger(__name__)

# the shared .ui loader (ADR-005): it lives in gui/ui_loader.py; this
# alias keeps the house's imports and the pinned tests working
from .ui_loader import load_ui as _load_ui
from .ui_loader import UI_DIR

# Three guided steps for every project kind. The old "analyse" step (ADR-019,
# review 2026-08-28) was dropped, and "capture" merged into "plan" (ADR-030,
# 2026-09-06): planning the session and exporting/running it against CCDciel
# is one step (it now reads "Captura" under the ADR-043 rename). ADR-045
# (2026-09-24): "process" is renamed "analysis" — the flow reads Ficha →
# Captura → Análisis → Publicación and the Analysis tab is built around
# visits for every kind.
_STEP_KEYS = ("plan", "analysis", "publish")

# The pages of the project detail (ADR-041): the object card and the
# three steps. ONE page is visible at a time — the tab bar in the
# masthead decides which. The step pages are built lazily on first open
# and cached until the project changes. ADR-045: the old kind-gated
# follow-up tab is gone; its content lives in the Analysis tab and the
# "process"/"followup" deep-link keys alias to "analysis" forever.
_TAB_KEYS = ("details",) + _STEP_KEYS

# A2: outcome keys (from project.OUTCOMES) → human labels, by language.
# The editable combo stores the key (English) and shows the label; «Otro»
# is free text that passes through close() untouched.
_OUTCOME_LABELS = {
    "confirmed_ia": {"es": "Ia confirmada", "en": "Confirmed Ia"},
    "confirmed_other": {"es": "Confirmada (otro tipo)", "en": "Confirmed (other)"},
    "false_positive": {"es": "Falso positivo", "en": "False positive"},
    "lost": {"es": "Perdida", "en": "Lost"},
    "completed": {"es": "Completado", "en": "Completed"},
    "reported_mpc": {"es": "Reportado al MPC", "en": "Reported to MPC"},
    "reported_exoclock": {"es": "Reportado a ExoClock", "en": "Reported to ExoClock"},
    "reported_aavso": {"es": "Reportada a la AAVSO", "en": "Reported to AAVSO"},
    "abandoned": {"es": "Abandonado", "en": "Abandoned"},
}
# SC2 (ADR-040): the sky-event chips in the Tonight header — the big
# things first. One chip per family, at most three.
_SKY_CHIP_PRIORITY = {
    "lunar_eclipse": 100, "solar_eclipse": 100,
    "shadow_transit": 95, "sat_transit": 90,
    "opposition": 80, "max_elongation": 70, "planet_conjunction": 65,
    "moon_conjunction": 60, "meteor_shower": 50,
    "full_moon": 45, "new_moon": 45, "first_quarter": 40,
    "last_quarter": 40, "perigee": 30, "apogee": 25,
    "sun_conjunction": 20,
}


# Kinds with multi-night photometry follow-up (the tab is kind-agnostic;
# SN-only analysis buttons hide for the others)
# Track V: variables join (V-g: the quick-look engine serves them unchanged)
FOLLOWUP_KINDS = project.FOLLOWUP_KINDS
# ADR-043: the bar reads left to right like the night itself runs, so the
# tabs carry the plain action word and the "→" separators do the
# connecting. The five names are fixed by the project owner (Ficha,
# Captura, Procesado, Publicar, Seguimiento), so they live here as plain
# per-language pairs instead of tr() anchors
_STEP_LABELS_ES = {"details": "Ficha", "plan": "Captura",
                   "analysis": "Análisis", "publish": "Publicar"}
_STEP_LABELS_EN = {"details": "Object card", "plan": "Capture",
                   "analysis": "Analysis", "publish": "Publish"}


def tr(fmt, *sub):
    # Translate + fill, for helper code that lives outside the window class
    # (the SC2 signal rows, ...). Values go in AFTER the lookup, so the
    # translator may reorder them.
    # @args: fmt - source string with %1, %2, ... slots, sub - slot values
    # @return: localized string, slots filled
    t = QCoreApplication.translate("MainWindow", fmt)
    for i, val in enumerate(sub, 1):
        t = t.replace(f"%{i}", str(val))
    return t


def _settings_two_columns(dlg):
    # @args: dlg - the settings dialog (holds QTabWidget > pages > QGroupBox)
    # @return: re-lays every tab page into two side-by-side columns. The
    #          page keeps its original QVBoxLayout; a nested QHBoxLayout
    #          of two placeholder widgets is appended to it, and the
    #          QGroupBox children (original order) are reparented into
    #          the lighter column. Keeps .ui flat (single column of
    #          groups) so Qt Designer stays friendly; only visual height
    #          changes here.
    from PySide6.QtWidgets import (QTabWidget, QGroupBox, QWidget,
                                   QHBoxLayout, QVBoxLayout)
    tw = dlg.findChild(QTabWidget)
    if tw is None:
        return
    for i in range(tw.count()):
        page = tw.widget(i)
        groups = [w for w in page.findChildren(QGroupBox)
                  if w.parent() is page]
        if len(groups) < 2:
            continue
        old = page.layout()          # the page's original QVBoxLayout
        if old is None:
            continue
        # empty the page's vbox (widgets go back to a plain parent state)
        while old.count():
            old.takeAt(0)
        cols = QHBoxLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(14)
        cols.setStretch(0, 1)
        cols.setStretch(1, 1)
        c = [QWidget(page), QWidget(page)]
        v = [QVBoxLayout(c[k]) for k in range(2)]
        for k in range(2):
            v[k].setContentsMargins(0, 0, 0, 0)
            v[k].setSpacing(10)
        col_h = [0, 0]
        col_w = [0, 0]
        for g in groups:
            k = 0 if col_h[0] <= col_h[1] else 1
            g.setParent(c[k])
            v[k].addWidget(g)
            col_h[k] += max(g.sizeHint().height(), 1)
            # a group's natural width is the width at which its widest field
            # row (label + field + button) fits; recording the max per column
            # lets us floor it below so the wide rows are never squeezed.
            col_w[k] = max(col_w[k], g.sizeHint().width())
        cols.addWidget(c[0])
        cols.addWidget(c[1])
        # Floor each column's width at its content's natural width so the
        # wide field rows are not clipped and the help labels wrap to fewer
        # (non-overlapping) lines; equal stretch still lets the dialog grow
        # and share the leftover space between the two.
        c[0].setMinimumWidth(col_w[0])
        c[1].setMinimumWidth(col_w[1])
        old.addLayout(cols)


# Per-kind table columns for the full (collapsed) table
TABLE_COLS = {
    "neo": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
            ("Max alt", "max_alt"), ("Best time (UTC)", "best_time"),
            ("NEOfixer", "nf"), ("NObs", "nobs"), ("MOID (AU)", "moid"),
            ("Discovered", "disc"), ("Covered", "obs")],
    "sn": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
           ("SN type", "sn_type"), ("Host galaxy", "host"),
           ("Discovered", "disc"), ("Max alt", "max_alt"), ("Covered", "obs")],
    "comet": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
               ("Perihelion", "perihelion"), ("Max alt", "max_alt"),
               ("Best time (UTC)", "best_time"), ("Covered", "obs")],
    "pccp": [("Object", "name"), ("Score", "score"), ("PCCP score", "pccp"),
             ("Mag", "mag"), ("Arc (days)", "arc"), ("NObs", "nobs"),
             ("Max alt", "max_alt"), ("Covered", "obs")],
    "transit": [("Object", "name"), ("Score", "score"),
                ("Star mag", "mag"), ("Window (UTC)", "window"),
                ("Depth", "depth"), ("Max alt", "max_alt"),
                ("Covered", "obs")],
    "hads": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
             ("Period", "period"), ("Amp", "amp"), ("Cycles", "cycles"),
             ("Max alt", "max_alt"), ("Best time (UTC)", "best_time"),
             ("Covered", "obs")],
    "variable": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
                 ("Period (d)", "vperiod"), ("Next extremum", "vext"),
                 ("Campaign", "camp"), ("Max alt", "max_alt"),
                 ("Best time (UTC)", "best_time"), ("Covered", "obs")],
    "alert": [("Object", "name"), ("Approach date", "adate"),
              ("Distance (LD)", "ald"), ("Diameter (m)", "adiam"),
              ("Max mag", "amag"), ("Velocity (km/s)", "avel"),
              ("Covered", "obs")],
}
TABLE_COLS_DEFAULT = [("Object", "name"), ("Type", "kind"),
                      ("Campaign", "camp"), ("Score", "score"),
                      ("Mag", "mag"), ("Max alt", "max_alt"),
                      ("Best time (UTC)", "best_time"), ("NEOfixer", "nf"),
                      ("NObs", "nobs"), ("Discovered", "disc"),
                      ("Covered", "obs")]

# Canonical kind order (core/kinds.py catalogue, ADR-042): the tonight
# filter, the settings whitelist and the update wizard all read it, so
# the kinds stay in the same order wherever they are shown.
KIND_ORDER = list(kinds.ids())

# Top-level tab indices (ui/main_window.ui order; ADR-036: History left
# the bar for the Tools-menu journal dialog, J0): never use literals for
# the main tabs.
# UX-PC + SC2 (ADR-038/040): the Sun & sky content moved to the Tools
# menu as the "Sky calendar…" dialog; ADR-043 folds the Observatory tab
# into the project's Capture step, leaving three top-level tabs
TAB_TONIGHT, TAB_PROJECTS, TAB_CAMPAIGNS = range(3)


class _ClickableFrame(QFrame):
    # A frame that re-emits a plain mouse click anywhere over it (the
    # row's «explore» hook). Child labels without text selection forward
    # the event here; the action button keeps its own click.

    clicked = Signal()

    def mousePressEvent(self, event):
        # The click opens a modal dialog (explore) synchronously from inside
        # this event; a pending row deleteLater() can then run inside that
        # nested loop and destroy the C++ object before we return. The row
        # is rebuilt anyway, so swallow the stale-object RuntimeError.
        try:
            if event.button() == Qt.LeftButton:
                self.clicked.emit()
            super().mousePressEvent(event)
        except RuntimeError:
            pass


class _LinkChip(QLabel):
    # A chip that behaves like a link (UX-c): hand cursor + clicked
    # signal that CONSUMES the event, so a clickable parent row never
    # fires when the chip is the real target.
    clicked = Signal()

    def __init__(self, text, color, tip=""):
        super().__init__(text)
        self.setStyleSheet(theme.chip_style(color))
        if tip:
            self.setToolTip(tip)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, ev):
        ev.accept()
        self.clicked.emit()


class _ScoreBar(QFrame):
    # The 4-segment score meter: scientific / observability / urgency / hook.
    # Each segment is 25% of the width, filled proportionally to the part
    # (0-35 / 0-30 / 0-20 / 0-15), painted in the object's kind color.

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = color
        self._parts = (0.0, 0.0, 0.0, 0.0)
        self._maxes = (35.0, 30.0, 20.0, 15.0)
        self.setMinimumSize(120, 8)
        self.setFixedHeight(8)

    def set_parts(self, parts):
        # @args: parts - dict from suggest.score_target
        self._parts = (parts.get("scientific", 0.0),
                       parts.get("observability", 0.0),
                       parts.get("urgency", 0.0),
                       parts.get("hook", 0.0))
        self.update()

    def paintEvent(self, _event):
        from PySide6.QtGui import QBrush, QColor, QPainter
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        # empty track
        p.fillRect(self.rect(), QColor(theme.C_LINE))
        # four segments of w/4 each, with a 2px gap between them
        gap = 2
        seg = (w - 3 * gap) / 4.0
        for i in range(4):
            frac = self._parts[i] / self._maxes[i]
            fill = max(0.0, min(seg, frac * seg))
            x = i * (seg + gap)
            if fill > 0.5:
                p.fillRect(QRectF(x, 0, fill, self.height()),
                           QBrush(QColor(self._color)))
        p.end()


class MainWindow(QMainWindow):
    # Three tabs (ADR-043): Tonight · Projects · Campaigns: the CCDciel
    # control now lives inside the project's Capture step. The Tools menu
    # holds the Sky calendar, the observing journal, and the contextual
    # Explore/Post/Blink dialogs.

    def __init__(self):
        super().__init__()
        self._tonight_top = []
        self._tonight_all = []
        self._workers = []
        self._blink_pair = None
        self._blink_ref8 = None
        self._blink_obs8 = None
        self._blink_nudge = [0.0, 0.0]
        self._blink_phase = False
        self._current_project = None
        self._project_widgets = {}
        # ADR-043: the CCD block lives inside the open project's Capture
        # step, so this registry dies with the page (and rebirths with it)
        self._obs_widgets = {}
        self._skycal = None       # lazy Sky calendar dialog (SC2/ADR-040)
        self._proj_panel = None   # reusable ObjectPanel (phase D4), lazy
        self._tab_pages = {}  # ADR-041: key -> tab page QWidget ("details"|...)
        self._active_tab = None  # key of the visible tab page (or None)
        self._advisor_dismissed = None  # A2: id of the project whose advisor
        #                                the user dismissed this session

        # CCDciel integration (ADR-030). The connection survives project
        # switches: the observatory does not re-connect per target.
        self._ccd_client = None
        self._ccd_connected = False
        self._ccd_filter_names = []
        self._ccd_version = ""
        self._ccd_worker = None
        self._ccd_point_target = None  # last project a goto/astrometry aimed at
        self._ccd_timer = QTimer(self)
        self._ccd_timer.setInterval(1500)
        self._ccd_timer.timeout.connect(self._ccd_poll_tick)

        win = _load_ui("main_window")
        self.setWindowTitle(f"{win.windowTitle()} {full_version()}")
        self.setCentralWidget(win.centralwidget)
        self.setStatusBar(win.statusbar)
        self.setMenuBar(win.menubar)
        self.resize(self._initial_size())
        self._menus = win
        self._build_status_progress()

        self._build_tabs()
        self._connect_menu()
        self._connect()
        # Projects are visible from the very first open: load the hub list
        # once the event loop starts (a deferred singleShot reads only the
        # local SQLite, never the network). The "Refresh" button stays as a
        # fallback, and _on_main_tab_changed keeps the list fresh on every
        # visit to the Projects tab.
        QTimer.singleShot(0, self.on_refresh_projects)
        # SC2: the sky-event chips are local maths — no need to wait for
        # the network tonight computation
        QTimer.singleShot(0, self._skyevent_chips)
        if config.get("ccdciel_auto_connect", False):
            # ADR-030: opt-in, off by default — connecting an observatory is
            # a human decision, not something the app does silently.
            QTimer.singleShot(600, self._ccd_connect)
        self.statusBar().showMessage(
            f"NightScribe {full_version()} — "
            + self.tr("Ready — press 'Compute tonight'"), 8000)
        if config.is_configured():
            QTimer.singleShot(400, self.on_compute_tonight)
        self._now_timer = QTimer(self)
        self._now_timer.timeout.connect(self._refresh_now_badges)
        self._now_timer.start(5 * 60 * 1000)
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink_tick)
        self._blink_render_timer = QTimer(self)
        self._blink_render_timer.setSingleShot(True)
        self._blink_render_timer.setInterval(120)
        self._blink_render_timer.timeout.connect(self._blink_render)

    def _build_status_progress(self):
        # One global progress bar, docked to the RIGHT of the status bar (the
        # standard Qt spot for the current action). It stays hidden and is
        # shown while "Compute tonight" runs; it is a pure visual gauge (no
        # text on the bar — the message text lives beside it and in the
        # header, see _tonight_progress). We use addPermanentWidget on purpose:
        # a widget in the normal (left) area sits *behind* the area that
        # showMessage() paints into, so the bar would cover the message.
        bar = QProgressBar()
        bar.setObjectName("status_progress")
        bar.setFixedHeight(18)
        bar.setFixedWidth(180)
        bar.setTextVisible(False)         # the bar is the gauge, text is elsewhere
        bar.setFormat("")
        bar.setRange(0, 0)                # busy (indeterminate) by default
        bar.setStyleSheet(
            "QProgressBar#status_progress { border: 1px solid %s;"
            " border-radius: 4px; background: %s; }"
            "QProgressBar#status_progress::chunk {"
            " background: %s; border-radius: 3px; }" %
            (theme.C_LINE, theme.C_BASE, theme.C_ACCENT))
        bar.setVisible(False)
        self.statusBar().addPermanentWidget(bar)   # right (next to the size grip)
        self._status_progress = bar
        # smooth gauge: the value animates between steps instead of jumping
        self._bar_anim = QPropertyAnimation(self._status_progress, b"value", self)
        # one shared clock drives every skeleton row's shimmer
        self._skeleton_timer = QTimer(self)
        self._skeleton_timer.timeout.connect(self._skeleton_tick)
        self._skeleton_rows = []

    def _skeleton_tick(self):
        # Repaints every skeleton row with the current shimmer position
        for row in self._skeleton_rows:
            row.update()

    # ---------------- helpers ----------------

    def _lang(self):
        # @return: "es"|"en" — single source of truth in pretty.ui_lang()
        return pretty.ui_lang()

    def _txt(self, pair):
        return orbits.pick(pair, self._lang())

    def _step_label(self, key):
        labels = _STEP_LABELS_ES if self._lang() == "es" else _STEP_LABELS_EN
        return labels.get(key, key)

    def _initial_size(self):
        # ~90% of the screen's available area (menu bar + task bar already
        # excluded), with a sane floor for small displays. Adapts to any
        # resolution/DPI instead of a fixed 1200x800.
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QSize(1200, 800)
        g = screen.availableGeometry()
        return QSize(max(int(g.width() * 0.9), 640),
                     max(int(g.height() * 0.9), 480))

    def _goto_tab(self, index):
        from PySide6.QtWidgets import QTabWidget
        self.centralWidget().findChild(QTabWidget, "tabs").setCurrentIndex(index)

    # ---------------- tab construction ----------------

    def _build_tabs(self):
        from PySide6.QtWidgets import QTabWidget
        tabs = self.centralWidget().findChild(QTabWidget, "tabs")
        widgets = (self.tonight, self.projects, self.campaigns) = (
            _load_ui("tonight_tab"), _load_ui("projects_tab"),
            _load_ui("campaigns_tab"))
        for i, w in enumerate(widgets):
            title = tabs.tabText(i)
            tabs.removeTab(i)
            tabs.insertTab(i, w, title)
        tabs.setCurrentIndex(0)
        # UX-PC (plain-language rule): every tab explains itself in one
        # line on hover — no concept is taken for granted
        tabs.setTabToolTip(TAB_TONIGHT, self.tr(
            "Tonight's best objects from your observatory"))
        tabs.setTabToolTip(TAB_PROJECTS, self.tr(
            "Your projects: one object with its three steps: capture, "
            "track, follow-up — and what needs your attention"))
        tabs.setTabToolTip(TAB_CAMPAIGNS, self.tr(
            "Observing campaigns: several nights, several observatories, "
            "one shared goal"))
        # table starts collapsed
        self.tonight.grp_list.setVisible(False)
        self._prepare_table()
        # remember and restore the Tonight kind filter (WORKFLOWS 7quater):
        # the combo starts empty, so populate it from the enabled kinds and
        # re-select last night's choice if it is still enabled
        self._rebuild_kind_filters()
        saved = config.get("tonight_kind", "") or None
        if saved and self.tonight.cmb_filter.findData(saved) >= 0:
            self.tonight.cmb_filter.setCurrentIndex(
                self.tonight.cmb_filter.findData(saved))

        # A3: restore the projects hub classification prefs
        self.projects.cmb_kind.setCurrentIndex(
            int(config.get("projects_filter_kind", 0)))
        # UX-PC (U2): the sort combo gained "Needs you" at index 0 — a new
        # config key keeps old prefs from pointing at the wrong order
        sort_idx = int(config.get("projects_filter_sort_v2", 0))
        sort_idx = max(0, min(sort_idx, self.projects.cmb_sort.count() - 1))
        self.projects.cmb_sort.setCurrentIndex(sort_idx)
        self.projects.chk_favorites.setChecked(
            bool(config.get("projects_filter_fav", False)))
        # UX-PC (U2): the right pane starts on the dashboard (no selection)
        self.projects.stack_detail.setCurrentWidget(
            self.projects.page_dashboard)
        # UX-PC (U1): the advanced filters row starts collapsed; the toggle
        # restores the user's last choice
        filters_open = bool(config.get("projects_filters_open", False))
        self.projects.filters_box.setVisible(filters_open)
        self.projects.btn_filters.blockSignals(True)
        self.projects.btn_filters.setChecked(filters_open)
        self.projects.btn_filters.setText(
            self.tr("Filters ▾") if filters_open else self.tr("Filters ▸"))
        self.projects.btn_filters.blockSignals(False)

    def _prepare_table(self):
        # One-time table setup (UX v3 phase C): the row is the unit, not the
        # cell — no default 2x2 selection, no row numbers. The per-kind column
        # set is installed by _fill_table() once targets exist.
        from PySide6.QtWidgets import QAbstractItemView
        tbl = self.tonight.tbl_targets
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        tbl.verticalHeader().setVisible(False)
        tbl.setColumnCount(0)
        tbl.setRowCount(0)

    def _connect_menu(self):
        self._menus.action_quit.triggered.connect(self.close)
        self._menus.action_settings.triggered.connect(self.on_open_settings)
        self._menus.action_about.triggered.connect(self.on_about)
        self._menus.action_sources.triggered.connect(self.on_sources)
        self._menus.action_docs.triggered.connect(self.on_docs)
        self._menus.action_explore.triggered.connect(self._tools_explore)
        self._menus.action_blink.triggered.connect(self._tools_blink)
        self._menus.action_campaigns.triggered.connect(
            self._tools_campaigns)

    def _connect(self):
        t = self.tonight
        # Refresh the Projects hub list every time the user enters that
        # tab, so it is always up to date (UX-PC U1: the manual Refresh
        # fallback button is gone — the list never goes stale).
        from PySide6.QtWidgets import QTabWidget
        self.centralWidget().findChild(
            QTabWidget, "tabs").currentChanged.connect(
                self._on_main_tab_changed)
        t.btn_compute.clicked.connect(self.on_compute_tonight)
        t.btn_show_all.toggled.connect(self._toggle_table)
        # one filter rules grid + table (WORKFLOWS 7quater): the header combo
        # changes both views at once
        t.cmb_filter.currentIndexChanged.connect(self._apply_kind_filter)
        # "show observed" only reshapes the table, the grid keeps its podium
        # (a lambda: the check-state int must not leak into want=)
        t.chk_show_observed.stateChanged.connect(lambda _s: self._fill_table())
        t.tbl_targets.cellDoubleClicked.connect(self._table_open_explore)
        p = self.projects
        # UX-PC (U1): the list refreshes itself on every tab visit — no
        # manual Refresh button; the advanced filters live collapsed
        # behind the Filters ▸ toggle (state persisted in config).
        p.cmb_filter.currentIndexChanged.connect(self.on_refresh_projects)
        p.cmb_campaign.currentIndexChanged.connect(
            lambda _i: self.on_refresh_projects())
        p.btn_filters.toggled.connect(self._project_filters_toggled)
        from PySide6.QtWidgets import QMenu
        manage = QMenu(self)
        manage.aboutToShow.connect(self._rebuild_manage_menu)
        p.btn_manage.setMenu(manage)
        p.lst_projects.itemSelectionChanged.connect(self._project_selected)
        # UX-c: one gesture language — double-click/Enter opens the
        # project at its current step, right-click offers every action,
        # the hand cursor advertises clickability.
        p.btn_new_project.clicked.connect(self._tools_explore)
        p.lst_projects.itemActivated.connect(
            self._project_open_activated)
        p.lst_projects.setContextMenuPolicy(Qt.CustomContextMenu)
        p.lst_projects.customContextMenuRequested.connect(
            self._project_context_menu)
        p.lst_projects.viewport().setCursor(Qt.PointingHandCursor)
        # UX-d: the masthead campaign badge is a link to the Campaigns tab
        # (openExternalLinks stays off in the .ui so linkActivated fires
        # here instead of the browser)
        self.projects.lbl_mast_camp.linkActivated.connect(
            self._campaign_link_clicked)
        # A4 (rewritten): the project files window (ADR-019, UX v3). The
        # masthead "Files (n)" button is the single entry; the dialog
        # owns its row menus and the main window owns the two open
        # routes (FITS editor / OS) plus the button's live count.
        self.projects.btn_files.clicked.connect(
            self._show_project_files)
        # ADR-041: the tab bar — the object card, the three steps and
        # the follow-up view. A click opens that page (lazily built on
        # first open), like any other deep link.
        for key in _TAB_KEYS:
            btn = getattr(p, f"btn_tab_{key}")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(
                lambda _=False, k=key: self._show_tab(k))
        # UX-i: « / » — fold the list column away for more detail room
        # (and bring it back); the choice is remembered across sessions
        p.btn_hide_list.clicked.connect(
            lambda: self._toggle_project_list(False))
        p.btn_show_list.clicked.connect(
            lambda: self._toggle_project_list(True))
        if config.get("projects_list_hidden", 0):
            self._toggle_project_list(False)
        c = self.campaigns
        c.lst_campaigns.itemSelectionChanged.connect(
            self._campaign_selected)
        c.lbl_urls.linkActivated.connect(self._open_url)
        c.tbl_members.cellDoubleClicked.connect(self._campaign_member_opened)
        c.lst_campaigns.setContextMenuPolicy(Qt.CustomContextMenu)
        c.lst_campaigns.customContextMenuRequested.connect(
            self._campaign_context_menu)
        c.tbl_members.setContextMenuPolicy(Qt.CustomContextMenu)
        c.tbl_members.customContextMenuRequested.connect(
            self._campaign_member_menu)
        c.lst_campaigns.viewport().setCursor(Qt.PointingHandCursor)
        c.tbl_members.viewport().setCursor(Qt.PointingHandCursor)
        c.lst_signals.itemActivated.connect(self._camp_signal_opened)
        c.lst_signals.viewport().setCursor(Qt.PointingHandCursor)
        c.btn_new.clicked.connect(self._camp_new)
        # UX-PC (U5): the selected campaign's actions live in the detail
        # header — Edit / Close|Reopen (one state-aware button) / ⋯ (the
        # rest). Real enablement: disabled with no selection.
        c.btn_cedit.clicked.connect(self._camp_edit)
        c.btn_cclose.clicked.connect(self._camp_close_or_reopen)
        from PySide6.QtWidgets import QMenu as _QMenu
        cmore = _QMenu(self)
        cmore.aboutToShow.connect(self._rebuild_cmore_menu)
        c.btn_cmore.setMenu(cmore)
        # ⓘ help (plain-language rule): what a campaign IS, right where
        # the user meets the concept
        c.btn_help.clicked.connect(self._campaign_help)
        # U7: the "Happening now" strip explains its own icons (⚡ ⏳ 👁)
        c.btn_signals_help.clicked.connect(self._campaign_signals_help)
        c.lst_campaigns.currentItemChanged.connect(
            self._campaign_row_selection_sync)
        # U0.2: itemSelectionChanged is not re-emitted for the row that
        # is already selected, so a click on it used to be a no-op. It
        # now retries the detail load (e.g. after a failed enrich).
        p.lst_projects.itemClicked.connect(self._project_reclicked)
        # UX-PC (U1): the lifecycle actions (close/reopen/archive/delete)
        # live in the header's ⋯ manage menu now, not in footer buttons.
        p.cmb_kind.currentIndexChanged.connect(self.on_refresh_projects)
        p.edt_search.textChanged.connect(self.on_refresh_projects)
        p.edt_tag.textChanged.connect(self.on_refresh_projects)
        p.cmb_sort.currentIndexChanged.connect(self.on_refresh_projects)
        p.chk_favorites.stateChanged.connect(self.on_refresh_projects)
        # A3: favorite star toggle in the project header (tags live in the
        # ⋯ manage menu since UX-PC U1)
        p.btn_favorite.clicked.connect(self._project_toggle_favorite)
        p.btn_next_go.clicked.connect(
            lambda: self._scroll_to_section(self._next_target))
        # UX-PC (U3): the Next card is the step machine's command center:
        # "Mark done" for the CURRENT step lives beside Go (the foot of a
        # step page only offers "Reopen step" on finished steps, ADR-043)
        p.btn_next_done.clicked.connect(self._next_done)
        # UX-PC (U2): ⌂ goes back to the dashboard (clearing the selection
        # fires itemSelectionChanged -> the detail pane swaps itself)
        p.btn_home.clicked.connect(
            lambda: p.lst_projects.clearSelection())
        p.lst_projects.currentItemChanged.connect(
            self._project_row_selection_sync)
        # A2: click on the advisor banner dismisses it for this session
        self._advisor_dismissed = None
        self.projects.lbl_advisor.mouseReleaseEvent = \
            lambda _e: self._advisor_dismiss()
        self.projects.lbl_advisor.setCursor(Qt.PointingHandCursor)
        # SC2 (ADR-040): the Sun & sky content lives in the Tools menu as
        # the "Sky calendar…" dialog — its widgets are wired when the
        # dialog is first built (_skycal_build), not here.
        # ADR-036 (J0): the journal lives in the Tools menu, not in the
        # tab bar; Ctrl+1..3 switches the three main tabs (ADR-043 cut
        # the fourth).
        self._menus.action_journal.triggered.connect(
            self._open_journal_dialog)
        self._menus.action_skycal.triggered.connect(self._tools_skycal)
        # ADR-044: the Unified FITS Editor lives in the Tools menu too
        self._menus.action_ufe.triggered.connect(self._tools_ufe)
        from PySide6.QtGui import QKeySequence, QShortcut
        for i, tab_idx in enumerate((TAB_TONIGHT, TAB_PROJECTS,
                                     TAB_CAMPAIGNS)):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(lambda idx=tab_idx: self._goto_tab(idx))

    def _open_url(self, url):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    # ---------------- menu: settings / help ----------------

    def on_open_settings(self):
        dlg = _load_ui("settings_dialog")
        # 3-tab layout with per-field help labels BELOW each widget —
        # see ADR-028. The .ui carries structure + text; the 11 px dim
        # styling for the lblH_* labels is applied here so the .ui stays
        # tool-friendly and theme.py untouched.
        # style every help-below-field label: 11 px, dim.
        # The .ui sets wordWrap=true + top-aligned; the label wraps to the
        # width of its group (~half the dialog after the two-column reflow)
        # so long texts stay readable.
        from PySide6.QtWidgets import QLabel
        for w in dlg.findChildren(QLabel):
            if w.objectName().startswith("lblH_"):
                w.setStyleSheet("font-size: 11px; color: #8a90a6;")
                w.setWordWrap(True)
        # two-column grid per tab: stack the flat QGroupBox children
        # side by side (balanced by cumulative height) so the dialog
        # stays short instead of a tall single stack. Each column is
        # floored at its content's natural width so wide groups (site,
        # horizon, storage) keep their label+field+button rows unclipped.
        _settings_two_columns(dlg)
        # fit the widest tab's two content-floored columns: the dialog's
        # sizeHint grows with the column minimums, and each column is
        # already floored at its groups' natural width so the label+field+
        # button rows are never clipped and the help text wraps to a couple
        # of non-overlapping lines.
        dlg.resize(max(820, dlg.sizeHint().width()), dlg.sizeHint().height())
        dlg.edt_mpc_code.setText(config.get("mpc_code", ""))
        dlg.edt_obs_name.setText(config.get("observatory_name", ""))
        dlg.spn_lat.setValue(float(config.get("lat", 0)))
        dlg.spn_lon.setValue(float(config.get("lon", 0)))
        dlg.spn_height.setValue(int(config.get("height", 0)))
        dlg.spn_aperture.setValue(float(config.get("aperture_inches", 10)))
        dlg.chk_transit_scope_filter.setChecked(
            bool(config.get("transit_scope_filter", True)))
        dlg.spn_limit_mag.setValue(float(config.get("limit_mag", 20)))
        dlg.spn_min_alt.setValue(float(config.get("min_alt", 30)))
        dlg.edt_neofixer_key.setText(config.get("neofixer_key", ""))
        dlg.edt_astrometry_key.setText(config.get("astrometry_key", ""))
        dlg.spn_pixel_um.setValue(float(config.get("pixel_um", 3.76)))
        dlg.spn_focal_mm.setValue(float(config.get("focal_mm", 2000)))
        # Track D (EXOTIC handoff): AAVSO code, camera type and binning
        dlg.edt_aavso_code.setText(config.get("aavso_code", ""))
        dlg.edt_aavso_token.setText(config.get("aavso_api_token", ""))
        dlg.cmb_camera_type.addItems(["CCD", "CMOS", "DSLR"])
        dlg.cmb_camera_type.setCurrentText(config.get("camera_type", "CCD"))
        dlg.cmb_binning.addItems(["1x1", "2x2", "3x3"])
        dlg.cmb_binning.setCurrentText(config.get("pixel_binning", "1x1"))
        # Chart annotations (ADR-046): the identity stamped in the corner
        # boxes and the two style switches
        dlg.edt_observer.setText(config.get("observer_name", ""))
        dlg.edt_measurer.setText(config.get("measurer_name", ""))
        dlg.edt_telescope.setText(config.get("telescope_desc", ""))
        dlg.edt_camera_model.setText(config.get("camera_model", ""))
        dlg.cmb_marker_style.addItem(self.tr("Ring with ticks (classic)"),
                                     "ring")
        dlg.cmb_marker_style.addItem(self.tr("Full-frame cross with box"),
                                     "cross")
        dlg.cmb_marker_style.setCurrentIndex(
            1 if config.get("marker_style", "ring") == "cross" else 0)
        dlg.chk_chart_boxes.setChecked(
            bool(config.get("chart_boxes", False)))
        dlg.edt_horizon_file.setText(config.get("horizon_file", ""))
        dlg.spn_horizon_margin.setValue(
            float(config.get("horizon_margin_deg", 0)))
        dlg.chk_moon_enabled.setChecked(bool(config.get("moon_limit_enabled",
                                                        True)))
        dlg.spn_moon_sep.setValue(float(config.get("moon_min_sep_deg", 45)))
        dlg.spn_moon_illum.setValue(float(config.get("moon_max_illum", 0.5)))
        dlg.chk_moons_all.setChecked(bool(
            config.get("show_sat_moons_unobserved", False)))
        dlg.spn_overhead.setValue(float(config.get("overhead_s", 15)))
        dlg.spn_sn_cadence.setValue(int(config.get("sn_cadence_days", 3)))
        dlg.spn_event_mag.setValue(
            float(config.get("event_mag_threshold", 0.5)))
        dlg.spn_extremum_days.setValue(
            int(config.get("campaign_extremum_days", 3)))
        # ADR-037 SC4a: the vigil watch list, as editable text (one star
        # per line); the curated defaults show when nothing is stored
        from ..core import vigils
        dlg.edt_vigils.setPlainText(
            vigils.vigils_to_text(vigils.vigils_from_config(config)))
        dlg.chk_aavso.setChecked(bool(config.get("aavso_feed", True)))
        # ADR-044 rev (2026-09-24): icons-only top bar in the UFE
        dlg.chk_ufe_bar_icons.setChecked(
            bool(config.get("ufe_bar_icons", True)))
        dlg.chk_ufe_default.setChecked(bool(config.get("ufe_default",
                                                       True)))
        dlg.edt_ccdciel_host.setText(str(config.get("ccdciel_host",
                                                     "127.0.0.1")))
        dlg.spn_ccdciel_port.setValue(int(config.get("ccdciel_port", 3277)))
        dlg.chk_ccdciel_auto.setChecked(
            bool(config.get("ccdciel_auto_connect", False)))
        dlg.edt_tns_bot.setText(config.get("tns_bot_name", ""))
        dlg.edt_tns_bot_key.setText(config.get("tns_bot_key", ""))
        # Tonight object kinds (WORKFLOWS 7quater): the whitelist mirrors the
        # settings checkboxes; default (missing/legacy) is every kind.
        enabled = self._enabled_kinds()
        for k in KIND_ORDER:
            box = getattr(dlg, f"chk_kind_{k}", None)
            if box is not None:
                box.setChecked(k in enabled)
        # K3: the per-kind cap for the Tonight grid (default 5)
        dlg.spn_best_pk.setValue(int(config.get("best_per_kind_n", 5)))
        # Projects container root (ADR-032): empty = the app data folder
        dlg.edt_projects_root.setText(config.get("projects_root", ""))
        # interface language: system | es | en (applies on restart)
        dlg.cmb_language.addItems([self.tr("System"), self.tr("Spanish"),
                                   self.tr("English")])
        lang = config.get("language", "system")
        dlg.cmb_language.setCurrentIndex(
            {"system": 0, "es": 1, "en": 2}.get(lang, 0))
        # horizon preview + the min_alt precedence rule (ADR-020): a usable
        # file turns the flat minimum altitude off because the file decides
        dlg.edt_horizon_file.textChanged.connect(
            lambda _t: self._horizon_file_preview(dlg))
        self._horizon_file_preview(dlg)
        dlg.btn_resolve.clicked.connect(lambda: self._resolve_into(dlg))
        dlg.btn_horizon_browse.clicked.connect(
            lambda: self._horizon_browse_into(dlg))
        dlg.btn_projects_browse.clicked.connect(
            lambda: self._projects_browse_into(dlg))
        dlg.btn_projects_reset.clicked.connect(
            lambda: dlg.edt_projects_root.setText(""))
        dlg.buttonBox.accepted.connect(dlg.accept)
        dlg.buttonBox.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.Accepted:
            return
        config.set("mpc_code", dlg.edt_mpc_code.text().strip().upper())
        config.set("observatory_name", dlg.edt_obs_name.text().strip())
        config.set("lat", dlg.spn_lat.value())
        config.set("lon", dlg.spn_lon.value())
        config.set("height", dlg.spn_height.value())
        config.set("aperture_inches", dlg.spn_aperture.value())
        config.set("transit_scope_filter",
                   dlg.chk_transit_scope_filter.isChecked())
        config.set("limit_mag", dlg.spn_limit_mag.value())
        config.set("min_alt", dlg.spn_min_alt.value())
        config.set("neofixer_key", dlg.edt_neofixer_key.text().strip())
        config.set("astrometry_key", dlg.edt_astrometry_key.text().strip())
        config.set("pixel_um", dlg.spn_pixel_um.value())
        config.set("focal_mm", dlg.spn_focal_mm.value())
        config.set("aavso_code", dlg.edt_aavso_code.text().strip().upper())
        config.set("aavso_api_token", dlg.edt_aavso_token.text().strip())
        config.set("camera_type", dlg.cmb_camera_type.currentText())
        config.set("pixel_binning", dlg.cmb_binning.currentText().strip()
                   or "1x1")
        # Chart annotations (ADR-046)
        config.set("observer_name", dlg.edt_observer.text().strip())
        config.set("measurer_name", dlg.edt_measurer.text().strip())
        config.set("telescope_desc", dlg.edt_telescope.text().strip())
        config.set("camera_model", dlg.edt_camera_model.text().strip())
        config.set("marker_style",
                   dlg.cmb_marker_style.currentData() or "ring")
        config.set("chart_boxes", dlg.chk_chart_boxes.isChecked())
        config.set("horizon_file", dlg.edt_horizon_file.text().strip())
        config.set("horizon_margin_deg", dlg.spn_horizon_margin.value())
        config.set("moon_limit_enabled", dlg.chk_moon_enabled.isChecked())
        config.set("moon_min_sep_deg", dlg.spn_moon_sep.value())
        config.set("moon_max_illum", dlg.spn_moon_illum.value())
        config.set("show_sat_moons_unobserved", dlg.chk_moons_all.isChecked())
        config.set("overhead_s", dlg.spn_overhead.value())
        config.set("sn_cadence_days", dlg.spn_sn_cadence.value())
        config.set("event_mag_threshold", dlg.spn_event_mag.value())
        config.set("campaign_extremum_days", dlg.spn_extremum_days.value())
        from ..core import vigils
        config.set("vigil_list",
                   vigils.vigils_from_text(dlg.edt_vigils.toPlainText()))
        config.set("aavso_feed", dlg.chk_aavso.isChecked())
        # Development tab (ADR-044): which UI the FITS work opens in
        config.set("ufe_default", dlg.chk_ufe_default.isChecked())
        config.set("ufe_bar_icons", dlg.chk_ufe_bar_icons.isChecked())
        config.set("ccdciel_host", dlg.edt_ccdciel_host.text().strip())
        config.set("ccdciel_port", dlg.spn_ccdciel_port.value())
        config.set("ccdciel_auto_connect", dlg.chk_ccdciel_auto.isChecked())
        config.set("tns_bot_name", dlg.edt_tns_bot.text().strip())
        config.set("tns_bot_key", dlg.edt_tns_bot_key.text().strip())
        config.set("projects_root", dlg.edt_projects_root.text().strip())
        # Tonight object kinds: keep at least one, else refuse to save
        enabled = [k for k in KIND_ORDER
                   if getattr(dlg, f"chk_kind_{k}", None) is not None
                   and getattr(dlg, f"chk_kind_{k}").isChecked()]
        if not enabled:
            box = getattr(dlg, "lbl_kinds_hint", None)
            if box is not None:
                box.setStyleSheet(f"color: {theme.C_WARN};")
                box.setText(self.tr("Enable at least one object kind."))
            return
        config.set("enabled_kinds", enabled)
        config.set("best_per_kind_n", dlg.spn_best_pk.value())
        # if the header filter points at a kind that just got removed,
        # fall back to "All" so nothing is left dangling
        current = self.tonight.cmb_filter.currentData()
        if current and current not in enabled:
            self.tonight.cmb_filter.blockSignals(True)
            self.tonight.cmb_filter.setCurrentIndex(0)  # "All"
            self.tonight.cmb_filter.blockSignals(False)
            config.set("tonight_kind", "")
        # re-apply the filter: this re-populates the combo with the new
        # whitelist and refreshes both views (the whitelist may have grown
        # too, so we always re-apply, not only when the selection dropped)
        if self._tonight_all:
            self._apply_kind_filter()
        # interface language: "system" (index 0) | "es" | "en"; a change
        # only applies after a restart
        # K3: the per-kind cap changed AND the grid is live? Rebuild it.
        if self._tonight_all:
            self._build_suggestion_grid()
        prev_lang = config.get("language", "system")
        new_lang = ("system", "es", "en")[dlg.cmb_language.currentIndex()]
        lang_changed = new_lang != prev_lang
        config.set("language", new_lang)
        if lang_changed:
            self.statusBar().showMessage(
                self.tr("Settings saved — restart the app to change the language"),
                8000)
        else:
            self.statusBar().showMessage(self.tr("Settings saved"), 6000)

    def _horizon_browse_into(self, dlg):
        # @args: dlg - the settings dialog; fills its file field with a
        #          browsed horizon file (TheSkyX .hrz first, ADR-020)
        path, _ = QFileDialog.getOpenFileName(
            dlg, self.tr("Choose the limit file"), "",
            "Limit files (*.hrz *.txt *.hor);;TheSkyX limits (*.hrz);"
            ";;Text files (*.txt);;All files (*)")
        if path:
            dlg.edt_horizon_file.setText(path)

    def _projects_browse_into(self, dlg):
        # @args: dlg - the settings dialog; fills the projects root field
        #          with a browsed directory (ADR-032)
        start = dlg.edt_projects_root.text().strip() or str(paths.data_dir())
        folder = QFileDialog.getExistingDirectory(
            dlg, self.tr("Choose the projects folder"), start)
        if folder:
            dlg.edt_projects_root.setText(folder)

    def _horizon_file_preview(self, dlg):
        # Precedence rule made visible (ADR-020): while a horizon file loads
        # successfully it IS the safety reference, so the flat minimum
        # altitude is greyed out; if the file is missing or broken the
        # minimum altitude takes over again (the planner behaves the same).
        # @args: dlg - settings dialog with edt_horizon_file / spn_min_alt
        path = (dlg.edt_horizon_file.text() or "").strip()
        stats = getattr(dlg, "lbl_horizon_stats", None)
        if not path:
            dlg.spn_min_alt.setEnabled(True)
            if stats:
                stats.setText("")
            return
        from ..core import horizon as _hor
        h = _hor.load(path)
        if h is None:
            dlg.spn_min_alt.setEnabled(True)
            if stats:
                stats.setText(self.tr(
                    "Could not be read as a limit file — the flat "
                    "minimum altitude is used instead"))
            return
        s = h.stats()
        dlg.spn_min_alt.setEnabled(False)
        if stats:
            peak = self.tr("peak at azimuth %1°").replace(
                "%1", str(int(round(s["peak_az"]))))
            stats.setText(
                f"{s['min_alt']:.1f}° – {s['max_alt']:.1f}° {peak} "
                f"({len(h.points)} {self.tr('points')})")

    def _resolve_into(self, dlg):
        code = dlg.edt_mpc_code.text().strip().upper()
        if not code:
            return
        w = MpcResolveWorker(code)
        w.finished.connect(lambda info: self._mpc_resolved_dialog(dlg, info))
        self._keep(w)
        w.start()

    def _mpc_resolved_dialog(self, dlg, info):
        if not info:
            self.statusBar().showMessage(
                self.tr("Unknown code or offline"), 8000)
            return
        dlg.edt_obs_name.setText(info["name"])
        dlg.spn_lat.setValue(info["lat"])
        dlg.spn_lon.setValue(info["lon"])
        self.statusBar().showMessage(
            self.tr("Found: %1").replace("%1", info["name"]), 8000)

    def on_about(self):
        # Show the exact build so the user can check "is this the right one?"
        # before reporting an issue (spirit of ADR-013: self-describing app).
        # @args: none
        QMessageBox.about(self, "NightScribe",
                          f"<b>NightScribe</b> {full_version()}<br><br>"
                          + self.tr("Plan your night, understand every object, "
                                    "tell your science.")
                          + "<br><br>(c) 2026 Francisco José Calvo Fernández<br>"
                          "GPL v3 · Irydeo Observatory (MPC Z41)")

    def on_sources(self):
        QMessageBox.information(
            self, self.tr("Data sources"),
            self.tr("NEOfixer · MPC (PCCP, ObsCodes) · JPL SBDB/Horizons/CAD · "
                    "COBS · Rochester Astronomy · SIMBAD · ExoClock · NASA "
                    "Exoplanet Archive · NOAA SWPC · SILSO · NASA SDO · DESI "
                    "Legacy Survey · CDS hips2fits"))

    def on_docs(self):
        # Opens the in-GUI documentation browser (Help > Documentation):
        # file tree on the left, rendered doc on the right. Starts at the
        # master doc for the current language (WORKFLOWS) when present.
        from .doc_viewer import open_browser
        root = paths.docs_dir()
        if not root.is_dir():
            self.statusBar().showMessage(
                self.tr("Documentation not found at %1").replace("%1", root),
                10000)
            return
        name = "WORKFLOWS.es.md" if self._lang() == "es" else "WORKFLOWS.md"
        start = root / name if (root / name).exists() else None
        open_browser(root, self, start=start)

    # ---------------- Tonight: suggestion grid ----------------

    # Type accent colors and short labels — single source of truth lives
    # in gui/theme.py (ADR-026); these references keep call sites stable.
    _KIND_COLORS = theme.KIND_COLORS
    _KIND_LABELS = theme.KIND_LABELS

    def _type_pixmap(self, kind, size=28):
        # Draws a small geometric icon per object type with QPainter.
        # Fast (no matplotlib), guaranteed to render on any platform.
        # @args: kind - object kind string, size - icon px
        # @return: QPixmap with a transparent background
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import (QBrush, QColor, QPainter,
                                    QPainterPath, QPen, QPixmap)
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor(self._KIND_COLORS.get(kind, "#888888"))
        cx = cy = size / 2.0
        if kind == "sn":
            # 4-point star (spark burst)
            p.setBrush(QBrush(color))
            path = QPainterPath()
            path.moveTo(QPointF(cx, 2))
            path.lineTo(QPointF(cx + 4, cy - 4))
            path.lineTo(QPointF(size - 2, cy))
            path.lineTo(QPointF(cx + 4, cy + 4))
            path.lineTo(QPointF(cx, size - 2))
            path.lineTo(QPointF(cx - 4, cy + 4))
            path.lineTo(QPointF(2, cy))
            path.lineTo(QPointF(cx - 4, cy - 4))
            path.closeSubpath()
            p.drawPath(path)
        elif kind == "neo":
            # small ellipse (asteroid body)
            p.setBrush(QBrush(color))
            p.drawEllipse(QRectF(cx - 7, cy - 4, 14, 8))
        elif kind == "comet":
            # nucleus + tail
            p.setBrush(QBrush(color))
            p.drawEllipse(QRectF(cx - 4, cy - 4, 8, 8))
            p.setPen(QPen(color, 1.5))
            p.drawLine(QPointF(cx + 3, cy), QPointF(size - 2, cy + 4))
            p.drawLine(QPointF(cx + 3, cy + 1), QPointF(size - 3, cy + 5))
        elif kind == "pccp":
            # dashed circle (uncertain identity)
            pen = QPen(color, 2)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(cx - 8, cy - 8, 16, 16))
        elif kind == "transit":
            # light curve with a dip
            p.setPen(QPen(color, 2))
            p.drawLine(QPointF(2, cy), QPointF(cx - 6, cy))
            p.drawArc(QRectF(cx - 6, cy - 6, 12, 12), 0, -180 * 16)
            p.drawLine(QPointF(cx + 6, cy), QPointF(size - 2, cy))
        elif kind == "alert":
            # warning triangle
            p.setBrush(QBrush(color))
            path = QPainterPath()
            path.moveTo(QPointF(cx, 3))
            path.lineTo(QPointF(size - 2, size - 3))
            path.lineTo(QPointF(2, size - 3))
            path.closeSubpath()
            p.drawPath(path)
            p.setPen(QPen(QColor("#e8eaf2"), 1.5))
            p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "!")
        elif kind == "hads":
            # pulsating star: small 4-point star + a sine wave underneath
            p.setBrush(QBrush(color))
            path = QPainterPath()
            path.moveTo(QPointF(cx, 4))
            path.lineTo(QPointF(cx + 3, cy - 5))
            path.lineTo(QPointF(size - 4, cy - 5))
            path.lineTo(QPointF(cx + 3, cy - 5 + 3))
            path.lineTo(QPointF(cx, cy + 1))
            path.lineTo(QPointF(cx - 3, cy - 2))
            path.lineTo(QPointF(4, cy - 5))
            path.lineTo(QPointF(cx - 3, cy - 5))
            path.closeSubpath()
            p.drawPath(path)
            p.setPen(QPen(color, 1.5))
            wave = QPainterPath()
            wave.moveTo(QPointF(3, size - 6))
            wave.cubicTo(QPointF(cx - 4, size - 6), QPointF(cx - 6, size - 11),
                         QPointF(cx, size - 11))
            wave.cubicTo(QPointF(cx + 6, size - 11), QPointF(cx + 4, size - 6),
                         QPointF(size - 3, size - 6))
            p.drawPath(wave)
        elif kind == "variable":
            # long-period variable: 4-point star + a slow wave underneath
            p.setBrush(QBrush(color))
            path = QPainterPath()
            path.moveTo(QPointF(cx, 4))
            path.lineTo(QPointF(cx + 3, cy - 5))
            path.lineTo(QPointF(size - 4, cy - 5))
            path.lineTo(QPointF(cx + 3, cy - 5 + 3))
            path.lineTo(QPointF(cx, cy + 1))
            path.lineTo(QPointF(cx - 3, cy - 2))
            path.lineTo(QPointF(4, cy - 5))
            path.lineTo(QPointF(cx - 3, cy - 5))
            path.closeSubpath()
            p.drawPath(path)
            p.setPen(QPen(color, 1.5))
            wave = QPainterPath()
            wave.moveTo(QPointF(3, size - 8))
            wave.cubicTo(QPointF(cx - 2, size - 2),
                         QPointF(cx + 2, size - 12),
                         QPointF(size - 3, size - 7))
            p.drawPath(wave)
        p.end()
        return pix

    def on_compute_tonight(self):
        self.tonight.btn_compute.setEnabled(False)
        self._show_loading_state()
        self.statusBar().showMessage(self.tr("Computing tonight…"))
        w = TonightWorker(config, db)
        w.progress.connect(self._tonight_progress)
        w.finished.connect(self._tonight_done)
        self._keep(w)
        w.start()

    def _tonight_progress(self, msg):
        # One load phase arrived (see workers.TonightWorker). The human label
        # is picked from a literal tr() table so lupdate sees it (CONTRIBUTING
        # rule 5: every visible string through tr()); the worker only sends
        # the phase key + index/total. The bar (status-left) is the gauge;
        # the message text and the header both reflect the current phase.
        key = msg.get("key", "")
        phases = {
            "neo": self.tr("Loading NEOfixer targets…"),
            "sn": self.tr("Loading supernovae…"),
            "comet": self.tr("Locating comets…"),
            "pccp": self.tr("Checking PCCP candidates…"),
            "transit": self.tr("Scanning exoplanet transits…"),
            "hads": self.tr("Checking HADS variables…"),
            "campaigns": self.tr("Checking campaigns…"),
            "vigils": self.tr("Checking vigils…"),
            "aavso": self.tr("Checking the AAVSO channel…"),
            "approach": self.tr("Fetching close approaches…"),
            "scoring": self.tr("Scoring targets…"),
        }
        label = phases.get(key, key)
        index = int(msg.get("index", 0))
        total = int(msg.get("total", 0))
        text = (self.tr("Step %1 of %2 — %3").replace("%1", str(index)).
                replace("%2", str(total)).replace("%3", label))
        self.statusBar().showMessage(text)
        self.tonight.lbl_context.setText(text)
        bar = self._status_progress
        bar.setVisible(True)                       # make sure it's on
        bar.setRange(1, max(total, 1))
        bar.setFormat("")                          # the bar is a pure gauge
        bar.setTextVisible(False)
        # animate the fill to the new step instead of jumping
        self._bar_anim.setDuration(200)
        self._bar_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._bar_anim.setStartValue(bar.value())
        self._bar_anim.setEndValue(index)
        self._bar_anim.start()

    def _show_loading_state(self):
        # Skeleton rows while the worker runs (same shape as the final rows),
        # each with a moving shimmer highlight driven by one shared timer.
        container = self._clear_suggestions()
        layout = container.layout()
        self._skeleton_rows = []
        n = 6
        for i in range(n):
            row = ShimmerRow(index=i, total_rows=n)
            layout.addWidget(row)
            self._skeleton_rows.append(row)
        layout.addStretch()
        # start the shimmer clock (one for all rows) if not already running
        if not self._skeleton_timer.isActive():
            self._skeleton_timer.start(30)
        # global status-bar gauge: on, busy until the first phase arrives
        self._status_progress.setVisible(True)
        self._status_progress.setRange(0, 0)
        self.tonight.lbl_context.setText(self.tr("Computing tonight…"))
        # a placeholder phase (first quarter) so the disc is not empty
        # while computing; the real phase replaces it in _update_night_header
        from . import moon_icon
        self.tonight.lbl_moon.setPixmap(moon_icon.moon_pixmap(-90, 30))
        self.tonight.lbl_moon.setToolTip(self.tr("Computing…"))

    def _tonight_done(self, top, all_scored, error=""):
        self.tonight.btn_compute.setEnabled(True)
        self._stop_skeleton()
        self._bar_anim.stop()
        self._status_progress.setVisible(False)
        if error or not all_scored:
            msg = error or self.tr("no sources answered")
            self._show_empty_state(msg)
            self.statusBar().showMessage(
                self.tr("Error: %1").replace("%1", msg), 15000)
            return
        self._tonight_top = top
        self._tonight_all = all_scored
        self._update_night_header()
        self._build_suggestion_grid()
        self._fill_table()
        self._show_cadence_hints()
        self._skyevent_chips()
        self.statusBar().showMessage(
            self.tr("%1 targets evaluated").replace("%1", str(len(all_scored))),
            8000)

    def _stop_skeleton(self):
        # Stops the shared shimmer timer (idempotent) once loading ends
        if self._skeleton_timer.isActive():
            self._skeleton_timer.stop()

    def _show_empty_state(self, msg):
        # Single helpful message when no targets are available
        container = self._clear_suggestions()
        layout = container.layout()
        self._stop_skeleton()
        self._status_progress.setVisible(False)
        lbl = QLabel(self.tr("No targets found") + "\n\n" + msg + "\n\n"
                        + self.tr("Check your network and try again."))
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setMinimumHeight(120)
        lbl.setStyleSheet(
            f"color: {theme.C_TEXT_DIM}; font-size: 14px;"
            f" background: {theme.C_BASE}; border-radius: 8px; padding: 24px;")
        layout.addWidget(lbl)
        layout.addStretch()
        self.tonight.lbl_context.setText(self.tr("No data"))

    def _update_night_header(self):
        from ..core import coords, ephem_minor
        from . import moon_icon
        jd = coords.jd_from_datetime(
            datetime.datetime.now(datetime.timezone.utc))
        m = ephem_minor.moon(jd)
        # the bare time range was the only unexplained piece of this row:
        # it is the astronomical night (sun below -18 deg), in UTC, the
        # same clock as the "Best time (UTC)" column — labeled and
        # translatable now (ADR-014: visible strings through tr())
        window = coords.tonight_window(config.get("lat"), config.get("lon"))
        date = datetime.date.today().isoformat()
        pct_now = m["illum"] * 100
        if window:
            dusk = window[0].strftime("%H:%M")
            dawn = window[1].strftime("%H:%M")
            self.tonight.lbl_context.setText(
                self.tr("%1  ·  Night %2–%3 (UTC)")
                .replace("%1", date).replace("%2", dusk).replace("%3", dawn))
            pct_by_dawn = ephem_minor.moon(
                coords.jd_from_datetime(window[1]))["illum"] * 100
        else:
            self.tonight.lbl_context.setText(
                self.tr("%1  ·  no astronomical night tonight")
                .replace("%1", date))
            pct_by_dawn = pct_now
        # the moon icon replaces the old "Moon 79%" text: a real disc at the
        # exact phase, and the tooltip explains where the number was going
        label = self.tonight.lbl_moon
        label.setPixmap(moon_icon.moon_pixmap(m["elong_deg"], 30))
        why = {"es": "La Luna avanza ~12°/día en su órbita: en la misma noche "
                     "cambia varios grados su ángulo con el Sol, por eso su "
                     "iluminación sube o baja de principio a fin de la noche",
               "en": "The Moon moves ~12°/day along its orbit: over one night "
                     "its angle to the Sun shifts a few degrees, so its "
                     "illumination rises or falls from dusk to dawn"}
        tip = (self.tr("Moon: %1% lit now, %2% by dawn")
               .replace("%1", f"{pct_now:.0f}").replace("%2", f"{pct_by_dawn:.0f}"))
        label.setToolTip(tip + "\n" + self._txt(why))

    def _show_cadence_hints(self):
        # B11: surface active SN projects that are due for a revisit ("hace
        # N noches que no la visitas"). Reads the follow-up cadence from the
        # project_sessions table and shows a chip in the Tonight header.
        from ..core import followup as fu
        # remove every previous cadence chip (several now, idempotent)
        for old in self.tonight.findChildren(QLabel, "ns_cadence_chip"):
            parent = old.parentWidget()
            if parent and parent.layout():
                parent.layout().removeWidget(old)
            old.deleteLater()
        threshold = int(config.get("sn_cadence_days", 3))
        # campaign projects already surface in Tonight via the planner's
        # "campaigns" phase (ADR-035, V-d): the chip only watches
        # campaign-less SN projects
        rows = db.execute(
            "SELECT id, object_name FROM projects"
            " WHERE status='active' AND kind='sn'"
            " AND (campaign_id IS NULL)").fetchall()
        hints = []
        for pid, name in rows:
            days = fu.days_since_last_session(db, pid)
            if days is not None and days >= threshold:
                hints.append((pid, name, days))
        if not hints:
            return
        # insert the chips in the tonight header's layout (the parent of
        # lbl_context is a QWidget; find its containing layout)
        parent = self.tonight.lbl_context.parentWidget()
        header_layout = parent.layout() if parent else None
        if header_layout is None:
            p = parent
            while p is not None:
                if p.layout() is not None:
                    header_layout = p.layout()
                    break
                p = p.parentWidget()
        if not (header_layout and hasattr(header_layout, "addWidget")):
            return
        for pid, name, days in hints[:3]:
            chip = _LinkChip(
                self.tr("SN due: %1 (%2 d)").replace(
                    "%1", name).replace("%2", str(days)),
                "#e0c060",
                self.tr("Due for a revisit: click to open its Follow-up"))
            chip.setObjectName("ns_cadence_chip")
            chip.clicked.connect(
                lambda _p=pid: self._goto_project_followup(_p))
            header_layout.addWidget(chip)
        if len(hints) > 3:
            more = QLabel(f"+{len(hints) - 3}")
            more.setObjectName("ns_cadence_chip")
            more.setStyleSheet(theme.chip_style("#e0c060"))
            header_layout.addWidget(more)

    def _goto_project_followup(self, pid):
        # Opens the project's Follow-up tab (ADR-043: the multi-night
        # journal keeps its "followup" key). The cadence chips land
        # here (UX-d). ADR-045: lands on the Analysis tab.
        if not self._goto_project_by_id(pid):
            return
        self._scroll_to_section("analysis")

    # ---------------- sky-event chips in the Tonight header (SC2) -------

    def _skyevent_chips(self, evs=None):
        # The solar system as an event source (SC2, ADR-040): up to three
        # chips in the Tonight header, the big things first, one per
        # family. Local maths, no network. A click opens the Sky calendar.
        # @args: evs - optional precomputed list (tests inject fakes)
        # @return: the picked events (also handy for tests)
        for old in self.tonight.findChildren(QLabel, "ns_skyevent_chip"):
            parent = old.parentWidget()
            if parent and parent.layout():
                parent.layout().removeWidget(old)
            old.setParent(None)     # detach NOW — deleteLater alone lets
            old.deleteLater()       # findChildren still see the corpse
        from ..core import coords, skyevents
        if evs is None:
            evs = skyevents.events(float(config.get("lat")),
                                   float(config.get("lon")), days=14)
        now_jd = coords.jd_from_datetime(
            datetime.datetime.now(datetime.timezone.utc))
        cands = [e for e in evs if e["jd"] >= now_jd - 1.0]
        cands.sort(key=lambda e: (-_SKY_CHIP_PRIORITY.get(e["kind"], 10),
                                  e["jd"]))
        picks = []
        seen = set()
        for e in cands:
            kind = e["kind"]
            if kind in ("sat_transit", "shadow_transit") \
                    and not e.get("observable"):
                continue            # invisible from the site: no chip
            if kind == "moon_conjunction" and not e.get("up_at_dusk"):
                continue            # a daytime pass is noise
            if kind in seen:
                continue
            seen.add(kind)
            picks.append(e)
            if len(picks) == 3:
                break
        if not picks:
            return picks
        # same header home as the cadence chips (the layout that hosts
        # lbl_context; see _show_cadence_hints for the fallback walk)
        parent = self.tonight.lbl_context.parentWidget()
        header_layout = parent.layout() if parent else None
        if header_layout is None:
            p = parent
            while p is not None:
                if p.layout() is not None:
                    header_layout = p.layout()
                    break
                p = p.parentWidget()
        if not (header_layout and hasattr(header_layout, "addWidget")):
            return picks
        for e in picks:
            chip = _LinkChip(self._sky_chip_text(e), "#6ab0ff",
                             self.tr("From the solar-system calendar — "
                                     "click to open the Sky calendar"))
            chip.setObjectName("ns_skyevent_chip")
            chip.clicked.connect(self._tools_skycal)
            header_layout.addWidget(chip)
        return picks

    def _sky_chip_text(self, e):
        # The chip's short text: icon + the thing + when ("tonight" or
        # the day). @args: e - the event dict. @return: text
        kind = e["kind"]
        objs = e["objects"]
        when = self.tr("tonight") if e.get("tonight") \
            else pretty.day(self._lang(), e["date"])

        def nm(i):
            # The chip's proper noun, in the UI's language (the engine
            # hands over lowercase keys: "ganymede", "perseids", ...).
            return pretty.name(self._lang(), objs[i])

        if kind == "lunar_eclipse":
            return self.tr("🌘 Lunar eclipse %1").replace("%1", when)
        if kind == "solar_eclipse":
            return self.tr("🌘 Solar eclipse %1").replace("%1", when)
        if kind == "shadow_transit":
            return self.tr("🔭 %1's shadow %2 UT").replace(
                "%1", nm(0)).replace("%2", e["t0"].strftime("%H:%M"))
        if kind == "sat_transit":
            return self.tr("🔭 %1 transit %2 UT").replace(
                "%1", nm(0)).replace("%2", e["t0"].strftime("%H:%M"))
        if kind == "opposition":
            return self.tr("🔴 %1 at opposition %2").replace(
                "%1", nm(0)).replace("%2", when)
        if kind == "max_elongation":
            return self.tr("%1 %2 greatest elongation").replace(
                "%1", e["icon"]).replace("%2", nm(0))
        if kind == "planet_conjunction":
            return self.tr("✨ %1–%2 %3°").replace(
                "%1", nm(0)).replace("%2", nm(1)).replace(
                "%3", str(e.get("sep_deg")))
        if kind == "moon_conjunction":
            return self.tr("🌙 Moon–%1 %2°").replace(
                "%1", nm(1)).replace("%2", str(e.get("sep_deg")))
        if kind == "meteor_shower":
            return self.tr("☄️ %1 %2").replace(
                "%1", nm(0)).replace("%2", when)
        if kind in ("full_moon", "new_moon", "first_quarter",
                    "last_quarter"):
            words = {"full_moon": self.tr("🌕 Full moon"),
                     "new_moon": self.tr("🌑 New moon"),
                     "first_quarter": self.tr("🌓 First quarter"),
                     "last_quarter": self.tr("🌗 Last quarter")}
            return f"{words[kind]} {when}"
        if kind == "perigee":
            return self.tr("🌕 Perigee Moon %1").replace("%1", when)
        return f"{e['icon']} {kind} {when}"

    def _clear_suggestions(self):
        # Drops every widget inside the suggestion scroll container and
        # guarantees it has a single-column vertical layout (one row each).
        container = self.tonight.scroll_suggestions.findChild(
            QWidget, "suggestions_container")
        if container.layout():
            while container.layout().count():
                item = container.layout().takeAt(0)
                w = item.widget() if item else None
                if w is not None:
                    # detach now: deleteLater alone may run inside a nested
                    # modal loop and leave the old row painted/clickable over
                    # the fresh grid.
                    w.setParent(None)
                    w.deleteLater()
        else:
            container.setLayout(QVBoxLayout(container))
        layout = container.layout()
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(8)
        return container

    def _build_suggestion_grid(self):
        # K3 (WORKFLOWS 7quater): only the targets that pass the header
        # filter are shown, capped at best_per_kind_n per kind (variety,
        # never a wall of one kind) but still ordered by global score.
        # The ring lands on the best target of EACH visible kind, not on
        # "the top 3 of the night".
        self._rebuild_kind_filters()
        want = self.tonight.cmb_filter.currentData()
        # start from the visible set (already whitelist-aware), then apply
        # the K3 per-kind cap. _tonight_all is already in global-score
        # order, but we re-sort to be safe (tests may inject the list).
        visible = self._visible_targets(want)
        visible.sort(key=lambda x: (-x[1], x[0]["name"]))
        n = int(config.get("best_per_kind_n", 5) or 0)
        shown, best_ids = suggest.best_per_kind(visible, n)
        self._grid = shown
        self._grid_best = best_ids
        container = self._clear_suggestions()
        container.layout().addStretch()
        for (t, score, parts, phrase) in shown:
            row = self._make_row(t, score, parts, phrase, ring=(t.get("id") in best_ids))
            container.layout().insertWidget(container.layout().count() - 1,
                                              row)

    def _rebuild_kind_filters(self):
        # One filter rules both views (WORKFLOWS 7quater): the header combo
        # offers only the enabled kinds (settings whitelist, K2), "All" first.
        # Re-populating with an unchanged list leaves the current kind (and
        # the persistent selection) untouched; a removed kind falls back to
        # "All" so nothing points at a dead option.
        cmb = self.tonight.cmb_filter
        old = cmb.currentData()  # None = "All"
        enabled = [k for k in KIND_ORDER
                   if k in self._enabled_kinds()
                   and k in self._KIND_LABELS]
        # block the signal: this runs from several hooks and we fill the
        # views right after
        cmb.blockSignals(True)
        cmb.clear()
        cmb.addItem(self.tr("All"), None)
        for k in enabled:
            cmb.addItem(self._KIND_LABELS[k], k)
        idx = cmb.findData(old) if old else 0
        cmb.setCurrentIndex(idx if idx >= 0 else 0)
        cmb.blockSignals(False)

    def _enabled_kinds(self):
        # @return: the settings whitelist; missing/legacy -> every kind
        val = config.get("enabled_kinds")
        if not isinstance(val, list) or not val:
            return list(KIND_ORDER)
        return val

    def _visible_targets(self, want):
        # @args: want - a kind key, or None ("All" = every *enabled* kind)
        # @return: the scored list, order preserved, cut to the filter.
        #   Disabled kinds are hidden everywhere (the whitelist, K2), so
        #   "All" means "all enabled kinds", never "everything in the night".
        enabled = self._enabled_kinds()
        all_ = self._tonight_all or []
        if want:
            return [x for x in all_ if x[0].get("kind") == want]
        return [x for x in all_ if x[0].get("kind") in enabled]

    def _apply_kind_filter(self, _index=None):
        # Header combo changed (WORKFLOWS 7quater): refresh BOTH views with
        # the same kind at once, keep the previous choice, and drop any that
        # is no longer enabled. Index is ignored — only the combo's data.
        want = self.tonight.cmb_filter.currentData()
        try:
            config.set("tonight_kind", want or "")
        except Exception:
            pass
        self._build_suggestion_grid()
        self._fill_table(want)

    def _chip(self, text, color, tip=""):
        # @return: a small pill label (status / window / moon / warning chip)
        lbl = QLabel(text)
        lbl.setStyleSheet(theme.chip_style(color))
        if tip:
            lbl.setToolTip(tip)
        return lbl

    def _make_row(self, t, score, parts, phrase, ring=False):
        # @return: one wide, click-to-explore row:
        #   [kind icon]  [name .......... status chips]
        #               [why-tonight phrase, always visible]
        #               [score bar 4 segments ......... NN  Start/Continue]
        # ring: K3 — True on the best target of each visible kind
        kind = t.get("kind", "")
        kind_color = self._KIND_COLORS.get(kind, "#888888")
        kind_label = self._KIND_LABELS.get(kind, kind)
        row = _ClickableFrame()
        edge = "#5a6478" if ring else "transparent"
        row.setStyleSheet(theme.row_skin("tonightrow", theme.C_BASE, edge,
                                         radius=8))
        row.setObjectName("tonightrow")
        row.setCursor(Qt.PointingHandCursor)
        row.clicked.connect(lambda t=t: self._open_explore_dialog(
            t.get("name") or t.get("id")))
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        # left: the kind icon, full height, kind-color tint
        lbl_icon = QLabel()
        lbl_icon.setPixmap(self._type_pixmap(kind, size=32))
        # solid wash: QSS mis-parses bare 8-digit hexes (alpha-first), so
        # composite() blends an opaque #rrggbb instead of an alpha tint
        lbl_icon.setStyleSheet(f"background: {theme.composite(kind_color, '18')}; border-radius: 6px;")
        lbl_icon.setFixedSize(44, 44)
        layout.addWidget(lbl_icon)
        # center: the readable content
        mid = QVBoxLayout()
        mid.setSpacing(5)
        # header line: kind chip + name + status chips, one row when it fits
        head = QHBoxLayout()
        head.setSpacing(8)
        lbl_kind = QLabel(kind_label)
        lbl_kind.setStyleSheet(theme.chip_style(kind_color, font_size=12))
        head.addWidget(lbl_kind)
        lbl_name = QLabel(t["name"])
        lbl_name.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #e8eaf2;"
            " background: transparent;")
        head.addWidget(lbl_name)
        head.addStretch()
        head_has_window = False
        if self._window_text(t):
            ws = (t.get("window_start") or "")[11:16]
            we = (t.get("window_end") or "")[11:16]
            head_has_window = True
            head.addWidget(self._chip(
                f"{ws}–{we}", theme.C_OK,
                self.tr("Best time to observe: visible %1–%2 UTC"
                        " (above the limit)").replace("%1", ws)
                .replace("%2", we)))
        # safe window (ADR-020): only present when a capture plan was saved
        # for this target (via the project hub); the chip doubles as the
        # red "does not fit" warning when it cannot be placed.
        if t.get("safe_window"):
            s0, s1 = t["safe_window"].split("|")
            s0h, s1h = s0[11:16], s1[11:16]
            bt = t.get("best_time")
            bt_hm = bt[11:16] if bt else None
            if bt_hm:
                head.addWidget(self._chip(
                    f"⊕ {s0h}–{s1h} · ≤ {bt_hm}",
                    theme.C_GOOD,
                    self.tr("Safe window %1–%2 UTC — the planned session "
                            "fits, latest safe start ≤ %3")
                    .replace("%1", s0h).replace("%2", s1h).replace("%3", bt_hm)))
        elif t.get("duration_s") and not t.get("safe_window"):
            # a session was planned but it could not be placed inside
            # tonight's visible span: the one safety warning
            mins = int(round(int(t.get("duration_s", 0)) / 60))
            head.addWidget(self._chip(
                f"⚠ {self.tr('does not fit')} · {mins} min",
                theme.C_WARN,
                self.tr("The planned {0} min session does not fit in the "
                        "time the object is above your local limit. "
                        "Do NOT force the instrument.").format(mins)))
        badge = self._now_badge(t)
        if badge:
            now = badge.startswith("▲")
            if now:
                head.addWidget(self._chip(
                    self.tr("now"), theme.C_GOOD,
                    self.tr("Above the limit right now")))
            elif not head_has_window:
                # window chip is absent, so the rise time is all we show
                head.addWidget(self._chip(
                    badge, theme.C_OK,
                    self.tr("Rises above the limit at %1 UTC")
                    .replace("%1", badge[:-1])))
        info = suggest.moon_info(t, config)
        if info and info.get("warning"):
            sep = f"{info['sep_deg']:.0f}°"
            illum = f"{info['illum']*100:.0f}%"
            reasons = []
            if info["sep_deg"] < float(config.get("moon_min_sep_deg", 45)):
                reasons.append(self.tr(
                    "close to the Moon (%1)")
                    .replace("%1", sep))
            if info["illum"] > float(config.get("moon_max_illum", 0.5)):
                reasons.append(self.tr(
                    "high illumination (%1)")
                    .replace("%1", illum))
            tip = self.tr(
                "Moon at %1 separation, %2 illuminated — bright night sky, "
                "faint targets need longer exposures. Reason: %3") \
                .replace("%1", sep).replace("%2", illum) \
                .replace("%3", self.tr(" and ").join(reasons))
            head.addWidget(self._chip(
                self.tr("Moon %1 · %2").replace("%1", sep)
                .replace("%2", illum),
                theme.C_WARN, tip))
        # campaign chip (UX-c): the target belongs to a campaign — the ⚑
        # chip jumps to the Campaigns tab on that campaign (and, unlike
        # the plain label, does not also fire the row's explore click)
        camp = t.get("campaign") or {}
        if camp.get("name"):
            chip = _LinkChip(
                "⚑ " + camp["name"], theme.KIND_COLORS["variable"],
                self.tr("Part of this observing campaign — click to "
                        "open it"))
            cid = camp.get("id")
            if cid is not None:
                chip.clicked.connect(
                    lambda _c=cid: self._goto_campaigns(_c))
            head.addWidget(chip)
        # ⏳ predicted extremum of the variability cycle (ADR-037 SC3):
        #   the max/min kind is decided by the VSX epoch convention inside
        #   variables.next_extremum — here we only render the countdown
        nxt = (t.get("variable") or {}).get("next_extremum") or {}
        if nxt.get("days") is not None:
            lab = self.tr("maximum") if nxt.get("kind") == "max" \
                else self.tr("minimum")
            txt = self.tr("%1 in %2 d").replace("%1", lab) \
                                  .replace("%2", f"{float(nxt['days']):.1f}")
            head.addWidget(self._chip(
                txt, theme.C_OK,
                self.tr("Next expected extremum (VSX epoch)")))
        # 👁 vigil alert (ADR-037 SC4a): a watch-list star off its
        #   baseline in the public survey data — standalone row, or fused
        #   into the campaign it belongs to (never a duplicate row, SC-g)
        vg = t.get("vigil") or (t.get("campaign") or {}).get("vigil")
        if vg:
            head.addWidget(self._chip(
                self.tr("👁 ZTF %1 %2").replace("%1", vg.get("filter", "?"))
                    .replace("%2", f"{vg.get('mag', 0.0):.1f}"),
                theme.C_WARN,
                self.tr("Vigil alert: the latest ZTF point shows it at "
                        "%1 mag versus its %2 baseline (Δ %3)")
                .replace("%1", f"{vg.get('mag', 0.0):.1f}")
                .replace("%2", f"{vg.get('baseline_mag', 0.0):.1f}")
                .replace("%3", f"{vg.get('delta', 0.0):+.1f}")))
        # 📣 AAVSO editorial channel (ADR-037 SC4b): an alert (warn) or an
        #   active observing campaign (ok) asks for this star — standalone
        #   row, or fused into its campaign project (SC-g)
        av = t.get("aavso") or (t.get("campaign") or {}).get("aavso")
        if av:
            col = theme.C_WARN if av.get("kind") == "alert" else theme.C_OK
            tip = av.get("title", "")
            if av.get("url"):
                tip += "\n" + av["url"]
            head.addWidget(self._chip(self.tr("📣 AAVSO"), col, tip))
        # soft-limit warning (ADR-025): predicted-mag kinds beyond the limit
        beyond, delta = suggest.beyond_limit(t, config)
        if beyond:
            limit = float(config.get("limit_mag", 20.0))
            head.addWidget(self._chip(
                "⚠ " + self.tr("mag >%1").replace("%1", f"{limit:.0f}"),
                theme.C_WARN,
                self.tr("Predicted magnitude beyond your limiting magnitude "
                        "by %1 mags. Still scored for its scientific "
                        "priority, but it will need a longer exposure.")
                .replace("%1", f"{delta}")))
        mid.addLayout(head)
        # the why-tonight phrase, always visible (not a tooltip anymore)
        lbl_why = QLabel(self._txt(phrase))
        lbl_why.setWordWrap(True)
        lbl_why.setStyleSheet("color: #aab0c4; font-size: 13px; background: transparent;")
        mid.addWidget(lbl_why)
        # score line: 4-segment meter + total + action button
        line = QHBoxLayout()
        line.setSpacing(10)
        bar = _ScoreBar(kind_color)
        bar.set_parts(parts or {})
        bar.setToolTip(self._parts_tooltip(parts))
        line.addWidget(bar, stretch=1)
        lbl_score = QLabel(f"{int(round(score))}")
        lbl_score.setStyleSheet(
            f"font-size: 20px; font-weight: bold; color: {kind_color};"
            " background: transparent;")
        line.addWidget(lbl_score)
        lbl_of = QLabel("/100")
        lbl_of.setStyleSheet(f"color: {theme.C_TEXT_DIM}; font-size: 12px;"
                             " background: transparent;")
        line.addWidget(lbl_of)
        btn = self._card_button(t)
        btn.setFixedWidth(130)
        line.addWidget(btn)
        mid.addLayout(line)
        layout.addLayout(mid)
        return row

    def _parts_tooltip(self, parts):
        # One line per score family, with the part's max, for the meter tip.
        if not parts:
            return ""
        return "\n".join((
            f"{self.tr('scientific')} {parts.get('scientific', 0):.0f}/35",
            f"{self.tr('observability')} {parts.get('observability', 0):.0f}/30",
            f"{self.tr('urgency')} {parts.get('urgency', 0):.0f}/20",
            f"{self.tr('hook')} {parts.get('hook', 0):.0f}/15"))

    def _now_badge(self, t):
        # @return: "▲ ahora" if up now, or "HH:MM↑" rise time, or ""
        from ..core import planner
        if not self._tonight_all:
            return ""
        targets = [x for x, _s, _p, _ph in self._tonight_all]
        now = planner.visible_now(targets, config)
        up_ids = {t2["id"] for t2, _a, _z in now}
        if t["id"] in up_ids:
            return "▲ " + self.tr("now")
        ws = (t.get("window_start") or "")[11:16]
        if ws:
            return f"{ws}↑"
        return ""

    def _window_text(self, t):
        ws = (t.get("window_start") or "")[11:16]
        we = (t.get("window_end") or "")[11:16]
        if not ws or not we:
            return ""
        return f"{self.tr('window')} {ws}–{we}"

    def _card_button(self, t):
        # @return: the smart shortcut button of the Tonight row:
        #   "Continue" (green) when an active project already exists for
        #     this object — it jumps straight to the project, like it did.
        #   "Explore"  (orange) when no project exists — it opens the
        #     Explore dialog (the single entry point of phase E); the
        #     user then explicitly picks "Create project" from there.
        # The row's click is always Explore, so the button is purely a
        # shortcut to the more likely destination.
        name = t.get("name") or t.get("id")
        existing = project.list_projects(db, "active")
        has_proj = any(p["object_name"] == name
                       or p["object_name"] == t.get("id")
                       for p in existing)
        if has_proj:
            btn = QPushButton(f"▶ {self.tr('Continue')}")
            btn.setToolTip(self.tr(
                "Resume the active project for this object"))
            btn.setStyleSheet(
                "QPushButton { background: #2a7a3a; color: #e8eaf2;"
                " border: none; border-radius: 4px; padding: 5px;"
                " font-weight: bold; }"
                "QPushButton:hover { background: #3a9a4a; }")
            btn.clicked.connect(
                lambda _=False, t=t: self._start_or_continue(t))
        else:
            btn = QPushButton(f"🔭 {self.tr('Explore')}")
            btn.setToolTip(self.tr(
                "Open the object in the Explore dialog (you can also "
                "create a project from there)"))
            btn.setStyleSheet(
                "QPushButton { background: #c46922; color: #e8eaf2;"
                " border: none; border-radius: 4px; padding: 5px;"
                " font-weight: bold; }"
                "QPushButton:hover { background: #e47932; }")
            btn.clicked.connect(
                lambda _=False, n=name: self._open_explore_dialog(n))
        return btn

    def _start_or_continue(self, t):
        # Start a new project or jump to the existing one (phase E: the
        # hub's "Continue" shortcut and the Explore dialog's "Continue
        # project" button both end up here).
        t = t if isinstance(t, dict) else {}
        if self._goto_active_project(t.get("name") or t.get("id"),
                                     fallback=t):
            return
        self._create_project(t)

    def _refresh_now_badges(self):
        # Refresh the "now" badges on existing cards (timer tick)
        if self._tonight_all:
            self._build_suggestion_grid()

    def _toggle_table(self, visible):
        self.tonight.grp_list.setVisible(visible)
        if visible:
            self.tonight.btn_show_all.setText(
                "▴ " + self.tr("Hide full list"))
        else:
            n = len(self._tonight_all) if self._tonight_all else 0
            self.tonight.btn_show_all.setText(
                "▾ " + self.tr("Show all targets (%1)").replace("%1", str(n)))

    # ---- table (collapsed by default) ----

    def _table_value(self, t, score, key):
        if key == "name":
            return t["name"]
        if key == "kind":
            return {"neo": "NEO", "sn": self.tr("Supernova"),
                    "comet": self.tr("Comet"),
                    "pccp": self.tr("Possible comet"),
                    "transit": self.tr("Transit"),
                    "alert": self.tr("Close approach"),
                    "hads": self.tr("HADS star"),
                    "variable": self.tr("Variable star")
                    }.get(t["kind"], t["kind"])
        if key == "score":
            return float(score)
        if key == "mag":
            return float(t["mag"]) if t.get("mag") is not None else None
        if key == "max_alt":
            # the reachable altitude (horizon-clipped) when computed, else
            # the raw astronomical peak for kinds without local context
            v = t.get("safe_max_alt", t.get("max_alt"))
            return float(v) if v is not None else None
        if key == "best_time":
            # recommended (horizon-safe) time first; the raw peak is only a
            # fallback for kinds that carry no recommendation
            val = t.get("best_time") or t.get("max_time") or ""
            return val[11:16] or "—"
        if key == "nf":
            nf = str(t.get("nf_priority") or "")
            if not nf:
                return None
            ranks = {"none": 0, "minimal": 1, "very low": 2, "low": 3,
                     "med-low": 4, "med": 5, "medium": 5, "med-high": 6,
                     "high": 7, "very high": 8, "critical": 9}
            rank = ranks.get(nf.lower())
            label = self.tr(nf).capitalize()
            return f"{rank} {label}" if rank is not None else nf
        if key == "nobs":
            return float(t["nobs"]) if str(t.get("nobs") or "").isdigit() else None
        if key == "moid":
            return float(t["moid"]) if t.get("moid") is not None else None
        if key == "disc":
            return dates.normalize_date(t.get("disc_date")) or "—"
        if key == "sn_type":
            return t.get("sn_type") or "—"
        if key == "host":
            return t.get("host") or "—"
        if key == "perihelion":
            return (t.get("perihelion_date") or "")[:10] or "—"
        if key == "pccp":
            return float(t["pccp_score"]) if t.get("pccp_score") else None
        if key == "arc":
            return float(t["arc_days"]) if str(t.get("arc_days") or "") \
                .replace(".", "").isdigit() else None
        if key == "window":
            tr = t.get("transit") or {}
            return (f"{tr['ingress'].strftime('%H:%M')}–"
                    f"{tr['egress'].strftime('%H:%M')}") if tr else "—"
        if key == "depth":
            tr = t.get("transit") or {}
            d = tr.get("depth_mmag")
            return float(d) if d else None
        if key == "period":
            p = (t.get("hads") or {}).get("period_h")
            return f"{p:.2f} h" if p else "—"
        if key == "amp":
            a = (t.get("hads") or {}).get("amp")
            return f"Δ {a:.1f}" if a else "—"
        if key == "cycles":
            c = (t.get("hads") or {}).get("cycles")
            return f"{c:.1f}" if c else "—"
        if key == "vperiod":
            per = (t.get("variable") or {}).get("period_d")
            return f"{per:.1f} d" if per else "—"
        if key == "vext":
            nxt = (t.get("variable") or {}).get("next_extremum") or {}
            days = nxt.get("days")
            if days is None:
                return "—"
            lab = self.tr("max") if nxt.get("kind") == "max" \
                else self.tr("min")
            return f"{lab} ~{days:.0f} d"
        if key == "camp":
            return (t.get("campaign") or {}).get("name") or "—"
        if key == "adate":
            return (t.get("approach") or {}).get("date", "—")
        if key == "ald":
            return float((t.get("approach") or {}).get("dist_ld") or 0) or None
        if key == "adiam":
            return float((t.get("approach") or {}).get("diameter_m") or 0) or None
        if key == "amag":
            a = t.get("approach") or {}
            return float(a["mag_max"]) if a.get("mag_max") else None
        if key == "avel":
            a = t.get("approach") or {}
            return float(a["vel_kms"]) if a.get("vel_kms") else None
        if key == "obs":
            # ADR-036 J3: the ✔ means "covered" — a project closed or a
            # post already written (the project world replaced the
            # never-written observations table)
            return "✔" if project.activity_for(db, t["id"])["covered"]                 else ""
        return "—"

    def _fill_table(self, want=None):
        # The full list as themed rows (UX v3 phase C): same data as before,
        # but the row is the unit — kind-tinted, the top 3 wear a stronger
        # tint (a quiet podium, like the wide rows above), hover and
        # selection come from the global theme (ADR-026). Double-click a row
        # to start / continue its project. WORKFLOWS 7quater: the kind comes
        # from the header combo (want=None -> every enabled kind).
        if want is None:
            want = self.tonight.cmb_filter.currentData()
        cols = TABLE_COLS.get(want, TABLE_COLS_DEFAULT)
        show_obs = self.tonight.chk_show_observed.isChecked()
        tbl = self.tonight.tbl_targets
        score_idx = next((i for i, (_h, k) in enumerate(cols) if k == "score"),
                          1)
        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)
        tbl.setColumnCount(len(cols))
        tbl.setHorizontalHeaderLabels([self.tr(h) for h, _k in cols])
        # start from the whitelist-aware visible set (the grid uses the very
        # same helper, so both views always agree on what "All" means), then
        # apply the observed-only switch
        kept = [x for x in self._visible_targets(want)
                if show_obs
                or not project.activity_for(db, x[0]["id"])["covered"]]
        # best first (score desc, name asc) so the podium tints land on the
        # top 3 of what is actually shown
        kept.sort(key=lambda x: (-x[1], x[0]["name"]))
        for i, (t, score, _parts, phrase) in enumerate(kept):
            row = tbl.rowCount()
            tbl.insertRow(row)
            kind_color = self._KIND_COLORS.get(t.get("kind"), "#888888")
            # quiet row tint; the top 3 wear a stronger kind-color tinge
            # (hover and selection come from the global theme, ADR-026)
            base = QColor(255, 255, 255, 9)
            if i < 3:
                base = QColor(kind_color)
                base.setAlpha(48)
            for col, (_h, key) in enumerate(cols):
                val = self._table_value(t, score, key)
                if isinstance(val, float):
                    item = QTableWidgetItem()
                    item.setData(Qt.DisplayRole, val)
                else:
                    item = QTableWidgetItem(val if val is not None else "—")
                bold = key in ("name", "score")
                if bold:
                    f = item.font()
                    f.setBold(True)
                    item.setFont(f)
                item.setBackground(QBrush(base))
                item.setForeground(
                    QBrush(QColor(kind_color if bold else theme.C_TEXT)))
                if col == 0:
                    item.setToolTip(self._txt(phrase))
                    item.setData(Qt.UserRole, t)
                tbl.setItem(row, col, item)
        tbl.setSortingEnabled(True)
        tbl.sortItems(score_idx, Qt.DescendingOrder)
        tbl.resizeColumnsToContents()
        if not self.tonight.btn_show_all.isChecked():
            self.tonight.btn_show_all.setText(
                "▾ " + self.tr("Show all targets (%1)").replace(
                    "%1", str(len(self._tonight_all))))

    def _table_open_explore(self, row, _col):
        # Phase E (single entry point): a double click on any column of
        # the full list opens the Explore dialog for that target — the
        # same target that the row's click opens, and the same destination
        # the "Explore" shortcut of the card uses. The project is still
        # created from the Explore dialog's own "Create project" button,
        # so the gesture is consistent across both views (the full list
        # is no longer a silent project creator).
        tbl = self.tonight.tbl_targets
        for col in range(tbl.columnCount()):
            item = tbl.item(row, col)
            if item is None:
                continue
            t = item.data(Qt.UserRole)
            if t:
                self._open_explore_dialog(t.get("name") or t.get("id"))
                return

    # ---------------- Projects (ADR-019 v3.1) ----------------

    def _on_main_tab_changed(self, index):
        # @args: index - the newly selected top-level tab index
        #        (TAB_PROJECTS == the hub, TAB_CAMPAIGNS == the
        #        campaigns manager, per main_window.ui order)
        # @return: None
        # Keep both master-detail tabs always fresh on every visit.
        if index == TAB_PROJECTS:
            self.on_refresh_projects()
        elif index == TAB_CAMPAIGNS:
            self._refresh_campaigns_tab()

    def _rebuild_campaign_filter(self):
        # Refills the hub's campaign combo, keeping the current selection.
        # @return: None
        from ..core import campaign as _camp
        cmb = self.projects.cmb_campaign
        current = cmb.currentData()
        cmb.blockSignals(True)
        cmb.clear()
        cmb.addItem(self.tr("All campaigns"), None)
        for c in _camp.list_campaigns(db):
            cmb.addItem(c["name"], c["id"])
        idx = cmb.findData(current)
        if idx < 0 and not getattr(self, "_campaign_filter_restored", False):
            # restore the persisted campaign filter once per session (U0.6)
            self._campaign_filter_restored = True
            saved = config.get("projects_filter_campaign", "")
            if saved != "":
                idx = cmb.findData(saved)
        cmb.setCurrentIndex(idx if idx >= 0 else 0)
        cmb.blockSignals(False)

    # ---------------- campaigns tab (UX-a) ----------------

    def _refresh_campaigns_tab(self):
        # Refills the campaign list as HEALTH CARDS (UX-PC U5): each row
        # shows the cadence health as dots (● up to date / ○ due) and the
        # next action in words; finished ones dim. The plain text stays on
        # the item as the accessible/searchable fallback (same pattern as
        # the projects hub rows, U2).
        from ..core import campaign as _camp
        lst = self.campaigns.lst_campaigns
        sel = lst.currentItem()
        keep_id = sel.data(Qt.UserRole) if sel is not None else None
        # keep the caller's own signal block intact (blockSignals is a
        # plain boolean — save/restore, never force)
        was_blocked = lst.signalsBlocked()
        lst.blockSignals(True)
        lst.clear()
        for c in _camp.list_campaigns(db):
            rep = _camp.status_report(db, c["id"])
            members = rep["members"] if rep else []
            due = sum(1 for m in members if m["due"])
            finished = c["status"] == _camp.CAMPAIGN_FINISHED
            text = c["name"]
            if c.get("group_name"):
                text += f"  ({c['group_name']})"
            text += "  —  " + self.tr("%1 projects · %2 due")\
                .replace("%1", str(len(members))).replace("%2", str(due))
            if any(m.get("event") for m in members):
                text += "  ⚡"
            if finished:
                text += "  " + self.tr("(finished)")
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, c["id"])
            if finished:
                item.setForeground(QColor(theme.C_TEXT_DIM))
            # the item's height must carry the row's fixed height (56): the
            # list lays items out from this hint, NOT from the attached
            # widget. A QSize(-1, h) is normalised to an *invalid* hint by
            # PySide and silently ignored, which squeezed the rows to the
            # text height — use a valid zero width instead.
            item.setSizeHint(QSize(0, 56))
            lst.addItem(item)
            row = CampaignRow()
            row.set_campaign(
                name=c["name"], group=c.get("group_name") or "",
                finished=finished, members=len(members),
                up_to_date=len(members) - due,
                next_text=self._campaign_next_text(members),
                has_event=any(m.get("event") for m in members))
            row.clicked.connect(
                lambda it=item: self.campaigns.lst_campaigns
                .setCurrentItem(it))
            row.context_menu.connect(
                lambda pos, it=item: self._campaign_row_menu(it, pos))
            lst.setItemWidget(item, row)
            if c["id"] == keep_id:
                lst.setCurrentItem(item)
        lst.blockSignals(was_blocked)
        self._campaign_row_selection_sync(lst.currentItem(), None)
        # the rebuild swallowed the selection signals: settle the detail
        # explicitly (it also clears the detail side when nothing is
        # selected and refreshes the Close/Reopen button's label)
        self._campaign_selected()
        self._refresh_campaign_signals()

    def _campaign_next_text(self, members):
        # @args: members - status_report member rows
        # @return: the campaign's next action in plain words: the firing
        #          event first, then the most overdue member, else calm
        ev = next((m for m in members if m.get("event")), None)
        if ev:
            return self.tr("measure %1 tonight").replace(
                "%1", ev["object_name"])
        due = [m for m in members if m["due"]]
        if due:
            m = max(due, key=lambda m: m["overdue_days"])
            return self.tr("measure %1 — %2 d since the last visit") \
                .replace("%1", m["object_name"]) \
                .replace("%2", str(m["overdue_days"]))
        if not members:
            return ""
        return self.tr("all up to date ✓")

    def _campaign_row_selection_sync(self, current, _previous):
        # Paints the selection on the campaign cards (the item widget
        # covers the list's own highlight, so the rows do it themselves).
        lst = self.campaigns.lst_campaigns
        for i in range(lst.count()):
            item = lst.item(i)
            row = lst.itemWidget(item)
            if row is not None:
                row.set_selected(item is current)

    def _campaign_row_menu(self, item, global_pos):
        # Right-click on a campaign card: the same menu as the plain list.
        self.campaigns.lst_campaigns.setCurrentItem(item)
        self._open_campaign_menu(item, global_pos)

    def _refresh_campaign_signals(self):
        # Fills the signals console (ADR-037 SC2): the coverage line and
        # the live signal list — detector events first (the strongest
        # news), then upcoming extrema ordered by arrival. A double-click
        # on a row opens its project in the hub.
        # U7 (UX-PC close): the strip says what it is BEFORE the numbers —
        # the scope line sits in the .ui; the coverage line names WHAT is
        # up to date, and an empty list is a calm state, not a dead one.
        from ..core import campaign as _camp
        w = self.campaigns
        rep = _camp.signals_report(
            db,
            config.get("campaign_extremum_days", 3),
            config.get("event_mag_threshold", 0.5))
        if rep["members"] == 0:
            w.lbl_cov.setToolTip("")
            w.lbl_cov.setText(
                tr("You follow no campaigns yet — create one below and "
                   "its stars will show up here."))
        else:
            w.lbl_cov.setToolTip(tr("Measured within their campaign's "
                                    "cadence"))
            w.lbl_cov.setText(
                tr("Up to date: %1 of %2 campaign projects",
                   rep["up_to_date"], rep["members"]))
        lst = w.lst_signals
        lst.clear()
        for row in rep["signals"]:
            # UX-PC (U5): the icon leads the row (⚡ event / ⏳ extremum)
            # and the text is a full sentence, never a code
            icon = "⚡" if row.get("event") else "⏳"
            item = QListWidgetItem(
                f"{icon} {row['project']['object_name']} · "
                f"{row['campaign']} — {self._format_campaign_signal(row)}")
            item.setData(Qt.UserRole, row["project"]["id"])
            lst.addItem(item)
        # 👁 vigil alerts (ADR-037 SC4a), cache-only re-read: the console
        # never touches the network — it shows what the last Tonight run
        # left in the short-TTL vigil cache, or nothing
        from ..core import vigils as _vig
        for a in _vig.cached_alerts(config, db):
            item = QListWidgetItem(
                f"👁 {a['name']} — {self._format_vigil_signal(a)}")
            item.setData(Qt.UserRole, "vigil")
            item.setData(Qt.UserRole + 1, a["name"])
            lst.addItem(item)
        if lst.count() == 0:
            # U7: calm is a STATE, not an absence — say what is being
            # watched and what will make it appear
            item = QListWidgetItem(
                tr("✨ All calm — when a star you follow erupts, dims or "
                   "nears a predicted extremum, it will show up here."))
            item.setFlags(Qt.NoItemFlags)   # empty state: not clickable
            lst.addItem(item)

    @staticmethod
    def _format_campaign_signal(row):
        # @args: row - a signals_report row
        # @return: the human part of the row — the event, or the countdown
        ev, ex = row["event"], row["extremum"]
        if ev:
            # inverted magnitude axis: a "drop" is the star dimming
            word = "down" if ev["direction"] == "drop" else "up"
            return tr("%1 mag %2 in %3 — measure tonight",
                      ev["delta_mag"], tr(word), ev["filter"])
        if ex:
            word = "maximum" if ex["kind"] == "max" else "minimum"
            return tr("%1 expected in %2 d", tr(word), f"{ex['days']:.1f}")
        return ""

    @staticmethod
    def _format_vigil_signal(a):
        # @args: a - a vigil alert dict (vigils.check_vigils)
        # @return: the human part of the row — direction, delta, band
        word = "up" if a.get("direction") == "rise" else "down"
        return tr("%1 mag %2 in ZTF %3 (baseline %4)",
                  abs(a.get("delta") or 0.0), tr(word),
                  a.get("filter") or "?", a.get("baseline_mag") or 0.0)

    def _camp_signal_opened(self, item):
        # Double-click on a signal row: open the project it points at.
        # Vigil rows carry the star name: they jump to its project when
        # one exists (SC-g fusion), else to Explore. Empty-state rows
        # carry no data, so they are no-ops.
        if item is None:
            return
        if item.data(Qt.UserRole) == "vigil":
            name = item.data(Qt.UserRole + 1) or ""
            if name and not self._goto_active_project(name):
                self._open_explore_dialog(name)
            return
        if item.data(Qt.UserRole) is not None:
            self._goto_project_by_id(item.data(Qt.UserRole))

    def _selected_campaign_id(self):
        # @return: campaign id selected in the tab's list, or None
        item = self.campaigns.lst_campaigns.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _campaign_selected(self):
        # Fills the whole campaign detail: header, protocol, URLs and the
        # members table with the per-target cadence health (UX-b).
        from PySide6.QtWidgets import QAbstractItemView
        w = self.campaigns
        cid = self._selected_campaign_id()
        from ..core import campaign as _camp
        rep = _camp.status_report(db, cid) if cid is not None else None
        tbl = w.tbl_members
        if rep is None:
            # UX-PC (U5): the empty state TEACHES the concept (this text
            # used to sit as a permanent label above the list), and the
            # action buttons stay disabled — no silent no-ops
            w.lbl_cname.setText(self.tr("What is a campaign?"))
            w.lbl_cmeta.setText("—")
            w.lbl_cgoal.setText(self.tr(
                "A campaign groups the projects of one shared observation "
                "effort — several nights, several observatories, one goal "
                "(e.g. “T CrB 2026 eruption”). A project is one object "
                "with its three steps: capture, track, follow-up."))
            w.lbl_urls.setText("")
            w.lbl_protocol.setText("—")
            tbl.setRowCount(0)
            tbl.setColumnCount(0)
            for b in (w.btn_cedit, w.btn_cclose, w.btn_cmore):
                b.setEnabled(False)
            return
        c = rep["campaign"]
        w.lbl_cname.setText(c["name"])
        # UX-PC (U5): the header actions follow the campaign's state
        is_active = c["status"] == _camp.CAMPAIGN_ACTIVE
        for b in (w.btn_cedit, w.btn_cclose, w.btn_cmore):
            b.setEnabled(True)
        w.btn_cclose.setText(
            self.tr("Close") if is_active else self.tr("Reopen"))
        status = self.tr("active") if c["status"] == \
            _camp.CAMPAIGN_ACTIVE else self.tr("finished")
        meta = [status]
        if c.get("group_name"):
            meta.append(c["group_name"])
        if c.get("coordinator"):
            meta.append(c["coordinator"])
        w.lbl_cmeta.setText(" · ".join(meta))
        w.lbl_cgoal.setText(c.get("goal") or "")
        # protocol block (plain readable text; the fields are free text)
        prot = c.get("protocol") or {}
        cad = int(prot.get("cadence_nights", 1) or 1)
        lines = [self.tr("One measurement every %1 night(s) per filter"
                         ).replace("%1", str(cad))]
        if prot.get("filters"):
            lines.append(self.tr("Filters: %1").replace(
                "%1", ", ".join(prot["filters"])))
        if prot.get("comp_stars"):
            lines.append(self.tr("Comparison stars: %1").replace(
                "%1", ", ".join(prot["comp_stars"])))
        if prot.get("notes"):
            lines.append(prot["notes"])
        w.lbl_protocol.setText("\n".join(lines))
        # clickable URLs (linkActivated is connected once in _connect)
        links = []
        if c.get("report_url"):
            links.append("<a href='%1'>%2</a>".replace(
                "%1", c["report_url"]).replace("%2", self.tr("Report form")))
        if c.get("data_url"):
            links.append("<a href='%1'>%2</a>".replace(
                "%1", c["data_url"]).replace("%2", self.tr("Data")))
        w.lbl_urls.setText(" · ".join(links))
        # members table: object | kind | last visit | status
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels([
            self.tr("Object"), self.tr("Kind"), self.tr("Last visit"),
            self.tr("Status")])
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        tbl.verticalHeader().setVisible(False)
        tbl.setRowCount(0)
        for m in rep["members"]:
            row = tbl.rowCount()
            tbl.insertRow(row)
            name_item = QTableWidgetItem(m["object_name"])
            name_item.setData(Qt.UserRole, m["id"])
            tbl.setItem(row, 0, name_item)
            tbl.setItem(row, 1, QTableWidgetItem(
                theme.KIND_LABELS.get(m["kind"], m["kind"])))
            last = "—" if m["days_since"] is None else \
                self.tr("%1 d ago").replace("%1", str(m["days_since"]))
            tbl.setItem(row, 2, QTableWidgetItem(last))
            if m["event"]:
                st, col = self.tr("⚡ brightness event"), theme.C_WARN
            elif m["due"] and m["days_since"] is None:
                st, col = self.tr("● never visited"), theme.C_WARN
            elif m["due"]:
                st, col = self.tr("⚠ %1 d overdue").replace(
                    "%1", str(m["overdue_days"])), theme.C_WARN
            else:
                st, col = self.tr("✓ up to date"), theme.C_GOOD
            st_item = QTableWidgetItem(st)
            st_item.setForeground(QColor(col))
            tbl.setItem(row, 3, st_item)

    def on_refresh_projects(self):
        self._rebuild_campaign_filter()
        idx = self.projects.cmb_filter.currentIndex()
        statuses = ("active", None, "done", "archived")
        status = statuses[idx] if idx < len(statuses) else None
        # A3: classification — kind, search, favorites, sort
        kind_idx = self.projects.cmb_kind.currentIndex()
        kinds = (None, "sn", "neo", "comet", "pccp", "transit", "hads",
                 "variable")
        kind = kinds[kind_idx] if kind_idx < len(kinds) else None
        search = self.projects.edt_search.text().strip() or None
        tag = self.projects.edt_tag.text().strip() or None
        camp_id = self.projects.cmb_campaign.currentData()
        sort_idx = self.projects.cmb_sort.currentIndex()
        # UX-PC (U2): index 0 is "Needs you" — the attention order; the
        # other entries are the classic core orders
        orders = (None, "updated", "created", "name")
        order = orders[sort_idx] if sort_idx < len(orders) else None
        favorites = self.projects.chk_favorites.isChecked()
        # persist the prefs (pattern of WORKFLOWS 7quater)
        config.set("projects_filter_kind", kind_idx)
        config.set("projects_filter_sort_v2", sort_idx)
        config.set("projects_filter_fav", favorites)
        config.set("projects_filter_campaign", camp_id or "")
        projects_list = project.list_projects(
            db, status, kind=kind, search=search, tags=tag,
            campaign_id=camp_id,
            favorites_first=favorites, order=order or "updated")
        # UX-PC (U2): one attention report feeds both the dashboard and the
        # "Needs you" row order (a project that calls for action floats up)
        self._attention = attention.attention_report(db, config)
        attn_map = {e["project_id"]: e for e in self._attention}
        if order is None:
            # stable: the core order (favorites + updated) breaks ties
            # inside the same urgency rung
            projects_list = sorted(
                projects_list,
                key=lambda p: attention.URGENCY_RANK.get(
                    attn_map.get(p["id"], {}).get("urgency"), 2)
                if p["id"] in attn_map else 3)
        from ..core import campaign as _camp
        camp_names = {c["id"]: c["name"] for c in _camp.list_campaigns(db)}
        lst = self.projects.lst_projects
        # preserve the selected project across the refresh (the list reloads
        # on every visit to the tab and at startup, so we must not drop the
        # project the user is currently viewing)
        sel = lst.currentItem()
        keep_id = sel.data(Qt.UserRole) if sel is not None else None
        # block selection signals while the rows are rebuilt — and restore
        # the PREVIOUS blocked state afterwards (blockSignals is a plain
        # boolean: an unconditional False would tear down a caller's own
        # block, and the selection would fire mid-rebuild)
        was_blocked = lst.signalsBlocked()
        lst.blockSignals(True)
        lst.clear()
        # A3: group by year of created (section headers, non-selectable) —
        # only when the order keeps years monotonic (attention order mixes
        # them on purpose: what needs you floats up regardless of age)
        last_year = None
        for p in projects_list:
            if order is not None:
                year = datetime.datetime.fromtimestamp(p["created"]).year
                if year != last_year:
                    last_year = year
                    header = QListWidgetItem(f"— {year} —")
                    header.setFlags(Qt.NoItemFlags)
                    font = header.font()
                    font.setBold(True)
                    header.setFont(font)
                    header.setTextAlignment(Qt.AlignCenter)
                    lst.addItem(header)
            kind_label = {"sn": "SN", "neo": "NEO", "comet": self.tr("Comet"),
                          "pccp": "PCCP", "transit": self.tr("Transit"),
                          "hads": "HADS",
                          "variable": self.tr("Variable")}.get(
                          p["kind"], p["kind"])
            cur = project.current_step(db, p["id"]) or "done"
            step_n = _STEP_KEYS.index(cur) + 1 if cur in _STEP_KEYS else 3
            star = "★ " if p.get("favorite") else ""
            item = QListWidgetItem(
                f"{star}[{kind_label}] {p['object_name']}  {step_n}/3")
            item.setData(Qt.UserRole, p["id"])
            if p.get("campaign_id"):
                item.setText(item.text() + " ⚑")
                item.setToolTip(self.tr("Campaign: %1").replace(
                    "%1", camp_names.get(p["campaign_id"], "?")))
            # the item's height must carry the row's fixed height (74): the
            # list lays items out from this hint, NOT from the attached
            # widget. A QSize(-1, h) is normalised to an *invalid* hint by
            # PySide and silently ignored, which squeezed the rows to the
            # text height — use a valid zero width instead.
            item.setSizeHint(QSize(0, 74))
            lst.addItem(item)
            # UX-PC (U2): the rich row — the plain text above stays as the
            # accessible/searchable fallback under the widget
            row = ProjectRow()
            payload = self._project_row_payload(
                p, attn_map.get(p["id"]), camp_names)
            urgency = payload.pop("_urgency", None)
            row.set_project(**payload)
            if urgency == "event":
                row.lbl_next.setStyleSheet(
                    f"color: {theme.C_EVENT}; font-weight: bold;")
            elif urgency == "due":
                row.lbl_next.setStyleSheet(
                    f"color: {theme.C_WARN}; font-weight: bold;")
            row.clicked.connect(
                lambda it=item: self.projects.lst_projects
                .setCurrentItem(it))
            row.double_clicked.connect(
                lambda it=item: self._row_double_clicked(it))
            row.context_menu.connect(
                lambda pos, it=item: self._project_row_menu(it, pos))
            lst.setItemWidget(item, row)
            if p["id"] == keep_id:
                lst.setCurrentItem(item)
        lst.blockSignals(was_blocked)
        self._project_row_selection_sync(lst.currentItem(), None)
        # signals were blocked for the rebuild: settle the selection
        # aftermath explicitly (U0.2: no stale detail when the selected
        # project leaves the list — the pane then lands on the dashboard).
        # A kept selection does NOT reload the detail here: the callers
        # that mutate projects rebuild the page themselves.
        if lst.currentItem() is None:
            self._clear_project_detail()

    # ---------------- UX-PC (U2): rich rows + dashboard ----------------

    @staticmethod
    def _activity_words(p):
        # @args: p - project dict (list row)
        # @return: "today" / "yesterday" / "N d ago" from the updated stamp
        days = int((datetime.datetime.now().timestamp()
                    - (p.get("updated") or 0)) / 86400)
        if days <= 0:
            return tr("today")
        if days == 1:
            return tr("yesterday")
        return tr("%1 d ago").replace("%1", str(days))

    def _project_window_chip(self, p, full):
        # The "up tonight HH:MM–HH:MM" chip (UX-PC U2): fresh local maths
        # from the object's coords — never the stale creation-night
        # snapshot. Empty when the object is down tonight or has no coords.
        # @args: p - list row, full - the same project with steps
        # @return: chip text or ""
        if p["status"] != project.STATUS_ACTIVE:
            return ""
        ctx = p.get("context") or {}
        ra, dec = ctx.get("ra_deg"), ctx.get("dec_deg")
        if ra is None or dec is None:
            return ""
        plan = next((s["data"] for s in full.get("steps", [])
                     if s["step"] == "plan"), {})
        duration = 3600.0
        if plan.get("n_frames") and plan.get("exp_s"):
            duration = float(plan["n_frames"]) * (
                float(plan["exp_s"]) + float(config.get("overhead_s", 15.0)))
        try:
            from ..core import planner
            w = planner.safe_window_for(ra, dec, config, duration)
        except Exception:
            return ""
        if not w.get("window_start") or not w.get("window_end"):
            return tr("✕ not up tonight")
        try:
            t0 = datetime.datetime.fromisoformat(
                w["window_start"]).strftime("%H:%M")
            t1 = datetime.datetime.fromisoformat(
                w["window_end"]).strftime("%H:%M")
        except (TypeError, ValueError):
            return ""
        return f"⊕ {t0}–{t1}"

    def _project_row_payload(self, p, attn, camp_names):
        # @args: p - the list row, attn - its attention entry or None,
        #        camp_names - {campaign id: name}
        # @return: the kwargs dict for ProjectRow.set_project
        from ..core import followup as _fu
        kind = p["kind"]
        kind_color = self._KIND_COLORS.get(kind, "#888888")
        kind_label = {"sn": "SN", "neo": "NEO", "comet": self.tr("Comet"),
                      "pccp": "PCCP", "transit": self.tr("Transit"),
                      "hads": "HADS",
                      "variable": self.tr("Variable")}.get(kind, kind)
        full = project.get(db, p["id"]) or p
        steps = {s["step"]: s["status"] for s in full.get("steps", [])}
        dots = "".join(
            "●" if steps.get(k) == "done"
            else "–" if steps.get(k) == "skipped" else "○"
            for k in _STEP_KEYS)
        if p["status"] == project.STATUS_ACTIVE:
            next_text = self._next_action_text(
                project.next_action(db, full))
        elif p.get("closed_at"):
            dt = datetime.datetime.fromtimestamp(p["closed_at"])
            next_text = self.tr("closed %1").replace(
                "%1", dt.strftime("%Y-%m-%d"))
        else:
            next_text = self.tr("archived")
        # urgency paints the next action (the row says WHY it floats up)
        urgency = (attn or {}).get("urgency")
        spark = None
        if kind in FOLLOWUP_KINDS:
            # sparkline stroked in the row's kind hue (the anchor the chip
            # and the icon tile already carry)
            spark = sparkline_pixmap(
                _fu.list_points(db, p["id"]), color=kind_color)
        return {
            "kind_label": kind_label, "kind_color": kind_color,
            "name": p["object_name"], "favorite": bool(p.get("favorite")),
            "campaign_name": camp_names.get(p.get("campaign_id")),
            "progress_text": dots, "next_text": next_text,
            "activity_text": self._activity_words(p),
            "window_text": self._project_window_chip(p, full),
            "sparkline": spark,
            # the icon tile's glyph, drawn by the caller (unknown kinds
            # render a flat tint tile instead)
            "icon": self._type_pixmap(kind, size=28),
            # not a widget field: the urgency tint is applied after
            "_urgency": urgency,
        }

    def _project_row_selection_sync(self, current, _previous):
        # Paints the selection on the rich rows (the item widget covers the
        # list's own highlight, so the rows do it themselves).
        # @args: current - the newly current item (or None)
        lst = self.projects.lst_projects
        for i in range(lst.count()):
            item = lst.item(i)
            row = lst.itemWidget(item)
            if row is not None:
                row.set_selected(item is current)

    def _row_double_clicked(self, item):
        # Rich-row double-click = open at the current step (the same
        # gesture as the plain list underneath).
        self.projects.lst_projects.setCurrentItem(item)
        self._project_open_activated(item)

    def _project_row_menu(self, item, global_pos):
        # Right-click on a rich row: the same menu as the plain list.
        self.projects.lst_projects.setCurrentItem(item)
        self._open_project_menu(item, global_pos)

    # ---------------- UX-PC (U2): the attention dashboard ----------------

    def _next_action_text(self, act):
        # The project's voice in ONE plain line (UX-i + U2): shared by the
        # Next card, the rich rows and the dashboard cards.
        # @args: act - a project.next_action() dict
        # @return: the text
        if act["never_visited"]:
            analysis_txt = self.tr("First measurement — it opens the "
                                   "series")
        elif act["overdue_days"] is not None:
            analysis_txt = self.tr("Measure tonight — %1 d since the "
                                   "last visit").replace(
                "%1", str(act["overdue_days"]))
        else:
            analysis_txt = self.tr("Analyse your data")
        texts = {
            "analysis": analysis_txt,
            "plan": self.tr("Plan the capture"),
            "publish": self.tr("Draft the post"),
            "close": self.tr("All steps done — consider closing the "
                             "project"),
        }
        return texts[act["key"]]

    def _attention_text(self, e):
        # @args: e - an attention_report entry
        # @return: the full-sentence reason (the dashboard rows are plain
        #          words, never codes)
        name = e["object_name"]
        if e["reason"] == "event":
            ev = e["event"] or {}
            word = self.tr("down") if ev.get("direction") == "drop" \
                else self.tr("up")
            return self.tr("⚡ %1 — %2 mag %3 in %4 — measure tonight") \
                .replace("%1", name).replace("%2", str(ev.get("delta_mag"))) \
                .replace("%3", word).replace("%4", str(ev.get("filter")))
        if e["reason"] == "due":
            return self.tr("⏳ %1 — %2 nights since the last visit") \
                .replace("%1", name).replace("%2", str(e["overdue_days"]))
        if e["reason"] == "never_visited":
            return self.tr("⏳ %1 — the first measurement opens the "
                           "series").replace("%1", name)
        if e["reason"] == "extremum":
            ex = e["extremum"] or {}
            word = self.tr("maximum") if ex.get("kind") == "max" \
                else self.tr("minimum")
            return self.tr("⏳ %1 — %2 expected in ~%3 d") \
                .replace("%1", name).replace("%2", word) \
                .replace("%3", str(ex.get("days")))
        text = self._next_action_text(
            {"key": e["reason"], "overdue_days": None,
             "never_visited": False})
        return f"○ {name} — {text[0].lower() + text[1:] if text else ''}"

    def _attention_card(self, e):
        # @args: e - an attention_report entry
        # @return: a QFrame card: urgency band + the reason in words + one
        #          action button landing on the right section
        colors = {"event": theme.C_EVENT, "due": theme.C_WARN,
                  "info": theme.C_OK}
        color = colors.get(e["urgency"], theme.C_OK)
        card = QFrame()
        card.setObjectName("attcard")
        card.setStyleSheet(
            f"QFrame#attcard {{ background: {theme.C_BASE};"
            f" border-radius: 8px; border: 1px solid {theme.C_LINE}; }}")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(0, 8, 10, 8)
        lay.setSpacing(10)
        band = QFrame()
        band.setFixedWidth(4)
        band.setStyleSheet(f"background: {color}; border-radius: 2px;")
        lay.addWidget(band)
        text = self._attention_text(e)
        if e.get("campaign"):
            text += "  ·  ⚑ " + e["campaign"]
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lay.addWidget(lbl, 1)
        btn = QPushButton(
            self.tr("Measure →") if e.get("section") == "analysis"
            else self.tr("Go →"))
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _=False, entry=e:
                            self._dashboard_goto(entry))
        lay.addWidget(btn, 0, Qt.AlignVCenter)
        return card

    def _dashboard_goto(self, e):
        # A dashboard card button: open the project AND land on the
        # section the reason calls for (the app speaks, then walks you).
        # @args: e - the attention entry behind the card
        if self._goto_project_by_id(e["project_id"]) and e.get("section"):
            self._scroll_to_section(e["section"])

    def _refresh_dashboard(self):
        # Fills the dashboard page from the last attention report (UX-PC
        # U2). Three states: no projects at all (a pointer to Tonight),
        # nothing calling (calm), and the calling cards.
        lay = self.projects.dash_container.layout()
        self._wipe_layout(lay)
        entries = getattr(self, "_attention", None)
        if entries is None:
            entries = attention.attention_report(db, config)
        any_projects = bool(project.list_projects(db))
        if not any_projects:
            self.projects.lbl_dash_title.setText(
                self.tr("Your projects live here"))
            self.projects.lbl_dash_sub.setText(
                self.tr("A project is one object with its three steps: "
                        "capture, track, follow-up. Pick an object in "
                        "Tonight and it becomes a project that guides "
                        "you."))
            box = QLabel(
                self.tr("No projects yet — tonight's best objects are on "
                        "the Tonight tab."))
            box.setWordWrap(True)
            box.setStyleSheet(f"color: {theme.C_TEXT_DIM}; padding: 12px;")
            lay.addWidget(box)
            btn = QPushButton(self.tr("Go to Tonight →"))
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda: self._goto_tab(TAB_TONIGHT))
            lay.addWidget(btn, 0, Qt.AlignLeft)
        elif not entries:
            self.projects.lbl_dash_title.setText(
                self.tr("Needs your attention"))
            self.projects.lbl_dash_sub.setText(
                self.tr("Your projects calling for action, most urgent "
                        "first."))
            box = QLabel(self.tr("✨ All quiet — nothing needs you "
                                 "tonight. Clear skies!"))
            box.setWordWrap(True)
            box.setStyleSheet(f"color: {theme.C_TEXT_DIM}; padding: 12px;")
            lay.addWidget(box)
        else:
            self.projects.lbl_dash_title.setText(
                self.tr("Needs your attention"))
            self.projects.lbl_dash_sub.setText(
                self.tr("Your projects calling for action, most urgent "
                        "first."))
            for e in entries[:5]:
                lay.addWidget(self._attention_card(e))
        lay.addStretch()

    def _show_dashboard(self):
        # Swaps the right pane to the dashboard (no selection) and fills it.
        self._refresh_dashboard()
        self.projects.stack_detail.setCurrentWidget(
            self.projects.page_dashboard)

    def _project_selected(self):
        items = self.projects.lst_projects.selectedItems()
        if not items:
            self._clear_project_detail()
            return
        pid = items[0].data(Qt.UserRole)
        p = project.get(db, pid)
        if not p:
            self._clear_project_detail()
            return
        self._current_project = p
        # UX-PC (U2): the right pane shows the project page when there is
        # a selection, the dashboard when there is none
        self.projects.stack_detail.setCurrentWidget(
            self.projects.page_detail)
        self._render_project_header(p)
        self._build_project_page(p)
        panel = self._get_proj_panel()
        if panel._worker is not None:
            panel.cancel()   # switching projects: drop the in-flight load
        ctx = dict(p.get("context") or {})
        ctx.setdefault("project_id", p["id"])   # B4: light-curve injection
        panel.explore(p["object_name"], fallback_target=ctx, ctx=ctx)

    def _project_open_activated(self, item):
        # Double-click / Enter on a project row (UX-c): jump straight to
        # its current step's section (single click stays near the top).
        if item is None or item.data(Qt.UserRole) is None:
            return
        self.projects.lst_projects.setCurrentItem(item)
        p = self._current_project
        if not p or p["status"] != project.STATUS_ACTIVE:
            return
        self._scroll_to_section(
            self._next_target_key(self._current_project))

    def _project_context_menu(self, pos):
        # Right-click on the projects list (UX-c): all the row actions,
        # with state-aware enablement.
        item = self.projects.lst_projects.itemAt(pos)
        if item is None or item.data(Qt.UserRole) is None:
            return
        self.projects.lst_projects.setCurrentItem(item)
        self._open_project_menu(
            item, self.projects.lst_projects.viewport().mapToGlobal(pos))

    def _open_project_menu(self, item, global_pos):
        # The project context menu body — shared by the plain list and the
        # rich rows (one gesture language, UX-c + UX-PC U2).
        # @args: item - the row's QListWidgetItem, global_pos - where to
        #        pop the menu
        # @return: None
        p = self._current_project
        if not p or item is None:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        act_open = menu.addAction(self.tr("Open"))
        # ADR-045: the Analysis tab exists for every kind (the visits
        # manager is kind-agnostic)
        act_fu = menu.addAction(self._tab_label("analysis"))
        act_fav = menu.addAction(
            self.tr("Unstar") if p.get("favorite")
            else self.tr("Star as favorite"))
        menu.addSeparator()
        act_close = menu.addAction(self.tr("Close project…"))
        act_close.setEnabled(p["status"] == project.STATUS_ACTIVE)
        act_reopen = menu.addAction(self.tr("Reopen"))
        act_reopen.setEnabled(p["status"] != project.STATUS_ACTIVE)
        act_archive = menu.addAction(self.tr("Archive…"))
        act_delete = menu.addAction(self.tr("Delete…"))
        menu.addSeparator()
        act_folder = menu.addAction(self.tr("Show in folder"))
        chosen = menu.exec(global_pos)
        if chosen is act_open:
            self._project_open_activated(item)
        elif chosen is act_fu:
            self._scroll_to_section("analysis")
        elif chosen is act_fav:
            self._project_toggle_favorite()
        elif chosen is act_close:
            self._project_close()
        elif chosen is act_reopen:
            self._project_reopen()
        elif chosen is act_archive:
            self._project_archive()
        elif chosen is act_delete:
            self._project_delete()
        elif chosen is act_folder:
            self._open_project_folder()

    def _project_reclicked(self, item):
        # @args: item - the QListWidgetItem just clicked
        # @return: None — reloads the detail when the clicked row is the
        #          already-selected project
        if item is not None and item.data(Qt.UserRole) == \
                (self._current_project or {}).get("id"):
            self._project_selected()

    def _proj_files_build(self):
        # A4 (rewritten): the project files window (ADR-019, UX v3) is
        # built lazily once and kept alive on self, so it survives a
        # project switch and gets re-populated every time it is shown.
        # @return: the ProjectFilesDialog
        if getattr(self, "_proj_files_dlg", None) is not None:
            return self._proj_files_dlg
        from .project_files_dialog import ProjectFilesDialog
        dlg = ProjectFilesDialog(parent=self)
        dlg.sig_open_ufe.connect(self._proj_file_open_ufe)
        dlg.sig_open_os.connect(self._open_path_with_os)
        self._proj_files_dlg = dlg
        return dlg

    def _show_project_files(self):
        # A4 (rewritten): the masthead "Files (n)" button opens the
        # files window for the current project with a fresh file list.
        # @args: _ - the clicked signal payload
        # @return: None
        p = self._current_project
        if not p:
            return
        dlg = self._proj_files_build()
        dlg.set_project(p)
        dlg.set_files(project.list_files(db, p["id"]))
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _populate_project_files(self, pid):
        # A4 (rewritten): the masthead "Files (n)" button, with the
        # live count (disabled at zero), and the files window table
        # when it is already open and attached to this project.
        # @args: pid - the project id
        # @return: None
        files = project.list_files(db, pid)
        btn = self.projects.btn_files
        btn.setEnabled(len(files) > 0)
        btn.setText(self.tr("Files ({})").format(len(files)))
        dlg = getattr(self, "_proj_files_dlg", None)
        if dlg is not None and dlg.project_id == pid and dlg.isVisible():
            dlg.set_files(files)

    def _proj_file_open_ufe(self, path):
        # A4 (rewritten): a double-clicked plate row opens in the FITS
        # editor with the project's save hook on (files written there
        # get registered) and the project's object attached; the object
        # is re-applied after the load so the annotate marker lands
        # through the fresh WCS (ADR-044).
        # @args: path - the plate path string
        # @return: None
        pid = self._proj_files_dlg.project_id
        p = project.get(db, pid) if pid is not None else None
        if p is None:
            return
        obj = self._ufe_object_from_project(p)
        dlg = self._ufe_open("annotate", hook_pid=p["id"], obj=obj)
        if not dlg.open_plate(str(path)):
            return
        dlg.set_object(obj)

    def _open_path_with_os(self, path):
        # A4 (rewritten): "Open with the system" (menu action, or a
        # double-click on a non-plate row).
        # @args: path - the file path string
        # @return: None
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_project_folder(self):
        # "Show in folder" (⋯ manage menu, UX-PC U1): opens the project's
        # container folder, creating it on first use so it never fails
        # silently. One behavior only — the old divergence (file's parent
        # vs. project folder) is gone.
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        p = self._current_project
        if not p:
            return
        folder = project.storage_dir(p)
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _change_project_folder(self):
        # ADR-032: re-home the current project's container folder. Future
        # exports follow the new root; already-registered files keep their
        # absolute paths, so the history never breaks.
        p = self._current_project
        if not p:
            return
        start = str(project.storage_dir(p))
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("Choose the project folder"), start)
        if not folder:
            return
        updated = project.set_root_dir(db, p["id"], folder)
        if not updated:
            return
        self._current_project = updated
        self._render_project_header(updated)
        self.statusBar().showMessage(
            self.tr("Project folder changed — new files will go there"), 6000)

    # ---------------- object panel (phase D4) ----------------

    def _proj_panel_loader(self, name, fallback_target=None):
        # @args: name - object identifier, fallback_target - the project's
        #         context, so an unconfirmed NEOCP/PCCP still renders
        # @return: a kept, not-yet-started ExploreWorker (the panel starts it)
        from .workers import ExploreWorker
        worker = ExploreWorker(config, name, fallback_target=fallback_target)
        self._keep(worker)   # the hub owns the worker, even if switched away
        return worker

    def _get_proj_panel(self):
        # Reusable object card (lazy): built once, then re-parented into
        # whatever section asks for it on each project-page build (UX-i).
        # UD.5: a page wipe can leave a dangling wrapper behind once its
        # deleteLater() has run — if the C++ card is gone, build a fresh
        # one instead of touching the dead object ("already deleted").
        if self._proj_panel is not None \
                and not Shiboken.isValid(self._proj_panel):
            self._proj_panel = None
        if self._proj_panel is None:
            from .overview import ObjectPanel
            panel = ObjectPanel(loader=self._proj_panel_loader)
            self._proj_panel = panel
        return self._proj_panel

    def _reset_proj_panel(self):
        # Drops any in-flight worker and empties the panel (used when the
        # selection or the project list goes away).
        if self._proj_panel is not None \
                and not Shiboken.isValid(self._proj_panel):
            # UD.5: the C++ card is already gone — nothing in flight to
            # cancel, just drop the dead wrapper (a live cancel() below
            # would not reach it either, and touching it would raise).
            self._proj_panel = None
            return
        if self._proj_panel is not None:
            self._proj_panel.cancel()

    def _clear_project_detail(self):
        # Empties the whole detail side when the selection goes away
        # (closed under the Active filter, filtered out, deleted): header,
        # context, step tabs and the panel worker. Before U0.2 the header
        # and tabs kept showing the vanished project (stale detail).
        # UX-PC (U2): no selection -> the right pane is the dashboard.
        self._current_project = None
        self._reset_proj_panel()
        self._clear_project_page()
        # UX-i: reset the flat masthead (the old rich-text header is gone)
        mast = self.projects
        mast.lbl_mast_icon.clear()
        mast.lbl_mast_name.setText("")
        mast.lbl_mast_kind.setText("")
        mast.lbl_mast_camp.setText("")
        mast.btn_files.setEnabled(False)
        mast.btn_files.setText(self.tr("Files (0)"))
        self.projects.lbl_context.setText("—")
        self.projects.lbl_advisor.setVisible(False)
        self._show_dashboard()

    def _render_project_header(self, p):
        # UX-i: the flat masthead — icon, name, kind chip, campaign
        # link. No rich-text header: the tab bar below (plus the Next
        # card) tells you where the project stands.
        mast = self.projects
        mast.lbl_mast_icon.setPixmap(self._type_pixmap(p["kind"], 28))
        name = p["object_name"]
        if p.get("closed_at"):
            when = datetime.datetime.fromtimestamp(
                p["closed_at"]).strftime("%Y-%m-%d")
            name += f"  —  {self.tr('closed')} {when}"
            if p.get("outcome"):
                name += f"  ({p['outcome']})"
        mast.lbl_mast_name.setText(name)
        # kind chip (the old "[Supernova]" tag, now a solid pill)
        kind = p["kind"]
        mast.lbl_mast_kind.setText(theme.KIND_LABELS.get(kind, kind))
        mast.lbl_mast_kind.setStyleSheet(
            theme.chip_style(theme.KIND_COLORS.get(kind, theme.C_PANEL)))
        # campaign badge (UX-d): the old header link, now on its own label
        if p.get("campaign_id"):
            from ..core import campaign as _camp
            c = _camp.get(db, p["campaign_id"])
            if c:
                mast.lbl_mast_camp.setText(
                    "<a href='campaign://{cid}'>⚑ {lab}: {nm}</a>".format(
                        cid=c["id"], lab=self.tr("campaign"), nm=c["name"]))
        else:
            mast.lbl_mast_camp.setText("")
        ctx = p["context"]
        parts = []
        if ctx.get("mag") is not None:
            parts.append(f"mag {ctx['mag']}")
        if ctx.get("ra_deg") is not None:
            parts.append(f"RA {ctx['ra_deg']:.2f}°")
        if ctx.get("dec_deg") is not None:
            parts.append(f"Dec {ctx['dec_deg']:+.2f}°")
        if ctx.get("rate_arcsec_min"):
            parts.append(f"{ctx['rate_arcsec_min']:.1f}″/min")
        self.projects.lbl_context.setText(" · ".join(parts) or "—")
        # A3: favorite star (☆/★) in the header; the rest of the project
        # management lives in the ⋯ menu next to it (UX-PC U1)
        self.projects.btn_favorite.setText("★" if p.get("favorite") else "☆")
        is_active = p["status"] == project.STATUS_ACTIVE
        # Close advisor (T10): suggest closing when a project has been idle
        # for too long. v1: time-based; the evolution signal from track B
        # (B11) plugs into this same label later. Sugiere, nunca decide.
        advisor = self.projects.lbl_advisor
        # T10: sugerencia descartable — clic en el banner la descarta para
        # esta sesión del proyecto (no persiste; reaparece al refrescar)
        dismissed = self._advisor_dismissed == p["id"]
        if is_active and p.get("updated") and not dismissed:
            days = int((datetime.datetime.now().timestamp() - p["updated"]) / 86400)
            threshold = int(config.get("close_advisor_days", 30))
            if days >= threshold:
                advisor.setText(
                    self.tr("This project has been idle for {} days. "
                            "Consider closing it. (click to dismiss)").format(days))
                advisor.setVisible(True)
            else:
                advisor.setVisible(False)
        else:
            advisor.setVisible(False)

    def _advisor_dismiss(self):
        # A2: dismiss the close-advisor banner for the current project.
        if self._current_project:
            self._advisor_dismissed = self._current_project["id"]
            self.projects.lbl_advisor.setVisible(False)

    def _wipe_layout(self, layout):
        # Delete every widget and nested layout inside `layout`. setParent(None)
        # detaches widgets from the paint tree immediately (so none of them can
        # linger over the new tab content), deleteLater() frees the C++ object.
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                self._wipe_layout(item.layout())

    def _section_layout(self, key, title):
        # One tab PAGE of the project detail (ADR-041): a flat page in
        # the scroll area with a slim header (bold title + state chip)
        # and the per-kind content below. Only one page is visible at a
        # time — the tab bar in the masthead decides which.
        # @args: key - "details"|"plan"|"process"|"publish"|"followup",
        #        title - the visible header text
        # @return: the page's content QLayout (where the per-kind
        #          builders add their widgets, exactly as before)
        page = QWidget(self.projects.page_container)
        page._chip = QLabel(page)
        page._chip.setStyleSheet(theme.chip_style(theme.C_PANEL))
        page._chip.setVisible(False)  # _step_section lifts it with a badge
        header = QHBoxLayout()
        head = QLabel(title, page)
        head.setStyleSheet("font-weight: bold;")
        header.addWidget(head, 1)
        header.addWidget(page._chip)
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 6, 0, 0)
        v.addLayout(header)
        self._tab_pages[key] = page
        self.projects.page_container.layout().addWidget(page)
        page.setVisible(False)  # _show_tab() lifts the active one
        return v

    def _clear_project_page(self):
        # Wipes the project page (ADR-041: one rebuild per project
        # selection, same discipline as the old step tabs).
        self._tab_pages = {}
        self._active_tab = None
        # the registry belongs to the wiped page: stale keys must not
        # survive the rebuild (UD.5)
        self._project_widgets = {}
        # ADR-043: the CCDciel block lives inside the Capture step of this
        # page, so its registry dies with it: worker slots guard through
        # _ccd_widgets() and a wiped registry is an empty dict
        self._obs_widgets = {}
        # the wipe below destroys whatever the page hosted (UD.5: nothing
        # from a wiped page survives): drop the page-level caches so the
        # next build creates fresh ones, and never touch the project
        # files window on purpose: it lives with the app, not the page,
        # so a wipe must not delete it.
        # The reusable ObjectPanel stays put on purpose: it is not killed
        # here (tests may have slotted a fake one in, and a live panel can
        # be re-parented into the new page); _get_proj_panel() checks
        # liveness and rebuilds it only if its C++ object really is gone.
        self._next_step_key = None
        self._wipe_layout(self.projects.page_container.layout())

    def _advanced_block(self, layout, title):
        # A non-accordion collapsible sub-block for the advanced/secondary
        # controls of a step section (UX-PC U3): starts collapsed, never
        # joins the page accordion, plain-language title saying WHAT is
        # inside (no generic "Advanced" drawers).
        # @args: layout - the hosting section content layout,
        #        title - the visible header
        # @return: the block's content QLayout
        from .widgets.collapsible_section import CollapsibleSection
        sec = CollapsibleSection(title)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(12, 0, 0, 0)
        sec.setContentWidget(inner)
        sec.setCollapsed(True)
        layout.addWidget(sec)
        return v

    def _next_target_key(self, p):
        # @return: the section key the Next card points at
        act = project.next_action(db, p)
        return {"analysis": "analysis", "plan": "plan",
                "publish": "publish", "close": None}.get(act["key"])

    def _render_tab_bar(self, p):
        # ADR-041: the masthead tab bar — one flat button per page.
        # The ACTIVE tab is painted solid in the project's kind accent
        # ("you are here"); the others keep the quiet state vocabulary
        # (filled done, outlined current, dimmed skipped, plain
        # pending). They say WHERE your steps are, not a to-do list.
        # The follow-up tab is hidden for the kinds that have no
        # multi-night journal.
        # @args: p - the project dict
        # @return: None
        w = self.projects
        cur = project.current_step(db, p["id"]) \
            if p["status"] == project.STATUS_ACTIVE else None
        steps = {s["step"]: s["status"] for s in p.get("steps", [])}
        color = theme.KIND_COLORS.get(p.get("kind"), theme.C_ACCENT)
        active = getattr(self, "_active_tab", None)
        for key in _TAB_KEYS:
            btn = getattr(w, f"btn_tab_{key}")
            if key in _STEP_KEYS:
                st = steps.get(key, "pending")
                state = "current" if cur == key else st
                if state not in ("current", "done", "skipped"):
                    state = "pending"
            else:
                state = "pending"
            label = self._tab_label(key)
            btn.setText(label)
            btn.setToolTip(self.tr("Open the {l} tab").replace(
                "{l}", label))
            btn.setChecked(active == key)
            btn.setStyleSheet(theme.tab_state_style(state, color,
                                                    active == key))

    def _refresh_next_card(self, p):
        # Fills the Next card from next_action() (UX-i): one bold line
        # saying what to do, and the Go button opening the right tab.
        # The per-step state lives in the masthead tab bar.
        # @args: p - the project dict
        # @return: None
        act = project.next_action(db, p)
        self.projects.lbl_next.setText("▶ " + self._next_action_text(act))
        self._render_tab_bar(p)
        target = self._next_target_key(p)
        self._next_target = target
        self.projects.btn_next_go.setVisible(target is not None)
        # UX-PC (U3): "Mark done" applies to the current step only.
        # ADR-045: the cadence call shares the "analysis" key with the
        # step, but it is not step bookkeeping — when the action carries
        # the cadence payload there is nothing to mark.
        step_key = act["key"] if act["key"] in _STEP_KEYS else None
        if act.get("overdue_days") is not None or act.get("never_visited"):
            step_key = None
        self._next_step_key = step_key
        self.projects.btn_next_done.setVisible(step_key is not None)

    def _next_done(self):
        # The Next card's "✔ Mark done" (UX-PC U3): acts on the step the
        # card is currently pointing at.
        if self._current_project and self._next_step_key:
            self._step_done(self._next_step_key)



    def _scroll_to_section(self, key):
        # Deep link (Next card Go, dashboard, the ⋯ menu, cadence
        # chips, double-click): land on the part of the project the
        # caller asked for. With the tab bar (ADR-041) that means
        # activating the tab; "files" is the nested list inside the
        # object card.
        # @args: key - section key, e.g. "analysis"|"plan"|"files"|None
        # @return: None
        if not key:
            return
        self._show_tab("details" if key == "files" else key)

    def _show_tab(self, key):
        # ADR-041: activate one tab page — built on first open (lazy),
        # the other pages of this project get hidden, and the bar is
        # repainted so the active tab reads "you are here". ADR-045: the
        # retired "process"/"followup" keys alias to "analysis" forever,
        # so every old deep link keeps landing.
        # @args: key - tab key ("details"|"plan"|"analysis"|"publish")
        # @return: None (a no-op when the page cannot exist here)
        if key is None or self._current_project is None:
            return
        key = {"process": "analysis", "followup": "analysis"}.get(key, key)
        self._ensure_tab_built(key)
        if key not in self._tab_pages:
            return
        self._active_tab = key
        for k, page in self._tab_pages.items():
            page.setVisible(k == key)
        # each tab page is its own world: land at the top of the page
        self.projects.scroll_page.verticalScrollBar().setValue(0)
        self._render_tab_bar(self._current_project)

    def _ensure_tab_built(self, key):
        # ADR-041: the lazy build — tab pages are created on FIRST open
        # and kept in _tab_pages until the project changes (the clear
        # wipes them). Object card is already eager: it exists by the
        # time anything calls this.
        # @args: key - the tab key
        # @return: None
        if key in self._tab_pages or self._current_project is None:
            return
        p = self._current_project
        kind, ctx = p["kind"], p["context"]
        if key in _STEP_KEYS:
            builders = {
                "plan": self._build_plan_tab,
                "analysis": self._build_analysis_tab,
                "publish": self._build_publish_tab,
            }
            builders[key](p, kind, ctx)
            # UX-PC (U3): the discreet step footer (state words + reopen
            # on finished steps) goes at the END of the step page, after
            # content
            self._tab_pages[key].layout().addLayout(
                self._step_footer(p, key))

    def _build_project_page(self, p):
        # The project detail (ADR-041): the object card, the steps and
        # follow-up are TAB PAGES under one scroll — one visible at a
        # time (the tab bar in the masthead decides). The object card
        # is the light page, so it builds eagerly; the step pages build
        # lazily on first open and are cached in _tab_pages. The Next
        # card still decides where you land.
        self._clear_project_page()
        kind, ctx = p["kind"], p["context"]
        # page 0: the object card + project files (not a step)
        det = self._section_layout("details", self._tab_label("details"))
        panel = self._get_proj_panel()
        det.addWidget(panel)
        self._populate_project_files(p["id"])
        # the Next card fills itself AND tells us which page starts
        # active (a finished project — no target — lands on the object
        # card); the other pages build on first click
        self._refresh_next_card(p)
        self._show_tab(self._next_target or "details")

    def _step_section(self, key):
        # Builds one tab page with its state chip in the header
        # (ADR-041). UX-PC (U3) still holds: the state ACTIONS live on
        # the Next card; the page carries only the discreet footer
        # (_step_footer).
        # @args: key - "plan"|"process"|"publish"|"followup"
        # @return: the page's content layout
        layout = self._section_layout(key, self._tab_label(key))
        p = self._current_project
        if p and key in _STEP_KEYS:
            # step state as a chip in the page header ("done <date>" /
            # "skipped" / "pending"). Real step pages only — follow-up
            # has no step row and its chip stays hidden.
            self._set_tab_badge(key, self._step_chip_text(p, key))
        return layout

    def _tab_label(self, key):
        # @args: key - tab key
        # @return: the visible tab text. All five pages share the fixed
        #          label pairs (_STEP_LABELS_ES/EN): Ficha/Captura/
        #          Procesado/Publicar/Seguimiento
        return self._step_label(key)

    def _set_tab_badge(self, key, text):
        # @args: key - tab key, text - chip text ("" keeps it hidden)
        # @return: None
        page = self._tab_pages.get(key)
        if page is None:
            return
        page._chip.setText(text or "")
        page._chip.setVisible(bool(text))

    def _step_chip_text(self, p, key):
        # @args: p - the project dict, key - step key
        # @return: the chip text on the section header. Same words as
        #          the toggle row, minus the icon: "done <date>" when
        #          the step is done, "skipped" or "pending" (a "current"
        #          step reads as pending to its owner).
        step = next((s for s in p.get("steps", []) if s["step"] == key),
                    None)
        if not step or step["status"] not in ("done", "skipped"):
            return self.tr("pending")
        if step["status"] == "skipped":
            return self.tr("skipped")
        when = (datetime.datetime.fromtimestamp(step["updated"])
                .strftime("%Y-%m-%d") if step.get("updated") else "")
        return self.tr("done %1").replace("%1", when)

    def _step_footer(self, p, key):
        # The step state in words, at the FOOT of its section (UX-PC U3):
        # discreet, out of the way of the content. Done/skipped steps
        # offer "Reopen step" (skipping a step interactively went out:
        # it had no real purpose, so a "skipped" row now only ever
        # comes from old databases); a pending step carries no footer
        # action (Mark done for the CURRENT step lives on the Next card).
        # @args: p - the project dict, key - step key ("plan"|...)
        # @return: the QHBox row appended at the end of the step section
        row = QHBoxLayout()
        step = next((s for s in p["steps"] if s["step"] == key), None)
        status = step["status"] if step else "pending"
        row.addStretch()
        if status in ("done", "skipped"):
            when = datetime.datetime.fromtimestamp(
                step["updated"]).strftime("%Y-%m-%d") \
                if step and step.get("updated") else ""
            lbl = QLabel(
                self.tr("✔ done on %1").replace("%1", when)
                if status == "done" else self.tr("– skipped"))
            lbl.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
            row.addWidget(lbl)
            btn_reopen = QPushButton(self.tr("Reopen step"))
            btn_reopen.setFlat(True)
            btn_reopen.setCursor(Qt.PointingHandCursor)
            btn_reopen.clicked.connect(
                lambda _=False, k=key: self._step_reopen(k))
            row.addWidget(btn_reopen)
        return row

    def _step_done(self, key):
        # Marks the step done and rebuilds (advance() keeps the
        # single-current invariant); the close prompt at the last
        # step survives from the old wizard.
        # @args: key - step key
        # @return: None
        p = self._current_project
        if not p:
            return
        cur = project.current_step(db, p["id"])
        if cur != key:
            project.set_step_status(db, p["id"], key,
                                    project.STEP_CURRENT)
        project.advance(db, p["id"])
        p = project.get(db, p["id"])
        self._current_project = p
        self.on_refresh_projects()
        self._build_project_page(p)
        self._render_project_header(p)
        if p["status"] != project.STATUS_ACTIVE:
            ans = QMessageBox.question(
                self, self.tr("Close project"),
                self.tr("All steps are done. Close this project?"))
            if ans == QMessageBox.Yes:
                self._project_close()

    def _step_reopen(self, key):
        # Reopens a done/skipped step (moves it back to current) + rebuild.
        # @args: key - step key
        # @return: None
        project.reopen_step(db, self._current_project["id"], key)
        p = project.get(db, self._current_project["id"])
        self._current_project = p
        self._build_project_page(p)

    def _build_plan_tab(self, p, kind, ctx):
        # Plan & Captura (ADR-030): the session plan (frames/exposure/filter),
        # the calibration frames, the CCDciel/NINA/CSV export and the NEO
        # ephemeris export all live in this single step.
        layout = self._step_section("plan")
        # common: capture plan inputs
        layout.addWidget(QLabel(self.tr("Capture plan")))
        form = QFrame()
        form_layout = QVBoxLayout(form)
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Frames:")))
        spn = PassiveSpinBox(); spn.setMinimum(1); spn.setMaximum(999); spn.setValue(30)
        row.addWidget(spn)
        row.addWidget(QLabel(self.tr("Exposure (s):")))
        spn_exp = PassiveDoubleSpinBox(); spn_exp.setMinimum(0.1)
        spn_exp.setMaximum(3600.0); spn_exp.setValue(60.0)
        row.addWidget(spn_exp)
        row.addWidget(QLabel(self.tr("Filter:")))
        cmb_f = QComboBox()
        for f in ("L", "R", "G", "B", "Ha", "OIII", "SII"):
            cmb_f.addItem(f)
        row.addWidget(cmb_f)
        form_layout.addLayout(row)
        layout.addWidget(form)
        # NEO: exposure calculator
        if kind in ("neo", "pccp") and ctx.get("rate_arcsec_min"):
            from ..core import exposure
            scale = exposure.plate_scale(config.get("pixel_um"),
                                          config.get("focal_mm"))
            t_max = exposure.max_exposure_no_trail(ctx["rate_arcsec_min"], scale)
            if t_max:
                layout.addWidget(QLabel(
                    f"<small>{self.tr('Max exposure (no trail)')}: "
                    f"{t_max:.0f}s · {self.tr('plate scale')}: "
                    f"{scale:.2f}″/px · {self.tr('rate')}: "
                    f"{ctx['rate_arcsec_min']:.1f}″/min</small>"))
                spn_exp.setValue(min(t_max, 60.0))
        # Track D: first-timer transit block (timeline, times, exposure,
        # cadence, pre-flight checklist). Placed before the plan restore so
        # a saved plan still overrides the heuristic exposure.
        if kind == "transit" and (ctx.get("transit") or {}):
            self._build_transit_block(layout, p, ctx, spn_exp)
        # HADS: the 2P continuous-capture block (no event, no timeline)
        if kind == "hads" and (ctx.get("hads") or {}):
            self._build_hads_block(layout, p, ctx, spn_exp, spn)
        # Track V: variable/campaign block (protocol, extremum, exposure)
        if kind == "variable":
            self._build_variable_block(layout, p, ctx, spn_exp)
        # restore saved plan data
        plan_data = next((s["data"] for s in p["steps"]
                          if s["step"] == "plan"), {})
        if plan_data.get("n_frames"):
            spn.setValue(int(plan_data["n_frames"]))
        if plan_data.get("exp_s"):
            spn_exp.setValue(float(plan_data["exp_s"]))
        if plan_data.get("filter"):
            idx = cmb_f.findText(plan_data["filter"])
            if idx >= 0:
                cmb_f.setCurrentIndex(idx)
        self._project_widgets["spn_nframes"] = spn
        self._project_widgets["spn_exps"] = spn_exp
        self._project_widgets["cmb_filter"] = cmb_f
        # CCDciel calibration frames (ADR-021): the generated target list
        # appends a Dark and a Bias step from these counts (0 = omit).
        # UX-PC (U3): secondary to the plan itself — lives collapsed.
        cal = self._advanced_block(layout, self.tr("Calibration"))
        cal_form = QFormLayout()
        cal.addLayout(cal_form)
        spn_darks = PassiveSpinBox(); spn_darks.setMinimum(0); spn_darks.setMaximum(999)
        spn_darks.setValue(25)
        cal_form.addRow(self.tr("Darks:"), spn_darks)
        spn_darkexp = PassiveDoubleSpinBox(); spn_darkexp.setMinimum(0.1)
        spn_darkexp.setMaximum(3600.0)
        spn_darkexp.setValue(spn_exp.value())
        cal_form.addRow(self.tr("Dark exposure (s):"), spn_darkexp)
        spn_bias = PassiveSpinBox(); spn_bias.setMinimum(0); spn_bias.setMaximum(999)
        spn_bias.setValue(100)
        cal_form.addRow(self.tr("Bias:"), spn_bias)
        if plan_data.get("n_darks") is not None:
            spn_darks.setValue(int(plan_data["n_darks"]))
        if plan_data.get("exp_dark"):
            spn_darkexp.setValue(float(plan_data["exp_dark"]))
        if plan_data.get("n_bias") is not None:
            spn_bias.setValue(int(plan_data["n_bias"]))
        self._project_widgets["spn_darks"] = spn_darks
        self._project_widgets["spn_darkexp"] = spn_darkexp
        self._project_widgets["spn_bias"] = spn_bias
        # B8/Track V: SN and variable exposure hint
        # by brightness + multi-filter step rows
        if kind in ("sn", "variable") and ctx.get("mag") is not None:
            from ..core import exposure
            sn_exp = exposure.recommended_sn_exposure(ctx["mag"])
            if sn_exp:
                layout.addWidget(QLabel(
                    f"<small>{self.tr('Recommended exposure')}: "
                    f"{sn_exp}s · {self.tr('mag')} {ctx['mag']:.1f}"
                    f" · {self.tr('guide, not SNR — confirm with a test shot')}"
                    f"</small>"))
                spn_exp.setValue(min(sn_exp, 60.0))
            # multi-filter rows: add/remove (filter × N × exp) steps.
            # The "Add filter" button shares the header row (right side),
            # so we save one full row for the button alone
            filt_head = QHBoxLayout()
            filt_head.addWidget(QLabel(self.tr("Filters (add rows for multi-band)")))
            filt_head.addStretch()
            btn_add_filt = QPushButton(self.tr("Add filter"))
            btn_add_filt.clicked.connect(lambda: self._sn_add_step_row(steps_vlay))
            filt_head.addWidget(btn_add_filt)
            layout.addLayout(filt_head)
            steps_container = QWidget()
            steps_vlay = QVBoxLayout(steps_container)
            steps_vlay.setContentsMargins(2, 2, 2, 2)
            self._sn_steps = []
            default_filters = ("Clear",)
            if kind == "variable" and p.get("campaign_id"):
                from ..core import campaign as _camp
                camp = _camp.get(db, p["campaign_id"])
                prot_filters = ((camp or {}).get("protocol") or {}).get(
                    "filters") or []
                if prot_filters:
                    default_filters = tuple(prot_filters)
            for filt in default_filters:
                self._sn_add_step_row(steps_vlay, filt, 30, spn_exp.value())
            layout.addWidget(steps_container)
            self._project_widgets["sn_steps_container"] = steps_container
        # sequence export (all kinds): the format combo and the
        # right-aligned "Export sequence…" button share one row
        seq_row = QHBoxLayout()
        seq_row.addWidget(QLabel(self.tr("Export format")))
        cmb_fmt = QComboBox()
        cmb_fmt.addItem(self.tr("CCDciel (targets)"))
        cmb_fmt.addItem(self.tr("NINA (JSON)"))
        cmb_fmt.addItem(self.tr("CSV (generic)"))
        seq_row.addWidget(cmb_fmt)
        seq_row.addStretch()
        btn_seq = QPushButton(self.tr("Export sequence…"))
        btn_seq.clicked.connect(self._project_export_sequence)
        seq_row.addWidget(btn_seq)
        layout.addLayout(seq_row)
        # NEO: also ephemeris export
        if kind in ("neo", "pccp"):
            layout.addWidget(QLabel(""))
            layout.addWidget(QLabel(self.tr("Export ephemeris for planetarium")))
            btn_eph = QPushButton(self.tr("Export ephemeris…"))
            btn_eph.clicked.connect(self._project_export_ephem)
            layout.addWidget(btn_eph)
        self._project_widgets["cmb_seqfmt"] = cmb_fmt
        # ADR-043: the live CCDciel control lives in the Capture step
        # itself (the Observatory tab is gone): the hardware has one home,
        # and it is the step that plans its capture
        self._build_capture_ccd_block(layout)
        # ADR-043: the plan auto-saves: every input writes the same payload
        # the "Save plan" button used to, silently (the project bar is the
        # visible truth). The connects sit after every build-time
        # setValue()/setCurrentIndex() above, so the signals only fire on
        # real user interaction.
        spn.valueChanged.connect(self._project_save_plan)
        spn_exp.valueChanged.connect(self._project_save_plan)
        cmb_f.currentIndexChanged.connect(self._project_save_plan)
        spn_darks.valueChanged.connect(self._project_save_plan)
        spn_darkexp.valueChanged.connect(self._project_save_plan)
        spn_bias.valueChanged.connect(self._project_save_plan)
        layout.addStretch()

    def _project_save_plan(self):
        if not self._current_project:
            return
        spn = self._project_widgets.get("spn_nframes")
        spn_exp = self._project_widgets.get("spn_exps")
        cmb_f = self._project_widgets.get("cmb_filter")
        spn_darks = self._project_widgets.get("spn_darks")
        spn_darkexp = self._project_widgets.get("spn_darkexp")
        spn_bias = self._project_widgets.get("spn_bias")
        if spn and spn_exp and cmb_f:
            n_darks = spn_darks.value() if spn_darks else 0
            exp_dark = spn_darkexp.value() if (spn_darkexp and n_darks) else None
            n_bias = spn_bias.value() if spn_bias else 0
            project.update_step_data(
                db, self._current_project["id"], "plan",
                {"n_frames": spn.value(), "exp_s": spn_exp.value(),
                 "filter": cmb_f.currentText(), "n_darks": n_darks,
                 "exp_dark": exp_dark, "n_bias": n_bias})
            # (re)compute the safe window from this plan's duration (including
            # calibration frames) and store it in the project context so the
            # overview, narrative and sky chart all agree (ADR-020).
            p = self._current_project
            ctx = p.get("context") or {}
            ra = ctx.get("ra_deg")
            dec = ctx.get("dec_deg")
            if ra is not None and dec is not None:
                plan = sequence.make_plan(
                    spn.value(), spn_exp.value(), cmb_f.currentText(),
                    overhead_s=float(config.get("overhead_s", 15.0)),
                    n_darks=n_darks, exp_dark=exp_dark, n_bias=n_bias)
                dur = plan["duration_s"]
                from ..core import planner as _planner
                sw = _planner.safe_window_for(ra, dec, config, dur)
                ctx.update(sw)
                project.update_context(db, p["id"],
                                       {k: v for k, v in sw.items()
                                        if v is not None})
                # refresh the overview panel: the capture chips and the
                # sky chart now carry the safe window
                panel = self._get_proj_panel()
                if panel._e is not None:
                    panel._ctx = ctx
                    panel._render_capture(panel._e)
                    panel._render_charts(panel._e)
            # ADR-043: silent by design: the plan auto-saves from the
            # Capture step inputs; the project bar is the visible truth

    # -- CCDciel control (ADR-030) -----------------------------------------

    def _build_capture_ccd_block(self, layout):
        # ADR-043: the Observatory tab is gone; this is its whole control
        # panel, rebuilt per project page inside the Capture step. Built
        # in code (not a .ui) because it is small and per-project now;
        # the tr() sources keep the old ObservatoryTab strings as
        # anchors for the existing translations. The block always works
        # on the CURRENT project: listing projects inside the observatory
        # had no purpose, so there is no target-selection combo (a
        # project that is not open is not what you are looking at that
        # night).
        grp = QGroupBox(self.tr("CCDciel control"))
        gv = QVBoxLayout(grp)
        gv.setContentsMargins(12, 9, 12, 9)
        row = QHBoxLayout()
        btn_c = QPushButton(self.tr("Connect CCDciel"))
        btn_d = QPushButton(self.tr("Disconnect"))
        btn_r = QPushButton(self.tr("Refresh"))
        lbl_s = QLabel(self.tr("CCDciel: not connected"))
        row.addWidget(btn_c)
        row.addWidget(btn_d)
        row.addWidget(btn_r)
        row.addWidget(lbl_s)
        row.addStretch()
        gv.addLayout(row)
        layout.addWidget(grp)

        grp = QGroupBox(self.tr("Observatory status"))
        form = QFormLayout(grp)
        lbl_v = QLabel("—")
        lbl_t = QLabel("—")
        lbl_tr = QLabel("—")
        lbl_sl = QLabel("—")
        form.addRow(self.tr("Version:"), lbl_v)
        form.addRow(self.tr("CCD temperature:"), lbl_t)
        form.addRow(self.tr("Tracking:"), lbl_tr)
        form.addRow(self.tr("Slew:"), lbl_sl)
        layout.addWidget(grp)

        grp = QGroupBox(self.tr("Telescope"))
        gv = QVBoxLayout(grp)
        gv.setContentsMargins(12, 9, 12, 9)
        row = QHBoxLayout()
        btn_goto = QPushButton(self.tr("Point telescope"))
        btn_goto.setToolTip(self.tr(
            "Quick slew to the freshly-computed position of a moving "
            "target: J2000_to_Apparent + Telescope_slewasync, no "
            "plate-solve. Fast, but assumes the ephemeris is already "
            "accurate."))
        btn_sync = QPushButton(self.tr("Astrometric Goto"))
        btn_sync.setToolTip(self.tr(
            "Slew + capture + plate-solve and correct to the true sky "
            "position. Absorbs residual ephemeris error; the reliable "
            "route for NEOCPs and preliminary orbits."))
        row.addWidget(btn_goto)
        row.addWidget(btn_sync)
        row.addStretch()
        gv.addLayout(row)
        layout.addWidget(grp)

        grp = QGroupBox(self.tr("Live capture"))
        gv = QVBoxLayout(grp)
        gv.setContentsMargins(12, 9, 12, 9)
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Filter on wheel:")))
        cmb_f = QComboBox()
        btn_push = QPushButton(self.tr("Send plan"))
        btn_push.setToolTip(self.tr(
            "Stage the current project's saved plan (frames × exposure) "
            "in CCDciel's Capture module"))
        btn_start = QPushButton(self.tr("Start capture"))
        btn_start.setToolTip(self.tr("Start the staged capture in CCDciel"))
        row.addWidget(cmb_f)
        row.addWidget(btn_push)
        row.addWidget(btn_start)
        row.addStretch()
        gv.addLayout(row)
        lbl_co = QLabel("—")
        lbl_co.setWordWrap(True)
        gv.addWidget(lbl_co)
        lbl_h = QLabel(self.tr(
            "Uses the current project's saved plan (its Capture step "
            "holds frames × exposure)."))
        lbl_h.setWordWrap(True)
        lbl_h.setStyleSheet("color: #8a90a6; font-size: 11px;")
        gv.addWidget(lbl_h)
        layout.addWidget(grp)

        self._obs_widgets = {
            "ccd_connect": btn_c,
            "ccd_disconnect": btn_d,
            "ccd_refresh": btn_r,
            "ccd_status": lbl_s,
            "ccd_version": lbl_v,
            "ccd_temp": lbl_t,
            "ccd_tracking": lbl_tr,
            "ccd_slew": lbl_sl,
            "ccd_goto": btn_goto,
            "ccd_sync": btn_sync,
            "cmb_ccd_filter": cmb_f,
            "ccd_push": btn_push,
            "ccd_start": btn_start,
            "ccd_coords": lbl_co,
        }
        btn_c.clicked.connect(self._ccd_connect)
        btn_d.clicked.connect(self._ccd_disconnect)
        btn_r.clicked.connect(self._ccd_refresh)
        btn_goto.clicked.connect(self._ccd_goto)
        btn_sync.clicked.connect(self._ccd_astrometry_goto)
        btn_push.clicked.connect(self._ccd_send_plan)
        btn_start.clicked.connect(self._ccd_start_capture)
        self._ccd_apply_state()
        # the wheel combo starts on the static fallback list (a real wheel
        # replaces it on connect via _ccd_fill_filters)
        self._ccd_fill_filters()

    def _ccd_widgets(self):
        # @return: the CCDciel widget registry of the open Capture step
        #          (ADR-043: the block lives inside the project page, so
        #          it is empty until a plan tab has been built — every
        #          consumer guard-checks its keys against that).
        return dict(getattr(self, "_obs_widgets", {}) or {})

    def _ccd_apply_state(self):
        # Enable/disable the CCDciel widgets after a connection change and
        # refresh the status line. Safe to call even before the widgets exist.
        w = self._ccd_widgets()
        if not w.get("ccd_connect"):
            return
        on = self._ccd_connected
        for key in ("ccd_disconnect", "ccd_refresh", "ccd_push",
                    "ccd_start", "ccd_goto", "ccd_sync"):
            widget = w.get(key)
            if widget is not None:
                widget.setEnabled(on)
        cb = w.get("cmb_ccd_filter")
        if cb is not None:
            cb.setEnabled(on)
        w["ccd_connect"].setEnabled(not on)
        if not on:
            w["ccd_status"].setText(self.tr("CCDciel: not connected"))
            w["ccd_version"].setText(self.tr("—"))
            w["ccd_temp"].setText(self.tr("—"))
            w["ccd_tracking"].setText(self.tr("—"))
            w["ccd_slew"].setText(self.tr("—"))
        else:
            w["ccd_status"].setText(
                f"{self.tr('CCDciel')}: {self._ccd_client.host}:"
                f"{self._ccd_client.port} · {self._ccd_version}")
            self._ccd_fill_filters()

    def _ccd_connect(self):
        # Manual connect button (ADR-030): build a client from config and let
        # a worker prove it answers JSON-RPC 2.0 on the background thread.
        if (self._ccd_worker is not None and self._ccd_worker.isRunning()):
            return
        from ..core.sources import ccdciel
        self._ccd_client = ccdciel.Client(
            host=str(config.get("ccdciel_host", "127.0.0.1")),
            port=int(config.get("ccdciel_port", 3277)))
        self._ccd_version = self.tr("—")

        def action(c):
            version = c.ping()
            if version is None:
                raise ccdciel.CCDcielError("no JSON-RPC answer")
            return {"version": version, "dashboard": c.dashboard(),
                    "filters": c.filters()}

        self._ccd_worker = CcdcielWorker(self._ccd_client, action)
        self._ccd_worker.finished.connect(self._ccd_on_connect)
        self._ccd_worker.start()

    def _ccd_on_connect(self, result, error):
        # @args: result - dict with version/dashboard/filters, error - message
        self._ccd_worker = None
        if error or not result:
            QMessageBox.warning(self, self.tr("CCDciel"),
                                self.tr("Could not connect to CCDciel.")
                                + f"\n{error}")
            self._ccd_connected = False
            self._ccd_apply_state()
            return
        self._ccd_connected = True
        self._ccd_version = str(result.get("version", self.tr("—")))
        w = self._ccd_widgets()
        if w.get("ccd_version"):
            w["ccd_version"].setText(self._ccd_version)
        self._ccd_filter_names = list(result.get("filters") or [])
        self._ccd_timer.start()
        self._ccd_render_dashboard(result.get("dashboard") or {})
        self._ccd_apply_state()
        self.statusBar().showMessage(
            f"{self.tr('CCDciel connected')} · {self._ccd_version}", 5000)

    def _ccd_disconnect(self):
        self._ccd_connected = False
        self._ccd_timer.stop()
        self._ccd_filter_names = []
        self._ccd_version = self.tr("—")
        self._ccd_apply_state()

    def _ccd_run(self, slot, action, poll=False):
        # One worker at a time keeps slew/capture/filter commands ordered.
        # @args: slot - slot(result, error), action - callable(Client),
        #        poll - wait for Telescope_slewing to settle before emitting
        if (self._ccd_worker is not None and self._ccd_worker.isRunning()):
            return
        self._ccd_worker = CcdcielWorker(self._ccd_client, action,
                                         poll_slew=poll)
        self._ccd_worker.finished.connect(slot)
        self._ccd_worker.start()

    def _ccd_refresh(self):
        # @return: re-fetches the dashboard plus a live mount snapshot
        # (slewing/tracking) on the worker thread — reads never block the UI.
        def action(c):
            from ..core.sources import ccdciel
            payload = {"dashboard": c.dashboard()}
            try:
                payload["slewing"] = c.slewing()
                payload["tracking"] = c.tracking()
            except ccdciel.CCDcielError:
                # mount state is optional in the dashboard; keep the rest
                pass
            return payload
        self._ccd_run(self._ccd_on_refreshed, action)

    def _ccd_on_refreshed(self, result, error):
        self._ccd_worker = None
        if error:
            self.statusBar().showMessage(error, 5000)
            return
        result = result or {}
        self._ccd_render_dashboard(result.get("dashboard") or {},
                                   result.get("slewing"),
                                   result.get("tracking"))

    def _ccd_render_dashboard(self, dash, slewing=None, tracking=None):
        # @args: dash - sections dict from the "status" method,
        #        slewing/tracking - live mount state (may override the
        #                          dashboard when the server hides them there)
        w = self._ccd_widgets()
        if not w.get("ccd_temp"):
            return
        cam = dash.get("camera") or {}
        temp = cam.get("temperature")
        if temp is None and cam:
            for key in ("ccd_temp", "temp", "temperature_C"):
                if isinstance(cam.get(key), (int, float)):
                    temp = cam[key]
                    break
        w["ccd_temp"].setText(f"{temp} °C" if temp is not None else self.tr("—"))
        mount = dash.get("mount") or {}
        if tracking is None:
            tracking = mount.get("tracking")
        if tracking is None and "tracking" in cam:
            tracking = cam["tracking"]
        if isinstance(tracking, str):
            tracking = tracking.strip().lower() not in ("", "false", "no", "0")
        if tracking is None:
            w["ccd_tracking"].setText(self.tr("—"))
        elif tracking:
            w["ccd_tracking"].setText(self.tr("Tracking"))
        else:
            w["ccd_tracking"].setText(self.tr("Stopped"))
        if slewing is None:
            slewing = mount.get("slewing")
        if slewing is None and "slewing" in cam:
            slewing = cam["slewing"]
        if isinstance(slewing, str):
            slewing = slewing.strip().lower() not in ("", "false", "no", "0")
        if slewing is None:
            w["ccd_slew"].setText(self.tr("—"))
        elif slewing:
            w["ccd_slew"].setText(self.tr("Slewing…"))
        else:
            w["ccd_slew"].setText(self.tr("Idle"))

    def _ccd_poll_tick(self):
        # QTimer tick while connected: the read runs on the CCD worker
        # thread (ADR-030: no network on the GUI thread); the cache keeps it
        # cheap once the dashboard is warm. _ccd_run itself refuses to queue a
        # second worker, so a busy refresh is simply skipped.
        if not self._ccd_connected:
            return
        if not self._ccd_widgets().get("ccd_temp"):
            return
        self._ccd_refresh()

    def _ccd_fill_filters(self):
        # @return: fills the wheel combo from CCDciel (fallback labels when
        #          the wheel is disconnected or slots are unnamed)
        w = self._ccd_widgets()
        cmb = w.get("cmb_ccd_filter")
        if not cmb:
            return
        names = self._ccd_filter_names or ["L", "R", "G", "B", "Ha", "OIII",
                                           "SII"]
        before = cmb.currentText()
        cmb.blockSignals(True)
        cmb.clear()
        for name in names:
            if name and name not in ("", "-", "None"):
                cmb.addItem(name)
        if cmb.count() == 0:
            cmb.addItem(self.tr("No filter"))
        idx = cmb.findText(before)
        if idx >= 0:
            cmb.setCurrentIndex(idx)
        cmb.blockSignals(False)

    def _ccd_coords_text(self, ctx, kind):
        # @args: ctx - project context, kind - project kind
        # @return: label describing the freshness of the pointing coords:
        #          moving kinds show the epoch of the last fresh computation
        #          (or "from the plan" when never refreshed); fixed kinds
        #          just say so.
        ra, dec = ctx.get("ra_deg"), ctx.get("dec_deg")
        if ra is None:
            return self.tr("This object has no coordinates yet.")
        if kind in ("neo", "comet", "pccp"):
            epoch = ctx.get("coords_epoch")
            if epoch:
                return self.tr("Position at %1 UT").replace("%1", epoch)
            return self.tr("Position from the plan (not refreshed)")
        return self.tr("Fixed coordinates")

    def _ccd_update_coords_label(self):
        # Refreshes the coords/epoch label (ADR-043: it lives in the
        # Capture step now and follows the current project).
        p = self._current_project
        lbl = self._ccd_widgets().get("ccd_coords")
        if not p or not lbl:
            return
        lbl.setText(self._ccd_coords_text(p.get("context") or {},
                                          p.get("kind")))

    def _ccd_point_action(self, slew_fn, ctx):
        # Builds a CcdcielWorker action that resolves a fresh position for
        # moving kinds (neo/comet/pccp) right before slewing, so the mount
        # never points at a stale snapshot. Fixed kinds (sn/transit) use the
        # stored coordinates. The action returns the position dict so the
        # slot can update the project context and the freshness label.
        # @args: slew_fn - c.slew_target or c.astrometry_goto,
        #        ctx - project context dict
        # @return: callable(Client) -> position dict
        # kind/object may come via ctx (the project page context);
        # otherwise fall back to the project open in the hub
        p = self._current_project or {}
        kind = ctx.get("kind") or p.get("kind")
        obj_id = (ctx.get("id") or ctx.get("packed")
                  or p.get("object_name") or ctx.get("object_name"))
        site = config.get("mpc_code", "")
        if kind in ("neo", "comet", "pccp"):
            def action(c):
                pos = ephemeris.position_at(obj_id, site,
                                            fallback_target=ctx)
                if pos is None:
                    pos = {"ra_deg": ctx["ra_deg"], "dec_deg": ctx["dec_deg"],
                           "epoch_iso": None, "source": "snapshot",
                           "preliminary": False, "fell_back": True,
                           "rate_arcsec_min": ctx.get("rate_arcsec_min")}
                slew_fn(c, pos["ra_deg"], pos["dec_deg"])
                return pos
            return action
        ra, dec = ctx["ra_deg"], ctx["dec_deg"]

        def fixed(c):
            slew_fn(c, ra, dec)
            return {"ra_deg": ra, "dec_deg": dec, "source": "snapshot",
                    "preliminary": False, "epoch_iso": None}
        return fixed

    def _ccd_apply_position(self, pos):
        # Folds a fresh position into the project context and refreshes the
        # coords/epoch label. The context is the single source the overview,
        # sky chart and re-pointing all read.
        # @args: pos - dict from position_at / the worker action
        # the project the last goto/astrometry aimed at; if none (or a
        # direct call) the project open in the Projects hub
        p = self._ccd_point_target or self._current_project
        self._ccd_point_target = None
        if not pos or not p:
            return
        upd = {"ra_deg": pos["ra_deg"], "dec_deg": pos["dec_deg"]}
        if pos.get("epoch_iso"):
            upd["coords_epoch"] = pos["epoch_iso"]
        if pos.get("rate_arcsec_min") is not None:
            upd["rate_arcsec_min"] = pos["rate_arcsec_min"]
        if pos.get("source"):
            upd["coords_source"] = pos["source"]
        project.update_context(db, p["id"], upd)
        p.setdefault("context", {}).update(upd)
        # ADR-043: the coords label lives in the Capture step and follows
        # the current project — the position belongs to it by definition
        self._ccd_update_coords_label()
        if pos.get("fell_back"):
            self.statusBar().showMessage(
                self.tr("No fresh ephemeris; using the plan coordinates."),
                8000)

    def _ccd_goto(self):
        # Point the mount at the current object. Moving kinds get a fresh
        # position resolved inside the worker (network off the GUI thread);
        # the async slew then waits for Telescope_slewing to settle.
        p = self._current_project
        if not p:
            self.statusBar().showMessage(
                self.tr("Open a project first (the Capture step needs one)"),
                6000)
            return
        ctx = dict(p.get("context") or {})
        ctx["kind"] = p.get("kind")
        ctx["object_name"] = p.get("object_name")
        if ctx.get("ra_deg") is None:
            self.statusBar().showMessage(
                self.tr("This object has no coordinates yet."), 5000)
            return
        w = self._ccd_widgets()
        if not w.get("ccd_goto"):
            return
        w["ccd_slew"].setText(self.tr("Slewing…"))
        w["ccd_goto"].setEnabled(False)
        action = self._ccd_point_action(
            lambda c, ra, dec: c.slew_target(ra, dec), ctx)
        self._ccd_point_target = p
        self._ccd_run(self._ccd_on_goto, action, poll=True)

    def _ccd_on_goto(self, result, error):
        w = self._ccd_widgets()
        if w.get("ccd_goto"):
            w["ccd_goto"].setEnabled(True)
        if w.get("ccd_slew"):
            w["ccd_slew"].setText(
                self.tr("Failed") if error else self.tr("Idle"))
        if error:
            self.statusBar().showMessage(error, 8000)
            return
        self._ccd_apply_position(result)
        self.statusBar().showMessage(
            self.tr("Telescope pointed at the object."), 5000)

    def _ccd_astrometry_goto(self):
        # Astrometric pointing at the current object: CCDciel slews,
        # plate-solves and corrects. Moving kinds resolve a fresh position
        # first (the plate solve absorbs any residual ephemeris error as
        # long as the prediction lands inside the solve field). The client
        # polls the running flag, so no mount-state polling is needed here.
        p = self._current_project
        if not p:
            self.statusBar().showMessage(
                self.tr("Open a project first (the Capture step needs one)"),
                6000)
            return
        ctx = dict(p.get("context") or {})
        ctx["kind"] = p.get("kind")
        ctx["object_name"] = p.get("object_name")
        if ctx.get("ra_deg") is None:
            self.statusBar().showMessage(
                self.tr("This object has no coordinates yet."), 5000)
            return
        action = self._ccd_point_action(
            lambda c, ra, dec: c.astrometry_goto(ra, dec), ctx)
        self._ccd_point_target = p
        self._ccd_run(self._ccd_on_astrometry, action, poll=False)

    def _ccd_on_astrometry(self, result, error):
        # @args: result - position dict the worker resolved (or None),
        #        error - error text
        if error:
            self.statusBar().showMessage(error, 8000)
            return
        self._ccd_apply_position(result)
        self.statusBar().showMessage(
            self.tr("Astrometric pointing finished."), 5000)

    def _ccd_send_plan(self):
        # Stage the planned frames/exposure/filter inside CCDciel
        # (Capture_set*). ADR-043: lives in the Capture step and reads
        # the CURRENT project's SAVED plan (the block is bound to it).
        p = self._current_project
        if not p:
            self.statusBar().showMessage(
                self.tr("Open a project first (the Capture step needs one)"),
                6000)
            return
        # the Capture step auto-saves the plan straight to the db, so
        # re-read it: the in-memory dict is the one from selection time
        p = project.get(db, p["id"]) or p
        plan = next((s["data"] for s in p.get("steps", [])
                     if s["step"] == "plan"), {})
        n_frames, exp_s = plan.get("n_frames"), plan.get("exp_s")
        if not n_frames or not exp_s:
            self.statusBar().showMessage(
                self.tr("Save the plan in the project's Plan section "
                        "first"), 8000)
            return
        cmb = self._ccd_widgets().get("cmb_ccd_filter")
        if not cmb:
            return
        f_idx = cmb.currentIndex()
        # prefer the plan's own filter when the wheel knows the name
        pf = plan.get("filter")
        if pf:
            idx = cmb.findText(pf)
            if idx >= 0:
                cmb.setCurrentIndex(idx)
                f_idx = idx
        name = p["object_name"]

        def action(c):
            c.set_filter(f_idx)
            return c.push_plan(n_frames, exp_s, name)

        self._ccd_run(self._ccd_on_sent, action)

    def _ccd_on_sent(self, _result, error):
        if error:
            self.statusBar().showMessage(error, 8000)
        else:
            self.statusBar().showMessage(
                self.tr("Capture plan sent to CCDciel."), 5000)

    def _ccd_start_capture(self):
        self._ccd_run(self._ccd_on_started, lambda c: c.start_capture())

    def _ccd_on_started(self, _result, error):
        if error:
            self.statusBar().showMessage(error, 8000)
        else:
            self.statusBar().showMessage(
                self.tr("Capture started in CCDciel."), 5000)

    def _build_analysis_tab(self, p, kind, ctx):
        # ADR-045: the Analysis tab. Its core is the visits manager, for
        # EVERY kind: each day you work the object is a visit, and every
        # resource (plates, reports, imports) hangs from one. The per-kind
        # blocks absorbed from the retired Process tab ride below; the
        # retired SN FITS-import/blink block is gone for good: a visit's
        # plate opens in the editor, which owns blink/measure/annotate;
        # and the MPC astrometry block lives inside the visit's window
        # (the report is the visit's product — form A).
        layout = self._step_section("analysis")
        pid = p["id"]
        if kind in FOLLOWUP_KINDS:
            self._fu_header_blocks(layout, p, pid)
        from .widgets.visits_panel import VisitsPanel
        panel = VisitsPanel(
            db, lang=self._lang(),
            open_in_editor=lambda path, sid:
                self._visit_open_in_editor(pid, path, sid),
            # ADR-047: a measurement row is a shortcut to its plate
            on_measure_click=self._visit_open_measure,
            on_change=lambda: self._visit_data_changed(pid),
            kind=kind)
        panel.set_project(pid)
        layout.addWidget(panel, 1)
        self._project_widgets["visits_panel"] = panel
        if kind == "transit":
            self._analysis_transit_block(layout)
        elif kind == "hads":
            self._analysis_hads_block(layout)
        if kind in ("neo", "pccp", "comet"):
            adv = self._advanced_block(
                layout, self.tr("What you kept from the session"))
            self._build_products_block(adv, p)
        if kind in FOLLOWUP_KINDS:
            self._fu_science_blocks(layout, p, ctx, pid)
        layout.addStretch()

    def _selected_visit_id(self):
        # @return: the visits panel's selected visit id, or None
        panel = self._project_widgets.get("visits_panel")
        return panel.current_session_id() if panel is not None else None

    # ------------- the per-kind analysis blocks (ADR-045; absorbed from
    # the retired Process tab; the SN FITS-import/blink block is gone for
    # good: a visit's plate opens in the editor, which owns blink,
    # measure and annotate) -------------

    def _analysis_transit_block(self, layout):
        # Track D (subplan 4d): the reduction is 100% external (EXOTIC,
        # NASA/JPL); NightScribe hands over a pre-filled inits.json and
        # then guides the closing of the scientific loop.
        layout.addWidget(QLabel(self.tr(
            "Reduce the photometry with EXOTIC (NASA/JPL), in your own "
            "Python ≤3.10 environment.")))
        btn_exotic = QPushButton(
            self.tr("Export to EXOTIC (inits.json)…"))
        btn_exotic.setToolTip(self.tr(
            "Pre-filled EXOTIC initialization file: planet, observatory, "
            "camera and filter — EXOTIC skips its wizard where it can"))
        btn_exotic.clicked.connect(self._transit_export_exotic)
        layout.addWidget(btn_exotic)
        lbl_exotic = QLabel(self.tr(
            "After the reduction, upload EXOTIC's output file to "
            "ExoClock (exoclock.space) and/or the AAVSO Exoplanet "
            "Database — and tell the story when you publish."))
        lbl_exotic.setWordWrap(True)
        layout.addWidget(lbl_exotic)

    def _analysis_hads_block(self, layout):
        # ADR-034 (D.3): publication photometry is external — FotoDif
        # (its AUTO mode watches the capture folder live) or AIJ.
        # NightScribe registers the measurements (the visit's
        # measurements block above) and points to the AAVSO submission.
        lbl = QLabel(self.tr(
            "Reduce the series with FotoDif (its AUTO mode follows the "
            "capture live) or AIJ. FotoDif writes the AAVSO Extended "
            "File Format report directly; the cadence and exposure "
            "are in the Capture step."))
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        code = config.get("aavso_code", "")
        if code:
            layout.addWidget(QLabel(
                self.tr("Your AAVSO observer code: %1").replace(
                    "%1", code)))
        else:
            lbl_code = QLabel(self.tr(
                "No AAVSO observer code yet — set it in Settings"))
            lbl_code.setWordWrap(True)
            lbl_code.setStyleSheet("color: #e0c060;")
            layout.addWidget(lbl_code)
        btn_webobs = QPushButton(self.tr("Open AAVSO WebObs…"))
        btn_webobs.setToolTip(self.tr(
            "Submit the FotoDif/AAVSO report to the AAVSO database"))
        btn_webobs.clicked.connect(
            lambda: self._open_url("https://www.aavso.org/webobs/"))
        layout.addWidget(btn_webobs)
        lbl_imp = QLabel(self.tr(
            "Import the FotoDif measurements («JD mag …» text) with "
            "«Import file…» in the photometry tools menu above — the "
            "light curve and the phase-folded view update themselves."))
        lbl_imp.setWordWrap(True)
        layout.addWidget(lbl_imp)

    def _visit_open_in_editor(self, pid, path, sid):
        # A visit's plate opens in the UFE with everything attached: the
        # object context, and both hooks land on THIS visit (ADR-045:
        # nothing attaches without one).
        # @args: pid - project id, path - the FITS to open, sid - visit id
        if not self._use_ufe():
            self.statusBar().showMessage(
                self.tr("Enable the unified editor in Settings → Development "
                        "to measure from the editor"), 8000)
            return
        p = project.get(db, pid)
        if not p:
            return
        obj = self._ufe_object_from_project(p)
        dlg = self._ufe_open("measure", hook_pid=pid, obj=obj,
                             session_id=sid)
        if not dlg.open_plate(path):
            return
        dlg.set_object(obj)
        # ADR-047: the plate's saved working state comes back with it:
        # stretch, the measure recipe, the sequence field, when there
        # is one (nothing was saved, or the plate predates it, and the
        # fresh defaults stand)
        row = project.find_file(db, pid, path)
        if row is not None and (row.get("meta") or {}).get("ufe"):
            dlg.apply_plate_state(row["meta"]["ufe"])

    def _visit_open_measure(self, point_id):
        # ADR-047: a measured point in the visit window is a shortcut
        # to its origin: the editor opens on the plate the point came
        # from, with its saved working state, and the measure tab armed.
        # A point without a plate (hand-entered, pasted, or saved before
        # ADR-047 gets one) gets a plain note, never a blind open.
        # @args: point_id - the photometry_points id
        from ..core import followup as fu
        pt = fu.point_by_id(db, point_id)
        if pt is None:
            self.statusBar().showMessage(
                self.tr("This measurement no longer exists."), 6000)
            return
        if pt.get("file_id") is None:
            self.statusBar().showMessage(
                self.tr("This point has no plate: it was hand-entered, "
                        "pasted, or saved before this feature."), 8000)
            return
        row = project.get_file(db, pt["file_id"])
        if row is None or row.get("kind") != "fits":
            self.statusBar().showMessage(
                self.tr("The plate this point came from is not a usable "
                        "image anymore."), 8000)
            return
        pid = row["project_id"]
        if not self._use_ufe():
            self.statusBar().showMessage(
                self.tr("Enable the unified editor in Settings → Development "
                        "to open this plate"), 8000)
            return
        p = project.get(db, pid)
        if not p:
            return
        obj = self._ufe_object_from_project(p)
        dlg = self._ufe_open("measure", hook_pid=pid, obj=obj,
                             session_id=pt.get("session_id"))
        if not dlg.open_plate(row["path"]):
            return
        dlg.set_object(obj)
        # the same restore as "restore in the editor"
        if (row.get("meta") or {}).get("ufe"):
            dlg.apply_plate_state(row["meta"]["ufe"])

    def _visit_data_changed(self, pid):
        # A visit or its contents changed (the panel owns the edit): the
        # reactive blocks refresh in place — the user's place in the
        # visits list is never lost to a full page rebuild.
        w = self._project_widgets
        p = project.get(db, pid)
        if p is None:
            return
        from ..core import followup as fu
        lbl = w.get("fu_cadence")
        if lbl is not None:
            text, colour = self._fu_cadence_state(p, pid)
            if text is None:
                lbl.setVisible(False)
            else:
                lbl.setText(text)
                if colour:
                    lbl.setStyleSheet(f"color: {colour}; font-size: 13px;")
                lbl.setVisible(True)
        chart = w.get("fu_curve")
        if chart is not None:
            from ..core import lightcurve_data
            pts = fu.list_points(db, pid)
            payload = lightcurve_data.build_payload(
                {"points": pts,
                 "sn_type": (p["context"].get("sn_type"))},
                sn_type_fallback=p["context"].get("sn_type")
                or p["context"].get("otype"),
                variable=p["context"].get("variable"))
            chart.set_data(
                payload["points"], sn_type=payload.get("sn_type"),
                peak_mjd=payload.get("peak_mjd"),
                peak_mag=payload.get("peak_mag"),
                fold_period_d=payload.get("fold_period_d"),
                epoch_mjd=payload.get("epoch_mjd"),
                schematic=payload.get("schematic"))
        camp = w.get("fu_campaign_text")
        if camp is not None:
            camp.setText(self._fu_campaign_text(p, pid))

    def _build_products_block(self, layout, p):
        # C0: "what you kept" block for the NEO/PCCP/comet Process step
        # (lives collapsed since UX-PC U3). Registration goes to
        # project_files (visible in Details, A4) and a summary with the
        # FITS metadata is persisted in the process step data. The MPC
        # report needs no button: it is registered on save.
        # @args: layout - the host layout, p - project dict
        gl = layout
        hint = QLabel(self.tr(
            "Register what you keep from the session: the FITS frames and "
            "the annotated images (e.g. from Tycho). The MPC report is "
            "registered automatically when you save it."))
        hint.setWordWrap(True)
        gl.addWidget(hint)
        row = QHBoxLayout()
        btn_fits = QPushButton(self.tr("Register FITS…"))
        btn_fits.setToolTip(self.tr(
            "One or more FITS from the session — date, filter and exposure "
            "are read from each header"))
        btn_fits.clicked.connect(self._neo_register_fits)
        row.addWidget(btn_fits)
        btn_img = QPushButton(self.tr("Register annotated image…"))
        btn_img.setToolTip(self.tr(
            "Annotated image with the object marked (e.g. Tycho-Tracker "
            "output)"))
        btn_img.clicked.connect(self._neo_register_image)
        row.addWidget(btn_img)
        gl.addLayout(row)
        # C1: motion animation (the fire test) built from the registered FITS
        row2 = QHBoxLayout()
        btn_anim = QPushButton(self.tr("Motion animation"))
        btn_anim.setToolTip(self.tr(
            "GIF/MP4 following the predicted position — if a point stays "
            "under the marker while the stars drift, it is that object"))
        btn_anim.clicked.connect(self._neo_motion_animation)
        row2.addWidget(btn_anim)
        lbl_zoom = QLabel(self.tr("Zoom:"))
        row2.addWidget(lbl_zoom)
        spn_zoom = PassiveSpinBox()
        spn_zoom.setRange(1, 8)
        spn_zoom.setValue(2)
        spn_zoom.setToolTip(self.tr("Crop zoom (1 = full frame)"))
        row2.addWidget(spn_zoom)
        row2.addStretch()
        gl.addLayout(row2)
        lst = PassiveList()
        lst.setMaximumHeight(120)
        gl.addWidget(lst)
        self._project_widgets["neo_products"] = lst
        self._project_widgets["neo_zoom"] = spn_zoom
        self._neo_populate_products(lst, p)

    def _neo_populate_products(self, lst, p):
        # @args: lst - read-only QListWidget, p - project dict
        # Fills the products summary from the process step data.
        lst.clear()
        step = next((s for s in p.get("steps", []) if s["step"] == "analysis"),
                    None)
        data = (step and step.get("data")) or {}
        for e in data.get("session_fits", []):
            bits = [b for b in (
                e.get("date_obs"), e.get("filter"),
                f"{e['exptime_s']:g} s" if e.get("exptime_s") else None)
                if b]
            line = f"FITS  {Path(e['path']).name}"
            if bits:
                line += "  —  " + " · ".join(str(b) for b in bits)
            lst.addItem(QListWidgetItem(line))
        for e in data.get("session_images", []):
            lst.addItem(QListWidgetItem(f"IMG  {Path(e['path']).name}"))

    def _neo_register_fits(self):
        # C0: multi-select the session FITS. Metadata is auto-read from each
        # header (fits_meta, tolerant); every file lands in project_files
        # (kind "fits") and a summary in the process step data.
        p = self._current_project
        if not p:
            return
        paths_sel, _ = QFileDialog.getOpenFileNames(
            self, self.tr("Choose session FITS"), "",
            "FITS (*.fits *.fit *.fts);;All files (*)")
        if not paths_sel:
            return
        from ..core import fits_meta
        entries = []
        for path in paths_sel:
            try:
                meta = fits_meta.read_meta(path)
            except Exception:
                meta = {}
            project.add_file(db, p["id"], path, "fits")
            entries.append({"path": path,
                            "date_obs": meta.get("date_obs"),
                            "filter": meta.get("filter"),
                            "exptime_s": meta.get("exptime_s")})
        self._neo_save_products(p, "session_fits", entries)

    def _neo_register_image(self):
        # C0: annotated images (Tycho-Tracker output etc.) -> kind "image".
        p = self._current_project
        if not p:
            return
        paths_sel, _ = QFileDialog.getOpenFileNames(
            self, self.tr("Choose annotated images"), "",
            self.tr("Images (*.png *.jpg *.jpeg *.bmp);;All files (*)"))
        if not paths_sel:
            return
        entries = []
        for path in paths_sel:
            project.add_file(db, p["id"], path, "image")
            entries.append({"path": path})
        self._neo_save_products(p, "session_images", entries)

    def _neo_motion_animation(self):
        # C1: motion GIF/MP4 from the registered session FITS — the fire
        # test: a point staying under the marker while the stars drift is
        # *that* object. Prediction: ephemeris.position_at at each DATE-OBS.
        from ..viz import motion_view
        p = self._current_project
        if not p:
            return
        step = next((s for s in p.get("steps", []) if s["step"] == "analysis"),
                    None)
        fits = ((step and step.get("data")) or {}).get("session_fits", [])
        paths_f = [e["path"] for e in fits]
        if len(paths_f) < 2:
            self.statusBar().showMessage(
                self.tr("Register at least 2 session FITS first"), 6000)
            return
        ctx = p.get("context") or {}
        obj_id = ctx.get("id") or ctx.get("packed") or p["object_name"]
        site = config.get("mpc_code", "")
        lang = config.get("language", "es")
        spn = self._project_widgets.get("neo_zoom")
        zoom = spn.value() if spn else 2
        try:
            loaded = motion_view.load_motion_frames(
                paths_f, obj_id, site, fallback_target=ctx, zoom=zoom,
                lang=lang)
        except Exception as err:
            self.statusBar().showMessage(
                self.tr("Motion animation failed: %1").replace(
                    "%1", str(err)), 8000)
            return
        frames = loaded["frames_data"]
        if len(frames) < 2:
            self.statusBar().showMessage(
                self.tr("Need at least 2 frames with WCS and ephemeris "
                        "(skipped: {})").format(len(loaded["skipped"])), 8000)
            return
        out_gif = project.storage_dir(p) / \
            f"{p['object_name']}_motion.gif"
        out_mp4 = out_gif.with_suffix(".mp4")
        names = [p["object_name"]] * len(frames)
        xys = [xy for _, xy in frames]
        motion_view.make_motion_gif(
            frames, loaded["dates"], xys, out=str(out_gif), names=names,
            lang=lang)
        motion_view.make_motion_video(
            frames, loaded["dates"], xys, out=str(out_mp4), names=names,
            lang=lang)
        project.add_file(db, p["id"], str(out_gif), "motion_gif")
        project.add_file(db, p["id"], str(out_mp4), "motion_mp4")
        self._populate_project_files(p["id"])
        msg = self.tr("Motion animation saved ({} frames)").format(len(frames))
        if loaded["skipped"]:
            msg += self.tr(" — {} skipped (no WCS/date/ephemeris)").format(
                len(loaded["skipped"]))
        self.statusBar().showMessage(msg, 10000)

    def _neo_save_products(self, p, key, entries):
        # @args: p - project dict, key - "session_fits" | "session_images",
        #        entries - list of dicts to append
        # Merges into the process step data (keeping the in-memory copy in
        # sync so consecutive registrations accumulate), then refreshes the
        # products list and the Details files list.
        step = next((s for s in p.get("steps", []) if s["step"] == "analysis"),
                    None)
        existing = []
        if step:
            existing = list((step.get("data") or {}).get(key, []))
        existing.extend(entries)
        project.update_step_data(db, p["id"], "analysis", {key: existing})
        if step is not None:
            step.setdefault("data", {})[key] = existing
        lst = self._project_widgets.get("neo_products")
        if lst is not None:
            self._neo_populate_products(lst, p)
        self._populate_project_files(p["id"])
        self.statusBar().showMessage(
            self.tr("Registered {} file(s)").format(len(entries)), 5000)

    def _build_transit_block(self, layout, p, ctx, spn_exp):
        # Track D (subplan 2): the transit capture block, written for the
        # observer who has NEVER captured one ("que cualquiera se atreva"):
        # a visual timeline of the night, the five key times (UTC + local),
        # the heuristic exposure preselected, the cadence check with the
        # overhead made explicit, and a persistent pre-flight checklist.
        # @args: layout - plan tab layout, p - project dict, ctx - project
        #        context (carries the "transit" event snapshot), spn_exp -
        #        the capture-plan exposure spin (preselected here)
        from ..core import coords, planner
        from .widgets.timeline_widget import TransitTimeline
        tr = ctx.get("transit") or {}
        plan_data = next((s["data"] for s in p["steps"]
                          if s["step"] == "plan"), {})
        grp = QGroupBox(self.tr("Transit capture plan"))
        gl = QVBoxLayout(grp)

        def _as_dt(v):
            # the context crosses the db as JSON: times come back as ISO
            # strings; accept datetimes too (fresh planner snapshots)
            if isinstance(v, datetime.datetime):
                return v
            if isinstance(v, str):
                try:
                    return datetime.datetime.fromisoformat(v)
                except ValueError:
                    return None
            return None

        dts = {k: _as_dt(tr.get(k)) for k in
               ("ingress", "mid", "egress", "capture_start", "capture_end")}
        # --- visual timeline: capture window vs darkness vs horizon -------
        # the night the transit belongs to = its EARIEST evening event (the
        # capture opens the night), NOT mid.date(): a transit straddling a
        # local midnight puts mid on the following date, so mid.date() pulled
        # in the NEXT evening's dusk/dawn and stretched the axis ~3.6x (the
        # capture bunched into a far-left sliver — HAT-P-53b: 480 vs 1770 min)
        _ev = [dts[k] for k in ("capture_start", "ingress", "mid")
               if dts[k] is not None]
        date = (min(_ev) if _ev else
                datetime.datetime.now(datetime.timezone.utc)).date()
        win = coords.tonight_window(config.get("lat"), config.get("lon"),
                                    date)
        safe = None
        if ctx.get("ra_deg") is not None and dts["capture_start"] \
                and dts["capture_end"]:
            dur = (dts["capture_end"] - dts["capture_start"]).total_seconds()
            safe = planner.safe_window_for(
                ctx["ra_deg"], ctx["dec_deg"], config, dur, date=date
            ).get("safe_window")
        timeline = TransitTimeline()
        # keep the night-view compact on very tall windows: the scene now
        # FILLS the widget (TransitTimeline._apply_fit), so the cap bounds
        # the drawing area itself
        timeline.setMaximumHeight(220)
        kw = dict(dusk=win[0] if win else None, dawn=win[1] if win else None,
                  safe=safe, capture_start=dts["capture_start"],
                  capture_end=dts["capture_end"], ingress=dts["ingress"],
                  mid=dts["mid"], egress=dts["egress"])
        timeline.set_data(**kw)
        # the timeline sits inside the Plan-tab scroll page: passive
        # preview (wheel scrolls the page, no inline pan) and a plain click
        # opens the shared ChartViewer (zoom / pan / export) — the same
        # contract as the ObjectPanel chart slots
        timeline.set_embedded(True)
        timeline.setToolTip(self.tr(
            "Click to open in the chart viewer (zoom, pan, export)"))
        timeline.scene_clicked.connect(self._open_timeline_viewer)
        # keep the draw inputs so the click handler can rebuild a FRESH
        # copy for the viewer — reparenting the embedded one would rip it
        # out of this tab
        self._project_widgets["transit_timeline"] = {
            "kw": kw, "obj": p.get("object_name") or ""}
        gl.addWidget(timeline)
        # --- the five key times, UTC + local -------------------------------
        def _hm(dt):
            return dt.strftime("%H:%M") if dt else "—"

        def _hm_local(dt):
            return dt.astimezone().strftime("%H:%M") if dt else "—"

        if dts["capture_start"] and dts["capture_end"]:
            lbl_times = QLabel(self.tr(
                "Capture (with baselines): {cs} → {ce} UTC  ·  "
                "({cs_l} → {ce_l} local)\n"
                "Ingress {i} · Mid {m} · Egress {e} UTC"
            ).format(cs=_hm(dts["capture_start"]), ce=_hm(dts["capture_end"]),
                     cs_l=_hm_local(dts["capture_start"]),
                     ce_l=_hm_local(dts["capture_end"]),
                     i=_hm(dts["ingress"]), m=_hm(dts["mid"]),
                     e=_hm(dts["egress"])))
            lbl_times.setWordWrap(True)
            gl.addWidget(lbl_times)
            self._project_widgets["transit_times"] = lbl_times
        if tr.get("baseline_fits") is False:
            lbl_warn = QLabel(self.tr(
                "⚠ The out-of-transit baseline does not fit in your night "
                "— the light curve will lack a comparison level"))
            lbl_warn.setWordWrap(True)
            lbl_warn.setStyleSheet("color: #e0c060;")
            gl.addWidget(lbl_warn)
            self._project_widgets["transit_baseline_warn"] = lbl_warn
        # --- heuristic exposure (guide, not a promise) ---------------------
        exp_rec = tr.get("exp_recommended_s")
        if exp_rec:
            lbl_exp = QLabel(
                f"<small>{self.tr('Recommended exposure')}: {exp_rec} s · "
                f"{self.tr('honest guide — confirm with a test shot (peak below saturation)')}"
                f"</small>")
            lbl_exp.setWordWrap(True)
            gl.addWidget(lbl_exp)
            spn_exp.setValue(float(exp_rec))
        # --- cadence: resolve the ingress, overhead made explicit ----------
        cad_max = tr.get("cadence_max_s")
        if cad_max:
            lbl_cad = QLabel()
            gl.addWidget(lbl_cad)
            self._project_widgets["transit_cadence"] = lbl_cad

            def _refresh_cadence():
                overhead = float(config.get("overhead_s", 15.0))
                exp = spn_exp.value()
                per = exp + overhead
                txt = self.tr(
                    "Max cadence to resolve the ingress: {cad:.0f} s · "
                    "{exp:.0f} s + {ov:.0f} s pause → one point every "
                    "{per:.0f} s").format(cad=float(cad_max), exp=exp,
                                          ov=overhead, per=per)
                if per > float(cad_max):
                    txt += "  " + self.tr(
                        "⚠ slower than the ingress — shorten the exposure")
                    lbl_cad.setStyleSheet("color: #e0c060;")
                else:
                    lbl_cad.setStyleSheet("")
                lbl_cad.setText(txt)

            spn_exp.valueChanged.connect(lambda _v: _refresh_cadence())
            _refresh_cadence()
        # --- altitude / Moon context line ----------------------------------
        bits = []
        if ctx.get("max_alt") is not None:
            bits.append(self.tr("Max altitude: {:.0f}°")
                        .format(float(ctx["max_alt"])))
        moon = suggest.moon_info(
            {"ra_deg": ctx.get("ra_deg"), "dec_deg": ctx.get("dec_deg"),
             "max_time": ctx.get("max_time")}, config)
        if moon:
            bits.append(self.tr("Moon: {:.0f}% at {:.0f}°").format(
                moon["illum"] * 100, moon["sep_deg"])
                + (" ⚠" if moon["warning"] else ""))
        if bits:
            lbl_ctx = QLabel(" · ".join(bits))
            gl.addWidget(lbl_ctx)
        # --- pre-flight checklist (persistent) ------------------------------
        gl.addWidget(QLabel(self.tr("Pre-flight checklist")))
        saved = plan_data.get("checklist") or []
        items = [
            self.tr("Test shot: the star's peak stays below saturation "
                    "(~50-70% of the detector range)"),
            self.tr("Small, constant defocus (spread the light over more "
                    "pixels; do not refocus mid-run)"),
            self.tr("Comparison star in the FOV: similar brightness and "
                    "colour, not variable"),
            self.tr("Session flats with the light filter (+ darks/bias as "
                    "usual)"),
            self.tr("Broad-band L/R filter, the same one you will report "
                    "(ExoClock logs the filter)"),
        ]
        cbs = []
        for i, text in enumerate(items):
            cb = QCheckBox(text)
            cb.setChecked(bool(saved[i]) if i < len(saved) else False)
            cb.stateChanged.connect(
                lambda _s, pid=p["id"]: self._transit_checklist_save(pid))
            gl.addWidget(cb)
            cbs.append(cb)
        self._project_widgets["transit_checklist"] = cbs
        layout.addWidget(grp)

    def _open_timeline_viewer(self, _pos=None):
        # Transit-timeline click: open the shared ChartViewer around a
        # FRESH TransitTimeline rebuilt from the stored draw inputs (the
        # embedded widget must not be reparented — it belongs to this tab).
        # The viewer drives the live widget: fit / zoom / pan / export.
        # @args: _pos - scene point under the click (unused: the whole
        #        chart opens fitted)
        from .chart_viewer import open_chart_widget
        from .widgets.timeline_widget import TransitTimeline
        stored = self._project_widgets.get("transit_timeline") or {}
        kw = stored.get("kw") or {}
        if not kw:
            return
        fresh = TransitTimeline()
        fresh.set_data(**kw)
        open_chart_widget(self, fresh,
                          title=self.tr("Transit capture plan"),
                          obj_name=stored.get("obj") or "",
                          chart_key="transit_plan")

    def _transit_checklist_save(self, pid):
        # Persists the pre-flight checklist into the plan step data, so the
        # ticks survive a project switch / an app restart.
        cbs = self._project_widgets.get("transit_checklist") or []
        if cbs:
            project.update_step_data(
                db, pid, "plan",
                {"checklist": [bool(cb.isChecked()) for cb in cbs]})

    def _build_hads_block(self, layout, p, ctx, spn_exp, spn_frames=None):
        # The HADS capture block (ADR-034): no transit-style event exists
        # (the phase is unknown), so the plan is a CONTINUOUS 2-period
        # session — see it repeat, then fold. Shows the period/amplitude,
        # the safe 2P window, the cycles that fit tonight, the heuristic
        # exposure, the cadence check (>=12 points per cycle, 15-min cap)
        # and a persistent pre-flight checklist.
        # @args: layout - plan tab layout, p - project dict, ctx - project
        #        context (carries the "hads" snapshot + window keys),
        #        spn_exp - the capture-plan exposure spin (preselected here),
        #        spn_frames - the frames spin (defaulted to fill 2P)
        h = ctx.get("hads") or {}
        plan_data = next((s["data"] for s in p["steps"]
                          if s["step"] == "plan"), {})
        grp = QGroupBox(self.tr("HADS capture plan"))
        gl = QVBoxLayout(grp)

        def _hm(v):
            # @return: "HH:MM" UTC from an ISO string/datetime, or "—"
            if isinstance(v, str):
                try:
                    v = datetime.datetime.fromisoformat(v)
                except ValueError:
                    return "—"
            return v.strftime("%H:%M") if isinstance(v, datetime.datetime) \
                else "—"

        def _hm_local(v):
            if isinstance(v, str):
                try:
                    v = datetime.datetime.fromisoformat(v)
                except ValueError:
                    return "—"
            return v.astimezone().strftime("%H:%M") if \
                isinstance(v, datetime.datetime) else "—"

        # --- summary: period, amplitude, the 2P session -------------------
        per = h.get("period_h")
        amp = h.get("amp")
        if per:
            lbl_sum = QLabel(self.tr(
                "Period {p:.2f} h · amplitude Δ{a:.1f} mag\n"
                "Recommended session: {s:.1f} h continuous (2 periods — "
                "watch it repeat, then fold)").format(
                    p=float(per), a=float(amp or 0.0),
                    s=float(h.get("session_req_h") or 2 * per)))
            lbl_sum.setWordWrap(True)
            gl.addWidget(lbl_sum)
            self._project_widgets["hads_summary"] = lbl_sum
        # --- safe 2P window (UTC + local) + cycles tonight -----------------
        bits = []
        if ctx.get("best_time"):
            bits.append(self.tr("Start around {bt} UTC ({bl} local)").format(
                bt=_hm(ctx.get("best_time")), bl=_hm_local(ctx.get("best_time"))))
        if ctx.get("latest_safe_start"):
            bits.append(self.tr("latest safe start {ls} UTC").format(
                ls=_hm(ctx.get("latest_safe_start"))))
        if h.get("cycles"):
            bits.append(self.tr("{n:.1f} full cycles fit tonight").format(
                n=float(h["cycles"])))
        if bits:
            lbl_win = QLabel(" · ".join(bits))
            lbl_win.setWordWrap(True)
            gl.addWidget(lbl_win)
            self._project_widgets["hads_window"] = lbl_win
        if h.get("session_fits") is False:
            lbl_warn = QLabel(self.tr(
                "⚠ Two full cycles don't fit back to back tonight — capture "
                "the longest contiguous run you can"))
            lbl_warn.setWordWrap(True)
            lbl_warn.setStyleSheet("color: #e0c060;")
            gl.addWidget(lbl_warn)
            self._project_widgets["hads_fits_warn"] = lbl_warn
        # --- heuristic exposure (guide, not a promise) ---------------------
        exp_rec = h.get("exp_s")
        if exp_rec:
            lbl_exp = QLabel(
                "<small>" + self.tr("Recommended exposure")
                + f": {exp_rec} s · "
                + self.tr("honest guide — confirm with a test shot at MAXIMUM brightness")
                + "</small>")
            lbl_exp.setWordWrap(True)
            gl.addWidget(lbl_exp)
            spn_exp.setValue(float(exp_rec))
            # default the frames count so the run covers the 2P session
            if spn_frames is not None and h.get("session_req_h"):
                overhead = float(config.get("overhead_s", 15.0))
                n = int(float(h["session_req_h"]) * 3600
                        / (float(exp_rec) + overhead))
                spn_frames.setValue(max(1, n))
        # --- cadence: >= 12 points per cycle, 15 min cap (AAVSO) -----------
        cad = h.get("cadence_s")
        if cad:
            lbl_cad = QLabel()
            lbl_cad.setWordWrap(True)
            gl.addWidget(lbl_cad)
            self._project_widgets["hads_cadence"] = lbl_cad

            def _refresh_cadence():
                overhead = float(config.get("overhead_s", 15.0))
                exp = spn_exp.value()
                per_point = exp + overhead
                txt = self.tr(
                    "Cadence to resolve the pulsation: one point every "
                    "≤{cad:.0f} s · {exp:.0f} s + {ov:.0f} s pause → one "
                    "point every {per:.0f} s").format(
                        cad=float(cad), exp=exp, ov=overhead, per=per_point)
                if per_point > float(cad):
                    txt += "  " + self.tr(
                        "⚠ slower than P/12 — shorten the exposure")
                    lbl_cad.setStyleSheet("color: #e0c060;")
                else:
                    lbl_cad.setStyleSheet("")
                lbl_cad.setText(txt)

            spn_exp.valueChanged.connect(lambda _v: _refresh_cadence())
            _refresh_cadence()
        # --- altitude / Moon context line ----------------------------------
        bits = []
        if ctx.get("max_alt") is not None:
            bits.append(self.tr("Max altitude: {:.0f}°")
                        .format(float(ctx["max_alt"])))
        moon = suggest.moon_info(
            {"ra_deg": ctx.get("ra_deg"), "dec_deg": ctx.get("dec_deg"),
             "max_time": ctx.get("max_time")}, config)
        if moon:
            bits.append(self.tr("Moon: {:.0f}% at {:.0f}°").format(
                moon["illum"] * 100, moon["sep_deg"])
                + (" ⚠" if moon["warning"] else ""))
        if bits:
            gl.addWidget(QLabel(" · ".join(bits)))
        # --- pre-flight checklist (persistent) ------------------------------
        gl.addWidget(QLabel(self.tr("Pre-flight checklist")))
        saved = plan_data.get("checklist") or []
        items = [
            self.tr("Focus locked at imaging temperature"),
            self.tr("Comparison stars identified (VSX chart)"),
            self.tr("Cadence ≤ P/12 set in the capture sequence"),
            self.tr("Exposure checked at MAXIMUM brightness (no saturation)"),
            self.tr("Continuous run covering 2 periods planned"),
        ]
        cbs = []
        for i, text in enumerate(items):
            cb = QCheckBox(text)
            cb.setChecked(bool(saved[i]) if i < len(saved) else False)
            cb.stateChanged.connect(
                lambda _s, pid=p["id"]: self._hads_checklist_save(pid))
            gl.addWidget(cb)
            cbs.append(cb)
        self._project_widgets["hads_checklist"] = cbs
        layout.addWidget(grp)

    def _build_variable_block(self, layout, p, ctx, spn_exp):
        # The variable/campaign plan block (ADR-035): the campaign protocol
        # reminder, the next expected extremum, tonight's safe window and
        # the heuristic exposure (the SN brightness table, B8) with a
        # saturation warning for bright stars (the T CrB lesson).
        # @args: layout - plan tab layout, p - project dict, ctx - context,
        #        spn_exp - the capture-plan exposure spin (preselected here)
        v = ctx.get("variable") or {}
        grp = QGroupBox(self.tr("Variable star plan"))
        gl = QVBoxLayout(grp)
        if p.get("campaign_id"):
            from ..core import campaign as _camp
            camp = _camp.get(db, p["campaign_id"])
            if camp:
                prot = camp.get("protocol") or {}
                bits = [self.tr("Campaign: %1").replace("%1", camp["name"])]
                if prot.get("cadence_nights"):
                    bits.append(self.tr(
                        "one measurement every %1 night(s) per filter"
                    ).replace("%1", str(prot["cadence_nights"])))
                if prot.get("filters"):
                    bits.append(self.tr("filters: %1").replace(
                        "%1", ", ".join(prot["filters"])))
                lbl = QLabel(" · ".join(bits))
                lbl.setWordWrap(True)
                gl.addWidget(lbl)
        nxt = v.get("next_extremum") or {}
        if nxt.get("days") is not None:
            lab = self.tr("Maximum") if nxt.get("kind") == "max" \
                else self.tr("Minimum")
            gl.addWidget(QLabel(self.tr("%1 expected in ~%2 days").replace(
                "%1", lab).replace("%2", f"{nxt['days']:.0f}")))
        from ..core import narrative
        swt = narrative.safe_window_text(ctx)
        if swt:
            lbl_win = QLabel(self._txt(swt))
            lbl_win.setWordWrap(True)
            gl.addWidget(lbl_win)
        if ctx.get("mag") is not None:
            from ..core import exposure
            exp_rec = exposure.recommended_sn_exposure(ctx["mag"])
            if exp_rec:
                lbl_exp = QLabel(
                    "<small>" + self.tr("Recommended exposure")
                    + f": {exp_rec} s · " + self.tr("guide, not SNR — confirm with a test shot")
                    + "</small>")
                lbl_exp.setWordWrap(True)
                gl.addWidget(lbl_exp)
                spn_exp.setValue(float(exp_rec))
            try:
                if float(ctx["mag"]) <= 10.0:
                    lbl_sat = QLabel(self.tr(
                        "⚠ Bright star: watch the saturation — a slight "
                        "defocus helps (T CrB lesson)"))
                    lbl_sat.setWordWrap(True)
                    lbl_sat.setStyleSheet("color: #e0c060;")
                    gl.addWidget(lbl_sat)
            except (TypeError, ValueError):
                pass
        layout.addWidget(grp)
        self._project_widgets["variable_block"] = grp

    def _hads_checklist_save(self, pid):
        # Persists the HADS pre-flight checklist (same plan-data "checklist"
        # key as the transit block: one project carries one kind).
        cbs = self._project_widgets.get("hads_checklist") or []
        if cbs:
            project.update_step_data(
                db, pid, "plan",
                {"checklist": [bool(cb.isChecked()) for cb in cbs]})

    def _transit_export_exotic(self):
        # 4d: enrich the planet (worker — the GUI never blocks on the
        # network; the Archive row is cached from the Details tab anyway),
        # then write the pre-filled inits.json next to a user-chosen path.
        p = self._current_project
        if not p:
            return
        from .workers import ExploreWorker
        self.statusBar().showMessage(
            self.tr("Gathering planet data for EXOTIC…"), 4000)
        worker = ExploreWorker(config, p["object_name"],
                               fallback_target=p.get("context") or {})
        worker.finished.connect(lambda e: self._exotic_write(p["id"], e))
        self._keep(worker)
        worker.start()

    def _exotic_write(self, pid, e):
        # @args: pid - project id, e - enrich result ({} on failure)
        from ..core import exotic
        p = project.get(db, pid)
        if not p:
            return
        if not e or not e.get("data"):
            self.statusBar().showMessage(
                self.tr("No planet data — check the name and retry"), 8000)
            return
        ctx = p.get("context") or {}
        # the capture plan (filter/exposure) saved in the plan step feeds
        # the filter name and the exposure time of the handoff file
        plan_data = next((s["data"] for s in p["steps"]
                          if s["step"] == "plan"), {})
        plan = {"filter": plan_data.get("filter", "L"),
                "exp_s": plan_data.get("exp_s")}
        outdir = project.storage_dir(p)
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export EXOTIC inits.json"),
            str(outdir / exotic.suggested_name()),
            "JSON (*.json);;All files (*)")
        if not out:
            return
        inits = exotic.make_inits(ctx, e["data"], config, plan=plan,
                                  out_dir=str(Path(out).parent))
        path = exotic.export_inits(inits, out)
        project.add_file(db, pid, path, "exotic_inits")
        self._populate_project_files(pid)
        self.statusBar().showMessage(
            self.tr("inits.json written — run EXOTIC in your Python ≤3.10 "
                    "environment"), 10000)

    def _build_publish_tab(self, p, kind, ctx):
        layout = self._step_section("publish")
        btn = QPushButton(self.tr("Generate post…"))
        btn.clicked.connect(self._project_post)
        layout.addWidget(btn)
        layout.addWidget(QLabel(
            f"<small>{self.tr('Opens the post dialog for')} "
            f"{p['object_name']}</small>"))
        layout.addStretch()

    def _fu_cadence_state(self, p, pid):
        # The cadence line for the follow-up kinds (T9): text + colour,
        # shared by the tab build and the in-place refresh after a visit
        # changes (ADR-045).
        # @return: (text, colour) or (None, None) when there are no
        #          visits yet
        from ..core import followup as fu
        camp = None
        if p.get("campaign_id"):
            from ..core import campaign as _camp
            camp = _camp.get(db, p["campaign_id"])
        days = fu.days_since_last_session(db, pid)
        threshold = int(config.get("sn_cadence_days", 3))
        if camp is not None:
            threshold = int((camp.get("protocol") or {}).get(
                "cadence_nights") or threshold)
        if days is None:
            return None, None
        text = self.tr("Last visit: {} days ago").format(days)
        if p["kind"] == "hads" \
                and (p["context"].get("hads") or {}).get("multiperiodic"):
            text += " · " + self.tr(
                "multiperiodic stars want consecutive nights")
        colour = "#e0c060" if days >= threshold else "#8a90a6"
        return text, colour

    def _fu_header_blocks(self, layout, p, pid):
        # The follow-up kinds' header above the visits manager (ADR-045):
        # cadence reminder, the campaign protocol when the project hangs
        # from one, and the event advisor (V-h).
        from ..core import followup as fu
        text, colour = self._fu_cadence_state(p, pid)
        if text is not None:
            lbl_cadence = QLabel(text)
            lbl_cadence.setStyleSheet(f"color: {colour}; font-size: 13px;")
            layout.addWidget(lbl_cadence)
            self._project_widgets["fu_cadence"] = lbl_cadence
        else:
            layout.addWidget(QLabel(
                self.tr("No visits yet. Add one to start the follow-up.")))

        # campaign protocol (ADR-035): show the agreed observing protocol
        camp = None
        if p.get("campaign_id"):
            from ..core import campaign as _camp
            camp = _camp.get(db, p["campaign_id"])
        if camp is not None:
            prot = camp.get("protocol") or {}
            bits = [self.tr("Campaign: %1").replace("%1", camp["name"])]
            if prot.get("cadence_nights"):
                bits.append(self.tr("cadence every %1 night(s)").replace(
                    "%1", str(prot["cadence_nights"])))
            if prot.get("filters"):
                bits.append(self.tr("filters: %1").replace(
                    "%1", ", ".join(prot["filters"])))
            if prot.get("comp_stars"):
                bits.append(self.tr("comparison stars: %1").replace(
                    "%1", ", ".join(prot["comp_stars"])))
            lbl_prot = QLabel(" · ".join(bits))
            lbl_prot.setWordWrap(True)
            layout.addWidget(lbl_prot)
            if prot.get("notes"):
                lbl_notes = QLabel("⚠ " + prot["notes"])
                lbl_notes.setWordWrap(True)
                lbl_notes.setStyleSheet("color: #e0c060;")
                layout.addWidget(lbl_notes)

        # event advisor (V-h): warn when the latest own point jumped
        from ..core import variables as _vars
        ev = _vars.detect_event(
            fu.list_points(db, pid),
            threshold=float(config.get("event_mag_threshold", 0.5)))
        if ev:
            if ev["direction"] == "drop":
                msg = self.tr("⚠ Possible brightness drop (Δ≈+%1 mag, filter %2): consider raising the cadence tonight")
            else:
                msg = self.tr("⚠ Possible outburst (Δ≈−%1 mag, filter %2): top priority tonight")
            lbl_ev = QLabel(msg.replace("%1", f"{ev['delta_mag']:.2f}")
                            .replace("%2", ev["filter"]))
            lbl_ev.setWordWrap(True)
            lbl_ev.setStyleSheet("color: #e0c060;")
            layout.addWidget(lbl_ev)

    def _fu_campaign_text(self, p, pid):
        # The campaign summary line over the saved points (ADR-044): the
        # series engine reports nights, points, slope, delta-from-peak and
        # the verdict. Shared by the tab build and the in-place refresh.
        # @return: the text
        from ..core import followup as fu
        camp_pts = fu.list_points(db, pid)
        if not camp_pts:
            return self.tr(
                "No points saved yet. Open a visit's plate in the editor "
                "or add a magnitude by hand: the summary updates after "
                "every save.")
        from ..core import series as _series
        ctx = p["context"]
        camp = _series.analyze_campaign(
            camp_pts, sn_type=ctx.get("sn_type") or ctx.get("otype"))
        text = self.tr("{n} nights · {p} points").format(
            n=camp.get("nights", 0), p=len(camp_pts))
        slope = camp.get("slope_mag_per_day")
        if slope is not None:
            text += self.tr(" · {:.2f} mag/day").format(slope)
        delta = camp.get("delta_from_peak")
        if delta is not None:
            text += self.tr(" · {:.2f} mag from peak").format(delta)
        verdict_map = {
            "normal": self.tr("consistent with the typical curve"),
            "faster": self.tr("fading faster than typical"),
            "slower": self.tr("fading slower than typical"),
            "unknown": self.tr("no template to compare against"),
            "no_data": self.tr("no data")}
        verdict = camp.get("verdict") or "unknown"
        text += self.tr(" · verdict: {}").format(
            verdict_map.get(verdict, verdict))
        return text

    def _fu_science_blocks(self, layout, p, ctx, pid):
        # The photometry science blocks under the visits manager
        # (ADR-045): the comparison-chart action and the bulk tools menu,
        # the sequence status line, the light curve, the campaign
        # summary and the SN-only animation block.
        from ..core import followup as fu
        kind = p["kind"]
        act_row = QHBoxLayout()
        # ADR-042: the photometry prerequisite, «with what do I compare?»,
        # as a primary action (ADR-038 prominence), never buried in the menu
        btn_seq = QPushButton(self.tr("Comparison chart…"))
        btn_seq.setToolTip(self.tr(
            "Pick the reference stars for this target: NightScribe "
            "proposes them over the field image (brighter, of similar "
            "colour, never a known variable)"))
        btn_seq.clicked.connect(lambda: self._fu_sequence_dialog(pid))
        act_row.addWidget(btn_seq)
        from PySide6.QtWidgets import QMenu, QToolButton
        tools = QToolButton()
        tools.setText(self.tr("⋯ Photometry tools"))
        tools.setPopupMode(QToolButton.InstantPopup)
        tools_menu = QMenu(tools)
        act_paste = tools_menu.addAction(self.tr("Paste photometry…"))
        act_paste.triggered.connect(lambda: self._fu_paste_dialog(pid))
        act_file = tools_menu.addAction(self.tr("Import file…"))
        act_file.triggered.connect(lambda: self._fu_import_file(pid))
        act_export = tools_menu.addAction(
            self.tr("Export photometry report…"))
        act_export.setToolTip(self.tr(
            "CSV or AAVSO EFF with heliocentric dates, for the campaign "
            "form / WebObs"))
        act_export.triggered.connect(lambda: self._fu_export_report(pid))
        if kind in ("sn", "variable"):
            act_survey = tools_menu.addAction(
                self.tr("Download survey photometry…"))
            act_survey.setToolTip(self.tr(
                "ASAS-SN/ZTF context points, drawn in grey and never "
                "mixed with your own measurements"))
            act_survey.triggered.connect(
                lambda: self._fu_download_survey(pid))
            # the download toggles enabled-state mid-flight: the action
            # carries the same registry key the old button had
            self._project_widgets["fu_survey"] = act_survey
        tools.setMenu(tools_menu)
        act_row.addWidget(tools)
        act_row.addStretch()
        layout.addLayout(act_row)

        # ADR-042: the comparison-sequence status in one plain line
        lbl_seq = QLabel(self._fu_sequence_status_text(p))
        lbl_seq.setStyleSheet("color: #8a90a6; font-size: 12px;")
        layout.addWidget(lbl_seq)
        self._project_widgets["fu_sequence"] = lbl_seq

        # Inline light curve (2026-09-17): all the project's photometry —
        # manual, pasted, file, measured, survey — with the SN template
        # or the folded sawtooth. Live in the tab, no dialog, no rebuild;
        # the template is toggleable without the axis moving.
        if kind in ("sn", "variable"):
            from .widgets.lightcurve_widget import LightCurveChart
            from ..core import lightcurve_data
            grp_lc = QGroupBox(self.tr("Light curve"))
            glc = QVBoxLayout(grp_lc)
            chk_tpl = QCheckBox(self.tr("Show template"))
            chk_tpl.setChecked(True)
            glc.addWidget(chk_tpl)
            lchart = LightCurveChart()
            lchart.setMinimumHeight(220)
            glc.addWidget(lchart, stretch=1)
            lcurve_pts = fu.list_points(db, pid)
            if lcurve_pts:
                payload = lightcurve_data.build_payload(
                    {"points": lcurve_pts,
                     "sn_type": ctx.get("sn_type")},
                    sn_type_fallback=ctx.get("sn_type") or ctx.get("otype"),
                    variable=ctx.get("variable"))
                lchart.set_data(
                    payload["points"],
                    sn_type=payload.get("sn_type"),
                    peak_mjd=payload.get("peak_mjd"),
                    peak_mag=payload.get("peak_mag"),
                    fold_period_d=payload.get("fold_period_d"),
                    epoch_mjd=payload.get("epoch_mjd"),
                    schematic=payload.get("schematic"))
            chk_tpl.toggled.connect(lchart.set_template_visible)
            layout.addWidget(grp_lc)
            self._project_widgets["fu_curve"] = lchart

            # campaign summary over the saved points (ADR-044): the series
            # engine reports how the campaign goes so far, rebuilt on tab
            # open and refreshed in place after each saved point
            grp_camp = QGroupBox(self.tr("Campaign summary"))
            grp_camp.setObjectName("fu_campaign_summary")
            g_camp = QVBoxLayout(grp_camp)
            camp_lbl = QLabel("")
            camp_lbl.setObjectName("fu_campaign_text")
            camp_lbl.setWordWrap(True)
            g_camp.addWidget(camp_lbl)
            camp_lbl.setText(self._fu_campaign_text(p, pid))
            layout.addWidget(grp_camp)
            self._project_widgets["fu_campaign_text"] = camp_lbl

        # B6/B10: the SN evolution animation and the annotated FITS export
        # — secondary analysis tools, collapsed by default (UX-PC U4).
        # HADS never had them (intra-night series live in FotoDif,
        # ADR-034 D.3); the retired quick-look (V-g, ADR-019) served
        # variables, so this block is SN-only now.
        if kind == "sn":
            adv = self._advanced_block(
                layout, self.tr("Animation and annotated FITS"))
            ana_row = QHBoxLayout()
            btn_evo = QPushButton(self.tr("Generate animation"))
            btn_evo.setToolTip(self.tr(
                "GIF/MP4 of the photometric evolution across visits"))
            btn_evo.clicked.connect(lambda: self._fu_run_animation(pid))
            ana_row.addWidget(btn_evo)
            btn_annot = QPushButton(self.tr("Export annotated FITS"))
            btn_annot.setToolTip(self.tr(
                "Preview the stacked FITS, place the SN marker and save "
                "an annotated copy (AIJ readable)"))
            btn_annot.clicked.connect(
                lambda: self._fu_export_annotated(pid))
            ana_row.addWidget(btn_annot)
            ana_row.addStretch()
            adv.addLayout(ana_row)

    def _fu_run_animation(self, pid):
        # B6: generate the evolution GIF/MP4 from the registered stacked images.
        from ..core import followup as fu
        from ..viz import evolution_view
        p = project.get(db, pid)
        if not p:
            return
        fits_paths = []
        dates = []
        for s in fu.list_sessions(db, pid):
            for img in fu.list_images(db, s["id"]):
                if img["fits_path"]:
                    fits_paths.append(img["fits_path"])
                    dates.append(s["obs_date"])
        if len(fits_paths) < 2:
            self.statusBar().showMessage(
                self.tr("Need at least 2 stacked images"), 5000)
            return
        ctx = p.get("context") or {}
        sn_ra = ctx.get("ra_deg")
        sn_dec = ctx.get("dec_deg")
        if sn_ra is None or sn_dec is None:
            self.statusBar().showMessage(
                self.tr("Project has no coordinates"), 5000)
            return
        # align frames by WCS and build the animation
        try:
            frames_data = []
            dates_out = []
            for path, date in zip(fits_paths, dates):
                import numpy as np
                from ..core import fits_io, wcs as wcs_mod
                header, data = fits_io.read_fits(path)
                wcs = wcs_mod.Wcs.from_header(header)
                sn_xy = wcs.sky_to_pixel(sn_ra, sn_dec) if wcs else None
                img8, sn_crop = evolution_view.align_frame(
                    data, wcs, wcs, sn_xy or (data.shape[1]//2,
                                                    data.shape[0]//2))
                frames_data.append((img8, sn_crop))
                dates_out.append(date or "")
            out_gif = project.storage_dir(p) / \
                f"{p['object_name']}_evo.gif"
            out_mp4 = out_gif.with_suffix(".mp4")
            evolution_view.make_evolution_gif(
                frames_data, dates=dates_out,
                sn_xy_s=[sn for _, sn in frames_data],
                out=str(out_gif), names=[p["object_name"]]*len(frames_data))
            evolution_view.make_evolution_video(
                frames_data, dates=dates_out,
                sn_xy_s=[sn for _, sn in frames_data],
                out=str(out_mp4), names=[p["object_name"]]*len(frames_data))
            project.add_file(db, pid, str(out_gif), "evo_gif")
            project.add_file(db, pid, str(out_mp4), "evo_mp4")
            self._populate_project_files(pid)
            self.statusBar().showMessage(
                self.tr("Animation written to %1").replace("%1", str(out_gif)),
                8000)
        except Exception as err:
            self.statusBar().showMessage(
                self.tr("Animation failed: %1").replace("%1", str(err)), 8000)

    def _fu_export_annotated(self, pid):
        # B10: open the preview dialog; the observer picks which of the
        # registered stacked FITS to annotate (several visits => several
        # plates), checks the marker, overlays and stretch, and only then
        # confirms: a copy is written with the SN marked (AIJ ANNOTATE
        # card) at that moment.
        from ..core import followup as fu
        p = project.get(db, pid)
        if not p:
            return
        images = []
        for s in fu.list_sessions(db, pid):
            for img in fu.list_images(db, s["id"]):
                if img["fits_path"]:
                    images.append({
                        "fits_path": img["fits_path"],
                        "date_obs": img.get("date_obs") or s.get("obs_date"),
                        "filter": img.get("filter"),
                        "exptime_s": img.get("exptime_s"),
                    })
        if not images:
            self.statusBar().showMessage(
                self.tr("No stacked images registered"), 5000)
            return
        ctx = p.get("context") or {}
        sn_ra = ctx.get("ra_deg")
        sn_dec = ctx.get("dec_deg")
        if self._use_ufe():
            # ADR-044: the annotated FITS inside the editor; the whole
            # object attaches (marker on its sky position), the other
            # visits queue as extra plates, and written copies register
            # like the legacy dialog's did
            obj = self._ufe_object_from_project(p)
            dlg = self._ufe_open("annotate", hook_pid=pid, obj=obj)
            if not dlg.open_plate(images[-1]["fits_path"]):
                return
            dlg.set_object(obj)          # re-apply on the fresh plate
            dlg.tab_annotate.prefill(
                notes=self.tr("SN follow-up"),
                extra_paths=[im["fits_path"] for im in images[:-1]])
            return
        # Preview first: the observer chooses the plate, checks the marker,
        # the overlays and the stretch. The dialog resolves the WCS from
        # the chosen frame's header (each visit may carry the SN on a
        # different plate) and writes the copy only on confirm.
        from .sn_annotate_dialog import SnAnnotateDialog
        try:
            dlg = SnAnnotateDialog(
                self, images, p, p["object_name"],
                ra_deg=sn_ra, dec_deg=sn_dec,
                default_notes=self.tr("SN follow-up"))
        except Exception as err:
            self.statusBar().showMessage(
                self.tr("Could not open the FITS for annotation: %1")
                .replace("%1", str(err)), 8000)
            return
        dlg.saved.connect(lambda path: self._fu_annotated_saved(pid, path))
        dlg.exec()

    def _fu_annotated_saved(self, pid, path):
        # @args: pid - project id, path - annotated copy just written
        try:
            project.add_file(db, pid, path, "fits")
            self._populate_project_files(pid)
        except Exception as err:
            logger.warning("annotated FITS saved but not registered: %s",
                           err)
        self.statusBar().showMessage(
            self.tr("Annotated FITS written to %1")
            .replace("%1", str(path)), 8000)

    def _fu_paste_dialog(self, pid):
        # B3: paste bulk photometry — tolerant parser + preview + save.
        from ..core.photometry_import import parse_photometry
        from ..core import followup as fu
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Paste photometry"))
        dlg.setLayout(QVBoxLayout())
        dlg.layout().addWidget(QLabel(self.tr(
            "Paste your AIJ / Tycho / CSV measurements.\n"
            "One per line: date  magnitude  [error]  filter")))
        edit = QTextEdit()
        edit.setMinimumSize(400, 200)
        dlg.layout().addWidget(edit)
        # default filter for lines without one
        cmb_def = QComboBox()
        cmb_def.setEditable(True)
        cmb_def.addItems(["Clear", "V", "R", "B", "I", "NIR"])
        dlg.layout().addWidget(QLabel(self.tr("Default filter:")))
        dlg.layout().addWidget(cmb_def)
        preview = QListWidget()
        dlg.layout().addWidget(QLabel(self.tr("Preview:")))
        dlg.layout().addWidget(preview)
        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg.layout().addWidget(btns)
        # live parse as the user types
        def _human(mjd):
            # preview-only: show the parsed date so a typo is visible
            # before saving. ±60-year sanity band around today (2026).
            from ..core import coords
            try:
                dt = coords.datetime_from_jd(mjd + 2400000.5)
                s = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, OverflowError):
                return f"MJD {mjd:.5f}"
            if not (39380.0 <= mjd <= 83220.0):
                s += "  " + self.tr("⚠ date outside 1966–2086 — check")
            return s

        def on_text_changed():
            pts, skipped = parse_photometry(
                edit.toPlainText(),
                default_filter=cmb_def.currentText().strip() or "Clear")
            preview.clear()
            for p in pts:
                err_str = f" ±{p['err']}" if p["err"] else ""
                preview.addItem(
                    f"{_human(p['mjd'])}  ·  mag {p['mag']}{err_str}"
                    f"  [{p['filter']}]")
            if skipped:
                preview.addItem(
                    self.tr("({} lines skipped)").format(len(skipped)))
        edit.textChanged.connect(on_text_changed)
        cmb_def.currentTextChanged.connect(on_text_changed)
        if dlg.exec() != QDialog.Accepted:
            return
        pts, _ = parse_photometry(
            edit.toPlainText(),
            default_filter=cmb_def.currentText().strip() or "Clear")
        sid = self._selected_visit_id()
        for p in pts:
            fu.add_point(db, pid, p["mjd"], p["filter"], p["mag"],
                         err=p["err"], source="paste", session_id=sid)
        self._populate_project_files(pid)

    def _fu_import_file(self, pid):
        # B3: optional file import — read, parse, preview, save.
        from ..core.photometry_import import parse_photometry
        from ..core import followup as fu
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Import photometry file"), "",
            "CSV/Text (*.csv *.txt *.tsv);;All files (*)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError as err:
            self.statusBar().showMessage(
                self.tr("Cannot read file: %1").replace("%1", str(err)), 6000)
            return
        pts, skipped = parse_photometry(text)
        # quick confirmation with a count
        msg = self.tr("{} points parsed").format(len(pts))
        if skipped:
            msg += self.tr(", {} lines skipped").format(len(skipped))
        if QMessageBox.question(
                self, self.tr("Import"), msg,
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        sid = self._selected_visit_id()
        for p in pts:
            fu.add_point(db, pid, p["mjd"], p["filter"], p["mag"],
                          err=p["err"], source="file", session_id=sid)
        self._populate_project_files(pid)

    def _fu_sequence_status_text(self, p):
        # One plain line with the comparison-sequence status (ADR-042).
        # @args: p - project dict
        # @return: the status sentence (plain language, ADR-038)
        seq = (p.get("context") or {}).get("sequence") or {}
        entries = seq.get("entries") or []
        if not entries:
            return self.tr(
                "No comparison sequence yet — «Comparison chart…» answers "
                "the question: with what do I compare?")
        n_comp = sum(1 for e in entries if e.get("kind") != "check")
        has_check = any(e.get("kind") == "check" for e in entries)
        text = self.tr("Sequence: %1 comparison stars").replace(
            "%1", str(n_comp))
        if has_check:
            text += self.tr(" + check star")
        if seq.get("catalog_name"):
            text += " · " + seq["catalog_name"]
        return text

    def _fu_sequence_via_ufe(self, pid):
        # The comparison chart inside the UFE (ADR-044): the project's
        # newest registered plate when there is one, else the Compare
        # tab's own survey (DSS2) download; saves register into the
        # project through the hook (files + sequence context + campaign
        # protocol, the legacy default).
        p = project.get(db, pid)
        if not p:
            return
        obj = self._ufe_object_from_project(p)
        dlg = self._ufe_open("compare", hook_pid=pid, obj=obj)
        from ..core import followup as fu
        fits_path = None
        for s in fu.list_sessions(db, pid):
            for img in fu.list_images(db, s["id"]):
                if img["fits_path"]:
                    fits_path = img["fits_path"]      # the newest visit
        if fits_path and not dlg.open_plate(fits_path):
            return
        dlg.set_object(obj)              # re-apply on the fresh plate

    def _fu_sequence_dialog(self, pid):
        if self._use_ufe():
            self._fu_sequence_via_ufe(pid)
            return
        # Options dialog + launch of the comparison chart (ADR-042). The
        # heavy work (VizieR, image, render) runs in a SequenceWorker: the
        # GUI never blocks.
        p = project.get(db, pid)
        if not p:
            return
        ctx = p.get("context") or {}
        ra, dec = ctx.get("ra_deg"), ctx.get("dec_deg")
        if ra is None or dec is None:
            self.statusBar().showMessage(self.tr(
                "This project has no coordinates: cannot build the chart"),
                8000)
            return
        camp = None
        if p.get("campaign_id"):
            from ..core import campaign as _camp
            camp = _camp.get(db, p["campaign_id"])

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Comparison chart"))
        form = QFormLayout(dlg)
        intro = QLabel(self.tr(
            "«With what do I compare?» Choose the catalog and NightScribe "
            "proposes the reference stars over the field image: brighter "
            "than the target, of similar colour when known, and never a "
            "known variable."))
        intro.setWordWrap(True)
        form.addRow(intro)
        cmb_cat = QComboBox()
        cmb_cat.addItem("Gaia EDR3 (G)", "gaia")
        cmb_cat.addItem("APASS DR9 (V)", "apass")
        form.addRow(self.tr("Catalog:"), cmb_cat)
        spn_fov = QSpinBox()
        spn_fov.setRange(3, 60)
        spn_fov.setValue(18)
        spn_fov.setSuffix(" \u2032")
        form.addRow(self.tr("Field of view:"), spn_fov)
        spn_comps = QSpinBox()
        spn_comps.setRange(2, 15)
        spn_comps.setValue(8)
        form.addRow(self.tr("Comparison stars:"), spn_comps)
        mag0 = ctx.get("mag")
        if mag0 is None:
            mag0 = (ctx.get("variable") or {}).get("max")
        spn_mag = QDoubleSpinBox()
        spn_mag.setRange(-2.0, 25.0)
        spn_mag.setDecimals(2)
        spn_mag.setValue(float(mag0) if mag0 is not None else 12.0)
        spn_mag.setToolTip(self.tr(
            "Used to propose brighter comparisons; the current best "
            "estimate comes pre-filled"))
        form.addRow(self.tr("Target magnitude:"), spn_mag)
        fits_row = QHBoxLayout()
        ed_fits = QLineEdit()
        ed_fits.setPlaceholderText(self.tr(
            "Optional: your stacked FITS as the background"))
        fits_row.addWidget(ed_fits)

        def _browse():
            path, _ = QFileDialog.getOpenFileName(
                dlg, self.tr("Your FITS image"), "",
                "FITS (*.fits *.fit *.fts);;" + self.tr("All files (*)"))
            if path:
                ed_fits.setText(path)

        btn_browse = QPushButton(self.tr("Browse…"))
        btn_browse.clicked.connect(_browse)
        fits_row.addWidget(btn_browse)
        form.addRow(self.tr("Background:"), fits_row)
        lbl_fits_hint = QLabel(self.tr(
            "If your FITS has no astrometry we solve it with "
            "Astrometry.net (your file is never modified); without it, "
            "the background is the DSS2 survey image"))
        lbl_fits_hint.setWordWrap(True)
        lbl_fits_hint.setStyleSheet("color: #8a90a6; font-size: 12px;")
        form.addRow(lbl_fits_hint)
        chk_camp = None
        if camp is not None:
            chk_camp = QCheckBox(self.tr(
                "Also save the sequence to the campaign protocol"))
            chk_camp.setChecked(True)
            form.addRow(chk_camp)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText(self.tr("Generate"))
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() != QDialog.Accepted:
            return

        from .workers import SequenceWorker
        fits_path = ed_fits.text().strip()
        w = SequenceWorker(p["object_name"], ra, dec,
                           cmb_cat.currentData(), float(spn_fov.value()),
                           spn_comps.value(), spn_mag.value(),
                           Path(fits_path) if fits_path else None,
                           self._lang())
        # The build takes seconds (VizieR + image download): a modal busy
        # dialog says so plainly — the status bar alone reads as "nothing
        # is happening". No Cancel: a download cannot be aborted halfway,
        # so the dialog never promises what it cannot keep.
        wait = QProgressDialog(
            self.tr("Building the comparison chart…"), "", 0, 0, self)
        wait.setWindowTitle(self.tr("Comparison chart"))
        wait.setWindowModality(Qt.WindowModal)
        wait.setCancelButton(None)
        wait.setMinimumDuration(0)
        w.progress.connect(wait.setLabelText)
        w.progress.connect(lambda m: self.statusBar().showMessage(m, 0))
        save_camp = chk_camp is not None and chk_camp.isChecked()
        w.finished.connect(
            lambda out: self._fu_sequence_landed(wait, pid, out, save_camp))
        self._keep(w)
        self.statusBar().showMessage(
            self.tr("Building the comparison chart…"), 0)
        w.start()

    def _fu_sequence_landed(self, wait, pid, out, save_campaign):
        # The SequenceWorker finished: the wait dialog is closed and reaped
        # BEFORE anything else runs — the picker's exec() spins a nested
        # loop, so any pending dialog would otherwise linger on top of it.
        # close()+deleteLater(): the reap discipline of e31f394.
        # @args: wait - the busy QProgressDialog, pid - project id,
        #        out - worker payload, save_campaign - protocol flag
        wait.close()
        wait.deleteLater()
        self._fu_sequence_done(pid, out, save_campaign)

    def _fu_sequence_done(self, pid, out, save_campaign):
        # Lands the SequenceWorker result: warnings on the status bar and
        # the interactive picker dialog (ADR-042 phase 4); files/context
        # are only written when the user saves from the dialog.
        self.statusBar().clearMessage()
        if out.get("status") != "ok":
            self.statusBar().showMessage(
                out.get("error") or self.tr("Could not build the chart"),
                10000)
            return
        p = project.get(db, pid)
        if not p:
            return
        notes = []
        if out.get("vsx_warning"):
            notes.append(self.tr(
                "VSX did not answer: field variables are not flagged"))
        if out.get("fits_error"):
            notes.append(out["fits_error"])
        if out.get("target_outside"):
            notes.append(self.tr(
                "the target falls outside your image: DSS2 used instead"))
        if notes:
            self.statusBar().showMessage(". ".join(notes), 10000)
        from .seqchart_dialog import SeqChartDialog
        dlg = SeqChartDialog(
            self, p["object_name"], out["field"], out["entries"],
            image=out.get("image"), wcs=out.get("wcs"),
            img_label=out.get("img_label", ""), lang=self._lang(),
            default_dir=project.storage_dir(p),
            on_save=lambda entries, files: self._fu_sequence_save(
                pid, entries, files, out, save_campaign))
        dlg.exec()

    def _fu_sequence_save(self, pid, entries, files, out, save_campaign):
        # Persists the sequence the user confirmed in the picker dialog:
        # files registered, sequence into the project context (and the
        # campaign protocol when asked), status line refreshed.
        # @args: pid - project id, entries - sequence entries, files -
        #        {"csv", "png"} written by the dialog, out - the worker
        #        payload (catalog metadata), save_campaign - protocol flag
        p = project.get(db, pid)
        if not p:
            return
        project.add_file(db, pid, files["csv"], "report")
        project.add_file(db, pid, files["png"], "chart")
        project.update_context(db, pid, {"sequence": {
            "catalog": out["catalog"], "catalog_name": out["catalog_name"],
            "fov_arcmin": out["fov_arcmin"], "target_mag":
            out["target_mag"], "entries": entries, "csv": files["csv"],
            "png": files["png"]}})
        if save_campaign and p.get("campaign_id"):
            from ..core import campaign as _camp
            c = _camp.get(db, p["campaign_id"])
            if c:
                prot = c.get("protocol") or {}
                prot["comp_stars"] = [
                    f"{e['name']} {e['star']['band']} "
                    f"{e['star']['mag']:.2f}" for e in entries]
                _camp.update(db, c["id"], protocol=prot)
        self.statusBar().showMessage(
            self.tr("Comparison chart ready"), 8000)
        p = project.get(db, pid)
        lbl = self._project_widgets.get("fu_sequence")
        if lbl is not None and p:
            lbl.setText(self._fu_sequence_status_text(p))
        self._populate_project_files(pid)

    def _fu_export_report(self, pid):
        # Exports the project's photometry to CSV or AAVSO EFF (HJD in-app,
        # ADR-035 V-i) and registers the file in the project.
        from ..core import photometry_export
        p = project.get(db, pid)
        ctx = p.get("context") or {}
        # quick-look inclusion is an explicit choice (T6)
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Export photometry report"))
        form = QFormLayout(dlg)
        cmb_fmt = QComboBox()
        cmb_fmt.addItem(self.tr("CSV (group format)"), "csv")
        cmb_fmt.addItem(self.tr("AAVSO EFF (WebObs)"), "eff")
        form.addRow(self.tr("Format:"), cmb_fmt)
        chk_ql = QCheckBox(self.tr("Include quick-look (indicative) points"))
        form.addRow(chk_ql)
        box = QDialogButtonBox(QDialogButtonBox.Save
                               | QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() != QDialog.Accepted:
            return
        pts = photometry_export.collect_points(db, pid,
                                               include_quicklook=
                                               chk_ql.isChecked())
        if not pts:
            self.statusBar().showMessage(
                self.tr("No photometry points to export"), 6000)
            return
        # comparison stars: the project's saved sequence wins (ADR-042);
        # the campaign protocol strings are the fallback
        comps, observer = [], config.get("aavso_code", "")
        comp, check = None, None
        seq_entries = (ctx.get("sequence") or {}).get("entries") or []
        if seq_entries:
            comps = [e["name"] for e in seq_entries
                     if e.get("kind") == "comp"]
            first = next((e for e in seq_entries
                          if e.get("kind") == "comp"), None)
            chk = next((e for e in seq_entries
                        if e.get("kind") == "check"), None)
            if first:
                comp = {"name": first["name"], "mag": first["star"]["mag"]}
            if chk:
                check = {"name": chk["name"], "mag": chk["star"]["mag"]}
        if not comps and p.get("campaign_id"):
            from ..core import campaign as _camp
            camp = _camp.get(db, p["campaign_id"])
            if camp:
                comps = (camp.get("protocol") or {}).get("comp_stars") or []
        ext = ".txt" if cmb_fmt.currentData() == "eff" else ".csv"
        outdir = project.storage_dir(p)
        default = outdir / f"{p['object_name']}_photometry{ext}"
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export photometry report"), str(default),
            f"*{ext};;All files (*)")
        if not out:
            return
        meta = {"name": p["object_name"], "ra_deg": ctx.get("ra_deg"),
                "dec_deg": ctx.get("dec_deg")}
        if cmb_fmt.currentData() == "eff":
            path = photometry_export.export_eff(pts, out, obscode=observer,
                                                comp=comp, check=check,
                                                **meta)
        else:
            path = photometry_export.export_csv(pts, out, observer=observer,
                                                comp_stars=comps, **meta)
        project.add_file(db, pid, str(path), "report")
        self.statusBar().showMessage(
            self.tr("Written to %1").replace("%1", str(path)), 8000)

    def _fu_download_survey(self, pid):
        # Pulls the survey context points (V-f; closes the B12 option) into
        # photometry_points as source="survey:ztf". The download runs in a
        # SurveyWorker (UX-f): the GUI never blocks on the network.
        # Idempotent: a point with the same mjd+filter+source is not
        # duplicated.
        p = project.get(db, pid)
        ctx = p.get("context") or {}
        ra, dec = ctx.get("ra_deg"), ctx.get("dec_deg")
        if ra is None or dec is None:
            self.statusBar().showMessage(
                self.tr("The project has no coordinates"), 6000)
            return
        from .workers import SurveyWorker
        btn = self._project_widgets.get("fu_survey")
        if btn is not None:
            btn.setEnabled(False)
        w = SurveyWorker(ra, dec)
        w.finished.connect(lambda out: self._fu_survey_done(pid, out))
        self._keep(w)

    def _fu_survey_done(self, pid, out):
        # Stores the worker's result and reports the outcome — the old
        # silent success was the bug. ok: upserts (added/updated/unchanged/
        # removed), MJD range, bands, origin. empty: nothing at the
        # position. error: what the network said.
        from ..core import followup as fu
        btn = self._project_widgets.get("fu_survey")
        if btn is not None:
            btn.setEnabled(True)
        status = (out or {}).get("status") or "error"
        pts = (out or {}).get("points") or []
        if status == "error":
            extra = (out or {}).get("error")
            msg = self.tr("Survey download failed")
            if extra:
                msg += " — " + str(extra)
            self.statusBar().showMessage(msg, 10000)
            self._build_project_page(project.get(db, pid))
            return
        if not pts:
            self.statusBar().showMessage(
                self.tr("No survey data for this position"), 8000)
            return
        try:
            res = fu.upsert_survey_points(db, pid, pts)
        except ValueError as err:      # wrong project kind
            self.statusBar().showMessage(
                self.tr("Cannot store survey points: %1")
                .replace("%1", str(err)), 10000)
            return
        mjds = [p["mjd"] for p in pts if p.get("mjd") is not None]
        bands = sorted({p.get("filter") or "Clear" for p in pts})
        msg = (self.tr("Survey data (ZTF via ALeRCE): %1 new, %2 updated, "
                       "%3 unchanged, %4 removed; MJD %5 → %6; bands %7")
               .replace("%1", str(res["added"]))
               .replace("%2", str(res["updated"]))
               .replace("%3", str(res["unchanged"]))
               .replace("%4", str(res["removed"]))
               .replace("%5", f"{min(mjds):.1f}")
               .replace("%6", f"{max(mjds):.1f}")
               .replace("%7", ", ".join(bands)))
        self.statusBar().showMessage(msg, 15000)
        # rebuild the page so the curve/points update in place
        self._build_project_page(project.get(db, pid))

    def _sn_add_step_row(self, layout, filt="Clear", n=30, exp=60.0):
        # B8: add a filter×N×exp row to the SN multi-filter step list.
        row = QHBoxLayout()
        cmb = QComboBox()
        cmb.setEditable(True)
        cmb.addItems(["Clear", "V", "R", "G", "B", "I", "NIR", "L"])
        cmb.setCurrentText(filt)
        row.addWidget(cmb)
        spn_n = PassiveSpinBox()
        spn_n.setMinimum(1); spn_n.setMaximum(999)
        spn_n.setValue(n)
        row.addWidget(spn_n)
        spn_e = PassiveDoubleSpinBox()
        spn_e.setMinimum(0.1); spn_e.setMaximum(3600.0)
        spn_e.setValue(exp)
        row.addWidget(spn_e)
        btn_del = QPushButton("✕")
        btn_del.setFixedWidth(28)
        btn_del.setProperty("compact", True)   # see ufe_compare_tab
        entry = {"cmb": cmb, "spn_n": spn_n, "spn_e": spn_e,
                    "row": row, "btn_del": btn_del}
        btn_del.clicked.connect(lambda checked, e=entry: self._sn_del_step_row(e))
        self._sn_steps.append(entry)
        layout.addLayout(row)

    def _sn_del_step_row(self, entry):
        # B8: remove a multi-filter step row.
        layout = entry["row"].parentLayout()
        for w in (entry["cmb"], entry["spn_n"], entry["spn_e"],
                    entry["btn_del"]):
            layout.removeWidget(w)
            w.deleteLater()
        self._sn_steps.remove(entry)

    def _sn_collect_steps(self):
        # B8: gather (filter, n, exp) tuples from the multi-filter rows.
        # @return: list of (filter, n, exp) tuples
        steps = []
        for e in self._sn_steps:
            filt = e["cmb"].currentText().strip() or "Clear"
            steps.append((filt, e["spn_n"].value(), e["spn_e"].value()))
        return steps

    def _project_export_sequence(self):
        if not self._current_project:
            return
        spn = self._project_widgets.get("spn_nframes")
        spn_exp = self._project_widgets.get("spn_exps")
        cmb_f = self._project_widgets.get("cmb_filter")
        spn_darks = self._project_widgets.get("spn_darks")
        spn_darkexp = self._project_widgets.get("spn_darkexp")
        spn_bias = self._project_widgets.get("spn_bias")
        if not (spn and spn_exp and cmb_f and spn_darks
                and spn_darkexp and spn_bias):
            return
        n_darks = spn_darks.value()
        # B8: SN multi-filter plans use the step rows; other kinds use the
        # legacy single-filter fields.
        steps = None
        if self._current_project["kind"] in ("sn", "variable") \
                and self._sn_steps:
            steps = self._sn_collect_steps()
            # total n_frames for the plan dict (sum of per-step counts)
            n_total = sum(n for _f, n, _e in steps)
            plan = sequence.make_plan(
                n_total, steps[0][2], steps[0][0], cfg=config,
                n_darks=n_darks,
                exp_dark=spn_darkexp.value() if n_darks else None,
                n_bias=spn_bias.value(), steps=steps)
        else:
            plan = sequence.make_plan(
                spn.value(), spn_exp.value(), cmb_f.currentText(), cfg=config,
                n_darks=n_darks,
                exp_dark=spn_darkexp.value() if n_darks else None,
                n_bias=spn_bias.value())
        ctx = self._current_project.get("context") or {}
        target = {"name": self._current_project["object_name"],
                  "ra_deg": ctx.get("ra_deg"), "dec_deg": ctx.get("dec_deg"),
                  "safe_window": ctx.get("safe_window")}
        # Track D: a transit exports its capture window (baseline included)
        if self._current_project["kind"] == "transit":
            tr = ctx.get("transit") or {}
            target["capture_start"] = tr.get("capture_start")
            target["capture_end"] = tr.get("capture_end")
        # HADS: the 2P session starting at the recommended (horizon-safe)
        # time — advisory only: any contiguous 2P run inside the safe span
        # works, nothing is mandatory here (ADR-034)
        if self._current_project["kind"] == "hads":
            h = ctx.get("hads") or {}
            bt = ctx.get("best_time")
            if bt and h.get("session_req_h"):
                try:
                    start = datetime.datetime.fromisoformat(str(bt))
                    target["capture_start"] = start
                    target["capture_end"] = start + datetime.timedelta(
                        hours=float(h["session_req_h"]))
                    target["capture_advisory"] = True
                except (TypeError, ValueError):
                    pass
        fmt_map = {0: "ccdciel", 1: "nina", 2: "csv"}
        fmt = fmt_map[self._project_widgets["cmb_seqfmt"].currentIndex()]
        ext = {"nina": ".json", "ccdciel": ".targets", "csv": ".csv"}[fmt]
        outdir = project.storage_dir(self._current_project)
        default = outdir / f"{target['name']}_sequence{ext}"
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export capture sequence"), str(default),
            f"*{ext};;All files (*)")
        if not out:
            return
        try:
            path = sequence.export(target, plan, out, fmt=fmt)
            project.add_file(db, self._current_project["id"], path, "sequence")
            msg = self.tr("Written to %1").replace("%1", path)
            if fmt == "ccdciel" \
                    and self._current_project["kind"] == "transit":
                # Track D: MandatoryStartTime is best-effort until checked
                # against the observatory's real CCDciel (ADR-021)
                msg += " · " + self.tr(
                    "transit start written as mandatory — validate once "
                    "against your CCDciel")
            if fmt == "ccdciel" \
                    and self._current_project["kind"] == "hads":
                # ADR-034: the 2P window is advisory — any contiguous run
                # of two periods inside the safe span captures the science
                msg += " · " + self.tr(
                    "HADS window is advisory — any contiguous 2-period run "
                    "inside the safe span works")
            self.statusBar().showMessage(msg, 8000)
        except OSError as err:
            self.statusBar().showMessage(
                self.tr("Export failed: %1").replace("%1", str(err)), 8000)

    def _project_export_ephem(self):
        if not self._current_project:
            return
        ctx = self._current_project["context"]
        obj_id = (ctx.get("id") or ctx.get("packed")
                  or self._current_project["object_name"])

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Export ephemeris"))
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(self.tr("Format:")))
        combo = QComboBox()
        combo.addItem(self.tr("MPC elements (MPOrbit)"), "mpx")
        combo.setItemData(0, self.tr(
            "One MPOrbit element line per object (the universal MPC "
            "elements handover format), importable by any planetarium or "
            "orbit reader. Best for orbit handover."), Qt.ToolTipRole)
        combo.addItem(self.tr("MPC orbit report"), "fo")
        combo.setItemData(1, self.tr(
            "Orbital elements, perihelion, P/Q, state vector, MOIDs, "
            "Tisserand, encounter speed, diameter and an MPC element "
            "footer. Universal: importable by any planetarium or orbit "
            "reader. Best for a readable follow-up report."), Qt.ToolTipRole)
        layout.addWidget(combo)
        chk_force = QCheckBox(self.tr("Force fresh data (bypass cache)"))
        chk_force.setToolTip(self.tr(
            "Re-query JPL SBDB / NEOfixer now instead of using the cached "
            "orbit. Use after the MPC has improved the preliminary orbit."))
        layout.addWidget(chk_force)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if not dlg.exec():
            return
        fmt = combo.currentData()
        force = chk_force.isChecked()

        outdir = project.storage_dir(self._current_project)
        base = obj_id
        if fmt == "fo":
            ext, default_name = ".txt", f"{base}_orbit_report.txt"
        else:
            ext, default_name = ".txt", f"{base}_elements.txt"
        default = outdir / default_name
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export ephemeris"), str(default),
            f"*{ext};;All files (*)")
        if not out:
            return

        try:
            packed = ctx.get("packed")
            if fmt == "fo":
                path = ephemeris.export_fo_report(
                    name=obj_id, out=out, packed=packed, force=force)
            else:
                path = ephemeris.export_mpc_elements(
                    name=obj_id, out=out, packed=packed, force=force)
            if not path:
                self.statusBar().showMessage(
                    self.tr("No orbit record for %1").replace("%1", obj_id),
                    8000)
                return
            project.add_file(db, self._current_project["id"], path, "ephemeris")
            self.statusBar().showMessage(
                self.tr("Written to %1").replace("%1", path), 8000)
        except OSError as err:
            self.statusBar().showMessage(
                self.tr("Export failed: %1").replace("%1", str(err)), 8000)

    def _project_post(self):
        if self._current_project:
            self._open_post_dialog(self._current_project["object_name"])

    def _project_archive(self):
        if not self._current_project:
            return
        if QMessageBox.question(
                self, self.tr("Archive project"),
                self.tr("Archive this project? You can reopen it later."),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        project.set_status(db, self._current_project["id"],
                           project.STATUS_ARCHIVED)
        self.on_refresh_projects()

    def _project_toggle_favorite(self):
        # A3: star toggle in the header — marks the project as favorite.
        if not self._current_project:
            return
        pid = self._current_project["id"]
        fav = not self._current_project.get("favorite")
        project.set_favorite(db, pid, fav)
        self.on_refresh_projects()

    def _project_filters_toggled(self, checked):
        # UX-PC (U1): the advanced filters row (type/tag/campaign/sort/
        # favorites) collapses behind the Filters ▸ toggle; the choice is
        # remembered across sessions.
        # @args: checked - the toggle state
        # @return: None
        self.projects.filters_box.setVisible(checked)
        self.projects.btn_filters.setText(
            self.tr("Filters ▾") if checked else self.tr("Filters ▸"))
        config.set("projects_filters_open", checked)

    def _toggle_project_list(self, visible):
        # UX-i: the list column is a luxury, not the point — « folds it
        # away so the project page gets the full width, » brings it back.
        # The choice sticks for the next sessions.
        # @args: visible - show or hide the list pane
        # @return: None
        self.projects.grp_list.setVisible(visible)
        self.projects.btn_show_list.setVisible(not visible)
        config.set("projects_list_hidden", int(not visible))

    def _rebuild_manage_menu(self):
        # UX-PC (U1): the ⋯ menu in the project header is the single home
        # of project management — tags, folder and the whole lifecycle.
        # Rebuilt on every open so Close/Reopen follow the live state.
        # @return: None
        menu = self.projects.btn_manage.menu()
        menu.clear()
        p = self._current_project
        if not p:
            menu.addAction(self.tr("(no project selected)")).setEnabled(False)
            return
        act_tags = menu.addAction(self.tr("Edit tags…"))
        act_tags.triggered.connect(self._project_edit_tags)
        act_folder = menu.addAction(self.tr("Show in folder"))
        act_folder.triggered.connect(self._open_project_folder)
        act_chfolder = menu.addAction(self.tr("Change folder…"))
        act_chfolder.triggered.connect(self._change_project_folder)
        menu.addSeparator()
        is_active = p["status"] == project.STATUS_ACTIVE
        act_close = menu.addAction(self.tr("Close project…"))
        act_close.setEnabled(is_active)
        act_close.triggered.connect(self._project_close)
        act_reopen = menu.addAction(self.tr("Reopen"))
        act_reopen.setEnabled(not is_active)
        act_reopen.triggered.connect(self._project_reopen)
        act_archive = menu.addAction(self.tr("Archive…"))
        act_archive.setEnabled(is_active)
        act_archive.triggered.connect(self._project_archive)
        act_delete = menu.addAction(self.tr("Delete…"))
        act_delete.triggered.connect(self._project_delete)

    def _project_edit_tags(self):
        # A3 tags editor, UX-PC home: a small prompt from the ⋯ manage
        # menu (comma-separated free text, saved on accept).
        # @return: None
        p = self._current_project
        if not p:
            return
        text, ok = QInputDialog.getText(
            self, self.tr("Edit tags"),
            self.tr("Comma-separated tags:"), QLineEdit.Normal,
            p.get("tags") or "")
        if not ok:
            return
        project.set_tags(db, p["id"], text.strip())
        # refresh the list row (the tag filter may depend on it)
        self.on_refresh_projects()

    def _project_close(self):
        # Close the current active project with an outcome dialog (A2).
        if not self._current_project:
            return
        p = self._current_project
        if p["status"] != project.STATUS_ACTIVE:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Close project"))
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(self.tr("Final outcome:")))
        cmb = QComboBox()
        cmb.setEditable(True)
        # A2: show translated labels, store the key; «Other» = free text
        lang = self._lang()
        outcome_map = {}
        for oc in project.OUTCOMES.get(p["kind"], project.OUTCOME_DEFAULT):
            lbl = _OUTCOME_LABELS.get(oc, {})
            label = lbl.get(lang) or oc
            cmb.addItem(label, oc)
            outcome_map[label] = oc
        cmb.addItem(self.tr("Other (free text)"), "")
        cmb.setCurrentIndex(0)
        lay.addWidget(cmb)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() != QDialog.Accepted:
            return
        # store the key (data), not the translated label; «Other» (data="")
        # falls back to the free text the user typed
        outcome = cmb.currentData()
        if not outcome:
            outcome = cmb.currentText().strip() or None
        project.close(db, p["id"], outcome)
        self.on_refresh_projects()

    def _project_reopen(self):
        # Reopen a closed/archived project (A2). The "un año después" revisita
        # is a real flow — this works from done AND archived.
        if not self._current_project:
            return
        p = self._current_project
        if p["status"] == project.STATUS_ACTIVE:
            return
        project.reopen(db, p["id"])
        self.on_refresh_projects()

    def _project_delete(self):
        if not self._current_project:
            return
        pid = self._current_project["id"]
        if QMessageBox.question(
                self, self.tr("Delete project"),
                self.tr("Delete this project permanently?"),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        project.delete(db, pid)
        self._current_project = None
        self.on_refresh_projects()

    def _create_project(self, target):
        # @args: target - a planner target dict (must carry name/id and kind)
        # @return: the created project dict (with "id"), or None if the kind
        #          is not a valid project kind or the name is missing; the
        #          Explore dialog uses this to decide whether to close
        kind = target.get("kind")
        name = target.get("name") or target.get("id")
        if kind not in project.VALID_KINDS or not name:
            self.statusBar().showMessage(
                self.tr("Cannot create a project for this target"), 6000)
            return None
        ctx = {k: target.get(k) for k in
                ("id", "name", "kind", "mag", "ra_deg", "dec_deg",
                 "max_alt", "safe_max_alt", "max_time", "window_start",
                 "window_end", "safe_window", "best_time",
                 "latest_safe_start", "hours_up", "sn_type", "host",
                 "disc_date",
                 "rate_arcsec_min", "nobs", "moid", "h",
                 "nf_score", "nf_priority", "neocp", "pccp_score",
                  "perihelion_date", "transit", "approach", "hads",
                  "variable", "campaign", "project_id")
                 if target.get(k) is not None}
        p = project.create(db, kind, name, ctx)
        if p:
            self.on_refresh_projects()
            self._goto_tab(TAB_PROJECTS)
            self._select_project_row(p["id"])
            self.statusBar().showMessage(
                self.tr("Project created: %1").replace("%1", name), 8000)
        return p

    def _select_project_row(self, pid):
        # @args: pid - project id
        # @return: True when the hub list holds the project and selects it
        for i in range(self.projects.lst_projects.count()):
            if self.projects.lst_projects.item(i).data(Qt.UserRole) == pid:
                self.projects.lst_projects.setCurrentRow(i)
                return True
        return False

    def _goto_project_by_id(self, pid):
        # Jumps to the Projects hub with this project selected (UX-d).
        # @return: True when the project was found in the list
        self.on_refresh_projects()
        self._goto_tab(TAB_PROJECTS)
        return self._select_project_row(pid)

    def _goto_campaigns(self, cid=None):
        # Jumps to the Campaigns tab, optionally selecting a campaign
        # (the landing spot of every campaign link, UX-d).
        self._goto_tab(TAB_CAMPAIGNS)
        self._refresh_campaigns_tab()
        if cid is not None:
            lst = self.campaigns.lst_campaigns
            for i in range(lst.count()):
                if lst.item(i).data(Qt.UserRole) == cid:
                    lst.setCurrentRow(i)
                    break

    def _campaign_link_clicked(self, url):
        # The project header campaign badge is a link (UX-d).
        if url.startswith("campaign://"):
            self._goto_campaigns(int(url.split("://", 1)[1]))

    def _camp_after_action(self):
        # Refresh both master-detail tabs after any campaign mutation.
        self._refresh_campaigns_tab()
        self.on_refresh_projects()

    def _camp_new(self):
        from .campaigns_dialog import CampaignEditDialog
        if CampaignEditDialog(self, db_obj=db).exec():
            self._camp_after_action()

    def _camp_edit(self):
        # Finished campaigns are editable too (UX, ex U0.4).
        from .campaigns_dialog import CampaignEditDialog
        from ..core import campaign as _camp
        cid = self._selected_campaign_id()
        if cid is None:
            return
        if CampaignEditDialog(self, camp=_camp.get(db, cid),
                              db_obj=db).exec():
            self._camp_after_action()

    def _camp_delete(self):
        # Deletes the campaign after confirmation; its projects keep
        # going (campaign_id -> NULL, migration v7).
        from PySide6.QtWidgets import QMessageBox
        from ..core import campaign as _camp
        cid = self._selected_campaign_id()
        if cid is None:
            return
        c = _camp.get(db, cid)
        ans = QMessageBox.question(
            self, self.tr("Delete campaign"),
            self.tr("Delete the campaign “%1”? Its projects are kept, "
                    "only the link is removed.").replace("%1", c["name"]))
        if ans == QMessageBox.Yes:
            _camp.delete(db, cid)
            self._camp_after_action()

    def _camp_finish(self):
        from ..core import campaign as _camp
        cid = self._selected_campaign_id()
        if cid is not None:
            _camp.finish(db, cid)
            self._camp_after_action()

    def _camp_reopen(self):
        from ..core import campaign as _camp
        cid = self._selected_campaign_id()
        if cid is not None:
            _camp.reopen(db, cid)
            self._camp_after_action()

    def _camp_new_project(self):
        # Creates a project for a new object and links it to the selected
        # campaign (terminology: a campaign member is a *project*; "target"
        # is reserved for tonight's candidates).
        from .campaigns_dialog import NewProjectDialog
        cid = self._selected_campaign_id()
        if cid is None:
            return
        if NewProjectDialog(self, campaign_id=cid, db_obj=db).exec():
            self._camp_after_action()

    def _camp_attach(self):
        # Links an existing active project to the selected campaign.
        # Never silent (UX-e): an empty candidate list says so.
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        from ..core import project
        cid = self._selected_campaign_id()
        if cid is None:
            return
        actives = project.list_projects(db, status="active")
        choices = [p for p in actives if not p.get("campaign_id")]
        if not choices:
            QMessageBox.information(
                self, self.tr("Attach project"),
                self.tr("No active project without a campaign."))
            return
        names = [f"[{p['kind']}] {p['object_name']}" for p in choices]
        sel, ok = QInputDialog.getItem(
            self, self.tr("Attach project"), self.tr("Project:"),
            names, 0, False)
        if ok:
            project.set_campaign(db, choices[names.index(sel)]["id"], cid)
            self._camp_after_action()

    def _camp_detach(self):
        # Unlinks a member of the selected campaign (chosen by name).
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        from ..core import campaign as _camp
        from ..core import project
        cid = self._selected_campaign_id()
        if cid is None:
            return
        members = _camp.projects_of(db, cid, status=None)
        if not members:
            QMessageBox.information(
                self, self.tr("Detach project"),
                self.tr("This campaign has no projects yet."))
            return
        names = [p["object_name"] for p in members]
        sel, ok = QInputDialog.getItem(
            self, self.tr("Detach project"), self.tr("Project:"),
            names, 0, False)
        if ok:
            project.set_campaign(db, members[names.index(sel)]["id"], None)
            self._camp_after_action()

    def _camp_detach_member(self, pid):
        # Detaches one member project straight from the members table.
        from ..core import project
        project.set_campaign(db, pid, None)
        self._camp_after_action()

    def _campaign_member_opened(self, row, _col):
        # Double-click on a member row: open its project in the hub.
        item = self.campaigns.tbl_members.item(row, 0)
        if item is not None and item.data(Qt.UserRole) is not None:
            self._goto_project_by_id(item.data(Qt.UserRole))

    def _campaign_context_menu(self, pos):
        # Right-click on the campaign list (UX-c): the row's actions.
        item = self.campaigns.lst_campaigns.itemAt(pos)
        if item is None or item.data(Qt.UserRole) is None:
            return
        self.campaigns.lst_campaigns.setCurrentItem(item)
        self._open_campaign_menu(
            item, self.campaigns.lst_campaigns.viewport()
            .mapToGlobal(pos))

    def _open_campaign_menu(self, item, global_pos):
        # The campaign context menu body — shared by the plain list and
        # the health cards (one gesture language), with state-aware
        # labels/enablement (UX-PC U5: "Close", not "Finish").
        # @args: item - the row's QListWidgetItem, global_pos - where to
        #        pop the menu
        # @return: None
        from ..core import campaign as _camp
        c = _camp.get(db, item.data(Qt.UserRole))
        is_active = bool(c) and c["status"] == _camp.CAMPAIGN_ACTIVE
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        for label, slot, enabled in (
                (self.tr("Edit…"), self._camp_edit, True),
                (self.tr("Close campaign"), self._camp_finish, is_active),
                (self.tr("Reopen"), self._camp_reopen, not is_active),
                (self.tr("Delete…"), self._camp_delete, True),
                ("SEP", None, True),
                (self.tr("New project in this campaign…"),
                 self._camp_new_project, True),
                (self.tr("Attach project…"), self._camp_attach, True),
                (self.tr("Detach project…"), self._camp_detach, True)):
            if label == "SEP":
                menu.addSeparator()
                continue
            act = menu.addAction(label)
            act.setEnabled(enabled)
            act.triggered.connect(slot)
        menu.exec(global_pos)

    def _camp_close_or_reopen(self):
        # The detail header's lifecycle button (UX-PC U5): one button, the
        # campaign's state decides — Close when active, Reopen when
        # finished (same words as the projects' lifecycle).
        from ..core import campaign as _camp
        cid = self._selected_campaign_id()
        c = _camp.get(db, cid) if cid is not None else None
        if not c:
            return
        if c["status"] == _camp.CAMPAIGN_ACTIVE:
            self._camp_finish()
        else:
            self._camp_reopen()

    def _rebuild_cmore_menu(self):
        # The ⋯ menu of the campaign detail header (UX-PC U5): the
        # secondary project-link actions + delete. Rebuilt on open so it
        # always matches the current selection.
        # @return: None
        menu = self.campaigns.btn_cmore.menu()
        menu.clear()
        if self._selected_campaign_id() is None:
            menu.addAction(
                self.tr("(no campaign selected)")).setEnabled(False)
            return
        for label, slot in (
                (self.tr("New project in this campaign…"),
                 self._camp_new_project),
                (self.tr("Attach project…"), self._camp_attach),
                (self.tr("Detach project…"), self._camp_detach),
                ("SEP", None),
                (self.tr("Delete campaign…"), self._camp_delete)):
            if label == "SEP":
                menu.addSeparator()
                continue
            act = menu.addAction(label)
            act.triggered.connect(slot)

    def _campaign_help(self):
        # The ⓘ next to "New campaign…" (UX-PC U5, plain-language rule):
        # what a campaign IS, with a real example, right where the user
        # meets the concept.
        QMessageBox.information(
            self, self.tr("What is a campaign?"),
            self.tr("A campaign groups the projects of one shared "
                    "observation effort — several nights, several "
                    "observatories, one goal.\n\n"
                    "Example: “T CrB 2026 eruption” (obsSN group) — every "
                    "night you measure T CrB with the same protocol and "
                    "report the results together.\n\n"
                    "A project is one object with its three steps: plan, "
                    "process, publish."))

    def _campaign_signals_help(self):
        # The ⓘ in "Happening now" (U7, plain-language rule): what the
        # icons mean, how to act on a row, and — honest about the data —
        # that this strip never touches the network.
        QMessageBox.information(
            self, self.tr("What do the icons mean?"),
            self.tr("⚡ — something happened in YOUR measurements: an "
                    "outburst or a brightness drop beyond our threshold.\n\n"
                    "⏳ — a predicted extremum is approaching, with a "
                    "countdown (maximum or minimum).\n\n"
                    "👁 — a T CrB / R CrB vigil: the star is moving away "
                    "from its quiescent level in a recent survey.\n\n"
                    "Double-click a row to open its project. This strip "
                    "reads the cache of the last Tonight run — it never "
                    "touches the network."))

    def _campaign_member_menu(self, pos):
        # Right-click on a member row (UX-c): open its project or detach.
        tbl = self.campaigns.tbl_members
        item = tbl.itemAt(pos)
        if item is None:
            return
        row = item.row()
        pid_item = tbl.item(row, 0)
        if pid_item is None or pid_item.data(Qt.UserRole) is None:
            return
        tbl.selectRow(row)
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        act_open = menu.addAction(self.tr("Open project"))
        act_detach = menu.addAction(self.tr("Detach from campaign"))
        chosen = menu.exec(tbl.viewport().mapToGlobal(pos))
        if chosen is act_open:
            self._goto_project_by_id(pid_item.data(Qt.UserRole))
        elif chosen is act_detach:
            self._camp_detach_member(pid_item.data(Qt.UserRole))

    def _goto_active_project(self, name, fallback=None):
        # Jumps to the existing active project that matches `name` (or the
        # fallback's id if it carries one) and selects it in the hub list.
        # Used by "Continue" of the card and by the Explore dialog's
        # "Continue project" button (phase E).
        # @args: name - object name to match, fallback - planner target with
        #         a possible "id" that was recorded when the project was
        #         created (NEOCP/PCCP names and their MPC numbers are not
        #         equal)
        # @return: True if an active project was found and the hub shows it
        candidates = {name}
        if isinstance(fallback, dict):
            for k in ("id", "name"):
                v = fallback.get(k)
                if v:
                    candidates.add(v)
        existing = project.list_projects(db, "active")
        match = next((p for p in existing for c in candidates
                      if p["object_name"] == c), None)
        if not match:
            return False
        self._goto_tab(TAB_PROJECTS)
        return self._select_project_row(match["id"])

    # ---------------- Contextual dialogs (Explore / Post / Blink) --------

    def _tools_explore(self):
        name, ok = QInputDialog.getText(self, self.tr("Explore object"),
                                        self.tr("Object:"))
        if ok and name.strip():
            self._open_explore_dialog(name.strip())

    def _tools_blink(self):
        # ADR-044: with the UFE as default the ad-hoc blink opens in the
        # editor; the classic dialog stays one setting away
        if self._use_ufe():
            self._ufe_open("blink")
            return
        self._open_blink_dialog()

    def _tools_campaigns(self):
        # Campaigns live in their own top-level tab (UX-a; supersedes
        # the modal manager of ADR-035 V-j). Also the hub button.
        self._goto_campaigns()

    def _open_explore_dialog(self, name):
        # E (docs/WORKFLOWS.es.md §7ses, corrected 2026-09-02): the
        # Explore… dialog is the shared ObjectPanel (gui/overview.py)
        # with a single CTA at its bottom — "Create project" /
        # "Continue project" depending on the injected lookup. The old
        # "Create post" button is gone: posts are built inside the
        # project (Publish step) or ad-hoc under Tools.
        # @args: name - object identifier to explore
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Explore — %1").replace("%1", name))
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        panel = self._explore_panel(name)
        area.setWidget(panel)
        # Small first size (loading state only); the real size comes
        # from `panel.ready` via a 0 ms singleShot (so the panels'
        # lazy sizeHints are computed before we read them).
        dlg.resize(720, 540)
        layout = QVBoxLayout(dlg)
        layout.addWidget(area)

        def _fit(_e):
            # Once the panel is ready, fit the dialog to its natural
            # content size so the charts grid and the parameters
            # table fit without visible scroll. The 0 ms pump lets
            # the panels' lazy sizeHints resolve first.
            QTimer.singleShot(0, _apply_fit)

        def _apply_fit():
            from .overview import resize_to_panel_content
            try:
                resize_to_panel_content(dlg, panel)
            except RuntimeError:
                pass

        def _target(nm, fb):
            # build the minimal target dict the project layer needs:
            # the planner fallback (if any) plus the explored name
            t = dict(fb or {})
            t["name"] = nm
            return t

        def _on_create(nm, fb):
            # the CTA said "create a fresh project on this object". `fb`
            # is the planner target (Tonight) or None for an ad-hoc
            # Tools-menu name. PySide6 passes only the declared args.
            # Only close the dialog when the project was really created
            # (UX, U0.2): otherwise the status-bar error would be lost.
            if self._create_project(_target(nm, fb)) is not None:
                dlg.accept()

        def _on_continue(nm, fb):
            # the CTA said "resume the active project". When nothing
            # matches the ad-hoc name (Tools menu), create it — same
            # intent as the card's green "Continue" button. Only close
            # on success (UX, U0.2).
            fb = fb if isinstance(fb, dict) else None
            name_or_id = nm or (fb.get("id") if fb else None)
            ok = self._goto_active_project(name_or_id, fb)
            if not ok:
                ok = self._create_project(_target(nm, fb)) is not None
            if ok:
                dlg.accept()

        panel.project_create.connect(_on_create)
        panel.project_continue.connect(_on_continue)
        panel.ready.connect(_fit)
        # If the worker already finished (cached, or the FakeWorker
        # pattern in tests), the ready signal may fire before this
        # connect — in which case the fit is driven by the next
        # event loop turn below.
        QTimer.singleShot(0, _apply_fit)
        dlg.exec()

    def _explore_panel(self, name):
        # Builds the Explore-dialog flavour of the shared panel and starts
        # loading `name` on it (the window keeps the worker, per D4's rule).
        # @args: name - object identifier
        # @return: the ready-to-show ObjectPanel (already loading `name`)
        fallback = next((t for t, _s, _p, _ph in self._tonight_all
                         if t["id"] == name or t["name"] == name), None)
        def _active_for(nm):
            # phase E — the panel asks us for the active-project lookup.
            # We try the name it gives us, plus the fallback's id/name,
            # because NEOCP/PCCP keep their MPC number as `id` and a
            # different string as `name` (and the project we created
            # stored one of them).
            candidates = {nm} if nm else set()
            if isinstance(fallback, dict):
                for k in ("id", "name"):
                    v = fallback.get(k)
                    if v:
                        candidates.add(v)
            if not candidates:
                return None
            return next((p for p in project.list_projects(db, "active")
                         if p["object_name"] in candidates), None)
        panel = ObjectPanel(loader=self._explore_loader,
                            chart_dir=str(paths.data_dir() / "posts"),
                            for_post=True,
                            project_lookup=_active_for,
                            parent=self)
        panel.explore(name, fallback_target=fallback)
        return panel

    def _explore_loader(self, name, fallback_target=None):
        # @args: name - object identifier, fallback_target - planner target
        # @return: a kept, not-yet-started ExploreWorker
        worker = ExploreWorker(config, name, fallback_target=fallback_target)
        self._keep(worker)
        return worker

    def _render_object_charts(self, e, prefix, outdir=None):
        # Renders every chart the enriched object supports into the posts
        # directory, for the post/publish flow. Thin wrapper over
        # core.post.build_charts (single source of truth).
        # @args: e - enriched dict, prefix - file name prefix (per-flow),
        #         outdir - save folder (defaults to the data dir's posts)
        # @return: dict {chart_key: Path} for the charts actually produced
        from ..core import post
        outdir = Path(outdir) if outdir else paths.data_dir() / "posts"
        outdir.mkdir(parents=True, exist_ok=True)
        charts = post.build_charts(e, outdir, prefix, cfg=config)
        if charts:
            import matplotlib.pyplot as plt
            plt.close("all")
        return charts

    def _open_post_dialog(self, name):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Post — %1").replace("%1", name))
        dlg.resize(700, 560)
        layout = QVBoxLayout(dlg)
        post_w = _load_ui("post_tab")
        layout.addWidget(post_w)
        post_w.edt_object.setText(name)
        # A4: default save folder — the project's own folder when the post
        # comes from a project, the flat posts dir otherwise
        default_folder = str(paths.data_dir() / "posts")
        if self._current_project \
                and self._current_project["object_name"] == name:
            default_folder = str(project.storage_dir(self._current_project))
        post_w.edt_folder.setText(default_folder)
        post_w.btn_folder_browse.clicked.connect(
            lambda: self._dialog_post_browse_folder(post_w))
        post_w.btn_generate.clicked.connect(
            lambda: self._dialog_generate_post(post_w, name))
        post_w.btn_copy_es.clicked.connect(
            lambda: QApplication.clipboard().setText(
                post_w.txt_es.toPlainText()))
        post_w.btn_copy_en.clicked.connect(
            lambda: QApplication.clipboard().setText(
                post_w.txt_en.toPlainText()))
        post_w.btn_copy_tweet.clicked.connect(
            lambda: QApplication.clipboard().setText(
                post_w.txt_tweet.toPlainText()))
        self._dialog_generate_post(post_w, name)
        dlg.exec()

    def _dialog_post_browse_folder(self, post_w):
        # @args: post_w - the post tab widget
        # @return: None; asks for a folder and fills edt_folder
        start = post_w.edt_folder.text().strip() or str(paths.data_dir())
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("Choose the folder for the post files"), start)
        if folder:
            post_w.edt_folder.setText(folder)

    def _dialog_post_folder(self, post_w):
        # @args: post_w - the post tab widget
        # @return: Path of the chosen folder (created if missing)
        folder = post_w.edt_folder.text().strip() or str(paths.data_dir())
        p = Path(folder)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _dialog_generate_post(self, post_w, name):
        post_w.btn_generate.setEnabled(False)
        self.statusBar().showMessage(self.tr("Building drafts…"))
        fallback = next((t for t, _s, _p, _ph in self._tonight_all
                         if t["id"] == name or t["name"] == name), None)
        w = PostWorker(config, name, fallback_target=fallback)
        w.finished.connect(lambda e, r: self._dialog_post_done(post_w, name, e, r))
        self._keep(w)
        w.start()

    def _dialog_post_done(self, post_w, name, e, rendered):
        post_w.btn_generate.setEnabled(True)
        if not rendered:
            post_w.lbl_files.setText(self.tr("Not found: ") + name)
            return
        from ..core import post as post_mod
        # B9: inject the project's follow-up photometry so the light curve
        # can be drawn in the post (the panel does this for the Details tab;
        # the post flow must do it too — the post is the living document)
        if self._current_project \
                and self._current_project["object_name"] == name:
            from ..core import followup as fu
            pts = fu.list_points(db, self._current_project["id"])
            if pts:
                e.setdefault("data", {}).setdefault("followup", {})["points"] = pts
        outdir = self._dialog_post_folder(post_w)
        safe = "".join(c if c.isalnum() or c in "-_" else "_"
                        for c in name)
        charts, resources = {}, {}
        # charts for the post/report, drawn with a stable per-object name so
        # the markdown can reference them (they end up next to the .md)
        try:
            charts = self._render_object_charts(e, f"{safe}_", outdir=outdir)
        except Exception as err:  # charts must never break the post flow
            logger.warning("post charts failed for %s: %s", name, err)
        # previous blink resources for this object already in the folder
        try:
            for f in sorted(outdir.iterdir()):
                n = f.name.lower()
                if not n.startswith(safe.lower() + "_"):
                    continue
                if n.endswith(".gif"):
                    resources.setdefault("gif", f)
                elif n.endswith(".mp4"):
                    resources.setdefault("mp4", f)
                elif n.endswith("_before_after.png"):
                    resources.setdefault("pair", f)
                elif n.endswith("_evo.gif"):
                    resources.setdefault("evo_gif", f)
                elif n.endswith("_evo.mp4"):
                    resources.setdefault("evo_mp4", f)
        except OSError:
            pass
        written = post_mod.save_outputs(rendered, outdir, name, e=e,
                                        charts=charts or None, cfg=config,
                                        resources=resources or None)
        # show the final drafts (with the gallery/resources links) in the tab
        post_w.txt_es.setPlainText(rendered.get("es", ""))
        post_w.txt_en.setPlainText(rendered.get("en", ""))
        post_w.txt_tweet.setPlainText(rendered.get("tweet", ""))
        db.mark_posted(name)
        # A4: register every written file (posts + tweet) in the project,
        # plus charts and resources, and refresh the files list
        if self._current_project \
                and self._current_project["object_name"] == name:
            pid = self._current_project["id"]
            for key, p in written.items():
                if key in ("es", "en", "tweet"):
                    project.add_file(db, pid, str(p), "post")
            for p in charts.values():
                project.add_file(db, pid, str(p), "chart")
            for p in resources.values():
                project.add_file(db, pid, str(p), "chart")
            self._populate_project_files(pid)
        post_w.lbl_files.setText(
            self.tr("Saved to: ") + ", ".join(str(p) for p in written.values()))
        self.statusBar().showMessage(self.tr("Drafts ready"), 5000)

    def _open_blink_dialog(self, sn_name=None, ra=None, dec=None,
                            fits_path=None):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Blink"))
        dlg.resize(1100, 640)
        layout = QVBoxLayout(dlg)
        blink_w = _load_ui("blink_tab")
        layout.addWidget(blink_w)
        if sn_name:
            blink_w.edt_sn_name.setText(sn_name)
        if ra is not None and dec is not None:
            blink_w.chk_manual.setChecked(True)
            blink_w.edt_ra.setEnabled(True)
            blink_w.edt_dec.setEnabled(True)
            blink_w.edt_ra.setText(f"{ra:.5f}")
            blink_w.edt_dec.setText(f"{dec:+.5f}")
        if fits_path:
            blink_w.edt_fits.setText(fits_path)
        blink_w.btn_browse.clicked.connect(
            lambda: self._dialog_blink_browse(blink_w))
        blink_w.btn_prepare.clicked.connect(
            lambda: self._dialog_blink_prepare(blink_w))
        blink_w.chk_manual.stateChanged.connect(
            lambda s: self._dialog_blink_manual(blink_w, s))
        blink_w.btn_auto_stretch.clicked.connect(
            lambda: self._dialog_blink_auto_stretch(blink_w))
        for sld in (blink_w.sld_black, blink_w.sld_white, blink_w.sld_gamma,
                    blink_w.sld_balance, blink_w.sld_fade, blink_w.sld_marker):
            sld.valueChanged.connect(
                lambda: self._dialog_blink_render_soon(blink_w))
        blink_w.chk_marker.stateChanged.connect(
            lambda: self._dialog_blink_render_soon(blink_w))
        blink_w.cmb_zoom.currentIndexChanged.connect(
            lambda: self._dialog_blink_render(blink_w))
        blink_w.btn_balance_auto.clicked.connect(
            lambda: self._dialog_blink_balance_auto(blink_w))
        blink_w.btn_up.clicked.connect(
            lambda: self._dialog_blink_nudge(blink_w, 0.0, 0.5))
        blink_w.btn_down.clicked.connect(
            lambda: self._dialog_blink_nudge(blink_w, 0.0, -0.5))
        blink_w.btn_left.clicked.connect(
            lambda: self._dialog_blink_nudge(blink_w, -0.5, 0.0))
        blink_w.btn_right.clicked.connect(
            lambda: self._dialog_blink_nudge(blink_w, 0.5, 0.0))
        blink_w.btn_gif.clicked.connect(
            lambda: self._dialog_blink_export(blink_w, "gif"))
        blink_w.btn_video.clicked.connect(
            lambda: self._dialog_blink_export(blink_w, "video"))
        blink_w.btn_png.clicked.connect(
            lambda: self._dialog_blink_export(blink_w, "png"))
        self._blink_dialog_widget = blink_w
        dlg.exec()
        self._blink_timer.stop()
        w = getattr(self, "_blink_worker", None)
        if w is not None and w.isRunning():
            try:
                w.progress.disconnect()
                w.finished.disconnect()
            except RuntimeError:
                pass
            self._blink_worker = None

    # ---- blink dialog helpers ----

    def _dialog_blink_browse(self, b):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Choose FITS"), "",
            "FITS (*.fits *.fit *.fts);;All files (*)")
        if path:
            b.edt_fits.setText(path)

    def _dialog_blink_manual(self, b, state):
        b.edt_ra.setEnabled(bool(state))
        b.edt_dec.setEnabled(bool(state))

    def _dialog_blink_manual_coords(self, b):
        if not b.chk_manual.isChecked():
            return None
        try:
            ra = float(b.edt_ra.text().strip().replace(",", "."))
            dec = float(b.edt_dec.text().strip().replace(",", "."))
        except ValueError:
            return None
        if not (0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0):
            return None
        return ra, dec

    def _dialog_blink_prepare(self, b):
        image = b.edt_fits.text().strip()
        if not image:
            b.lbl_blink_status.setText(self.tr("Choose a FITS image first."))
            return
        name = b.edt_sn_name.text().strip()
        ra = dec = None
        if b.chk_manual.isChecked():
            manual = self._dialog_blink_manual_coords(b)
            if manual is None:
                b.lbl_blink_status.setText(
                    self.tr("Manual coordinates invalid"))
                return
            ra, dec = manual
        elif not name:
            b.lbl_blink_status.setText(
                self.tr("Type the supernova name or tick 'Manual coordinates'."))
            return
        b.btn_prepare.setEnabled(False)
        b.lbl_blink_status.setText(self.tr("Reading the FITS image…"))
        w = BlinkWorker(image, sn_name=name or None, ra=ra, dec=dec)
        self._blink_worker = w
        w.progress.connect(lambda msg: b.lbl_blink_status.setText(
            self._txt(msg)))
        w.finished.connect(lambda pair, errors: self._dialog_blink_done(
            b, pair, errors))
        self._keep(w)
        w.start()

    def _dialog_blink_done(self, b, pair, errors):
        b.btn_prepare.setEnabled(True)
        if errors:
            b.lbl_blink_status.setText("⚠ " + self._txt(errors))
            return
        self._blink_pair = pair
        self._blink_nudge = [0.0, 0.0]
        b.lbl_nudge.setText("(0.0, 0.0)")
        for wgt, val in ((b.sld_black, 10), (b.sld_white, 995),
                         (b.sld_gamma, 100), (b.sld_balance, 100),
                         (b.sld_marker, 10), (b.cmb_zoom, 0)):
            wgt.blockSignals(True)
            if hasattr(wgt, "setValue"):
                wgt.setValue(val)
            else:
                wgt.setCurrentIndex(val)
            wgt.blockSignals(False)
        h, w = pair["obs"].shape
        b.lbl_blink_status.setText(
            f"{pair['name']} @ ({pair['ra']:.5f}, {pair['dec']:+.5f}) — "
            f"{pair['ref_label']} · {w}×{h}px")
        if pair.get("flipped"):
            b.lbl_blink_status.setText(
                b.lbl_blink_status.text() + " · " + self.tr("mirrored"))
        self._blink_dialog_widget = b
        self._dialog_blink_render(b)
        if b.chk_blink_live.isChecked():
            self._blink_timer.start(b.spn_interval.value())

    def _dialog_blink_auto_stretch(self, b):
        for sld, val in ((b.sld_black, 10), (b.sld_white, 995),
                         (b.sld_gamma, 100)):
            sld.setValue(val)
        self._dialog_blink_render(b)

    def _dialog_blink_render_soon(self, b):
        self._blink_dialog_widget = b
        self._blink_render_timer.start()

    def _dialog_blink_render(self, b):
        if not self._blink_pair:
            return
        import numpy as np
        from ..viz import blink_view
        black = b.sld_black.value() / 10.0
        white = b.sld_white.value() / 10.0
        gamma = b.sld_gamma.value() / 100.0
        gain = b.sld_balance.value() / 100.0
        pair = self._blink_pair
        ref_f = blink_view.apply_stretch(
            pair["ref"], *blink_view.auto_limits(pair["ref"], black, white),
            gamma)
        obs_f = blink_view.apply_stretch(
            pair["obs"], *blink_view.auto_limits(pair["obs"], black, white),
            gamma)
        ref_f = blink_view.apply_gain(ref_f, gain)
        self._blink_ref8 = self._blink_shift_ref(blink_view.to_uint8(ref_f))
        self._blink_obs8 = blink_view.to_uint8(obs_f)
        zoom = (1, 2, 4)[b.cmb_zoom.currentIndex()]
        disp_ref, disp_obs, sn_disp = self._blink_display_frames(zoom)
        if b.chk_blink_live.isChecked():
            self._blink_pix = (self._blink_pixmap(disp_ref, sn_disp),
                               self._blink_pixmap(disp_obs, sn_disp))
            self._blink_show_dlg(b, self._blink_pix[int(self._blink_phase)])
        else:
            self._blink_timer.stop()
            a = b.sld_fade.value() / 100.0
            mix = ((1.0 - a) * disp_ref + a * disp_obs).astype(np.uint8)
            self._blink_show_dlg(b, self._blink_pixmap(mix, sn_disp))

    def _blink_show_dlg(self, b, pix):
        b.lbl_blink.setPixmap(
            pix.scaled(b.lbl_blink.size(), Qt.KeepAspectRatio,
                       Qt.SmoothTransformation))

    def _dialog_blink_balance_auto(self, b):
        if not self._blink_pair:
            return
        from ..viz import blink_view
        black = b.sld_black.value() / 10.0
        white = b.sld_white.value() / 10.0
        gamma = b.sld_gamma.value() / 100.0
        pair = self._blink_pair
        ref_f = blink_view.apply_stretch(
            pair["ref"], *blink_view.auto_limits(pair["ref"], black, white),
            gamma)
        obs_f = blink_view.apply_stretch(
            pair["obs"], *blink_view.auto_limits(pair["obs"], black, white),
            gamma)
        b.sld_balance.setValue(round(blink_view.auto_gain(ref_f, obs_f) * 100))

    def _dialog_blink_nudge(self, b, dx, dy):
        if not self._blink_pair:
            return
        self._blink_nudge[0] += dx
        self._blink_nudge[1] += dy
        b.lbl_nudge.setText(
            f"({self._blink_nudge[0]:+.1f}, {self._blink_nudge[1]:+.1f})")
        self._dialog_blink_render(b)

    def _dialog_blink_export(self, b, kind):
        if not self._blink_pair or self._blink_ref8 is None:
            return
        pair = self._blink_pair
        # A4: per-project folder when opened from a project, flat posts/ otherwise
        if self._current_project:
            outdir = project.storage_dir(self._current_project)
        else:
            outdir = paths.data_dir() / "posts"
            outdir.mkdir(parents=True, exist_ok=True)
        if kind == "gif":
            out, _ = QFileDialog.getSaveFileName(
                self, self.tr("Export GIF"),
                str(outdir / f"{pair['name']}_blink.gif"), "GIF (*.gif)")
        elif kind == "video":
            out, _ = QFileDialog.getSaveFileName(
                self, self.tr("Export video"),
                str(outdir / f"{pair['name']}_blink.mp4"),
                "MP4 video (*.mp4)")
        else:
            out, _ = QFileDialog.getSaveFileName(
                self, self.tr("Export PNG"),
                str(outdir / f"{pair['name']}_before_after.png"),
                "PNG (*.png)")
        if not out:
            return
        # A4: register the blink export in the project if we came from one
        if self._current_project:
            project.add_file(db, self._current_project["id"], out, "chart")
            self._populate_project_files(self._current_project["id"])
        effect = "blink" if b.rdo_blink.isChecked() else "fade"
        sn = pair["sn_xy"] if b.chk_marker.isChecked() else None
        b.lbl_blink_status.setText(self.tr("Rendering…"))
        # ADR-046: corner boxes, marker look and the N/E compass follow
        # the settings (the legacy previews stay as they were)
        boxes = compass = None
        if config.get("chart_boxes", False):
            from ..core import chart_annotate, fits_meta
            from ..viz import blink_view as _bv
            boxes = _bv.pair_boxes(
                pair, fits_meta.read_meta(pair["image_path"]),
                chart_annotate.site_from_config(config))
            compass = _bv.pair_compass(pair)
        w = BlinkExportWorker(
            kind, self._blink_ref8, self._blink_obs8, sn, out, effect=effect,
            name=pair["name"], ref_label=pair["ref_label"],
            lang=self._lang(),
            observatory=config.get("observatory_name", ""),
            zoom=(1, 2, 4)[b.cmb_zoom.currentIndex()],
            marker_scale=b.sld_marker.value() / 10.0,
            interval_ms=b.spn_interval.value(),
            boxes=boxes,
            marker_style=config.get("marker_style", "ring"),
            compass=compass)
        w.finished.connect(lambda out, err: b.lbl_blink_status.setText(
            self.tr("Written to %1").replace("%1", out) if out else
            self.tr("Export failed: %1").replace("%1", err)))
        self._keep(w)
        w.start()

    def _blink_tick(self):
        if not self._blink_pair or not hasattr(self, "_blink_pix"):
            self._blink_timer.stop()
            return
        self._blink_phase = not self._blink_phase
        pix = self._blink_pix[int(self._blink_phase)]
        b = getattr(self, "_blink_dialog_widget", None)
        if b is not None:
            self._blink_show_dlg(b, pix)

    def _blink_render(self, *_args):
        b = getattr(self, "_blink_dialog_widget", None)
        if b is not None and self._blink_pair:
            self._dialog_blink_render(b)

    def _blink_shift_ref(self, ref8):
        dx, dy = self._blink_nudge
        if dx == 0.0 and dy == 0.0:
            return ref8
        import numpy as np
        from PIL import Image
        im = Image.fromarray(ref8, mode="L")
        im = im.transform(im.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy),
                          fillcolor=0)
        return np.asarray(im)

    def _blink_display_frames(self, zoom):
        import numpy as np
        from ..viz import blink_view
        disp_ref = np.ascontiguousarray(np.flipud(self._blink_ref8))
        disp_obs = np.ascontiguousarray(np.flipud(self._blink_obs8))
        sn = self._blink_pair.get("sn_xy") if self._blink_pair else None
        if sn is None:
            return disp_ref, disp_obs, None
        h = self._blink_obs8.shape[0]
        sn_disp = (sn[0], h - 1 - sn[1])
        disp_ref, _sr = blink_view.crop_zoom(disp_ref, sn_disp, zoom)
        disp_obs, sn_disp = blink_view.crop_zoom(disp_obs, sn_disp, zoom)
        return (np.ascontiguousarray(disp_ref),
                np.ascontiguousarray(disp_obs), sn_disp)

    def _blink_pixmap(self, disp8, sn_disp):
        from PySide6.QtGui import QImage, QPixmap
        h, w = disp8.shape
        img = QImage(disp8.data, w, h, w, QImage.Format_Grayscale8).copy()
        pix = QPixmap.fromImage(img)
        b = getattr(self, "_blink_dialog_widget", None)
        if b is not None and b.chk_marker.isChecked() and sn_disp is not None:
            if 0 <= sn_disp[0] < w and 0 <= sn_disp[1] < h:
                pix = self._blink_draw_marker(pix, sn_disp)
        return pix

    def _blink_draw_marker(self, pix, sn):
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QColor, QPainter, QPen
        b = getattr(self, "_blink_dialog_widget", None)
        scale = (b.sld_marker.value() / 10.0) if b is not None else 1.0
        x, y = sn
        r = 0.06 * min(pix.width(), pix.height()) * scale
        p = QPainter(pix)
        pen = QPen(QColor("#ffb347"))
        pen.setWidth(max(2, round(2 * scale)))
        p.setPen(pen)
        p.drawEllipse(QPointF(x, y), r, r)
        p.drawLine(QPointF(x - 1.6 * r, y), QPointF(x - 0.5 * r, y))
        p.drawLine(QPointF(x + 0.5 * r, y), QPointF(x + 1.6 * r, y))
        p.drawLine(QPointF(x, y - 1.6 * r), QPointF(x, y - 0.5 * r))
        p.drawLine(QPointF(x, y + 0.5 * r), QPointF(x, y + 1.6 * r))
        p.drawText(QRectF(x - 120, y - 2.6 * r, 240, 1.4 * r),
                   Qt.AlignHCenter | Qt.AlignBottom, self._blink_pair["name"])
        p.end()
        return pix

    # ---------------- Solar ----------------

    _SDO_CHANNELS = ["0193", "0304", "0171", "HMII", "HMIB"]

    # both sun pictures share one display size so they compare side by side
    _SUN_IMG_PX = 400

    def on_refresh_sun(self):
        self.solar.btn_refresh_sun.setEnabled(False)
        channel = self._SDO_CHANNELS[self.solar.cmb_channel.currentIndex()]
        w = SunWorker(channel)
        w.finished.connect(self._sun_done)
        self._keep(w)
        w.start()

    def _channel_changed(self):
        self.on_refresh_sun()

    def _sun_done(self, data, img_path, hmi_path):
        self.solar.btn_refresh_sun.setEnabled(True)
        self._last_sun = data             # S2: kept for the social PNG
        self._last_sun_img = img_path
        if img_path:
            self._set_sun_image(img_path)
        lines = []
        if data.get("ssn") is not None:
            ssn = data["ssn"]
            mood = {"es": "actividad moderada" if ssn < 100 else "actividad alta",
                    "en": "moderate activity" if ssn < 100 else "high activity"}
            lines.append(f"• SSN {ssn:.0f} — {self._txt(mood)} "
                         + self.tr("(cycle 25)"))
        if data.get("f107") is not None:
            lines.append(f"• F10.7: {data['f107']:.0f} sfu")
        if data.get("flare_7d"):
            fl = data["flare_7d"]
            lines.append("• " + self.tr("Strongest flare this week: ")
                         + f"{fl['class']}{fl['value']}")
        if data.get("kp") is not None:
            aur = {"possible": {"es": "auroras posibles en latitudes medias",
                                "en": "mid-latitude auroras possible"},
                   "unlikely": {"es": "sin auroras en latitudes medias",
                                "en": "no mid-latitude auroras"}} \
                .get(data.get("aurora"))
            lines.append(f"• Kp {data['kp']:.1f} — {self._txt(aur)}")
        lines.append("• " + self.tr("Numbered active regions: ")
                     + str(data.get("n_regions")))
        self.solar.txt_sun_data.setPlainText("\n".join(lines))
        self._fill_almanac()
        self._draw_sun_map(data.get("regions") or [], hmi_path)

    def on_sky_post(self):
        # ADR-036 S3: the bilingual "sky today" draft — Sun (if loaded)
        # + Moon + dusk planets, ready to copy (narrative.sky_draft).
        from ..core import coords, ephem_minor, narrative
        from .skypost_dialog import SkyPostDialog
        jd = coords.jd_from_datetime(
            datetime.datetime.now(datetime.timezone.utc))
        moon = ephem_minor.moon(jd)
        draft = narrative.sky_draft(getattr(self, "_last_sun", None) or {},
                                    moon, self._planets_at_dusk())
        SkyPostDialog(draft, parent=self).exec()

    def on_render_sun_post(self):
        # ADR-036 S2: today's Sun as a shareable PNG — the panel the CLI
        # (`solar --png`) already produced, now one click from the tab.
        # Written to the posts folder and shown in the chart viewer.
        data = getattr(self, "_last_sun", None)
        if not data:
            self.statusBar().showMessage(
                self.tr("Refresh the Sun first"), 5000)
            return
        from ..viz import sun_panel
        out = paths.data_dir() / "posts" / (
            "sun_" + datetime.date.today().isoformat() + ".png")
        out.parent.mkdir(parents=True, exist_ok=True)
        sun_panel.draw_sun(getattr(self, "_last_sun_img", None), data,
                           out=str(out),
                           watermark=config.get("observatory_name",
                                                "NightScribe"),
                           lang=self._lang())
        self.statusBar().showMessage(
            self.tr("Saved to: %1").replace("%1", str(out)), 8000)
        from .chart_viewer import open_chart
        open_chart(self, str(out), title=self.tr("Sun today"))

    def _set_sun_image(self, img_path):
        from PySide6.QtGui import QPixmap
        pix = QPixmap(img_path)
        s = self._SUN_IMG_PX
        self.solar.lbl_sun_image.setPixmap(
            pix.scaled(s, s, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _draw_sun_map(self, regions, hmi_path=""):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from PySide6.QtGui import QPixmap
        from ..viz import style, sun_panel
        p = paths.data_dir() / "posts" / "_sun_map.png"
        if hmi_path:
            sun_panel.draw_annotated_sun(hmi_path, regions, out=str(p))
            plt.close("all")
        else:
            fig = plt.figure(figsize=(3.4, 3.4), dpi=100)
            style.apply_style()
            ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
            sun_panel._draw_region_map(ax, regions)
            style.save(fig, str(p))
            plt.close(fig)
        s = self._SUN_IMG_PX
        self.solar.lbl_sun_map.setPixmap(
            QPixmap(str(p)).scaled(s, s, Qt.KeepAspectRatio,
                                  Qt.SmoothTransformation))

    def _fill_almanac(self):
        from ..core import coords, ephem_minor
        jd = coords.jd_from_datetime(
            datetime.datetime.now(datetime.timezone.utc))
        m = ephem_minor.moon(jd)
        from . import moon_icon
        # same real-disc phase icon as the Tonight header (replaces emoji)
        self.solar.lbl_moon.setText(
            self.tr("Moon: %1% lit · %2 km · %3 days")
            .replace("%1", f"{m['illum'] * 100:.0f}")
            .replace("%2", f"{m['dist_km']:,.0f}")
            .replace("%3", f"{m['phase_age_days']:.0f}"))
        # ADR-036 S1: the "impact on your night" line — the tab connects its
        # context to the observing plan. The Moon phase now lives in the
        # Moon calendar below, so only the space-weather signal stays here;
        # with no Kp/aurora alert the line is dropped rather than left as a
        # bare "See Tonight" link.
        parts = []
        kp = (getattr(self, "_last_sun", None) or {}).get("kp")
        if kp is not None and kp >= 5:
            parts.append(self.tr(
                "Kp %1 — mid-latitude auroras possible")
                .replace("%1", f"{kp:.1f}"))
        if parts:
            link = ("<a href='tonight://'>"
                    + self.tr("See Tonight →") + "</a>")
            self.solar.lbl_impact.setText(" · ".join(parts) + " — " + link)
            self.solar.lbl_impact.setVisible(True)
        else:
            self.solar.lbl_impact.setText("")
            self.solar.lbl_impact.setVisible(False)
        self.solar.lbl_moon_icon.setPixmap(
            moon_icon.moon_pixmap(m["elong_deg"], 20))
        # the almanac's real "which planets are up tonight" answer: a
        # seven-row table (icon, name, mag, rise, best moment, set)
        self._fill_planets_table()

    def _planets_at_dusk(self):
        # The naked-eye planets above 15° at dusk (Schlyter, pure local
        # maths) — shared by the almanac line and the sky-post draft (S3).
        # @return: ["Venus (mag -4.2, 18°)", ...]
        from ..core import coords, ephem_minor
        window = coords.tonight_window(config.get("lat"), config.get("lon"))
        visible = []
        if window:
            jd_dusk = coords.jd_from_datetime(window[0])
            for name in ("venus", "mars", "jupiter", "saturn", "mercury"):
                p = ephem_minor.planet(name, jd_dusk)
                alt, az = coords.altaz(p["ra"], p["dec"], config.get("lat"),
                                       coords.lst_degrees(jd_dusk,
                                                          config.get("lon")))
                if alt >= 15:
                    visible.append(f"{pretty.name(self._lang(), name)} "
                                   f"(mag {p['mag']}, {alt:.0f}°)")
        return visible

    def _fill_planets_table(self):
        # The almanac's planet table: all seven, the naked-eye five plus
        # Uranus and Neptune. The drawn disc, the magnitude, the rise/set
        # and the best moment come from the *moving* ephemeris (core.coords
        # .planet_rise_set_max_alt), re-evaluated every 5 minutes across
        # tonight's darkness window. A planet that never reaches 15°
        # stays in the table, dimmed — not hidden: all seven are countable.
        # Pure local maths; no network.
        # @return: nothing
        from PySide6.QtGui import QColor, QIcon
        from PySide6.QtWidgets import (QAbstractItemView, QHeaderView,
                                       QTableWidgetItem)
        from ..core import coords, ephem_minor
        from . import planet_icon

        now = datetime.datetime.now(datetime.timezone.utc)
        jd = coords.jd_from_datetime(now)
        lat, lon = float(config.get("lat")), float(config.get("lon"))
        dim_color = QColor("#8a90a6")           # the theme's muted grey

        tbl = self.solar.tbl_planets
        # a quiet, fixed, read-only table with rows in classical order
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionMode(QAbstractItemView.NoSelection)
        tbl.setShowGrid(False)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed)
        tbl.setColumnWidth(0, 28)

        def hm(dt):
            # @return: the UTC clock, or the dash when the case is n/a
            return dt.strftime("%H:%M") if dt else "—"

        def tip_local(dt):
            # tooltip: the same instant on the local clock (system tz)
            if not dt:
                return ""
            return self.tr("{t} UTC  ·  {l} local").format(
                t=dt.strftime("%H:%M"),
                l=dt.astimezone().strftime("%H:%M"))

        headers = ["", self.tr("Planet"), self.tr("Mag"),
                   self.tr("Rise (UTC)"), self.tr("Max (alt · UTC)"),
                   self.tr("Set (UTC)")]
        tbl.setColumnCount(len(headers))
        for c, h in enumerate(headers):
            tbl.setHorizontalHeaderItem(c, QTableWidgetItem(h))
        names = ("mercury", "venus", "mars", "jupiter", "saturn",
                 "uranus", "neptune")
        tbl.setRowCount(len(names))

        for row, name in enumerate(names):
            p = ephem_minor.planet(name, jd)
            arc = coords.planet_rise_set_max_alt(name, lat, lon, now.date())
            dim = arc["max_alt"] is None or arc["max_alt"] < 15.0
            fg = dim_color if dim else None

            def cell(text, tip=""):
                # @return: the row's item, greyed with an explanation when
                #          the planet never gets close to naked-eye range
                it = QTableWidgetItem(text)
                if fg is not None:
                    it.setForeground(fg)
                if tip:
                    it.setToolTip(tip)
                return it

            # rise/set are now searched ±48 h around the darkness window,
            # so an "—" only means an edge the search cannot close: the
            # planet was up (or down) for over two days — never a bare gap.
            # Each dash gets its own plain-language explanation.
            never_up = self.tr(
                "Never above the horizon within two days of tonight")
            up_open_tip = self.tr(
                "Up already two days ago — it never sets from your site")
            down_open_tip = self.tr(
                "Still up two days from now — it never sets from your site")
            rise_tip = (tip_local(arc["rise_utc"]) if arc["rise_utc"]
                        else up_open_tip if arc["open_earlier"]
                        else never_up)
            set_tip = (tip_local(arc["set_utc"]) if arc["set_utc"]
                       else down_open_tip if arc["open_later"]
                       else never_up)
            name_tip = (self.tr("Best {alt}° tonight — below 15°, "
                                "needs optics or a better season")
                        .format(alt=f"{arc['max_alt']:.0f}")
                        if dim and arc["max_alt"] is not None
                        else "")
            max_txt = ("—" if arc["max_alt"] is None else
                       f"{arc['max_alt']:.0f}° · {hm(arc['max_utc'])}")

            icon_it = QTableWidgetItem()
            icon_it.setIcon(QIcon(planet_icon.planet_pixmap(name, 20)))

            tbl.setItem(row, 0, icon_it)
            # proper noun from the shared pretty tables (not .capitalize())
            tbl.setItem(row, 1, cell(pretty.name(self._lang(), name), name_tip))
            tbl.setItem(row, 2, cell(f"{p['mag']:.1f}"))
            tbl.setItem(row, 3, cell(hm(arc["rise_utc"]), rise_tip))
            tbl.setItem(row, 4, cell(max_txt, tip_local(arc["max_utc"])))
            tbl.setItem(row, 5, cell(hm(arc["set_utc"]), set_tip))
        tbl.resizeColumnsToContents()
        tbl.setColumnWidth(0, 28)               # keep the disc column slim

    # ---------------- Sky calendar (SC2, ADR-040) ----------------

    def _skycal_build(self):
        # Builds the «Sky calendar…» dialog once (lazy) and re-homes the
        # old Sun & sky tab handlers onto its content widget — every
        # existing `self.solar.*` handler keeps working unchanged.
        # @return: the SkyCalendarDialog
        if getattr(self, "_skycal", None) is not None:
            return self._skycal
        from .skycal_dialog import SkyCalendarDialog
        content = _load_ui("sky_calendar")
        self.solar = content      # the handlers' old home, dialog-owned now
        dlg = SkyCalendarDialog(content, lang=self._lang(), parent=self)
        # wire the Sun & outreach controls (moved verbatim from the tab)
        content.btn_refresh_sun.clicked.connect(self.on_refresh_sun)
        content.cmb_channel.currentIndexChanged.connect(
            self._channel_changed)
        content.btn_raben.clicked.connect(
            lambda: self._open_url("https://www.raben.com/maps"))
        content.btn_solarmonitor.clicked.connect(
            lambda: self._open_url("https://www.solarmonitor.org"))
        content.btn_sidc.clicked.connect(
            lambda: self._open_url("https://sidc.be/uset"))
        content.lbl_impact.linkActivated.connect(
            lambda _u: self._goto_tab(TAB_TONIGHT))
        content.btn_sun_post.clicked.connect(self.on_render_sun_post)
        content.btn_sky_post.clicked.connect(self.on_sky_post)
        self._skycal = dlg
        return dlg

    def _skycal_fill(self, dlg):
        # Fills the dialog's local-math sections on every open: the 60-day
        # events, the Moon calendar, the week's Galilean windows, and the
        # almanac line (none of this touches the network — the Sun section
        # keeps its own Refresh button).
        from ..core import skyevents
        evs = skyevents.events(float(config.get("lat")),
                               float(config.get("lon")), days=60)
        dlg.fill_events(evs, dlg.content)
        dlg.fill_jupiter_moons(evs, dlg.content,
                               show_unobserved=bool(
                                   config.get("show_sat_moons_unobserved",
                                              False)))
        self._fill_almanac()

    def _tools_skycal(self):
        # Menu Tools → Sky calendar… (ADR-040)
        dlg = self._skycal_build()
        self._skycal_fill(dlg)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ---------------- Unified FITS Editor (ADR-044) ----------------

    def _ufe_build(self):
        # Builds the «FITS editor…» dialog once (lazy) and keeps it alive
        # on self: the observer's plate and stretch survive a close.
        # @return: the UfeDialog
        if getattr(self, "_ufe", None) is not None:
            return self._ufe
        from .ufe_dialog import UfeDialog
        self._ufe = UfeDialog(lang=self._lang(), parent=self)
        return self._ufe

    def _tools_ufe(self):
        # Menu Tools → FITS editor… (ADR-044)
        dlg = self._ufe_build()
        dlg.set_save_hook(None)      # ad-hoc: no project registration
        dlg.set_point_hook(None)     # and no project to save points to
        dlg.set_reset_hooks(None, None)   # and nothing to reset (ADR-047)
        dlg.set_object(None)         # and no stale project object
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _use_ufe(self):
        # @return: True when FITS work opens in the unified editor
        #          (Settings → Development; the classic dialogs stay
        #          reachable for the review period, ADR-044)
        return bool(config.get("ufe_default", True))

    def _ufe_object_from_project(self, p):
        # Everything the project knows about the object, for the UFE:
        # name, sky position, magnitude (planner → VSX max → the last
        # saved sequence) and B-V when the record carries it.
        # @args: p - the project dict
        # @return: {"name", "ra", "dec", "mag", "bv"} (values or None)
        ctx = p.get("context") or {}
        var = ctx.get("variable") or {}
        ra = ctx.get("ra_deg")
        dec = ctx.get("dec_deg")
        if ra is None or dec is None:
            ra = var.get("ra_deg")
            dec = var.get("dec_deg")
        mag = ctx.get("mag")
        if mag is None:
            mag = var.get("max")          # VSX MaxMag: the bright extreme
        if mag is None:
            mag = (ctx.get("sequence") or {}).get("target_mag")
        return {"name": p.get("object_name"), "ra": ra, "dec": dec,
                "mag": mag, "bv": var.get("bv") or ctx.get("bv")}

    def _ufe_open(self, tab, hook_pid=None, obj=None, session_id=None):
        # Shared open path: the persistent dialog, the right tab on
        # stage, the project save hook set or cleared, the point hook set
        # or cleared, and the object attached (or cleared on an ad-hoc
        # open).
        # @args: tab - "blink"|"compare"|"annotate"|"measure", hook_pid -
        #        project id whose written files get registered (and whose
        #        measured points get saved, tab "measure"), or None,
        #        obj - the object dict from _ufe_object_from_project,
        #        session_id - the visit a saved point belongs to, or None
        # @return: the UfeDialog
        dlg = self._ufe_build()
        dlg.set_save_hook(None)
        dlg.set_object(obj)
        if hook_pid is not None:
            dlg.set_save_hook(
                lambda paths, kind, payload:
                self._ufe_save_hook(hook_pid, paths, kind, payload,
                                    session_id=session_id))
            dlg.set_point_hook(
                lambda payload:
                self._ufe_point_hook(hook_pid, session_id, payload))
            # ADR-047: the plate's two resets land on this project's
            # plate row (the open image, resolved by path)
            dlg.set_reset_hooks(
                lambda: self._ufe_reset_state(dlg, hook_pid),
                lambda: self._ufe_reset_points(dlg, hook_pid))
        else:
            dlg.set_point_hook(None)
            dlg.set_reset_hooks(None, None)
        dlg.show_tab({"blink": dlg.tab_blink, "compare": dlg.tab_compare,
                      "annotate": dlg.tab_annotate,
                      "measure": dlg.tab_measure}[tab])
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    # (the object attaches via set_object at the end of _ufe_open; a
    # route that loads a plate re-applies it after the load so the
    # annotate marker lands through the fresh WCS)

    def _ufe_save_hook(self, pid, paths, kind, payload, session_id=None):
        # Files the UFE wrote while opened from a project get registered
        # there, like the legacy dialogs did; a sequence CSV also lands
        # in the project context and its campaign protocol (the legacy
        # default had the checkbox on). ADR-045: opened from a visit, the
        # files land on it.
        # @args: pid - project id, paths - written files, kind - "fits" |
        #        "chart" | "sequence", payload - the tab's extra context,
        #        session_id - the visit the files belong to, or None
        p = project.get(db, pid)
        if not p:
            return
        for path in paths:
            fkind = {"fits": "fits", "chart": "chart",
                     "report": "report"}.get(kind)
            if kind == "sequence":
                fkind = "chart" if payload.get("which") == "png" \
                    else "report"
            try:
                project.add_file(db, pid, path, fkind,
                                 session_id=session_id)
            except Exception as err:
                logger.warning("UFE save registration failed: %s", err)
        self._populate_project_files(pid)
        if kind != "sequence" or payload.get("which") != "csv" \
                or not payload.get("entries"):
            return
        ctx_update = {"sequence": {
            "catalog": payload.get("catalog"),
            "catalog_name": payload.get("catalog_name"),
            "fov_arcmin": payload.get("fov_arcmin"),
            "target_mag": payload.get("target_mag"),
            "entries": payload["entries"], "csv": paths[0]}}
        if payload.get("target_mag") is not None:
            # the magnitude lives in the project from now on (the next
            # prefill finds it at the top level)
            ctx_update["mag"] = payload["target_mag"]
        project.update_context(db, pid, ctx_update)
        # ADR-047: the sequence lands in the OPEN plate's saved state
        # too, merged over whatever it already carries (stretch and
        # measure blocks survive); the open image is the state holder,
        # not the CSV just written. No plate row: nothing to attach to,
        # and no editor open (hook driven from outside): the CSV and the
        # context stand on their own.
        ufe = getattr(self, "_ufe", None)
        if ufe is not None and getattr(ufe, "state", None) is not None:
            plate_row = project.find_file(db, pid, ufe.state.path)
            if plate_row is not None:
                st = ufe.capture_full_state()
                st["saved_at"] = datetime.datetime.now(
                    datetime.timezone.utc).isoformat()
                project.update_file_meta(db, plate_row["id"], {"ufe": st})
        if p.get("campaign_id"):
            from ..core import campaign as _camp
            c = _camp.get(db, p["campaign_id"])
            if c:
                entries = payload["entries"]
                prot = c.get("protocol") or {}
                prot["comp_stars"] = [
                    f"{e['name']} {e['star']['band']} "
                    f"{e['star']['mag']:.2f}" for e in entries]
                _camp.update(db, c["id"], protocol=prot)

    def _ufe_point_hook(self, pid, session_id, payload):
        # A calibrated magnitude from the Measure tab lands in the project
        # as a photometry point with source "measure", under the visit the
        # button came from (ADR-044; replaces the retired quick-look, see
        # ADR-019 section "Análisis rápido"). ADR-047: the point
        # remembers the plate it was measured on, and the plate's
        # working state is saved along with it, so a click on the row
        # later can restore the whole session.
        # @args: pid - project id, session_id - visit or None,
        #        payload - {"mjd", "filter", "mag", "err", "path", ...}
        from ..core import followup as fu
        if not payload or payload.get("mag") is None:
            self.statusBar().showMessage(
                self.tr("Point not saved: no magnitude to record"), 6000)
            return
        if payload.get("mjd") is None:
            self.statusBar().showMessage(
                self.tr("Point not saved: the plate has no observation date"),
                8000)
            return
        # ADR-047: the open plate's registry row, when it has one
        plate = payload.get("path")
        file_row = project.find_file(db, pid, plate) if plate else None
        try:
            fu.add_point(db, pid, float(payload["mjd"]),
                         payload.get("filter") or "Clear",
                         float(payload["mag"]), err=payload.get("err"),
                         source="measure", session_id=session_id,
                         file_id=file_row["id"] if file_row else None)
        except (TypeError, ValueError) as err:
            self.statusBar().showMessage(
                self.tr("Point not saved: %1").replace("%1", str(err)), 8000)
            return
        # and the plate's working state rides along, so "restore in
        # the editor" from the visit window brings it back (ADR-047);
        # the editor is always present when this hook is armed, but the
        # guard keeps hooks driven from outside safe
        ufe = getattr(self, "_ufe", None)
        if file_row is not None and ufe is not None:
            st = ufe.capture_full_state()
            st["saved_at"] = datetime.datetime.now(
                datetime.timezone.utc).isoformat()
            project.update_file_meta(db, file_row["id"], {"ufe": st})
        if file_row is None:
            self.statusBar().showMessage(
                self.tr("Point saved without plate state: this plate "
                        "is not registered in the project."), 8000)
        else:
            self.statusBar().showMessage(
                self.tr("Point saved: {} band, {:.3f} mag").format(
                    payload.get("filter") or "Clear",
                    float(payload["mag"])), 6000)
        # refresh the panel: light curve, visits and campaign summary update
        self._project_selected()

    # ---------------- UFE plate resets (ADR-047) ----------------

    def _ufe_reset_state(self, dlg, pid):
        # The tab already restored the editor's defaults locally (and
        # told the user); here the plate's saved state block is cleared
        # from its project row. No row: nothing was ever saved, and the
        # local reset stands on its own.
        # @args: dlg - the UfeDialog, pid - the project id
        row = project.find_file(db, pid, dlg.state.path)
        if row is None:
            return
        project.update_file_meta(db, row["id"], {"ufe": None})
        self.statusBar().showMessage(
            self.tr("The plate's saved state was cleared."), 6000)

    def _ufe_reset_points(self, dlg, pid):
        # Destructive, confirmed in the tab: the measured points tied
        # to this plate are dropped (they leave the light curve), and
        # the project page refreshes so the curve and the visit show it
        # at once.
        # @args: dlg - the UfeDialog, pid - the project id
        from ..core import followup as fu
        row = project.find_file(db, pid, dlg.state.path)
        if row is not None:
            fu.delete_points_for_file(db, row["id"])
        self._project_selected()

    # ---------------- Observing journal (ADR-036) ----------------

    def _open_journal_dialog(self):
        # Menu Tools → Observing journal… (ADR-036, J2): the derived
        # journal dialog (core/journal.py); entries jump to their project
        # or to Explore.
        from .journal_dialog import JournalDialog
        dlg = JournalDialog(db, lang=self._lang(),
                            on_open_object=self._journal_entry_open,
                            parent=self)
        dlg.exec()

    def _journal_entry_open(self, name, pid):
        # A journal entry jumps to its project (by id when known, else by
        # name), or to Explore when there is none (UX-c/UX-d).
        # @args: name - object name, pid - project id or None
        if pid is not None and self._goto_project_by_id(pid):
            return
        if not self._goto_active_project(name):
            self._open_explore_dialog(name)

    # ---------------- housekeeping ----------------

    def _keep(self, worker):
        from PySide6.QtCore import QTimer
        self._workers.append(worker)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(
            lambda *a: QTimer.singleShot(0, lambda: self._drop(worker)))

    def _drop(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)
