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
                                QListWidgetItem, QMainWindow, QMessageBox,
                                QProgressBar, QPushButton, QScrollArea,
                                QSpinBox, QDoubleSpinBox, QComboBox,
                                QTextEdit, QVBoxLayout, QWidget,
                                QTableWidgetItem)

from .. import paths
from ..config import config
from ..version import full_version
from ..core import (ephemeris, mpc_report, orbits, project,
                    sequence, suggest)
from ..core.db import db
from . import theme
from .overview import ObjectPanel
from .skeleton import ShimmerRow
from .workers import (BlinkExportWorker, BlinkWorker, ExploreWorker,
                      MpcResolveWorker, PostWorker, SunWorker, TonightWorker)

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent / "ui"

# Four guided steps for every project kind. The old "analyse" step (ADR-019,
# review 2026-08-28) was dropped: the explore view already lives in the
# Details tab and the SN blink now sits in "process".
_STEP_KEYS = ("plan", "capture", "process", "publish")
_STEP_TABS = {0: "tab_plan", 1: "tab_capture", 2: "tab_process",
              3: "tab_publish"}
_STEP_LABELS_ES = {"plan": "Plan", "capture": "Captura", "process": "Procesado",
                   "publish": "Publicar"}
_STEP_LABELS_EN = {"plan": "Plan", "capture": "Capture", "process": "Process",
                   "publish": "Publish"}


def _load_ui(name, parent=None):
    # @args: name - .ui file name without extension, parent - widget
    # @return: the loaded widget
    file = QFile(str(UI_DIR / f"{name}.ui"))
    file.open(QFile.ReadOnly)
    widget = QUiLoader().load(file, parent)
    file.close()
    return widget


# Per-kind table columns for the full (collapsed) table
TABLE_COLS = {
    "neo": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
            ("Max alt", "max_alt"), ("Best time (UTC)", "best_time"),
            ("NEOfixer", "nf"), ("NObs", "nobs"), ("MOID (AU)", "moid"),
            ("Observed", "obs")],
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
    "alert": [("Object", "name"), ("Approach date", "adate"),
              ("Distance (LD)", "ald"), ("Diameter (m)", "adiam"),
              ("Max mag", "amag"), ("Velocity (km/s)", "avel"),
              ("Observed", "obs")],
}
TABLE_COLS_DEFAULT = [("Object", "name"), ("Type", "kind"), ("Score", "score"),
                      ("Mag", "mag"), ("Max alt", "max_alt"),
                      ("Best time (UTC)", "best_time"), ("NEOfixer", "nf"),
                      ("NObs", "nobs"), ("Discovered", "disc"),
                      ("Observed", "obs")]

# Canonical kind order (theme.KIND_LABELS order, ADR-026): the tonight filter
# combo and the settings whitelist stay in the same order wherever shown.
KIND_ORDER = ["neo", "sn", "comet", "pccp", "transit", "alert"]


