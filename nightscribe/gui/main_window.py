############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Main window module (UX v2, ADR-017)
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
from PySide6.QtWidgets import (QApplication, QDialog, QMainWindow, QMessageBox,
                               QTableWidgetItem)

from .. import paths
from ..config import config
from ..core import orbits
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
    # Six views + menu bar; settings live in a dialog (ADR-017).

    def __init__(self):
        super().__init__()
        self._tonight_top = []
        self._tonight_all = []
        self._tonight_now = []
        self._workers = []
        self._explored = None
        self._selected_row = None
        # blink tab state (ADR-018)
        self._blink_pair = None
        self._blink_ref8 = None
        self._blink_obs8 = None
        self._blink_nudge = [0.0, 0.0]      # screen coords: +dx right, +dy up
        self._blink_phase = False

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
        # open the app already suggesting the night: nobody wants an empty
        # home view (auto-compute shortly after the window shows)
        from PySide6.QtCore import QTimer
        if config.is_configured():
            QTimer.singleShot(400, self.on_compute_tonight)
        # refresh the "right now" band every 5 minutes once we have targets
        self._now_timer = QTimer(self)
        self._now_timer.timeout.connect(self._fill_now)
        self._now_timer.start(5 * 60 * 1000)
        # live blink alternates reference/observatory every half second
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink_tick)
        # slider drags fire many events; coalesce them into one render
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

    # ---------------- tab construction ----------------

    def _build_tabs(self):
        # Loads each tab widget into the tab container, keeping the
        # placeholder tab titles from main_window.ui.
        from PySide6.QtWidgets import QTabWidget
        tabs = self.centralWidget().findChild(QTabWidget, "tabs")
        widgets = (self.tonight, self.explore, self.post,
                   self.solar, self.history, self.blink) = (
            _load_ui("tonight_tab"), _load_ui("explore_tab"),
            _load_ui("post_tab"), _load_ui("solar_tab"),
            _load_ui("history_tab"), _load_ui("blink_tab"))
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
        t.chk_detail_obs.stateChanged.connect(self._detail_observed)
        for i in range(3):
            getattr(t, f"card{i}_post").clicked.connect(
                lambda _=False, i=i: self._post_from_card(i))
        self.explore.btn_explore.clicked.connect(self.on_explore)
        self.explore.chk_deep.stateChanged.connect(self._explore_render_params)
        self.explore.btn_mkpost.clicked.connect(self._explore_post)
        self.explore.chk_explore_obs.stateChanged.connect(
            self._explore_observed)
        self.post.btn_generate.clicked.connect(self.on_generate_post)
        self.post.btn_copy_es.clicked.connect(
            lambda: QApplication.clipboard().setText(self.post.txt_es.toPlainText()))
        self.post.btn_copy_en.clicked.connect(
            lambda: QApplication.clipboard().setText(self.post.txt_en.toPlainText()))
        self.post.btn_copy_tweet.clicked.connect(
            lambda: QApplication.clipboard().setText(self.post.txt_tweet.toPlainText()))
        self.solar.btn_refresh_sun.clicked.connect(self.on_refresh_sun)
        self.solar.cmb_channel.currentIndexChanged.connect(self._channel_changed)
        self.solar.btn_raben.clicked.connect(
            lambda: self._open_url("https://www.raben.com/maps"))
        self.solar.btn_solarmonitor.clicked.connect(
            lambda: self._open_url("https://www.solarmonitor.org"))
        self.solar.btn_sidc.clicked.connect(
            lambda: self._open_url("https://sidc.be/uset"))
        self.history.btn_refresh_hist.clicked.connect(self.on_refresh_history)
        b = self.blink
        b.btn_browse.clicked.connect(self.on_blink_browse)
        b.btn_prepare.clicked.connect(self.on_blink_prepare)
        b.chk_manual.stateChanged.connect(self._blink_manual_toggled)
        b.btn_auto_stretch.clicked.connect(self._blink_auto_stretch)
        b.sld_black.valueChanged.connect(self._blink_render_soon)
        b.sld_white.valueChanged.connect(self._blink_render_soon)
        b.sld_gamma.valueChanged.connect(self._blink_render_soon)
        b.sld_balance.valueChanged.connect(self._blink_render_soon)
        b.btn_balance_auto.clicked.connect(self._blink_balance_auto)
        b.chk_blink_live.stateChanged.connect(self._blink_live_toggled)
        b.sld_fade.valueChanged.connect(self._blink_render_soon)
        b.chk_marker.stateChanged.connect(self._blink_render_soon)
        b.sld_marker.valueChanged.connect(self._blink_render_soon)
        b.cmb_zoom.currentIndexChanged.connect(self._blink_render)
        b.spn_interval.valueChanged.connect(self._blink_interval_changed)
        b.btn_up.clicked.connect(lambda: self._blink_nudge_move(0.0, 0.5))
        b.btn_down.clicked.connect(lambda: self._blink_nudge_move(0.0, -0.5))
        b.btn_left.clicked.connect(lambda: self._blink_nudge_move(-0.5, 0.0))
        b.btn_right.clicked.connect(lambda: self._blink_nudge_move(0.5, 0.0))
        b.btn_gif.clicked.connect(self.on_blink_export_gif)
        b.btn_video.clicked.connect(self.on_blink_export_video)
        b.btn_png.clicked.connect(self.on_blink_export_png)

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
        dlg.btn_resolve.clicked.connect(lambda: self._resolve_into(dlg))
        # QUiLoader does not wire the button box: connect Save/Cancel here
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
        self.statusBar().showMessage(self.tr("Settings saved"), 6000)

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
        from ..core import planner
        self.tonight.btn_compute.setEnabled(True)
        if error or not all_scored:
            # tell the user *why* nothing showed up, do not stay silent
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
                label.setText(
                    f"{medals[i]} <b>{t['name']}</b> [{t['kind']}] "
                    f"· score {score}<br>mag {mag} · alt {alt}{extra}"
                    f"<br><i>{self._txt(phrase)}</i>")
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

    def _fill_now(self):
        # The "right now" band: targets currently above the horizon.
        if not self._tonight_now:
            return
        from ..core import planner, suggest
        now = planner.visible_now(self._tonight_now, config)
        # order the visible ones by their tonight score
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
            # NEOfixer priority scale, from their own filter docs
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
                    item.setData(Qt.DisplayRole, val)  # numeric sort
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
            self._goto_explore(self._selected_row["id"])

    def _detail_post(self):
        if self._selected_row:
            self._goto_post(self._selected_row["id"])

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
            self._goto_explore(item.data(Qt.UserRole) or item.text())

    def _goto_explore(self, name):
        from PySide6.QtWidgets import QTabWidget
        self.centralWidget().findChild(QTabWidget, "tabs").setCurrentIndex(1)
        self.explore.edt_explore.setText(name)
        self.on_explore()

    def _goto_post(self, name):
        from PySide6.QtWidgets import QTabWidget
        self.centralWidget().findChild(QTabWidget, "tabs").setCurrentIndex(2)
        self.post.edt_object.setText(name)
        self.on_generate_post()

    def _post_from_card(self, i):
        if i < len(self._tonight_top):
            self._goto_post(self._tonight_top[i][0]["id"])

    # ---------------- Explore ----------------

    def on_explore(self):
        # Explained card for the typed object (background worker + fallback).
        name = self.explore.edt_explore.text().strip()
        if not name:
            return
        self.explore.btn_explore.setEnabled(False)
        self.explore.lbl_hook.setText(self.tr("Loading…"))
        fallback = next((t for t, _s, _p, _ph in self._tonight_all
                         if t["id"] == name or t["name"] == name), None)
        w = ExploreWorker(config, name, fallback_target=fallback)
        w.finished.connect(lambda e: self._explore_done(name, e))
        self._keep(w)
        w.start()

    def _explore_done(self, name, e):
        from ..core import narrative
        self.explore.btn_explore.setEnabled(True)
        if not e or not e.get("data"):
            self.explore.lbl_hook.setText(self.tr("Not found: ") + name)
            return
        self._explored = e
        self.explore.lbl_hook.setText(self._txt(narrative.hook(e)))
        try:
            self.explore.chk_explore_obs.stateChanged.disconnect()
        except RuntimeError:
            pass
        self.explore.chk_explore_obs.setChecked(db.is_observed(name))
        self.explore.chk_explore_obs.stateChanged.connect(
            lambda s: self._toggle_observed(name, e.get("type"), s))
        self._explore_render_params()
        self._explore_render_charts()

    def _explore_render_params(self):
        # Parameters table in one language, basic or in-depth.
        e = self._explored
        if not e:
            return
        rows = self._orbit_rows(e)
        deep = self.explore.chk_deep.isChecked()
        if not deep:
            rows = [r for r in rows if r.get("level") == "basic"]
        tbl = self.explore.tbl_params
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

    def _explore_render_charts(self):
        # 2D charts inside the Explore tabs (orbit / sky / families / field).
        e = self._explored
        if not e:
            return
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
            self.explore.lbl_orbit.setPixmap(QPixmap(str(p)))
            fam = d.get("family")
            a = sb["elements"].get("a")
            if fam:
                p2 = outdir / "_explore_families.png"
                families_view.draw_families(fam, obj_name=e["name"], a=a,
                                            out=str(p2))
                self.explore.lbl_families.setPixmap(QPixmap(str(p2)))
        # sky curve whenever we have coordinates
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
            sky_view.draw_sky(ra_deg, dec_deg, config.get("lat"),
                              config.get("lon"), obj_name=e["name"],
                              out=str(p3))
            self.explore.lbl_sky.setPixmap(QPixmap(str(p3)))
        # SN reference field with crosshair
        if sim:
            from ..core.sources import cutouts
            img = cutouts.reference_cutout(ra_deg, dec_deg)
            if img:
                p4 = outdir / "_explore_field.png"
                sn_view.draw_sn_field(img, sn_name=e["name"], out=str(p4))
                self.explore.lbl_field.setPixmap(QPixmap(str(p4)))

    def _explore_post(self):
        if self._explored:
            self._goto_post(self._explored["name"])

    def _explore_observed(self, state):
        pass  # handled by the connection in _explore_done

    # ---------------- Post ----------------

    def on_generate_post(self):
        # Starts the background worker that builds the drafts.
        name = self.post.edt_object.text().strip()
        if not name:
            return
        self.post.btn_generate.setEnabled(False)
        self.statusBar().showMessage(self.tr("Building drafts…"))
        fallback = next((t for t, _s, _p, _ph in self._tonight_all
                         if t["id"] == name or t["name"] == name), None)
        w = PostWorker(config, name, fallback_target=fallback)
        w.finished.connect(lambda e, r: self._post_done(name, e, r))
        self._keep(w)
        w.start()

    def _post_done(self, name, e, rendered):
        self.post.btn_generate.setEnabled(True)
        if not rendered:
            self.post.lbl_files.setText(
                self.tr("Not found: ") + name + " — " +
                self.tr("try an MPC designation (2021EQ3), a comet (29P), "
                        "SN/AT (SN2023ixf), a planet (HD 209458 b) "
                        "or 'sun'"))
            return
        self.post.txt_es.setPlainText(rendered.get("es", ""))
        self.post.txt_en.setPlainText(rendered.get("en", ""))
        self.post.txt_tweet.setPlainText(rendered.get("tweet", ""))
        from ..core import post as post_mod
        written = post_mod.save_outputs(rendered, paths.data_dir() / "posts",
                                        name)
        db.mark_posted(name)
        self.post.lbl_files.setText(
            self.tr("Saved to: ") + ", ".join(str(p) for p in written.values()))
        self.statusBar().showMessage(self.tr("Drafts ready"), 5000)

    # ---------------- Solar ----------------

    # SDO channels in the combo box order (see solar_tab.ui)
    _SDO_CHANNELS = ["0193", "0304", "0171", "HMII", "HMIB"]

    def on_refresh_sun(self):
        self.solar.btn_refresh_sun.setEnabled(False)
        channel = self._SDO_CHANNELS[self.solar.cmb_channel.currentIndex()]
        w = SunWorker(channel)
        w.finished.connect(self._sun_done)
        self._keep(w)
        w.start()

    def _channel_changed(self):
        # Reloads the image in the newly selected SDO channel.
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
        # @args: img_path - local SDO JPEG
        from PySide6.QtGui import QPixmap
        pix = QPixmap(img_path)
        self.solar.lbl_sun_image.setPixmap(
            pix.scaled(420, 420, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _draw_sun_map(self, regions):
        # Our own active-region map as a small PNG next to the SDO image.
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
        # Moon phase + planets visible at dusk tonight.
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
        # planets above 15 deg at the start of darkness
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

    # ---------------- Blink ----------------

    def on_blink_browse(self):
        # Lets the user pick the plate-solved FITS from disk.
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Choose the plate-solved FITS image"), "",
            "FITS (*.fits *.fit *.fts);;All files (*)")
        if path:
            self.blink.edt_fits.setText(path)

    def _blink_manual_toggled(self, state):
        self.blink.edt_ra.setEnabled(bool(state))
        self.blink.edt_dec.setEnabled(bool(state))

    def _blink_manual_coords(self):
        # Manual RA/Dec from the text fields (locale-proof: dot or comma).
        # @return: (ra, dec) in degrees, or None if unchecked/invalid
        if not self.blink.chk_manual.isChecked():
            return None
        try:
            ra = float(self.blink.edt_ra.text().strip().replace(",", "."))
            dec = float(self.blink.edt_dec.text().strip().replace(",", "."))
        except ValueError:
            return None
        if not (0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0):
            return None
        return ra, dec

    def on_blink_prepare(self):
        # Starts the worker that resolves the SN and builds the aligned pair.
        image = self.blink.edt_fits.text().strip()
        if not image:
            self.blink.lbl_blink_status.setText(
                self.tr("Choose a FITS image first."))
            return
        name = self.blink.edt_sn_name.text().strip()
        ra = dec = None
        if self.blink.chk_manual.isChecked():
            manual = self._blink_manual_coords()
            if manual is None:
                self.blink.lbl_blink_status.setText(
                    self.tr("Manual coordinates invalid — use degrees, e.g. "
                            "187.7050 and +12.3910"))
                return
            ra, dec = manual
        elif not name:
            self.blink.lbl_blink_status.setText(
                self.tr("Type the supernova name (e.g. 2026ziz) or tick "
                        "'Manual coordinates'."))
            return
        self.blink.btn_prepare.setEnabled(False)
        self.blink.lbl_blink_status.setText(
            self.tr("Reading the FITS image…"))
        w = BlinkWorker(image, sn_name=name or None, ra=ra, dec=dec)
        w.progress.connect(lambda msg: self.blink.lbl_blink_status.setText(
            self._txt(msg)))
        w.finished.connect(self._blink_done)
        self._keep(w)
        w.start()

    def _blink_done(self, pair, errors):
        # Receives the aligned pair (or the bilingual error) from the worker.
        self.blink.btn_prepare.setEnabled(True)
        if errors:
            self.blink.lbl_blink_status.setText("⚠ " + self._txt(errors))
            return
        self._blink_pair = pair
        self._blink_nudge = [0.0, 0.0]
        self.blink.lbl_nudge.setText("(0.0, 0.0)")
        for wgt, val in ((self.blink.sld_black, 10), (self.blink.sld_white, 995),
                         (self.blink.sld_gamma, 100),
                         (self.blink.sld_balance, 100),
                         (self.blink.sld_marker, 10),
                         (self.blink.cmb_zoom, 0)):
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
        self.blink.lbl_blink_status.setText(status)
        self._blink_render()
        if self.blink.chk_blink_live.isChecked():
            self._blink_timer.start(self.blink.spn_interval.value())

    def _blink_auto_stretch(self):
        # Back to the robust default: 1%-99.5% percentiles, gamma 1.
        for sld, val in ((self.blink.sld_black, 10),
                         (self.blink.sld_white, 995),
                         (self.blink.sld_gamma, 100)):
            sld.setValue(val)
        self._blink_render()

    def _blink_shift_ref(self, ref8):
        # Applies the manual nudge to the survey frame only (PIL affine);
        # nudge is in screen coords: +dx right, +dy up.
        dx, dy = self._blink_nudge
        if dx == 0.0 and dy == 0.0:
            return ref8
        import numpy as np
        from PIL import Image
        im = Image.fromarray(ref8, mode="L")
        im = im.transform(im.size, Image.AFFINE, (1, 0, -dx, 0, 1, -dy),
                          fillcolor=0)
        return np.asarray(im)

    def _blink_render_soon(self, *_args):
        # Debounced render trigger for slider drags (120 ms coalescing).
        self._blink_render_timer.start()

    def _blink_render(self, *_args):
        # Recomputes stretches and refreshes the viewer (sliders, nudge).
        if not self._blink_pair:
            return
        import numpy as np
        from ..viz import blink_view
        b = self.blink
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
            self._blink_show(self._blink_pix[int(self._blink_phase)])
        else:
            self._blink_timer.stop()
            a = b.sld_fade.value() / 100.0
            mix = ((1.0 - a) * disp_ref + a * disp_obs).astype(np.uint8)
            self._blink_show(self._blink_pixmap(mix, sn_disp))

    def _blink_display_frames(self, zoom):
        # Display-oriented frames (north-up: FITS row 0 is the sky's south,
        # QImage row 0 is the top) cropped around the SN when zoomed in.
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
        # QImage needs a C-contiguous buffer (crops are views with strides)
        return (np.ascontiguousarray(disp_ref),
                np.ascontiguousarray(disp_obs), sn_disp)

    def _blink_interval_changed(self, ms):
        # Live-blink dwell time per frame, configurable (100-3000 ms).
        self._blink_timer.setInterval(int(ms))

    def _blink_balance_auto(self):
        # Sets the survey gain so both sky backgrounds match (median).
        if not self._blink_pair:
            return
        from ..viz import blink_view
        b = self.blink
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

    def _blink_pixmap(self, disp8, sn_disp):
        # QPixmap from a display-oriented (flipped/cropped) uint8 frame.
        # @args: disp8 - display frame, sn_disp - SN pixel in display coords
        from PySide6.QtGui import QImage, QPixmap
        h, w = disp8.shape
        img = QImage(disp8.data, w, h, w, QImage.Format_Grayscale8).copy()
        pix = QPixmap.fromImage(img)
        if self.blink.chk_marker.isChecked() and sn_disp is not None:
            if 0 <= sn_disp[0] < w and 0 <= sn_disp[1] < h:
                pix = self._blink_draw_marker(pix, sn_disp)
        return pix

    def _blink_draw_marker(self, pix, sn):
        # Orange crosshair + circle + label at the SN pixel (display coords).
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QColor, QPainter, QPen
        scale = self.blink.sld_marker.value() / 10.0
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
        self.blink.lbl_blink.setPixmap(
            pix.scaled(self.blink.lbl_blink.size(), Qt.KeepAspectRatio,
                       Qt.SmoothTransformation))

    def _blink_tick(self):
        # Live blink: alternate reference and observatory frames.
        if not self._blink_pair or not hasattr(self, "_blink_pix"):
            self._blink_timer.stop()
            return
        self._blink_phase = not self._blink_phase
        self._blink_show(self._blink_pix[int(self._blink_phase)])

    def _blink_live_toggled(self, *_args):
        if self._blink_pair and self.blink.chk_blink_live.isChecked():
            self._blink_timer.start(self.blink.spn_interval.value())
        else:
            self._blink_timer.stop()
        self._blink_render()

    def _blink_nudge_move(self, dx, dy):
        # Fine alignment of the survey frame, 0.5 px per click.
        if not self._blink_pair:
            return
        self._blink_nudge[0] += dx
        self._blink_nudge[1] += dy
        self.blink.lbl_nudge.setText(
            f"({self._blink_nudge[0]:+.1f}, {self._blink_nudge[1]:+.1f})")
        self._blink_render()

    def _blink_export(self, kind):
        # Shared export flow: ask for a path, then render in a worker so the
        # GUI never freezes while matplotlib builds the frames.
        if not self._blink_pair or self._blink_ref8 is None:
            return
        from PySide6.QtWidgets import QFileDialog
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
                str(outdir / f"{pair['name']}_blink.mp4"), "MP4 video (*.mp4)")
        else:
            out, _ = QFileDialog.getSaveFileName(
                self, self.tr("Export side-by-side PNG"),
                str(outdir / f"{pair['name']}_before_after.png"),
                "PNG (*.png)")
        if not out:
            return
        effect = "blink" if self.blink.rdo_blink.isChecked() else "fade"
        sn = pair["sn_xy"] if self.blink.chk_marker.isChecked() else None
        self.blink.lbl_blink_status.setText(
            self.tr("Rendering %1…").replace("%1", kind.upper()))
        w = BlinkExportWorker(
            kind, self._blink_ref8, self._blink_obs8, sn, out, effect=effect,
            name=pair["name"], ref_label=pair["ref_label"],
            lang=self._lang(),
            observatory=config.get("observatory_name", ""),
            zoom=(1, 2, 4)[self.blink.cmb_zoom.currentIndex()],
            marker_scale=self.blink.sld_marker.value() / 10.0,
            interval_ms=self.blink.spn_interval.value())
        w.finished.connect(self._blink_export_done)
        self._keep(w)
        w.start()

    def _blink_export_done(self, out, error):
        if error or not out:
            self.blink.lbl_blink_status.setText(
                self.tr("Export failed: %1").replace("%1", error))
            return
        self.blink.lbl_blink_status.setText(
            self.tr("Written to %1").replace("%1", out))

    def on_blink_export_gif(self):
        # Exports the animated GIF with the current stretch and nudge.
        self._blink_export("gif")

    def on_blink_export_video(self):
        # Exports the same animation as H.264 MP4 (for sites that reject GIFs).
        self._blink_export("video")

    def on_blink_export_png(self):
        # Exports the side-by-side before/after PNG for posts (ADR-016).
        self._blink_export("png")

    # ---------------- housekeeping ----------------

    def _keep(self, worker):
        # Keeps a reference to a running worker so Qt does not GC it, and
        # releases it *safely*: deleteLater runs in the event loop, after the
        # finished signal has been fully delivered.
        from PySide6.QtCore import QTimer
        self._workers.append(worker)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(
            lambda *a: QTimer.singleShot(0, lambda: self._drop(worker)))

    def _drop(self, worker):
        if worker in self._workers:
            self._workers.remove(worker)
