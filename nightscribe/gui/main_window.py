############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Main window module (UX v3, ADR-019)
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
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox,
                               QFileDialog, QListWidgetItem, QMainWindow,
                               QMessageBox, QTableWidgetItem)

from .. import paths
from ..config import config
from ..core import horizon, orbits, project, suggest
from ..core.db import db
from .workers import (BlinkExportWorker, BlinkWorker, ExploreWorker,
                      MpcResolveWorker, PostWorker, SunWorker, TonightWorker)

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).parent / "ui"


def _load_ui(name, parent=None):
    # @args: name - .ui file name without extension, parent - widget
    # @return: the loaded widget
    file = QFile(str(UI_DIR / f"{name}.ui"))
    file.open(QFile.ReadOnly)
    widget = QUiLoader().load(file, parent)
    file.close()
    return widget


# Per-kind table columns: (header translation key, value getter). Dynamic
# columns per type filter (ADR-017).
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
    # UX v3: four tabs (Tonight · Projects · Solar · History) with
    # contextual Explore/Post/Blink dialogs (ADR-019).

    def __init__(self):
        super().__init__()
        self._tonight_top = []
        self._tonight_all = []
        self._tonight_now = []
        self._workers = []
        self._explored = None
        self._selected_row = None
        # blink state (ADR-018)
        self._blink_pair = None
        self._blink_ref8 = None
        self._blink_obs8 = None
        self._blink_nudge = [0.0, 0.0]
        self._blink_phase = False
        # projects hub state
        self._current_project = None

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
        self._now_timer.timeout.connect(self._fill_now)
        self._now_timer.start(5 * 60 * 1000)
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink_tick)
        self._blink_render_timer = QTimer(self)
        self._blink_render_timer.setSingleShot(True)
        self._blink_render_timer.setInterval(120)
        self._blink_render_timer.timeout.connect(self._blink_render)

    # ---------------- helpers ----------------

    def _lang(self):
        # @return: effective UI language ("es" | "en")
        from PySide6.QtCore import QLocale
        lang = config.get("language", "system")
        if lang == "system":
            lang = QLocale.system().name()[:2]
        return lang if lang in ("es", "en") else "en"

    def _txt(self, pair):
        # @args: pair - {"es","en"} dict
        # @return: single-language string for the UI
        return orbits.pick(pair, self._lang())

    def _goto_tab(self, index):
        # @args: index - tab index in the main tab widget
        from PySide6.QtWidgets import QTabWidget
        self.centralWidget().findChild(QTabWidget, "tabs").setCurrentIndex(index)

    # ---------------- tab construction ----------------

    def _build_tabs(self):
        # Loads each tab widget into the tab container, keeping the
        # placeholder tab titles from main_window.ui.
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

    def _connect_menu(self):
        # Menu bar actions.
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
        # Wires every button to its action.
        t = self.tonight
        t.btn_compute.clicked.connect(self.on_compute_tonight)
        t.btn_now_refresh.clicked.connect(self._fill_now)
        t.cmb_filter.currentIndexChanged.connect(self._fill_table)
        t.chk_show_observed.stateChanged.connect(self._fill_table)
        t.tbl_targets.cellDoubleClicked.connect(self._explore_row)
        t.tbl_targets.itemSelectionChanged.connect(self._row_selected)
        t.btn_detail_explore.clicked.connect(self._detail_explore)
        t.btn_detail_post.clicked.connect(self._detail_post)
        t.btn_detail_project.clicked.connect(self._detail_project)
        t.chk_detail_obs.stateChanged.connect(self._detail_observed)
        for i in range(3):
            getattr(t, f"card{i}_post").clicked.connect(
                lambda _=False, i=i: self._post_from_card(i))
            getattr(t, f"card{i}_project").clicked.connect(
                lambda _=False, i=i: self._project_from_card(i))
        # projects hub
        p = self.projects
        p.btn_refresh.clicked.connect(self.on_refresh_projects)
        p.cmb_filter.currentIndexChanged.connect(self.on_refresh_projects)
        p.lst_projects.itemSelectionChanged.connect(self._project_selected)
        p.btn_advance.clicked.connect(self._project_advance)
        p.btn_skip.clicked.connect(self._project_skip)
        p.btn_explore.clicked.connect(self._project_explore)
        p.btn_post.clicked.connect(self._project_post)
        p.btn_blink.clicked.connect(self._project_blink)
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
        # @args: url - external resource to open in the browser
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(url))

    # ---------------- menu: language / settings / help ----------------

    def _set_language(self, lang):
        # Stores the language choice; a restart applies it fully (ADR-014).
        config.set("language", lang)
        self.statusBar().showMessage(
            self.tr("Language saved — restart the app to apply it"), 8000)

    def on_open_settings(self):
        # Settings as a modal dialog (from the Tools menu).
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
        # UX v3 groups (ADR-020 / ADR-021)
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
        # Lets the user pick a TheSkyX-style horizon text file.
        path, _ = QFileDialog.getOpenFileName(
            dlg, self.tr("Choose the horizon file"), "",
            "Text files (*.txt);;All files (*)")
        if path:
            dlg.edt_horizon_file.setText(path)

    def _resolve_into(self, dlg):
        # Resolves the MPC code into the dialog fields.
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

    # ---------------- Tonight ----------------

    def on_compute_tonight(self):
        # Starts the background worker for tonight's list.
        self.tonight.btn_compute.setEnabled(False)
        self.tonight.lbl_now.setText(self.tr("Computing tonight…"))
        self.statusBar().showMessage(self.tr("Computing tonight…"))
        w = TonightWorker(config, db)
        w.finished.connect(self._tonight_done)
        self._keep(w)
        w.start()

    def _tonight_done(self, top, all_scored, error=""):
        # Fills cards, the now-section and the table when the worker ends.
        self.tonight.btn_compute.setEnabled(True)
        if error or not all_scored:
            msg = error or self.tr("no sources answered")
            self.tonight.lbl_now.setText(
                self.tr("Could not compute tonight: %1 — check your network "
                        "and try 'Compute tonight'.").replace("%1", msg))
            self.statusBar().showMessage(
                self.tr("Error computing tonight: %1").replace("%1", msg),
                15000)
            return
        self._tonight_top = top
        self._tonight_all = all_scored
        self._tonight_now = [t for t, _s, _p, _ph in all_scored]
        medals = ["🥇", "🥈", "🥉"]
        for i in range(3):
            label = getattr(self.tonight, f"card{i}_text")
            obs_chk = getattr(self.tonight, f"card{i}_obs")
            if i < len(top):
                t, score, parts, phrase = top[i]
                label.setText(self._card_text(t, score, phrase))
                try:
                    obs_chk.stateChanged.disconnect()
                except (RuntimeError, TypeError):
                    pass
                obs_chk.setChecked(db.is_observed(t["id"]))
                obs_chk.stateChanged.connect(
                    lambda _s, tid=t["id"], kind=t["kind"]:
                    self._toggle_observed(tid, kind, _s))
            else:
                label.setText("—")
        self._fill_now()
        self._fill_table()
        self.statusBar().showMessage(
            self.tr("%1 targets evaluated").replace("%1", str(len(all_scored))),
            8000)

    def _card_text(self, t, score, phrase):
        # @args: t - target dict, score - float, phrase - {"es","en"} dict
        # @return: the HTML card body with window and Moon/safe-start hints
        mag = f"{t['mag']:.1f}" if t.get("mag") else "—"
        alt = f"{t['max_alt']:.0f}°" if t.get("max_alt") else "—"
        extra = ""
        if t.get("nobs"):
            extra += f" · NObs {t['nobs']}"
        if t.get("disc_date"):
            extra += f" · {self.tr('discovered')} {t['disc_date'].split('.')[0]}"
        nf = t.get("nf_priority")
        if nf:
            extra += f" · NEOfixer: {str(nf).capitalize()}"
        # UX v3: observing window against the real horizon (ADR-020)
        win_txt = self._window_text(t)
        # Moon hint (ADR-020)
        moon_txt = self._moon_text(t)
        return (f"<b>{t['name']}</b> [{t['kind']}] "
                f"· score {score}<br>mag {mag} · alt {alt}{extra}"
                f"{win_txt}{moon_txt}"
                f"<br><i>{self._txt(phrase)}</i>")

    def _window_text(self, t):
        # @return: short HTML snippet with the safe observing window, or ""
        ws = (t.get("window_start") or "")[11:16]
        we = (t.get("window_end") or "")[11:16]
        if not ws or not we:
            return ""
        return (f"<br><small>{self.tr('window')} {ws}–{we} UTC · "
                f"{self.tr('safe start until')} {we}</small>")

    def _moon_text(self, t):
        # @return: short HTML moon warning snippet, or ""
        info = suggest.moon_info(t, config)
        if not info or not info.get("warning"):
            return ""
        return (f"<br><small>🌙 {self.tr('Moon')}: "
                f"{info['sep_deg']:.0f}° · {info['illum']*100:.0f}%</small>")

    def _fill_now(self):
        # The "right now" band: targets currently above the horizon.
        if not self._tonight_now:
            return
        from ..core import planner
        now = planner.visible_now(self._tonight_now, config)
        rank = {id(t): s for t, s, _p, _ph in self._tonight_all}
        now.sort(key=lambda x: -rank.get(id(x[0]), 0))
        if not now:
            self.tonight.lbl_now.setText(
                self.tr("Nothing from the list is above the horizon right now."))
            return
        now_txt = self.tr("now")
        max_txt = self.tr("max")
        at_txt = self.tr("at")
        lines = []
        for t, alt, az in now[:3]:
            mag = f"{t['mag']:.1f}" if t.get("mag") else "—"
            best = (t.get("max_time") or "")[11:16]
            best_txt = ""
            if best and t.get("max_alt"):
                best_txt = (f" · {max_txt} {t['max_alt']:.0f}° "
                            f"{at_txt} {best} UTC")
            lines.append(f"▸ <b>{t['name']}</b> [{t['kind']}] — "
                         f"{now_txt} alt {alt:.0f}°, az {az:.0f}°, "
                         f"mag {mag}{best_txt}")
        self.tonight.lbl_now.setText("<br>".join(lines))

    def _table_value(self, t, score, key):
        # @args: t - target, score - its score, key - column value getter name
        # @return: cell value (str/float/None)
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
        # Refills the table with dynamic columns per selected type filter.
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
                    item.setData(Qt.UserRole, t["id"])
                tbl.setItem(row, col, item)
        tbl.setSortingEnabled(True)
        tbl.sortItems(1 if want else 2, Qt.DescendingOrder)
        tbl.resizeColumnsToContents()

    def _row_selected(self):
        # Shows the selected target's "why" and wires the detail buttons.
        items = self.tonight.tbl_targets.selectedItems()
        if not items:
            return
        row = items[0].row()
        id_item = self.tonight.tbl_targets.item(row, 0)
        if not id_item:
            return
        obj_id = id_item.data(Qt.UserRole)
        found = next((x for x in self._tonight_all if x[0]["id"] == obj_id),
                     None)
        if not found:
            return
        t, score, parts, phrase = found
        self._selected_row = t
        self.tonight.lbl_detail.setText(
            f"<b>{t['name']}</b> — {self._txt(phrase)}")
        try:
            self.tonight.chk_detail_obs.stateChanged.disconnect()
        except RuntimeError:
            pass
        self.tonight.chk_detail_obs.setChecked(db.is_observed(t["id"]))
        self.tonight.chk_detail_obs.stateChanged.connect(
            lambda s, tid=t["id"], kind=t["kind"]: self._toggle_observed(
                tid, kind, s))

    def _detail_explore(self):
        if self._selected_row:
            self._open_explore_dialog(self._selected_row["id"])

    def _detail_post(self):
        if self._selected_row:
            self._open_post_dialog(self._selected_row["id"])

    def _detail_project(self):
        if self._selected_row:
            self._create_project(self._selected_row)

    def _detail_observed(self, state):
        pass  # handled by the connection in _row_selected

    def _toggle_observed(self, obj_id, kind, state):
        # Marks/unmarks an object as observed (and reports to NEOfixer if set).
        if state:
            db.mark_observed(obj_id, kind)
            key = config.get("neofixer_key", "")
            if key and kind == "neo":
                from ..core.sources import neofixer
                neofixer.report(key, config.get("mpc_code"), obj_id, "observed")
        else:
            db.unmark_observed(obj_id)
        self._fill_table()

    def _explore_row(self, row, _col):
        item = self.tonight.tbl_targets.item(row, 0)
        if item:
            self._open_explore_dialog(item.data(Qt.UserRole) or item.text())

    def _post_from_card(self, i):
        if i < len(self._tonight_top):
            self._open_post_dialog(self._tonight_top[i][0]["id"])

    def _project_from_card(self, i):
        if i < len(self._tonight_top):
            self._create_project(self._tonight_top[i][0])

    # ---------------- Projects (ADR-019) ----------------

    def on_refresh_projects(self):
        # Refills the project list from the database.
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
            item = QListWidgetItem(f"[{kind_label}] {p['object_name']}")
            item.setData(Qt.UserRole, p["id"])
            lst.addItem(item)
        if not projects:
            self.projects.lbl_header.setText(
                self.tr("No projects yet. Create one from Tonight."))
            self.projects.lbl_context.setText("—")
            self.projects.lst_steps.clear()
            self.projects.lbl_step_info.setText("—")
            self._current_project = None

    def _project_selected(self):
        # Loads the selected project's detail into the stepper panel.
        items = self.projects.lst_projects.selectedItems()
        if not items:
            return
        pid = items[0].data(Qt.UserRole)
        p = project.get(db, pid)
        if not p:
            return
        self._current_project = p
        self._render_project(p)

    def _render_project(self, p):
        # @args: p - full project dict (with steps and files)
        kind_label = {"sn": "Supernova", "neo": "NEO", "comet": "Comet",
                      "pccp": "Possible comet",
                      "transit": "Exoplanet transit"}.get(p["kind"], p["kind"])
        self.projects.lbl_header.setText(
            f"<b>[{kind_label}] {p['object_name']}</b> — {p['status']}")
        ctx = p["context"]
        ctx_parts = []
        if ctx.get("mag") is not None:
            ctx_parts.append(f"mag {ctx['mag']}")
        if ctx.get("ra_deg") is not None:
            ctx_parts.append(f"RA {ctx['ra_deg']:.2f}°")
        if ctx.get("dec_deg") is not None:
            ctx_parts.append(f"Dec {ctx['dec_deg']:+.2f}°")
        if ctx.get("rate_arcsec_min"):
            ctx_parts.append(f"{ctx['rate_arcsec_min']:.1f}″/min")
        self.projects.lbl_context.setText(" · ".join(ctx_parts) or "—")
        lst = self.projects.lst_steps
        lst.clear()
        icons = {"done": "✔", "current": "▶", "pending": "○",
                 "skipped": "–"}
        step_labels = {"plan": self.tr("Plan"), "capture": self.tr("Capture"),
                       "process": self.tr("Process"),
                       "analyse": self.tr("Analyse"),
                       "publish": self.tr("Publish")}
        cur = project.current_step(db, p["id"])
        for s in p["steps"]:
            icon = icons.get(s["status"], "○")
            label = step_labels.get(s["step"], s["step"])
            lst.addItem(f"{icon} {label}")
        info = (self.tr("Current step: ") + step_labels.get(cur, "—")
                if cur else self.tr("All steps done"))
        n_files = len(p["files"])
        if n_files:
            info += f" · {n_files} {self.tr('file(s)')}"
        self.projects.lbl_step_info.setText(info)

    def _project_advance(self):
        if not self._current_project:
            return
        p = project.advance(db, self._current_project["id"])
        if p:
            self._current_project = p
            self._render_project(p)
            self.statusBar().showMessage(self.tr("Step completed"), 5000)

    def _project_skip(self):
        if not self._current_project:
            return
        cur = project.current_step(db, self._current_project["id"])
        if cur:
            project.set_step_status(db, self._current_project["id"], cur,
                                    project.STEP_SKIPPED)
            self._project_advance()

    def _project_explore(self):
        if self._current_project:
            self._open_explore_dialog(self._current_project["object_name"])

    def _project_post(self):
        if self._current_project:
            self._open_post_dialog(self._current_project["object_name"])

    def _project_blink(self):
        if self._current_project:
            ctx = self._current_project["context"]
            self._open_blink_dialog(sn_name=self._current_project["object_name"],
                                    ra=ctx.get("ra_deg"),
                                    dec=ctx.get("dec_deg"))

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
        # @args: target - dict from the planner/tonight list
        kind = target.get("kind")
        name = target.get("name") or target.get("id")
        if kind not in project.VALID_KINDS or not name:
            self.statusBar().showMessage(
                self.tr("Cannot create a project for this target"), 6000)
            return
        # snapshot the relevant context
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
            self._goto_tab(1)  # Projects tab
            # select the new project
            for i in range(self.projects.lst_projects.count()):
                if self.projects.lst_projects.item(i).data(Qt.UserRole) == p["id"]:
                    self.projects.lst_projects.setCurrentRow(i)
                    break
            self.statusBar().showMessage(
                self.tr("Project created: %1").replace("%1", name), 8000)

    # ---------------- Contextual dialogs (Explore / Post / Blink) --------

    def _tools_explore(self):
        # Ad-hoc Explore from the Tools menu (asks for the object name).
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, self.tr("Explore object"),
                                        self.tr("Object:"))
        if ok and name.strip():
            self._open_explore_dialog(name.strip())

    def _tools_blink(self):
        # Ad-hoc Blink from the Tools menu.
        self._open_blink_dialog()

    def _open_explore_dialog(self, name):
        # Opens the Explore widget inside a modal dialog, pre-filled.
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Explore — %1").replace("%1", name))
        dlg.resize(900, 640)
        from PySide6.QtWidgets import QVBoxLayout
        layout = QVBoxLayout(dlg)
        explore = _load_ui("explore_tab")
        layout.addWidget(explore)
        explore.edt_explore.setText(name)
        # wire the explore widget to a local handler
        explore.btn_explore.clicked.connect(
            lambda: self._dialog_explore(explore, name))
        explore.chk_deep.stateChanged.connect(
            lambda: self._dialog_explore_params(explore))
        explore.btn_mkpost.clicked.connect(
            lambda: (self._open_post_dialog(name), dlg.accept()))
        # kick off the enrichment immediately
        self._dialog_explore(explore, name)
        dlg.exec()

    def _dialog_explore(self, explore, name):
        # Runs the ExploreWorker and fills the dialog widget (reuses the
        # same logic as the old Explore tab, but local to the dialog).
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
        # Parameters table in one language, basic or in-depth.
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
        # 2D charts inside the Explore dialog (orbit / sky / families / field).
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
        # @args: e - enriched dict
        # @return: list of interpreted parameter rows
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
        # Opens the Post widget inside a modal dialog, pre-filled.
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Post — %1").replace("%1", name))
        dlg.resize(700, 560)
        from PySide6.QtWidgets import QVBoxLayout
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
        # kick off generation immediately
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
            post_w.lbl_files.setText(
                self.tr("Not found: ") + name + " — " +
                self.tr("try an MPC designation (2021EQ3), a comet (29P), "
                        "SN/AT (SN2023ixf), a planet (HD 209458 b) or 'sun'"))
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

    def _open_blink_dialog(self, sn_name=None, ra=None, dec=None):
        # Opens the Blink widget inside a modal dialog, pre-filled when the
        # context provides the SN name/coordinates (ADR-019).
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Blink"))
        dlg.resize(1100, 640)
        from PySide6.QtWidgets import QVBoxLayout
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
        # wire the blink widget to local handlers (reuse the same methods,
        # but pointed at the dialog's widget)
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
        # stop timers when the dialog closes
        self._blink_timer.stop()

    # ---- blink dialog helpers (operate on the dialog's widget) ----

    def _dialog_blink_browse(self, b):
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Choose the plate-solved FITS image"), "",
            "FITS (*.fits *.fit *.fts);;All files (*)")
        if path:
            b.edt_fits.setText(path)

    def _dialog_blink_manual(self, b, state):
        b.edt_ra.setEnabled(bool(state))
        b.edt_dec.setEnabled(bool(state))

    def _dialog_blink_manual_coords(self, b):
        # @return: (ra, dec) in degrees, or None if unchecked/invalid
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
                    self.tr("Manual coordinates invalid — use degrees, e.g. "
                            "187.7050 and +12.3910"))
                return
            ra, dec = manual
        elif not name:
            b.lbl_blink_status.setText(
                self.tr("Type the supernova name (e.g. 2026ziz) or tick "
                        "'Manual coordinates'."))
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
        status = (self.tr("%1 @ (%2, %3) — %4 · %5×%6 px")
                  .replace("%1", pair["name"])
                  .replace("%2", f"{pair['ra']:.5f}")
                  .replace("%3", f"{pair['dec']:+.5f}")
                  .replace("%4", pair["ref_label"])
                  .replace("%5", str(w)).replace("%6", str(h)))
        if pair.get("flipped"):
            status += " · " + self.tr("mirrored image: flipped horizontally "
                                      "to align")
        b.lbl_blink_status.setText(status)
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
        # Debounced render for slider drags (reuse the main render timer).
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
                self, self.tr("Export blink GIF"),
                str(outdir / f"{pair['name']}_blink.gif"), "GIF (*.gif)")
        elif kind == "video":
            out, _ = QFileDialog.getSaveFileName(
                self, self.tr("Export blink video"),
                str(outdir / f"{pair['name']}_blink.mp4"),
                "MP4 video (*.mp4)")
        else:
            out, _ = QFileDialog.getSaveFileName(
                self, self.tr("Export side-by-side PNG"),
                str(outdir / f"{pair['name']}_before_after.png"),
                "PNG (*.png)")
        if not out:
            return
        effect = "blink" if b.rdo_blink.isChecked() else "fade"
        sn = pair["sn_xy"] if b.chk_marker.isChecked() else None
        b.lbl_blink_status.setText(
            self.tr("Rendering %1…").replace("%1", kind.upper()))
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

    # ---- live blink tick works for whichever blink widget is active ----

    def _blink_tick(self):
        if not self._blink_pair or not hasattr(self, "_blink_pix"):
            self._blink_timer.stop()
            return
        self._blink_phase = not self._blink_phase
        pix = self._blink_pix[int(self._blink_phase)]
        b = getattr(self, "_blink_dialog_widget", None)
        if b is not None:
            self._blink_show_dlg(b, pix)
        else:
            self._blink_show(pix)

    def _blink_render(self, *_args):
        # When the debounce timer fires, render the active blink widget.
        b = getattr(self, "_blink_dialog_widget", None)
        if b is not None and self._blink_pair:
            self._dialog_blink_render(b)

    # ---------------- shared blink helpers (unchanged from v2) -----------

    def _blink_shift_ref(self, ref8):
        # Applies the manual nudge to the survey frame only (PIL affine).
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
        # @args: zoom - 1, 2 or 4
        # @return: (disp_ref, disp_obs, sn_display_xy or None)
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

    def _blink_show(self, pix):
        b = getattr(self, "_blink_dialog_widget", None)
        if b is not None:
            self._blink_show_dlg(b, pix)

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
        lang = self._lang()
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
            f"{icon} " + self.tr("Moon: %1% lit · %2 km away · %3 days old")
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
