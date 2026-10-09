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
import datetime as _dt
import logging
import re
import uuid
from pathlib import Path

from PySide6 import Shiboken
from PySide6.QtCore import (QCoreApplication, QEvent, QSize, Qt, Signal,
                            QPropertyAnimation, QEasingCurve, QTimer)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog,
                                QFileDialog, QFrame,
                                QFormLayout, QGroupBox, QHBoxLayout,
                                QHeaderView, QInputDialog, QLabel, QLineEdit,
                                QListWidget, QListWidgetItem, QMainWindow,
                                QMessageBox, QProgressBar, QProgressDialog,
                                QPushButton, QScrollArea,
                                QComboBox,
                                QCheckBox, QDialogButtonBox, QTextEdit,
                                QVBoxLayout, QWidget, QTableWidget,
                                QTableWidgetItem)

from .. import paths
from ..config import config
from ..version import full_version
from ..core import (attention, dates, ephemeris, journal, kinds, mpc_report,
                    orbits, project, sequence, suggest)
from ..core.db import db
from . import pretty, theme
from .overview import ObjectPanel
from .skeleton import ShimmerRow
from .widgets.passive_wheel import (PassiveDoubleSpinBox, PassiveList,
                                    PassiveSpinBox)
from .widgets.campaign_row import CampaignRow
from .widgets.project_row import ROW_HEIGHT as _PROJECT_ROW_H
from .widgets.project_row import ProjectRow
from .widgets.project_row import SPARK_H as ROW_SPARK_H
from .widgets.project_row import SPARK_W as ROW_SPARK_W
from .widgets.sparkline import sparkline_pixmap
from .workers import (AiPostWorker, CcdcielWorker,
                      ExploreWorker, MpcResolveWorker, PassWorker,
                      PositionRefreshWorker, PostWorker, SunWorker,
                      TonightWorker, hold, running_workers)

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