class _ClickableFrame(QFrame):
    # A frame that re-emits a plain mouse click anywhere over it (the
    # row's «explore» hook). Child labels without text selection forward
    # the event here; the action button keeps its own click.

    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


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
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.on_refresh_projects)
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
        widgets = (self.tonight, self.projects, self.solar,
                   self.history) = (
            _load_ui("tonight_tab"), _load_ui("projects_tab"),
            _load_ui("solar_tab"), _load_ui("history_tab"))
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
        p.lst_projects.itemSelectionChanged.connect(self._project_selected)
        p.tabs_steps.currentChanged.connect(self._project_step_changed)
        p.btn_prev.clicked.connect(self._project_prev)
        p.btn_next.clicked.connect(self._project_next)
        p.btn_skip.clicked.connect(self._project_skip)
        p.btn_mark_done.clicked.connect(self._project_mark_done)
        p.btn_archive.clicked.connect(self._project_archive)
        p.btn_delete.clicked.connect(self._project_delete)
        self.solar.btn_refresh_sun.clicked.connect(self.on_refresh_sun)
        self.solar.cmb_channel.currentIndexChanged.connect(self._channel_changed)
        self.solar.btn_raben.clicked.connect(
            lambda: self._open_url("https://www.raben.com/maps"))
        self.solar.btn_solarmonitor.clicked.connect(
            lambda: self._open_url("https://www.solarmonitor.org"))
        self.solar.btn_sidc.clicked.connect(
            lambda: self._open_url("https://sidc.be/uset"))
        self.history.btn_refresh_hist.clicked.connect(self.on_refresh_history)

    def _open_url(self, url):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    # ---------------- menu: settings / help ----------------

    def on_open_settings(self):
        dlg = _load_ui("settings_dialog")
        # The Observing tab packs four group boxes; give it room so the
        # kind checkboxes and rows are never crushed (the .ui minimum is
        # the floor; the initial size opens it comfortably).
        dlg.resize(860, 740)
        dlg.edt_mpc_code.setText(config.get("mpc_code", ""))
        dlg.edt_obs_name.setText(config.get("observatory_name", ""))
        dlg.spn_lat.setValue(float(config.get("lat", 0)))
        dlg.spn_lon.setValue(float(config.get("lon", 0)))
        dlg.spn_height.setValue(int(config.get("height", 0)))
        dlg.spn_aperture.setValue(float(config.get("aperture_inches", 10)))
        dlg.spn_limit_mag.setValue(float(config.get("limit_mag", 20)))
        dlg.spn_min_alt.setValue(float(config.get("min_alt", 30)))
        dlg.edt_neofixer_key.setText(config.get("neofixer_key", ""))
        dlg.edt_astrometry_key.setText(config.get("astrometry_key", ""))
        dlg.spn_pixel_um.setValue(float(config.get("pixel_um", 3.76)))
        dlg.spn_focal_mm.setValue(float(config.get("focal_mm", 2000)))
        dlg.edt_horizon_file.setText(config.get("horizon_file", ""))
        dlg.spn_horizon_margin.setValue(
            float(config.get("horizon_margin_deg", 0)))
        dlg.chk_moon_enabled.setChecked(bool(config.get("moon_limit_enabled",
                                                        True)))
        dlg.spn_moon_sep.setValue(float(config.get("moon_min_sep_deg", 45)))
        dlg.spn_moon_illum.setValue(float(config.get("moon_max_illum", 0.5)))
        dlg.spn_overhead.setValue(float(config.get("overhead_s", 15)))
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
        config.set("limit_mag", dlg.spn_limit_mag.value())
        config.set("min_alt", dlg.spn_min_alt.value())
        config.set("neofixer_key", dlg.edt_neofixer_key.text().strip())
        config.set("astrometry_key", dlg.edt_astrometry_key.text().strip())
        config.set("pixel_um", dlg.spn_pixel_um.value())
        config.set("focal_mm", dlg.spn_focal_mm.value())
        config.set("horizon_file", dlg.edt_horizon_file.text().strip())
        config.set("horizon_margin_deg", dlg.spn_horizon_margin.value())
        config.set("moon_limit_enabled", dlg.chk_moon_enabled.isChecked())
        config.set("moon_min_sep_deg", dlg.spn_moon_sep.value())
        config.set("moon_max_illum", dlg.spn_moon_illum.value())
        config.set("overhead_s", dlg.spn_overhead.value())
        config.set("tns_bot_name", dlg.edt_tns_bot.text().strip())
        config.set("tns_bot_key", dlg.edt_tns_bot_key.text().strip())
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

    def _clear_suggestions(self):
        # Drops every widget inside the suggestion scroll container and
        # guarantees it has a single-column vertical layout (one row each).
        container = self.tonight.scroll_suggestions.findChild(
            QWidget, "suggestions_container")
        if container.layout():
            while container.layout().count():
                item = container.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
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
                    "alert": self.tr("Close approach")}.get(t["kind"], t["kind"])
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
            return (t.get("disc_date") or "").split(".")[0] or "—"
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
        #        (1 == the Projects hub, per main_window.ui order)
        # @return: None
        # Keep the Projects hub list always fresh: refresh on every visit,
        # so projects appear without pressing "Refresh" (which stays as a
        # just-in-case fallback). Only the Projects tab triggers a reload.
        if index == 1:
            self.on_refresh_projects()

    def on_refresh_projects(self):
        idx = self.projects.cmb_filter.currentIndex()
        statuses = ("active", None, "done", "archived")
        status = statuses[idx] if idx < len(statuses) else None
        projects = project.list_projects(db, status)
        lst = self.projects.lst_projects
        # preserve the selected project across the refresh (the list reloads
        # on every visit to the tab and at startup, so we must not drop the
        # project the user is currently viewing)
        sel = lst.currentItem()
        keep_id = sel.data(Qt.UserRole) if sel is not None else None
        lst.clear()
        for p in projects:
            kind_label = {"sn": "SN", "neo": "NEO", "comet": self.tr("Comet"),
                          "pccp": "PCCP", "transit": self.tr("Transit")}.get(
                          p["kind"], p["kind"])
            cur = project.current_step(db, p["id"]) or "done"
            step_n = _STEP_KEYS.index(cur) + 1 if cur in _STEP_KEYS else 4
            item = QListWidgetItem(f"[{kind_label}] {p['object_name']}  {step_n}/4")
            item.setData(Qt.UserRole, p["id"])
            lst.addItem(item)
            if p["id"] == keep_id:
                lst.setCurrentItem(item)
        if not projects:
            self.projects.lbl_header.setText(
                self.tr("No projects yet. Create one from Tonight."))
            self.projects.lbl_context.setText("—")
            self._reset_proj_panel()
            self._clear_step_tabs()
            self._current_project = None

    def _project_selected(self):
        items = self.projects.lst_projects.selectedItems()
        if not items:
            self._reset_proj_panel()
            return
        pid = items[0].data(Qt.UserRole)
        p = project.get(db, pid)
        if not p:
            self._reset_proj_panel()
            return
        self._current_project = p
        self._render_project_header(p)
        self._build_step_tabs(p)
        # "Detalles" first: the object's business card is what you open a
        # project for; the current step is marked ● on its own tab and
        # reached with Next →
        self.projects.tabs_steps.setCurrentIndex(0)
        self._update_step_buttons()
        panel = self._get_proj_panel()
        if panel._worker is not None:
            panel.cancel()   # switching projects: drop the in-flight load
        ctx = p.get("context") or {}
        panel.explore(p["object_name"], fallback_target=ctx, ctx=ctx)

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
        # Builds the reusable panel on first use and docks it into the
        # «Detalles» tab (index 0), so the object's business card owns the
        # whole panel height with the step tabs next to it.
        if self._proj_panel is None:
            from .overview import ObjectPanel
            panel = ObjectPanel(loader=self._proj_panel_loader)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            area.setFrameShape(QFrame.Shape.NoFrame)
            area.setWidget(panel)
            tab = self.projects.tabs_steps.findChild(
                QWidget, "tab_details")
            tab.layout().addWidget(area)
            self._proj_panel = panel
            self._proj_panel_area = area
        return self._proj_panel

    def _reset_proj_panel(self):
        # Drops any in-flight worker and empties the panel (used when the
        # selection or the project list goes away).
        if self._proj_panel is not None:
            self._proj_panel.cancel()

    def _render_project_header(self, p):
        kind_label = {"sn": "Supernova", "neo": "NEO", "comet": "Comet",
                      "pccp": "Possible comet",
                      "transit": "Exoplanet transit"}.get(p["kind"], p["kind"])
        cur = project.current_step(db, p["id"])
        step_n = _STEP_KEYS.index(cur) + 1 if cur in _STEP_KEYS else 4
        self.projects.lbl_header.setText(
            f"<b>[{kind_label}] {p['object_name']}</b> — "
            f"{self.tr('step')} {step_n}/4")
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

    def _clear_step_tabs(self):
        # Remove all dynamic content from step tabs
        for tab_name in ("tab_plan", "tab_capture", "tab_process",
                         "tab_publish"):
            tab = self.projects.tabs_steps.findChild(QWidget, tab_name)
            if tab and tab.layout():
                while tab.layout().count():
                    item = tab.layout().takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
        self.projects.lbl_step_status.setText("—")
        self._project_widgets = {}

    def _build_step_tabs(self, p):
        # Populate each step tab with only the content relevant to the
        # project kind. Steps are clickable (the QTabWidget handles that).
        self._clear_step_tabs()
        kind = p["kind"]
        ctx = p["context"]
        # update tab labels with status icons (steps start at index 1;
        # index 0 is "Detalles", which keeps its plain title)
        for i, key in enumerate(_STEP_KEYS):
            step = next((s for s in p["steps"] if s["step"] == key), None)
            icon = {"done": "✔", "current": "●", "pending": "○",
                    "skipped": "–"}.get(step["status"] if step else "○", "○")
            label = self._step_label(key)
            self.projects.tabs_steps.setTabText(i + 1, f"{icon} {label}")
        # build content per step
        self._build_plan_tab(p, kind, ctx)
        self._build_capture_tab(p, kind, ctx)
        self._build_process_tab(p, kind, ctx)
        self._build_publish_tab(p, kind, ctx)
        # "Detalles" stays open (set by _project_selected); the current
        # step is marked ● on its tab and reached with Next →
        self._update_step_status(p)
        self._update_step_buttons()

    def _build_plan_tab(self, p, kind, ctx):
        tab = self.projects.tabs_steps.findChild(QWidget, "tab_plan")
        layout = tab.layout()
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

    def _build_capture_tab(self, p, kind, ctx):
        tab = self.projects.tabs_steps.findChild(QWidget, "tab_capture")
        layout = tab.layout()
        # sequence export (all kinds)
        layout.addWidget(QLabel(self.tr("Export capture sequence")))
        cmb_fmt = QComboBox()
        cmb_fmt.addItem(self.tr("NINA (JSON)"))
        cmb_fmt.addItem(self.tr("CCDciel (targets)"))
        cmb_fmt.addItem(self.tr("CSV (generic)"))
        layout.addWidget(cmb_fmt)
        btn_seq = QPushButton(self.tr("Export sequence…"))
        btn_seq.clicked.connect(self._project_export_sequence)
        layout.addWidget(btn_seq)
        # CCDciel calibration frames (ADR-021): the generated target list
        # appends a Dark and a Bias step from these counts (0 = omit).
        grp = QGroupBox(self.tr("Calibration"))
        form = QFormLayout(grp)
        spn_darks = QSpinBox(); spn_darks.setMinimum(0); spn_darks.setMaximum(999)
        spn_darks.setValue(25)
        form.addRow(self.tr("Darks:"), spn_darks)
        spn_darkexp = QDoubleSpinBox(); spn_darkexp.setMinimum(0.1)
        spn_darkexp.setMaximum(3600.0)
        spn_exps = self._project_widgets.get("spn_exps")
        spn_darkexp.setValue(spn_exps.value() if spn_exps else 60.0)
        form.addRow(self.tr("Dark exposure (s):"), spn_darkexp)
        spn_bias = QSpinBox(); spn_bias.setMinimum(0); spn_bias.setMaximum(999)
        spn_bias.setValue(100)
        form.addRow(self.tr("Bias:"), spn_bias)
        layout.addWidget(grp)
        plan_data = next((s["data"] for s in p["steps"]
                          if s["step"] == "plan"), {})
        if plan_data.get("n_darks") is not None:
            spn_darks.setValue(int(plan_data["n_darks"]))
        if plan_data.get("exp_dark"):
            spn_darkexp.setValue(float(plan_data["exp_dark"]))
        if plan_data.get("n_bias") is not None:
            spn_bias.setValue(int(plan_data["n_bias"]))
        self._project_widgets["spn_darks"] = spn_darks
        self._project_widgets["spn_darkexp"] = spn_darkexp
        self._project_widgets["spn_bias"] = spn_bias
        # NEO: also ephemeris export
        if kind in ("neo", "pccp"):
            layout.addWidget(QLabel(""))
            layout.addWidget(QLabel(self.tr("Export ephemeris for planetarium")))
            btn_eph = QPushButton(self.tr("Export ephemeris…"))
            btn_eph.clicked.connect(self._project_export_ephem)
            layout.addWidget(btn_eph)
        self._project_widgets["cmb_seqfmt"] = cmb_fmt
        layout.addStretch()

    def _build_process_tab(self, p, kind, ctx):
        tab = self.projects.tabs_steps.findChild(QWidget, "tab_process")
        layout = tab.layout()
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
        else:
            layout.addWidget(QLabel(
                self.tr("Process your images with your usual software.")))
        layout.addStretch()

    def _build_publish_tab(self, p, kind, ctx):
        tab = self.projects.tabs_steps.findChild(QWidget, "tab_publish")
        layout = tab.layout()
        btn = QPushButton(self.tr("Generate post…"))
        btn.clicked.connect(self._project_post)
        layout.addWidget(btn)
        layout.addWidget(QLabel(
            f"<small>{self.tr('Opens the post dialog for')} "
            f"{p['object_name']}</small>"))
        layout.addStretch()

    def _step_key_idx(self, idx):
        # Tab index -> _STEP_KEYS index. Index 0 is the "Detalles" tab (no
        # step); steps start at 1. Returns None when there is no step key.
        # @args: idx - tab index
        # @return: position in _STEP_KEYS, or None on the details tab
        if idx <= 0:
            return None
        n = idx - 1
        return n if n < len(_STEP_KEYS) else None

    def _project_step_changed(self, idx):
        # Update the status label and the step buttons when the tab changes
        self._update_step_buttons()
        if not self._current_project:
            return
        self._update_step_status(self._current_project)

    def _update_step_status(self, p):
        idx = self.projects.tabs_steps.currentIndex()
        n = self._step_key_idx(idx)
        if n is None:
            self.projects.lbl_step_status.setText("—")
            return
        key = _STEP_KEYS[n]
        step = next((s for s in p["steps"] if s["step"] == key), None)
        status = step["status"] if step else "—"
        status_txt = {"done": self.tr("done"), "current": self.tr("current"),
                      "pending": self.tr("pending"),
                      "skipped": self.tr("skipped")}.get(status, status)
        self.projects.lbl_step_status.setText(
            f"{self._step_label(key)} — {status_txt}")

    def _update_step_buttons(self):
        # The step buttons (prev / skip / done / next) only make sense on the
        # step tabs, not on "Detalles": prev has no target there, skip / done
        # have no step to act on, next is allowed (it enters step 1).
        idx = self.projects.tabs_steps.currentIndex()
        last = self.projects.tabs_steps.count() - 1
        on_details = idx == 0
        self.projects.btn_prev.setEnabled(not on_details)
        self.projects.btn_next.setEnabled(idx != last)
        self.projects.btn_skip.setEnabled(not on_details)
        self.projects.btn_mark_done.setEnabled(not on_details)

    def _project_prev(self):
        idx = self.projects.tabs_steps.currentIndex()
        if not self.projects.btn_prev.isEnabled():
            return
        self.projects.tabs_steps.setCurrentIndex(idx - 1)

    def _project_next(self):
        idx = self.projects.tabs_steps.currentIndex()
        if not self.projects.btn_next.isEnabled():
            return
        self.projects.tabs_steps.setCurrentIndex(idx + 1)

    def _project_skip(self):
        if not self._current_project:
            return
        if not self.projects.btn_skip.isEnabled():
            return
        n = self._step_key_idx(self.projects.tabs_steps.currentIndex())
        if n is None:
            return
        project.set_step_status(db, self._current_project["id"],
                                _STEP_KEYS[n], project.STEP_SKIPPED)
        self._project_next()
        self._refresh_current_project()

    def _project_mark_done(self):
        if not self._current_project:
            return
        if not self.projects.btn_mark_done.isEnabled():
            return
        n = self._step_key_idx(self.projects.tabs_steps.currentIndex())
        if n is None:
            return
        project.set_step_status(db, self._current_project["id"],
                                _STEP_KEYS[n], project.STEP_DONE)
        self._project_next()
        self._refresh_current_project()

    def _refresh_current_project(self):
        if not self._current_project:
            return
        p = project.get(db, self._current_project["id"])
        if p:
            self._current_project = p
            self._render_project_header(p)
            self._build_step_tabs(p)

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
        plan = sequence.make_plan(
            spn.value(), spn_exp.value(), cmb_f.currentText(), cfg=config,
            n_darks=n_darks,
            exp_dark=spn_darkexp.value() if n_darks else None,
            n_bias=spn_bias.value())
        ctx = self._current_project.get("context") or {}
        target = {"name": self._current_project["object_name"],
                  "ra_deg": ctx.get("ra_deg"), "dec_deg": ctx.get("dec_deg"),
                  "safe_window": ctx.get("safe_window")}
        fmt_map = {0: "nina", 1: "ccdciel", 2: "csv"}
        fmt = fmt_map[self._project_widgets["cmb_seqfmt"].currentIndex()]
        ext = {"nina": ".json", "ccdciel": ".targets", "csv": ".csv"}[fmt]
        outdir = paths.data_dir() / "exports"
        outdir.mkdir(parents=True, exist_ok=True)
        default = outdir / f"{target['name']}_sequence{ext}"
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export capture sequence"), str(default),
            f"*{ext};;All files (*)")
        if not out:
            return
        try:
            path = sequence.export(target, plan, out, fmt=fmt)
            project.add_file(db, self._current_project["id"], path, "sequence")
            self.statusBar().showMessage(
                self.tr("Written to %1").replace("%1", path), 8000)
        except OSError as err:
            self.statusBar().showMessage(
                self.tr("Export failed: %1").replace("%1", str(err)), 8000)

    def _project_export_ephem(self):
        if not self._current_project:
            return
        ctx = self._current_project["context"]
        obj_id = ctx.get("id") or self._current_project["object_name"]
        site = config.get("mpc_code", "Z41")
        items = [self.tr("CSV (generic)"), "TheSkyX", "Cartes du Ciel"]
        choice, ok = QInputDialog.getItem(
            self, self.tr("Ephemeris format"), self.tr("Format:"),
            items, 0, False)
        if not ok:
            return
        fmt = {0: "csv", 1: "skyx", 2: "cdc"}[items.index(choice)]
        ext = ".csv" if fmt == "csv" else ".txt"
        outdir = paths.data_dir() / "exports"
        outdir.mkdir(parents=True, exist_ok=True)
        default = outdir / f"{obj_id}_ephemeris{ext}"
        out, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export ephemeris"), str(default),
            f"*{ext};;All files (*)")
        if not out:
            return
        self.statusBar().showMessage(self.tr("Querying Horizons…"))
        rows = ephemeris.generate(obj_id, site, step="30m")
        if not rows:
            self.statusBar().showMessage(
                self.tr("No ephemeris for %1").replace("%1", obj_id), 8000)
            return
        try:
            path = ephemeris.export(rows, out, fmt=fmt,
                                    obj_name=self._current_project["object_name"])
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
        outdir = paths.data_dir() / "exports"
        outdir.mkdir(parents=True, exist_ok=True)
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
        project.set_status(db, self._current_project["id"],
                           project.STATUS_ARCHIVED)
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
                 "perihelion_date", "transit", "approach")
                if target.get(k) is not None}
        p = project.create(db, kind, name, ctx)
        if p:
            self.on_refresh_projects()
            self._goto_tab(1)
            for i in range(self.projects.lst_projects.count()):
                if self.projects.lst_projects.item(i).data(Qt.UserRole) == p["id"]:
                    self.projects.lst_projects.setCurrentRow(i)
                    break
            self.statusBar().showMessage(
                self.tr("Project created: %1").replace("%1", name), 8000)
        return p

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
        self._goto_tab(1)
        for i in range(self.projects.lst_projects.count()):
            if self.projects.lst_projects.item(i).data(Qt.UserRole) == match["id"]:
                self.projects.lst_projects.setCurrentRow(i)
                break
        return True

    # ---------------- Contextual dialogs (Explore / Post / Blink) --------

    def _tools_explore(self):
        name, ok = QInputDialog.getText(self, self.tr("Explore object"),
                                        self.tr("Object:"))
        if ok and name.strip():
            self._open_explore_dialog(name.strip())

    def _tools_blink(self):
        self._open_blink_dialog()

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
            self._create_project(_target(nm, fb))
            dlg.accept()

        def _on_continue(nm, fb):
            # the CTA said "resume the active project". When nothing
            # matches the ad-hoc name (Tools menu), create it — same
            # intent as the card's green "Continue" button.
            fb = fb if isinstance(fb, dict) else None
            name_or_id = nm or (fb.get("id") if fb else None)
            if not self._goto_active_project(name_or_id, fb):
                self._create_project(_target(nm, fb))
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
        # default save folder: the data dir's posts directory
        post_w.edt_folder.setText(str(paths.data_dir() / "posts"))
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
        if charts and self._current_project \
                and self._current_project["object_name"] == name:
            pid = self._current_project["id"]
            for p in charts.values():
                project.add_file(db, pid, str(p), "chart")
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
