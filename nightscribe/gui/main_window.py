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

from PySide6.QtCore import QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QFrame,
                               QGridLayout, QGroupBox, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidgetItem,
                               QMainWindow, QMessageBox, QPushButton,
                               QSpinBox, QDoubleSpinBox, QComboBox,
                               QTextEdit, QVBoxLayout, QWidget, QTableWidgetItem)

from .. import paths
from ..config import config
from ..core import (ephemeris, horizon, mpc_report, orbits, project,
                    sequence, suggest)
from ..core.db import db
from .workers import (BlinkExportWorker, BlinkWorker, ExploreWorker,
                      MpcResolveWorker, PostWorker, SunWorker, TonightWorker)

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent / "ui"

_STEP_NAMES = ("plan", "tab_plan", "capture", "tab_capture", "process",
               "tab_process", "analyse", "tab_analyse", "publish", "tab_publish")
_STEP_KEYS = ("plan", "capture", "process", "analyse", "publish")
_STEP_TABS = {0: "tab_plan", 1: "tab_capture", 2: "tab_process",
              3: "tab_analyse", 4: "tab_publish"}
_STEP_LABELS_ES = {"plan": "Plan", "capture": "Captura", "process": "Procesado",
                   "analyse": "Análisis", "publish": "Publicar"}
_STEP_LABELS_EN = {"plan": "Plan", "capture": "Capture", "process": "Process",
                   "analyse": "Analyse", "publish": "Publish"}


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
            ("Max alt", "max_alt"), ("Best time (UTC)", "max_time"),
            ("NEOfixer", "nf"), ("NObs", "nobs"), ("MOID (AU)", "moid"),
            ("Observed", "obs")],
    "sn": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
           ("SN type", "sn_type"), ("Host galaxy", "host"),
           ("Discovered", "disc"), ("Max alt", "max_alt"), ("Observed", "obs")],
    "comet": [("Object", "name"), ("Score", "score"), ("Mag", "mag"),
              ("Perihelion", "perihelion"), ("Max alt", "max_alt"),
              ("Best time (UTC)", "max_time"), ("Observed", "obs")],
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
                      ("Best time (UTC)", "max_time"), ("NEOfixer", "nf"),
                      ("NObs", "nobs"), ("Discovered", "disc"),
                      ("Observed", "obs")]