def _parse_date_obs(text):
    # The FITS DATE-OBS, in the several shapes it actually arrives in.
    # @args: text - "2026-10-02T21:14:03.5", "2026-10-02T21:14:03", a space
    #        instead of the T, or None
    # @return: a UTC datetime, or None when it cannot be read. A
    #          half-written header is normal in the wild, not exceptional.
    if not text:
        return None
    raw = str(text).strip().replace("Z", "").replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(raw, fmt).replace(
                tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
    return None


# Which Settings spin shows each config key of the camera profile: the map
# the preset fill walks (core/cameras.profile_from_preset returns config keys,
# the dialog owns the widgets, and this is the only place that knows both).
_CAM_PRESET_SPINS = {
    "pixel_um": "spn_pixel_um",
    "cam_full_well_e": "spn_cam_full_well",
    "cam_linearity_adu": "spn_cam_linearity",
    "ccd_read_noise": "spn_cam_ron",
    "cam_dark_current_e_s": "spn_cam_dark",
    "cam_max_exposure_s": "spn_cam_max_exp",
}


def _master_num(value, fmt="{:.3g}"):
    # @args: value - a master's gain, temperature or exposure (maybe None),
    #        fmt - how a number is shown
    # @return: the text for the master table's cell. None becomes an EMPTY
    #          cell, not "None" and not "0": the library only knows what
    #          the header said, and a blank says "the file did not say",
    #          while a zero would be matched against a light as if it were
    #          a real measurement.
    return "" if value is None else fmt.format(float(value))


# How much of an EXOTIC run log is read to report a failure (P2 #21): the
# tail is where the error is, and a two-hour log can be big.
_LOG_TAIL_BYTES = 64 * 1024


def _exotic_log_tail(path, lines=8, chars=1200):
    # What EXOTIC actually said when a run failed (P2 #21). The log is
    # written line by line while the run streams, so its last lines are
    # the error; reporting the file's PATH instead left the user with
    # nothing to act on.
    # @args: path - the run log (None or missing is tolerated), lines -
    #        trailing non-empty lines to keep, chars - cap for the box
    # @return: the tail as one string, "" when there is nothing to read
    if not path:
        return ""
    try:
        p = Path(path)
        size = p.stat().st_size
        with p.open("rb") as fh:
            if size > _LOG_TAIL_BYTES:
                fh.seek(size - _LOG_TAIL_BYTES)
            raw = fh.read()
    except OSError:
        return ""
    tail = [ln.rstrip() for ln in raw.decode("utf-8", "replace").splitlines()]
    if size > _LOG_TAIL_BYTES and tail:
        tail = tail[1:]              # the chunk cut its first line in half
    tail = [ln for ln in tail if ln.strip()][-lines:]
    return "\n".join(tail)[-chars:]


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

# Top-level view indices in the shell's QStackedWidget (Interfaz 1.0;
# ADR-053). The old QTabWidget is gone: Home is the projects hub (the
# start view), Tonight is the "new project" flow, Campaigns is the hub's
# campaign section, and Detail is one project full-screen. The legacy
# TAB_* names are kept as aliases so the deep links across the file
# (project created -> hub, campaign badge -> campaigns) keep working.
# Interfaz 1.6: the projects view is ONE page holding the list and the
# project side by side (a splitter between them). Opening a project is a
# SELECTION inside it, not a different place, so VIEW_HOME and VIEW_DETAIL
# are two names for the same page: every deep link in the file keeps
# working, the history still tells the two apart by the project id it
# carries, and the list never disappears when you open something.
VIEW_PROJECTS, VIEW_TONIGHT, VIEW_CAMPAIGNS, VIEW_WELCOME, VIEW_UFE = range(5)
VIEW_HOME = VIEW_PROJECTS
VIEW_DETAIL = VIEW_PROJECTS
TAB_PROJECTS = VIEW_HOME
TAB_TONIGHT = VIEW_TONIGHT
TAB_CAMPAIGNS = VIEW_CAMPAIGNS

# The published user guide (ADR-070). The site is generated from the very same
# docs/user the in-app browser reads, so this link and Help > Technical
# Documentation cannot tell different stories; the language is appended.
GUIDE_WEB_URL = "https://irydeo.github.io/nightscribe/docs/index"

# The projects list: how wide it opens, and the range the splitter allows.
# It is the observer's to choose and it is remembered between runs. The
# default is measured, not guessed: at ~500 px the row fits the curve AND
# the object's numbers (at 420 the numbers have to give way, and at 560 the
# campaign badge joins them).
_LIST_W_DEFAULT = 500
_LIST_W_MIN = 260
_LIST_W_MAX = 560


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


class _AiWidgetCfg:
    # A Config-shaped reader over the AI fields on screen (ADR-075): the
    # Settings "Test connection" tries the values you typed WITHOUT saving
    # them, so testing a half-typed endpoint never touches your setup.
    def __init__(self, dlg):
        self._dlg = dlg

    def get(self, k, d=None):
        return {
            "ai_base_url": self._dlg.edt_ai_base_url.text().strip(),
            "ai_api_key": self._dlg.edt_ai_api_key.text().strip(),
            "ai_model": self._dlg.cmb_ai_model.currentText().strip(),
            "ai_temperature": self._dlg.spn_ai_temp.value(),
        }.get(k, d)


class MainWindow(QMainWindow):
    # Three tabs (ADR-043): Tonight · Projects · Campaigns: the CCDciel
    # control now lives inside the project's Capture step. The Tools menu
    # holds the Sky calendar, the observing journal, and the contextual
    # Explore/Post/Blink dialogs.

    # @args: snapshot - the pre-migration backup dict from core/backup.py
    #        (the Welcome view's data report), or None when there is no
    #        database yet
    def __init__(self, snapshot=None):
        super().__init__()
        self._snapshot = snapshot
        self._welcome = None
        self._welcome_gate = False   # True while an update is unacknowledged
        # Interfaz 1.0: Tonight is computed on demand, when the new-project
        # view is first opened (never at start).
        self._tonight_loaded = False
        self._tonight_running = False
        # Interfaz 1.1: navigation history (back/forward) over locations
        # (view, project, tab, campaign). _navigating guards against
        # recording the history replay itself.
        self._nav_back = []
        self._nav_fwd = []
        self._navigating = False
        self._tonight_top = []
        self._tonight_all = []
        self._workers = []
        self._current_project = None
        self._project_widgets = {}
        # Which astrometry run the editor must SHOW when a visit is opened:
        # (project_id, session_id, run_id) when it was opened from the
        # Analysis tab's list (the observer picked one), None when it was
        # opened from the visit (the newest run wins, as always).
        self._astrometry_run_pref = None
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
        self._pos_worker = None        # the position-refresh worker, if any
        self._pos_target = None        # the project a refresh was for
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

        self._build_shell()
        self._connect_menu()
        # the AI master switch (ADR-075): set the Help action's state before
        # the window is shown, so a disabled AI never offers its dialog
        self._refresh_ai_availability()
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
            + self.tr("Ready"), 8000)
        # Interfaz 1.0: nothing is computed on start. Tonight is on demand,
        # when the observer asks for a new project (the app opens fast and
        # offline). See ADR-053.
        self._now_timer = QTimer(self)
        self._now_timer.timeout.connect(self._refresh_now_badges)
        self._now_timer.start(5 * 60 * 1000)

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

    def _shell_stack(self):
        # @return: the shell's QStackedWidget that hosts every view
        from PySide6.QtWidgets import QStackedWidget
        return self.centralWidget().findChild(QStackedWidget, "stack")

    def _goto_tab(self, index):
        # Switches the shell's view. The name is kept (Interfaz 1.0): every
        # deep link in the file calls _goto_tab(TAB_*). While an update's
        # Data step is unacknowledged, Welcome is a gate: nothing else can
        # be opened until "Got it".
        if getattr(self, "_welcome_gate", False) and index != VIEW_WELCOME:
            return
        # The workbench stays alive when another view is opened (ADR-047:
        # its plate and stretch survive); its workers are only shut down
        # when the app itself closes (MainWindow.closeEvent -> ufe.close).
        self._shell_stack().setCurrentIndex(index)
        self._sync_sky_bar(index)
        if index != VIEW_UFE:
            # the workbench's tool windows (Blink, Calibrate, Annotate, the
            # series) are floating windows of its page: they must not hang
            # over the view the observer just opened. The workbench itself
            # stays alive (ADR-047).
            ufe = getattr(self, "_ufe", None)
            leave = getattr(ufe, "leave_view", None)
            if callable(leave):
                leave()
        if index == VIEW_PROJECTS:
            self._sync_projects_pane()

    def _sync_sky_bar(self, index):
        # The night (Moon, darkness, planets and the event chips) lives in
        # the navigation row and is useful while planning. Inside the image
        # workbench it is only noise: the observer is looking at a plate, not
        # at tonight, and the row is the one piece of chrome the workbench
        # cannot hide. Asked for: out of the UFE, in everywhere else.
        # @args: index - the view just opened
        # @return: None. The bar is HIDDEN, never destroyed, so its state
        #          (texts, chips) is where it was when the observer returns;
        #          the refresh is skipped while it is out of sight and run
        #          again on the way back, so nothing is rebuilt for nobody.
        bar = getattr(self, "_sky_bar", None)
        if bar is None:
            return
        if index == VIEW_UFE:
            self._sky_bar_out = True
            bar.setVisible(False)
            return
        if getattr(self, "_sky_bar_out", False):
            self._sky_bar_out = False
            bar.setVisible(True)
            # the bar was frozen while the workbench was open: tonight has
            # moved (or the site has), so it is filled again on the way back
            self.refresh_sky_bar()
        else:
            bar.setVisible(True)

    # ---------------- navigation history (Interfaz 1.1, ADR-056) ---------

    def _current_location(self):
        # @return: the location the app is on right now, as a hashable
        #          tuple (view, project id, tab key, campaign id)
        pid = self._current_project["id"] if self._current_project else None
        return (self._shell_stack().currentIndex(), pid,
                getattr(self, "_active_tab", None), self._selected_campaign_id())

    def navigate(self, view, pid=None, tab=None, cid=None, replace=False):
        # The single entry for user navigation: records the current
        # location on the back stack (unless replace), clears the forward
        # stack and applies the new one. Applying never records.
        # @args: view - a VIEW_* index; pid/tab/cid - the state to restore;
        #        replace - drop the current location instead of stacking it
        loc = (view, pid, tab, cid)
        if getattr(self, "_navigating", False):
            self._apply_location(loc)
            return
        cur = self._current_location()
        if cur == loc:
            return
        if replace:
            if self._nav_back and self._nav_back[-1] == cur:
                self._nav_back.pop()
        else:
            self._nav_back.append(cur)
        self._nav_fwd.clear()
        self._navigating = True
        try:
            self._apply_location(loc)
        finally:
            self._navigating = False
        self._update_nav_bar()

    def _apply_location(self, loc):
        # Restores a location WITHOUT recording it (used by navigate and by
        # back/forward). A missing project is skipped to Home.
        # @args: loc - (view, pid, tab, cid)
        view, pid, tab, cid = loc
        if view == VIEW_PROJECTS and pid is not None:
            self._goto_tab(VIEW_PROJECTS)
            if project.get(db, pid) is None:
                # the project was deleted while it was in the history
                self._goto_tab(VIEW_HOME)
                return
            if (self._current_project or {}).get("id") == pid:
                # same project: a tab change is NOT a rebuild (only the
                # page switches), or every click would wipe the pages
                if tab:
                    self._show_tab(tab)
                return
            # different project: keep the list highlight in sync WITHOUT
            # re-entering _project_selected (signals blocked), open once
            lst = self.projects.lst_projects
            was_blocked = lst.signalsBlocked()
            lst.blockSignals(True)
            try:
                self._select_project_row(pid)
            finally:
                lst.blockSignals(was_blocked)
            if not self._open_project(pid):
                # the project was deleted while it was in the history:
                # fall back to the hub
                self._goto_tab(VIEW_HOME)
                return
            if tab:
                self._show_tab(tab)
            return
        if view == VIEW_CAMPAIGNS:
            self._goto_tab(VIEW_CAMPAIGNS)
            self._refresh_campaigns_tab()
            if cid is not None:
                lst = self.campaigns.lst_campaigns
                for i in range(lst.count()):
                    if lst.item(i).data(Qt.UserRole) == cid:
                        lst.setCurrentRow(i)
                        break
            return
        if view == VIEW_WELCOME:
            self._ensure_welcome()
            # the page is built once and reused: who is looking at it can
            # have changed (a project was created, an update was sealed)
            self._sync_welcome()
        self._goto_tab(view)

    def back(self):
        # Goes to the previous location. Blocked while Welcome gates the
        # app (an unacknowledged update). An open drawer closes first.
        if getattr(self, "_welcome_gate", False):
            return
        if getattr(self, "_drawer", None) is not None and self._drawer.isVisible():
            self._drawer_open(False)
            return
        if not self._nav_back:
            return
        cur = self._current_location()
        loc = self._nav_back.pop()
        self._nav_fwd.append(cur)
        self._navigating = True
        try:
            self._apply_location(loc)
        finally:
            self._navigating = False
        self._update_nav_bar()

    def forward(self):
        # Re-applies the location we just left with back().
        if getattr(self, "_welcome_gate", False) or not self._nav_fwd:
            return
        cur = self._current_location()
        loc = self._nav_fwd.pop()
        self._nav_back.append(cur)
        self._navigating = True
        try:
            self._apply_location(loc)
        finally:
            self._navigating = False
        self._update_nav_bar()

    def home(self):
        # Back to the hub (the root of the app).
        self.navigate(VIEW_HOME)

    def _update_nav_bar(self):
        # Paints the navigation bar (buttons + breadcrumb). Guarded so the
        # history model works before the bar exists (early construction).
        back = getattr(self._menus, "btn_nav_back", None)
        if back is None:
            return
        gate = getattr(self, "_welcome_gate", False)
        back.setEnabled(bool(self._nav_back) and not gate)
        fwd = getattr(self._menus, "btn_nav_fwd", None)
        if fwd is not None:
            fwd.setEnabled(bool(self._nav_fwd) and not gate)
        crumbs = getattr(self._menus, "lbl_crumbs", None)
        if crumbs is not None:
            crumbs.setText(self._crumbs_html())

    def _breadcrumb(self):
        # @return: [(label, view, pid, tab, cid)] from Home to here
        loc = self._current_location()
        view, pid, tab, _cid = loc
        crumbs = []
        if view == VIEW_WELCOME:
            crumbs.append((self.tr("Welcome"), VIEW_WELCOME, None, None, None))
            return crumbs
        # Interfaz 1.6: the projects view holds the list AND the project, so
        # the project is a second crumb of the SAME view (the pid is what
        # tells the two states apart, not the index).
        crumbs.append((self.tr("Projects"), VIEW_PROJECTS, None, None, None))
        if view == VIEW_TONIGHT:
            crumbs.append((self.tr("New project"), VIEW_TONIGHT,
                           None, None, None))
        elif view == VIEW_CAMPAIGNS:
            crumbs.append((self.tr("Campaigns"), VIEW_CAMPAIGNS,
                           None, None, None))
        elif view == VIEW_PROJECTS and pid is not None:
            p = project.get(db, pid) or self._current_project or {}
            name = p.get("object_name") or "?"
            crumbs.append((name, VIEW_PROJECTS, pid, None, None))
            if tab:
                crumbs.append((self._tab_label(tab), VIEW_PROJECTS, pid, tab,
                               None))
        elif view == VIEW_UFE and pid is not None:
            p = project.get(db, pid) or self._current_project or {}
            crumbs.append((p.get("object_name") or "?", VIEW_PROJECTS, pid,
                           None, None))
            crumbs.append((self.tr("Image Workbench"), VIEW_UFE, pid,
                           None, None))
        return crumbs

    def _crumb_href(self, view, pid, tab, cid):
        # @return: the internal link a breadcrumb segment points at.
        #   Interfaz 1.6: the projects view answers two links, the list
        #   ("nav:home") and one project ("nav:project:<id>"), and the pid
        #   is what tells them apart now that both share a view index.
        if view == VIEW_PROJECTS:
            if pid is None:
                return "nav:home"
            base = f"nav:project:{pid}"
            return f"{base}:{tab}" if tab else base
        if view == VIEW_TONIGHT:
            return "nav:tonight"
        if view == VIEW_CAMPAIGNS:
            return "nav:campaigns"
        if view == VIEW_WELCOME:
            return "nav:welcome"
        if view == VIEW_UFE:
            return f"nav:ufe:{pid}" if pid is not None else "nav:ufe"
        return "nav:home"

    def _crumbs_html(self):
        # @return: the breadcrumb as rich text with clickable segments
        import html as _html
        items = self._breadcrumb()
        parts = []
        for i, (label, view, pid, tab, cid) in enumerate(items):
            if i == len(items) - 1:
                parts.append(
                    '<span style="color:%s;font-weight:600">%s</span>'
                    % (theme.C_TEXT, _html.escape(str(label))))
            else:
                parts.append(
                    '<a href="%s" style="color:%s;text-decoration:none">%s</a>'
                    % (self._crumb_href(view, pid, tab, cid), theme.C_ACCENT,
                       _html.escape(str(label))))
        # the tree reads with arrows: Home → project → tab. The separator
        # is the dim text colour, not the border line: on the dark bar the
        # line colour made the arrows almost invisible.
        sep = ' <span style="color:%s">→</span> ' % theme.C_TEXT_DIM
        return sep.join(parts)

    def _crumb_clicked(self, url):
        # @args: url - a nav:* link from the breadcrumb
        if url == "nav:home":
            self.home()
        elif url == "nav:tonight":
            self.navigate(VIEW_TONIGHT)
        elif url == "nav:campaigns":
            self.navigate(VIEW_CAMPAIGNS)
        elif url == "nav:welcome":
            self.navigate(VIEW_WELCOME)
        elif url.startswith("nav:ufe"):
            self.navigate(VIEW_UFE)
        elif url.startswith("nav:project:"):
            rest = url.split(":")[2:]
            try:
                pid = int(rest[0])
            except (ValueError, IndexError):
                return
            tab = rest[1] if len(rest) > 1 else None
            self.navigate(VIEW_DETAIL, pid=pid, tab=tab)

    # ---------------- shell construction (Interfaz 1.0, ADR-053) ----------

    def _build_shell(self):
        # The widgets are the SAME as before, re-hosted full-screen in a
        # QStackedWidget. The projects_tab husk keeps its registered child
        # attributes (self.projects.lst_projects and friends), so no other
        # code had to move: its two halves are reparented into the Home
        # view (attention dashboard + project list) and the Detail view
        # (the project page). The old QTabWidget is gone.
        from PySide6.QtWidgets import QWidget, QVBoxLayout
        self.tonight = _load_ui("tonight_tab")
        self.projects = _load_ui("projects_tab")
        self.campaigns = _load_ui("campaigns_tab")
        proj = self.projects
        stack = self._shell_stack()

        # The projects view (Interfaz 1.6): header, then the list and the
        # project side by side with a splitter between them. The old design
        # pulled the two halves into separate shell pages, so opening a
        # project threw the list away; together they let you move between
        # projects without leaving the view, and the splitter is what makes
        # the list's width the observer's choice.
        home = QWidget()
        hl = QVBoxLayout(home)
        hl.setContentsMargins(12, 10, 12, 10)
        hl.setSpacing(8)
        from PySide6.QtWidgets import (QFrame, QLabel, QHBoxLayout,
                                       QPushButton, QSplitter)
        # header: "My projects" + the prominent new-project tile
        head = QFrame()
        head.setObjectName("homeHead")
        hlay = QHBoxLayout(head)
        hlay.setContentsMargins(0, 0, 0, 0)
        title = QLabel(self.tr("My projects"))
        title.setObjectName("homeTitle")
        hlay.addWidget(title)
        hlay.addStretch(1)
        newtile = QPushButton(self.tr("+ NEW PROJECT"))
        newtile.setObjectName("newTile")
        newtile.setCursor(Qt.PointingHandCursor)
        newtile.setToolTip(self.tr("Create a project from tonight's targets"))
        newtile.clicked.connect(self._new_project_view)
        hlay.addWidget(newtile)
        hl.addWidget(head)
        # the splitter: list left, project right. Neither side collapses by
        # accident (childrenCollapsible False); the « button is the one that
        # hides the list, on purpose.
        split = QSplitter(Qt.Horizontal)
        split.setObjectName("projectsSplit")
        split.setChildrenCollapsible(False)
        split.setHandleWidth(6)
        self._projects_split = split
        # left: the list. It stops being a QGroupBox: a bordered box inside
        # the page was a box inside a box, and its title said nothing.
        lst = proj.grp_list
        proj.layout().removeWidget(lst)
        lst.setTitle("")
        lst.setObjectName("projectsListPanel")
        self.projects.btn_new_project.setVisible(False)
        split.addWidget(lst)
        # right: the detail stack, whose resting page is the night panel
        right = QFrame()
        right.setObjectName("projectsDetailPanel")
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(10, 0, 0, 0)
        rlay.setSpacing(0)
        rlay.addWidget(proj.stack_detail)
        split.addWidget(right)
        split.setStretchFactor(0, 0)      # the list keeps the width it is given
        split.setStretchFactor(1, 1)      # the project takes what is left
        # the list, and only the list, can fold: the « button does it and »
        # brings it back at the width it had. The project pane never
        # collapses (a view with nothing in it is not a state)
        split.setCollapsible(0, True)
        split.setCollapsible(1, False)
        hl.addWidget(split, 1)
        self._restore_list_width()
        split.splitterMoved.connect(self._on_splitter_moved)
        # double click on the handle = back to the default width (dragging
        # something to a bad place needs an undo that is not a preference
        # dialog)
        handle = split.handle(1)
        if handle is not None:
            handle.installEventFilter(self)
            handle.setToolTip(self.tr(
                "Drag to resize the list; double click to reset"))
        # the width is applied on the splitter's FIRST real resize: at build
        # time it has none, and setSizes on a zero-width splitter does
        # nothing (which is how the remembered width quietly got lost)
        split.installEventFilter(self)
        # Interfaz 1.6: the campaigns strip is gone from the bottom (it was
        # a 45 px bar holding a single link). Campaigns is now a button in
        # the header, next to the new-project tile, where the eye already is.
        self._camp_btn = QPushButton(self.tr("Campaigns →"))
        self._camp_btn.setObjectName("campTile")
        self._camp_btn.setCursor(Qt.PointingHandCursor)
        self._camp_btn.setToolTip(self.tr(
            "Observing campaigns: several projects sharing a protocol"))
        self._camp_btn.clicked.connect(self._tools_campaigns)
        hlay.insertWidget(hlay.count() - 1, self._camp_btn)

        # the night panel takes the resting page of the detail stack
        self._build_night_panel()

        stack.addWidget(home)            # VIEW_PROJECTS (home + detail)
        stack.addWidget(self.tonight)    # VIEW_TONIGHT
        stack.addWidget(self.campaigns)  # VIEW_CAMPAIGNS
        # Fixed placeholder pages for the lazily built views: the stack
        # ALWAYS has five pages, so VIEW_WELCOME (3) and VIEW_UFE (4) are
        # valid whatever order the views are first opened in. Building them
        # with addWidget() instead would append them at whatever free index
        # and the constants would be wrong (the bug that hid the workbench).
        self._welcome_page = QWidget()
        stack.addWidget(self._welcome_page)      # VIEW_WELCOME
        self._ufe_page_widget = QWidget()
        stack.addWidget(self._ufe_page_widget)   # VIEW_UFE
        stack.setCurrentIndex(VIEW_HOME)
        self._sync_projects_pane()
        # Interfaz 1.0: the new-project search bar sits at the top of the
        # Tonight view (the manual search moved out of Tools). Tonight's
        # own .ui is untouched: the bar is a shell widget inserted above it.
        from .widgets.new_project_bar import NewProjectBar
        self._newbar = NewProjectBar()
        self._newbar.create_target.connect(self._new_project_from_target)
        self.tonight.layout().insertWidget(0, self._newbar)
        # the Tonight full table starts collapsed
        self.tonight.grp_list.setVisible(False)
        self._prepare_table()
        # remember and restore the Tonight kind filter (WORKFLOWS 7quater)
        self._rebuild_kind_filters()
        saved = config.get("tonight_kind", "") or None
        if saved and self.tonight.cmb_filter.findData(saved) >= 0:
            self.tonight.cmb_filter.setCurrentIndex(
                self.tonight.cmb_filter.findData(saved))

        # A3: restore the projects hub classification prefs
        self.projects.cmb_kind.setCurrentIndex(
            int(config.get("projects_filter_kind", 0)))
        sort_idx = int(config.get("projects_filter_sort_v2", 0))
        sort_idx = max(0, min(sort_idx, self.projects.cmb_sort.count() - 1))
        self.projects.cmb_sort.setCurrentIndex(sort_idx)
        self.projects.chk_favorites.setChecked(
            bool(config.get("projects_filter_fav", False)))
        # UX-PC (U1): the advanced filters row starts collapsed; the toggle
        # restores the user's last choice
        filters_open = bool(config.get("projects_filters_open", False))
        self.projects.filters_box.setVisible(filters_open)
        self.projects.btn_filters.blockSignals(True)
        self.projects.btn_filters.setChecked(filters_open)
        self.projects.btn_filters.setText(
            self.tr("Filters ▾") if filters_open else self.tr("Filters ▸"))
        self.projects.btn_filters.blockSignals(False)
        self._build_drawer()
        self._build_sky_bar()
        # Interfaz 1.0 (ADR-053): Welcome only when it is needed: a first
        # run (no observatory), a pending update (a newer version than the
        # one last run) or no projects at all. Otherwise the app opens on
        # Home, ready and offline.
        from . import wizard as _wz
        self._fresh = not config.is_configured()
        self._update_due = _wz._wizard_needed(config.get("app_version") or "")
        if self._fresh or self._update_due or not project.list_projects(db):
            self._show_welcome()
        else:
            self._goto_tab(VIEW_HOME)

    def _ensure_welcome(self):
        # Builds the Welcome view into its fixed page ONCE. Shared by the
        # startup decision (_show_welcome) and the manual entry
        # (navigate(VIEW_WELCOME)) so both build the same widget.
        # @return: the WelcomeSetup
        if self._welcome is not None:
            return self._welcome
        from .widgets.welcome_setup import WelcomeSetup
        from PySide6.QtWidgets import QVBoxLayout
        self._welcome = WelcomeSetup(snapshot=self._snapshot)
        self._welcome.create_project.connect(self._welcome_create)
        self._welcome.finished.connect(self._welcome_finished)
        # "Explore first": a first run is not a gate, so the observer may
        # walk away from the setup and land on the projects (Interfaz 1.4)
        self._welcome.skip.connect(self._welcome_skip)
        # "See the full guide" opens the PUBLISHED guide (the HTML site,
        # ADR-070), the same page as Help > User guide (web), in the app's
        # language: the in-app markdown browser stays under Help > Technical
        # Documentation.
        self._welcome.open_guide.connect(self.on_guide_web)
        self._welcome.open_skycal.connect(self._tools_skycal)
        lay = QVBoxLayout(self._welcome_page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._welcome)
        return self._welcome

    def _sync_welcome(self):
        # Tells the Welcome view WHO is looking at it (Interfaz 1.5): does
        # the observer already have projects (which flips the call to
        # action), and is this the post-update notice (which rewrites the
        # hero and leaves a single action with the report). The page is
        # built once and lives as long as the window, so this runs on every
        # entry, not only at build time.
        if self._welcome is None:
            return
        from . import wizard as _wz
        self._welcome.set_context(
            has_projects=bool(project.list_projects(db)),
            update_version=(_wz._display_version()
                            if self._welcome_gate else None))

    def _show_welcome(self):
        # Startup decision (first run / update / no projects): builds
        # Welcome and makes it current. An update is a blocking gate (the
        # data report is read before the app is usable); a first run is not.
        self._ensure_welcome()
        self._welcome_gate = bool(self._update_due
                                  and self._snapshot is not None)
        self._sync_welcome()
        # Only a REAL update lands on the data report (the gate). A first
        # run has no database to report on, so jumping to step 3 there
        # would open the app on a paragraph about a file that does not
        # exist yet: it starts at the observatory, which is the first thing
        # an observer can actually answer (Interfaz 1.4).
        if self._welcome_gate:
            self._welcome.show_step("data")
        self._shell_stack().setCurrentIndex(VIEW_WELCOME)
        self._update_vtab_visibility()

    def _welcome_finished(self):
        # "Got it" on the Data step. Only a REAL update seals the version
        # (and unlocks Home); a manual visit just goes back (Interfaz 1.1).
        if self._update_due:
            if self._welcome is not None:
                self._welcome.ack_data()
            self._update_due = False
            self._welcome_gate = False
            self.on_refresh_projects()
            self.navigate(VIEW_HOME, replace=True)
            return
        if self._nav_back:
            self.back()
        else:
            self.navigate(VIEW_HOME, replace=True)

    def _welcome_skip(self):
        # "Explore first" on Welcome. A pending update is still a gate (its
        # report must be read once), so the skip is honoured only when the
        # app is otherwise free; on a first run it simply lands on Home.
        if self._welcome_gate:
            return
        self.navigate(VIEW_HOME, replace=True)

    def _welcome_create(self):
        # The CTA: persist the setup, acknowledge a pending update (the
        # report was seen) and open the new-project view, replacing Welcome.
        if self._update_due and self._welcome is not None:
            self._welcome.ack_data()
            self._update_due = False
            self._welcome_gate = False
        self.navigate(VIEW_TONIGHT, replace=True)

    def _visit_window(self):
        # @return: the visit window that is open right now, or None. The
        #          visits panel owns it (one at a time); we only look.
        panel = getattr(self, "_project_widgets", {}).get("visits_panel")
        win = getattr(panel, "_win", None) if panel is not None else None
        if win is None or not Shiboken.isValid(win):
            return None
        return win

    def _ufe_enter(self):
        # The workbench took the screen: get the visit window out of the
        # way. Hidden, not closed: it is the same visit when you come back,
        # and the workbench has its own frame navigator for measuring.
        # @return: None
        win = self._visit_window()
        self._visit_win_hidden = None
        if win is not None and win.isVisible():
            self._visit_win_hidden = win
            win.hide()

    def _ufe_leave(self):
        # Leaving the workbench: the visit window comes back, in front.
        # @return: None
        win = getattr(self, "_visit_win_hidden", None)
        self._visit_win_hidden = None
        if win is None or not Shiboken.isValid(win):
            return
        # a project change while it was hidden closes the panel's window;
        # a stale reference must not resurrect it
        if win is not self._visit_window():
            return
        win.show()
        win.raise_()
        win.activateWindow()

    def _build_night_panel(self):
        # Interfaz 1.6: the resting page of the detail pane. An empty pane
        # is a wasted pane, so when nothing is selected it shows tonight
        # (same painted sky and same brief as Welcome) and the way in to a
        # new project.
        from .ui_loader import drop_in
        from .widgets.night_panel import NightPanel
        host = self.projects.nightPanelHost
        self._night_panel = NightPanel()
        self._night_panel.create_project.connect(self._new_project_view)
        self._night_panel.set_animations(
            bool(config.get("ui_animations", True)))
        drop_in(host.parentWidget().layout(), host, self._night_panel)

    def _sync_projects_pane(self):
        # The right pane shows the project, or the night when there is
        # none. One place, so the two can never both be right.
        # @return: None
        if getattr(self, "_night_panel", None) is None:
            return
        stack = self.projects.stack_detail
        page = (self.projects.page_detail if self._current_project
                else self.projects.page_night)
        if stack.currentWidget() is not page:
            stack.setCurrentWidget(page)

    def _restore_list_width(self):
        # @return: None. The list's width belongs to the observer (it is
        #          the splitter) and is remembered between runs.
        try:
            width = int(config.get("projects_list_width") or 0)
        except (TypeError, ValueError):
            width = 0
        if width <= 0:
            width = _LIST_W_DEFAULT
        self._list_width = max(_LIST_W_MIN, min(_LIST_W_MAX, width))
        # deferred: at build time the splitter has no width yet, and
        # setSizes() SCALES the numbers when their sum does not match the
        # widget, so [400, 1200] on a 1000 px splitter would give 250
        QTimer.singleShot(0, self._apply_list_width)

    def _apply_list_width(self, width=None):
        # @args: width - the list's width to apply, or None for the one
        #        remembered. Reads the splitter's REAL width on purpose:
        #        QSplitter::setSizes distributes proportionally when the sum
        #        of the sizes differs from the widget's, which is how a
        #        request for 400 px quietly became 250.
        # @return: None
        total = self._projects_split.width()
        if total <= 0:
            return
        if width is None:
            width = getattr(self, "_list_width", _LIST_W_DEFAULT)
        # the project pane keeps a floor: a list that eats the whole view is
        # not a width, it is a mistake
        width = max(0, min(int(width), max(0, total - 200)))
        self._projects_split.setSizes([width, total - width])

    def _on_splitter_moved(self, _pos, _index):
        # Remembers where the divider was left. A single-shot timer because
        # splitterMoved fires on every pixel of the drag, and the settings
        # file has no business taking that many writes.
        sizes = self._projects_split.sizes()
        if sizes and sizes[0] > 20:
            self._list_width = sizes[0]
        if getattr(self, "_split_save", None) is None:
            self._split_save = QTimer(self)
            self._split_save.setSingleShot(True)
            self._split_save.setInterval(400)
            self._split_save.timeout.connect(
                lambda: config.set("projects_list_width", self._list_width))
        self._split_save.start()

    def _toggle_list(self, show):
        # @args: show - True brings the list back at the width it had,
        #        False folds it away. The « / » buttons of the list header.
        if show:
            self._apply_list_width()
        else:
            sizes = self._projects_split.sizes()
            if sizes and sizes[0] > 20:
                self._list_width = sizes[0]
            self._apply_list_width(0)

    def eventFilter(self, obj, event):
        split = getattr(self, "_projects_split", None)
        # The remembered width lands on the splitter's first real resize:
        # before that it has no width and setSizes is a no-op.
        if (split is not None and obj is split
                and event.type() == QEvent.Resize
                and not getattr(self, "_list_width_applied", False)):
            self._list_width_applied = True
            self._apply_list_width()
            return False
        # Double click on the splitter handle: back to the default width.
        # Dragging something into a bad place needs an undo that is not a
        # preferences dialog.
        if (event.type() == QEvent.MouseButtonDblClick
                and split is not None
                and obj is split.handle(1)):
            self._list_width = _LIST_W_DEFAULT
            self._apply_list_width(_LIST_W_DEFAULT)
            config.set("projects_list_width", _LIST_W_DEFAULT)
            return True
        return super().eventFilter(obj, event)

    def _build_sky_bar(self):
        # Interfaz 1.6: the night in the navigation row. It replaces the
        # "What's up in the sky" band that Home used to carry: the row
        # already had the room (28 px buttons, 20 px chips), so the band's
        # ~60 px go back to the projects list, and the Moon and the
        # darkness window are visible from EVERY view, not only from Home.
        from .ui_loader import drop_in
        from .widgets.sky_bar import SkyBar
        host = self._menus.skyHost
        self._sky_bar = SkyBar()
        self._sky_bar.calendar_clicked.connect(self._tools_skycal)
        drop_in(host.parentWidget().layout(), host, self._sky_bar)
        # the sky-event chips land in the bar from now on
        self._sky_chips_row = self._sky_bar.chips
        # the workbench hides the whole bar (see _sync_sky_bar): the flag is
        # the source of truth, not isVisible(), which is also False before
        # the window is first shown
        self._sky_bar_out = False
        self.refresh_sky_bar()

    def refresh_sky_bar(self):
        # Recomputes the bar from the site. All local ephemeris, so it can
        # afford to run whenever the site or the clock may have moved.
        # @return: None. While the workbench has the bar hidden (it is out of
        #          sight) the work is skipped: the chips are rebuilt on the
        #          way back (see _sync_sky_bar), and nothing is computed for
        #          a row nobody can see.
        if getattr(self, "_sky_bar_out", False):
            return
        from ..core import night_brief as nb
        try:
            lat = float(config.get("lat") or 0.0)
            lon = float(config.get("lon") or 0.0)
        except (TypeError, ValueError):
            lat = lon = 0.0
        brief = nb.brief(lat, lon) if (lat or lon) else None
        self._sky_bar.refresh(brief)
        # the events are local maths too (ADR-040): the bar can fill its
        # chips without waiting for the planner to run
        self._skyevent_chips()

    def _build_drawer(self):
        # The overlay project drawer: a compact list summoned by the
        # vertical tab from any view. A scrim dims the content behind it.
        from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout,
                                       QLabel, QPushButton, QListWidget)
        cw = self.centralWidget()
        self._scrim = QFrame(cw)
        self._scrim.setObjectName("shell_scrim")
        self._scrim.setStyleSheet("background: rgba(7,8,13,150);")
        self._scrim.hide()
        self._scrim.mousePressEvent = lambda _e: self._drawer_open(False)
        self._drawer = QFrame(cw)
        self._drawer.setObjectName("shell_drawer")
        self._drawer.setStyleSheet(
            "QFrame#shell_drawer { background: %s;"
            " border-right: 1px solid %s; }" % (theme.C_BASE, theme.C_LINE))
        lay = QVBoxLayout(self._drawer)
        lay.setContentsMargins(12, 12, 12, 12)
        head = QHBoxLayout()
        title = QLabel(self.tr("Projects"))
        title.setStyleSheet("font-weight: 700; font-size: 14px;")
        head.addWidget(title)
        head.addStretch(1)
        close = QPushButton("✕")
        close.setFlat(True)
        close.setFixedWidth(28)
        # compact="true": the global 6px/16px padding leaves a 28 px button
        # no content rect, and the ✕ drew as an empty box (same fix the
        # row-removal × and the step ✕ already carry)
        close.setProperty("compact", True)
        close.clicked.connect(lambda: self._drawer_open(False))
        head.addWidget(close)
        lay.addLayout(head)
        # Interfaz 1.1: Home and Welcome at the top of the switcher
        navrow = QHBoxLayout()
        home_btn = QPushButton(self.tr("⌂ Home"))
        home_btn.setFlat(True)
        home_btn.clicked.connect(self._drawer_home)
        navrow.addWidget(home_btn)
        welcome_btn = QPushButton(self.tr("ⓘ Welcome"))
        welcome_btn.setFlat(True)
        welcome_btn.setToolTip(self.tr("Setup guide and observatory"))
        welcome_btn.clicked.connect(self._drawer_welcome)
        navrow.addWidget(welcome_btn)
        navrow.addStretch(1)
        lay.addLayout(navrow)
        self._drawer_list = QListWidget()
        self._drawer_list.setObjectName("drawer_list")
        self._drawer_list.itemClicked.connect(self._drawer_row_clicked)
        lay.addWidget(self._drawer_list, 1)
        newp = QPushButton(self.tr("+ New project…"))
        newp.clicked.connect(self._drawer_new_project)
        lay.addWidget(newp)
        self._drawer.hide()

    def _drawer_open(self, on):
        # @args: on - show (True) or hide (False) the overlay drawer
        # Interfaz 1.3: on Home the list IS the screen, so the drawer is
        # not available there (the vertical tab is hidden too).
        if on and self._shell_stack().currentIndex() == VIEW_HOME:
            return
        if on:
            self._refresh_drawer()
            self._position_overlay()
            self._scrim.show()
            self._scrim.raise_()
            self._drawer.show()
            self._drawer.raise_()
        else:
            self._drawer.hide()
            self._scrim.hide()

    def _position_overlay(self):
        # Places the drawer and the scrim over the content area (right of
        # the vertical tab). Called on open and on every resize.
        cw = self.centralWidget()
        vw = getattr(self._menus, "btn_vtab", None)
        vw = vw.width() if vw is not None else 28
        rect = cw.rect()
        self._scrim.setGeometry(vw, 0, rect.width() - vw, rect.height())
        # 430 px: enough for the rich project row (icon + name + sparkline)
        self._drawer.setGeometry(vw, 0,
                                 min(430, rect.width() - vw), rect.height())

    def _refresh_drawer(self):
        # Interfaz 1.1: the overlay drawer shows the SAME rich rows as the
        # hub list (same ProjectRow, same payload), built from the data of
        # the last refresh so the two cannot drift.
        self._drawer_list.clear()
        projects_list = getattr(self, "_last_projects_list", None)
        if projects_list is None:
            return
        attn_map = getattr(self, "_last_attn_map", {}) or {}
        camp_names = getattr(self, "_last_camp_names", {}) or {}
        current_id = (self._current_project or {}).get("id")
        for p in projects_list:
            item = QListWidgetItem(f"[{p['kind']}] {p['object_name']}")
            item.setData(Qt.UserRole, p["id"])
            # the item's height must carry the row's fixed 74 px
            # the item's height must carry the row's fixed height (the
            # rich row is a widget over the item, so the item has to be
            # told how tall it is)
            item.setSizeHint(QSize(0, _PROJECT_ROW_H))
            self._drawer_list.addItem(item)
            row = self._project_row_widget(p, attn_map.get(p["id"]),
                                           camp_names)
            row.clicked.connect(
                lambda it=item: self._drawer_row_clicked(it))
            row.double_clicked.connect(
                lambda it=item: self._drawer_row_clicked(it))
            self._drawer_list.setItemWidget(item, row)
            if p["id"] == current_id:
                row.set_selected(True)

    def _drawer_row_clicked(self, item):
        pid = item.data(Qt.UserRole)
        self._drawer_open(False)
        if pid is not None:
            self.navigate(VIEW_DETAIL, pid=pid)

    def _drawer_new_project(self):
        self._drawer_open(False)
        self._new_project_view()

    def _drawer_home(self):
        self._drawer_open(False)
        self.home()

    def _drawer_welcome(self):
        self._drawer_open(False)
        self.navigate(VIEW_WELCOME)

    def _new_project_view(self):
        # Interfaz 1.0: the new-project view (Tonight on demand + the
        # embedded search/manual form). The hub's "New project…" and the
        # drawer both land here, focusing the search.
        self.navigate(VIEW_TONIGHT)
        bar = getattr(self, "_newbar", None)
        if bar is not None:
            bar.edt_search.setFocus()

    def _chip_band(self, title, variant="sky", link=None):
        # A slim Home band that hosts a row of clickable chips (sky events,
        # SN cadence). Hidden while it has no chips. Interfaz 1.2: the
        # variant picks the accent stripe (sky = blue, cadence = orange) and
        # an optional right-side link button.
        # @args: title - the band's small header; variant - "sky"|"cadence";
        #        link - (text, slot) for a trailing link button, or None
        # @return: (the band QFrame, its chips QHBoxLayout)
        from PySide6.QtWidgets import (QFrame, QLabel, QHBoxLayout,
                                       QVBoxLayout, QPushButton)
        band = QFrame()
        band.setObjectName("skyBand" if variant == "sky" else "cadenceBand")
        lay = QVBoxLayout(band)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(6)
        headrow = QHBoxLayout()
        head = QLabel(title)
        head.setObjectName("bandHead")
        head.setStyleSheet("color: %s;" % (
            theme.C_ACCENT if variant == "sky" else theme.C_WARN))
        headrow.addWidget(head)
        headrow.addStretch(1)
        if link is not None:
            btn = QPushButton(link[0])
            btn.setFlat(True)
            btn.setStyleSheet(
                "color: %s; text-align: right; padding: 0; border: none;"
                % theme.C_ACCENT)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(link[1])
            headrow.addWidget(btn)
        lay.addLayout(headrow)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        lay.addLayout(row)
        band.setVisible(False)
        return band, row

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
        self._menus.action_guide_web.triggered.connect(self.on_guide_web)
        self._menus.action_log.triggered.connect(self.on_open_log)
        self._menus.action_assistant.triggered.connect(
            lambda: self._open_assistant())
        # keep the "enabled" tooltip; the disabled state swaps in its reason
        self._assistant_tip = self._menus.action_assistant.toolTip()
        self._menus.action_welcome.triggered.connect(
            lambda: self.navigate(VIEW_WELCOME))
        self._menus.action_explore.triggered.connect(self._tools_explore)
        # the navigation row's own door to Explore (always visible)
        self._menus.edt_nav_explore.returnPressed.connect(self._nav_explore)
        self._menus.action_campaigns.triggered.connect(
            self._tools_campaigns)

    def _refresh_ai_availability(self):
        # The AI master switch (ADR-075). Off, every AI surface is closed,
        # not left to fail: the Help action and the editor's "?" button are
        # disabled, with the reason in their tooltip. The Publish page is
        # rebuilt each time its project opens, so it reads the switch itself.
        # @return: None
        from ..core.sources import llm
        on = llm.is_enabled(config)
        menus = getattr(self, "_menus", None)
        act = getattr(menus, "action_assistant", None)
        if act is not None:
            act.setEnabled(on)
            tip = getattr(self, "_assistant_tip", None)
            if tip is None:
                tip = act.toolTip()
            act.setToolTip(tip if on else self.tr(
                "The AI is off: turn it on in Settings → Integrations."))
        ufe = getattr(self, "_ufe", None)
        if ufe is not None and hasattr(ufe, "set_ai_available"):
            ufe.set_ai_available(on)

    def _connect(self):
        t = self.tonight
        # Refresh the Projects hub list every time the user enters that
        # tab, so it is always up to date (UX-PC U1: the manual Refresh
        # fallback button is gone — the list never goes stale).
        self._shell_stack().currentChanged.connect(self._on_main_tab_changed)
        # the vertical tab toggles the overlay project drawer from any view
        self._menus.btn_vtab.clicked.connect(
            lambda: self._drawer_open(not self._drawer.isVisible()))
        # Interfaz 1.1: the navigation bar (back/forward/home/welcome and
        # the clickable breadcrumb)
        self._menus.btn_nav_back.clicked.connect(self.back)
        self._menus.btn_nav_fwd.clicked.connect(self.forward)
        self._menus.btn_nav_home.clicked.connect(self.home)
        self._menus.btn_nav_welcome.clicked.connect(
            lambda: self.navigate(VIEW_WELCOME))
        self._menus.lbl_crumbs.linkActivated.connect(self._crumb_clicked)
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
        p.btn_new_project.clicked.connect(self._new_project_view)
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
                lambda _=False, k=key: self._show_tab(k, record=True))
        # Interfaz 1.6: « folds the LIST pane (the splitter's left side) and
        # » brings it back with the width it had. The list and the project
        # share one page now, so folding is a matter of the splitter, not of
        # leaving the view.
        p.btn_hide_list.clicked.connect(lambda: self._toggle_list(False))
        p.btn_show_list.clicked.connect(lambda: self._toggle_list(True))
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
        for i, tab_idx in enumerate((VIEW_HOME, VIEW_TONIGHT,
                                     VIEW_CAMPAIGNS)):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(lambda idx=tab_idx: self.navigate(idx))
        # Interfaz 1.1: back/forward/home shortcuts
        for seq, fn in (("Alt+Left", self.back),
                        ("Alt+Right", self.forward),
                        ("Alt+Home", self.home)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(fn)
        # paint the bar for the initial view
        logo = theme.app_logo(20)
        if not logo.isNull():
            self._menus.lbl_nav_logo.setPixmap(logo)
        self._update_nav_bar()
        self._update_vtab_visibility()
        self._install_mouse_nav()

    def _open_url(self, url):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    # ---------------- menu: settings / help ----------------

    def _pick_astap(self, dlg):
        # Browse for the ASTAP executable (ADR-051).
        from PySide6.QtWidgets import QFileDialog
        path, _sel = QFileDialog.getOpenFileName(
            dlg, self.tr("Select the ASTAP executable"), "",
            self.tr("Executables (*)"))
        if path:
            dlg.edt_astap_path.setText(path)

    def _test_astap(self, dlg):
        # Probe the configured binary: does it exist and where (ADR-051).
        from PySide6.QtWidgets import QMessageBox
        from ..core.sources import astap
        rep = astap.probe(dlg.edt_astap_path.text().strip())
        QMessageBox.information(dlg, self.tr("ASTAP"), rep["message"])

    def _pick_findorb(self, dlg):
        # Browse for the Find_Orb executable (astrometry plan, D31: the
        # NON-interactive one; probe refuses the interactive program).
        from PySide6.QtWidgets import QFileDialog
        path, _sel = QFileDialog.getOpenFileName(
            dlg, self.tr("Select the Find_Orb executable"), "",
            self.tr("Executables (*)"))
        if path:
            dlg.edt_findorb_path.setText(path)

    def _test_findorb(self, dlg):
        # Probe the configured binary: `fo` exists, and it is not the
        # interactive Find_Orb (the mistake everybody makes once).
        from PySide6.QtWidgets import QMessageBox
        from ..core import findorb
        _path, message = findorb.probe(dlg.edt_findorb_path.text().strip())
        QMessageBox.information(dlg, self.tr("Find_Orb"), message)

    def _install_findorb(self, dlg):
        # ADR-062, D31: the guided installation of Find_Orb. Three steps,
        # in the order that saves the most work:
        #   1. is `fo` already on PATH? Then the program is installed and
        #      the app was never told, which is the common case: fill the
        #      path and say so.
        #   2. is there a package manager we can drive? Then offer the one
        #      command that installs it in a PRIVATE environment.
        #   3. otherwise, the guide: what to install and what to type.
        # The app never downloads a package manager on its own: fetching
        # and running a binary from the internet is the user's decision.
        # @args: dlg - the settings dialog
        # @return: None
        from ..core import findorb_install as fi
        worker = getattr(self, "_findorb_worker", None)
        if worker is not None and worker.isRunning():
            worker.cancel()
            return
        found = fi.find_on_path()
        if found:
            dlg.edt_findorb_path.setText(found)
            QMessageBox.information(dlg, self.tr("Find_Orb"), self.tr(
                "Find_Orb is already installed:\n%1\n\nThe path now points "
                "at it.").replace("%1", found))
            return
        name, manager = fi.find_manager()
        if manager is None:
            QMessageBox.information(dlg, self.tr("Install Find_Orb"),
                                    self._findorb_manual_text())
            return
        from .. import paths as paths_mod
        folder = QFileDialog.getExistingDirectory(
            dlg, self.tr("Folder for the Find_Orb environment"),
            str(paths_mod.data_dir()))
        if not folder:
            return
        target = str(Path(folder) / "findorb")
        plan = fi.install_plan(name, manager, target)
        if QMessageBox.question(
                dlg, self.tr("Install Find_Orb"),
                self.tr("Run this command?\n\n%1\n\nThe environment is "
                        "private, inside the folder you chose, so nothing "
                        "of your existing setup is touched. The download "
                        "takes a few minutes.").replace(
                            "%1", plan["what"])
        ) != QMessageBox.Yes:
            return
        self._findorb_install_start(dlg, manager, target)

    def _findorb_manual_text(self):
        # @return: the guide, in plain language, for the case the app
        #          cannot install Find_Orb for the observer
        return self.tr(
            "NightScribe did not find micromamba, mamba or conda, and it "
            "does not download a package manager on its own.\n\n"
            "The easy road on Linux and macOS is the conda-forge package "
            "\"findorb\": it brings the precompiled binaries and the DE430t "
            "ephemerides the perturbations need, in one command:\n\n"
            "    micromamba create -p ~/findorb -c conda-forge findorb\n\n"
            "On Windows, Project Pluto ships the binaries as zips: download "
            "the console version and the non-interactive fo, unpack both in "
            "the same folder (they share their configuration and the "
            "ephemerides) and point the path above at fo64.exe.\n\n"
            "The whole guide is in the documentation.")

    def _findorb_install_start(self, dlg, manager_path, target):
        # @args: dlg - the settings dialog, manager_path - the package
        #        manager, target - the private environment
        # @return: None. The manager's own output is streamed into the
        #          dialog's label: when an install fails, that log is the
        #          only thing that says why.
        from PySide6.QtWidgets import QProgressDialog
        from .workers import FindOrbInstallWorker
        prog = QProgressDialog(self.tr("Installing Find_Orb…"),
                               self.tr("Cancel"), 0, 0, dlg)
        prog.setWindowTitle(self.tr("Install Find_Orb"))
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(0)
        prog.setAutoClose(False)
        prog.setAutoReset(False)
        worker = FindOrbInstallWorker(manager_path, target)
        self._findorb_worker = worker
        self._findorb_prog = prog
        worker.line.connect(lambda text: prog.setLabelText(
            text.strip()[-160:] or self.tr("Installing Find_Orb…")))
        worker.finished.connect(
            lambda out: self._findorb_install_done(dlg, target, out))
        worker.failed.connect(
            lambda message: self._findorb_install_failed(dlg, message))
        prog.canceled.connect(worker.cancel)
        self._keep(worker)
        worker.start()
        prog.show()

    def _findorb_install_close(self):
        # @return: None. The progress window goes, whatever the outcome.
        prog = getattr(self, "_findorb_prog", None)
        if prog is not None:
            prog.reset()
            prog.close()
        self._findorb_prog = None
        self._findorb_worker = None

    def _findorb_install_done(self, dlg, target, out):
        # @args: dlg - the settings dialog (maybe already destroyed),
        #        target - the environment, out - the worker's report
        # @return: None
        self._findorb_install_close()
        out = out if isinstance(out, dict) else {}
        path = out.get("path")
        if not Shiboken.isValid(dlg):
            return
        if out.get("ok") and path:
            dlg.edt_findorb_path.setText(path)
            from ..core import findorb
            _probe, message = findorb.probe(path)
            QMessageBox.information(dlg, self.tr("Find_Orb"), message)
            return
        QMessageBox.warning(dlg, self.tr("Find_Orb"), self.tr(
            "The installation did not finish. The last lines of the "
            "package manager were:\n\n%1\n\nYou can still install Find_Orb "
            "by hand (the guide is in the documentation) and point the "
            "path above at it.").replace(
                "%1", "\n".join(out.get("log") or [])[-700:]))

    def _findorb_install_failed(self, dlg, message):
        # @args: dlg - the settings dialog, message - the error (English)
        # @return: None
        self._findorb_install_close()
        if Shiboken.isValid(dlg):
            QMessageBox.warning(
                dlg, self.tr("Find_Orb"),
                self.tr("The installation failed:") + f" {message}")

    def _pick_exotic_python(self, dlg):
        # Browse for the Python <=3.10 interpreter that will host EXOTIC.
        from PySide6.QtWidgets import QFileDialog
        path, _sel = QFileDialog.getOpenFileName(
            dlg, self.tr("Select the Python 3.10 interpreter"), "",
            self.tr("Executables (*)"))
        if path:
            dlg.edt_exotic_python.setText(path)

    def _pick_exotic_dir(self, dlg):
        # Browse for the folder the EXOTIC environment will live in.
        from PySide6.QtWidgets import QFileDialog
        path = QFileDialog.getExistingDirectory(
            dlg, self.tr("Select the EXOTIC environment folder"))
        if path:
            dlg.edt_exotic_install.setText(path)

    def _cam_preset_selected(self, dlg):
        # Load the datasheet TEMPLATE of the chosen camera preset: choosing a
        # camera IS asking to see that camera's figures, so the datasheet
        # fields are written over whatever was there. The RULE lives in
        # core/cameras (shared with the Welcome step); here we only map its
        # config keys to the spins. The gain is passed along so the suggested
        # linearity comes from the real full well at the observer's gain; it is
        # never written.
        from ..core import cameras
        p = cameras.preset(dlg.cmb_cam_preset.currentData())
        gain = dlg.spn_cam_gain.value() or None
        for key, value in cameras.profile_from_preset(p, gain).items():
            spin = _CAM_PRESET_SPINS.get(key)
            if spin is not None:
                # an unknown field comes back None: show 0 ("unknown")
                getattr(dlg, spin).setValue(value if value is not None else 0)
        self._cam_ref_update(dlg)

    def _ai_preset_selected(self, dlg):
        # Choosing a known endpoint fills the base URL; the key and the model
        # are the observer's to type (ADR-075). "Custom…" writes nothing, so
        # a hand-typed address is never clobbered.
        base = dlg.cmb_ai_preset.currentData()
        if base:
            dlg.edt_ai_base_url.setText(base)

    def _ai_list_models(self, dlg):
        # "List models" (ADR-075): asks the endpoint which models it has and
        # fills the combo with them, keeping whatever was typed. A local
        # server answers with its exact names, so nobody types them from
        # memory. Off the GUI thread; nothing is saved here.
        from .workers import LlmModelsWorker
        dlg.btn_ai_models.setEnabled(False)
        dlg.lbl_ai_status.setText(self.tr("Asking the endpoint…"))
        dlg.lbl_ai_status.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        worker = LlmModelsWorker(_AiWidgetCfg(dlg))

        def done(models, err):
            dlg.btn_ai_models.setEnabled(True)
            if err:
                dlg.lbl_ai_status.setText("✗ " + err)
                dlg.lbl_ai_status.setStyleSheet(f"color: {theme.C_WARN};")
                return
            current = dlg.cmb_ai_model.currentText().strip()
            dlg.cmb_ai_model.clear()
            dlg.cmb_ai_model.addItems(models)
            if current:
                dlg.cmb_ai_model.setCurrentText(current)
            dlg.lbl_ai_status.setText(
                self.tr("{0} models").format(len(models)))
            dlg.lbl_ai_status.setStyleSheet(f"color: {theme.C_GOOD};")

        worker.done.connect(done)
        self._keep(worker)
        worker.start()

    def _ai_test(self, dlg):
        # The Settings "Test connection" click (ADR-075): one short call,
        # off the GUI thread, that tells whether the address, the key and
        # the model agree. It reads the widgets, not the config, and saves
        # nothing: testing a half-typed endpoint must not touch your setup.
        from .workers import LlmTestWorker

        dlg.btn_ai_test.setEnabled(False)
        dlg.lbl_ai_status.setText(self.tr("Testing…"))
        dlg.lbl_ai_status.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        worker = LlmTestWorker(_AiWidgetCfg(dlg))

        def done(ok, msg):
            dlg.btn_ai_test.setEnabled(True)
            dlg.lbl_ai_status.setText(("✓ " if ok else "✗ ") + msg)
            dlg.lbl_ai_status.setStyleSheet(
                f"color: {theme.C_GOOD if ok else theme.C_WARN};")

        worker.done.connect(done)
        self._keep(worker)
        worker.start()

    def _cam_ref_update(self, dlg):
        # The plate scale FIRST (what the pixel size and the focal length
        # mean together, and the number the NEO advice and the report read),
        # then the sensor facts the preset brought, so the suggested
        # linearity can be sanity-checked at a glance. It is rebuilt live
        # whenever pixel, focal, gain or read noise change.
        from ..core import cameras
        pixel = dlg.spn_pixel_um.value()
        focal = dlg.spn_focal_mm.value()
        bits = []
        if cameras.USER_ERROR:
            # the user's cameras.toml could not be read: say it HERE, or the
            # camera they added would simply not be in the list and nothing
            # would explain why
            bits.append(self.tr("My cameras file could not be read: {0}")
                        .replace("{0}", cameras.USER_ERROR))
        if pixel > 0 and focal > 0:
            # 206265 is the arcseconds in a radian: the small-angle scale
            # of a pixel of this size behind this focal length.
            scale = 206.264806 * pixel / focal
            bits.append(self.tr("Plate scale: {0:.2f}″/pixel").format(scale))
        p = cameras.preset(dlg.cmb_cam_preset.currentData())
        if p is not None:
            bits.append(self.tr("Sensor: {0}").replace("{0}", p["sensor"]))
            if p.get("sensor_w_mm") and p.get("sensor_h_mm"):
                bits.append(self.tr("{0:g} × {1:g} mm sensor").format(
                    p["sensor_w_mm"], p["sensor_h_mm"]))
                if focal > 0:
                    # the sky the sensor covers behind this focal length
                    fov_w = p["sensor_w_mm"] / focal * 57.29578
                    fov_h = p["sensor_h_mm"] / focal * 57.29578
                    bits.append(self.tr("FOV {0:.2f}° × {1:.2f}°").format(
                        fov_w, fov_h))
            if p.get("bit_depth"):
                bits.append(self.tr("{0}-bit ADC").replace(
                    "{0}", str(p["bit_depth"])))
            if p.get("dark_current_e_s") is not None \
                    and p.get("dark_temp_c") is not None:
                bits.append(self.tr("dark {0} e-/pix/s @ {1} °C")
                            .replace("{0}", f"{p['dark_current_e_s']:g}")
                            .replace("{1}", f"{p['dark_temp_c']:g}"))
            bits.append(self.tr("regime: {0}").replace(
                "{0}", self.tr("short (group frames)")
                if p["regime"] == "short" else self.tr("normal")))
            gain = dlg.spn_cam_gain.value() or None
            fw = cameras.full_well_adu(p, gain)
            if fw:
                bits.append(self.tr("full well ≈ {0:.0f} ADU at your gain")
                            .format(fw))
            lin = cameras.suggested_linearity_adu(p, gain)
            if lin:
                bits.append(self.tr("linearity ≈ {0:.0f} ADU").format(lin))
            if p.get("linearity_note"):
                bits.append(p["linearity_note"])
        dlg.lbl_cam_ref.setText(" · ".join(bits))
        self._cam_gain_note(dlg)

    def _cam_gain_note(self, dlg):
        # The consequence of the gain, live (quality plan, phase G): with
        # one, the error bar is the CCD equation; without one it is only
        # the scatter of the comparison stars, and the observer must know
        # before wondering why a 0.06 mag curve has 0.2 mag error bars.
        gain = dlg.spn_cam_gain.value() or None
        ron = dlg.spn_cam_ron.value() or None
        if gain:
            bits = [self.tr("gain {0:.3g} e-/ADU").format(gain)]
            if ron:
                bits.append(self.tr("read noise {0:.3g} e-").format(ron))
            from ..core import cameras
            p = cameras.preset(dlg.cmb_cam_preset.currentData())
            if p is not None and p.get("read_noise_note"):
                bits.append(p["read_noise_note"])
            bits.append(self.tr(
                "the error bar is the CCD equation"))
            dlg.lbl_cam_gain_note.setText(" · ".join(bits))
        else:
            dlg.lbl_cam_gain_note.setText(self.tr(
                "No gain: the error bar of every point is the scatter of "
                "the comparison stars, not the CCD equation. Measure it on "
                "your own frames, or set it here."))

    def _measure_gain_into(self, dlg):
        # ADR-072: the one-time gain measurement, from Settings -> Camera.
        # Point at a folder with two frames of the same exposure, measure the
        # conversion gain and remember it for this camera; the field is filled
        # so the observer sees the value and the note stops saying it is
        # missing.
        # @args: dlg - the settings dialog
        # @return: None
        from ..core import fits_io, gain as gain_mod, gain_store
        from ..core.db import db
        folder = QFileDialog.getExistingDirectory(
            dlg, self.tr("Measure my gain"), "")
        if not folder:
            return
        paths = sorted(str(p) for p in Path(folder).iterdir()
                       if p.suffix.lower() in (".fit", ".fits", ".fts"))
        if len(paths) < 2:
            QMessageBox.information(dlg, self.tr("Measure my gain"),
                                    self.tr("That folder has fewer than two "
                                            "FITS frames: the gain needs a "
                                            "pair of the same exposure."))
            return
        try:
            estimate = gain_mod.estimate_from_paths(paths)
        except Exception as err:                # never fatal
            logger.warning("gain estimate failed: %s", err)
            estimate = None
        gain = (estimate or {}).get("gain")
        if gain is None:
            notes = (estimate or {}).get("notes") or []
            lang = self._lang()
            said = notes[-1].get(lang) or notes[-1].get("en") if notes else None
            QMessageBox.information(
                dlg, self.tr("Measure my gain"),
                said or self.tr("The gain could not be measured there: it "
                                "needs two frames of the same exposure with a "
                                "usable sky."))
            return
        try:
            header = fits_io.read_header(paths[0])
        except Exception as err:                # never fatal
            logger.warning("gain header failed: %s", err)
            header = None
        if header is not None:
            try:
                gain_store.remember(db, header, estimate)
            except Exception as err:            # never fatal
                logger.warning("gain remember failed: %s", err)
        dlg.spn_cam_gain.setValue(float(gain))
        parts = [self.tr("Gain {0} e-/ADU")
                 .format("{:.4g}".format(float(gain)))]
        ron = estimate.get("ron")
        if ron is not None:
            parts.append(self.tr("read noise {0} e-")
                         .format("{:.3g}".format(float(ron))))
        if estimate.get("n_kept"):
            parts.append(self.tr("{0} sky boxes")
                         .format(int(estimate["n_kept"])))
        QMessageBox.information(
            dlg, self.tr("Measure my gain"),
            self.tr("Measured on your own frames: {0}. It is remembered for "
                    "this camera, so a single image reuses it."
                    ).format(" · ".join(parts)))

    def _exotic_python(self, dlg):
        # @return: the interpreter to use (configured, else detected)
        from ..core import exotic_env
        return exotic_env.detect_python(
            dlg.edt_exotic_python.text().strip())

    def _test_exotic(self, dlg):
        # Probes the interpreter for a working EXOTIC import off the GUI
        # thread: detect_python spawns subprocesses and the cold import
        # of exotic can take minutes, which used to freeze the app for
        # the whole probe. The button stays disabled while it runs.
        # @args: dlg - the settings dialog
        if getattr(self, "_exotic_probe", None) is not None:
            return
        from .workers import ProbeExoticWorker
        dlg.btn_exotic_test.setEnabled(False)
        self.statusBar().showMessage(
            self.tr("Checking the EXOTIC environment…"), 0)
        worker = ProbeExoticWorker(dlg.edt_exotic_python.text().strip())
        worker.finished.connect(
            lambda rep: self._exotic_test_done(dlg, rep))
        self._exotic_probe = worker
        self._keep(worker)
        worker.start()

    def _exotic_test_done(self, dlg, rep):
        # The probe landed: re-arm the button and report. The probe
        # takes minutes, so the dialog may be closed and destroyed by
        # now: never touch a destroyed dialog's widgets; the status bar
        # carries the report when it is gone.
        # @args: dlg - the settings dialog (maybe already destroyed),
        #        rep - the probe report {"ok","version","message","python"}
        from PySide6.QtWidgets import QMessageBox
        self._exotic_probe = None
        self.statusBar().clearMessage()
        if not Shiboken.isValid(dlg):
            self.statusBar().showMessage(rep.get("message", ""), 8000)
            return
        dlg.btn_exotic_test.setEnabled(True)
        QMessageBox.information(dlg, self.tr("EXOTIC"),
                                rep.get("message", ""))

    def _prepare_exotic(self, dlg):
        # Build the external EXOTIC environment in the background.
        from PySide6.QtWidgets import QMessageBox
        from ..core import exotic_env
        from .workers import PrepareExoticWorker
        python = self._exotic_python(dlg)
        if not python:
            QMessageBox.warning(dlg, self.tr("EXOTIC"), self.tr(
                "No Python 3.10 interpreter found: install it or point to "
                "one above."))
            return
        install = dlg.edt_exotic_install.text().strip() or str(
            paths.data_dir() / "exotic-venv")
        self._exotic_worker = hold(PrepareExoticWorker(install, python))
        self._exotic_worker.progress.connect(
            lambda stage: self.statusBar().showMessage(
                self.tr("Preparing EXOTIC: {0}").format(stage), 0))
        self._exotic_worker.finished.connect(
            lambda ok, log: self._exotic_prepared(dlg, install, ok, log))
        self._exotic_worker.start()
        self.statusBar().showMessage(
            self.tr("Preparing the EXOTIC environment…"), 0)

    def _exotic_prepared(self, dlg, install, ok, log):
        # The environment build finished: report and point the setting at
        # the new venv interpreter. The build takes minutes, so the modal
        # dialog may be long closed and destroyed when this lands: guard
        # every widget write (writing into a destroyed dialog crashed the
        # app) and let the status bar carry the report when it is gone.
        # @args: dlg - the settings dialog (maybe already destroyed),
        #        install - the venv folder, ok - the build succeeded,
        #        log - the build log
        from PySide6.QtWidgets import QMessageBox
        from ..core import exotic_env
        self._exotic_worker = None
        self.statusBar().clearMessage()
        if not Shiboken.isValid(dlg):
            lines = [ln for ln in (log or "").splitlines() if ln.strip()]
            self.statusBar().showMessage(
                self.tr("EXOTIC environment ready.") if ok else
                self.tr("Could not prepare EXOTIC: {0}").format(
                    lines[-1] if lines else ""), 10000)
            return
        if ok:
            dlg.edt_exotic_install.setText(install)
            dlg.edt_exotic_python.setText(str(exotic_env.venv_python(install)))
            QMessageBox.information(dlg, self.tr("EXOTIC"), self.tr(
                "EXOTIC environment ready."))
        else:
            QMessageBox.warning(dlg, self.tr("EXOTIC"), self.tr(
                "Could not prepare EXOTIC:\n{0}").format(log[-600:]))

    def on_open_settings(self):
        # ADR-071: the dialog is a rail of six categories (Observatory,
        # Equipment, Observing, Measurement, Integrations, Interface), a
        # search box and scrollable pages. The .ui carries the structure;
        # the simple fields are filled and saved from ONE table
        # (settings_spec.FIELDS), so a field cannot be loaded and forgotten
        # on the way out. The combos whose items are built at runtime (the
        # camera preset, the solver, the marker, the language) and the
        # parsed lists (kinds, vigils) stay hand-wired here, where their
        # index or data mapping is visible.
        from . import settings_spec
        from . import settings_view
        from ..core import cameras
        from ..core import vigils

        # the camera catalogue is data (assets/cameras.toml + the user file):
        # re-read it here so a camera added or corrected in the user's
        # cameras.toml shows up without restarting the app
        cameras.reload()

        dlg = _load_ui("settings_dialog")
        settings_view.style_help_labels(dlg)
        settings_view.build_rail(dlg, settings_spec.CATEGORIES, self.tr)
        for name in settings_spec.ADVANCED_GROUPS:
            group = getattr(dlg, name, None)
            if group is not None:
                settings_view.make_collapsible(group, collapsed=True)
        settings_view.wire_search(
            dlg, self.tr("No setting matches that search."))
        dlg.resize(max(900, dlg.sizeHint().width()),
                   max(640, dlg.sizeHint().height()))

        # combos whose items are built here, before the table fills them
        dlg.cmb_camera_type.addItems(["CCD", "CMOS", "DSLR"])
        dlg.cmb_binning.addItems(["1x1", "2x2", "3x3"])
        dlg.cmb_solver.addItem(self.tr("Auto (ASTAP, then nova)"), "auto")
        dlg.cmb_solver.addItem(self.tr("ASTAP (local)"), "astap")
        dlg.cmb_solver.addItem(self.tr("Astrometry.net (nova)"), "astrometry")
        dlg.cmb_cam_preset.addItem(self.tr("None"), "")
        for text, key, is_header in cameras.combo_entries():
            dlg.cmb_cam_preset.addItem(text, key)
            if is_header:
                # a family header: bold, accent and not selectable, so the
                # list reads as a few groups and not as twenty-one rows
                theme.style_combo_header(
                    dlg.cmb_cam_preset.model().item(
                        dlg.cmb_cam_preset.count() - 1))
        dlg.cmb_marker_style.addItem(self.tr("Ring with ticks (classic)"),
                                     "ring")
        dlg.cmb_marker_style.addItem(self.tr("Full-frame cross with box"),
                                     "cross")
        dlg.cmb_mark_color.addItem(self.tr("The object type's colour"), "kind")
        dlg.cmb_mark_color.addItem(self.tr("One common colour"), "common")
        dlg.cmb_language.addItems([self.tr("System"), self.tr("Spanish"),
                                   self.tr("English")])

        # AI endpoint presets (ADR-075): a convenience that fills the base
        # URL. Any OpenAI-compatible address works, cloud or local; the
        # presets are the ones people ask for first.
        dlg.cmb_ai_preset.addItem(self.tr("Custom…"), "")
        for label, base in (
                (self.tr("OpenRouter"), "https://openrouter.ai/api/v1"),
                (self.tr("Groq"), "https://api.groq.com/openai/v1"),
                (self.tr("Google AI Studio"),
                 "https://generativelanguage.googleapis.com/v1beta/openai"),
                (self.tr("Ollama (local)"), "http://localhost:11434/v1"),
                (self.tr("LM Studio (local)"), "http://localhost:1234/v1")):
            dlg.cmb_ai_preset.addItem(label, base)

        # every simple field, one table both ways (ADR-071)
        settings_spec.load(dlg, config)

        # combos with an index or a data mapping of their own
        dlg.cmb_camera_type.setCurrentText(config.get("camera_type", "CCD"))
        dlg.cmb_binning.setCurrentText(config.get("pixel_binning", "1x1"))
        idx = dlg.cmb_solver.findData(config.get("solver", "auto"))
        dlg.cmb_solver.setCurrentIndex(idx if idx >= 0 else 0)
        idx = dlg.cmb_cam_preset.findData(config.get("cam_preset", ""))
        # restore the saved preset WITHOUT firing the template load: the
        # profile on screen is the observer's (measured) one, not the
        # datasheet, and opening Settings must not throw it away
        dlg.cmb_cam_preset.blockSignals(True)
        dlg.cmb_cam_preset.setCurrentIndex(idx if idx >= 0 else 0)
        dlg.cmb_cam_preset.blockSignals(False)
        # paint the reference (and the user-file error, if any) on open: the
        # index above does not fire the fill any more
        self._cam_ref_update(dlg)
        idx = dlg.cmb_marker_style.findData(config.get("marker_style", "ring"))
        dlg.cmb_marker_style.setCurrentIndex(idx if idx >= 0 else 0)
        idx = dlg.cmb_mark_color.findData(config.get("marker_color", "kind"))
        dlg.cmb_mark_color.setCurrentIndex(idx if idx >= 0 else 0)
        lang = config.get("language", "system")
        dlg.cmb_language.setCurrentIndex(
            {"system": 0, "es": 1, "en": 2}.get(lang, 0))

        # reflect the saved AI endpoint: a value that matches no preset shows
        # as "Custom…" and the base URL below keeps it. Wire the fill AFTER
        # setting the index, so restoring never overwrites the saved address.
        saved_base = (config.get("ai_base_url") or "").strip()
        idx = dlg.cmb_ai_preset.findData(saved_base)
        dlg.cmb_ai_preset.setCurrentIndex(idx if idx >= 0 else 0)
        dlg.cmb_ai_preset.currentIndexChanged.connect(
            lambda _i: self._ai_preset_selected(dlg))

        # the vigils list is parsed, not a plain string
        dlg.edt_vigils.setPlainText(
            vigils.vigils_to_text(vigils.vigils_from_config(config)))

        # Tonight object kinds: the whitelist mirrors the checkboxes
        enabled = self._enabled_kinds()
        for kind in KIND_ORDER:
            box = getattr(dlg, f"chk_kind_{kind}", None)
            if box is not None:
                box.setChecked(kind in enabled)

        # the camera profile note (sensor facts + the live plate scale):
        # recompute it whenever any number it reads changes
        dlg.cmb_cam_preset.currentIndexChanged.connect(
            lambda _i: self._cam_preset_selected(dlg))
        for spin in (dlg.spn_cam_gain, dlg.spn_cam_ron, dlg.spn_pixel_um,
                     dlg.spn_focal_mm):
            spin.valueChanged.connect(lambda _v: self._cam_ref_update(dlg))
        self._cam_ref_update(dlg)
        # ADR-072: measure the gain on two of the observer's own frames and
        # remember it, so a single image can reuse it (the FITS header often
        # carries the camera's setting or a placeholder).
        dlg.btn_measure_gain.clicked.connect(
            lambda: self._measure_gain_into(dlg))
        dlg.btn_ai_test.clicked.connect(lambda: self._ai_test(dlg))
        dlg.btn_ai_models.clicked.connect(lambda: self._ai_list_models(dlg))

        # buttons
        dlg.btn_astap_browse.clicked.connect(lambda: self._pick_astap(dlg))
        dlg.btn_astap_test.clicked.connect(lambda: self._test_astap(dlg))
        dlg.btn_findorb_browse.clicked.connect(
            lambda: self._pick_findorb(dlg))
        dlg.btn_findorb_test.clicked.connect(lambda: self._test_findorb(dlg))
        dlg.btn_findorb_install.clicked.connect(
            lambda: self._install_findorb(dlg))
        dlg.btn_exotic_py_browse.clicked.connect(
            lambda: self._pick_exotic_python(dlg))
        dlg.btn_exotic_dir_browse.clicked.connect(
            lambda: self._pick_exotic_dir(dlg))
        dlg.btn_exotic_prepare.clicked.connect(
            lambda: self._prepare_exotic(dlg))
        dlg.btn_exotic_test.clicked.connect(lambda: self._test_exotic(dlg))
        dlg.btn_resolve.clicked.connect(lambda: self._resolve_into(dlg))
        dlg.btn_map_pick.clicked.connect(lambda: self._map_pick_into(dlg))
        dlg.btn_horizon_browse.clicked.connect(
            lambda: self._horizon_browse_into(dlg))
        dlg.btn_projects_browse.clicked.connect(
            lambda: self._projects_browse_into(dlg))
        dlg.btn_projects_reset.clicked.connect(
            lambda: dlg.edt_projects_root.setText(""))
        dlg.edt_horizon_file.textChanged.connect(
            lambda _t: self._horizon_file_preview(dlg))
        self._horizon_file_preview(dlg)
        self._settings_masters_init(dlg)

        dlg.buttonBox.accepted.connect(dlg.accept)
        dlg.buttonBox.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.Accepted:
            return

        # save: the same table, one direction (ADR-071)
        settings_spec.save(dlg, config)

        # the AI master switch may have changed (ADR-075): close or reopen
        # its surfaces right away, so the app acts on what was just saved
        self._refresh_ai_availability()

        # combos with their own mapping
        config.set("camera_type", dlg.cmb_camera_type.currentText())
        config.set("pixel_binning", dlg.cmb_binning.currentText().strip()
                   or "1x1")
        config.set("solver", dlg.cmb_solver.currentData() or "auto")
        config.set("cam_preset", dlg.cmb_cam_preset.currentData() or "")
        _cp = cameras.preset(dlg.cmb_cam_preset.currentData())
        config.set("cam_regime", _cp["regime"] if _cp else "normal")
        # the temperature the dark current was quoted at travels with it, or
        # the number in the profile loses its meaning (the preset fill writes
        # it too, for the Welcome step; this keeps Settings in step)
        config.set("cam_dark_temp_c",
                   _cp.get("dark_temp_c") if _cp else None)
        config.set("marker_style",
                   dlg.cmb_marker_style.currentData() or "ring")
        config.set("marker_color",
                   dlg.cmb_mark_color.currentData() or "kind")
        config.set("vigil_list",
                   vigils.vigils_from_text(dlg.edt_vigils.toPlainText()))

        # Interface: the Welcome motion applies live, no restart needed
        if self._welcome is not None:
            self._welcome.refresh_animations()

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
        # if the header filter points at a kind that just got removed,
        # fall back to "All" so nothing is left dangling
        current = self.tonight.cmb_filter.currentData()
        if current and current not in enabled:
            self.tonight.cmb_filter.blockSignals(True)
            self.tonight.cmb_filter.setCurrentIndex(0)  # "All"
            self.tonight.cmb_filter.blockSignals(False)
            config.set("tonight_kind", "")
        # re-apply the filter and rebuild the grid with the new whitelist
        # and the new per-kind cap
        if self._tonight_all:
            self._apply_kind_filter()
            self._build_suggestion_grid()
        # interface language: "system" (index 0) | "es" | "en"; a change
        # only applies after a restart
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

    # ---------------- the master library (ADR-061) ----------------

    def _settings_masters_init(self, dlg):
        # The library of calibration masters lives in Settings. The
        # editor's Calibration tab resolves a recipe against it and says
        # which master each piece uses; before this, nothing in the GUI
        # could put a master IN, so that tab could only ever report what
        # was missing.
        # @args: dlg - the settings dialog
        # @return: None
        from ..core import calibration
        for kind in calibration.KINDS:
            dlg.cmb_master_kind.addItem(self._master_kind_label(kind), kind)
        dlg.btn_master_add.clicked.connect(
            lambda: self._settings_master_add(dlg))
        dlg.btn_master_remove.clicked.connect(
            lambda: self._settings_master_remove(dlg))
        dlg.tbl_masters.itemSelectionChanged.connect(
            lambda: self._settings_masters_sync(dlg))
        self._settings_masters_refresh(dlg)

    def _master_kind_label(self, kind):
        # @args: kind - one of core.calibration.KINDS
        # @return: its name in the observer's language. The four kinds are
        #          not synonyms: they are four different arithmetics, and
        #          the help label above the table says what each one is.
        return {"bias": self.tr("Bias"),
                "dark": self.tr("Dark"),
                "dark_flat": self.tr("Dark of the flats"),
                "flat": self.tr("Flat")}.get(kind, kind)

    def _settings_masters_refresh(self, dlg):
        # @args: dlg - the settings dialog
        # @return: None. The table is filled from the database, newest
        #          first, and the Remove button follows the selection: a
        #          button that can act on nothing is a trap (U5).
        from pathlib import Path
        from ..core import calibration
        masters = calibration.list_masters(db)
        tbl = dlg.tbl_masters
        tbl.setRowCount(len(masters))
        for row, m in enumerate(masters):
            cells = [Path(m.path).name, self._master_kind_label(m.kind),
                     m.camera or "", _master_num(m.gain),
                     _master_num(m.temp_c), _master_num(m.exptime_s),
                     m.filter or "", (m.created or "")[:10]]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if col == 0:
                    # the file name is what fits; the whole path (and the
                    # row's id, for the Remove button) travel with it
                    item.setToolTip(m.path)
                    item.setData(Qt.UserRole, m.id)
                tbl.setItem(row, col, item)
        self._settings_masters_sync(dlg)

    def _settings_masters_sync(self, dlg):
        # @args: dlg - the settings dialog
        # @return: None
        selected = bool(dlg.tbl_masters.selectionModel().selectedRows())
        dlg.btn_master_remove.setEnabled(selected)

    def _settings_master_selected_id(self, dlg):
        # @args: dlg - the settings dialog
        # @return: the id of the selected master, or None
        rows = dlg.tbl_masters.selectionModel().selectedRows()
        if not rows:
            return None
        item = dlg.tbl_masters.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item is not None else None

    def _masters_index_files(self, kind, files):
        # @args: kind - one of core.calibration.KINDS, files - the FITS paths
        # @return: (added, repeated, failed) with failed = [(name, why)].
        # One home for the indexing, shared by the Settings dialog and the
        # editor's Calibration tab (ADR-061 rev): a master is INDEXED, never
        # copied or moved, and what makes it valid is read from its own
        # header.
        from pathlib import Path
        from ..core import calibration
        known = {m.path for m in calibration.list_masters(db, kind=kind)}
        added, repeated, failed = 0, 0, []
        for path in files:
            if str(path) in known:
                repeated += 1
                continue
            try:
                calibration.add_master(db, path, {"kind": kind})
                added += 1
            except Exception as err:
                # one unreadable file must not lose the rest of the batch
                failed.append((Path(path).name, str(err)))
        return added, repeated, failed

    def _masters_add_words(self, kind, added, repeated, failed):
        # @args: kind - the kind indexed, added/repeated - counts, failed -
        #        [(name, why)]
        # @return: the result in words, for the label that asked for it
        bits = [self.tr("Indexed %1 masters (%2).").replace(
            "%1", str(added)).replace("%2", self._master_kind_label(kind))
            if added else self.tr("Nothing new to index.")]
        if repeated:
            bits.append(self.tr("%1 were already in the library.").replace(
                "%1", str(repeated)))
        for name, why in failed[:3]:
            bits.append(f"✕ {name}: {why}")
        return "  ".join(bits)

    def _ufe_add_masters(self, kind):
        # ADR-061 rev: the editor's Calibration tab fills the library from
        # where the recipe is read. The tab never touches the database: this
        # opens the dialog and answers with words.
        # @args: kind - one of core.calibration.KINDS
        # @return: what happened, in words ("" when nothing was chosen)
        files, _sel = QFileDialog.getOpenFileNames(
            self, self.tr("Add masters"), "",
            self.tr("FITS images (*.fits *.fit *.fts);;All files (*)"))
        if not files:
            return ""
        added, repeated, failed = self._masters_index_files(kind, files)
        return self._masters_add_words(kind, added, repeated, failed)

    def _settings_master_add(self, dlg):
        # @args: dlg - the settings dialog
        # @return: None. The files are INDEXED, never copied or moved: a
        #          master can be big and the library only needs to know
        #          where it is and what makes it valid (camera, gain,
        #          temperature, exposure, filter). Any of those the file's
        #          own header carries is read from it.
        from ..core import calibration
        files, _sel = QFileDialog.getOpenFileNames(
            dlg, self.tr("Add masters"), "",
            self.tr("FITS images (*.fits *.fit *.fts);;All files (*)"))
        if not files:
            return
        kind = dlg.cmb_master_kind.currentData() or "dark"
        added, repeated, failed = self._masters_index_files(kind, files)
        self._settings_masters_refresh(dlg)
        dlg.lbl_master_status.setText(
            self._masters_add_words(kind, added, repeated, failed))

    def _settings_master_remove(self, dlg):
        # @args: dlg - the settings dialog
        # @return: None. Only the INDEX entry goes: the file on disk is
        #          the observer's own data and is never deleted from here.
        from pathlib import Path
        from ..core import calibration
        mid = self._settings_master_selected_id(dlg)
        if mid is None:
            return
        master = next((m for m in calibration.list_masters(db)
                       if m.id == mid), None)
        name = Path(master.path).name if master is not None else ""
        if QMessageBox.question(
                dlg, self.tr("Remove from the library"),
                self.tr("Take %1 out of the master library? The file on "
                        "disk is not touched.").replace("%1", name)
        ) != QMessageBox.Yes:
            return
        calibration.delete_master(db, mid, delete_file=False)
        self._settings_masters_refresh(dlg)
        dlg.lbl_master_status.setText(
            self.tr("Removed %1 from the library.").replace("%1", name))

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

    def _map_pick_into(self, dlg):
        # Opens the site picker (Interfaz 1.5) and copies the chosen point
        # into the dialog's fields. The map is a dialog rather than a panel
        # here because Settings is already a dense page of groups.
        from .site_map_dialog import SiteMapDialog
        picker = SiteMapDialog(lat=dlg.spn_lat.value(),
                               lon=dlg.spn_lon.value(),
                               name=dlg.edt_obs_name.text().strip(),
                               parent=dlg)
        if picker.exec() != QDialog.Accepted:
            return
        lat, lon = picker.chosen()
        if lat is None:
            return
        dlg.spn_lat.setValue(lat)
        dlg.spn_lon.setValue(lon)

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
        # The box is built by hand because QMessageBox.about() offers no way
        # to let its label open the project link; the HTML itself lives in
        # _about_html so a test can read it without opening anything.
        # @args: none
        box = QMessageBox(self)
        box.setWindowTitle("NightScribe")
        box.setIcon(QMessageBox.Information)
        box.setTextFormat(Qt.RichText)
        box.setText(self._about_html())
        box.setStandardButtons(QMessageBox.Ok)
        label = box.findChild(QLabel, "qt_msgbox_label")
        if label is not None:
            label.setOpenExternalLinks(True)
        box.exec()

    def _about_html(self):
        # @return: the About text as rich HTML. The project URL is the one
        #          thing that leaves the app from here, so it is a real link
        #          (the report of a bug starts at the same page). The data
        #          sources live here too: they were a Help entry of their own
        #          (a static list, no live status) and one informational box
        #          is enough (2026-10-08).
        return (
            f"<b>NightScribe</b> {full_version()}<br><br>"
            + self.tr("Plan your night, understand every object, "
                      "tell your science.")
            + "<br><br>(c) 2026 Francisco José Calvo Fernández<br>"
            "GPL v3 · Irydeo Observatory (MPC Z41)<br><br>"
            '<a href="https://github.com/irydeo/nightscribe">'
            "github.com/irydeo/nightscribe</a>"
            + "<br><br><b>" + self.tr("Data sources") + "</b><br>"
            + self.tr("NEOfixer · MPC (PCCP, ObsCodes) · JPL SBDB/Horizons/CAD · "
                      "COBS · Rochester Astronomy · SIMBAD · ExoClock · NASA "
                      "Exoplanet Archive · NOAA SWPC · SILSO · NASA SDO · DESI "
                      "Legacy Survey · CDS hips2fits"))

    def on_open_log(self):
        # Help > Open the log: the file the app writes while it runs, so a
        # report like "a dialog appeared and nothing happened" can be
        # answered with what really happened. Opening it is the OS's job;
        # the path also lands in the status bar (for a file manager).
        # @return: None
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        path = paths.log_path()
        if not path.exists():
            self.statusBar().showMessage(
                self.tr("No log yet: %1").replace("%1", str(path)), 8000)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.statusBar().showMessage(str(path), 8000)

    def on_guide_web(self):
        # Opens the published user guide in the OS browser (ADR-070): it is
        # now the app's only general door to the guide (Help > User guide
        # (web)), and the one the Welcome screen opens too. The site's own
        # pages pick the language from the suffix.
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        suffix = ".es" if self._lang() == "es" else ""
        QDesktopServices.openUrl(QUrl(f"{GUIDE_WEB_URL}{suffix}.html"))

    def _open_assistant(self, scope="app"):
        # The grounded assistant (ADR-075), non-modal and opt-in. The object
        # scope is offered only with a project open; the brief is built in
        # the worker (it may enrich over the network), the editor scope is
        # opened from the editor itself.
        # @args: scope - "app"|"object"|"editor"
        # @return: None
        from .assistant_window import AssistantWindow
        from ..core.sources import llm
        if not llm.is_enabled(config):
            # the AI is off (ADR-075): no dialog at all. The Help action and
            # the editor's "?" are already disabled; this is the belt to
            # their braces
            return
        win = getattr(self, "_assistant_win", None)
        if win is not None:
            win.close()
        project = self._current_project
        name = project.get("object_name") if project else None
        brief_provider = None
        if project is not None:
            def brief_provider(project=project):
                from ..core import enrich, object_brief
                e = enrich.enrich(project.get("object_name") or "",
                                  site=config.get("mpc_code"))
                return object_brief.build_brief(
                    project, db, enriched=e, lang=config.ui_language(),
                    cfg=config)
        win = AssistantWindow(object_name=name, brief_provider=brief_provider,
                              start_scope=scope, parent=self)
        self._assistant_win = win
        win.show()
        win.raise_()
        win.activateWindow()

    # ---------------- Tonight: suggestion grid ----------------

    # Type accent colors and short labels — single source of truth lives
    # in gui/theme.py (ADR-026); these references keep call sites stable.
    _KIND_COLORS = theme.KIND_COLORS
    _KIND_LABELS = theme.KIND_LABELS

    def _type_pixmap(self, kind, size=28):
        # Draws a small geometric icon per object type with QPainter.
        # Fast (no matplotlib), guaranteed to render on any platform.
        # The painter itself lives in widgets/kind_glyph.py (ADR-057): the
        # object card's hero draws the same glyph at 44 px, and one grammar
        # of shapes wants one home.
        # @args: kind - object kind string, size - icon px
        # @return: QPixmap with a transparent background
        from .widgets.kind_glyph import kind_glyph_pixmap
        return kind_glyph_pixmap(kind, size)

    def on_compute_tonight(self):
        self._tonight_running = True
        self.tonight.btn_compute.setEnabled(False)
        self._show_loading_state()
        self.statusBar().showMessage(self.tr("Computing tonight…"))
        w = TonightWorker(config, db)
        w.progress.connect(self._tonight_progress)
        w.finished.connect(self._tonight_done)
        self._keep(w)
        w.start()

    def _maybe_compute_tonight(self):
        # Interfaz 1.0: the new-project view triggers the first compute on
        # demand (the app itself never computes at start). A manual ↻
        # still forces a fresh run through on_compute_tonight().
        if self._tonight_loaded or self._tonight_running:
            return
        if not config.is_configured():
            self.tonight.lbl_context.setText(
                self.tr("Set your observatory in Welcome to get tonight's "
                        "targets"))
            return
        self.on_compute_tonight()

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
        self._tonight_running = False
        self._tonight_loaded = True
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

    def _goto_project_followup(self, pid):
        # Opens the project on its Analysis tab (ADR-045). The cadence
        # chips land here (UX-d). Interfaz 1.1: one navigation that records
        # the tab, so "back" returns to the chip's origin.
        if not project.get(db, pid):
            return
        self.on_refresh_projects()
        self.navigate(VIEW_DETAIL, pid=pid, tab="analysis")

    # ---------------- sky-event chips in the Tonight header (SC2) -------

    def _skyevent_chips(self, evs=None):
        # The solar system as an event source (SC2, ADR-040): up to three
        # chips, the big things first, one per family. Local maths, no
        # network. A click opens the Sky calendar. Interfaz 1.0: their home
        # is the Home band "What's up in the sky" (they used to fall to the
        # bottom of Tonight by an accident of layout parenting).
        # @args: evs - optional precomputed list (tests inject fakes)
        # @return: the picked events (also handy for tests)
        for old in self.findChildren(QLabel, "ns_skyevent_chip"):
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
            # Two, not three: the bar shares the row with the navigation
            # and with the Moon, and a third chip pushed the last one off
            # the right edge (seen at 1360 px). The rest of the calendar is
            # one click away, which is where the chips lead anyway.
            if len(picks) == 2:
                break
        # Interfaz 1.6: the chips live in the navigation sky bar now, which
        # is always visible (its Moon and its darkness window do not depend
        # on there being events). Only the chips come and go.
        row = getattr(self, "_sky_chips_row", None)
        if row is None:
            # fallback (no shell): the old Tonight header home
            parent = self.tonight.lbl_context.parentWidget()
            row = parent.layout() if parent else None
        if row is None or not hasattr(row, "insertWidget"):
            return picks
        if not picks:
            return picks
        for i, e in enumerate(picks):
            chip = _LinkChip(self._sky_chip_text(e), "#6ab0ff",
                             self.tr("From the solar-system calendar — "
                                     "click to open the Sky calendar"))
            chip.setObjectName("ns_skyevent_chip")
            chip.clicked.connect(self._tools_skycal)
            row.insertWidget(i, chip)
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
        # Interfaz 1.6 fix: the workbench is a PAGE of this window now, but
        # the visit window is a non-modal dialog WITH a parent, so the
        # window manager keeps it above its parent. Opening a plate from a
        # visit therefore put the editor behind the visit window. The visit
        # steps aside while the workbench is on screen and comes back when
        # it leaves (nothing is lost: the workbench carries its own visit
        # pane with the frame navigator).
        previous = getattr(self, "_last_view_index", None)
        self._last_view_index = index
        if index == VIEW_UFE and previous != VIEW_UFE:
            self._ufe_enter()
        elif previous == VIEW_UFE and index != VIEW_UFE:
            self._ufe_leave()
        # Keep both master-detail tabs always fresh on every visit.
        if index == TAB_PROJECTS:
            self.on_refresh_projects()
        elif index == TAB_CAMPAIGNS:
            self._refresh_campaigns_tab()
        elif index == VIEW_TONIGHT:
            # Interfaz 1.0: the new-project view computes tonight on demand
            self._maybe_compute_tonight()
        # Interfaz 1.3: the drawer has no place on Home (the list is the
        # screen); close it and hide its tab while Home is shown.
        if index == VIEW_HOME and getattr(self, "_drawer", None) is not None \
                and self._drawer.isVisible():
            self._drawer_open(False)
        self._update_vtab_visibility()

    def _update_vtab_visibility(self):
        # The vertical PROJECTS tab is shown everywhere EXCEPT Home, where
        # the project list is already the screen (Interfaz 1.3). While an
        # update gates the app it stays visible but disabled.
        btn = getattr(self._menus, "btn_vtab", None)
        if btn is None:
            return
        btn.setVisible(self._shell_stack().currentIndex() != VIEW_HOME)
        btn.setEnabled(not getattr(self, "_welcome_gate", False))

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
                "effort: several nights, several observatories, one goal. "
                "A project is one object with its three steps: capture, "
                "track, follow-up."))
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
        seq = _camp.sequence_of(c)
        if seq:
            # the shared sequence of a pass (E5b): saying it here is the
            # point, because a project measuring with the campaign's stars
            # instead of its own must be able to see it
            lines.append(self.tr("Shared sequence: %1 comparison stars"
                                 ).replace("%1",
                                           str(len(seq.get("entries") or []))))
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
        # Interfaz 1.1: keep the last rows' data so the overlay drawer can
        # rebuild the SAME rich rows without recomputing them
        self._last_projects_list = projects_list
        self._last_attn_map = attn_map
        self._last_camp_names = camp_names
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
            # the item's height must carry the row's fixed height (the
            # rich row is a widget over the item, so the item has to be
            # told how tall it is)
            item.setSizeHint(QSize(0, _PROJECT_ROW_H))
            lst.addItem(item)
            # UX-PC (U2): the rich row — the plain text above stays as the
            # accessible/searchable fallback under the widget
            row = self._project_row_widget(p, attn_map.get(p["id"]),
                                           camp_names)
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
        # keep the overlay drawer in sync with the hub list
        if getattr(self, "_drawer_list", None) is not None \
                and self._drawer.isVisible():
            self._refresh_drawer()

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
        # the curve thumbnail: the LAST available curve of the project, drawn
        # in the SAME magnitude window the chart uses. Reported twice: it
        # stretched min-to-max on its own, so a flat curve and a
        # three-magnitude one looked exactly the same (a real project's
        # curve spans 11.074 to 13.224 mag, one anomalous frame, while its
        # chart's window is 11.074 to 11.241), and it showed the project's
        # pile instead of the latest reduction. The sparkline is null when
        # there is nothing to draw (fewer than two usable points), so the row
        # hides it by itself.
        from ..core import lightcurve_data
        from .widgets.lightcurve_widget import source_label
        run = _fu.latest_curve_run(db, p["id"])
        pts = (_fu.list_points_for_run(db, run["id"]) if run is not None
               else _fu.list_points(db, p["id"]))
        window = lightcurve_data.mag_window(
            [q["mag"] for q in pts if q.get("mag") is not None])
        # the row's own thumbnail size: the standalone default (110x26)
        # leaves the object's numbers no room at the default list width
        spark = sparkline_pixmap(pts, width=ROW_SPARK_W, height=ROW_SPARK_H,
                                 color=kind_color, y_window=window)
        spark_text = None
        if not spark.isNull():
            what = _fu.curve_summary(pts)
            if run is not None:
                # a run whose cfg carries no source is a series run (that is
                # what the series engine writes), so it must not read
                # "Manual entry"
                src = (run.get("cfg") or {}).get("source") or "measure"
                spark_text = self.tr(
                    "Last curve: {0} · {1} points · the chart's scale"
                ).format(source_label(src), what["points"])
            else:
                spark_text = self.tr("{0} nights · {1} points").format(
                    what["nights"], what["points"])
        # the one-glance numbers of the object (mag, rate, period...), in
        # the vocabulary of its own kind: the row has room for two or three
        # and the object card shows the rest
        from ..core import kinds as _kinds
        detail_text = _kinds.context_line(kind, p.get("context") or {})
        return {
            "kind": kind,
            "kind_label": kind_label, "kind_color": kind_color,
            "name": p["object_name"], "favorite": bool(p.get("favorite")),
            "campaign_name": camp_names.get(p.get("campaign_id")),
            "progress_text": dots, "next_text": next_text,
            "detail_text": detail_text,
            "activity_text": self._activity_words(p),
            "window_text": self._project_window_chip(p, full),
            "sparkline": spark,
            "sparkline_text": spark_text,
            # the icon tile's glyph, drawn by the caller (unknown kinds
            # render a flat tint tile instead)
            "icon": self._type_pixmap(kind, size=28),
            # not a widget field: the urgency tint is applied after
            "_urgency": urgency,
        }

    def _project_row_widget(self, p, attn, camp_names):
        # The single builder of a rich project row, shared by the hub list
        # and the overlay drawer (Interfaz 1.1) so their look cannot drift.
        # @args: p - the list row, attn - its attention entry or None,
        #        camp_names - {campaign id: name}
        # @return: a configured ProjectRow (payload + urgency tint)
        row = ProjectRow()
        payload = self._project_row_payload(p, attn, camp_names)
        urgency = payload.pop("_urgency", None)
        row.set_project(**payload)
        if urgency == "event":
            row.lbl_next.setStyleSheet(
                f"color: {theme.C_EVENT}; font-weight: bold;")
        elif urgency == "due":
            row.lbl_next.setStyleSheet(
                f"color: {theme.C_WARN}; font-weight: bold;")
        return row

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

    def _show_home(self):
        # No selection: the hub (the list). It only NAVIGATES to Home when
        # the observer is already in the hub or in a project: at startup
        # this is called from on_refresh_projects with no selection, and
        # switching blindly would yank the user out of Welcome.
        if self._shell_stack().currentIndex() in (VIEW_HOME, VIEW_DETAIL):
            self._goto_tab(VIEW_HOME)

    def _project_selected(self):
        items = self.projects.lst_projects.selectedItems()
        if not items:
            self._clear_project_detail()
            return
        pid = items[0].data(Qt.UserRole)
        if not project.get(db, pid):
            self._clear_project_detail()
            return
        if getattr(self, "_navigating", False):
            # history replay / programmatic selection: open without recording
            self._open_project(pid)
            return
        if (self._current_project or {}).get("id") == pid:
            # re-select of the SAME project (status change, reload): refresh
            # in place, do not push a duplicate location and do not move the
            # observer off the tab they are on
            self._open_project(pid, land="keep")
            return
        # a user pick is a navigation (Interfaz 1.1)
        self.navigate(VIEW_DETAIL, pid=pid)

    def _open_project(self, pid, land="details"):
        # Opens one project full screen: header, page and object panel. No
        # history here (the callers decide whether it is a navigation).
        # @args: pid - project id; land - the tab to open, as
        #        _build_project_page reads it ("details" by default)
        # @return: True when the project existed and was opened
        p = project.get(db, pid)
        if not p:
            return False
        self._current_project = p
        self._goto_tab(VIEW_DETAIL)
        self._sync_projects_pane()
        self._render_project_header(p)
        self._build_project_page(p, land=land)
        panel = self._get_proj_panel()
        if panel._worker is not None:
            panel.cancel()   # switching projects: drop the in-flight load
        ctx = dict(p.get("context") or {})
        ctx.setdefault("project_id", p["id"])   # B4: light-curve injection
        panel.explore(p["object_name"], fallback_target=ctx, ctx=ctx)
        return True

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
            # clicking the already-selected row reloads the detail (no
            # navigation: the location did not change, nor does the tab)
            self._open_project(item.data(Qt.UserRole), land="keep")

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
        self._sync_projects_pane()
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
        # Interfaz 1.0: drop the list's current item too, or the refresh
        # fired when we switch back to Home would re-select it and rebuild
        # the detail we are clearing (re-entrancy).
        lst = self.projects.lst_projects
        was_blocked = lst.signalsBlocked()
        lst.blockSignals(True)
        lst.setCurrentItem(None)
        lst.clearSelection()
        lst.blockSignals(was_blocked)
        self._show_home()

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

    def _section_layout(self, key):
        # One tab PAGE of the project detail (ADR-041): a flat page in
        # the scroll area with the per-kind content, and the step's state
        # chip in a slim row above it. Only one page is visible at a time,
        # the tab bar in the masthead decides which.
        #
        # No page TITLE on purpose (Interfaz 1.7): the active tab already
        # says which page you are on, and the bold label above the content
        # was 25 px of a 500 px page spent repeating it.
        # @args: key - "details"|"plan"|"analysis"|"publish"
        # @return: the page's content QLayout (where the per-kind
        #          builders add their widgets, exactly as before)
        page = QWidget(self.projects.page_container)
        page._chip = QLabel(page)
        page._chip.setStyleSheet(theme.chip_style(theme.C_PANEL))
        page._chip.setVisible(False)  # _step_section lifts it with a badge
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch(1)
        header.addWidget(page._chip)
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
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

    def _show_tab(self, key, record=False):
        # ADR-041: activate one tab page — built on first open (lazy),
        # the other pages of this project get hidden, and the bar is
        # repainted so the active tab reads "you are here". ADR-045: the
        # retired "process"/"followup" keys alias to "analysis" forever,
        # so every old deep link keeps landing.
        # @args: key - tab key ("details"|"plan"|"analysis"|"publish");
        #        record - True for a user tab click (Interfaz 1.1: a tab
        #        change is a navigation, so back returns to the old tab)
        # @return: None (a no-op when the page cannot exist here)
        if key is None or self._current_project is None:
            return
        key = {"process": "analysis", "followup": "analysis"}.get(key, key)
        if record and not getattr(self, "_navigating", False):
            self.navigate(VIEW_DETAIL, pid=self._current_project["id"],
                          tab=key)
            return
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

    def _build_project_page(self, p, land="details"):
        # The project detail (ADR-041): the object card, the steps and
        # follow-up are TAB PAGES under one scroll — one visible at a
        # time (the tab bar in the masthead decides). The object card
        # is the light page, so it builds eagerly; the step pages build
        # lazily on first open and are cached in _tab_pages.
        #
        # ADR-041 rev.: opening a project lands on the OBJECT CARD. It used
        # to land on the Next card's target (a fresh project opened on
        # Capture), which meant you landed in the middle of a workflow
        # before seeing what the object is. The Next card still says what
        # to do next and its Go button still jumps to that step; a double
        # click on a row still jumps straight to the work
        # (_project_open_activated).
        #
        # @args: p - the project dict
        #        land - which tab to open after the rebuild:
        #          "details" (default): the object card, the landing page
        #          "keep": whatever tab was open. An IN-PLACE refresh (a
        #                  survey landing, the curve after a measurement, a
        #                  reload of the same project) must not throw the
        #                  observer out of the page they are reading.
        #          "next": the Next card's target. The step machine asks
        #                  for it when a step is marked done or reopened,
        #                  so "✔ Mark done" keeps moving you forward.
        # the tab to keep, read BEFORE the wipe: _clear_project_page()
        # resets _active_tab to None
        keep = getattr(self, "_active_tab", None)
        self._clear_project_page()
        # page 0: the object card + project files (not a step)
        det = self._section_layout("details")
        panel = self._get_proj_panel()
        det.addWidget(panel)
        self._populate_project_files(p["id"])
        # the Next card fills itself (its Go button and the "Mark done"
        # chip need a target); the landing tab comes from the caller
        self._refresh_next_card(p)
        if land == "next":
            self._show_tab(self._next_target or "details")
        elif land == "keep":
            self._show_tab(keep or "details")
        else:
            self._show_tab("details")

    def _step_section(self, key):
        # Builds one tab page with its state chip in the header
        # (ADR-041). UX-PC (U3) still holds: the state ACTIONS live on
        # the Next card; the page carries only the discreet footer
        # (_step_footer).
        # @args: key - "plan"|"process"|"publish"|"followup"
        # @return: the page's content layout
        layout = self._section_layout(key)
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
        # the step machine advances: land on the step it moved to
        self._build_project_page(p, land="next")
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
        self._build_project_page(p, land="next")

    def _build_plan_tab(self, p, kind, ctx):
        # Plan & Captura (ADR-030), laid out as a mission console
        # (ADR-059): a summary strip, the night drawn as a flight strip,
        # and the plan grouped in cards (exposure, type block, sequence,
        # telescope) so the page reads as cards instead of floating labels
        # and QGroupBox chrome. Behaviour, widget keys and autosave are
        # untouched.
        from .widgets.section_card import PanelCard
        layout = self._step_section("plan")
        accent = theme.KIND_COLORS.get(kind, theme.C_ACCENT)

        # the summary strip: integration, filter and the dawn verdict, the
        # three numbers the observer reads before touching anything
        self._plan_summary_strip(layout, accent)

        # Interfaz 1.8: the plan DRAWN on the night it happens in. The same
        # band the Ficha uses for the object, here carrying the plan's own
        # duration as a block inside the dark window and the verdict the
        # observer actually asks ("does it fit before dawn?"). It is the
        # Welcome hero's trick: a picture of YOUR night, with real numbers.
        from .widgets.night_ribbon import NightRibbon
        ribbon = NightRibbon()
        layout.addWidget(ribbon)
        self._project_widgets["plan_ribbon"] = ribbon

        # --- card: exposure plan (frames / exposure / filter) -----------
        card = PanelCard(self.tr("Exposure plan"), accent)
        layout.addWidget(card)
        body = card.body
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
        body.addLayout(row)
        self._project_widgets["plan_spins"] = (spn, spn_exp, cmb_f)
        for widget in (spn, spn_exp):
            widget.valueChanged.connect(
                lambda _v: self._plan_ribbon_refresh(p, ctx))
        # the filter also feeds the summary strip
        cmb_f.currentIndexChanged.connect(
            lambda _i: self._plan_ribbon_refresh(p, ctx))
        self._plan_ribbon_refresh(p, ctx)

        # NEO: exposure calculator
        if kind in ("neo", "pccp") and ctx.get("rate_arcsec_min"):
            from ..core import exposure
            scale = exposure.plate_scale(config.get("pixel_um"),
                                          config.get("focal_mm"),
                                          config.get("pixel_binning"))
            t_max = exposure.max_exposure_no_trail(ctx["rate_arcsec_min"], scale)
            if t_max:
                body.addWidget(QLabel(
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

        # --- card: sequence (multi-filter rows + exports) ---------------
        seq_card = PanelCard(self.tr("Sequence"), accent)
        layout.addWidget(seq_card)
        sbody = seq_card.body
        # B8/Track V: SN and variable exposure hint
        # by brightness + multi-filter step rows
        if kind in ("sn", "variable") and ctx.get("mag") is not None:
            from ..core import exposure
            sn_exp = exposure.recommended_sn_exposure(ctx["mag"])
            if sn_exp:
                sbody.addWidget(QLabel(
                    f"<small>{self.tr('Recommended exposure')}: "
                    f"{sn_exp}s · {self.tr('mag')} {ctx['mag']:.1f}"
                    f" · {self.tr('guide, not SNR — confirm with a test shot')}"
                    f"</small>"))
                spn_exp.setValue(min(sn_exp, 60.0))
            # multi-filter rows: add/remove (filter × N × exp) steps.
            # The "Add filter" button shares the header row (right side),
            # so we save one full row for the button alone
            filt_head = QHBoxLayout()
            lbl_filt = QLabel(self.tr("Filters"))
            lbl_filt.setToolTip(self.tr(
                "Add a row per band: each one is its own set of frames, "
                "exposure and filter (a supernova is worth following in "
                "more than one)"))
            filt_head.addWidget(lbl_filt)
            filt_head.addStretch()
            btn_add_filt = QPushButton(self.tr("Add filter"))
            btn_add_filt.clicked.connect(lambda: self._sn_add_step_row(steps_vlay))
            filt_head.addWidget(btn_add_filt)
            sbody.addLayout(filt_head)
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
            sbody.addWidget(steps_container)
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
        sbody.addLayout(seq_row)
        # NEO: also ephemeris export
        if kind in ("neo", "pccp"):
            sbody.addWidget(QLabel(self.tr("Export ephemeris for planetarium")))
            btn_eph = QPushButton(self.tr("Export ephemeris…"))
            btn_eph.clicked.connect(self._project_export_ephem)
            sbody.addWidget(btn_eph)
        self._project_widgets["cmb_seqfmt"] = cmb_fmt
        # ADR-043: the live CCDciel control lives in the Capture step
        # itself (the Observatory tab is gone): the hardware has one home,
        # and it is the step that plans its capture
        self._build_capture_ccd_block(layout, accent)
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

    def _plan_summary_strip(self, layout, accent):
        # The three numbers the observer reads before touching anything:
        # total integration, filter and the "does it fit before dawn?"
        # verdict. KpiTiles (ADR-057), updated live from the plan spins by
        # _plan_ribbon_refresh, so the strip and the band never disagree.
        # @args: layout - the Capture page layout, accent - the kind hue
        from .widgets.kpi_tile import KpiTile
        strip = QHBoxLayout()
        strip.setSpacing(8)
        t_int = KpiTile("—", self.tr("Integration"), accent)
        t_fil = KpiTile("—", self.tr("Filter"))
        t_ver = KpiTile("—", self.tr("Before dawn"))
        for t in (t_int, t_fil, t_ver):
            strip.addWidget(t)
        strip.addStretch(1)
        layout.addLayout(strip)
        self._project_widgets["plan_kpis"] = {
            "integration": t_int, "filter": t_fil, "verdict": t_ver}

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
                # refresh the overview panel: the KPI strip and the sky
                # chart now carry the safe window (ADR-057)
                panel = self._get_proj_panel()
                if panel._e is not None:
                    panel._ctx = ctx
                    panel._render_kpis(panel._e)
                    panel._render_flags(panel._e)
                    panel._render_charts(panel._e)
            # ADR-043: silent by design: the plan auto-saves from the
            # Capture step inputs; the project bar is the visible truth

    # -- CCDciel control (ADR-030) -----------------------------------------

    def _build_capture_ccd_block(self, layout, accent=None):
        # ADR-043: the Observatory tab is gone; this is its whole control
        # panel, rebuilt per project page inside the Capture step. Built
        # in code (not a .ui) because it is small and per-project now;
        # the tr() sources keep the old ObservatoryTab strings as
        # anchors for the existing translations. The block always works
        # on the CURRENT project: listing projects inside the observatory
        # had no purpose, so there is no target-selection combo (a
        # project that is not open is not what you are looking at that
        # night).
        # ADR-059: the panel is a PanelCard now, the same card voice as the
        # rest of the Capture console. One card, four rows, and the status
        # is one row of four pairs (Interfaz 1.8 had already collapsed the
        # old three group boxes).
        # @args: layout - the Capture page layout, accent - the kind hue
        from .widgets.section_card import PanelCard
        grp = PanelCard(self.tr("Telescope and camera"),
                        accent or theme.C_ACCENT)
        gv = grp.body

        # row 1: the connection, with a colour that says which state it is
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl_s = QLabel()
        row.addWidget(lbl_s)
        row.addStretch()
        btn_c = QPushButton(self.tr("Connect CCDciel"))
        btn_d = QPushButton(self.tr("Disconnect"))
        btn_r = QPushButton(self.tr("Refresh"))
        row.addWidget(btn_c)
        row.addWidget(btn_d)
        row.addWidget(btn_r)
        gv.addLayout(row)

        # row 2: what the telescope is doing, in a 2x2 grid (hidden until
        # CCDciel answers: four dashes are 130 px of nothing)
        state = QWidget()
        grid = QHBoxLayout(state)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(18)
        lbl_v = QLabel("—")
        lbl_t = QLabel("—")
        lbl_tr = QLabel("—")
        lbl_sl = QLabel("—")
        # ONE row of four pairs: the same four values in half the height the
        # 2x2 grid took, and they still read left to right as "what version,
        # how cold, is it tracking, is it moving"
        for title, value in ((self.tr("Version"), lbl_v),
                             (self.tr("Temperature"), lbl_t),
                             (self.tr("Tracking"), lbl_tr),
                             (self.tr("Slew"), lbl_sl)):
            head = QLabel(title)
            head.setStyleSheet("color: %s; font-size: 11px;" % theme.C_TEXT_DIM)
            grid.addWidget(head)
            grid.addWidget(value)
        grid.addStretch(1)
        self._ccd_state_grp = state
        state.setVisible(False)
        gv.addWidget(state)

        # row 3: pointing
        row = QHBoxLayout()
        row.setSpacing(8)
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
        btn_refresh_pos = QPushButton(self.tr("Refresh position"))
        btn_refresh_pos.setToolTip(self.tr(
            "Re-query the orbit and the ephemeris now instead of using the "
            "cache. A preliminary orbit improves as new astrometry arrives, "
            "so a position computed from an old one can be minutes of "
            "motion off."))
        row.addWidget(btn_goto)
        row.addWidget(btn_sync)
        row.addWidget(btn_refresh_pos)
        row.addStretch()
        gv.addLayout(row)

        # row 4: live capture
        row = QHBoxLayout()
        row.setSpacing(8)
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
        lbl_co = QLabel("")
        lbl_co.setWordWrap(True)
        lbl_co.setStyleSheet("color: %s; font-size: 11px;" % theme.C_TEXT_DIM)
        # an empty label costs a line: it appears when it has coordinates to
        # name and hides again when it does not
        lbl_co.setVisible(False)
        gv.addWidget(lbl_co)
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
            "ccd_refresh_pos": btn_refresh_pos,
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
        btn_refresh_pos.clicked.connect(self._ccd_refresh_position)
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
        state_grp = getattr(self, "_ccd_state_grp", None)
        if state_grp is not None:
            # the block earns its place only when it has values: four
            # dashes are 130 px of nothing in a page that has none to spare
            state_grp.setVisible(bool(on))
        for key in ("ccd_disconnect", "ccd_refresh", "ccd_push",
                    "ccd_start", "ccd_goto", "ccd_sync"):
            widget = w.get(key)
            if widget is not None:
                widget.setEnabled(on)
        # the position refresh is a NETWORK action, not a CCDciel one: it is
        # enabled by the project (a moving target) even with the mount off,
        # because the observer may want the freshest orbit before connecting
        btn_rp = w.get("ccd_refresh_pos")
        if btn_rp is not None:
            proj = self._current_project
            btn_rp.setEnabled(bool(proj)
                              and proj.get("kind") in ("neo", "comet", "pccp"))
        cb = w.get("cmb_ccd_filter")
        if cb is not None:
            cb.setEnabled(on)
        w["ccd_connect"].setEnabled(not on)
        # Interfaz 1.8: the state is a COLOUR, not a sentence. Green with a
        # dot when CCDciel answers, amber when it does not: it is the one
        # thing the observer glances at before trusting anything else in
        # this panel, and it used to be grey text like everything else.
        if not on:
            w["ccd_status"].setText(
                "\u25cf " + self.tr("CCDciel: not connected"))
            w["ccd_status"].setStyleSheet(
                f"color: {theme.C_WARN}; font-weight: 600;")
            w["ccd_connect"].setStyleSheet(
                f"background: {theme.composite(theme.C_ACCENT, '2e')};"
                f" border: 1px solid {theme.C_ACCENT}; color: {theme.C_TEXT};")
            w["ccd_version"].setText(self.tr("—"))
            w["ccd_temp"].setText(self.tr("—"))
            w["ccd_tracking"].setText(self.tr("—"))
            w["ccd_tracking"].setStyleSheet("")
            w["ccd_slew"].setText(self.tr("—"))
            w["ccd_slew"].setStyleSheet("")
        else:
            w["ccd_status"].setText(
                "\u25cf " + f"{self.tr('CCDciel')}: "
                f"{self._ccd_client.host}:{self._ccd_client.port}"
                f" · {self._ccd_version}")
            w["ccd_status"].setStyleSheet(
                f"color: {theme.C_GOOD}; font-weight: 600;")
            w["ccd_connect"].setStyleSheet("")
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

        self._ccd_worker = hold(CcdcielWorker(self._ccd_client, action))
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
        hold(self._ccd_worker)
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
            w["ccd_tracking"].setStyleSheet("")
        elif tracking:
            w["ccd_tracking"].setText(self.tr("Tracking"))
            w["ccd_tracking"].setStyleSheet(
                f"color: {theme.C_GOOD}; font-weight: 600;")
        else:
            w["ccd_tracking"].setText(self.tr("Stopped"))
            w["ccd_tracking"].setStyleSheet(
                f"color: {theme.C_WARN}; font-weight: 600;")
        if slewing is None:
            slewing = mount.get("slewing")
        if slewing is None and "slewing" in cam:
            slewing = cam["slewing"]
        if isinstance(slewing, str):
            slewing = slewing.strip().lower() not in ("", "false", "no", "0")
        if slewing is None:
            w["ccd_slew"].setText(self.tr("—"))
            w["ccd_slew"].setStyleSheet("")
        elif slewing:
            w["ccd_slew"].setText(self.tr("Slewing…"))
            w["ccd_slew"].setStyleSheet(
                f"color: {theme.C_OK}; font-weight: 600;")
        else:
            w["ccd_slew"].setText(self.tr("Idle"))
            w["ccd_slew"].setStyleSheet(f"color: {theme.C_TEXT_DIM};")

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
        text = self._ccd_coords_text(p.get("context") or {}, p.get("kind"))
        lbl.setText(text)
        lbl.setVisible(bool(text.strip()))

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

    def _ccd_refresh_position(self):
        # Force a fresh orbit + ephemeris for the current moving target,
        # bypassing the source caches: the preliminary orbit of an
        # unconfirmed object improves as new astrometry arrives, and a
        # position computed from an old one can be minutes of motion off.
        # This is a NETWORK action (no CCDciel), so it works with the mount
        # off, and it runs on its own worker (ADR-030: never on the GUI
        # thread).
        p = self._current_project
        w = self._ccd_widgets()
        if not p or not w.get("ccd_refresh_pos"):
            return
        if p.get("kind") not in ("neo", "comet", "pccp"):
            self.statusBar().showMessage(
                self.tr("This target has fixed coordinates: there is nothing "
                        "to refresh."), 5000)
            return
        if self._pos_worker is not None and self._pos_worker.isRunning():
            return
        ctx = dict(p.get("context") or {})
        obj_id = (ctx.get("id") or ctx.get("packed")
                  or p.get("object_name") or "")
        site = config.get("mpc_code", "")
        btn = w["ccd_refresh_pos"]
        btn.setEnabled(False)
        btn.setText(self.tr("Refreshing…"))
        # a bound slot of this QObject, not a lambda: a lambda would run on
        # the worker's thread and touch the GUI from there
        self._pos_target = p
        self._pos_worker = hold(PositionRefreshWorker(obj_id, site, ctx))
        self._pos_worker.finished.connect(self._ccd_on_position_refreshed)
        self._pos_worker.start()

    def _ccd_on_position_refreshed(self, pos):
        # @args: pos - the worker's position dict (or {})
        # @return: None. The project the refresh was for is remembered so the
        #          queued slot can hand it to the shared handler.
        self._ccd_on_refreshed_position(pos, self._pos_target)

    def _ccd_on_refreshed_position(self, pos, project_row):
        # @args: pos - the worker's position dict (or {}), project_row - the
        #        project the refresh was for (the current one may have moved)
        w = self._ccd_widgets()
        btn = w.get("ccd_refresh_pos")
        if btn is not None:
            btn.setEnabled(True)
            btn.setText(self.tr("Refresh position"))
        cur = self._current_project
        if (not cur or not project_row
                or cur.get("id") != project_row.get("id")):
            return                    # the observer moved on: drop the answer
        if not pos:
            self.statusBar().showMessage(
                self.tr("No fresh position: no source resolved the object."),
                8000)
            return
        self._ccd_point_target = project_row
        self._ccd_apply_position(pos)
        src = {"horizons": self.tr("Horizons"),
               "neofixer:ephem": self.tr("NEOfixer"),
               "kepler:sbdb": self.tr("SBDB (Kepler)"),
               "kepler:neofixer": self.tr("NEOfixer (Kepler)")}.get(
                   pos.get("source"), pos.get("source") or "")
        self.statusBar().showMessage(
            self.tr("Position refreshed: %1").replace("%1", src), 6000)

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
            # ADR-048: the visit's "Measure the sequence" opens the
            # editor's series block for this visit (D8/D36)
            measure_series=lambda sid:
                self._visit_measure_series(pid, sid),
            # ADR-062, phase 7: the visit's "Astrometry" opens the editor's
            # Track & Stack tab for this visit (D15); it is the entry point
            # the observer looks for, next to the series one.
            astrometry=lambda sid:
                self._visit_astrometry(pid, sid),
            on_change=lambda: self._visit_data_changed(pid),
            # the curve below is the one of the visit you are looking at
            # (reported), so the list has to say which one that is
            on_visit_selected=lambda _sid: (
                self._fu_curve_refresh(pid),
                self._analysis_ribbon_refresh(p)),
            kind=kind)
        panel.set_project(pid)
        self._project_widgets["visits_panel"] = panel
        # Interfaz 1.7: the visits and their curve go SIDE BY SIDE. Stacked
        # they asked for ~800 px in a 630 px page, so the tab always
        # scrolled; and the two are exactly a master-detail pair: pick the
        # visit on the left, read its curve on the right. The list keeps a
        # sane width (it is a list of dates) and the chart takes the rest.
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(520)
        curve = self._analysis_curve_block(p, pid)
        # Interfaz 1.8: the night the visit happened in, drawn above the
        # visits it summarises (the same band the Ficha and Capture use).
        # In the LEFT column on purpose: the right one is the chart, and
        # the chart's column is the taller of the two, so the band costs
        # the page NOTHING. Above the chart it took 73 px off the curve and
        # left it too short to read.
        from .widgets.night_ribbon import NightRibbon
        ribbon = NightRibbon()
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(6)
        llay.addWidget(ribbon)
        llay.addWidget(panel, 1)
        self._project_widgets["analysis_ribbon"] = ribbon
        pair = QHBoxLayout()
        pair.setSpacing(10)
        pair.addWidget(left)
        pair.addWidget(curve, 1)
        # 45/55: the visits are a list of dates (they only need their own
        # column) and the chart is what wants the width
        pair.setStretch(0, 9)
        pair.setStretch(1, 11)
        layout.addLayout(pair, 1)
        self._analysis_ribbon_refresh(p)
        # ADR-062 (D): the astrometry runs of a moving object, where the
        # observer reads them back without opening the editor
        if kind in ("neo", "pccp", "comet"):
            self._analysis_astrometry_block(layout, p, pid)
        if kind == "transit":
            self._analysis_transit_block(layout, pid)
        elif kind == "hads":
            self._analysis_hads_block(layout)
        if kind in ("neo", "pccp", "comet"):
            adv = self._advanced_block(
                layout, self.tr("What you kept from the session"))
            self._build_products_block(adv, p)
        if kind in FOLLOWUP_KINDS:
            self._fu_science_blocks(layout, p, ctx, pid)
        layout.addStretch()

    # ---------------- the astrometry runs of the project (ADR-062) ------

    def _analysis_astrometry_block(self, layout, p, pid):
        # The astrometry runs, listed in the Analysis tab. The numbers
        # already live in astrometry_runs/points (phase 8); what was
        # missing was a place to READ them without opening the editor, and
        # to undo one execution without hunting for the right visit.
        # @args: layout - the Analysis section content, p - project dict,
        #        pid - project id
        # @return: None
        from .widgets.collapsible_section import CollapsibleSection
        sec = CollapsibleSection(self.tr("Astrometry runs"))
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(12, 0, 0, 0)
        sec.setContentWidget(inner)
        layout.addWidget(sec)
        hint = QLabel(self.tr(
            "Each run is one pass of the track & stack: the positions it "
            "measured, the motion it resolved and the brightness it read. "
            "The magnitude says WHO wrote it: the run itself (automatic) or "
            "a measurement you made by hand in the Photometry tab and sent "
            "to the report. The MPC report is drafted in the editor."))
        hint.setWordWrap(True)
        v.addWidget(hint)
        tbl = QTableWidget(0, 6)
        tbl.setHorizontalHeaderLabels([
            self.tr("Date"), self.tr("Observations"), self.tr("Motion"),
            self.tr("Magnitude"), self.tr("Check"), self.tr("State")])
        tbl.verticalHeader().setVisible(False)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # each column fits what it says ("17.98 G (by hand)" is the longest
        # magnitude) and the last one takes the slack
        header = tbl.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        # a project with many nights must not push the curve off the page
        tbl.setMaximumHeight(160)
        tbl.itemSelectionChanged.connect(
            lambda: self._analysis_astrometry_sync(tbl))
        v.addWidget(tbl)
        row = QHBoxLayout()
        btn_open = QPushButton(self.tr("Open in the editor"))
        btn_open.setToolTip(self.tr(
            "Open the visit's frames in the editor with the track & stack "
            "tab on stage, to re-measure or to draft the report"))
        btn_open.clicked.connect(lambda: self._analysis_astrometry_open(tbl))
        row.addWidget(btn_open)
        btn_undo = QPushButton(self.tr("Undo this run"))
        btn_undo.setToolTip(self.tr(
            "Undo the execution whole: its positions and its frame manifest "
            "go, and the run stays marked as undone for the audit"))
        btn_undo.clicked.connect(lambda: self._analysis_astrometry_undo(tbl))
        row.addWidget(btn_undo)
        row.addStretch()
        v.addLayout(row)
        note = QLabel("")
        note.setWordWrap(True)
        v.addWidget(note)
        w = self._project_widgets
        w["astrometry_runs_sec"] = sec
        w["astrometry_runs_tbl"] = tbl
        w["astrometry_runs_btn_open"] = btn_open
        w["astrometry_runs_btn_undo"] = btn_undo
        w["astrometry_runs_note"] = note
        self._analysis_astrometry_refresh(pid)

    def _analysis_astrometry_refresh(self, pid):
        # @args: pid - project id
        # @return: None. The whole section hides itself when the project has
        #          no run: an empty list of runs says nothing, and a folded
        #          block with nothing inside is noise (ADR-038).
        w = self._project_widgets
        tbl = w.get("astrometry_runs_tbl")
        if tbl is None:
            return
        from ..core import astrometry_store as store
        runs = store.list_runs(db, pid) if pid is not None else []
        sec = w.get("astrometry_runs_sec")
        if sec is not None:
            sec.setVisible(bool(runs))
        tbl.setRowCount(len(runs))
        # newest first: the run you just made is the one you are looking at
        for row, run in enumerate(reversed(runs)):
            points = store.points_for_run(db, run["id"])
            # the STACK is the object's own measurement (the per-frame one
            # is the other half of the double check): its magnitude and its
            # check are what the report carries
            stack = next((q for q in points
                          if q.get("source") == "stack"), None)
            cells = [self._astrometry_when(run),
                     str(run.get("n_obs") or run.get("points") or 0),
                     self._astrometry_motion(run),
                     self._astrometry_magnitude(stack),
                     self._astrometry_check(stack),
                     self._astrometry_state(run)]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(str(text))
                if col == 0:
                    item.setData(Qt.UserRole, run["id"])
                    item.setToolTip(self.tr(
                        "Run %1 of %2").replace(
                            "%1", str(run["id"])).replace(
                            "%2", run.get("object_name") or ""))
                if col == 4 and stack is not None and stack.get("check_note"):
                    # the check's own words, not a paraphrase of them
                    item.setToolTip(str(stack["check_note"]))
                tbl.setItem(row, col, item)
        self._analysis_astrometry_sync(tbl)

    def _astrometry_when(self, run):
        # @args: run - a run dict
        # @return: the run's timestamp, "YYYY-MM-DD HH:MM". `created` holds
        #          epoch seconds and SQLite's TEXT affinity hands them back
        #          as a string, so the number is PARSED: slicing it would
        #          print "1791221326.12345" in the Date column.
        raw = run.get("created")
        try:
            stamp = float(raw)
        except (TypeError, ValueError):
            return str(raw or "")
        return datetime.datetime.fromtimestamp(stamp).strftime(
            "%Y-%m-%d %H:%M")

    def _astrometry_motion(self, run):
        # @args: run - a run dict
        # @return: the motion the run resolved, or a dash when it did not
        rate = run.get("rate_arcsec_min")
        if not rate:
            return "—"
        text = f"{rate:.2f}″/min"
        if run.get("pa_deg") is not None:
            text += f" · PA {run['pa_deg']:.0f}°"
        return text

    def _astrometry_magnitude(self, stack):
        # @args: stack - the run's stack point, or None
        # @return: the brightness AND who wrote it. The observer must never
        #          read a magnitude without knowing whether the machine
        #          measured it or they did (D).
        if stack is None or stack.get("mag") is None:
            return "—"
        who = (self.tr("by hand") if stack.get("mag_source") == "manual"
               else self.tr("automatic"))
        band = stack.get("band") or ""
        return f"{stack['mag']:.2f} {band} ({who})".strip()

    def _astrometry_check(self, stack):
        # @args: stack - the run's stack point, or None
        # @return: the check against the other observers, in words
        if stack is None or stack.get("check_ok") is None:
            return self.tr("not checked")
        return (self.tr("in order") if stack.get("check_ok")
                else self.tr("see the note"))

    def _astrometry_state(self, run):
        # @args: run - a run dict
        # @return: what became of the execution, in words
        return {"complete": self.tr("complete"),
                "not_detected": self.tr("not detected"),
                "incomplete": self.tr("incomplete"),
                "undone": self.tr("undone")}.get(
                    run.get("status"), run.get("status") or "")

    def _analysis_astrometry_sync(self, tbl):
        # @args: tbl - the runs table
        # @return: None. Both buttons act on a selected run, so they follow
        #          the selection: a button that can act on nothing is a trap
        #          (U5).
        has = bool(tbl.selectionModel().selectedRows())
        for key in ("astrometry_runs_btn_open", "astrometry_runs_btn_undo"):
            btn = self._project_widgets.get(key)
            if btn is not None:
                btn.setEnabled(has)

    def _analysis_astrometry_selected(self, tbl):
        # @args: tbl - the runs table
        # @return: the selected run id, or None
        rows = tbl.selectionModel().selectedRows()
        if not rows:
            return None
        item = tbl.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item is not None else None

    def _analysis_astrometry_run(self, run_id):
        # @args: run_id - the execution
        # @return: its run dict, or None
        from ..core import astrometry_store as store
        pid = (self._current_project or {}).get("id")
        if pid is None:
            return None
        return next((r for r in store.list_runs(db, pid)
                     if r["id"] == run_id), None)

    def _analysis_astrometry_open(self, tbl):
        # @args: tbl - the runs table
        # @return: None. The editor opens on the run's OWN visit: a run
        #          belongs to one night, and that night is where its frames
        #          are.
        run = self._analysis_astrometry_run(
            self._analysis_astrometry_selected(tbl))
        if run is None:
            return
        if run.get("session_id") is None:
            self.statusBar().showMessage(self.tr(
                "This run has no visit behind it: open the editor from the "
                "visit whose frames you want to re-measure."), 8000)
            return
        # The run the observer PICKED is the one the editor must show, not
        # the visit's newest (a visit holds many passes)
        self._visit_astrometry(run["project_id"], run["session_id"],
                               run_id=run["id"])

    def _analysis_astrometry_undo(self, tbl):
        # @args: tbl - the runs table
        # @return: None
        run = self._analysis_astrometry_run(
            self._analysis_astrometry_selected(tbl))
        if run is None:
            return
        if QMessageBox.question(
                self, self.tr("Undo this run"),
                self.tr("Undo run %1 whole? Its positions and its frame "
                        "manifest go; the run stays marked as undone for "
                        "the audit.").replace("%1", str(run["id"]))
        ) != QMessageBox.Yes:
            return
        removed = self._ufe_astrometry_undo(run["id"])
        self._analysis_astrometry_refresh(run["project_id"])
        note = self._project_widgets.get("astrometry_runs_note")
        if note is not None:
            note.setText(self.tr(
                "Run %1 undone: %2 positions removed.").replace(
                    "%1", str(run["id"])).replace("%2", str(removed or 0)))

    def _selected_visit_id(self):
        # @return: the visits panel's selected visit id, or None
        panel = self._project_widgets.get("visits_panel")
        return panel.current_session_id() if panel is not None else None

    # ------------- the Analysis curve: the selected visit (reported) ----

    def _analysis_ribbon_refresh(self, p):
        # @args: p - the project row
        # @return: None. The band of the SELECTED visit: when its frames
        #          were shot, drawn on the night they were shot in.
        ribbon = self._project_widgets.get("analysis_ribbon")
        panel = self._project_widgets.get("visits_panel")
        if ribbon is None or panel is None:
            return
        try:
            lat = float(config.get("lat") or 0.0)
            lon = float(config.get("lon") or 0.0)
        except (TypeError, ValueError):
            lat = lon = 0.0
        if not (lat or lon):
            lat = lon = None
        ctx = p.get("context") or {}
        ribbon.set_site(lat, lon)
        ribbon.set_object(ctx.get("ra_deg"), ctx.get("dec_deg"),
                          p.get("object_name") or "")
        ribbon.set_accent(theme.KIND_COLORS.get(p.get("kind"),
                                                theme.C_ACCENT))
        sid = panel.current_session_id()
        stamps = []
        if sid is not None:
            from ..core import followup as _fu
            for img in _fu.list_images(db, sid):
                when = _parse_date_obs(img.get("date_obs"))
                if when is not None:
                    stamps.append(when)
        if len(stamps) >= 1:
            first, last = min(stamps), max(stamps)
            # one block, not one per frame: twenty ticks in a 400 px band
            # are a smear, and what the observer asks is "when was I out"
            ribbon.set_blocks([{
                "start": first, "end": max(last, first +
                                           _dt.timedelta(minutes=2)),
                "label": self.tr("{n} frames").format(n=len(stamps)),
                "color": theme.KIND_COLORS.get(p.get("kind"),
                                               theme.C_ACCENT)}])
            ribbon.set_note(self.tr("{n} frames · {span} min").format(
                n=len(stamps),
                span=int((last - first).total_seconds() // 60)),
                theme.C_TEXT_DIM)
        else:
            ribbon.set_blocks([])
            ribbon.set_note("")

    def _plan_ribbon_refresh(self, p, ctx):
        # @args: p - the project row, ctx - its context
        # @return: None. Feeds the plan's band: the site, the object's arc
        #          and ONE block, the plan itself, dropped at dusk (when an
        #          observer starts) with its total duration.
        ribbon = self._project_widgets.get("plan_ribbon")
        spins = self._project_widgets.get("plan_spins")
        if ribbon is None or spins is None:
            return
        kind = p.get("kind")
        try:
            lat = float(config.get("lat") or 0.0)
            lon = float(config.get("lon") or 0.0)
        except (TypeError, ValueError):
            lat = lon = 0.0
        if not (lat or lon):
            lat = lon = None
        ra = ctx.get("ra_deg")
        dec = ctx.get("dec_deg")
        ribbon.set_site(lat, lon)
        ribbon.set_object(ra, dec, p.get("object_name") or "")
        ribbon.set_accent(theme.KIND_COLORS.get(kind, theme.C_ACCENT))
        n_frames = int(spins[0].value())
        exp_s = float(spins[1].value())
        total_min = n_frames * exp_s / 60.0
        # the summary strip reads the same numbers as the band (ADR-059):
        # integration and filter are known before the window is
        kp = self._project_widgets.get("plan_kpis")
        if kp:
            kp["integration"].set_value(
                f"{total_min / 60.0:.1f} h" if total_min >= 90
                else f"{total_min:.0f} min")
            kp["filter"].set_value(spins[2].currentText())
        window = ribbon.window()
        if window is None:
            ribbon.set_blocks([])
            ribbon.set_note("")
            if kp:
                kp["verdict"].set_accent(None)
                kp["verdict"].set_value("—")
            return
        dusk, dawn = window
        end = min(dawn, dusk + _dt.timedelta(minutes=total_min))
        fits = (dusk + _dt.timedelta(minutes=total_min)) <= dawn
        ribbon.set_blocks([{
            "start": dusk, "end": end,
            "label": self.tr("{n} × {s} s").format(
                n=n_frames, s=("%.0f" % exp_s).replace(".0", "")),
            "color": theme.C_GOOD if fits else theme.C_WARN}])
        ribbon.set_note(
            self.tr("fits: {used} min of {dark} h").format(
                used=("%.0f" % total_min),
                dark=("%.1f" % ((dawn - dusk).total_seconds() / 3600.0)
                      ).replace(".0", ""))
            if fits else
            self.tr("does not fit before dawn"),
            theme.C_GOOD if fits else theme.C_WARN)
        if kp:
            kp["verdict"].set_accent(theme.C_GOOD if fits else theme.C_WARN)
            kp["verdict"].set_value(
                self.tr("fits") if fits else self.tr("does not fit"))

    def _analysis_curve_block(self, p, pid):
        # The light curve of the Analysis tab: THE VISIT YOU SELECTED, with
        # a switch to the whole project.
        #
        # Reported: the chart drew the project's pile of points whatever
        # visit was selected, and it only existed for the follow-up kinds
        # (sn, variable), so a transit with 1255 measured points showed no
        # curve here at all. The curve of a night is ONE pass (2026-09-30),
        # and that is what this draws by default; "all the nights" is the
        # project's curve, which is what folding a period needs.
        # @args: p - the project row, pid - the project id
        # @return: the block's widget (the caller places it: Interfaz 1.7
        #          puts it BESIDE the visits list, not under it)
        from .widgets.lightcurve_widget import LightCurveChart
        grp = QGroupBox(self.tr("Light curve"))
        glc = QVBoxLayout(grp)
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("Show:")))
        cmb = QComboBox()
        cmb.addItem(self.tr("This visit"), "visit")
        cmb.addItem(self.tr("All the nights"), "project")
        cmb.setToolTip(self.tr(
            "Which curve the chart draws: the one of the visit selected "
            "above (its own pass of the night, the normal way to look at "
            "one night) or the whole project, which is the curve of every "
            "night together, one pass per night (that is the one a period "
            "search needs)"))
        row.addWidget(cmb)
        lbl_what = QLabel("")
        lbl_what.setWordWrap(True)
        lbl_what.setStyleSheet("color: #8a90a6; font-size: 12px;")
        row.addWidget(lbl_what, 1)
        chk_tpl = QCheckBox(self.tr("Show template"))
        chk_tpl.setChecked(True)
        row.addWidget(chk_tpl)
        # the period search works on the PROJECT's curve (every night, one
        # pass each), so it lives with the curve and not in a visit's window
        # (ADR-045 review). It needs «All the nights» and enough points; the
        # refresh below decides when it shows.
        btn_phase = QPushButton(self.tr("Period and phase…"))
        btn_phase.setToolTip(self.tr(
            "Search the project's curve for its period (Lomb-Scargle and PDM) "
            "and fold it into the two-panel report, with what the baseline "
            "can and cannot say. It works on «All the nights»"))
        btn_phase.clicked.connect(lambda: self._open_phase_dialog(pid))
        row.addWidget(btn_phase)
        glc.addLayout(row)
        chart = LightCurveChart()
        chart.setMinimumHeight(190)
        glc.addWidget(chart, stretch=1)
        chk_tpl.toggled.connect(chart.set_template_visible)
        w = self._project_widgets
        w["fu_curve"] = chart
        w["fu_curve_scope"] = cmb
        w["fu_curve_what"] = lbl_what
        w["fu_curve_tpl"] = chk_tpl
        w["fu_curve_phase"] = btn_phase
        cmb.currentIndexChanged.connect(
            lambda _i: self._fu_curve_refresh(pid))
        self._fu_curve_refresh(pid)
        return grp

    def _fu_curve_points(self, pid):
        # The points the Analysis curve draws, and the words that say which
        # curve it is (a chart of "some" points is a chart nobody trusts).
        # @args: pid - the project
        # @return: (points, what)
        from ..core import followup as fu
        w = self._project_widgets
        cmb = w.get("fu_curve_scope")
        scope = cmb.currentData() if cmb is not None else "visit"
        if scope == "project":
            pts = fu.list_points(db, pid)
            summary = fu.curve_summary(pts)
            return pts, self.tr(
                "The whole project: {0} night(s), {1} points").format(
                    summary["nights"], summary["points"])
        sid = self._selected_visit_id()
        if sid is None:
            pts = fu.list_points(db, pid)
            return pts, self.tr(
                "No visit selected: the whole project ({0} points).").format(
                    len(pts))
        # the visit's own points: its pass of the series plus whatever was
        # entered by hand in that visit (never another night's)
        pts = fu.points_for_session(db, sid, series_only=False)
        session = fu.get_session(db, sid) or {}
        return pts, self.tr("Visit {0}: {1} points").format(
            session.get("obs_date") or "?", len(pts))

    def _fu_curve_refresh(self, pid):
        # Rebuilds the Analysis curve in place (the selection changed, the
        # scope changed, or a measurement was saved). The chart's own
        # template/fold follows the kind, and the checkbox that toggles it
        # is hidden when there is no template to show.
        # @args: pid - the project
        # @return: None
        w = self._project_widgets
        chart = w.get("fu_curve")
        if chart is None:
            return
        p = project.get(db, pid)
        if p is None:
            return
        from ..core import lightcurve_data
        ctx = p.get("context") or {}
        pts, what = self._fu_curve_points(pid)
        payload = lightcurve_data.build_payload(
            {"points": pts, "sn_type": ctx.get("sn_type")},
            sn_type_fallback=ctx.get("sn_type") or ctx.get("otype"),
            variable=ctx.get("variable"))
        chart.set_data(
            payload["points"],
            sn_type=payload.get("sn_type"),
            peak_mjd=payload.get("peak_mjd"),
            peak_mag=payload.get("peak_mag"),
            fold_period_d=payload.get("fold_period_d"),
            epoch_mjd=payload.get("epoch_mjd"),
            schematic=payload.get("schematic"))
        lbl = w.get("fu_curve_what")
        if lbl is not None:
            lbl.setText(what)
        chk = w.get("fu_curve_tpl")
        if chk is not None:
            has_overlay = bool(payload.get("sn_type")
                               or payload.get("schematic"))
            chk.setVisible(has_overlay)
        # the period search needs the whole project's curve and enough
        # points to say anything
        btn = w.get("fu_curve_phase")
        if btn is not None:
            cmb = w.get("fu_curve_scope")
            scope = cmb.currentData() if cmb is not None else "visit"
            btn.setVisible(scope == "project" and len(pts) >= 4)

    # ------------- the per-kind analysis blocks (ADR-045; absorbed from
    # the retired Process tab; the SN FITS-import/blink block is gone for
    # good: a visit's plate opens in the editor, which owns blink,
    # measure and annotate) -------------

    def _analysis_transit_block(self, layout, pid):
        # Track D (subplan 4d): the reduction is 100% external (EXOTIC,
        # NASA/JPL). The reduce itself lives in the editor next to the
        # sequence it needs (ADR-048 follow-up), so here is the door in.
        # @args: layout - the Analysis column, pid - the project id
        layout.addWidget(QLabel(self.tr(
            "Reduce the photometry with EXOTIC (NASA/JPL), in your own "
            "Python ≤3.10 environment.")))
        btn_reduce = QPushButton(
            self.tr("Open the visit in the editor (reduce with EXOTIC)…"))
        btn_reduce.setToolTip(self.tr(
            "Open this project's visit in the editor: build the comparison "
            "sequence there and run «Reduce and fit with EXOTIC…» next to it"))
        btn_reduce.clicked.connect(
            lambda: self._open_transit_visit_editor(pid))
        layout.addWidget(btn_reduce)
        btn_exotic = QPushButton(
            self.tr("Export to EXOTIC (inits.json)…"))
        btn_exotic.setToolTip(self.tr(
            "Pre-filled EXOTIC initialization file: planet, observatory, "
            "camera and filter — EXOTIC skips its wizard where it can"))
        btn_exotic.clicked.connect(lambda: self._transit_export_exotic(pid))
        layout.addWidget(btn_exotic)
        # the last reduction, if there is one: its numbers here and the whole
        # result (light curve + every file) one click away, so the door does
        # not need the editor
        last = self._exotic_result_text(pid)
        if last:
            lbl_last = QLabel(last)
            lbl_last.setWordWrap(True)
            lbl_last.setStyleSheet("color: #8a90a6; font-size: 12px;")
            layout.addWidget(lbl_last)
            btn_result = QPushButton(
                self.tr("See the last reduction…"))
            btn_result.setToolTip(self.tr(
                "The fitted parameters, the light curve EXOTIC drew and "
                "every file the reduction wrote, each one a double click "
                "from the system"))
            btn_result.clicked.connect(
                lambda: self._open_exotic_result(pid))
            layout.addWidget(btn_result)
        lbl_exotic = QLabel(self.tr(
            "After the reduction, upload EXOTIC's output file to "
            "ExoClock (exoclock.space) and/or the AAVSO Exoplanet "
            "Database — and tell the story when you publish."))
        lbl_exotic.setWordWrap(True)
        layout.addWidget(lbl_exotic)

    def _open_transit_visit_editor(self, pid):
        # The selected visit (or the newest) opens in the editor with the
        # series and the EXOTIC block armed.
        # @args: pid - the project id
        sid = self._selected_visit_id()
        if sid is None:
            from ..core import followup as fu
            sessions = fu.list_sessions(db, pid)
            sid = sessions[0]["id"] if sessions else None
        if sid is None:
            self.statusBar().showMessage(self.tr(
                "This project has no visit yet: attach the frames first."),
                8000)
            return
        self._visit_measure_series(pid, sid)

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

    def _load_editor_sequence(self, dlg, pid, path):
        # ADR-047/048: restore a plate's saved working state when it has
        # one; whatever it leaves empty is filled with the project's saved
        # sequence (so a series or an EXOTIC reduction finds the comps
        # already built, never the bare "no comparison stars"). A plate
        # state saved without a sequence no longer blocks the project one.
        # @args: dlg - the UfeDialog, pid - project id, path - open plate
        row = project.find_file(db, pid, path) if path else None
        meta = (row or {}).get("meta") or {}
        if meta.get("ufe"):
            dlg.apply_plate_state(meta["ufe"])
        p = project.get(db, pid) or {}
        ctx = p.get("context") or {}
        dlg.load_saved_sequence(ctx.get("sequence"))
        # the object's magnitude, from the project (the planner put it
        # there, or the astrometry measured it): the Compare tab's proposal
        # anchors on it, and without this it showed a default nobody chose.
        # A host double from before the magnitude existed simply has no
        # setter, and that is not an error.
        setter = getattr(dlg, "set_target_magnitude", None)
        if callable(setter):
            # with its origin: "measured" after a run, "predicted" from the
            # planner, "manual" if the observer set it. The field says which,
            # because the proposal anchors the comparison stars on this figure
            setter(ctx.get("mag"), ctx.get("mag_origin"))

    def _ufe_sequence_hook(self, pid, state):
        # The editor's sequence changed by the observer: keep it in the
        # project context (and its target magnitude), so reopening the
        # visit brings the comparison stars back instead of rebuilding them.
        # @args: pid - project id, state - the Compare tab's sequence dict
        entries = (state or {}).get("entries") or []
        ctx_update = {"sequence": {
            "catalog": state.get("catalog"),
            "catalog_name": state.get("catalog_name"),
            "fov_arcmin": state.get("fov_arcmin"),
            "target_mag": state.get("target_mag"),
            "entries": entries}}
        if state.get("target_mag"):
            # only a magnitude somebody chose becomes the project's: the
            # sentinel ("no data") is falsy on purpose, so a widget default
            # can never be written here as if it were data
            ctx_update["mag"] = state["target_mag"]
            # the observer's own figure (the Compare tab's field): neither a
            # prediction nor a measurement of ours
            ctx_update["mag_origin"] = "manual"
        project.update_context(db, pid, ctx_update)

    def _visit_open_in_editor(self, pid, path, sid):
        # A visit's plate opens in the UFE with everything attached: the
        # object context, and both hooks land on THIS visit (ADR-045:
        # nothing attaches without one).
        # @args: pid - project id, path - the FITS to open, sid - visit id
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
        # is one; without it, the project's saved sequence fills the
        # Compare tab (ADR-048 follow-up: EXOTIC finds the comps)
        self._load_editor_sequence(dlg, pid, path)

    def _open_phase_dialog(self, pid):
        # The period + phase window (quality plan, C): it takes the
        # project's own curve, whatever measured it, and remembers the
        # period in the project when the observer says so.
        # @args: pid - the project id
        # @return: the dialog, or None when there are no points yet
        from .phase_dialog import collect_project_points, open_phase
        pts = collect_project_points(db, pid)
        if not pts:
            self.statusBar().showMessage(self.tr(
                "This project has no measured points yet: measure the "
                "series (or import a curve) first."), 8000)
            return None
        p = project.get(db, pid) or {}
        kind = p.get("kind")
        if kind not in ("sn", "hads", "variable", "transit"):
            self.statusBar().showMessage(self.tr(
                "The period search is for light-curve projects (a "
                "variable, a HADS star, a supernova)."), 8000)
            return None
        return open_phase(self, pts,
                          title=p.get("object_name") or "",
                          lang=self._lang(), db=db, project_id=pid)

    def _visit_measure_series(self, pid, session_id):
        # ADR-048 (D8/D36): the visit's frames become a series. The
        # editor opens on the visit's first plate (the reference WCS) with
        # the series block armed; a visit with no FITS says so.
        # @args: pid - project id, session_id - the visit
        files = project.files_for_session(db, session_id)
        paths = sorted(f["path"] for f in files
                       if f.get("kind") == "fits" and f.get("path"))
        if not paths:
            self.statusBar().showMessage(
                self.tr("This visit has no FITS frames to measure."), 8000)
            return
        p = project.get(db, pid)
        if not p:
            return
        obj = self._ufe_object_from_project(p)
        dlg = self._ufe_open("measure", hook_pid=pid, obj=obj,
                             session_id=session_id)
        dlg.open_plate(paths[0])
        dlg.set_object(obj)
        # ADR-048 follow-up: the series/EXOTIC flow starts from the
        # sequence already built (plate state first, project second)
        self._load_editor_sequence(dlg, pid, paths[0])

    def _visit_astrometry(self, pid, session_id, run_id=None):
        # ADR-062, phase 7 (D15): the visit's frames become a track & stack
        # run. The editor opens on the visit's first plate with the visit
        # armed (the astrometry hook), and the Track & Stack tab on stage.
        # @args: pid - project id, session_id - the visit, run_id - the
        #        execution the editor must SHOW (the one picked in the
        #        Analysis tab's list), or None for the newest (the visit's
        #        own button, whose meaning is "the last pass of this night")
        # A visit accumulates several passes, and the tab restores the LAST
        # one unless it is told otherwise: without this, opening the
        # 2-observation run of a visit whose last pass was 1 observation
        # showed 1 (reported 2026-10-07).
        self._astrometry_run_pref = (
            (pid, session_id, int(run_id)) if run_id is not None else None)
        files = project.files_for_session(db, session_id)
        paths = sorted(f["path"] for f in files
                       if f.get("kind") == "fits" and f.get("path"))
        if not paths:
            self.statusBar().showMessage(
                self.tr("This visit has no FITS frames to stack."), 8000)
            return
        p = project.get(db, pid)
        if not p:
            return
        obj = self._ufe_object_from_project(p)
        dlg = self._ufe_open("trackstack", hook_pid=pid, obj=obj,
                             session_id=session_id)
        dlg.open_plate(paths[0])
        dlg.set_object(obj)
        show = getattr(dlg, "show_tab", None)
        if callable(show):
            show("trackstack")

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
        p = project.get(db, pid)
        if not p:
            return
        obj = self._ufe_object_from_project(p)
        dlg = self._ufe_open("measure", hook_pid=pid, obj=obj,
                             session_id=pt.get("session_id"))
        if not dlg.open_plate(row["path"]):
            return
        dlg.set_object(obj)
        # the same restore as "restore in the editor" (and, without a
        # saved plate state, the project's sequence: ADR-048 follow-up)
        self._load_editor_sequence(dlg, pid, row["path"])

    def _visit_data_changed(self, pid):
        # A visit or its contents changed (the panel owns the edit): the
        # reactive blocks refresh in place — the user's place in the
        # visits list is never lost to a full page rebuild.
        w = self._project_widgets
        p = project.get(db, pid)
        if p is None:
            return
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
            # the curve follows the visit and the scope the observer chose
            self._fu_curve_refresh(pid)
        if w.get("astrometry_runs_tbl") is not None:
            # a visit changed: the runs list is the observer's own record of
            # what they measured and it is never stale
            self._analysis_astrometry_refresh(pid)
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
        from .widgets.section_card import PanelCard
        tr = ctx.get("transit") or {}
        plan_data = next((s["data"] for s in p["steps"]
                          if s["step"] == "plan"), {})
        grp = PanelCard(self.tr("Transit capture plan"),
                        theme.KIND_COLORS.get(p.get("kind"), theme.C_ACCENT))
        gl = grp.body

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
        from .widgets.section_card import PanelCard
        h = ctx.get("hads") or {}
        plan_data = next((s["data"] for s in p["steps"]
                          if s["step"] == "plan"), {})
        grp = PanelCard(self.tr("HADS capture plan"),
                        theme.KIND_COLORS.get(p.get("kind"), theme.C_ACCENT))
        gl = grp.body

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
        from .widgets.section_card import PanelCard
        v = ctx.get("variable") or {}
        grp = PanelCard(self.tr("Variable star plan"),
                        theme.KIND_COLORS.get(p.get("kind"), theme.C_ACCENT))
        gl = grp.body
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
                        "defocus helps"))
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

    def _transit_export_exotic(self, pid=None):
        # 4d: enrich the planet (worker — the GUI never blocks on the
        # network; the Archive row is cached from the Details tab anyway),
        # then write the pre-filled inits.json next to a user-chosen path.
        # @args: pid - the project id (None: the project in the main tab)
        pid = pid or (self._current_project or {}).get("id")
        if pid is None:
            return
        p = project.get(db, pid)
        if not p:
            return
        from .workers import ExploreWorker
        self.statusBar().showMessage(
            self.tr("Gathering planet data for EXOTIC…"), 4000)
        worker = ExploreWorker(config, p["object_name"],
                               fallback_target=p.get("context") or {})
        worker.finished.connect(lambda e: self._exotic_write(pid, e))
        self._keep(worker)
        worker.start()

    # -------------------- the UFE's EXOTIC block (ADR-048 follow-up)

    def _ufe_exotic_reduce(self, pid, session_id):
        # The reduce button in the editor: the open frame is the reference
        # and the loaded sequence the comparison stars, so the reduction
        # never fails for a sequence the project has not saved yet.
        dlg = getattr(self, "_ufe", None)
        ref = None
        entries = []
        if dlg is not None and getattr(dlg, "state", None) is not None:
            ref = dlg.state.path if dlg.state.has_image else None
            entries = list(dlg.tab_compare.entries())
        self._exotic_overrides = {"ref": ref, "entries": entries,
                                  "session_id": session_id}
        self._transit_reduce_exotic(pid)

    def _ufe_exotic_export(self, pid, session_id):
        # The handoff file (the wizard-style inits.json); the loaded
        # sequence is registered first so the project carries it.
        dlg = getattr(self, "_ufe", None)
        if dlg is not None and getattr(dlg, "state", None) is not None \
                and dlg.state.has_image:
            self._register_editor_sequence(pid, session_id, dlg)
        self._transit_export_exotic(pid)

    def _register_editor_sequence(self, pid, session_id, dlg):
        # Persists the editor's current sequence into the project context
        # (and the open plate's saved state), so the export/handoff never
        # works from an unsaved one.
        entries = dlg.tab_compare.entries()
        if not entries:
            return
        state = dlg.tab_compare.capture_state() or {}
        ctx_update = {"sequence": {
            "catalog": state.get("catalog"),
            "catalog_name": state.get("catalog_name"),
            "fov_arcmin": state.get("fov_arcmin"),
            "target_mag": state.get("target_mag"),
            "entries": state.get("entries") or []}}
        if state.get("target_mag"):
            # only a magnitude somebody chose becomes the project's: the
            # sentinel ("no data") is falsy on purpose, so a widget default
            # can never be written here as if it were data
            ctx_update["mag"] = state["target_mag"]
            # the observer's own figure (the Compare tab's field): neither a
            # prediction nor a measurement of ours
            ctx_update["mag_origin"] = "manual"
        project.update_context(db, pid, ctx_update)

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
        project.add_file_once(db, pid, path, "exotic_inits")
        self._populate_project_files(pid)
        self.statusBar().showMessage(
            self.tr("inits.json written — run EXOTIC in your Python ≤3.10 "
                    "environment"), 10000)

    def _transit_reduce_exotic(self, pid=None):
        # Gather the planet data (worker), then run the orchestration.
        # @args: pid - the project id (None: the project in the main tab)
        pid = pid or (self._current_project or {}).get("id")
        if pid is None:
            return
        p = project.get(db, pid)
        if not p:
            return
        from .workers import ExploreWorker
        self.statusBar().showMessage(
            self.tr("Gathering planet data for EXOTIC…"), 4000)
        self._show_exotic_prep(self.tr("Gathering planet data for EXOTIC…"))
        worker = ExploreWorker(config, p["object_name"],
                               fallback_target=p.get("context") or {})
        self._exotic_gather_worker = worker
        worker.finished.connect(lambda e: self._exotic_reduce(pid, e))
        self._keep(worker)
        worker.start()

    def _show_exotic_prep(self, text):
        # One visible dialog across the gather / probe / inits steps, so
        # «Reduce and fit with EXOTIC…» is never a silent wait (ADR-052).
        if getattr(self, "_exotic_prep", None) is None:
            wait = QProgressDialog(text, self.tr("Cancel"), 0, 0, self)
            wait.setWindowTitle(self.tr("EXOTIC"))
            wait.setWindowModality(Qt.NonModal)
            wait.setMinimumDuration(0)
            wait.setAutoClose(False)
            wait.setAutoReset(False)
            wait.canceled.connect(self._cancel_exotic_prep)
            wait.show()
            self._exotic_prep = wait
        else:
            self._exotic_prep.setLabelText(text)
        return self._exotic_prep

    def _close_exotic_prep(self):
        wait = getattr(self, "_exotic_prep", None)
        if wait is not None:
            wait.blockSignals(True)     # close() emits canceled()
            wait.close()
            wait.deleteLater()
            self._exotic_prep = None

    def _cancel_exotic_prep(self):
        # The dialog's Cancel: stop whichever worker is in flight.
        for name in ("_exotic_gather_worker", "_exotic_probe_worker",
                     "_solve_worker"):
            w = getattr(self, name, None)
            if w is not None and hasattr(w, "cancel"):
                try:
                    w.cancel()
                except Exception:
                    pass
        self._close_exotic_prep()
        self.statusBar().showMessage(self.tr("EXOTIC cancelled"), 4000)

    def _exotic_reduce(self, pid, e):
        # Gather the planet data (worker), check the environment and run
        # EXOTIC headless; the result is imported on finish (phase E).
        # The interpreter check runs off the GUI thread: detect_python
        # spawns subprocesses and the cold import of exotic can take
        # minutes, which used to freeze the app for the whole probe. The
        # visible dialog covers the check; the flow resumes on the report.
        # @args: pid - the project id, e - the ExploreWorker's enriched
        #        dict
        p = project.get(db, pid)
        if not p:
            self._close_exotic_prep()
            return
        if not e or not e.get("data"):
            from PySide6.QtWidgets import QMessageBox
            self._close_exotic_prep()
            QMessageBox.warning(self, self.tr("EXOTIC"), self.tr(
                "No planet data was found for «{0}»: check the name or "
                "the connection and retry.").format(
                    (p or {}).get("object_name") or ""))
            return
        # the interpreter that has EXOTIC: the user's own Python 3.10 (the
        # cleanest on Windows) or the venv the app prepared
        from .workers import ProbeExoticWorker
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.statusBar().showMessage(
            self.tr("Checking the EXOTIC environment…"), 0)
        self._show_exotic_prep(self.tr("Checking the EXOTIC environment…"))
        worker = ProbeExoticWorker(config.get("exotic_python_path") or None)
        self._exotic_probe_worker = worker
        worker.finished.connect(
            lambda rep: self._exotic_reduce_go(pid, e, rep))
        self._keep(worker)
        worker.start()

    def _exotic_reduce_go(self, pid, e, rep):
        # The environment check landed: warn and stop, or run the
        # orchestration on the interpreter the probe validated.
        # @args: pid - the project id, e - the enriched planet data,
        #        rep - the probe report {"ok","version","message","python"}
        QApplication.restoreOverrideCursor()
        self.statusBar().clearMessage()
        self._close_exotic_prep()
        self._exotic_probe_worker = None
        python = rep.get("python") or ""
        if not python:
            QMessageBox.warning(self, self.tr("EXOTIC"), self.tr(
                "No Python 3.10 found. Install it (python.org, ticking the "
                "py launcher) and run «pip install exotic» in it, or use "
                "«Prepare environment» in Settings → EXOTIC."))
            return
        if not rep.get("ok"):
            QMessageBox.warning(self, self.tr("EXOTIC"), self.tr(
                "This Python has no EXOTIC installed: run «pip install "
                "exotic» in it, or use «Prepare environment» in Settings → "
                "EXOTIC."))
            return
        self._exotic_launch(pid, e, python)

    def _exotic_launch(self, pid, e, python):
        # Guarded entry: an exception anywhere in the handoff (a read-only
        # folder, a bad header) must land in a box, never vanish in the
        # console while the observer stares at a flashed dialog.
        try:
            self._exotic_launch_impl(pid, e, python)
        except Exception as err:
            logger.exception("EXOTIC launch failed: %s", err)
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, self.tr("EXOTIC"), self.tr(
                "The EXOTIC reduction could not be prepared:\n\n{0}")
                .format(err))

    def _exotic_launch_impl(self, pid, e, python):
        # Generate the visit's inits.json and run EXOTIC headless; the
        # result is imported on finish (phase E).
        # @args: pid - the project id, e - the enriched planet data,
        #        python - the interpreter the probe validated
        from PySide6.QtWidgets import QMessageBox
        from ..core import exotic, fits_io, wcs as wcs_mod
        p = project.get(db, pid)
        if not p:
            return
        # the visit's frames: the UFE hook names its session (ADR-048
        # follow-up); the Analysis route takes the latest visit with FITS
        from ..core import followup as fu
        over = getattr(self, "_exotic_overrides", None) or {}
        want_sid = over.get("session_id")
        sessions = fu.list_sessions(db, pid)
        if want_sid is not None:
            sessions = [s for s in sessions if s["id"] == want_sid] or sessions
        session_id, frame_paths = None, []
        for s in sessions:
            fs = [f["path"] for f in project.files_for_session(db, s["id"])
                  if f.get("kind") == "fits"]
            if fs:
                session_id, frame_paths = s["id"], fs
                break
        if not frame_paths:
            QMessageBox.warning(self, self.tr("EXOTIC"), self.tr(
                "This project has no FITS frames in a visit yet."))
            return
        # the UFE hook selects the open frame as the reference and passes
        # the sequence it has loaded; the Analysis route falls back to the
        # first frame and the project's saved sequence
        ref = over.get("ref")
        if ref not in frame_paths:
            ref = frame_paths[0]
        entries = over.get("entries") or None
        self._exotic_overrides = None
        try:
            header, _data = fits_io.read_fits(ref)
        except Exception:
            header = {}
        wcs = wcs_mod.Wcs.from_header(header)
        if wcs is None:
            # ADR-051: the reference frame is solved with the configured
            # solver and the reduction continues with that WCS; never ask
            # the observer for pixel coordinates
            self._exotic_solve_first(pid, e, python, frame_paths,
                                     session_id, header, ref, entries)
            return
        self._exotic_launch_final(pid, e, python, frame_paths, session_id,
                                  wcs, ref, entries)

    def _exotic_solve_first(self, pid, e, python, frame_paths, session_id,
                            header, ref=None, entries=None):
        # No WCS on the reference frame: blind-solve it off the GUI thread
        # (the ADR-051 dispatcher honours the configured solver), then
        # continue the reduction with the solved WCS. The solution is
        # persisted into the FITS (ADR-051 rev).
        from PySide6.QtWidgets import QMessageBox, QProgressDialog
        from ..core import blink, wcs as wcs_mod
        from .workers import UfeSolveWorker
        ref = ref or frame_paths[0]
        self.statusBar().showMessage(
            self.tr("The first frame has no WCS: solving it…"), 0)
        # the project's own coordinates go with the solve: they are what
        # keeps ASTAP from sweeping the sky (0.1 s against a minute)
        proj = project.get(db, pid) or {}
        ctx = proj.get("context") or {}
        ra, dec = ctx.get("ra_deg"), ctx.get("dec_deg")
        pointing = (ra, dec) if ra is not None and dec is not None else None
        worker = UfeSolveWorker(Path(ref), pointing=pointing)
        # the same feedback as the editor (ADR-051 rev.): an indeterminate
        # dialog with a Cancel that kills the solver
        wait = QProgressDialog(
            self.tr("The first frame has no WCS: solving it…"),
            self.tr("Cancel"), 0, 0, self)
        wait.setWindowTitle(self.tr("EXOTIC"))
        wait.setWindowModality(Qt.NonModal)
        wait.setMinimumDuration(0)
        wait.setAutoClose(False)
        wait.setAutoReset(False)
        wait.canceled.connect(worker.cancel)
        wait.show()
        worker.progress.connect(
            lambda s: wait.setLabelText(
                self.tr("Solving: {0}…").format((s or "")[:70])))

        def done(cards):
            # closing a QProgressDialog emits canceled(): block it, this is
            # the solve landing, not the observer cancelling
            wait.blockSignals(True)
            wait.close()
            wait.deleteLater()
            self.statusBar().clearMessage()
            if worker.cancelled():
                return
            if not cards:
                QMessageBox.warning(
                    self, self.tr("EXOTIC"),
                    self.tr("The first frame has no WCS and it could not be "
                            "solved. Check the solver in Settings: ASTAP "
                            "path or Astrometry.net key."))
                return
            self._persist_solution(ref, cards)
            wcs = wcs_mod.Wcs.from_header(
                blink.merge_solved_wcs(header, cards))
            if wcs is None:
                QMessageBox.warning(
                    self, self.tr("EXOTIC"),
                    self.tr("The solution of the first frame is not usable "
                            "(non-TAN WCS)."))
                return
            self._exotic_launch_final(pid, e, python, frame_paths,
                                      session_id, wcs, ref, entries)
        worker.finished.connect(done)
        self._keep(worker)
        worker.start()

    def _persist_solution(self, path, cards):
        # ADR-051 rev: store the solved WCS in the FITS so the frame is
        # solved everywhere; a write problem is reported, never fatal.
        # @args: path - the solved FITS, cards - solved WCS cards
        from ..core import wcs_store
        _done, err = wcs_store.persist_solution(path, cards)
        if err:
            self.statusBar().showMessage(
                self.tr("The solved WCS could not be written into the file "
                        "({0}); it stays in memory for this session.")
                .format(err), 8000)
        return err == ""

    def _exotic_launch_final(self, pid, e, python, frame_paths, session_id,
                             wcs, ref=None, entries=None):
        # Guarded: the handoff write runs right after the prep dialog
        # closes, so any error must be shown, not swallowed.
        try:
            self._exotic_launch_final_impl(pid, e, python, frame_paths,
                                           session_id, wcs, ref, entries)
        except Exception as err:
            logger.exception("EXOTIC handoff failed: %s", err)
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, self.tr("EXOTIC"), self.tr(
                "The EXOTIC reduction could not be prepared:\n\n{0}")
                .format(err))

    def _exotic_launch_final_impl(self, pid, e, python, frame_paths,
                                  session_id, wcs, ref=None, entries=None):
        # The reference WCS is in hand: target and comparison pixels come
        # from it (never hand-entered); without a sequence the observer is
        # sent to build it in the editor.
        # @args: wcs - the reference frame's usable WCS, ref - the
        #        reference frame (defaults to the first), entries - the
        #        sequence from the UFE (None: the project's saved one)
        from PySide6.QtWidgets import QMessageBox
        from ..core import exotic
        p = project.get(db, pid)
        if not p:
            return
        obj = self._ufe_object_from_project(p)
        ctx = p.get("context") or {}
        if entries is None:
            entries = (ctx.get("sequence") or {}).get("entries") or []
        tx = ty = None
        if (obj or {}).get("ra") is not None:
            try:
                tx, ty = wcs.sky_to_pixel(obj["ra"], obj["dec"])
            except Exception:
                tx = ty = None
        comps = []
        for ent in entries:
            star = ent.get("star") or {}
            if star.get("ra") is None:
                continue
            try:
                comps.append(wcs.sky_to_pixel(star["ra"], star["dec"]))
            except Exception:
                continue
        if tx is None:
            QMessageBox.warning(self, self.tr("EXOTIC"), self.tr(
                "The target position is unknown: attach the object to the "
                "project or set its coordinates."))
            return
        if not comps:
            QMessageBox.warning(self, self.tr("EXOTIC"), self.tr(
                "No comparison stars: build the sequence in the editor "
                "(Photometry, «Build the sequence…») before reducing with "
                "EXOTIC."))
            return
        plan_data = next((s["data"] for s in p["steps"]
                          if s["step"] == "plan"), {})
        plan = {"filter": plan_data.get("filter", "L"),
                "exp_s": plan_data.get("exp_s")}
        work = Path(project.storage_dir(p)) / "exotic"
        work.mkdir(parents=True, exist_ok=True)   # EXOTIC writes here too
        inits = exotic.make_inits_for_visit(
            ctx, e["data"], config, frame_paths, (tx, ty), comps,
            plan=plan, out_dir=str(work))
        inits_path = work / "inits.json"
        exotic.export_inits(inits, inits_path)
        project.add_file_once(db, pid, str(inits_path), "exotic_inits",
                              session_id=session_id)
        self._populate_project_files(pid)
        self._exotic_pid = pid
        self._exotic_session = session_id
        basis = plan.get("filter") or "V"
        self._exotic_filter = "V" if basis in ("L", "CV", None) else basis
        from .workers import ExoticRunWorker
        self._exotic_worker = hold(ExoticRunWorker(python, str(work),
                                                   str(inits_path)))
        self._exotic_progress_dialog()
        self._exotic_worker.progress.connect(self._exotic_progress_line)
        self._exotic_worker.finished.connect(
            lambda res: self._exotic_done(res))
        self._exotic_worker.start()
        self.statusBar().showMessage(
            self.tr("Running EXOTIC (this can take a while)…"), 0)

    def _exotic_progress_dialog(self):
        # P2 #21: a run takes up to hours, so it gets a progress dialog
        # with a Cancel that really stops it (the worker kills EXOTIC's
        # whole process tree). Non-modal, unlike the house's WindowModal
        # busy dialogs: those cover seconds of network work, and freezing
        # the window for two hours is not an option. Indeterminate:
        # EXOTIC's log gives no percentage, only the line it is on.
        # @args: none
        # @return: the shown dialog, kept on self._exotic_wait
        wait = QProgressDialog(
            self.tr("Running EXOTIC (this can take a while)…"),
            self.tr("Cancel"), 0, 0, self)
        wait.setWindowTitle(self.tr("EXOTIC"))
        wait.setWindowModality(Qt.NonModal)
        wait.setMinimumDuration(0)
        # only _exotic_reap_wait closes it: the run's end is the report,
        # not a value the bar ever reaches
        wait.setAutoClose(False)
        wait.setAutoReset(False)
        wait.canceled.connect(self._exotic_cancel)
        wait.show()
        self._exotic_wait = wait
        return wait

    def _exotic_progress_line(self, line):
        # A log line from the worker: the dialog's label and the status
        # bar both say where EXOTIC is (a silent two-hour run reads as a
        # hung app).
        # @args: line - one log line, already stripped
        # @return: nothing
        stage = self._exotic_stage(line)
        if not stage:
            return
        wait = getattr(self, "_exotic_wait", None)
        if wait is not None and Shiboken.isValid(wait):
            wait.setLabelText(stage[-120:])
        self.statusBar().showMessage(stage[-120:], 0)

    def _exotic_stage(self, line):
        # Turns one raw log line into something the observer can read, and
        # drops the noise. EXOTIC's spinner ("Thinking | ...") repeats the
        # same text for minutes and reads as a hang: it is exactly what the
        # astrometry.net wait looked like (2026-09-30, the run that never
        # moved). "Finding transformation i of N" is its real per-frame
        # progress, so it becomes a plain counter.
        # @args: line - one raw log line
        # @return: the readable stage, or "" when the line is only noise
        # EXOTIC colours its warnings, and the raw escapes ended up in the
        # label ("[33m  Warning: ..."): drop them before showing the text.
        text = re.sub(r"\x1b\[[0-9;]*m", "", line or "").strip()
        if not text or text.startswith("Thinking"):
            return ""
        m = re.match(r"Finding transformation (\d+) of (\d+)", text)
        if m:
            return self.tr("Reducing frame {0} of {1}…").format(
                m.group(1), m.group(2))
        # EXOTIC prints this once per aperture / comparison-star combination
        # whose frames do not straddle the transit: 1143 times in a 142-frame
        # run (measured 2026-09-30), and the observer read it as a failure. It
        # is its own diagnostic about that one combination, not about the
        # reduction (the fit of the whole night is unaffected), so the label
        # says what is really happening instead of repeating it.
        if "not within the observations" in text:
            return self.tr("Comparing apertures and comparison stars…")
        return text

    def _exotic_cancel(self):
        # The dialog's Cancel: ask the worker to stop (it takes EXOTIC's
        # process tree down and reports "cancelled" when it lands) and
        # say so where the user is looking; the dialog goes on the report.
        # @args: none
        # @return: nothing
        worker = getattr(self, "_exotic_worker", None)
        if worker is not None:
            worker.cancel()
        wait = getattr(self, "_exotic_wait", None)
        if wait is not None and Shiboken.isValid(wait):
            wait.setLabelText(self.tr("Cancelling EXOTIC…"))
        self.statusBar().showMessage(self.tr("Cancelling EXOTIC…"), 0)

    def _exotic_reap_wait(self):
        # The run ended (finished, failed or cancelled): the dialog is
        # closed and reaped BEFORE anything else runs, so no box lands on
        # top of it (close() + deleteLater(), the discipline of e31f394).
        # @args: none
        # @return: nothing
        wait = getattr(self, "_exotic_wait", None)
        self._exotic_wait = None
        if wait is not None and Shiboken.isValid(wait):
            wait.close()
            wait.deleteLater()

    def _exotic_done(self, res):
        # EXOTIC finished: import its curve and parameters into the project.
        from PySide6.QtWidgets import QMessageBox
        from ..core import exotic_import
        self._exotic_worker = None
        self._exotic_reap_wait()
        self.statusBar().clearMessage()
        pid = getattr(self, "_exotic_pid", None)
        if res.get("cancelled"):
            # the user stopped it: no error box, just the plain outcome
            self.statusBar().showMessage(
                self.tr("EXOTIC cancelled: nothing was imported."), 8000)
            return
        if res.get("timed_out"):
            # it ran past the limit and was killed: say that, not "did not
            # finish", which would send the observer hunting a crash
            QMessageBox.warning(self, self.tr("EXOTIC"), self.tr(
                "EXOTIC ran past its time limit and was stopped. The last "
                "lines of its log:\n\n{0}"
            ).format(_exotic_log_tail(res.get("log_path"))
                     or self.tr("(the log is empty)")))
            return
        if not res.get("ok") or pid is None:
            # P2 #21: the user reads what EXOTIC said, not where its log
            # lives: the last lines of the log, in plain language.
            QMessageBox.warning(self, self.tr("EXOTIC"), self.tr(
                "EXOTIC did not finish. The last lines of its log:\n\n{0}"
            ).format(_exotic_log_tail(res.get("log_path"))
                     or self.tr("(the log is empty)")))
            return
        result = exotic_import.load_result(res["out_dir"])
        sid = getattr(self, "_exotic_session", None)
        _run_id, n = exotic_import.persist(
            db, pid, sid, result,
            filter_name=getattr(self, "_exotic_filter", None))
        # the products are the visit's resources from now on (they open from
        # its window, ADR-045)
        self._register_exotic_products(pid, sid, res["out_dir"])
        par = result.get("params") or {}
        msg = self.tr(
            "EXOTIC finished: {0} points imported.\n"
            "T_mid = {1} (BJD_TDB)\nRp/Rs = {2}").format(
                n,
                f"{par.get('tmid'):.5f} ± {par.get('tmid_err'):.5f}"
                if par.get("tmid") else "?",
                f"{par.get('rprs'):.4f} ± {par.get('rprs_err'):.4f}"
                if par.get("rprs") else "?")
        QMessageBox.information(self, self.tr("EXOTIC"), msg)
        self._project_selected()
        # ... and the result itself lands on screen: the numbers, the light
        # curve EXOTIC drew and every file it wrote, instead of a box that
        # says them once and a folder nobody knows about
        self._open_exotic_result(pid, sid, out_dir=res["out_dir"],
                                 params=result.get("params"),
                                 when=datetime.datetime.now())

    def _exotic_last_run(self, pid, session_id=None):
        # The newest EXOTIC reduction of a project (or of one visit), with
        # what the result window needs: its fitted parameters and its work
        # folder. The parameters live in the run (they were saved and nobody
        # read them back); the folder is deterministic.
        # @args: pid - the project, session_id - the visit, or None for any
        # @return: {"params", "created", "session_id", "out_dir"} or None
        from ..core import followup as fu
        sessions = ([fu.get_session(db, session_id)] if session_id is not None
                    else fu.list_sessions(db, pid))
        runs = []
        for s in sessions:
            if not s:
                continue
            runs += fu.runs_for_session(db, s["id"], series_only=False)
        exotic = [r for r in runs
                  if (r.get("cfg") or {}).get("source") == "exotic"]
        if not exotic:
            return None
        run = max(exotic, key=lambda r: r.get("created") or 0)
        p = project.get(db, pid) or {}
        return {"params": (run["cfg"] or {}).get("params") or {},
                "created": run.get("created"),
                "session_id": run.get("session_id"),
                "out_dir": str(Path(project.storage_dir(p)) / "exotic")}

    def _exotic_result_text(self, pid, session_id=None):
        # The one line the editor's EXOTIC block shows about the last
        # reduction: the two numbers an observer looks for first.
        # @args: pid - the project, session_id - the visit, or None
        # @return: the text, or "" when the visit has no reduction yet
        last = self._exotic_last_run(pid, session_id)
        if not last:
            return ""
        par = last.get("params") or {}
        if par.get("tmid") is None:
            return self.tr("EXOTIC ran, but left no fitted result.")
        stamp = ""
        if last.get("created"):
            stamp = datetime.datetime.fromtimestamp(
                last["created"]).strftime("%d %b %Y %H:%M")
        bits = [self.tr("T_mid {0} ± {1}").format(
                    f"{par['tmid']:.5f}", f"{par.get('tmid_err') or 0:.5f}")]
        if par.get("rprs") is not None:
            bits.append(self.tr("Rp/Rs {0} ± {1}").format(
                f"{par['rprs']:.4f}", f"{par.get('rprs_err') or 0:.4f}"))
        if stamp:
            bits.append(stamp)
        return " · ".join(bits)

    def _register_exotic_products(self, pid, session_id, out_dir):
        # The reduction's products become resources of the visit (ADR-045):
        # the light curve, the AAVSO report and the parameters then show up
        # in the visit's window and open from there, so nobody has to go
        # digging in the work folder. One entry per path, however many times
        # the result is imported or saved.
        # @args: pid - the project, session_id - the visit, out_dir - the
        #        work folder the reduction wrote into
        # @return: how many were registered now (0 when they were there)
        from ..core import exotic_import
        kinds = {"figure": "exotic_figure", "aavso": "exotic_aavso",
                 "params": "exotic_params"}
        n = 0
        for role, path in exotic_import.find_products(out_dir):
            kind = kinds.get(role)
            if kind is None or not path.lower().endswith((".png", ".txt",
                                                          ".json")):
                continue
            _fid, created = project.add_file_once(
                db, pid, path, kind, session_id=session_id)
            if created:
                n += 1
        if n:
            self._populate_project_files(pid)
        return n

    def _open_exotic_result(self, pid, session_id=None, out_dir=None,
                            params=None, when=None):
        # The result window: the numbers, the light curve EXOTIC drew and
        # every file the reduction wrote. Non-modal, like the period window,
        # so the observer keeps working with it open.
        # @args: pid - the project, session_id - the visit, out_dir/params/
        #        when - the run just finished (None: the last one on record)
        # @return: the dialog, or None when there is nothing to show
        from .exotic_result_dialog import open_exotic_result
        last = self._exotic_last_run(pid, session_id) or {}
        out_dir = out_dir or last.get("out_dir")
        if not out_dir:
            return None
        sid = session_id or last.get("session_id")
        p = project.get(db, pid) or {}
        return open_exotic_result(
            self, out_dir,
            params=params if params is not None else last.get("params"),
            # the window's title is the project's identity, in the list's own
            # language: the same payload the workbench's badge gets
            badge=self._ufe_project_badge_payload(pid),
            title=p.get("object_name") or "",
            when=when or (datetime.datetime.fromtimestamp(last["created"])
                          if last.get("created") else None),
            save_fn=(lambda: self._register_exotic_products(pid, sid,
                                                            out_dir))
            if sid is not None else None)

    def _exotic_open_folder(self, pid):
        # The reduction's work folder, with the file manager: opening it is
        # the OS's job (the pattern of Help > Open the log), and the path
        # lands in the status bar for whoever prefers a terminal.
        # @args: pid - the project
        # @return: nothing
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        p = project.get(db, pid) or {}
        folder = Path(project.storage_dir(p)) / "exotic"
        if not folder.is_dir():
            self.statusBar().showMessage(self.tr(
                "No EXOTIC folder yet: run a reduction first."), 8000)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self.statusBar().showMessage(str(folder), 8000)

    def _build_publish_tab(self, p, kind, ctx):
        # Publicar (ADR-045), redesigned 2026-10-09: the post panel lives IN
        # the page, in the same card voice as Capture (ADR-059), instead of a
        # modal dialog. The template is the offline answer; the AI is opt-in.
        # The page never generates on its own: the observer presses a button,
        # and a busy bar covers the wait (a local reasoning model can take a
        # couple of minutes).
        from .widgets.section_card import PanelCard
        from PySide6.QtWidgets import QTabWidget
        layout = self._step_section("publish")
        accent = theme.KIND_COLORS.get(kind, theme.C_ACCENT)
        name = p["object_name"]

        post_w = QWidget()
        self._project_widgets["post_panel"] = post_w

        # --- card: the draft (actions, folder, progress) ----------------
        card = PanelCard(self.tr("Draft"), accent)
        layout.addWidget(card)
        body = card.body
        intro_txt = self.tr(
            "Turn this observation into a post. The template works offline; "
            "the AI (experimental) drafts from your own data.")
        intro = QLabel(f"<small>{intro_txt}</small>")
        intro.setWordWrap(True)
        body.addWidget(intro)

        actions = QHBoxLayout()
        btn_generate = QPushButton(self.tr("Generate"))
        # The AI half of this panel is experimental: say so on the button and
        # in the help, so nobody takes a model's draft for the app's own word
        btn_ai = QPushButton(self.tr("Write with AI (experimental)…"))
        btn_ai.setToolTip(self.tr(
            "Experimental: an optional language model drafts the post from "
            "your own data; the offline template is the other button."))
        btn_brief = QPushButton(self.tr("What will be sent…"))
        btn_brief.setToolTip(self.tr(
            "Experimental: show exactly what leaves your machine when you "
            "generate with the model."))
        for b in (btn_generate, btn_ai, btn_brief):
            actions.addWidget(b)
        actions.addStretch(1)
        body.addLayout(actions)

        lbl_ai_note = QLabel()
        lbl_ai_note.setWordWrap(True)
        lbl_ai_note.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        body.addWidget(lbl_ai_note)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel(self.tr("Save to:")))
        edt_folder = QLineEdit()
        edt_folder.setPlaceholderText(
            self.tr("Folder for the drafts and charts"))
        btn_browse = QPushButton(self.tr("Browse…"))
        folder_row.addWidget(edt_folder, 1)
        folder_row.addWidget(btn_browse)
        body.addLayout(folder_row)

        progress = QProgressBar()
        progress.setRange(0, 0)          # indeterminate: the model is opaque
        progress.setTextVisible(False)
        progress.setVisible(False)
        body.addWidget(progress)

        lbl_files = QLabel()
        lbl_files.setWordWrap(True)
        body.addWidget(lbl_files)

        # --- card: the text (ES / EN / X) -------------------------------
        card2 = PanelCard(self.tr("Text"), accent)
        layout.addWidget(card2)
        tabs = QTabWidget()
        for label, key in (("ES", "es"), ("EN", "en"), ("X", "tweet")):
            page = QWidget()
            v = QVBoxLayout(page)
            edt = QTextEdit()
            btn = QPushButton(self.tr("Copy"))
            v.addWidget(edt, 1)
            v.addWidget(btn)
            tabs.addTab(page, label)
            setattr(post_w, f"txt_{key}", edt)
            setattr(post_w, f"btn_copy_{key}", btn)
        card2.body.addWidget(tabs)

        # --- card: the long report (ES / EN), when the setting is on -----
        # It is hidden when the long report is off: without it there is
        # nothing to put here, and an empty card would be furniture.
        report_card = PanelCard(self.tr("Long report"), accent)
        report_card.setVisible(bool(config.get("ai_long_report")))
        layout.addWidget(report_card)
        rtabs = QTabWidget()
        for label, key in (("ES", "report_es"), ("EN", "report_en")):
            page = QWidget()
            v = QVBoxLayout(page)
            edt = QTextEdit()
            btn = QPushButton(self.tr("Copy"))
            v.addWidget(edt, 1)
            v.addWidget(btn)
            rtabs.addTab(page, label)
            setattr(post_w, f"txt_{key}", edt)
            setattr(post_w, f"btn_copy_{key}", btn)
        report_card.body.addWidget(rtabs)

        post_w.btn_generate = btn_generate
        post_w.btn_ai_generate = btn_ai
        post_w.btn_ai_brief = btn_brief
        post_w.lbl_ai_note = lbl_ai_note
        post_w.edt_folder = edt_folder
        post_w.btn_folder_browse = btn_browse
        post_w.progress = progress
        post_w.lbl_files = lbl_files
        post_w.report_card = report_card
        post_w._enriched = None
        post_w._brief = None

        self._wire_post_panel(post_w, name)
        self._post_note(post_w)
        layout.addStretch(1)

    def _wire_post_panel(self, post_w, name):
        # The post panel's wiring: the default folder (the project's own), the
        # generate / copy / AI buttons. One place, since the panel is built in
        # code now.
        # @args: post_w - the panel widget, name - the object's name
        # @return: None
        default_folder = str(paths.data_dir() / "posts")
        if self._current_project:
            default_folder = str(project.storage_dir(self._current_project))
        post_w.edt_folder.setText(default_folder)
        post_w.btn_folder_browse.clicked.connect(
            lambda: self._post_browse_folder(post_w))
        post_w.btn_generate.clicked.connect(
            lambda: self._post_generate(post_w, name))
        post_w.btn_ai_generate.clicked.connect(
            lambda: self._post_generate_ai(post_w, name))
        post_w.btn_ai_brief.clicked.connect(
            lambda: self._post_show_brief(post_w))
        for key in ("es", "en", "tweet", "report_es", "report_en"):
            edt = getattr(post_w, f"txt_{key}", None)
            btn = getattr(post_w, f"btn_copy_{key}", None)
            if edt is not None and btn is not None:
                btn.clicked.connect(
                    lambda _c=False, e=edt:
                    QApplication.clipboard().setText(e.toPlainText()))

    def _post_note(self, post_w):
        # The AI note under the actions: which model is ready, that the AI is
        # off, or that there is no endpoint. The template is always the
        # offline answer (ADR-075).
        # @args: post_w - the panel widget
        # @return: None
        from ..core.sources import llm
        if llm.is_enabled(config):
            base = self.tr("AI model (experimental): {0}").replace(
                "{0}", config.get("ai_model", ""))
            if config.get("ai_long_report"):
                if llm.is_local(config.get("ai_base_url")):
                    base += " · " + self.tr(
                        "long report on; a local model costs nothing")
                else:
                    base += " · " + self.tr(
                        "long report on; a cloud model spends many tokens "
                        "and may cost")
            post_w.lbl_ai_note.setText(base)
            return
        post_w.btn_ai_generate.setEnabled(False)
        post_w.btn_ai_brief.setEnabled(False)
        if not config.get("ai_enabled"):
            post_w.lbl_ai_note.setText(self.tr(
                "The AI is off: the template writes the post."))
        else:
            post_w.lbl_ai_note.setText(self.tr(
                "No language model configured: the template writes the post."))

    def _post_busy(self, post_w, on, msg=""):
        # The busy state: an indeterminate bar (the model is opaque) and the
        # buttons off while a worker runs. A local reasoning model can take a
        # couple of minutes, so the page says so instead of looking frozen.
        # @args: post_w - the panel widget, on - busy?, msg - the line to show
        # @return: None
        from ..core.sources import llm
        post_w.progress.setVisible(on)
        post_w.btn_generate.setEnabled(not on)
        post_w.btn_ai_generate.setEnabled(not on and llm.is_enabled(config))
        post_w.btn_ai_brief.setEnabled(not on)
        if msg:
            post_w.lbl_files.setText(msg)
        elif not on:
            # finished: the "drafting" line must not linger on screen after
            # the answer has arrived (the note carries the real status)
            post_w.lbl_files.setText("")

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
        used = camp.get("points", len(camp_pts))
        text = self.tr("{n} nights · {p} points").format(
            n=camp.get("nights", 0), p=used)
        skipped = len(camp_pts) - used
        if skipped > 0:
            text += self.tr(" · {0} without magnitude ignored").format(skipped)
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
        # the sequence status line, the campaign summary and the SN-only
        # animation block (the light curve moved up, under the visits:
        # _analysis_curve_block).
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

        # Inline light curve: it lives right under the visits manager now
        # (see _analysis_curve_block), for EVERY kind with a curve and
        # following the selected visit. Here stays what is kind-specific:
        # the campaign summary and, for an SN, the animation block.
        if kind in ("sn", "variable"):
            # campaign summary over the saved points (ADR-044): the series
            # engine reports how the campaign goes so far, rebuilt on tab
            # open and refreshed in place after each saved point
            grp_camp = QFrame()
            grp_camp.setObjectName("fu_campaign_summary")
            g_camp = QHBoxLayout(grp_camp)
            g_camp.setContentsMargins(10, 4, 10, 4)
            g_camp.setSpacing(8)
            head_camp = QLabel(self.tr("Campaign summary"))
            head_camp.setStyleSheet(
                "color: %s; font-weight: 700;" % theme.C_TEXT_DIM)
            g_camp.addWidget(head_camp)
            camp_lbl = QLabel("")
            camp_lbl.setObjectName("fu_campaign_text")
            camp_lbl.setWordWrap(True)
            g_camp.addWidget(camp_lbl, 1)
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
        # B10: the annotated FITS opens in the unified editor; the observer
        # picks which of the registered stacked FITS to annotate (several
        # visits => several plates), checks the marker, overlays and stretch,
        # and only then confirms: a copy is written with the SN marked (AIJ
        # ANNOTATE card) at that moment. The editor's Annotate tab is the only
        # door since the classic dialog retired (2026-10-07).
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
        # the whole object attaches (marker on its sky position), the other
        # visits queue as extra plates, and written copies register through
        # the editor's save hook
        obj = self._ufe_object_from_project(p)
        dlg = self._ufe_open("annotate", hook_pid=pid, obj=obj)
        if not dlg.open_plate(images[-1]["fits_path"]):
            return
        dlg.set_object(obj)              # re-apply on the fresh plate
        dlg.tab_annotate.prefill(
            notes=self.tr("SN follow-up"),
            extra_paths=[im["fits_path"] for im in images[:-1]])

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
        # ADR-048 follow-up: the sequence already built comes back (plate
        # state first, project second), so the Compare tab is not empty
        self._load_editor_sequence(dlg, pid, fits_path)

    def _fu_sequence_dialog(self, pid):
        # The comparison chart lives in the unified editor (ADR-044):
        # the project's newest registered plate when there is one, else
        # the Compare tab's own survey (DSS2) download. The classic
        # options dialog, its SequenceWorker and its picker retired on
        # 2026-10-07, when the UFE became the only door (ADR-044 rev.).
        self._fu_sequence_via_ufe(pid)

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
        # the report's columns are the observer's choice (quality plan, A2):
        # one colleague wants the curve, another wants the quality controls
        lst_cols = QListWidget()
        lst_cols.setSelectionMode(QListWidget.NoSelection)
        lst_cols.setMaximumHeight(190)
        for key, label in photometry_export.column_labels(self._lang()):
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked
                               if key in photometry_export.DEFAULT_COLUMNS
                               else Qt.Unchecked)
            lst_cols.addItem(item)
        lvl_cols = QLabel(self.tr(
            "The columns of the file. The header always carries the "
            "canonical name of each column, so a colleague's reader does "
            "not break because of the language."))
        lvl_cols.setWordWrap(True)
        form.addRow(lvl_cols)
        form.addRow(lst_cols)
        box = QDialogButtonBox(QDialogButtonBox.Save
                               | QDialogButtonBox.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() != QDialog.Accepted:
            return
        columns = [lst_cols.item(i).data(Qt.UserRole)
                   for i in range(lst_cols.count())
                   if lst_cols.item(i).checkState() == Qt.Checked]
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
                                                comp_stars=comps,
                                                columns=columns or None,
                                                **meta)
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
            self._build_project_page(project.get(db, pid), land="keep")
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
        # rebuild the page so the curve/points update in place, without
        # moving the observer off the tab they are reading
        self._build_project_page(project.get(db, pid), land="keep")

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
        if kind not in project.VALID_KINDS:
            # an ad-hoc Explore (Tools) has no planner target, so no kind:
            # infer it from the enriched object type (exoplanet -> transit...)
            from ..core import kinds as kinds_mod
            kind = kinds_mod.project_kind(target)
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
                  "variable", "campaign", "project_id", "notes")
                 if target.get(k) is not None}
        if ctx.get("mag") is not None:
            # WHERE the figure comes from, said out loud (2026-10-07). The
            # planner's magnitude is a PREDICTION (an ephemeris, a catalogue,
            # an alert) and a stack run later overwrites it with a
            # MEASUREMENT: the same field, two very different things, and the
            # app uses it to choose the comparison stars. The stack already
            # says which of the two it carries (NS_MAGSR); the project had no
            # way to say it, and reading 18.28 could not tell you whether
            # anybody had measured it.
            # The name is mag_ORIGIN and not mag_source on purpose: the
            # points table already has a mag_source that answers a
            # different question (WHO wrote the figure: "auto" or
            # "manual"), and two things with the same name is how a
            # provenance gets lost.
            ctx["mag_origin"] = "predicted"
        p = project.create(db, kind, name, ctx)
        if p:
            self.on_refresh_projects()
            # Interfaz 1.1: the creation flow ends on the project. Coming
            # from the new-project view, Tonight is REPLACED, so "back"
            # returns to the hub, not to the search.
            from_tonight = (self._shell_stack().currentIndex() == VIEW_TONIGHT)
            self.navigate(VIEW_DETAIL, pid=p["id"], replace=from_tonight)
            self.statusBar().showMessage(
                self.tr("Project created: %1").replace("%1", name), 8000)
        return p

    def _new_project_from_target(self, target):
        # The new-project bar (search or manual form) built a target dict:
        # create the project and clear the bar on success (the creation
        # path itself navigates to the project).
        # @args: target - a planner-target dict from the bar
        p = self._create_project(target)
        if p is not None and getattr(self, "_newbar", None) is not None:
            self._newbar.reset()
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
        # Jumps to this project's full-screen view (UX-d). Interfaz 1.1:
        # recorded as a navigation so "back" returns to where we came from.
        # @return: True when the project exists
        self.on_refresh_projects()
        if not project.get(db, pid):
            return False
        self.navigate(VIEW_DETAIL, pid=pid)
        return True

    def _goto_campaigns(self, cid=None):
        # Jumps to the Campaigns view, optionally selecting a campaign
        # (the landing spot of every campaign link, UX-d).
        self.navigate(VIEW_CAMPAIGNS, cid=cid)

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
                (self.tr("Measure the campaign pass…"), self._camp_pass),
                ("SEP", None),
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
        # what a campaign IS, right where the user meets the concept. It
        # explains the idea and does NOT name an example: a help that cites a
        # particular object ages badly and reads as if that were the only
        # case (the same rule the stacking helps follow).
        QMessageBox.information(
            self, self.tr("What is a campaign?"),
            self.tr("A campaign groups the projects of one shared "
                    "observation effort: several nights, several "
                    "observatories, one goal.\n\n"
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
        self.navigate(VIEW_DETAIL, pid=match["id"])
        return True

    # ---------------- Contextual dialogs (Explore / Post / Blink) --------

    def _tools_explore(self):
        # Tools > Explore object: the entry dialog that explains, in one
        # line, what the feature is for (the top-bar search is the quick
        # door for whoever already knows the name). The lookup itself is
        # untouched: the dialog only collects the name and hands it over.
        from .explore_dialog import ExploreDialog
        dlg = ExploreDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.name():
            self._open_explore_dialog(dlg.name())

    def _nav_explore(self):
        # The top-bar search: type a name, Enter, straight to the object's
        # card. It is the always-visible door to objects tonight's list does
        # not suggest. The field is cleared afterwards so it does not read
        # as a stale filter once the card is up.
        edt = self._menus.edt_nav_explore
        name = edt.text().strip()
        if not name:
            return
        edt.clear()
        self._open_explore_dialog(name)

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
            # an ad-hoc Explore has no planner target: borrow the kind and
            # the coordinates the enriched panel already knows, so the
            # project layer can create it (exoplanet -> transit, ...)
            e = getattr(panel, "_e", None) or {}
            if e.get("type") and not t.get("kind"):
                t["type"] = e["type"]
            data = e.get("data") or {}
            for src, dst in (("ra", "ra_deg"), ("ra_deg", "ra_deg"),
                             ("dec", "dec_deg"), ("dec_deg", "dec_deg"),
                             ("mag", "mag"), ("vmag", "mag")):
                if t.get(dst) is None and data.get(src) is not None:
                    t[dst] = data[src]
            return t

        def _on_create(nm, fb):
            # the CTA said "create a fresh project on this object". `fb`
            # is the planner target (Tonight) or None for an ad-hoc
            # Tools-menu name. PySide6 passes only the declared args.
            # Only close the dialog when the project was really created
            # (UX, U0.2); on failure the reason is shown IN the dialog
            # (the main status bar is hidden behind this modal).
            from PySide6.QtWidgets import QMessageBox
            if self._create_project(_target(nm, fb)) is not None:
                dlg.accept()
            else:
                QMessageBox.warning(dlg, self.tr("Create project"),
                                    self.tr("Could not create the project: "
                                            "the object kind could not be "
                                            "determined."))

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

    def _post_browse_folder(self, post_w):
        # @args: post_w - the post panel widget
        # @return: None; asks for a folder and fills edt_folder
        start = post_w.edt_folder.text().strip() or str(paths.data_dir())
        folder = QFileDialog.getExistingDirectory(
            self, self.tr("Choose the folder for the post files"), start)
        if folder:
            post_w.edt_folder.setText(folder)

    def _post_folder(self, post_w):
        # @args: post_w - the post panel widget
        # @return: Path of the chosen folder (created if missing)
        folder = post_w.edt_folder.text().strip() or str(paths.data_dir())
        p = Path(folder)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _post_generate(self, post_w, name):
        # The offline template draft (the fallback that always works).
        # @args: post_w - the panel, name - the object
        # @return: None
        self._post_busy(post_w, True, self.tr("Building the draft…"))
        self.statusBar().showMessage(self.tr("Building drafts…"))
        fallback = next((t for t, _s, _p, _ph in self._tonight_all
                         if t["id"] == name or t["name"] == name), None)
        w = PostWorker(config, name, fallback_target=fallback)
        w.finished.connect(lambda e, r: self._post_done(post_w, name, e, r))
        self._keep(w)
        w.start()

    def _post_generate_ai(self, post_w, name):
        # Draft with the model (ADR-075). The template already on screen
        # stays: a failure is said, never silent, and never empties the
        # boxes the observer may already be editing. A local reasoning model
        # can take a couple of minutes, hence the busy bar.
        # @args: post_w - the panel, name - the object
        # @return: None
        from ..core.sources import llm
        if not llm.is_enabled(config):
            self._post_note(post_w)
            return
        proj = self._current_project
        if not (proj and proj.get("object_name") == name):
            proj = {"id": None, "kind": "", "object_name": name,
                    "context": {}, "status": ""}
        fallback = next((t for t, _s, _p, _ph in self._tonight_all
                         if t["id"] == name or t["name"] == name), None)
        # the long report is the setting's decision; the images are rendered
        # in the worker (it needs their exact names to put them in the brief)
        long = bool(config.get("ai_long_report"))
        safe = "".join(c if c.isalnum() or c in "-_" else "_"
                       for c in name)
        outdir = self._post_folder(post_w)
        self._post_busy(post_w, True, self.tr(
            "The model is drafting. A reasoning model can take a couple of "
            "minutes."))
        w = AiPostWorker(config, proj, db,
                         enriched=getattr(post_w, "_enriched", None),
                         fallback_target=fallback, long=long,
                         outdir=outdir, safe=safe)
        w.done.connect(
            lambda brief, rendered, charts, resources, err:
            self._post_ai_done(post_w, name, brief, rendered, charts,
                               resources, err))
        self._keep(w)
        w.start()

    def _post_ai_done(self, post_w, name, brief, rendered, charts, resources,
                      err):
        # The AI answer: the long report (when the setting is on), the short
        # post and the tweet, plus the images the worker rendered. It goes
        # through the SAME save path as the template, so the images are
        # linked, the files written and the project updated either way.
        self._post_busy(post_w, False)
        if not rendered:
            post_w.lbl_ai_note.setText(self.tr("AI draft failed: ") + err)
            return
        post_w._brief = brief
        self._post_save_and_register(post_w, name, rendered, charts, resources)
        if err:
            # the report failed but the short post came back: keep it and be
            # honest about what failed (never a silent downgrade)
            post_w.lbl_ai_note.setText(
                self.tr("The long report failed; the short post was "
                        "written: ") + err)
        else:
            post_w.lbl_ai_note.setText(self.tr(
                "AI draft ready. Review it before publishing: the voice is "
                "yours."))

    def _post_save_and_register(self, post_w, name, rendered, charts,
                                resources):
        # The one save path for both drafts: writes the text files (with the
        # gallery attached), shows the final texts and registers every file
        # in the project. Shared by the template and the AI so neither can
        # forget a step (the AI path used to save nothing at all).
        # @args: post_w - the panel, name - the object, rendered - the text
        #        dict, charts/resources - {key: Path} (may be empty)
        # @return: None
        from ..core import post as post_mod
        outdir = self._post_folder(post_w)
        written = post_mod.save_outputs(
            rendered, outdir, name, e={"name": name},
            charts=charts or None, cfg=config,
            resources=resources or None)
        post_w.txt_es.setPlainText(rendered.get("es", ""))
        post_w.txt_en.setPlainText(rendered.get("en", ""))
        post_w.txt_tweet.setPlainText(rendered.get("tweet", ""))
        if rendered.get("report_es") and hasattr(post_w, "txt_report_es"):
            post_w.txt_report_es.setPlainText(rendered["report_es"])
            post_w.txt_report_en.setPlainText(rendered.get("report_en", ""))
            card = getattr(post_w, "report_card", None)
            if card is not None:
                card.setVisible(True)
        db.mark_posted(name)
        # A4: register every written file (posts + report + tweet) in the
        # project, plus charts and resources, and refresh the files list
        if self._current_project \
                and self._current_project["object_name"] == name:
            pid = self._current_project["id"]
            for key, p in written.items():
                if key in ("es", "en", "tweet", "report_es", "report_en"):
                    project.add_file(db, pid, str(p), "post")
            for p in (charts or {}).values():
                project.add_file(db, pid, str(p), "chart")
            for p in (resources or {}).values():
                project.add_file(db, pid, str(p), "chart")
            self._populate_project_files(pid)
        post_w.lbl_files.setText(
            self.tr("Saved to: ") + ", ".join(str(p) for p in written.values()))
        self.statusBar().showMessage(self.tr("Drafts ready"), 5000)

    def _post_show_brief(self, post_w):
        # The exact fact sheet the model reads (ADR-075): the observer sees
        # what would leave the machine before it does. No network here: it
        # is the same builder the writer uses.
        from ..core import object_brief
        brief = getattr(post_w, "_brief", None)
        if not brief:
            proj = self._current_project
            if not proj:
                return
            brief = object_brief.build_brief(
                proj, db, enriched=getattr(post_w, "_enriched", None),
                lang=config.ui_language(), cfg=config,
                long=bool(config.get("ai_long_report")))
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("What will be sent"))
        lay = QVBoxLayout(dlg)
        # the long report keeps the deep facts too, so the preview shows
        # exactly the bytes the model would read
        edt = QTextEdit(object_brief.to_text(
            brief, deep=bool(config.get("ai_long_report"))))
        edt.setReadOnly(True)
        lay.addWidget(edt)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(dlg.reject)
        lay.addWidget(box)
        dlg.resize(640, 560)
        dlg.exec()

    def _post_done(self, post_w, name, e, rendered):
        self._post_busy(post_w, False)
        post_w._enriched = e
        if not rendered:
            post_w.lbl_files.setText(self.tr("Not found: ") + name)
            return
        from ..core import post as post_mod
        # B9: inject the project's follow-up photometry so the light curve
        # can be drawn in the post (the panel does this for the Details tab;
        # the post flow must do it too: the post is the living document)
        if self._current_project \
                and self._current_project["object_name"] == name:
            from ..core import followup as fu
            pts = fu.list_points(db, self._current_project["id"])
            if pts:
                e.setdefault("data", {}).setdefault("followup", {})["points"] = pts
        outdir = self._post_folder(post_w)
        safe = "".join(c if c.isalnum() or c in "-_" else "_"
                       for c in name)
        charts, resources = {}, {}
        # charts for the post, drawn with a stable per-object name so the
        # markdown can reference them (they end up next to the .md), plus any
        # blink/evolution resource already in the folder
        try:
            charts, resources = post_mod.collect_assets(e, outdir, safe,
                                                        cfg=config)
        except Exception as err:  # charts must never break the post flow
            logger.warning("post charts failed for %s: %s", name, err)
        self._post_save_and_register(post_w, name, rendered, charts, resources)

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
            lambda _u: self.navigate(VIEW_TONIGHT))
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

    def _ufe_page(self):
        # Fills the fixed workbench page (VIEW_UFE) with the editor only.
        # Interfaz 1.3: the host "Back" bar is gone — the general
        # navigation stack (the top bar, Alt+Left, the mouse) already
        # returns to wherever the workbench was opened from. Built once;
        # the workbench's interior is the same widget as always.
        if getattr(self, "_ufe_page_built", False):
            return self._ufe_page_widget
        from PySide6.QtWidgets import QVBoxLayout
        lay = QVBoxLayout(self._ufe_page_widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._ufe_build(), 1)
        self._ufe_page_built = True
        return self._ufe_page_widget

    def _ufe_back(self):
        # Leaves the workbench: back to where it was opened from (the
        # project, or Home), or Home when there is no history.
        if self._nav_back:
            self.back()
        elif self._current_project is not None:
            self.navigate(VIEW_DETAIL, pid=self._current_project["id"])
        else:
            self.navigate(VIEW_HOME)

    def _ufe_project_badge_payload(self, pid):
        # The badge's payload, built by the SAME function the project list
        # rows use (G): same kind chip, same hue, same words.
        # @args: pid - the project this window is open for
        # @return: the kwargs of ProjectRow.set_project, or None
        from ..core import campaign as _camp
        row = project.get(db, pid)
        if not row:
            return None
        camp_names = {c["id"]: c["name"] for c in _camp.list_campaigns(db)}
        payload = self._project_row_payload(row, None, camp_names)
        payload.pop("_urgency", None)
        return payload

    def _tools_ufe(self):
        # Menu Tools → FITS editor… (ADR-044)
        dlg = self._ufe_build()
        begin = getattr(dlg, "begin_session", None)
        if callable(begin):
            begin(None)              # ad-hoc: its own session (issue report)
        dlg.set_save_hook(None)      # ad-hoc: no project registration
        dlg.set_point_hook(None)     # and no project to save points to
        dlg.set_reset_hooks(None, None)   # and nothing to reset (ADR-047)
        dlg.set_object(None)         # and no stale project object
        # Interfaz 1.0: the workbench is a page of the shell, full screen
        self._ufe_page()
        self.navigate(VIEW_UFE)

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
        # a different project (or visit) is a different SESSION: the
        # persistent dialog must not carry the previous one's plate,
        # sequence or series into it (issue report). Asked defensively: a
        # double in a test (or a future host) need not have the method.
        begin = getattr(dlg, "begin_session", None)
        if callable(begin):
            begin((hook_pid, session_id))
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
            # ADR-048: the visit context (its frames), the batch writer
            # for a series run and the per-run undo (D8/D9)
            dlg.set_series_hook(
                lambda scope="visit":
                self._ufe_series_context(hook_pid, session_id, scope))
            dlg.set_points_hook(
                lambda rows, cfg: self._ufe_points_hook(
                    hook_pid, session_id, rows, cfg))
            dlg.set_run_undo_hook(self._ufe_run_undo)
            dlg.set_exoclock_hook(
                lambda payload: self._ufe_exoclock_hook(hook_pid, payload))
            # ADR-045 rev: the period search's door from the editor's series
            # block, on the project's curve (it used to live in the visit
            # window; the editor is where the series was measured)
            phase_hook = getattr(dlg, "set_phase_hook", None)
            if callable(phase_hook):
                phase_hook(lambda pid_: self._open_phase_dialog(pid_))
            # astrometry plan, phase 7: the visit context for the
            # Calibration and Track & Stack tabs (their frames and the
            # project's object, D15) and the way a generated report
            # reaches the visit's MPC block. Asked defensively, like
            # every other hook: a host double need not have the method.
            astro_hook = getattr(dlg, "set_astrometry_hook", None)
            if callable(astro_hook):
                astro_hook(
                    lambda: self._ufe_astrometry_context(hook_pid,
                                                         session_id))
            # ADR-065: the run the visit already holds, so reopening it
            # SHOWS the result instead of an empty column. Goes with the
            # context hook (the tab asks for it as soon as it is armed).
            result_hook = getattr(dlg, "set_astrometry_result_hook", None)
            if callable(result_hook):
                result_hook(
                    lambda: self._ufe_astrometry_result(hook_pid, session_id))
            mpc_hook = getattr(dlg, "set_mpc_send_hook", None)
            if callable(mpc_hook):
                mpc_hook(self._ufe_mpc_send)
            # ADR-061 rev: the Calibration tab fills the master library from
            # where the recipe is read (it used to be only in Settings, so an
            # observer with real flats had no way to put them in)
            masters_hook = getattr(dlg, "set_add_masters_hook", None)
            if callable(masters_hook):
                masters_hook(self._ufe_add_masters)
            # the visit's frames, from the editor's preview list (2026-10-06):
            # the panel never touches the registry, it asks the host, and the
            # frames can be taken out of the visit or moved aside
            frames_hook = getattr(dlg, "set_visit_frames_hooks", None)
            if callable(frames_hook):
                frames_hook(
                    lambda paths: self._ufe_frames_remove(hook_pid,
                                                          session_id, paths),
                    lambda paths: self._ufe_frames_discard(hook_pid,
                                                           session_id, paths))
            # ADR-062, phase 8: the run is persisted by the HOST (the tab
            # never touches the database), with its undo per execution
            persist_hook = getattr(dlg, "set_astrometry_persist_hook", None)
            if callable(persist_hook):
                persist_hook(
                    lambda payload: self._ufe_astrometry_persist(
                        hook_pid, session_id, payload))
            undo_hook = getattr(dlg, "set_astrometry_undo_hook", None)
            if callable(undo_hook):
                undo_hook(self._ufe_astrometry_undo)
            # D: a brightness measured by hand in the Photometry tab can
            # take over the one the report uses, with the run's own value
            # kept beside it
            manual_hook = getattr(dlg, "set_manual_magnitude_hook", None)
            if callable(manual_hook):
                manual_hook(self._ufe_manual_magnitude)
            # the sequence is kept in the project: reopening the visit
            # must not mean rebuilding the comparison stars
            dlg.set_sequence_hook(
                lambda state: self._ufe_sequence_hook(hook_pid, state))
            # D: the visit's curve. Reading it asks nobody to measure again
            # (the points are already in the project); discarding it undoes
            # its series runs, keeping their rows marked. Asked defensively,
            # like every other hook: a host double need not have the method.
            #
            # The PASSES go first, on purpose: loading the curve tells the
            # panel how many other passes the visit holds, and that count
            # comes from this list (one night, one curve, 2026-09-30).
            passes_hooks = getattr(dlg, "set_visit_passes_hooks", None)
            if callable(passes_hooks):
                passes_hooks(
                    lambda: self._ufe_visit_passes(hook_pid, session_id),
                    lambda run_id: self._ufe_choose_curve(
                        hook_pid, session_id, run_id))
            # where the series figures are written: the project's own folder
            # (the Measure tab never touches the database)
            folder_hook = getattr(dlg, "set_export_folder_hook", None)
            if callable(folder_hook):
                folder_hook(
                    lambda: self._ufe_export_folder(hook_pid))
            curve_hooks = getattr(dlg, "set_visit_curve_hooks", None)
            if callable(curve_hooks):
                curve_hooks(
                    lambda scope="visit":
                    self._ufe_visit_curve(hook_pid, session_id, scope),
                    lambda: self._ufe_discard_curve(hook_pid, session_id))
            # G: the project, in the list's OWN language: the badge is fed
            # by the same builder the project rows use, so the two cannot
            # drift (a badge with its own words would be a second truth).
            badge = getattr(dlg, "set_project_badge", None)
            if callable(badge):
                badge(self._ufe_project_badge_payload(hook_pid))
            # ADR-048 follow-up: a transit project's reduce/export live in
            # the editor, next to the sequence they need
            proj = project.get(db, hook_pid) or {}
            if proj.get("kind") == "transit":
                dlg.set_exotic_hooks(
                    lambda: self._ufe_exotic_reduce(hook_pid, session_id),
                    lambda: self._ufe_exotic_export(hook_pid, session_id),
                    result_fn=lambda: self._open_exotic_result(
                        hook_pid, session_id),
                    folder_fn=lambda: self._exotic_open_folder(hook_pid),
                    result_text=self._exotic_result_text(hook_pid,
                                                         session_id))
            else:
                dlg.set_exotic_hooks(None, None)
        else:
            dlg.set_point_hook(None)
            dlg.set_reset_hooks(None, None)
            dlg.set_series_hook(None)
            dlg.set_points_hook(None)
            dlg.set_run_undo_hook(None)
            dlg.set_exoclock_hook(None)
            astro_hook = getattr(dlg, "set_astrometry_hook", None)
            if callable(astro_hook):
                astro_hook(None)
            result_hook = getattr(dlg, "set_astrometry_result_hook", None)
            if callable(result_hook):
                result_hook(None)
            persist_hook = getattr(dlg, "set_astrometry_persist_hook", None)
            if callable(persist_hook):
                persist_hook(None)
            undo_hook = getattr(dlg, "set_astrometry_undo_hook", None)
            if callable(undo_hook):
                undo_hook(None)
            manual_hook = getattr(dlg, "set_manual_magnitude_hook", None)
            if callable(manual_hook):
                manual_hook(None)
            mpc_hook = getattr(dlg, "set_mpc_send_hook", None)
            if callable(mpc_hook):
                mpc_hook(None)
            masters_hook = getattr(dlg, "set_add_masters_hook", None)
            if callable(masters_hook):
                masters_hook(None)
            frames_hook = getattr(dlg, "set_visit_frames_hooks", None)
            if callable(frames_hook):
                frames_hook(None, None)
            dlg.set_exotic_hooks(None, None)
            dlg.set_sequence_hook(None)
            passes_hooks = getattr(dlg, "set_visit_passes_hooks", None)
            if callable(passes_hooks):
                passes_hooks(None, None)
            folder_hook = getattr(dlg, "set_export_folder_hook", None)
            if callable(folder_hook):
                folder_hook(None)
            curve_hooks = getattr(dlg, "set_visit_curve_hooks", None)
            if callable(curve_hooks):
                curve_hooks(None, None)
            badge = getattr(dlg, "set_project_badge", None)
            if callable(badge):
                badge(None)              # ad-hoc: no project behind it
        self._ufe_page()
        # Defensive, like every other hook here: a host double in a test
        # need not have the new tabs.
        tabs = {"blink": getattr(dlg, "tab_blink", None),
                "compare": getattr(dlg, "tab_compare", None),
                "annotate": getattr(dlg, "tab_annotate", None),
                "measure": getattr(dlg, "tab_measure", None),
                "calibration": getattr(dlg, "tab_calibration", None),
                "trackstack": getattr(dlg, "tab_trackstack", None)}
        target = tabs.get(tab)
        if target is not None:
            dlg.show_tab(target)
        self.navigate(VIEW_UFE, pid=hook_pid)
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
            # Every kind a tab can send has to be mapped: an unmapped one
            # becomes None and the INSERT dies against NOT NULL, so the
            # file is written and then silently left out of the visit (the
            # astrometry stacks did exactly that). The map lives in
            # core/journal.py, next to the readable labels, so a test can
            # walk the kinds the tabs send and demand one for each.
            fkind = journal.FILE_KINDS.get(kind)
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
            ctx_update["mag_origin"] = "manual"
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

    # ---------------- E5c: the campaign pass ----------------

    def _camp_pass(self):
        # One read of the frames for every sibling project of the campaign
        # that shares the field. The dialog decides who travels (and
        # core.campaign says why the others do not), the engine measures
        # them in ONE pass — comps and zero point measured once per frame —
        # and each curve is filed in its own project, with its own run.
        from ..core import campaign as _camp
        from .pass_dialog import PassDialog
        cid = self._selected_campaign_id()
        if cid is None:
            return
        camp = _camp.get(db, cid)
        if camp is None:
            return
        if getattr(self, "_pass_worker", None) is not None:
            self.statusBar().showMessage(
                self.tr("A pass is already running."), 6000)
            return
        dlg = PassDialog(self, db_obj=db, camp=camp, lang=self._lang())
        if dlg.exec() != QDialog.Accepted:
            return
        source = dlg.source()
        seq, seq_source = dlg.sequence()
        targets = dlg.targets()
        if source is None or not targets or not seq:
            return
        self._pass_wcs = dlg.wcs()
        self._pass_camp = camp
        self._pass_start(source, targets, seq, seq_source, dlg.band(),
                         dlg.left_out())

    def _pass_start(self, source, targets, seq, seq_source, band, left):
        # Everything the dialog decided, put to work: the frames of the
        # source visit, the shared sequence, the objects and the band. The
        # measurement runs off the GUI thread; the frames are read once.
        cfg = self._pass_config(targets, seq, band)
        if cfg is None:
            return
        self._pass_source = source
        self._pass_targets = list(targets)
        self._pass_band = band
        self._pass_left = list(left or [])
        self._pass_worker = hold(PassWorker(source["paths"], cfg))
        self._pass_worker.progress.connect(self._pass_progress)
        self._pass_worker.finished.connect(self._pass_done)
        self._pass_worker.failed.connect(self._pass_failed)
        self._pass_wait = QProgressDialog(
            self.tr("Measuring the pass: {0} objects").format(len(targets)),
            self.tr("Cancel"), 0, len(source["paths"]), self)
        self._pass_wait.setWindowTitle(self.tr("Campaign pass"))
        self._pass_wait.setAutoClose(False)
        self._pass_wait.setAutoReset(False)
        self._pass_wait.canceled.connect(self._pass_cancel)
        self._pass_wait.show()
        # the sequence's origin is said out loud: an observer measuring
        # with someone else's comparison stars must be able to see it
        self.statusBar().showMessage(self.tr(
            "Pass over {0} frames with the {1}").format(
                len(source["paths"]),
                self.tr("campaign's shared sequence")
                if seq_source == "campaign"
                else self.tr("project's own sequence")), 8000)
        self._pass_worker.start()

    def _pass_config(self, targets, seq, band):
        # The engine's configuration for a pass, from the dialog and
        # Ajustes. It needs the reference pointing: without it the dialog
        # does not accept, and this is the last honest check.
        from ..core import photometry, series_measure
        from ..config import config
        if getattr(self, "_pass_wcs", None) is None:
            return None
        wanted = tuple((t["label"], float(t["xy"][0]), float(t["xy"][1]))
                       for t in targets)
        entries = tuple(seq.get("entries") or ())
        # catalog mode needs the sequence to carry the catalogue's own
        # values; without them the honest measurement is the differential
        # one (D40), and the choice is not left to chance
        zp_mode = "catalog" if any(
            photometry.band_of((e.get("star") or {}), band)[0] is not None
            for e in entries) else "relative"
        return series_measure.SeriesConfig(
            wcs=self._pass_wcs, targets=wanted,
            target_xy=(wanted[0][1], wanted[0][2]),
            comp_set=entries, band=band, fallback_band="V",
            zp_mode=zp_mode, align="coords", seeing_aperture=True,
            site_gain=config.get("ccd_gain"),
            site_ron=config.get("ccd_read_noise"),
            site_flat=config.get("flat_resid_mag", 0.007) or 0.007,
            site_saturate=config.get("ccd_saturate"),
            site_lon=config.get("lon"), site_lat=config.get("lat"),
            site_aperture_m=float(config.get("aperture_inches", 10.0))
            * 0.0254,
            site_height_m=float(config.get("height", 0) or 0.0),
            site_linear=config.get("cam_linearity_adu"),
            site_dark=config.get("cam_dark_current_e_s"))

    def _pass_progress(self, done, total):
        if getattr(self, "_pass_wait", None) is not None:
            self._pass_wait.setMaximum(max(1, total))
            self._pass_wait.setValue(done)

    def _pass_cancel(self):
        worker = getattr(self, "_pass_worker", None)
        if worker is not None:
            worker.cancel()
            self.statusBar().showMessage(
                self.tr("Cancelling the pass… the frames already measured "
                        "are kept."), 6000)

    def _pass_failed(self, message):
        self._pass_close_wait()
        self._pass_worker = None
        QMessageBox.warning(
            self, self.tr("Campaign pass"),
            self.tr("The pass failed: {0}").format(message))

    def _pass_close_wait(self):
        wait = getattr(self, "_pass_wait", None)
        if wait is not None:
            wait.blockSignals(True)
            wait.close()
            self._pass_wait = None

    def _pass_done(self, result):
        # The frames are filed in every measured project, and each curve
        # goes to its own project with its own run. The pass is recorded
        # in each run's echo, so the journal can say what it was.
        from ..core import followup as fu
        from ..core import project as project_mod, series_measure
        self._pass_close_wait()
        self._pass_worker = None
        if result is None:
            return
        source = self._pass_source
        targets = list(self._pass_targets)
        wanted = [t for t in targets]
        sessions = fu.share_frames(
            db, source["paths"],
            [{"project_id": t["pid"]} for t in wanted],
            obs_date=source.get("obs_date"),
            notes=self.tr("Campaign pass: shared frames"))
        entries = []
        measured = 0
        for t, got in zip(wanted, result.targets):
            rows = series_measure.series_rows(got["result"].points)
            if rows:
                measured += 1
            by_path = {f["path"]: f["id"]
                       for f in project_mod.list_files(db, t["pid"])
                       if f.get("kind") == "fits"}
            for r in rows:
                r["file_id"] = by_path.get(r.get("path"))
            entries.append({"project_id": t["pid"],
                            "session_id": sessions.get(t["pid"]),
                            "rows": rows, "label": t["label"],
                            "status": result.status})
        fu.save_pass(db, entries, cfg={
            "campaign": (self._pass_camp or {}).get("name"),
            "band": self._pass_band})
        self.statusBar().showMessage(self.tr(
            "Pass saved: {0} objects, {1} frames, {2} points").format(
                measured, len(source["paths"]),
                sum(len(e["rows"]) for e in entries)), 10000)
        left = getattr(self, "_pass_left", None) or []
        if left:
            self.statusBar().showMessage(
                self.tr("Pass saved. {0} project(s) stayed out of it: see "
                        "the dialog.").format(len(left)), 10000)
        self._campaign_selected()

    # ---------------- UFE plate resets (ADR-047) ----------------

    def _ufe_frames_remove(self, pid, session_id, paths):
        # @args: pid - project id, session_id - the visit, paths - the frames
        #        to take out of it
        # @return: what happened, in words
        # The editor's preview list asks for this: the frames stop being part
        # of the visit (the registry row goes) and NOTHING on disk is touched
        # (project.delete_file unlinks, it never deletes). The frames can be
        # attached again from the visit's window.
        taken = 0
        wanted = {str(p) for p in (paths or [])}
        for f in project.files_for_session(db, session_id):
            if str(f.get("path")) not in wanted:
                continue
            if project.delete_file(db, f["id"]):
                taken += 1
        if taken:
            # the tab's own context (frames, plan, result) is re-read: what
            # is on screen is what the visit holds now
            self._refresh_visit_after_frames(pid, session_id)
        return (self.tr("%1 frames are no longer part of the visit "
                        "(the files stay where they are).").replace(
                            "%1", str(taken)) if taken
                else self.tr("Nothing was taken out: those frames are not "
                             "part of this visit any more."))

    def _ufe_frames_discard(self, pid, session_id, paths):
        # @args: pid - project id, session_id - the visit, paths - the frames
        #        to move aside
        # @return: what happened, in words
        # A REAL move, into `descartados/` inside the project (free_space
        # does the work and the registry follows it). Nothing is deleted and
        # the frames can be brought back from that folder.
        from ..core import free_space
        p = project.get(db, pid) or {}
        storage = project.storage_dir(p) if p else None
        if not storage:
            return self.tr("This project has no folder to move them into.")
        report = free_space.discard_files(db, paths, storage)
        if report.moved:
            self._refresh_visit_after_frames(pid, session_id)
        bits = [self.tr("%1 frames moved to discarded/.").replace(
            "%1", str(report.moved))]
        if report.skipped:
            bits.append(self.tr("%1 were not there any more.").replace(
                "%1", str(len(report.skipped))))
        for err in report.errors[:2]:
            bits.append(f"✕ {err}")
        return " ".join(bits)

    def _refresh_visit_after_frames(self, pid, session_id):
        # @args: pid - project id, session_id - the visit
        # @return: None. The editor's own context (its frame list, the
        #          astrometry tab's sequence, the visit's window) is told
        #          that the visit changed: the frames are the visit's, and
        #          half of the app reads them.
        dlg = getattr(self, "_ufe", None)
        if dlg is not None:
            hook = getattr(dlg, "refresh_visit_context", None)
            if callable(hook):
                try:
                    hook()
                except Exception as err:      # a refresh never breaks a move
                    logger.warning("visit context refresh failed: %s", err)
        self._visit_sync(pid, session_id)

    def _visit_sync(self, pid, session_id):
        # @args: pid - project id, session_id - the visit
        # @return: None. The visit's window, when it is open, is told too
        #          (the panel's own refresh repopulates its resources).
        win = self._visit_window()
        refresh = getattr(win, "refresh", None)
        if callable(refresh):
            try:
                refresh()
            except Exception as err:
                logger.warning("the visit's window could not refresh: %s", err)

    def _ufe_series_context(self, pid, session_id, scope="visit"):
        # ADR-048 (D8): the series works from a visit's frames, never a
        # folder dialog. No visit (or no FITS in it): no series block.
        #
        # MULTI-NIGHT (2026-09-30, the observer's ask): a series that runs
        # over several nights is measured in ONE pass, so the scope
        # "project" hands the frames of EVERY visit of the project (ordered
        # by time). Each frame's point is then filed in its own visit: a
        # visit is one night, and the project's curve is the union of the
        # nights (one pass each), which is what the period search needs.
        # @args: pid - project id, session_id - the visit or None, scope -
        #        "visit" | "project"
        # @return: {"pid", "session_id", "paths", "kind", "context",
        #           "scope", "nights"} or None
        if session_id is None:
            return None
        p = project.get(db, pid) or {}
        if scope == "project":
            files = [f for f in project.list_files(db, pid)
                     if f.get("kind") == "fits" and f.get("path")
                     and f.get("session_id") is not None]
            # the frames in time order: the engine sorts them by their own
            # mjd too, but the reference frame is the one on stage
            paths = sorted({f["path"] for f in files})
            nights = {f["session_id"] for f in files}
            if not paths:
                return None
            return {"pid": pid, "session_id": session_id, "paths": paths,
                    "kind": p.get("kind"), "context": p.get("context") or {},
                    "scope": "project", "nights": len(nights),
                    "path_sessions": {f["path"]: f["session_id"]
                                      for f in files}}
        files = project.files_for_session(db, session_id)
        paths = sorted(f["path"] for f in files
                       if f.get("kind") == "fits" and f.get("path"))
        if not paths:
            return None
        # how many visits of this project hold frames: the tab offers the
        # multi-night scope only when there is more than one (one visit is
        # the same thing under another name)
        visits = {f.get("session_id") for f in project.list_files(db, pid)
                  if f.get("kind") == "fits" and f.get("path")
                  and f.get("session_id") is not None}
        return {"pid": pid, "session_id": session_id, "paths": paths,
                "kind": p.get("kind"), "context": p.get("context") or {},
                "scope": "visit", "nights": 1,
                "visits": len(visits),
                "path_sessions": {path: session_id for path in paths}}

    def _ufe_astrometry_context(self, pid, session_id):
        # Astrometry plan, phase 7 (D15): the Calibration and Track &
        # Stack tabs work from the visit's frames and the project's
        # object, never a folder dialog. No visit (or no FITS in it): the
        # tabs stay disarmed and say why.
        # @args: pid - project id, session_id - the visit or None
        # @return: {"pid", "session_id", "paths", "object_name"} or None
        if session_id is None:
            return None
        files = project.files_for_session(db, session_id)
        paths = sorted(f["path"] for f in files
                       if f.get("kind") == "fits" and f.get("path"))
        if not paths:
            return None
        p = project.get(db, pid) or {}
        ctx = p.get("context") or {}
        # The NEO's photometry reuses the SERIES engine, which calibrates
        # frame by frame against comparison stars. The project's saved
        # sequence is the observer's own choice of them (the Compare tab);
        # when there is none the worker proposes one from the catalog.
        seq = ctx.get("sequence") or {}
        comps = [e for e in (seq.get("entries") or [])
                 if (e.get("kind") or "comp") == "comp"]
        return {"pid": pid, "session_id": session_id, "paths": paths,
                "object_name": p.get("object_name") or "",
                "packed": ctx.get("packed") or ctx.get("id"),
                "comps": comps,
                "target_mag": seq.get("target_mag") or ctx.get("mag")}

    def _astrometry_summary(self, payload):
        # @args: payload - the worker's result dict
        # @return: a JSON-safe summary of the run, stored in the run's own
        #          cfg_json so the visit can RESTORE it (ADR-065): the
        #          detection, the sweep, the brightness, the registration and
        #          the check. The heavy pieces already have a home (the
        #          stacks are files, the points are rows); this is what
        #          neither of them carries, and it needs no schema change.
        import json
        def _scalar(v):
            # numpy scalars are not JSON's: .item() unwraps them (a
            # np.bool_ serialised by default=str would come back as the
            # STRING "True", which is truthy for the wrong reason)
            if v is None or isinstance(v, (bool, int, float, str)):
                return v
            item = getattr(v, "item", None)
            if callable(item):
                try:
                    return _scalar(item())
                except Exception:
                    return str(v)
            if isinstance(v, (list, tuple)):
                return [_scalar(x) for x in v]
            if isinstance(v, dict):
                return {str(k): _scalar(x) for k, x in v.items()}
            return str(v)
        def _obj(o, keys):
            if o is None:
                return None
            return {k: _scalar(getattr(o, k, None)) for k in keys}
        summary = {
            "method": payload.get("method"),
            "ephem_source": payload.get("ephem_source"),
            "n_failed": payload.get("n_failed"),
            "n_off_frame": payload.get("n_off_frame"),
            "phot_skipped": bool(payload.get("phot_skipped")),
            # What the manual mode needs to place a mark on a run that was
            # REOPENED: the base stack's cutout origin in the reference grid
            # (the mark is in the stack's pixels and the pipeline wants the
            # grid). The stack itself is a file in the project.
            "box_all": _scalar(payload.get("box_all")),
            "base_rate": _scalar(payload.get("base_rate")),
            "base_pa": _scalar(payload.get("base_pa")),
            # The ephemeris' own answer about the light: the band shows it,
            # labelled, when the run did not measure the brightness.
            "ephem_mag": _scalar(payload.get("ephem_mag")),
            "ephem_band": _scalar(payload.get("ephem_band")),
            "ephem_mag_source": _scalar(payload.get("ephem_mag_source")),
            "detection": _obj(payload.get("detection"),
                              ("detected", "snr", "x", "y", "fwhm",
                               "roundness", "mag_limit", "notes")),
            "dither": _obj(payload.get("dither"),
                           ("dithered", "spread_px", "note")),
            "wcs_qc": _obj(payload.get("wcs_qc"),
                           ("checked", "max_offset_arcsec", "ok", "note")),
            "sweep": _obj(payload.get("sweep"), ("best", "grid", "method")),
            "check": _obj(payload.get("check"),
                          ("available", "blocked", "outlier", "no_reference",
                           "our_residual", "scatter", "z", "n_others",
                           "n_stations", "note")),
            "photometry": _scalar(payload.get("photometry")),
            "register_report": _scalar(payload.get("register_report")),
            "calibration": _scalar(payload.get("calibration")),
            # The run's own record of what it could NOT use: the frames it
            # could not read and the ones it could not register (by path).
            # They live here because neither the points nor the stacks say
            # them, and reopening the visit must mark the bad frames again
            # instead of forgetting them (2026-10-07).
            "n_unreadable": _scalar(payload.get("n_unreadable")),
            "failed_frames": _scalar(payload.get("failed_frames")),
            # The PLAN of the run: which frames went into each observation.
            # Without it a reopened run can only guess the "N frames" of each
            # observation from its points, and the stack point carries 0 on
            # purpose (core/astrometry.py): the combo read "1 frames".
            "groups": _scalar(payload.get("groups")),
        }
        try:
            return json.loads(json.dumps(summary, ensure_ascii=False))
        except (TypeError, ValueError) as err:  # never lose a run over this
            logger.warning("the astrometry summary is not serialisable: %s",
                           err)
            return {}

    def _ufe_astrometry_persist(self, pid, session_id, payload):
        # ADR-062, phase 8: one execution, its observations and the frame
        # manifest land in the database (the tab never touches it). The run
        # id comes back so the tab can offer "undo this run".
        # @args: pid - project id, session_id - the visit, payload - the
        #        worker's result dict
        # @return: the run id, or None (no visit, or nothing measured)
        from ..core import astrometry_store as store
        payload = payload or {}
        # the worker's verdict is ok|not_detected|error|cancelled; the store
        # speaks complete|not_detected|incomplete|undone
        status = {"ok": "complete"}.get(payload.get("status"),
                                        payload.get("status"))
        if session_id is None or status not in ("complete", "not_detected"):
            return None
        points = payload.get("points") or []
        if status == "complete" and not points:
            return None
        p = project.get(db, pid) or {}
        det = payload.get("detection")
        sweep = payload.get("sweep")
        dither = payload.get("dither")
        frames = payload.get("frames") or []
        gate = float(config.get("astrometry_snr_sigma", 3.5))
        floor = float(config.get("astrometry_submit_snr", 10.0))
        best = (sweep.best if sweep is not None else None) or {}
        run_id = store.create_run(
            db, pid, session_id,
            cfg={"n_obs": payload.get("n_obs"),
                 "method": payload.get("method"),
                 "n_failed": payload.get("n_failed"),
                 "snr_gate": gate, "submit_snr": floor,
                 # the run's own words, JSON-safe: this is what the visit
                 # paints again when it is reopened (ADR-065)
                 "result": self._astrometry_summary(payload)},
            status=status, object_name=p.get("object_name") or "",
            method=payload.get("method") or "", n_frames=len(frames),
            n_obs=len(points), rate_arcsec_min=best.get("rate"),
            pa_deg=best.get("pa"),
            sweep=(sweep.grid if sweep is not None else None),
            dither=(dither.dithered if dither is not None else None),
            snr_gate=gate, submit_snr=floor,
            detected=(det.detected if det is not None else None))
        # The project learns the object's magnitude from the measurement:
        # the next comparison proposal anchors on a datum instead of a
        # guess, and the Photometry tab's field stops being empty. The
        # magnitude is the run's own summary, so nothing is invented.
        phot = payload.get("photometry") or {}
        if phot.get("mag"):
            project.update_context(db, pid, {
                "mag": float(phot["mag"]),
                # and it SAYS so: from here on, the project's figure is a
                # measurement and the interface can tell the observer which
                # of the two it is anchoring on
                "mag_origin": "measured"})
        # The comparison stars the run used are SAVED when the project had
        # none: opening the Photometry tab then finds the same sequence
        # instead of proposing a different one, and the next run starts from
        # the observer's own field. A project that already had a sequence
        # keeps it: the run used it, so there is nothing to write.
        comps = phot.get("comps") if isinstance(phot, dict) else None
        ctx = p.get("context") or {}
        if comps and not ((ctx.get("sequence") or {}).get("entries")):
            project.update_context(db, pid, {"sequence": {
                "catalog": phot.get("catalog") or "gaia",
                "catalog_name": "Gaia (proposed by the run)",
                "target_mag": phot.get("mag"),
                "entries": comps}})
        rows = []
        for sp, fp, _flags in points:
            for source, pt in (("stack", sp), ("frames", fp)):
                if pt is None:
                    continue
                rows.append({
                    "run_id": run_id, "project_id": pid,
                    "session_id": session_id, "group_index": pt.group_index,
                    "mjd": pt.mjd, "ra": pt.ra, "dec": pt.dec,
                    "rms_ra": pt.rms_ra, "rms_dec": pt.rms_dec,
                    "mag": pt.mag, "band": pt.band, "x": pt.x, "y": pt.y,
                    "n_frames": pt.n_frames, "snr": pt.snr, "source": source,
                    "method": payload.get("method"),
                    "flags": list(pt.flags or [])})
        store.add_points(db, rows)
        frame_rows = []
        for f in frames:
            try:
                size = Path(f.path).stat().st_size
            except OSError:
                size = None
            frame_rows.append({"path": f.path, "size": size,
                               "filter": f.filter, "exptime_s": f.exptime_s,
                               "date_obs": f.date_obs})
        store.add_frames(db, run_id, frame_rows)
        logger.info("astrometry run %s persisted (%d points, %d frames)",
                    run_id, len(rows), len(frame_rows))
        # the Analysis tab's list of runs is live if that project is open:
        # the run just measured shows up without reopening the project
        if self._project_widgets.get("astrometry_runs_tbl") is not None:
            self._analysis_astrometry_refresh(pid)
        return run_id

    def _ufe_astrometry_result(self, pid, session_id):
        # ADR-065: what the visit already holds, so reopening it SHOWS the
        # run instead of an empty column. The last complete (or
        # not-detected) execution of THIS visit, its points and the stack
        # files the visit registered. Nothing is recomputed here: the tab
        # paints it.
        # @args: pid - project id, session_id - the visit
        # @return: {"run", "points", "stacks"} or None
        from ..core import astrometry_store as store
        if pid is None or session_id is None:
            return None
        try:
            runs = [r for r in store.list_runs(db, pid)
                    if r.get("session_id") == session_id
                    and r.get("status") in ("complete", "not_detected")]
        except Exception as err:
            logger.warning("the astrometry runs could not be listed: %s", err)
            return None
        if not runs:
            return None
        # The run the editor was TOLD to show wins (the one picked in the
        # Analysis tab's list); with none, the newest, which is what the
        # visit's own "Astrometry" button means ("the last pass of the
        # night").
        pref = getattr(self, "_astrometry_run_pref", None)
        run = None
        if pref and pref[0] == pid and pref[1] == session_id:
            run = next((r for r in runs if r["id"] == pref[2]), None)
        if run is None:
            run = runs[-1]                # oldest first: the newest one wins
        try:
            points = store.points_for_run(db, run["id"])
            files = project.files_for_session(db, session_id)
        except Exception as err:
            logger.warning("the astrometry result could not be read: %s", err)
            return None
        # The stacks: deduplicated (a visit used to register the same file
        # once per look) and, when the files say so, only THIS run's. A visit
        # accumulates the stacks of every pass, and matching them by the
        # observation number alone showed ANOTHER pass's image (reported
        # 2026-10-07: a 2-observation run came out with the first stack of a
        # different run). An old run carries no NS_RUN card, and then the
        # whole set is offered, as it always was.
        from ..core import fits_io
        stacks, seen = [], set()
        for f in files:
            path = f.get("path")
            if f.get("kind") != "stack" or not path:
                continue
            path = str(path)
            if path in seen or not Path(path).exists():
                continue
            seen.add(path)
            stacks.append(path)
        mine = []
        for path in stacks:
            try:
                header = fits_io.read_header(path)
            except Exception:
                continue
            if header.get("NS_RUN") == run["id"]:
                mine.append(path)
        if mine:
            stacks = mine
        return {"run": run, "points": points, "stacks": stacks}

    def _ufe_manual_magnitude(self, run_id, group_index, mag, band=None):
        # @args: run_id - the execution, group_index - the observation,
        #        mag - the magnitude measured by hand in the Photometry tab,
        #        band - its band
        # @return: True when the observation took it. The EFFECTIVE
        #          magnitude moves and the run's own value stays in mag_auto:
        #          the report uses the first, the audit keeps both, and
        #          nothing is sent without its trace (D).
        from ..core import astrometry_store as store
        try:
            done = bool(store.set_manual_magnitude(db, int(run_id),
                                                   int(group_index),
                                                   float(mag), band))
        except Exception as err:
            logger.warning("the manual magnitude could not be stored: %s",
                           err)
            return False
        if done:
            # the list says WHO wrote the magnitude: a measurement made by
            # hand has to show up there at once
            run = self._analysis_astrometry_run(int(run_id))
            if run is not None and self._project_widgets.get(
                    "astrometry_runs_tbl") is not None:
                self._analysis_astrometry_refresh(run["project_id"])
        return done

    def _ufe_astrometry_undo(self, run_id):
        # ADR-062, phase 8 (D14): undo THIS execution, its points and its
        # frame manifest. The run row stays, marked "undone", for the audit
        # trail (the same shape the series' undo has).
        # @args: run_id - the execution
        # @return: how many points were removed, or None
        from ..core import astrometry_store as store
        if run_id is None:
            return None
        removed = store.delete_run(db, run_id)
        return removed.get("points") if isinstance(removed, dict) else removed

    def _ufe_mpc_send(self, text):
        # The Track & Stack tab's report lands in the visit's MPC paste
        # box (ADR-045 form A: the block lives in the visit window), and
        # the block's own ADR-022 validator speaks right away.
        # @args: text - the generated report
        # @return: True when the block received it
        win = self._visit_window()
        txt = getattr(win, "txt_mpc", None)
        if txt is None:
            return False
        txt.setPlainText(text)
        validate = getattr(win, "_on_mpc_validate", None)
        if callable(validate):
            validate()
        return True

    def _ufe_points_hook(self, pid, session_id, rows, cfg):
        # ADR-048 (D9): one series run = one measurement_runs row; its
        # points go in a single batch with the run id, so "Undo this run"
        # removes exactly them. A point keeps its plate link when the
        # frame is registered (ADR-047). D18: the run keeps its REAL
        # status, so a series the user cancelled is stored "incomplete"
        # and stays visible as such; the Measure tab sends the status in
        # the run echo and it lands in its own column, not in cfg_json.
        # @args: rows - point dicts, cfg - JSON-safe run echo (it may
        #        carry the run's "status")
        # @return: the new run id
        from ..core import followup as fu
        echo = dict(cfg or {})
        status = echo.pop("status", None) or "complete"
        # the frames of the project, by (path, visit) and by path: the
        # first is exact when the same frame is registered in two visits
        files = [f for f in project.list_files(db, pid)
                 if f.get("kind") == "fits"]
        by_path = {(f["path"], f.get("session_id")): f for f in files}
        by_path.update({f["path"]: f for f in files})
        # a live batch continues the run its session opened (one live
        # session, one run): the points pile into it, so the curve reloaded
        # from the project is the whole session and "undo" is one click
        append = echo.pop("append_run", None)
        run_id = fu.reusable_run(db, append, session_id)
        if run_id is not None:
            for r in rows:
                sid = r.get("session_id") or session_id
                f = by_path.get((r.get("path"), sid)) \
                    or by_path.get(r.get("path")) or {}
                r["project_id"] = pid
                r["session_id"] = sid
                r["run_id"] = run_id
                r["file_id"] = f.get("id")
            if rows:
                fu.add_points(db, rows)
            self.statusBar().showMessage(
                self.tr("Series saved: {} points").format(len(rows)), 8000)
            self._project_selected()
            return run_id
        # ONE PASS, ONE RUN PER VISIT. A multi-night pass measures the
        # frames of several visits in one go, and each frame's points are
        # filed in ITS OWN visit: a visit is one night, so the visit's
        # curve and the project's (the union of the nights) both read
        # right, and the whole pass shares a group id so "undo" takes it
        # all. A single-visit run resolves to one group and is exactly
        # what it always was.
        groups = {}
        for r in rows:
            # the visit the FRAME belongs to: the row says it (the tab took
            # it from the context), and a frame registered in two visits
            # would otherwise land in whichever row came last (measured on
            # the observer's database: the same 244 frames in three visits)
            sid = r.get("session_id") or session_id
            f = by_path.get((r.get("path"), sid)) \
                or by_path.get(r.get("path")) or {}
            r["project_id"] = pid
            r["session_id"] = sid
            r["file_id"] = f.get("id")
            groups.setdefault(sid, []).append(r)
        group = uuid.uuid4().hex if len(groups) > 1 else None
        run_id = None
        for sid, own in groups.items():
            run_echo = dict(echo)
            if group:
                run_echo["pass"] = {"group": group, "nights": len(groups)}
            run_id = fu.create_run(db, session_id=sid,
                                   cfg={"series": run_echo}, status=status)
            for r in own:
                r["run_id"] = run_id
            fu.add_points(db, own)
        if group:
            self.statusBar().showMessage(
                self.tr("Series saved: {} points over {} nights, one run "
                        "each").format(len(rows), len(groups)), 8000)
        else:
            self.statusBar().showMessage(
                self.tr("Series saved: {} points").format(len(rows)), 8000)
        self._project_selected()
        return run_id

    def _ufe_exoclock_hook(self, pid, payload):
        # ADR-049 (D30): the ExoClock files were written and the browser
        # opened; the project outcome is recorded as reported_exoclock.
        # @args: pid - project id, payload - {"planet", "points"}
        try:
            project.close(db, pid, "reported_exoclock")
        except Exception as err:
            logger.warning("exoclock outcome failed: %s", err)
            return False
        self.statusBar().showMessage(
            self.tr("ExoClock submission prepared; outcome recorded."), 8000)
        self._project_selected()
        return True

    def _ufe_run_undo(self, run_id):
        # ADR-048 (D6): undo one run's points, keep the run row for the
        # audit trail, and refresh the project view.
        #
        # A run that belongs to a MULTI-NIGHT pass (2026-09-30) takes its
        # whole pass with it: the observer measured one series in one go,
        # so "undo" has to undo the series and not one of its nights.
        # @args: run_id - the run to undo
        # @return: the number of points deleted
        from ..core import followup as fu
        group = fu.run_pass_group(db, run_id)
        if group:
            runs = fu.runs_in_pass(db, group)
            count = 0
            for run in runs:
                count += fu.delete_points_for_run(db, run["id"])
                fu.set_run_status(db, run["id"], "undone")
            self.statusBar().showMessage(
                self.tr("Pass undone: {} points over {} nights").format(
                    count, len(runs)), 8000)
            self._project_selected()
            return count
        count = fu.delete_points_for_run(db, run_id)
        fu.set_run_status(db, run_id, "undone")
        self.statusBar().showMessage(
            self.tr("Run undone: {} points removed").format(count), 8000)
        self._project_selected()
        return count

    def _curve_payload(self, points):
        # The stored rows shaped for the chart: the band each point's run
        # was calibrated in, the plate it was measured on (so the image's
        # band matches it by PATH) and, when that run asked for it, the
        # detrended curve (refitted here: the same points with the same
        # airmass give the same coefficients).
        #
        # The detrend is applied RUN BY RUN on purpose: one run is one
        # night, and a multi-night curve has one policy per night. Fitting
        # the whole curve with one policy would smear a night into another.
        # @args: points - followup rows (a visit's curve, or the project's)
        # @return: [point dicts] raw + detrended, as the chart reads them
        from ..core import followup as fu, project as project_mod
        from ..core import series_measure
        runs, paths = {}, {}
        for p in points:
            rid = p.get("run_id")
            if rid is not None and rid not in runs:
                runs[rid] = fu.get_run(db, rid) or {}
            fid = p.get("file_id")
            if fid is not None and fid not in paths:
                paths[fid] = (project_mod.get_file(db, fid) or {}).get("path")
        raw, by_run = [], {}
        for p in points:
            if p.get("mjd") is None or p.get("mag") is None:
                continue
            cfg = (runs.get(p.get("run_id")) or {}).get("cfg") or {}
            band = (cfg.get("series") or {}).get("band")
            shaped = {"mjd": p["mjd"], "mag": p["mag"], "err": p.get("err"),
                      "err_internal": p.get("err_internal"),
                      "mag_raw": p.get("mag_raw"),
                      "filter": p.get("filter") or band,
                      "flags": list(p.get("flags") or []),
                      "path": paths.get(p.get("file_id")),
                      # the NIGHT travels with the point (v14): the night
                      # figures are drawn from these, so a curve read back
                      # from the visit explains its night without measuring
                      "airmass": p.get("airmass"), "x": p.get("x"),
                      "y": p.get("y"), "fwhm": p.get("fwhm"),
                      "sky": p.get("sky"),
                      "source": "measure"}
            raw.append(shaped)
            by_run.setdefault(p.get("run_id"), []).append(shaped)
        out = list(raw)
        for rid, own in by_run.items():
            cfg = (runs.get(rid) or {}).get("cfg") or {}
            policy = (cfg.get("series") or {}).get("detrend_policy")
            if policy and policy != "off":
                out += series_measure.detrend_stored(own, policy)
        return out

    def _ufe_visit_curve(self, pid, session_id, scope="visit"):
        # The curve a visit already holds (D): the series points saved in
        # the project for THAT visit, shaped for the chart. No frame is
        # read and nothing is asked of the observer.
        #
        # ONE NIGHT, ONE RUN (2026-09-30): the visit may hold several
        # passes, and the chart draws the one the visit shows (its choice,
        # else the last one measured). Drawing all of them at once is the
        # reported corruption: 976 points at two levels joined by a zigzag.
        #
        # MULTI-NIGHT (the same day): with the scope "project" the chart
        # draws the PROJECT's curve, which is the union of its nights, one
        # pass per night: that is what a series measured across several
        # nights has to show, and what the period search reads.
        # @args: pid - project id, session_id - the visit or None, scope -
        #        "visit" | "project"
        # @return: {"points": [point dicts], "zp_mode": "catalog" |
        #          "relative"}, or {} when there is no curve
        from ..core import followup as fu
        if session_id is None:
            return {}
        if scope == "project":
            points = fu.list_points(db, pid)
            # a project curve is on the differential axis only when EVERY
            # night it holds was measured that way (mixing the two is not
            # a curve, it is two)
            modes = set()
            for p in points:
                run = fu.get_run(db, p.get("run_id")) or {}
                cfg = (run.get("cfg") or {}).get("series") or {}
                modes.add(cfg.get("zp_mode") or "catalog")
            mode = "relative" if modes == {"relative"} else "catalog"
            return {"points": self._curve_payload(points), "zp_mode": mode}
        run = fu.get_run(db, fu.curve_run_for_session(db, session_id)) or {}
        series_cfg = (run.get("cfg") or {}).get("series") or {}
        points = fu.points_for_session(db, session_id)
        return {"points": self._curve_payload(points),
                "zp_mode": ("relative" if series_cfg.get("zp_mode")
                            == "relative" else "catalog")}

    def _ufe_export_folder(self, pid):
        # Where this project's own files live: the folder the observer sees
        # in the project's Details (ADR-045), so a figure written from the
        # editor lands next to the rest of the project.
        # @args: pid - project id
        # @return: the folder (str), or None
        from .. import paths as paths_mod
        row = project.get(db, pid)
        if not row:
            return None
        return str(paths_mod.project_dir(
            pid, row.get("object_name") or "", row.get("root_dir") or ""))

    def _ufe_visit_passes(self, pid, session_id):
        # The passes of a visit (2026-09-30): one row per series run, oldest
        # first, with the one the chart shows. This is what the "Passes of
        # this visit" door reads, and the count the panel's line uses.
        #
        # A visit can hold several passes (measuring again with another band
        # is normal) and every one keeps its points; only one is DRAWN, and
        # drawing them all at once was the reported corruption.
        #
        # The passes ALREADY UNDONE are counted, not listed: on a real visit
        # there were 26 of them against 4 that mattered, and a wall of empty
        # rows hides the ones you can choose. They are not deleted (the trail
        # keeps them) and the window says so.
        # @args: pid - project id, session_id - the visit or None
        # @return: {"runs": [...], "curve_run_id": int|None, "undone_empty": n}
        from ..core import followup as fu
        if session_id is None:
            return {}
        runs = fu.runs_for_session(db, session_id)
        listed = [r for r in runs
                  if (r.get("status") or "") != "undone" or r.get("points")]
        return {"runs": listed,
                "curve_run_id": fu.curve_run_for_session(db, session_id),
                "undone_empty": len(runs) - len(listed)}

    def _ufe_choose_curve(self, pid, session_id, run_id):
        # "Make this the curve": the visit remembers which pass it shows.
        # Nothing is deleted and nothing is measured again: the points of
        # the other passes stay in the project, and the chart follows.
        # @args: run_id - the pass to draw
        # @return: True when the visit was found
        from ..core import followup as fu
        if session_id is None:
            return False
        ok = fu.set_session_curve_run(db, session_id, run_id)
        if ok:
            self.statusBar().showMessage(
                self.tr("The chart will show that pass of the visit."), 6000)
        return ok

    def _ufe_discard_curve(self, pid, session_id):
        # "Start the curve from scratch": every series run of the visit is
        # undone (its points go, its run row stays marked undone: the trail
        # is never silent) and the project view refreshes.
        # @return: (runs undone, points removed)
        from ..core import followup as fu
        if session_id is None:
            return 0, 0
        runs, points = fu.discard_session_curve(db, session_id)
        self.statusBar().showMessage(
            self.tr("Curve discarded: {0} run(s) undone, {1} points removed"
                    ).format(runs, points), 8000)
        self._project_selected()
        return runs, points

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
        # The window owns the worker: it stays referenced until its thread has
        # really finished (hold), so it is never destroyed while running (Qt 6
        # aborts for that). No deleteLater here: it would be triggered by the
        # worker's OWN finished signal, which is emitted BEFORE the thread
        # stops, and deleting a running QThread is the very abort we avoid.
        # The drop goes through a bound slot (queued to the GUI thread) and
        # sender() names the worker.
        self._workers.append(worker)
        hold(worker)
        worker.finished.connect(self._drop_sender)

    def _drop_sender(self, *args):
        # @args: args - the signal's payload (ignored: sender() names the
        #        worker). A bound slot runs on the GUI thread: a lambda here
        #        would run on the worker's thread and could even fire a QTimer
        #        with no event loop behind it.
        # @return: None. Drops the worker that just emitted finished.
        w = self.sender()
        if w is not None:
            self._drop(w)

    def _drop(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)

    def _install_mouse_nav(self):
        # Interfaz 1.1: the mouse side buttons (back/forward) navigate too.
        # An app-wide event filter is the only way to see them whatever
        # widget is under the cursor.
        from PySide6.QtCore import QObject, QEvent, Qt as _Qt
        from PySide6.QtWidgets import QApplication
        win = self

        class _NavMouseFilter(QObject):
            def eventFilter(self, obj, ev):
                if ev.type() == QEvent.Type.MouseButtonPress:
                    if ev.button() == _Qt.BackButton:
                        win.back()
                        return True
                    if ev.button() == _Qt.ForwardButton:
                        win.forward()
                        return True
                return False

        self._nav_mouse_filter = _NavMouseFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._nav_mouse_filter)

    def resizeEvent(self, event):
        # Keeps the overlay drawer/scrim glued to the content area while
        # the window grows or shrinks (Interfaz 1.0).
        # @args: event - the QResizeEvent
        super().resizeEvent(event)
        if getattr(self, "_drawer", None) is not None \
                and self._drawer.isVisible():
            self._position_overlay()

    def closeEvent(self, event):
        # Quitting with live threads must not end in «QThread destroyed
        # while running», nor cut a SQLite write mid-way: cancel every
        # worker the window tracks (the _keep list plus the EXOTIC
        # prepare/run attribute) and give each a bounded wait. The
        # series/live workers of the Measure tab belong to the non-modal
        # UFE dialog: closing it first runs its own closeEvent, which
        # shuts them down.
        # @args: event - the QCloseEvent
        from PySide6.QtCore import QThread
        ufe = getattr(self, "_ufe", None)
        if ufe is not None and Shiboken.isValid(ufe):
            ufe.close()
        tracked = list(self._workers)
        exotic = getattr(self, "_exotic_worker", None)
        if exotic is not None:
            tracked.append(exotic)
        # every worker held by the lifetime guard too (the CCDciel poll, the
        # position refresh, the UFE tabs): a running one must be waited on
        # here or Qt aborts the exit with "QThread destroyed while running"
        tracked.extend(running_workers())
        threads = []
        for w in tracked:
            if isinstance(w, QThread) and Shiboken.isValid(w) and w not in threads:
                threads.append(w)
        for w in threads:
            if callable(getattr(w, "cancel", None)):
                w.cancel()
        for w in threads:
            if w.isRunning():
                w.wait(3000)
        super().closeEvent(event)
