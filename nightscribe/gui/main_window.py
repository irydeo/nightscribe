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

from PySide6.QtCore import (QFile, Qt, Signal, QPropertyAnimation,
                            QEasingCurve, QTimer)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
                                QFormLayout, QGroupBox, QHBoxLayout,
                                QInputDialog, QLabel, QLineEdit,
                                QListWidget, QListWidgetItem, QMainWindow,
                                QMessageBox, QProgressBar,
                                QPushButton, QScrollArea,
                                QSpinBox, QDoubleSpinBox, QComboBox,
                                QCheckBox, QDialogButtonBox, QTextEdit,
                                QVBoxLayout, QWidget, QTableWidgetItem)

from .. import paths
from ..config import config
from ..version import full_version
from ..core import (dates, ephemeris, mpc_report, orbits, project,
                    sequence, suggest)
from ..core.db import db
from . import theme
from .overview import ObjectPanel
from .skeleton import ShimmerRow
from .workers import (BlinkExportWorker, BlinkWorker, CcdcielWorker,
                      ExploreWorker, MpcResolveWorker, PostWorker, SunWorker,
                      TonightWorker)

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent / "ui"

# Three guided steps for every project kind. The old "analyse" step (ADR-019,
# review 2026-08-28) was dropped, and "capture" merged into "plan" (ADR-030,
# 2026-09-06): planning the session and exporting/running it against CCDciel
# is one step — Plan & Captura.
_STEP_KEYS = ("plan", "process", "publish")

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
# Kinds with multi-night photometry follow-up (the tab is kind-agnostic;
# SN-only analysis buttons hide for the others)
# Track V: variables join (V-g: the quick-look engine serves them unchanged)
FOLLOWUP_KINDS = project.FOLLOWUP_KINDS
_STEP_LABELS_ES = {"plan": "Plan & Captura", "process": "Procesado",
                   "publish": "Publicar"}
_STEP_LABELS_EN = {"plan": "Plan & Capture", "process": "Process",
                   "publish": "Publish"}


def _load_ui(name, parent=None):
    # @args: name - .ui file name without extension, parent - widget
    # @return: the loaded widget
    file = QFile(str(UI_DIR / f"{name}.ui"))
    file.open(QFile.ReadOnly)
    widget = QUiLoader().load(file, parent)
    file.close()
    return widget


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
            ("Discovered", "disc"), ("Observed", "obs")],
    "sn": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
           ("SN type", "sn_type"), ("Host galaxy", "host"),
           ("Discovered", "disc"), ("Max alt", "max_alt"), ("Observed", "obs")],
    "comet": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
               ("Perihelion", "perihelion"), ("Max alt", "max_alt"),
               ("Best time (UTC)", "best_time"), ("Observed", "obs")],
    "pccp": [("Object", "name"), ("Score", "score"), ("PCCP score", "pccp"),
             ("Mag", "mag"), ("Arc (days)", "arc"), ("NObs", "nobs"),
             ("Max alt", "max_alt"), ("Observed", "obs")],
    "transit": [("Object", "name"), ("Score", "score"),
                ("Star mag", "mag"), ("Window (UTC)", "window"),
                ("Depth", "depth"), ("Max alt", "max_alt"),
                ("Observed", "obs")],
    "hads": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
             ("Period", "period"), ("Amp", "amp"), ("Cycles", "cycles"),
             ("Max alt", "max_alt"), ("Best time (UTC)", "best_time"),
             ("Observed", "obs")],
    "variable": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
                 ("Period (d)", "vperiod"), ("Next extremum", "vext"),
                 ("Campaign", "camp"), ("Max alt", "max_alt"),
                 ("Best time (UTC)", "best_time"), ("Observed", "obs")],
    "alert": [("Object", "name"), ("Approach date", "adate"),
              ("Distance (LD)", "ald"), ("Diameter (m)", "adiam"),
              ("Max mag", "amag"), ("Velocity (km/s)", "avel"),
              ("Observed", "obs")],
}
TABLE_COLS_DEFAULT = [("Object", "name"), ("Type", "kind"),
                      ("Campaign", "camp"), ("Score", "score"),
                      ("Mag", "mag"), ("Max alt", "max_alt"),
                      ("Best time (UTC)", "best_time"), ("NEOfixer", "nf"),
                      ("NObs", "nobs"), ("Discovered", "disc"),
                      ("Observed", "obs")]

# Canonical kind order (theme.KIND_LABELS order, ADR-026): the tonight filter
# combo and the settings whitelist stay in the same order wherever shown.
KIND_ORDER = ["neo", "sn", "comet", "pccp", "transit", "alert", "hads",
              "variable"]