class MainWindow(QMainWindow):
    # UX v3.1: four tabs — Tonight (suggestion grid) · Projects (step tabs)
    # · Solar · History. Contextual dialogs for Explore/Post/Blink.

    def __init__(self):
        super().__init__()
        self._tonight_top = []
        self._tonight_all = []
        self._workers = []
        self._explored = None
        self._blink_pair = None
        self._blink_ref8 = None
        self._blink_obs8 = None
        self._blink_nudge = [0.0, 0.0]
        self._blink_phase = False
        self._current_project = None
        self._project_widgets = {}

        win = _load_ui("main_window")
        self.setWindowTitle(win.windowTitle())
        self.setCentralWidget(win.centralwidget)
        self.setStatusBar(win.statusbar)
        self.setMenuBar(win.menubar)
        self.resize(1200, 800)
        self._menus = win

        self._build_tabs()
        self._connect_menu()
        self._connect()
        from .. import __version__
        self.statusBar().showMessage(
            f"NightScribe {__version__} — "
            + self.tr("Ready — press 'Compute tonight'"), 8000)
        from PySide6.QtCore import QTimer
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

    def _connect_menu(self):
        self._menus.action_quit.triggered.connect(self.close)
        self._menus.action_settings.triggered.connect(self.on_open_settings)
        self._menus.action_about.triggered.connect(self.on_about)
        self._menus.action_sources.triggered.connect(self.on_sources)
        self._menus.action_explore.triggered.connect(self._tools_explore)
        self._menus.action_blink.triggered.connect(self._tools_blink)
        self._menus.action_lang_system.triggered.connect(
            lambda: self._set_language("system"))
        self._menus.action_lang_es.triggered.connect(
            lambda: self._set_language("es"))
        self._menus.action_lang_en.triggered.connect(
            lambda: self._set_language("en"))

    def _connect(self):
        t = self.tonight
        t.btn_compute.clicked.connect(self.on_compute_tonight)
        t.btn_show_all.toggled.connect(self._toggle_table)
        t.cmb_filter.currentIndexChanged.connect(self._fill_table)
        t.chk_show_observed.stateChanged.connect(self._fill_table)
        t.tbl_targets.cellDoubleClicked.connect(self._table_start_project)
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

    # ---------------- menu: language / settings / help ----------------

    def _set_language(self, lang):
        config.set("language", lang)
        self.statusBar().showMessage(
            self.tr("Language saved — restart the app to apply it"), 8000)

    def on_open_settings(self):
        dlg = _load_ui("settings_dialog")
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
        self.statusBar().showMessage(self.tr("Settings saved"), 6000)

    def _horizon_browse_into(self, dlg):
        path, _ = QFileDialog.getOpenFileName(
            dlg, self.tr("Choose the horizon file"), "",
            "Text files (*.txt);;All files (*)")
        if path:
            dlg.edt_horizon_file.setText(path)

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
        QMessageBox.about(self, "NightScribe",
                          "<b>NightScribe</b> 0.1<br><br>"
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

    # ---------------- Tonight: suggestion grid ----------------

    # Type accent colors per kind — used for the left border and icon.
    # Brighter than before for readable contrast on the dark card.
    _KIND_COLORS = {
        "sn": "#e05555", "neo": "#5588dd", "comet": "#55bb66",
        "pccp": "#dd9944", "transit": "#aa77cc", "alert": "#ddaa44",
    }
    _KIND_LABELS = {"neo": "NEO", "sn": "SN", "comet": "CMT",
                    "pccp": "PCCP", "transit": "TRN", "alert": "ALT"}

    def _type_pixmap(self, kind, size=32):
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
        w.finished.connect(self._tonight_done)
        self._keep(w)
        w.start()

    def _show_loading_state(self):
        # Placeholder cards while the worker runs
        container = self.tonight.scroll_suggestions.findChild(
            QWidget, "suggestions_container")
        if container.layout():
            while container.layout().count():
                item = container.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        else:
            container.setLayout(QGridLayout(container))
        grid = container.layout()
        for i in range(8):
            placeholder = QLabel(self.tr("Loading…"))
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(
                "color: #555; background: #12141f; border-radius: 6px;"
                " padding: 20px;")
            grid.addWidget(placeholder, i // 4, i % 4)

    def _tonight_done(self, top, all_scored, error=""):
        self.tonight.btn_compute.setEnabled(True)
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

    def _show_empty_state(self, msg):
        # Single helpful message when no targets are available
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
        lbl = QLabel(
            f"<div style='text-align: center; color: #555;'>"
            f"<br><b>{self.tr('No targets found')}</b><br><br>"
            f"{msg}<br><br>"
            f"<small>{self.tr('Check your network and try again.')}</small>"
            f"</div>")
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        layout.addStretch()
        self.tonight.lbl_context.setText(self.tr("No data"))

    def _update_night_header(self):
        from ..core import coords, ephem_minor
        jd = coords.jd_from_datetime(
            datetime.datetime.now(datetime.timezone.utc))
        m = ephem_minor.moon(jd)
        window = coords.tonight_window(config.get("lat"), config.get("lon"))
        if window:
            dusk = window[0].strftime("%H:%M")
            dawn = window[1].strftime("%H:%M")
        else:
            dusk = dawn = "—"
        date = datetime.date.today().isoformat()
        moon_pct = m["illum"] * 100
        self.tonight.lbl_context.setText(
            f"{date}  ·  {dusk}–{dawn}  ·  Moon {moon_pct:.0f}%")

    def _build_suggestion_grid(self):
        # Builds up to 8 suggestion cards in a 4-column grid inside the
        # scroll area. Each card has one primary action: start/continue project.
        container = self.tonight.scroll_suggestions.findChild(
            QWidget, "suggestions_container")
        # clear previous content
        if container.layout():
            while container.layout().count():
                item = container.layout().takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        else:
            grid = QGridLayout(container)
            container.setLayout(grid)
        grid = container.layout()
        # use up to 8 suggestions
        suggestions = self._tonight_all[:8]
        medals = ["🥇", "🥈", "🥉"] + [""] * 5
        for i, (t, score, parts, phrase) in enumerate(suggestions):
            card = self._make_card(t, score, phrase, medals[i], i)
            grid.addWidget(card, i // 4, i % 4)

    def _make_card(self, t, score, phrase, medal, idx):
        # @return: a compact card — visual icon + 3 text rows + button.
        # Why-tonight phrase and full window live in the tooltip.
        kind = t.get("kind", "")
        kind_color = self._KIND_COLORS.get(kind, "#888888")
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(
            f"QFrame {{ background: #12141f; border-radius: 6px;"
            f" border-left: 3px solid {kind_color}; }}"
            f"QFrame:hover {{ background: #1a1f30; }}")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        # row 0: type icon (visual anchor, 32px) + medal + name on the right
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        lbl_icon = QLabel()
        lbl_icon.setPixmap(self._type_pixmap(kind))
        top_row.addWidget(lbl_icon)
        top_row.addStretch()
        if medal:
            lbl_medal = QLabel(f"<b style='font-size:15px'>{medal}</b>")
            top_row.addWidget(lbl_medal)
        layout.addLayout(top_row)
        # row 1: object name (bold, clear white)
        lbl_name = QLabel(f"<b>{t['name']}</b>")
        lbl_name.setStyleSheet("font-size: 13px; color: #e8eaf2;")
        layout.addWidget(lbl_name)
        # row 2: mag + alt + score in one compact line
        mag = f"{t['mag']:.1f}" if t.get("mag") else "—"
        alt = f"{t['max_alt']:.0f}°" if t.get("max_alt") else "—"
        # score text colored by range (no emoji dots — guaranteed render)
        sc = int(score)
        sc_color = "#55bb66" if sc >= 70 else "#ddbb44" if sc >= 40 else "#dd8844"
        lbl_stats = QLabel(
            f"<span style='color:#b0b8d0'>mag {mag} · alt {alt}</span>"
            f"  <b style='color:{sc_color}'>{sc}</b>")
        lbl_stats.setStyleSheet("font-size: 12px;")
        layout.addWidget(lbl_stats)
        # row 3: status badge (compact) + moon icon if needed
        status_row = QHBoxLayout()
        status_row.setSpacing(4)
        badge = self._now_badge(t)
        if badge:
            is_now = "▲" in badge
            lbl_badge = QLabel(badge)
            lbl_badge.setStyleSheet(
                f"color: {'#55bb88' if is_now else '#88aadd'};"
                f" font-size: 11px; font-weight: bold;")
            status_row.addWidget(lbl_badge)
        moon = self._moon_text(t)
        if moon:
            lbl_moon = QLabel("🌙")
            lbl_moon.setToolTip(
                f"{self.tr('Moon')}: {moon}")
            lbl_moon.setStyleSheet("font-size: 11px;")
            status_row.addWidget(lbl_moon)
        status_row.addStretch()
        layout.addLayout(status_row)
        # row 4: single full-width button
        btn = self._card_button(t)
        layout.addWidget(btn)
        # tooltip with why-tonight phrase + window details
        tips = [self._txt(phrase)]
        win = self._window_text(t)
        if win:
            tips.append(win)
        card.setToolTip("\n".join(tips))
        return card

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

    def _moon_text(self, t):
        info = suggest.moon_info(t, config)
        if not info or not info.get("warning"):
            return ""
        return f"{info['sep_deg']:.0f}° · {info['illum']*100:.0f}%"

    def _card_button(self, t):
        # @return: full-width color-coded button — orange for Start,
        # green for Continue
        existing = project.list_projects(db, "active")
        has_proj = any(p["object_name"] == t.get("name")
                       or p["object_name"] == t.get("id")
                       for p in existing)
        if has_proj:
            btn = QPushButton(f"▶ {self.tr('Continue')}")
            btn.setStyleSheet(
                "QPushButton { background: #2a7a3a; color: #e8eaf2;"
                " border: none; border-radius: 4px; padding: 5px;"
                " font-weight: bold; }"
                "QPushButton:hover { background: #3a9a4a; }")
        else:
            btn = QPushButton(f"▶ {self.tr('Start')}")
            btn.setStyleSheet(
                "QPushButton { background: #c46922; color: #e8eaf2;"
                " border: none; border-radius: 4px; padding: 5px;"
                " font-weight: bold; }"
                "QPushButton:hover { background: #e47932; }")
        btn.clicked.connect(lambda _=False, t=t: self._start_or_continue(t))
        return btn

    def _start_or_continue(self, t):
        # Start a new project or jump to the existing one
        existing = project.list_projects(db, "active")
        match = next((p for p in existing
                      if p["object_name"] == t.get("name")
                      or p["object_name"] == t.get("id")), None)
        if match:
            self._goto_tab(1)
            for i in range(self.projects.lst_projects.count()):
                if self.projects.lst_projects.item(i).data(Qt.UserRole) == match["id"]:
                    self.projects.lst_projects.setCurrentRow(i)
                    break
        else:
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
            return float(t["max_alt"]) if t.get("max_alt") is not None else None
        if key == "max_time":
            return (t.get("max_time") or "")[11:16] or "—"
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

    def _fill_table(self):
        kind_filter = self.tonight.cmb_filter.currentIndex()
        kinds = [None, "neo", "sn", "comet", "pccp", "transit", "alert"]
        want = kinds[kind_filter] if kind_filter < len(kinds) else None
        cols = TABLE_COLS.get(want, TABLE_COLS_DEFAULT)
        show_obs = self.tonight.chk_show_observed.isChecked()
        tbl = self.tonight.tbl_targets
        tbl.setSortingEnabled(False)
        tbl.setRowCount(0)
        tbl.setColumnCount(len(cols))
        tbl.setHorizontalHeaderLabels([self.tr(h) for h, _k in cols])
        for t, score, parts, phrase in self._tonight_all:
            if want and t["kind"] != want:
                continue
            if db.is_observed(t["id"]) and not show_obs:
                continue
            row = tbl.rowCount()
            tbl.insertRow(row)
            for col, (_h, key) in enumerate(cols):
                val = self._table_value(t, score, key)
                if isinstance(val, float):
                    item = QTableWidgetItem()
                    item.setData(Qt.DisplayRole, val)
                else:
                    item = QTableWidgetItem(val if val is not None else "—")
                if col == 0:
                    item.setToolTip(self._txt(phrase))
                    item.setData(Qt.UserRole, t)
                tbl.setItem(row, col, item)
        tbl.setSortingEnabled(True)
        tbl.sortItems(1 if want else 2, Qt.DescendingOrder)
        tbl.resizeColumnsToContents()
        if not self.tonight.btn_show_all.isChecked():
            self.tonight.btn_show_all.setText(
                "▾ " + self.tr("Show all targets (%1)").replace(
                    "%1", str(len(self._tonight_all))))

    def _table_start_project(self, row, _col):
        item = self.tonight.tbl_targets.item(row, 0)
        if item:
            t = item.data(Qt.UserRole)
            if t:
                self._start_or_continue(t)

    # ---------------- Projects (ADR-019 v3.1) ----------------

    def on_refresh_projects(self):
        idx = self.projects.cmb_filter.currentIndex()
        statuses = ("active", None, "done", "archived")
        status = statuses[idx] if idx < len(statuses) else None
        projects = project.list_projects(db, status)
        lst = self.projects.lst_projects
        lst.clear()
        for p in projects:
            kind_label = {"sn": "SN", "neo": "NEO", "comet": self.tr("Comet"),
                          "pccp": "PCCP", "transit": self.tr("Transit")}.get(
                          p["kind"], p["kind"])
            cur = project.current_step(db, p["id"]) or "done"
            step_n = _STEP_KEYS.index(cur) + 1 if cur in _STEP_KEYS else 5
            item = QListWidgetItem(f"[{kind_label}] {p['object_name']}  {step_n}/5")
            item.setData(Qt.UserRole, p["id"])
            lst.addItem(item)
        if not projects:
            self.projects.lbl_header.setText(
                self.tr("No projects yet. Create one from Tonight."))
            self.projects.lbl_context.setText("—")
            self._clear_step_tabs()
            self._current_project = None

    def _project_selected(self):
        items = self.projects.lst_projects.selectedItems()
        if not items:
            return
        pid = items[0].data(Qt.UserRole)
        p = project.get(db, pid)
        if not p:
            return
        self._current_project = p
        self._render_project_header(p)
        self._build_step_tabs(p)

    def _render_project_header(self, p):
        kind_label = {"sn": "Supernova", "neo": "NEO", "comet": "Comet",
                      "pccp": "Possible comet",
                      "transit": "Exoplanet transit"}.get(p["kind"], p["kind"])
        cur = project.current_step(db, p["id"])
        step_n = _STEP_KEYS.index(cur) + 1 if cur in _STEP_KEYS else 5
        self.projects.lbl_header.setText(
            f"<b>[{kind_label}] {p['object_name']}</b> — "
            f"{self.tr('step')} {step_n}/5")
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
                         "tab_analyse", "tab_publish"):
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
        # update tab labels with status icons
        for i, key in enumerate(_STEP_KEYS):
            step = next((s for s in p["steps"] if s["step"] == key), None)
            icon = {"done": "✔", "current": "●", "pending": "○",
                    "skipped": "–"}.get(step["status"] if step else "○", "○")
            label = self._step_label(key)
            self.projects.tabs_steps.setTabText(i, f"{icon} {label}")
        # build content per step
        self._build_plan_tab(p, kind, ctx)
        self._build_capture_tab(p, kind, ctx)
        self._build_process_tab(p, kind, ctx)
        self._build_analyse_tab(p, kind, ctx)
        self._build_publish_tab(p, kind, ctx)
        # jump to the current step
        cur = project.current_step(db, p["id"])
        if cur and cur in _STEP_KEYS:
            self.projects.tabs_steps.setCurrentIndex(_STEP_KEYS.index(cur))
        self._update_step_status(p)

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
        if spn and spn_exp and cmb_f:
            project.update_step_data(
                db, self._current_project["id"], "plan",
                {"n_frames": spn.value(), "exp_s": spn_exp.value(),
                 "filter": cmb_f.currentText()})
            self.statusBar().showMessage(self.tr("Plan saved"), 5000)

    def _build_capture_tab(self, p, kind, ctx):
        tab = self.projects.tabs_steps.findChild(QWidget, "tab_capture")
        layout = tab.layout()
        # sequence export (all kinds)
        layout.addWidget(QLabel(self.tr("Export capture sequence")))
        cmb_fmt = QComboBox()
        cmb_fmt.addItem("NINA (JSON)")
        cmb_fmt.addItem("CCDciel (XML)")
        cmb_fmt.addItem("CSV (generic)")
        layout.addWidget(cmb_fmt)
        btn_seq = QPushButton(self.tr("Export sequence…"))
        btn_seq.clicked.connect(self._project_export_sequence)
        layout.addWidget(btn_seq)
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
        else:
            layout.addWidget(QLabel(
                self.tr("Process your images with your usual software.")))
        layout.addStretch()

    def _build_analyse_tab(self, p, kind, ctx):
        tab = self.projects.tabs_steps.findChild(QWidget, "tab_analyse")
        layout = tab.layout()
        if kind == "sn":
            btn = QPushButton(self.tr("Open blink…"))
            btn.clicked.connect(self._project_blink)
            layout.addWidget(btn)
            layout.addWidget(QLabel(
                f"<small>{self.tr('Pre-filled with')} {p['object_name']} "
                f"@ {ctx.get('ra_deg', 0):.4f}, {ctx.get('dec_deg', 0):+.4f}"
                f"</small>"))
        else:
            btn = QPushButton(self.tr("Explore object…"))
            btn.clicked.connect(self._project_explore)
            layout.addWidget(btn)
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

    def _project_step_changed(self, idx):
        # Update the status label when the user clicks a step tab
        if not self._current_project:
            return
        self._update_step_status(self._current_project)

    def _update_step_status(self, p):
        idx = self.projects.tabs_steps.currentIndex()
        key = _STEP_KEYS[idx] if idx < len(_STEP_KEYS) else "plan"
        step = next((s for s in p["steps"] if s["step"] == key), None)
        status = step["status"] if step else "—"
        status_txt = {"done": self.tr("done"), "current": self.tr("current"),
                      "pending": self.tr("pending"),
                      "skipped": self.tr("skipped")}.get(status, status)
        self.projects.lbl_step_status.setText(
            f"{self._step_label(key)} — {status_txt}")

    def _project_prev(self):
        idx = self.projects.tabs_steps.currentIndex()
        if idx > 0:
            self.projects.tabs_steps.setCurrentIndex(idx - 1)

    def _project_next(self):
        idx = self.projects.tabs_steps.currentIndex()
        if idx < self.projects.tabs_steps.count() - 1:
            self.projects.tabs_steps.setCurrentIndex(idx + 1)

    def _project_skip(self):
        if not self._current_project:
            return
        idx = self.projects.tabs_steps.currentIndex()
        key = _STEP_KEYS[idx] if idx < len(_STEP_KEYS) else None
        if key:
            project.set_step_status(db, self._current_project["id"], key,
                                    project.STEP_SKIPPED)
            self._project_next()
            self._refresh_current_project()

    def _project_mark_done(self):
        if not self._current_project:
            return
        idx = self.projects.tabs_steps.currentIndex()
        key = _STEP_KEYS[idx] if idx < len(_STEP_KEYS) else None
        if key:
            project.set_step_status(db, self._current_project["id"], key,
                                    project.STEP_DONE)
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
        if not (spn and spn_exp and cmb_f):
            return
        plan = sequence.make_plan(spn.value(), spn_exp.value(),
                                  cmb_f.currentText(), cfg=config)
        ctx = self._current_project["context"]
        target = {"name": self._current_project["object_name"],
                  "ra_deg": ctx.get("ra_deg"), "dec_deg": ctx.get("dec_deg")}
        fmt_map = {0: "nina", 1: "ccdciel", 2: "csv"}
        fmt = fmt_map[self._project_widgets["cmb_seqfmt"].currentIndex()]
        ext = {"nina": ".json", "ccdciel": ".xml", "csv": ".csv"}[fmt]
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

    def _project_explore(self):
        if self._current_project:
            self._open_explore_dialog(self._current_project["object_name"])

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
        kind = target.get("kind")
        name = target.get("name") or target.get("id")
        if kind not in project.VALID_KINDS or not name:
            self.statusBar().showMessage(
                self.tr("Cannot create a project for this target"), 6000)
            return
        ctx = {k: target.get(k) for k in
               ("id", "name", "kind", "mag", "ra_deg", "dec_deg",
                "max_alt", "max_time", "window_start", "window_end",
                "hours_up", "sn_type", "host", "disc_date",
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

    # ---------------- Contextual dialogs (Explore / Post / Blink) --------

    def _tools_explore(self):
        name, ok = QInputDialog.getText(self, self.tr("Explore object"),
                                        self.tr("Object:"))
        if ok and name.strip():
            self._open_explore_dialog(name.strip())

    def _tools_blink(self):
        self._open_blink_dialog()

    def _open_explore_dialog(self, name):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Explore — %1").replace("%1", name))
        dlg.resize(900, 640)
        layout = QVBoxLayout(dlg)
        explore = _load_ui("explore_tab")
        layout.addWidget(explore)
        explore.edt_explore.setText(name)
        explore.btn_explore.clicked.connect(
            lambda: self._dialog_explore(explore, name))
        explore.chk_deep.stateChanged.connect(
            lambda: self._dialog_explore_params(explore))
        explore.btn_mkpost.clicked.connect(
            lambda: (self._open_post_dialog(name), dlg.accept()))
        self._dialog_explore(explore, name)
        dlg.exec()

    def _dialog_explore(self, explore, name):
        explore.btn_explore.setEnabled(False)
        explore.lbl_hook.setText(self.tr("Loading…"))
        fallback = next((t for t, _s, _p, _ph in self._tonight_all
                         if t["id"] == name or t["name"] == name), None)
        w = ExploreWorker(config, name, fallback_target=fallback)
        w.finished.connect(lambda e: self._dialog_explore_done(explore, name, e))
        self._keep(w)
        w.start()

    def _dialog_explore_done(self, explore, name, e):
        from ..core import narrative
        explore.btn_explore.setEnabled(True)
        if not e or not e.get("data"):
            explore.lbl_hook.setText(self.tr("Not found: ") + name)
            return
        explore.lbl_hook.setText(self._txt(narrative.hook(e)))
        self._explored = e
        self._dialog_explore_params(explore)
        self._dialog_explore_charts(explore, e)

    def _dialog_explore_params(self, explore):
        e = self._explored
        if not e:
            return
        rows = self._orbit_rows(e)
        deep = explore.chk_deep.isChecked()
        if not deep:
            rows = [r for r in rows if r.get("level") == "basic"]
        tbl = explore.tbl_params
        tbl.setRowCount(0)
        for r in rows:
            row = tbl.rowCount()
            tbl.insertRow(row)
            param = self._txt(r["param"]) if isinstance(r["param"], dict) \
                else str(r["param"])
            tbl.setItem(row, 0, QTableWidgetItem(param))
            tbl.setItem(row, 1, QTableWidgetItem(str(r["value"])))
            tbl.setItem(row, 2, QTableWidgetItem(self._txt(r)))
        tbl.resizeColumnsToContents()
        tbl.setColumnWidth(2, 520)

    def _dialog_explore_charts(self, explore, e):
        import matplotlib
        matplotlib.use("Agg")
        from PySide6.QtGui import QPixmap
        from ..core import coords
        from ..viz import families_view, orbit_view, sky_view, sn_view
        d = e.get("data") or {}
        outdir = paths.data_dir() / "posts"
        jd = coords.jd_from_datetime(
            datetime.datetime.now(datetime.timezone.utc))
        sb = d.get("sbdb")
        if sb and sb.get("elements") and sb["elements"].get("a") \
                and sb["elements"].get("e", 1) < 0.99:
            p = outdir / "_explore_orbit.png"
            orbit_view.draw_orbit(dict(sb["elements"]), jd=jd,
                                  obj_name=e["name"],
                                  approach=d.get("next_approach"), out=str(p))
            explore.lbl_orbit.setPixmap(QPixmap(str(p)))
            fam = d.get("family")
            a = sb["elements"].get("a")
            if fam:
                p2 = outdir / "_explore_families.png"
                families_view.draw_families(fam, obj_name=e["name"], a=a,
                                            out=str(p2))
                explore.lbl_families.setPixmap(QPixmap(str(p2)))
        ra_deg = dec_deg = None
        eph = d.get("ephem")
        if eph:
            try:
                ra_deg = coords.ra_hms_to_deg(eph["ra"])
                dec_deg = coords.dec_dms_to_deg(eph["dec"])
            except (ValueError, AttributeError):
                pass
        sim = d.get("simbad")
        if sim and ra_deg is None:
            try:
                ra_deg = coords.ra_hms_to_deg(sim["ra"])
                dec_deg = coords.dec_dms_to_deg(sim["dec"])
            except (ValueError, AttributeError):
                pass
        if ra_deg is not None:
            p3 = outdir / "_explore_sky.png"
            hor = horizon.from_config(config)
            sky_view.draw_sky(ra_deg, dec_deg, config.get("lat"),
                              config.get("lon"), obj_name=e["name"],
                              out=str(p3), horizon=hor.alt_at,
                              margin=float(config.get("horizon_margin_deg", 0)))
            explore.lbl_sky.setPixmap(QPixmap(str(p3)))
        if sim:
            from ..core.sources import cutouts
            img = cutouts.reference_cutout(ra_deg, dec_deg)
            if img:
                p4 = outdir / "_explore_field.png"
                sn_view.draw_sn_field(img, sn_name=e["name"], out=str(p4))
                explore.lbl_field.setPixmap(QPixmap(str(p4)))

    def _orbit_rows(self, e):
        d = e.get("data") or {}
        sb = d.get("sbdb")
        if sb:
            moid = sb.get("moid")
            try:
                moid = float(moid) if moid is not None else None
            except (TypeError, ValueError):
                moid = None
            return orbits.explain_elements(sb.get("elements") or {},
                                           sb.get("phys") or {},
                                           d.get("family"), moid)
        if d.get("unconfirmed"):
            return orbits.explain_neofixer(d["unconfirmed"])
        return []

    def _open_post_dialog(self, name):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Post — %1").replace("%1", name))
        dlg.resize(700, 560)
        layout = QVBoxLayout(dlg)
        post_w = _load_ui("post_tab")
        layout.addWidget(post_w)
        post_w.edt_object.setText(name)
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
        post_w.txt_es.setPlainText(rendered.get("es", ""))
        post_w.txt_en.setPlainText(rendered.get("en", ""))
        post_w.txt_tweet.setPlainText(rendered.get("tweet", ""))
        from ..core import post as post_mod
        written = post_mod.save_outputs(rendered, paths.data_dir() / "posts",
                                        name)
        db.mark_posted(name)
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

    def on_refresh_sun(self):
        self.solar.btn_refresh_sun.setEnabled(False)
        channel = self._SDO_CHANNELS[self.solar.cmb_channel.currentIndex()]
        w = SunWorker(channel)
        w.finished.connect(self._sun_done)
        self._keep(w)
        w.start()

    def _channel_changed(self):
        self.on_refresh_sun()

    def _sun_done(self, data, img_path):
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
        self._draw_sun_map(data.get("regions") or [])

    def _set_sun_image(self, img_path):
        from PySide6.QtGui import QPixmap
        pix = QPixmap(img_path)
        self.solar.lbl_sun_image.setPixmap(
            pix.scaled(420, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _draw_sun_map(self, regions):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from PySide6.QtGui import QPixmap
        from ..viz import style, sun_panel
        fig = plt.figure(figsize=(3.4, 3.4), dpi=100)
        style.apply_style()
        ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
        sun_panel._draw_region_map(ax, regions)
        p = paths.data_dir() / "posts" / "_sun_map.png"
        style.save(fig, str(p))
        plt.close(fig)
        self.solar.lbl_sun_map.setPixmap(QPixmap(str(p)))

    def _fill_almanac(self):
        from ..core import coords, ephem_minor
        jd = coords.jd_from_datetime(
            datetime.datetime.now(datetime.timezone.utc))
        m = ephem_minor.moon(jd)
        phase_icons = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]
        icon = phase_icons[int(m["phase_age_days"] / 29.53 * 8) % 8]
        self.solar.lbl_moon.setText(
            f"{icon} " + self.tr("Moon: %1% lit · %2 km · %3 days")
            .replace("%1", f"{m['illum'] * 100:.0f}")
            .replace("%2", f"{m['dist_km']:,.0f}")
            .replace("%3", f"{m['phase_age_days']:.0f}"))
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