# Top-level tab indices (ui/main_window.ui order, UX track): never
# use literals for the main tabs.
TAB_TONIGHT, TAB_PROJECTS, TAB_CAMPAIGNS, TAB_SOLAR, TAB_OBSERVATORY, \
    TAB_HISTORY = range(6)


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
    # UX v3.1: four tabs — Tonight (suggestion grid) · Projects (step tabs)
    # · Solar · History. Contextual dialogs for Explore/Post/Blink.

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
        self._proj_panel = None   # reusable ObjectPanel (phase D4), lazy
        self._page_sections = {}  # key -> CollapsibleSection of the project page
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
        from PySide6.QtCore import QLocale
        lang = config.get("language", "system")
        if lang == "system":
            lang = QLocale.system().name()[:2]
        return lang if lang in ("es", "en") else "en"

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
        widgets = (self.tonight, self.projects, self.campaigns,
                   self.solar, self.observatory, self.history) = (
            _load_ui("tonight_tab"), _load_ui("projects_tab"),
            _load_ui("campaigns_tab"), _load_ui("solar_tab"),
            _load_ui("observatory_tab"), _load_ui("history_tab"))
        for i, w in enumerate(widgets):
            title = tabs.tabText(i)
            tabs.removeTab(i)
            tabs.insertTab(i, w, title)
        tabs.setCurrentIndex(0)
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
        self.projects.cmb_sort.setCurrentIndex(
            int(config.get("projects_filter_sort", 0)))
        self.projects.chk_favorites.setChecked(
            bool(config.get("projects_filter_fav", False)))
        # window-owned Observatory tab: build its controls once (UX, UD.2)
        self._build_observatory_tab()

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
        # tab, so it is always up to date without pressing "Refresh" (which
        # stays as a just-in-case fallback).
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
        p.btn_refresh.clicked.connect(self.on_refresh_projects)
        p.cmb_filter.currentIndexChanged.connect(self.on_refresh_projects)
        p.btn_campaigns.clicked.connect(self._tools_campaigns)
        p.cmb_campaign.currentIndexChanged.connect(
            lambda _i: self.on_refresh_projects())
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
        # UX-d: the project header campaign badge is a link to the tab
        self.projects.lbl_header.linkActivated.connect(
            self._campaign_link_clicked)
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
        c.btn_new.clicked.connect(self._camp_new)
        c.btn_edit.clicked.connect(self._camp_edit)
        c.btn_delete.clicked.connect(self._camp_delete)
        c.btn_finish.clicked.connect(self._camp_finish)
        c.btn_reopen.clicked.connect(self._camp_reopen)
        c.btn_add_target.clicked.connect(self._camp_add_target)
        c.btn_attach.clicked.connect(self._camp_attach)
        c.btn_detach.clicked.connect(self._camp_detach)
        # U0.2: itemSelectionChanged is not re-emitted for the row that
        # is already selected, so a click on it used to be a no-op. It
        # now retries the detail load (e.g. after a failed enrich).
        p.lst_projects.itemClicked.connect(self._project_reclicked)
        p.btn_archive.clicked.connect(self._project_archive)
        p.btn_delete.clicked.connect(self._project_delete)
        p.btn_close.clicked.connect(self._project_close)
        p.btn_reopen.clicked.connect(self._project_reopen)
        p.cmb_kind.currentIndexChanged.connect(self.on_refresh_projects)
        p.edt_search.textChanged.connect(self.on_refresh_projects)
        p.edt_tag.textChanged.connect(self.on_refresh_projects)
        p.cmb_sort.currentIndexChanged.connect(self.on_refresh_projects)
        p.chk_favorites.stateChanged.connect(self.on_refresh_projects)
        # A3: favorite star toggle + tags editor in the project header
        p.btn_favorite.clicked.connect(self._project_toggle_favorite)
        p.btn_next_go.clicked.connect(
            lambda: self._scroll_to_section(self._next_target))
        p.edt_tags.editingFinished.connect(self._project_tags_edited)
        # A2: click on the advisor banner dismisses it for this session
        self._advisor_dismissed = None
        self.projects.lbl_advisor.mouseReleaseEvent = \
            lambda _e: self._advisor_dismiss()
        self.projects.lbl_advisor.setCursor(Qt.PointingHandCursor)
        self.solar.btn_refresh_sun.clicked.connect(self.on_refresh_sun)
        self.solar.cmb_channel.currentIndexChanged.connect(self._channel_changed)
        self.solar.btn_raben.clicked.connect(
            lambda: self._open_url("https://www.raben.com/maps"))
        self.solar.btn_solarmonitor.clicked.connect(
            lambda: self._open_url("https://www.solarmonitor.org"))
        self.solar.btn_sidc.clicked.connect(
            lambda: self._open_url("https://sidc.be/uset"))
        self.history.btn_refresh_hist.clicked.connect(self.on_refresh_history)
        # UX-c/UX-d: the history rows are links to their project (or to
        # Explore when there is none), and Ctrl+1..6 switches main tabs.
        self.history.tbl_history.cellDoubleClicked.connect(
            self._history_open)
        self.history.tbl_history.viewport().setCursor(
            Qt.PointingHandCursor)
        self.history.tbl_history.setToolTip(
            self.tr("Double-click a row to open its project or explore "
                    "the object"))
        from PySide6.QtGui import QKeySequence, QShortcut
        for i, tab_idx in enumerate((TAB_TONIGHT, TAB_PROJECTS,
                                     TAB_CAMPAIGNS, TAB_SOLAR,
                                     TAB_OBSERVATORY, TAB_HISTORY)):
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
        dlg.cmb_camera_type.addItems(["CCD", "CMOS", "DSLR"])
        dlg.cmb_camera_type.setCurrentText(config.get("camera_type", "CCD"))
        dlg.cmb_binning.addItems(["1x1", "2x2", "3x3"])
        dlg.cmb_binning.setCurrentText(config.get("pixel_binning", "1x1"))
        dlg.edt_horizon_file.setText(config.get("horizon_file", ""))
        dlg.spn_horizon_margin.setValue(
            float(config.get("horizon_margin_deg", 0)))
        dlg.chk_moon_enabled.setChecked(bool(config.get("moon_limit_enabled",
                                                        True)))
        dlg.spn_moon_sep.setValue(float(config.get("moon_min_sep_deg", 45)))
        dlg.spn_moon_illum.setValue(float(config.get("moon_max_illum", 0.5)))
        dlg.spn_overhead.setValue(float(config.get("overhead_s", 15)))
        dlg.spn_sn_cadence.setValue(int(config.get("sn_cadence_days", 3)))
        dlg.spn_event_mag.setValue(
            float(config.get("event_mag_threshold", 0.5)))
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
        config.set("camera_type", dlg.cmb_camera_type.currentText())
        config.set("pixel_binning", dlg.cmb_binning.currentText().strip()
                   or "1x1")
        config.set("horizon_file", dlg.edt_horizon_file.text().strip())
        config.set("horizon_margin_deg", dlg.spn_horizon_margin.value())
        config.set("moon_limit_enabled", dlg.chk_moon_enabled.isChecked())
        config.set("moon_min_sep_deg", dlg.spn_moon_sep.value())
        config.set("moon_max_illum", dlg.spn_moon_illum.value())
        config.set("overhead_s", dlg.spn_overhead.value())
        config.set("sn_cadence_days", dlg.spn_sn_cadence.value())
        config.set("event_mag_threshold", dlg.spn_event_mag.value())
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
            "campaigns": self.tr("Checking campaign targets…"),
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
                self.tr("Due for a revisit — click to open its "
                        "Follow-up"))
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
        # Opens the project's Follow-up section (the cadence chips land
        # here, UX-d). The section is expanded, not navigated by index.
        if not self._goto_project_by_id(pid):
            return
        self._scroll_to_section("followup")

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
        ring_css = " border: 1px solid #5a6478;" if ring else ""
        row.setStyleSheet(
            f"QFrame#tonightrow {{ background: {theme.C_BASE}"
            f" border-radius: 8px;{ring_css} }}"
            f"QFrame#tonightrow:hover {{ background: #1a1f30; }}")
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
        lbl_icon.setStyleSheet(f"background: {kind_color}18; border-radius: 6px;")
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
            label = nf.capitalize()
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
            return "✔" if db.is_observed(t["id"]) else ""
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
                if show_obs or not db.is_observed(x[0]["id"])]
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
        # Refills the single campaign list (UX-g: finished ones dimmed
        # and suffixed), keeping the selection. Each row carries the
        # health summary from status_report (UX-b).
        from ..core import campaign as _camp
        lst = self.campaigns.lst_campaigns
        sel = lst.currentItem()
        keep_id = sel.data(Qt.UserRole) if sel is not None else None
        lst.clear()
        for c in _camp.list_campaigns(db):
            rep = _camp.status_report(db, c["id"])
            members = rep["members"] if rep else []
            due = sum(1 for m in members if m["due"])
            text = c["name"]
            if c.get("group_name"):
                text += f"  ({c['group_name']})"
            text += "  —  " + self.tr("%1 targets · %2 due")\
                .replace("%1", str(len(members))).replace("%2", str(due))
            if any(m.get("event") for m in members):
                text += "  ⚡"
            if c["status"] == _camp.CAMPAIGN_FINISHED:
                text += "  " + self.tr("(finished)")
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, c["id"])
            if c["status"] == _camp.CAMPAIGN_FINISHED:
                item.setForeground(QColor(theme.C_TEXT_DIM))
            lst.addItem(item)
            if c["id"] == keep_id:
                lst.setCurrentItem(item)
        if lst.count() == 0:
            self._campaign_selected()     # clears the detail side

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
            w.lbl_cname.setText(self.tr("Select a campaign."))
            w.lbl_cmeta.setText("—")
            w.lbl_cgoal.setText("")
            w.lbl_urls.setText("")
            w.lbl_protocol.setText("—")
            tbl.setRowCount(0)
            tbl.setColumnCount(0)
            return
        c = rep["campaign"]
        w.lbl_cname.setText(c["name"])
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
        orders = ("updated", "created", "name")
        order = orders[sort_idx] if sort_idx < len(orders) else "updated"
        favorites = self.projects.chk_favorites.isChecked()
        # persist the prefs (pattern of WORKFLOWS 7quater)
        config.set("projects_filter_kind", kind_idx)
        config.set("projects_filter_sort", sort_idx)
        config.set("projects_filter_fav", favorites)
        config.set("projects_filter_campaign", camp_id or "")
        projects_list = project.list_projects(
            db, status, kind=kind, search=search, tags=tag,
            campaign_id=camp_id,
            favorites_first=favorites, order=order)
        from ..core import campaign as _camp
        camp_names = {c["id"]: c["name"] for c in _camp.list_campaigns(db)}
        lst = self.projects.lst_projects
        # preserve the selected project across the refresh (the list reloads
        # on every visit to the tab and at startup, so we must not drop the
        # project the user is currently viewing)
        sel = lst.currentItem()
        keep_id = sel.data(Qt.UserRole) if sel is not None else None
        lst.clear()
        # A3: group by year of created (section headers, non-selectable)
        last_year = None
        for p in projects_list:
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
            lst.addItem(item)
            if p["id"] == keep_id:
                lst.setCurrentItem(item)
        if not projects_list:
            self.projects.lbl_header.setText(
                self.tr("No projects yet. Create one from Tonight."))
            self.projects.lbl_context.setText("—")
            self._reset_proj_panel()
            self._clear_project_page()
            self._current_project = None
        # the Observatory tab's target combo follows the active projects
        self._refresh_obs_targets()

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
        p = self._current_project
        if not p:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        act_open = menu.addAction(self.tr("Open"))
        act_fu = menu.addAction(self.tr("Follow-up"))
        act_fu.setEnabled(p["kind"] in FOLLOWUP_KINDS)
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
        chosen = menu.exec(
            self.projects.lst_projects.viewport().mapToGlobal(pos))
        if chosen is act_open:
            self._project_open_activated(item)
        elif chosen is act_fu:
            self._scroll_to_section("followup")
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

    def _ensure_proj_files_list_section(self, det):
        # A4: lazily build the project files list inside the Object card
        # section (UX-i): same content as before, re-targeted at the
        # section layout instead of the old Details tab.
        if getattr(self, "_proj_files_list", None) is None:
            from .widgets.collapsible_section import CollapsibleSection
            sec = CollapsibleSection(self.tr("Project files"))
            self._proj_files_list = QListWidget()
            self._proj_files_list.itemDoubleClicked.connect(
                self._open_project_file)
            sec.setContentWidget(self._proj_files_list)
            # A4: "Show in folder" button (opens the file's parent folder)
            btn_folder = QPushButton(self.tr("Show in folder"))
            btn_folder.clicked.connect(self._open_project_folder)
            sec.contentLayout().addWidget(btn_folder)
            # ADR-032: re-home the project's container folder (future
            # exports only; registered files keep their absolute paths)
            btn_ch_folder = QPushButton(self.tr("Change folder…"))
            btn_ch_folder.clicked.connect(self._change_project_folder)
            sec.contentLayout().addWidget(btn_ch_folder)
            sec.setCollapsed(True)
            det.addWidget(sec)
            self._proj_files_section = sec

    def _populate_project_files(self, pid):
        # A4: refresh the files list in the Details tab from project_files.
        lst = getattr(self, "_proj_files_list", None)
        if lst is None:
            return
        lst.clear()
        for f in project.list_files(db, pid):
            name = Path(f["path"]).name
            dt = datetime.datetime.fromtimestamp(f["created"])
            item = QListWidgetItem(
                f"[{f['kind']}] {name}  ({dt.strftime('%Y-%m-%d')})")
            item.setData(Qt.UserRole, str(f["path"]))
            lst.addItem(item)
        sec = getattr(self, "_proj_files_section", None)
        if sec is not None and lst.count() > 0:
            sec.setCollapsed(True)

    def _open_project_file(self, item):
        # A4: double-click a file row to open it with the OS default.
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        path = item.data(Qt.UserRole)
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _open_project_folder(self):
        # A4: "Show in folder" opens the selected file's parent folder.
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        item = self._proj_files_list.currentItem()
        if item is not None:
            path = item.data(Qt.UserRole)
            if path:
                QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(Path(path).parent)))

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
        if self._proj_panel is None:
            from .overview import ObjectPanel
            panel = ObjectPanel(loader=self._proj_panel_loader)
            self._proj_panel = panel
        return self._proj_panel

    def _reset_proj_panel(self):
        # Drops any in-flight worker and empties the panel (used when the
        # selection or the project list goes away).
        if self._proj_panel is not None:
            self._proj_panel.cancel()

    def _clear_project_detail(self):
        # Empties the whole detail side when the selection goes away
        # (closed under the Active filter, filtered out, deleted): header,
        # context, step tabs and the panel worker. Before U0.2 the header
        # and tabs kept showing the vanished project (stale detail).
        self._current_project = None
        self._reset_proj_panel()
        self._clear_project_page()
        self.projects.lbl_header.setText(
            self.tr("Select a project or create one from Tonight."))
        self.projects.lbl_context.setText("—")
        self.projects.lbl_advisor.setVisible(False)

    def _render_project_header(self, p):
        kind_label = {"sn": "Supernova", "neo": "NEO", "comet": "Comet",
                      "pccp": "Possible comet",
                      "transit": "Exoplanet transit",
                      "hads": "HADS", "variable": self.tr("Variable star")
                      }.get(p["kind"], p["kind"])
        cur = project.current_step(db, p["id"])
        step_n = _STEP_KEYS.index(cur) + 1 if cur in _STEP_KEYS else 3
        header = f"<b>[{kind_label}] {p['object_name']}</b>"
        if p.get("closed_at"):
            dt = datetime.datetime.fromtimestamp(p["closed_at"])
            header += f" — <span style='color:#8a90a6'>{self.tr('closed')} {dt.strftime('%Y-%m-%d')}</span>"
            if p.get("outcome"):
                header += f" <span style='color:#8a90a6'>({p['outcome']})</span>"
        else:
            header += f" — {self.tr('step')} {step_n}/3"
        if p.get("campaign_id"):
            from ..core import campaign as _camp
            c = _camp.get(db, p["campaign_id"])
            if c:
                lab = self.tr("campaign")
                header += (" · <a href='campaign://%1' "
                           "style='color:#65cf30; text-decoration:none'>"
                           "⚑ %2: %3</a>").replace(
                               "%1", str(c["id"])).replace(
                               "%2", lab).replace("%3", c["name"])
        self.projects.lbl_header.setText(header)
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
        # A3: favorite star (☆/★) and tags editor in the header
        self.projects.btn_favorite.setText("★" if p.get("favorite") else "☆")
        self.projects.edt_tags.setText(p.get("tags") or "")
        # Button visibility: Close when active, Reopen when done/archived.
        is_active = p["status"] == project.STATUS_ACTIVE
        self.projects.btn_close.setVisible(is_active)
        self.projects.btn_reopen.setVisible(not is_active)
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
        # One collapsible section of the project page (UX-i).
        # @args: key - "details"|"plan"|"process"|"publish"|"followup",
        #        title - the visible header
        # @return: the section's content QLayout (where the per-kind
        #          builders add their widgets, exactly as before)
        from .widgets.collapsible_section import CollapsibleSection
        sec = CollapsibleSection(title)
        page_container = self.projects.page_container
        page_container.layout().addWidget(sec)
        self._page_sections[key] = sec
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        sec.setContentWidget(inner)
        return v

    def _clear_project_page(self):
        # Wipes the project page sections (one rebuild per project
        # selection, same discipline as the old step tabs).
        self._page_sections = {}
        self._wipe_layout(self.projects.page_container.layout())

    def _next_target_key(self, p):
        # @return: the section key the Next card points at
        act = project.next_action(db, p)
        return {"followup": "followup", "plan": "plan",
                "process": "process", "publish": "publish",
                "close": None}.get(act["key"])

    def _refresh_next_card(self, p):
        # Fills the Next card from next_action() (UX-i): one bold line
        # saying what to do, one small line with the steps in words,
        # and the Go button scrolling to the right section.
        # @args: p - the project dict
        # @return: None
        act = project.next_action(db, p)
        texts = {
            "followup": self.tr("Measure tonight — %1 d since the last "
                                "visit").replace(
                "%1", str(act["overdue_days"]))
            if not act["never_visited"] else
            self.tr("First measurement — it opens the series"),
            "plan": self.tr("Plan the capture"),
            "process": self.tr("Process your data"),
            "publish": self.tr("Draft the post"),
            "close": self.tr("All steps done — consider closing the "
                             "project"),
        }
        self.projects.lbl_next.setText("▶ " + texts[act["key"]])
        steps = {s["step"]: s["status"] for s in p.get("steps", [])}
        words = []
        for key in _STEP_KEYS:
            st = steps.get(key, "pending")
            mark = "✔" if st == "done" else "–" if st == "skipped" \
                else "○"
            words.append(f"{mark} {self._step_label(key)}")
        self.projects.lbl_steps_line.setText("  ·  ".join(words))
        target = self._next_target_key(p)
        self._next_target = target
        self.projects.btn_next_go.setVisible(target is not None)

    def _scroll_to_section(self, key):
        # Expands the section and scrolls the page to it (the landing
        # spot of every deep link after UD.4, UX-i).
        # @args: key - section key, e.g. "followup"|"plan"|None
        # @return: None
        if not key or key not in getattr(self, "_page_sections", {}):
            return
        sec = self._page_sections[key]
        sec.setCollapsed(False)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.projects.scroll_page
                          .ensureWidgetVisible(sec))

    def _build_project_page(self, p):
        # The project page (UX-i): one scroll with collapsible
        # sections instead of step tabs + wizard. Same per-kind
        # content builders, new container; the step state shows in
        # words and its toggle lives INSIDE each step section.
        self._clear_project_page()
        kind, ctx = p["kind"], p["context"]
        # section 0: the object card + project files (not a step)
        det = self._section_layout("details", self.tr("Object card"))
        panel = self._get_proj_panel()
        det.addWidget(panel)
        self._ensure_proj_files_list_section(det)
        self._populate_project_files(p["id"])
        # step sections keep the old builders: each one's first line
        # now asks for a section instead of a tab page
        self._build_plan_tab(p, kind, ctx)
        self._build_process_tab(p, kind, ctx)
        self._build_publish_tab(p, kind, ctx)
        if kind in FOLLOWUP_KINDS:
            self._build_followup_tab(p, ctx)
        # the Next card drives which sections start expanded:
        # the next-action section open, the rest collapsed (except details)
        self._refresh_next_card(p)
        target = self._next_target_key(p)
        for key, sec in self._page_sections.items():
            sec.setCollapsed(key not in ("details", target))

    def _step_section(self, key):
        # Builds one step section with its state line + toggle inside
        # (UX-i). @return: the section's content layout
        labels = {"plan": self._step_label("plan"),
                  "process": self._step_label("process"),
                  "publish": self._step_label("publish"),
                  "followup": self.tr("Follow-up")}
        layout = self._section_layout(key, labels[key])
        p = self._current_project
        if p and key in _STEP_KEYS:
            layout.addLayout(self._step_toggle_row(p, key))
        return layout

    def _step_toggle_row(self, p, key):
        # The step's own controls, in words (no more ✔/●/○/– icons):
        # "done on <date>" / "skipped" / pending with its buttons.
        # @args: p - the project dict, key - step key ("plan"|...)
        # @return: the QHBox row to add inside the step section
        row = QHBoxLayout()
        step = next((s for s in p["steps"] if s["step"] == key), None)
        status = step["status"] if step else "pending"
        lbl = QLabel()
        row.addWidget(lbl)
        if status in ("done", "skipped"):
            when = datetime.datetime.fromtimestamp(
                step["updated"]).strftime("%Y-%m-%d") \
                if step and step.get("updated") else ""
            lbl.setText(
                self.tr("✔ done on %1").replace("%1", when)
                if status == "done" else self.tr("– skipped"))
            btn_reopen = QPushButton(self.tr("Reopen step"))
            btn_reopen.setFlat(True)
            btn_reopen.clicked.connect(
                lambda _=False, k=key: self._step_reopen(k))
            row.addWidget(btn_reopen)
        else:
            lbl.setText(self.tr("pending"))
            btn_done = QPushButton(self.tr("Mark done"))
            btn_done.clicked.connect(
                lambda _=False, k=key: self._step_done(k))
            row.addWidget(btn_done)
            btn_skip = QPushButton(self.tr("Skip step"))
            btn_skip.setFlat(True)
            btn_skip.clicked.connect(
                lambda _=False, k=key: self._step_skip(k))
            row.addWidget(btn_skip)
        row.addStretch()
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

    def _step_skip(self, key):
        # Marks the step skipped and rebuilds the page.
        # @args: key - step key
        # @return: None
        project.set_step_status(db, self._current_project["id"], key,
                                project.STEP_SKIPPED)
        p = project.get(db, self._current_project["id"])
        self._current_project = p
        self._build_project_page(p)

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
        spn = QSpinBox(); spn.setMinimum(1); spn.setMaximum(999); spn.setValue(30)
        row.addWidget(spn)
        row.addWidget(QLabel(self.tr("Exposure (s):")))
        spn_exp = QDoubleSpinBox(); spn_exp.setMinimum(0.1)
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
        grp = QGroupBox(self.tr("Calibration"))
        cal_form = QFormLayout(grp)
        spn_darks = QSpinBox(); spn_darks.setMinimum(0); spn_darks.setMaximum(999)
        spn_darks.setValue(25)
        cal_form.addRow(self.tr("Darks:"), spn_darks)
        spn_darkexp = QDoubleSpinBox(); spn_darkexp.setMinimum(0.1)
        spn_darkexp.setMaximum(3600.0)
        spn_darkexp.setValue(spn_exp.value())
        cal_form.addRow(self.tr("Dark exposure (s):"), spn_darkexp)
        spn_bias = QSpinBox(); spn_bias.setMinimum(0); spn_bias.setMaximum(999)
        spn_bias.setValue(100)
        cal_form.addRow(self.tr("Bias:"), spn_bias)
        layout.addWidget(grp)
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
            # multi-filter rows: add/remove (filter × N × exp) steps
            layout.addWidget(QLabel(self.tr("Filters (add rows for multi-band)")))
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
            add_row = QHBoxLayout()
            btn_add_filt = QPushButton(self.tr("Add filter"))
            btn_add_filt.clicked.connect(lambda: self._sn_add_step_row(steps_vlay))
            add_row.addWidget(btn_add_filt)
            steps_vlay.addLayout(add_row)
            layout.addWidget(steps_container)
            self._project_widgets["sn_steps_container"] = steps_container
        # sequence export (all kinds)
        layout.addWidget(QLabel(self.tr("Export capture sequence")))
        cmb_fmt = QComboBox()
        cmb_fmt.addItem(self.tr("CCDciel (targets)"))
        cmb_fmt.addItem(self.tr("NINA (JSON)"))
        cmb_fmt.addItem(self.tr("CSV (generic)"))
        layout.addWidget(cmb_fmt)
        btn_seq = QPushButton(self.tr("Export sequence…"))
        btn_seq.clicked.connect(self._project_export_sequence)
        layout.addWidget(btn_seq)
        # UX-j: connection and mount live in the Observatory tab now; the
        # plan section keeps only its capture buttons + a jump link
        layout.addWidget(QLabel(""))
        btn_ccd_jump = QPushButton(
            self.tr("Not connected — open the Observatory tab →"))
        btn_ccd_jump.setFlat(True)
        btn_ccd_jump.setCursor(Qt.PointingHandCursor)
        btn_ccd_jump.clicked.connect(lambda: self._goto_tab(TAB_OBSERVATORY))
        layout.addWidget(btn_ccd_jump)
        # filter wheel feeding the staged capture plan
        f_row = QHBoxLayout()
        f_row.addWidget(QLabel(self.tr("Filter on wheel:")))
        cmb_ccd_filter = QComboBox()
        for f in ("L", "R", "G", "B", "Ha", "OIII", "SII"):
            cmb_ccd_filter.addItem(f)
        f_row.addWidget(cmb_ccd_filter)
        btn_ccd_push = QPushButton(self.tr("Send plan"))
        btn_ccd_push.clicked.connect(self._ccd_send_plan)
        f_row.addWidget(btn_ccd_push)
        btn_ccd_start = QPushButton(self.tr("Start capture"))
        btn_ccd_start.clicked.connect(self._ccd_start_capture)
        f_row.addWidget(btn_ccd_start)
        f_row.addStretch()
        layout.addLayout(f_row)
        lbl_ccd_coords = QLabel(self._ccd_coords_text(ctx, kind))
        lbl_ccd_coords.setStyleSheet("color: #9aa0a6;")
        lbl_ccd_coords.setWordWrap(True)
        layout.addWidget(lbl_ccd_coords)
        self._project_widgets.update({
            "cmb_ccd_filter": cmb_ccd_filter,
            "ccd_push": btn_ccd_push,
            "ccd_start": btn_ccd_start,
            "ccd_coords": lbl_ccd_coords,
        })
        self._ccd_apply_state()
        # NEO: also ephemeris export
        if kind in ("neo", "pccp"):
            layout.addWidget(QLabel(""))
            layout.addWidget(QLabel(self.tr("Export ephemeris for planetarium")))
            btn_eph = QPushButton(self.tr("Export ephemeris…"))
            btn_eph.clicked.connect(self._project_export_ephem)
            layout.addWidget(btn_eph)
        self._project_widgets["cmb_seqfmt"] = cmb_fmt
        # save plan button
        btn_save = QPushButton(self.tr("Save plan"))
        btn_save.clicked.connect(self._project_save_plan)
        layout.addWidget(btn_save)
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
            self.statusBar().showMessage(self.tr("Plan saved"), 5000)

    # -- CCDciel control (ADR-030) -----------------------------------------

    def _build_observatory_tab(self):
        # The CCDciel control, window-owned (UX-j): it used to be
        # rebuilt inside every project's Plan step (and orphaned on
        # rebuild). Built ONCE here; the Plan section keeps only the
        # capture buttons (send/start), which read this connection.
        o = self.observatory
        self._obs_widgets = {
            "ccd_connect": o.btn_obs_connect,
            "ccd_disconnect": o.btn_obs_disconnect,
            "ccd_refresh": o.btn_obs_refresh,
            "ccd_status": o.lbl_obs_status,
            "ccd_version": o.lbl_obs_version,
            "ccd_temp": o.lbl_obs_temp,
            "ccd_tracking": o.lbl_obs_tracking,
            "ccd_slew": o.lbl_obs_slew,
            "ccd_goto": o.btn_obs_goto,
            "ccd_sync": o.btn_obs_sync,
            "obs_target": o.cmb_obs_target,
        }
        o.btn_obs_connect.clicked.connect(self._ccd_connect)
        o.btn_obs_disconnect.clicked.connect(self._ccd_disconnect)
        o.btn_obs_refresh.clicked.connect(self._ccd_refresh)
        o.btn_obs_goto.clicked.connect(self._ccd_goto)
        o.btn_obs_sync.clicked.connect(self._ccd_astrometry_goto)
        o.cmb_obs_target.currentIndexChanged.connect(
            lambda _i: self._ccd_apply_state())
        self._ccd_apply_state()
        self._refresh_obs_targets()

    def _ccd_widgets(self):
        # @return: one merged view of the CCDciel widgets — the
        # window-owned Observatory tab ones plus the per-project
        # capture ones (filter combo, send/start) when a project is
        # open. All _ccd_* methods read through here.
        w = dict(getattr(self, "_obs_widgets", {}) or {})
        w.update(self._project_widgets or {})
        return w

    def _obs_target_project(self):
        # @return: the active project dict chosen in the Observatory
        #          tab's target combo, or None
        from ..core import project as _p
        pid = self.observatory.cmb_obs_target.currentData()
        return _p.get(db, pid) if pid else None

    def _refresh_obs_targets(self):
        # Refills the Observatory tab's target combo with the active
        # projects, keeping the selection (same keep-id pattern as
        # the campaigns list).
        cmb = self.observatory.cmb_obs_target
        current = cmb.currentData()
        cmb.blockSignals(True)
        cmb.clear()
        for p in project.list_projects(db, "active"):
            cmb.addItem(f"[{p['kind']}] {p['object_name']}", p["id"])
        idx = cmb.findData(current)
        cmb.setCurrentIndex(idx if idx >= 0 else 0)
        cmb.blockSignals(False)

    def _ccd_apply_state(self):
        # Enable/disable the CCDciel widgets after a connection change and
        # refresh the status line. Safe to call even before the widgets exist.
        w = self._ccd_widgets()
        if not w.get("ccd_connect"):
            return
        on = self._ccd_connected
        # the per-project capture widgets are only present when a project is
        # open — skip whatever is missing
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
        # Refreshes the coords/epoch label from the current project context.
        p = self._current_project
        lbl = self._project_widgets.get("ccd_coords")
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
        # kind/object may come via ctx (the Observatory-tab target
        # project); otherwise fall back to the project open in the hub
        p = self._current_project or {}
        kind = ctx.get("kind") or p.get("kind")
        obj_id = (ctx.get("id") or ctx.get("packed")
                  or p.get("object_name") or ctx.get("object_name"))
        site = config.get("mpc_code", "Z41")
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
        self._ccd_update_coords_label()
        if pos.get("fell_back"):
            self.statusBar().showMessage(
                self.tr("No fresh ephemeris; using the plan coordinates."),
                8000)

    def _ccd_goto(self):
        # Point the mount at the current object. Moving kinds get a fresh
        # position resolved inside the worker (network off the GUI thread);
        # the async slew then waits for Telescope_slewing to settle.
        p = self._obs_target_project()
        if not p:
            self.statusBar().showMessage(
                self.tr("Pick a target project in the Observatory tab"),
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
        if error:
            w["ccd_slew"].setText(self.tr("Failed"))
            self.statusBar().showMessage(error, 8000)
            return
        w["ccd_slew"].setText(self.tr("Idle"))
        self._ccd_apply_position(result)
        self.statusBar().showMessage(
            self.tr("Telescope pointed at the object."), 5000)

    def _ccd_astrometry_goto(self):
        # Astrometric pointing at the current object: CCDciel slews,
        # plate-solves and corrects. Moving kinds resolve a fresh position
        # first (the plate solve absorbs any residual ephemeris error as
        # long as the prediction lands inside the solve field). The client
        # polls the running flag, so no mount-state polling is needed here.
        p = self._obs_target_project()
        if not p:
            self.statusBar().showMessage(
                self.tr("Pick a target project in the Observatory tab"),
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
        # Stage the planned frames/exposure/filter inside CCDciel (Capture_set*).
        spn = self._project_widgets.get("spn_nframes")
        spn_exp = self._project_widgets.get("spn_exps")
        cmb = self._project_widgets.get("cmb_ccd_filter")
        if not (spn and spn_exp and cmb):
            return
        n_frames = spn.value()
        exp_s = spn_exp.value()
        f_idx = cmb.currentIndex()
        name = self._current_project["object_name"]

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

    def _build_process_tab(self, p, kind, ctx):
        layout = self._step_section("process")
        if kind in ("neo", "pccp"):
            # MPC report: paste + validate + save
            layout.addWidget(QLabel(
                self.tr("Paste astrometric measurements (MPC 80-col or ADES)")))
            txt = QTextEdit()
            txt.setMaximumHeight(140)
            txt.setAcceptRichText(False)
            txt.setPlaceholderText(
                self.tr("Paste MPC 80-column or ADES PSV lines here…"))
            font = txt.font(); font.setFamily("Monospace"); txt.setFont(font)
            layout.addWidget(txt)
            btn_val = QPushButton(self.tr("Validate"))
            btn_val.clicked.connect(self._project_mpc_validate)
            layout.addWidget(btn_val)
            btn_save = QPushButton(self.tr("Save report…"))
            btn_save.clicked.connect(self._project_mpc_save)
            layout.addWidget(btn_save)
            lbl_status = QLabel("—"); lbl_status.setWordWrap(True)
            layout.addWidget(lbl_status)
            self._project_widgets["txt_mpc"] = txt
            self._project_widgets["lbl_mpc_status"] = lbl_status
        elif kind == "sn":
            # SN: import result FITS
            layout.addWidget(QLabel(self.tr("Import your processed FITS image")))
            edt = QLineEdit()
            edt.setPlaceholderText(self.tr("Path to plate-solved FITS…"))
            layout.addWidget(edt)
            btn_browse = QPushButton(self.tr("Browse…"))
            btn_browse.clicked.connect(self._project_process_browse)
            layout.addWidget(btn_browse)
            lbl_path = QLabel("—")
            layout.addWidget(lbl_path)
            self._project_widgets["edt_fits"] = edt
            self._project_widgets["lbl_fits_path"] = lbl_path
            # A4: restore saved FITS path from the process step data
            step = next((s for s in p["steps"]
                         if s["step"] == "process"), None)
            saved = step and step["data"].get("fits_path")
            if saved:
                edt.setText(saved)
                lbl_path.setText(saved)
            # (ADR-019 review 2026-08-28) the old "Analyse" step lived here;
            # its only real action — the blink — moved into this step, so the
            # FITS import and the confirmation are side by side.
            btn = QPushButton(self.tr("Open blink…"))
            btn.clicked.connect(self._project_blink)
            layout.addWidget(btn)
            layout.addWidget(QLabel(
                f"<small>{self.tr('Pre-filled with')} {p['object_name']} "
                f"@ {ctx.get('ra_deg', 0):.4f}, {ctx.get('dec_deg', 0):+.4f}"
                f"</small>"))
        elif kind == "transit":
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
                "Database — and tell the story in the Publish step."))
            lbl_exotic.setWordWrap(True)
            layout.addWidget(lbl_exotic)
        elif kind == "hads":
            # ADR-034 (D.3): publication photometry is external — FotoDif
            # (its AUTO mode watches the capture folder live) or AIJ.
            # NightScribe registers the measurements (Follow-up tab) and
            # points to the AAVSO submission.
            lbl = QLabel(self.tr(
                "Reduce the series with FotoDif (its AUTO mode follows the "
                "capture live) or AIJ. FotoDif writes the AAVSO Extended "
                "File Format report directly; the cadence and exposure are "
                "in the Plan step."))
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
                "«Import file…» in the Follow-up tab — the light curve and "
                "the phase-folded view update themselves."))
            lbl_imp.setWordWrap(True)
            layout.addWidget(lbl_imp)
        else:
            layout.addWidget(QLabel(
                self.tr("Process your images with your usual software.")))
        # C0 (track C): NEO/PCCP/comet sessions produce files the observer
        # actually keeps (FITS, Tycho annotated images, MPC report) — they
        # are registered here so the project remembers them.
        if kind in ("neo", "pccp", "comet"):
            self._build_products_block(layout, p)
        layout.addStretch()

    def _build_products_block(self, layout, p):
        # C0: "Session products" group for the NEO/PCCP/comet Process step.
        # Registration goes to project_files (visible in Details, A4) and a
        # summary with the FITS metadata is persisted in the process step
        # data. The MPC report needs no button: it is registered on save.
        # @args: layout - the process tab layout, p - project dict
        grp = QGroupBox(self.tr("Session products"))
        gl = QVBoxLayout(grp)
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
        spn_zoom = QSpinBox()
        spn_zoom.setRange(1, 8)
        spn_zoom.setValue(2)
        spn_zoom.setToolTip(self.tr("Crop zoom (1 = full frame)"))
        row2.addWidget(spn_zoom)
        row2.addStretch()
        gl.addLayout(row2)
        lst = QListWidget()
        lst.setMaximumHeight(120)
        gl.addWidget(lst)
        layout.addWidget(grp)
        self._project_widgets["neo_products"] = lst
        self._project_widgets["neo_zoom"] = spn_zoom
        self._neo_populate_products(lst, p)

    def _neo_populate_products(self, lst, p):
        # @args: lst - read-only QListWidget, p - project dict
        # Fills the products summary from the process step data.
        lst.clear()
        step = next((s for s in p.get("steps", []) if s["step"] == "process"),
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
        step = next((s for s in p.get("steps", []) if s["step"] == "process"),
                    None)
        fits = ((step and step.get("data")) or {}).get("session_fits", [])
        paths_f = [e["path"] for e in fits]
        if len(paths_f) < 2:
            self.statusBar().showMessage(
                self.tr("Register at least 2 session FITS first"), 6000)
            return
        ctx = p.get("context") or {}
        obj_id = ctx.get("id") or ctx.get("packed") or p["object_name"]
        site = config.get("mpc_code", "Z41")
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
        step = next((s for s in p.get("steps", []) if s["step"] == "process"),
                    None)
        existing = []
        if step:
            existing = list((step.get("data") or {}).get(key, []))
        existing.extend(entries)
        project.update_step_data(db, p["id"], "process", {key: existing})
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
        date = (dts["mid"] or datetime.datetime.now(
            datetime.timezone.utc)).date()
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
        # keep the night-view compact on very tall windows (the scene
        # letterboxes inside the widget, so a hard cap costs nothing)
        timeline.setMaximumHeight(220)
        timeline.set_data(
            dusk=win[0] if win else None, dawn=win[1] if win else None,
            safe=safe, capture_start=dts["capture_start"],
            capture_end=dts["capture_end"], ingress=dts["ingress"],
            mid=dts["mid"], egress=dts["egress"])
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

    def _build_followup_tab(self, p, ctx):
        # B2: SN multi-night follow-up panel. Not a step — like Details, it
        # holds the session journal (nights, stacked images, notes) and the
        # cadence reminder ("última visita hace N noches"). All CRUD goes
        # through core/followup.py; FITS metadata through core/fits_meta.py.
        # D3 (ADR-034): shared with HADS projects — the tab's journal and the
        # photometry import are kind-agnostic; only the SN analysis buttons
        # (quick-look on per-night stacks, evolution animation, annotated
        # FITS) are hidden for hads.
        from ..core import followup as fu
        kind = p["kind"]
        layout = self._step_section("followup")
        pid = p["id"]

        # campaign lookup (ADR-035): used by the cadence override below and
        # the protocol block
        camp = None
        if p.get("campaign_id"):
            from ..core import campaign as _camp
            camp = _camp.get(db, p["campaign_id"])

        # cadence reminder (T9): "hace N noches que no la visitas"
        days = fu.days_since_last_session(db, pid)
        threshold = int(config.get("sn_cadence_days", 3))
        if camp is not None:
            threshold = int((camp.get("protocol") or {}).get(
                "cadence_nights") or threshold)
        if days is not None:
            text = self.tr("Last visit: {} days ago").format(days)
            if kind == "hads" and (ctx.get("hads") or {}).get("multiperiodic"):
                text += " · " + self.tr(
                    "multiperiodic stars want consecutive nights")
            lbl_cadence = QLabel(text)
            colour = "#e0c060" if days >= threshold else "#8a90a6"
            lbl_cadence.setStyleSheet(
                f"color: {colour}; font-size: 13px;")
            layout.addWidget(lbl_cadence)
        else:
            layout.addWidget(QLabel(
                self.tr("No visits yet. Add one to start the follow-up.")))

        # campaign protocol (ADR-035): show the agreed observing protocol
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

        # add visit button
        btn_add = QPushButton(self.tr("Add visit"))
        btn_add.clicked.connect(lambda: self._fu_add_session(pid))
        layout.addWidget(btn_add)
        # B3: paste bulk photometry + import file
        fu_btns = QHBoxLayout()
        btn_paste = QPushButton(self.tr("Paste photometry…"))
        btn_paste.clicked.connect(lambda: self._fu_paste_dialog(pid))
        fu_btns.addWidget(btn_paste)
        btn_file = QPushButton(self.tr("Import file…"))
        btn_file.clicked.connect(lambda: self._fu_import_file(pid))
        fu_btns.addWidget(btn_file)
        btn_export = QPushButton(self.tr("Export photometry report…"))
        btn_export.setToolTip(self.tr(
            "CSV or AAVSO EFF with heliocentric dates, for the campaign "
            "form / WebObs"))
        btn_export.clicked.connect(lambda: self._fu_export_report(pid))
        fu_btns.addWidget(btn_export)
        if kind in ("sn", "variable"):
            btn_survey = QPushButton(self.tr("Download survey photometry…"))
            btn_survey.setToolTip(self.tr(
                "ASAS-SN/ZTF context points, drawn in grey and never "
                "mixed with your own measurements"))
            btn_survey.clicked.connect(
                lambda: self._fu_download_survey(pid))
            fu_btns.addWidget(btn_survey)
            self._project_widgets["fu_survey"] = btn_survey
        layout.addLayout(fu_btns)

        # sessions list
        grp = QGroupBox(self.tr("Visits"))
        grp.setLayout(QVBoxLayout())
        lst = QListWidget()
        self._fu_populate_sessions(lst, pid)
        lst.itemSelectionChanged.connect(
            lambda: self._fu_session_selected(lst, pid))
        grp.layout().addWidget(lst)

        # session detail area (rebuilt per session: images, measurements,
        # notes). The notes widget is created in _fu_session_selected — keep
        # only a placeholder here so the dual-identity bug (two QTextEdit
        # bound to different sessions) can't happen.
        self._fu_detail = QFrame()
        fu_layout = QVBoxLayout(self._fu_detail)
        fu_layout.addWidget(QLabel(
            self.tr("Select a visit to see its images.")))
        fu_detail_area = QScrollArea()
        fu_detail_area.setWidgetResizable(True)
        fu_detail_area.setFrameShape(QFrame.Shape.NoFrame)
        fu_detail_area.setWidget(self._fu_detail)
        grp.layout().addWidget(fu_detail_area)
        layout.addWidget(grp)
        # B5/B6/B10: analysis buttons — quick-look, evolution animation,
        # annotated FITS export. They operate on the registered stacked
        # images and the follow-up photometry.
        ana_row = QHBoxLayout()
        btn_quicklook = QPushButton(self.tr("Run quick-look"))
        btn_quicklook.setToolTip(self.tr(
            "Differential magnitude vs. an automatic comparison ensemble"))
        btn_quicklook.clicked.connect(lambda: self._fu_run_quicklook(pid))
        ana_row.addWidget(btn_quicklook)
        btn_evo = QPushButton(self.tr("Generate animation"))
        btn_evo.setToolTip(self.tr(
            "GIF/MP4 of the photometric evolution across visits"))
        btn_evo.clicked.connect(lambda: self._fu_run_animation(pid))
        ana_row.addWidget(btn_evo)
        btn_annot = QPushButton(self.tr("Export annotated FITS"))
        btn_annot.setToolTip(self.tr(
            "Copy of the stacked FITS with annotation keywords (NS_)"))
        btn_annot.clicked.connect(lambda: self._fu_export_annotated(pid))
        ana_row.addWidget(btn_annot)
        if kind == "hads":
            # SN-only analysis: the quick-look engine measures stacked
            # per-night images, not an intra-night series (ADR-034, D.3)
            for b in (btn_quicklook, btn_evo, btn_annot):
                b.hide()
        elif kind == "variable":
            # variables share the quick-look (the series engine serves
            # them unchanged, V-g) but not the SN evolution animation or
            # the annotated FITS
            for b in (btn_evo, btn_annot):
                b.hide()
        layout.addLayout(ana_row)
        layout.addStretch()
        self._project_widgets["fu_sessions"] = lst

    def _fu_run_quicklook(self, pid):
        # B5: run the series engine on the registered stacked images and save
        # the quick-look points + campaign summary to the project.
        from ..core import followup as fu
        from ..core import series
        p = project.get(db, pid)
        if not p:
            return
        # collect the stacked images (one per session)
        paths = []
        for s in fu.list_sessions(db, pid):
            for img in fu.list_images(db, s["id"]):
                if img["fits_path"]:
                    paths.append(img["fits_path"])
        if not paths:
            self.statusBar().showMessage(
                self.tr("No stacked images registered"), 5000)
            return
        ctx = p.get("context") or {}
        sn_ra = ctx.get("ra_deg")
        sn_dec = ctx.get("dec_deg")
        if sn_ra is None or sn_dec is None:
            self.statusBar().showMessage(
                self.tr("Project has no coordinates"), 5000)
            return
        sn_type = (ctx.get("sn_type") or ctx.get("otype") or "")
        try:
            result = series.quicklook(paths, sn_ra, sn_dec, sn_type=sn_type)
        except Exception as err:
            self.statusBar().showMessage(
                self.tr("Quick-look failed: %1").replace("%1", str(err)), 8000)
            return
        # save quicklook points
        for pt in result.get("points", []):
            fu.add_point(db, pid, pt["mjd"], pt["filter"], pt["mag"],
                         err=pt.get("err"), source="quicklook")
        summary = result.get("summary", {})
        verdict = summary.get("verdict", "unknown")
        slope = summary.get("slope_mag_per_day")
        delta = summary.get("delta_from_peak")
        # show the campaign summary in the status bar + as a status label
        msg = self.tr("Quick-look: {} points — verdict: {}").format(
            len(result.get("points", [])), verdict)
        if slope is not None:
            msg += self.tr(" · slope: {:.2f} mag/d").format(slope)
        if delta is not None:
            msg += self.tr(" · Δmag from peak: {:.2f}").format(delta)
        self.statusBar().showMessage(msg, 10000)
        # refresh the panel so the new quicklook points show on the curve
        self._project_selected()

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
        # B10: export a copy of the first registered stacked FITS with the
        # annotation keywords injected (NS_SN_X, NS_SCALE, etc.).
        from ..core import followup as fu
        from ..core import fits_annotate
        p = project.get(db, pid)
        if not p:
            return
        fits_paths = []
        for s in fu.list_sessions(db, pid):
            for img in fu.list_images(db, s["id"]):
                if img["fits_path"]:
                    fits_paths.append(img["fits_path"])
        if not fits_paths:
            self.statusBar().showMessage(
                self.tr("No stacked images registered"), 5000)
            return
        ctx = p.get("context") or {}
        sn_ra = ctx.get("ra_deg")
        sn_dec = ctx.get("dec_deg")
        sn_xy = None
        if sn_ra is not None and sn_dec is not None:
            try:
                from ..core import fits_io, wcs as wcs_mod
                header, _ = fits_io.read_fits(fits_paths[0])
                wcs = wcs_mod.Wcs.from_header(header)
                if wcs:
                    sn_xy = wcs.sky_to_pixel(sn_ra, sn_dec)
            except Exception:
                pass
        out = project.storage_dir(p) / \
            f"{p['object_name']}_annotated.fits"
        try:
            fits_annotate.write_annotated_fits(
                fits_paths[0], str(out), sn_xy=sn_xy,
                obj_name=p["object_name"], ra_deg=sn_ra, dec_deg=sn_dec,
                notes=self.tr("SN follow-up"))
            project.add_file(db, pid, str(out), "fits")
            self._populate_project_files(pid)
            self.statusBar().showMessage(
                self.tr("Annotated FITS written to %1").replace("%1", str(out)),
                8000)
        except Exception as err:
            self.statusBar().showMessage(
                self.tr("Annotated FITS failed: %1").replace("%1", str(err)),
                8000)

    def _fu_populate_sessions(self, lst, pid):
        # @args: lst - QListWidget, pid - project id
        from ..core import followup as fu
        lst.clear()
        sessions = fu.list_sessions(db, pid)
        for s in sessions:
            n_img = len(fu.list_images(db, s["id"]))
            from ..core import followup as fumod
            pts = fumod.list_points(db, pid)
            n_pts = sum(1 for p in pts if p.get("session_id") == s["id"])
            notes_tag = f" · {s['notes'][:20]}" if s["notes"] else ""
            item = QListWidgetItem(
                f"{s['obs_date']}  ({n_img} img, {n_pts} mag){notes_tag}")
            item.setData(Qt.UserRole, s["id"])
            lst.addItem(item)

    def _fu_session_selected(self, lst, pid):
        # @args: lst - QListWidget, pid - project id
        from ..core import followup as fu
        items = lst.selectedItems()
        if not items:
            return
        sid = items[0].data(Qt.UserRole)
        self._fu_current_session = sid
        # rebuild the session detail area: images + measurements + notes
        detail = self._fu_detail
        self._wipe_layout(detail.layout())
        dlay = detail.layout()
        # action row: add stacked image + delete this visit
        fu_row = QHBoxLayout()
        btn_img = QPushButton(self.tr("Add stacked image…"))
        btn_img.clicked.connect(lambda: self._fu_add_image(sid, pid))
        fu_row.addWidget(btn_img)
        btn_del = QPushButton(self.tr("Delete visit…"))
        btn_del.setObjectName("fu_btn_delete")
        btn_del.clicked.connect(lambda: self._fu_delete_session(lst, sid, pid))
        fu_row.addWidget(btn_del)
        dlay.addLayout(fu_row)
        # images list for this session
        img_lst = QListWidget()
        self._fu_populate_images(img_lst, sid)
        dlay.addWidget(img_lst)
        self._project_widgets["fu_images"] = img_lst
        # B3: quick measurement entry — just type the magnitude
        grp_meas = QGroupBox(self.tr("Measurements"))
        grp_meas.setLayout(QVBoxLayout())
        meas_row = QHBoxLayout()
        meas_row.addWidget(QLabel(self.tr("Mag:")))
        spn_mag = QDoubleSpinBox()
        spn_mag.setRange(-5.0, 30.0)
        spn_mag.setDecimals(3)
        spn_mag.setValue(16.0)
        meas_row.addWidget(spn_mag)
        meas_row.addWidget(QLabel(self.tr("Err:")))
        spn_err = QDoubleSpinBox()
        spn_err.setRange(0.0, 9.0)
        spn_err.setDecimals(3)
        spn_err.setValue(0.0)
        spn_err.setSpecialValueText("—")
        meas_row.addWidget(spn_err)
        meas_row.addWidget(QLabel(self.tr("Filter:")))
        cmb_filt = QComboBox()
        cmb_filt.setEditable(True)
        cmb_filt.addItems(["Clear", "V", "R", "B", "I", "NIR"])
        meas_row.addWidget(cmb_filt)
        btn_add_meas = QPushButton(self.tr("Add"))
        btn_add_meas.clicked.connect(
            lambda: self._fu_add_measurement(sid, pid, spn_mag,
                                              spn_err, cmb_filt))
        grp_meas.layout().addLayout(meas_row)
        # measurements list for this session
        meas_lst = QListWidget()
        self._fu_populate_measurements(meas_lst, pid, sid)
        grp_meas.layout().addWidget(meas_lst)
        dlay.addWidget(grp_meas)
        self._project_widgets["fu_meas_mag"] = spn_mag
        self._project_widgets["fu_meas_err"] = spn_err
        self._project_widgets["fu_meas_filt"] = cmb_filt
        self._project_widgets["fu_measurements"] = meas_lst
        # notes
        s = fu.get_session(db, sid)
        notes = QTextEdit()
        notes.setPlaceholderText(self.tr("Night notes (seeing, clouds…)"))
        if s:
            notes.setText(s["notes"])
        notes.textChanged.connect(lambda: self._fu_save_notes(pid))
        dlay.addWidget(notes)
        self._project_widgets["fu_notes"] = notes

    def _fu_populate_measurements(self, lst, pid, sid):
        # @args: lst - QListWidget, pid - project id, sid - session id
        from ..core import followup as fu
        lst.clear()
        for pt in fu.list_points(db, pid):
            if pt.get("session_id") == sid:
                err_str = f" ±{pt['err']}" if pt["err"] is not None else ""
                item = QListWidgetItem(
                    f"[{pt['filter']}] mag {pt['mag']}{err_str}"
                    f"  ({pt['source']})")
                item.setData(Qt.UserRole, pt["id"])
                lst.addItem(item)

    def _session_mjd(self, s):
        # Turn a session row into a sensible MJD. Prefers the observing date;
        # falls back to the session's creation timestamp. Never returns 0 — a
        # zero MJD corrupts the light-curve ordering (B2 defect).
        # @args: s - session dict from followup.get_session (or None)
        # @return: MJD as float
        from ..core.coords import jd_from_datetime
        if s:
            date_str = (s.get("obs_date") or "").strip()
            for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y/%m/%d"):
                if date_str:
                    try:
                        dt = datetime.datetime.strptime(
                            date_str, fmt).replace(tzinfo=datetime.timezone.utc)
                        return jd_from_datetime(dt) - 2400000.5
                    except ValueError:
                        pass
            # no parseable date: use the row's creation epoch
            created = s.get("created")
            if created:
                dt = datetime.datetime.fromtimestamp(
                    created, tz=datetime.timezone.utc)
                return jd_from_datetime(dt) - 2400000.5
        # last resort: right now, so the point still plots in order
        dt = datetime.datetime.now(datetime.timezone.utc)
        return jd_from_datetime(dt) - 2400000.5

    def _fu_add_measurement(self, sid, pid, spn_mag, spn_err, cmb_filt):
        # B3 quick entry: one click saves a point (date/filter from the session).
        from ..core import followup as fu
        mag = spn_mag.value()
        err = spn_err.value() if spn_err.value() > 0 else None
        filt = cmb_filt.currentText().strip() or "Clear"
        s = fu.get_session(db, sid)
        mjd = self._session_mjd(s)
        fu.add_point(db, pid, mjd, filt, mag, err=err,
                     source="manual", session_id=sid)
        self._populate_project_files(pid)
        meas_lst = self._project_widgets.get("fu_measurements")
        if meas_lst:
            self._fu_populate_measurements(meas_lst, pid, sid)

    def _fu_populate_images(self, lst, sid):
        # @args: lst - QListWidget, sid - session id
        from ..core import followup as fu
        lst.clear()
        for img in fu.list_images(db, sid):
            filt = img["filter"] or "—"
            label = f"[{filt}] {Path(img['fits_path']).name}"
            if img["date_obs"]:
                label += f"  ({img['date_obs']})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, img["id"])
            lst.addItem(item)

    def _fu_add_image(self, sid, pid):
        # File dialog → fits_meta auto-fill → editable dialog → save.
        # The user can correct the filter / date / exptime before committing,
        # because a misnamed filter breaks the light-curve split (B2 defect).
        # @args: sid - session id, pid - project id
        from ..core import followup as fu
        from ..core import fits_meta
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Choose stacked FITS"), "",
            "FITS (*.fits *.fit *.fts);;All files (*)")
        if not path:
            return
        # auto-detect the header values we can, tolerate a bad/empty file
        try:
            meta = fits_meta.read_meta(path)
        except Exception:
            meta = {}
        filt = (meta.get("filter") or "Clear").strip() or "Clear"
        date_obs = meta.get("date_obs") or ""
        exptime_s = meta.get("exptime_s")
        # editable confirmation dialog pre-filled from the FITS header
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Add stacked image"))
        dlg.setLayout(QFormLayout())
        lbl_path = QLabel(Path(path).name)
        lbl_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        dlg.layout().addRow(self.tr("File:"), lbl_path)
        cmb_f = QComboBox()
        cmb_f.setObjectName("fu_img_filter")
        cmb_f.setEditable(True)
        cmb_f.addItems(["Clear", "V", "R", "B", "I", "NIR"])
        cmb_f.setCurrentText(filt)
        dlg.layout().addRow(self.tr("Filter:"), cmb_f)
        edt_date = QLineEdit(str(date_obs or ""))
        edt_date.setObjectName("fu_img_date")
        edt_date.setPlaceholderText(self.tr("e.g. 2026-09-01 (leave blank to skip)"))
        dlg.layout().addRow(self.tr("Date:"), edt_date)
        edt_exp = QLineEdit(
            "" if exptime_s in (None, "") else str(exptime_s))
        edt_exp.setObjectName("fu_img_exptime")
        edt_exp.setPlaceholderText(self.tr("exposure seconds (optional)"))
        dlg.layout().addRow(self.tr("Exptime:"), edt_exp)
        box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dlg.layout().addWidget(box)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.Accepted:
            return
        out_filt = cmb_f.currentText().strip() or "Clear"
        out_date = edt_date.text().strip() or None
        exp_text = edt_exp.text().strip()
        out_exp = None
        if exp_text:
            try:
                out_exp = float(exp_text)
            except ValueError:
                out_exp = None
        fu.add_image(db, sid, out_filt, path,
                     date_obs=out_date, exptime_s=out_exp)
        # T4: register the FITS path in the project
        project.add_file(db, pid, path, "fits")
        # refresh images list + files list
        img_lst = self._project_widgets.get("fu_images")
        if img_lst:
            self._fu_populate_images(img_lst, sid)
        self._populate_project_files(pid)

    def _fu_save_notes(self, pid):
        # Persist notes on the current session (B2: "en ocasiones" se guardan).
        from ..core import followup as fu
        sid = getattr(self, "_fu_current_session", None)
        notes = self._project_widgets.get("fu_notes")
        if sid and notes:
            fu.update_session_notes(db, sid, notes.toPlainText())

    def _fu_add_session(self, pid):
        # Create a session for today and refresh the list (B2).
        from ..core import followup as fu
        fu.create_session(db, pid)
        lst = self._project_widgets.get("fu_sessions")
        if lst:
            self._fu_populate_sessions(lst, pid)
            # select the new one (top of the list, ordered DESC)
            lst.setCurrentRow(0)

    def _fu_delete_session(self, lst, sid, pid):
        # Delete a visit after confirmation. The cascade removes its stacked
        # images; photometry points are kept (B2 defect: the GUI had no way to
        # drop a bad visit at all).
        # @args: lst - sessions QListWidget, sid - session id, pid - project id
        from ..core import followup as fu
        n_img = len(fu.list_images(db, sid))
        if QMessageBox.question(
                self, self.tr("Delete visit"),
                self.tr("Delete this visit? Its measurements are kept."
                        "  ({} stacked image{})").format(
                            n_img, "s" if n_img != 1 else ""),
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        fu.delete_session(db, sid)
        self._fu_current_session = None
        self._project_widgets.pop("fu_notes", None)
        self._fu_populate_sessions(lst, pid)
        # re-select the first remaining visit to refresh the detail pane, or
        # clear the pane if this was the last one
        if lst.count():
            lst.setCurrentRow(0)
        else:
            dlay = self._fu_detail.layout()
            self._wipe_layout(dlay)
            dlay.addWidget(QLabel(
                self.tr("Select a visit to see its images.")))
        self._populate_project_files(pid)

    def _populate_project_files(self, pid):
        # Refresh the project files list in the Details tab. The files list
        # widget is built by Track A (A4); if it doesn't exist yet this is a
        # safe no-op so B2/B3 don't crash on branches without A merged.
        lst = getattr(self, "_proj_files_list", None)
        if lst is None:
            return
        lst.clear()
        for f in project.list_files(db, pid):
            name = Path(f["path"]).name
            dt = datetime.datetime.fromtimestamp(f["created"])
            item = QListWidgetItem(
                f"[{f['kind']}] {name}  ({dt.strftime('%Y-%m-%d')})")
            item.setData(Qt.UserRole, str(f["path"]))
            lst.addItem(item)
        sec = getattr(self, "_proj_files_section", None)
        if sec is not None and lst.count() > 0:
            sec.setCollapsed(True)

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
        def on_text_changed():
            pts, skipped = parse_photometry(
                edit.toPlainText(),
                default_filter=cmb_def.currentText().strip() or "Clear")
            preview.clear()
            for p in pts:
                err_str = f" ±{p['err']}" if p["err"] else ""
                preview.addItem(
                    f"mag {p['mag']}{err_str}  [{p['filter']}]")
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
        for p in pts:
            fu.add_point(db, pid, p["mjd"], p["filter"], p["mag"],
                         err=p["err"], source="paste")
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
        for p in pts:
            fu.add_point(db, pid, p["mjd"], p["filter"], p["mag"],
                          err=p["err"], source="file")
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
        # comparison stars and observer code come from the campaign/config
        comps, observer = [], config.get("aavso_code", "")
        if p.get("campaign_id"):
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
        w.finished.connect(lambda pts: self._fu_survey_done(pid, pts))
        self._keep(w)

    def _fu_survey_done(self, pid, pts):
        # Merges the worker's survey points and rebuilds the tab in place.
        from ..core import followup as fu
        btn = self._project_widgets.get("fu_survey")
        if btn is not None:
            btn.setEnabled(True)
        if not pts:
            self.statusBar().showMessage(
                self.tr("No survey data for this position"), 6000)
            return
        existing = {(q["mjd"], q["filter"]) for q in fu.list_points(db, pid)
                    if (q.get("source") or "").startswith("survey:")}
        n = 0
        for pt in pts:
            if (pt["mjd"], pt["filter"]) in existing:
                continue
            fu.add_point(db, pid, pt["mjd"], pt["filter"], pt["mag"],
                         err=pt.get("err"), source=pt["source"])
            n += 1
        self.statusBar().showMessage(
            self.tr("Added %1 survey points").replace("%1", str(n)), 8000)
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
        spn_n = QSpinBox()
        spn_n.setMinimum(1); spn_n.setMaximum(999)
        spn_n.setValue(n)
        row.addWidget(spn_n)
        spn_e = QDoubleSpinBox()
        spn_e.setMinimum(0.1); spn_e.setMaximum(3600.0)
        spn_e.setValue(exp)
        row.addWidget(spn_e)
        btn_del = QPushButton("✕")
        btn_del.setFixedWidth(28)
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

    def _project_process_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Choose FITS image"), "",
            "FITS (*.fits *.fit *.fts);;All files (*)")
        if path:
            edt = self._project_widgets.get("edt_fits")
            lbl = self._project_widgets.get("lbl_fits_path")
            if edt:
                edt.setText(path)
            if lbl:
                lbl.setText(path)
            # A4: persist the FITS path in the project
            if self._current_project:
                project.update_step_data(
                    db, self._current_project["id"], "process",
                    {"fits_path": path})
                project.add_file(db, self._current_project["id"], path, "fits")
                self._populate_project_files(self._current_project["id"])

    def _project_mpc_validate(self):
        if not self._current_project:
            return
        txt = self._project_widgets.get("txt_mpc")
        if not txt:
            return
        text = txt.toPlainText()
        if not text.strip():
            self._project_widgets["lbl_mpc_status"].setText(
                self.tr("Paste your measurements first."))
            return
        obs_code = config.get("mpc_code", "")
        obj = self._current_project["object_name"]
        result = mpc_report.validate(text, obs_code=obs_code,
                                     expected_obj=obj)
        lbl = self._project_widgets.get("lbl_mpc_status")
        if result["valid"]:
            status = (self.tr("Valid: %1 lines, %2").replace("%1", str(result["n_lines"]))
                      .replace("%2", result["format"]))
            if result["warnings"]:
                status += " ⚠ " + "; ".join(result["warnings"])
            lbl.setText(status)
        else:
            lbl.setText(self.tr("Invalid: ") + "; ".join(result["errors"][:4])
                        + ("…" if len(result["errors"]) > 4 else ""))

    def _project_mpc_save(self):
        if not self._current_project:
            return
        txt = self._project_widgets.get("txt_mpc")
        if not txt:
            return
        text = txt.toPlainText()
        if not text.strip():
            self._project_widgets["lbl_mpc_status"].setText(
                self.tr("Paste your measurements first."))
            return
        obs_code = config.get("mpc_code", "")
        obj = self._current_project["object_name"]
        outdir = project.storage_dir(self._current_project)
        default = outdir / f"{obj}_mpc_report.txt"
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Save MPC report"), str(default),
            "Text files (*.txt);;All files (*)")
        if not out:
            return
        path, result = mpc_report.package(text, out, obs_code=obs_code,
                                          expected_obj=obj)
        lbl = self._project_widgets.get("lbl_mpc_status")
        if path:
            project.add_file(db, self._current_project["id"], path, "report")
            project.update_step_data(db, self._current_project["id"],
                                     "process", {"mpc_report": path})
            lbl.setText(self.tr("Saved: %1 (%2 lines)")
                        .replace("%1", path).replace("%2", str(result["n_lines"])))
            self.statusBar().showMessage(
                self.tr("MPC report ready to email"), 8000)
        else:
            lbl.setText(self.tr("Invalid: ") + "; ".join(result["errors"][:4])
                        + ("…" if len(result["errors"]) > 4 else ""))

    def _project_post(self):
        if self._current_project:
            self._open_post_dialog(self._current_project["object_name"])

    def _project_blink(self):
        if self._current_project:
            ctx = self._current_project["context"]
            # use the FITS from the process tab if available
            edt = self._project_widgets.get("edt_fits")
            fits_path = edt.text().strip() if edt else ""
            self._open_blink_dialog(
                sn_name=self._current_project["object_name"],
                ra=ctx.get("ra_deg"), dec=ctx.get("dec_deg"),
                fits_path=fits_path or None)

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

    def _project_tags_edited(self):
        # A3: tags editor — comma-separated free text, saved on Enter/focus-out.
        if not self._current_project:
            return
        pid = self._current_project["id"]
        tags = self.projects.edt_tags.text().strip()
        project.set_tags(db, pid, tags)
        # refresh the list row (tags appear in the label)
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

    def _camp_add_target(self):
        from .campaigns_dialog import AddTargetDialog
        cid = self._selected_campaign_id()
        if cid is None:
            return
        if AddTargetDialog(self, campaign_id=cid, db_obj=db).exec():
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
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        for label, slot in (
                (self.tr("Edit…"), self._camp_edit),
                (self.tr("Finish"), self._camp_finish),
                (self.tr("Reopen"), self._camp_reopen),
                (self.tr("Delete…"), self._camp_delete),
                (self.tr("Add target…"), self._camp_add_target),
                (self.tr("Attach…"), self._camp_attach),
                (self.tr("Detach…"), self._camp_detach)):
            act = menu.addAction(label)
            act.triggered.connect(slot)
        menu.exec(self.campaigns.lst_campaigns.viewport()
                  .mapToGlobal(pos))

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
        w = BlinkExportWorker(
            kind, self._blink_ref8, self._blink_obs8, sn, out, effect=effect,
            name=pair["name"], ref_label=pair["ref_label"],
            lang=self._lang(),
            observatory=config.get("observatory_name", ""),
            zoom=(1, 2, 4)[b.cmb_zoom.currentIndex()],
            marker_scale=b.sld_marker.value() / 10.0,
            interval_ms=b.spn_interval.value())
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
        self.solar.lbl_moon_icon.setPixmap(
            moon_icon.moon_pixmap(m["elong_deg"], 20))
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
                    visible.append(f"{name.capitalize()} (mag {p['mag']}, "
                                   f"{alt:.0f}°)")
        self.solar.lbl_planets.setText(
            self.tr("Planets at dusk: ")
            + (", ".join(visible) if visible else self.tr("none above 15°")))

    # ---------------- History ----------------

    def on_refresh_history(self):
        tbl = self.history.tbl_history
        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)
        for r in db.history(100):
            row = tbl.rowCount()
            tbl.insertRow(row)
            for col, val in enumerate((r["obs_date"], r["object"],
                                       r["type"] or "",
                                       "✔" if r["posted"] else "",
                                       r["notes"])):
                tbl.setItem(row, col, QTableWidgetItem(val))
        tbl.setSortingEnabled(True)
        tbl.sortItems(0, Qt.DescendingOrder)

    def _history_open(self, row, _col):
        # Double-click on a history row: open the object's active project,
        # or explore the object when there is none (UX-c/UX-d).
        name_item = self.history.tbl_history.item(row, 1)
        name = name_item.text().strip() if name_item is not None else ""
        if not name:
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
