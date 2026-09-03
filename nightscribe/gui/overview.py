############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - shared object overview panel module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

# The object's «business card» as one reusable panel (phase D,
# docs/WORKFLOWS.es.md §7ter): hook phrase, fact bullets, the
# parameters table with a wide, multi-line explanation column and a
# charts row (D2) rendered by core.post.build_charts. A slot that
# build_charts cannot produce is hidden (the «omit what is missing»
# rule); when no chart can be made, the whole charts group disappears
# instead of leaving a grid of «why not» lines.
#
# The orbit and sky slots are live vector widgets (OrbitChart / SkyChart,
# ADR-029 Fase 2-3) that the user can zoom, pan and hover. The transit
# (light curve) and field (cutout) slots have no vector widget yet and
# keep the QLabel+QPixmap route. Clicking any slot opens the same
# ChartViewer dialog (widget mode or pixmap mode).

import datetime

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QGroupBox,
                                QHBoxLayout, QLabel, QHeaderView, QPushButton,
                                QSizePolicy, QTableWidget, QTableWidgetItem,
                                QVBoxLayout, QWidget)

from ..core import exposure, narrative, orbits
from .. import paths
from . import theme

# Viewer / slot titles, translated at the point of use.
_TITLE = {"orbit": "Orbit", "sky": "Sky tonight",
          "field": "Reference field", "transit": "Light curve"}

# Grid order, left to right; the ones build_charts actually produced are
# laid out in this order (the rest stay hidden).
_CHART_SLOTS = ("orbit", "sky", "field", "transit")

# Slots that get a live vector widget (OrbitChart / SkyChart); the rest
# keep the QLabel+QPixmap route (light curve / cutout have no widget yet).
_VECTOR_SLOTS = frozenset({"orbit", "sky"})

# The re-render mode (Settings > Charts) draws 2× the panel preset.
_RENDER2X = (2400, 1350)


def _chip(text, color, tip=""):
    # @return: a small pill label, the same idiom the Tonight rows use
    lbl = QLabel(text)
    lbl.setStyleSheet(theme.chip_style(color))
    if tip:
        lbl.setToolTip(tip)
    return lbl


# Resizes `parent` so the `panel` fits its content (with a minimum
# size floor). Used by the Explore dialog and tested in isolation.
# @args: parent - the container widget (e.g. an Explora QDialog)
#        panel  - the ObjectPanel whose sizeHint sets the new size
def resize_to_panel_content(parent, panel):
    hint = panel.sizeHint()
    w = max(int(hint.width()),  420)
    h = max(int(hint.height()), 320)
    parent.resize(w, h)


class _SlotClick(QObject):
    # Opens the zoom/export viewer when a chart slot is released.
    # Vector slots rebuild a fresh widget; PNG slots copy the file.

    def __init__(self, panel):
        super().__init__()
        self._panel = panel

    def eventFilter(self, obj, event):
        if event.type() != QEvent.MouseButtonRelease:
            return False
        key = obj.property("chart_key")
        if not key:
            return False
        p = self._panel
        title = p._slot_titles.get(key, "")
        if key in _VECTOR_SLOTS:
            data = p._slot_data.get(key)
            if data is None:
                return False
            rebuilt = p._rebuild_widget(key, data)
            if rebuilt:
                from .chart_viewer import open_chart_widget
                open_chart_widget(p, rebuilt, title=title)
                return True
        else:
            png = obj.property("chart_png")
            if not png:
                return False
            from .chart_viewer import open_chart
            open_chart(p, png, title=title)
            return True
        return False


class ObjectPanel(QWidget):
    # Fixed panel describing the project's object. Three states:
    #   loading — a worker is still out there
    #   missing — the loader came back empty
    #   ready   — hook + bullets + parameters table
    #
    # Charts (D2): orbit and sky are live vector widgets (ADR-029);
    # transit and field keep QLabel+QPixmap. Clicking any of them opens
    # ChartViewer in the matching mode.
    #
    # Single CTA at the bottom of the panel (Phase E, corrected
    # 2026-09-02, docs/WORKFLOWS.es.md §7ses).
    project_create = Signal(str, object)
    project_continue = Signal(str, object)
    # Fires once the enriched dict is on screen. A parent (e.g. the
    # Explore dialog) can use this to resize itself to the panel's
    # content — the panel's sizeHint is only meaningful here.
    ready = Signal(dict)

    def __init__(self, loader=None, chart_dir=None, for_post=False,
                 project_lookup=None, parent=None):
        # @args: loader - callable(name, fallback_target) returning a
        #                     QThread-like worker with finished=Signal(dict)
        #         chart_dir - directory where the PNG charts are written;
        #         for_post  - the Explore-dialog flavour (Phase E)
        #         project_lookup - optional callable(name) -> dict-or-None
        #        parent - parent widget
        super().__init__(parent)
        self._loader = loader or self._default_loader
        self._chart_dir = chart_dir
        self._worker = None
        self._slot = None
        self._ctx = None
        self._rows = []
        self._state = "empty"
        self._name = None
        self._fallback = None
        self._for_post = for_post
        self._project_lookup = project_lookup

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._e = None          # last enriched dict (re-render on mode change)

        # state line (loading / not found); hidden when ready
        self.lbl_state = QLabel()
        self.lbl_state.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        self.lbl_state.hide()
        layout.addWidget(self.lbl_state)

        self.lbl_hook = QLabel()
        self.lbl_hook.setWordWrap(True)
        self.lbl_hook.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.lbl_hook.hide()
        layout.addWidget(self.lbl_hook)

        self.lbl_facts = QLabel()
        self.lbl_facts.setWordWrap(True)
        self.lbl_facts.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        self.lbl_facts.hide()
        layout.addWidget(self.lbl_facts)

        # capture/window block (D3)
        self.row_capture = QFrame()
        self.row_capture.setStyleSheet(
            f"background: {theme.C_BASE}; border-radius: 8px;"
            f" border: 1px solid {theme.C_LINE};")
        self._chips = QHBoxLayout(self.row_capture)
        self._chips.setContentsMargins(10, 6, 10, 6)
        self._chips.setSpacing(8)
        self._chips.addStretch(1)
        self.row_capture.hide()
        layout.addWidget(self.row_capture)

        # parameters table
        self.grp_params = QGroupBox(self.tr("Parameters"))
        gl = QVBoxLayout(self.grp_params)
        top = QHBoxLayout()
        self.chk_deep = QCheckBox(self.tr("In depth"))
        self.chk_deep.toggled.connect(lambda: self._refill_params())
        top.addWidget(self.chk_deep)
        top.addStretch(1)
        gl.addLayout(top)

        tbl = QTableWidget(0, 3)
        self.tbl_params = tbl
        tbl.setHorizontalHeaderLabels(
            [self.tr("Parameter"), self.tr("Value"), self.tr("What it means")])
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setSelectionMode(QTableWidget.SingleSelection)
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        gl.addWidget(tbl)
        self.grp_params.hide()
        layout.addWidget(self.grp_params)

        # charts 2×2 (D2): orbit/sky are vector widgets; field/transit are
        # QLabel+QPixmap. The grid is filled in _render_charts and emptied
        # by _empty_grid (state transitions: ready -> blank -> ready).
        self.grp_charts = QGroupBox(self.tr("Charts"))
        self._grid = QGridLayout(self.grp_charts)
        self._grid.setSpacing(8)
        self._slot_data = {}    # key -> data dict (for rebuild on click)
        self._slot_titles = {}  # key -> translated title (for the viewer)
        self._slot_click = _SlotClick(self)
        self.grp_charts.hide()
        layout.addWidget(self.grp_charts)

        # single CTA at the very bottom
        self.btn_project = QPushButton(self.tr("Create project"))
        self.btn_project.setCursor(Qt.PointingHandCursor)
        self.btn_project.setMinimumHeight(46)
        self.btn_project.setSizePolicy(QSizePolicy.Expanding,
                                       QSizePolicy.Fixed)
        self._action = "create"
        self.btn_project.clicked.connect(self._cta_clicked)
        self.btn_project.hide()
        layout.addSpacing(6)
        layout.addWidget(self.btn_project)

    # ---------------- states ----------------

    def state(self):
        # @return: "empty" | "loading" | "missing" | "ready"
        return self._state

    def _state_loading(self, name=None):
        # @args: name - identifier being fetched
        self._state = "loading"
        self._name = name
        self.lbl_state.setText(self.tr("Loading…"))
        self.lbl_state.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        self.lbl_state.show()
        self.lbl_hook.hide()
        self.lbl_facts.hide()
        self.row_capture.hide()
        self.grp_params.hide()
        self.grp_charts.hide()
        self.btn_project.hide()

    def _state_missing(self, name=None):
        # @args: name - identifier, shown when given
        self._state = "missing"
        self._name = name or getattr(self, "_name", None)
        self.lbl_state.setText(self.tr("Not found: %1").replace(
            "%1", self._name or self.tr("the requested object")))
        self.lbl_state.setStyleSheet(f"color: {theme.C_WARN};")
        self.lbl_state.show()
        self.lbl_hook.hide()
        self.lbl_facts.hide()
        self.row_capture.hide()
        self.grp_params.hide()
        self.grp_charts.hide()
        self._refresh_cta()

    def _state_ready(self, e):
        # @args: e - enriched dict from enrich.enrich()
        self._e = e
        self.lbl_state.hide()
        hook = self._txt(narrative.hook(e))
        self.lbl_hook.setText(hook)
        self.lbl_hook.show()

        bullets = [b for b in (narrative.fact_bullets(e) or []) if self._txt(b)]
        if bullets:
            self.lbl_facts.setText(
                "\n".join("•  " + self._txt(b) for b in bullets))
            self.lbl_facts.show()
        else:
            self.lbl_facts.hide()

        self._rows = self._orbit_rows(e)
        self.grp_params.setVisible(bool(self._rows))
        self._refill_params()
        self._render_charts(e)
        self._render_capture(e)
        self._refresh_cta()
        self._state = "ready"
        # The charts (and the CTA) are now on screen; let the owner
        # (e.g. the Explore dialog) fit itself to the content.
        self.ready.emit(e)

    # ---------------- public API ----------------

    def name(self):
        # @return: the identifier this panel is showing
        return self._name

    def _cta_clicked(self):
        # @return: fires the matching signal.
        if self._worker is not None:
            return
        if self._name is None or not self._for_post:
            return
        if self._action == "continue":
            self.project_continue.emit(self._name, self._fallback)
        else:
            self.project_create.emit(self._name, self._fallback)

    def _refresh_cta(self):
        # Gives the CTA its face or leaves it hidden.
        if not self._for_post or self._project_lookup is None \
                or self._name is None:
            self.btn_project.hide()
            return
        try:
            active = self._project_lookup(self._name)
        except Exception:
            active = None
        if active is not None:
            self._action = "continue"
            self.btn_project.setText(
                "\u25b6  " + self.tr("Continue project"))
            self.btn_project.setToolTip(self.tr(
                "Resume the active project for this object"))
            self.btn_project.setStyleSheet(
                "QPushButton { background: #2a7a3a; color: #e8eaf2;"
                " border: none; border-radius: 6px; font-size: 15px;"
                " font-weight: bold; }"
                "QPushButton:hover { background: #3a9a4a; }"
                "QPushButton:pressed { background: #236733; }")
        else:
            self._action = "create"
            self.btn_project.setText(
                "\U0001f680  " + self.tr("Create project"))
            self.btn_project.setToolTip(self.tr(
                "Start a new project for this object"))
            self.btn_project.setStyleSheet(
                "QPushButton { background: #b45309; color: #ffffff;"
                " border: none; border-radius: 6px; font-size: 15px;"
                " font-weight: bold; }"
                "QPushButton:hover { background: #d97706; }"
                "QPushButton:pressed { background: #92400e; }")
        self.btn_project.show()

    def show(self, e, ctx=None):
        # Renders the ready state from an enriched dict.
        # @args: e - dict from enrich.enrich() (or {} when nothing was found)
        #        ctx - project context snapshot
        self._ctx = ctx
        if not e or not e.get("data"):
            self._state_missing()
            return
        if self._name is None and e.get("name"):
            self._name = str(e["name"])
        self._state_ready(e)

    def explore(self, name, fallback_target=None, ctx=None):
        # Kicks off the injected loader; the panel renders whatever lands.
        if self._worker is not None:
            return
        self._name = name
        self._fallback = fallback_target
        self._ctx = ctx
        self._state_loading(name)
        worker = self._loader(name, fallback_target)
        self._worker = worker
        self._slot = lambda e, w=worker: self._worker_done(w, e)
        worker.finished.connect(self._slot)
        worker.start()

    def cancel(self):
        # Drops a running worker so its result can never land on this panel.
        worker, slot = self._worker, self._slot
        self._worker = None
        self._slot = None
        if worker is not None and slot is not None:
            try:
                worker.finished.disconnect(slot)
            except RuntimeError:
                pass
        self._blank()

    def _blank(self):
        # Puts the panel back to the pre-load state.
        self._state = "empty"
        self._ctx = None
        self._e = None
        self._rows = []
        self._name = None
        self._fallback = None
        self._clear_chips()
        self._empty_grid()
        self.lbl_state.hide()
        self.lbl_hook.hide()
        self.lbl_facts.hide()
        self.row_capture.hide()
        self.grp_params.hide()
        self.grp_charts.hide()
        self.btn_project.hide()

    def _worker_done(self, w, e):
        # @args: w - the worker that finished, e - its enriched payload
        if w is not self._worker:
            return
        slot = self._slot
        self._worker = None
        self._slot = None
        self.show(e, self._ctx)
        if slot is not None:
            try:
                w.finished.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    # ---------------- internals ----------------

    @staticmethod
    def _default_loader(name, fallback_target=None):
        # @args: name - object identifier, fallback_target - planner target
        # @return: a not-yet-started ExploreWorker
        from ..config import config
        from .workers import ExploreWorker
        return ExploreWorker(config, name, fallback_target=fallback_target)

    def _lang(self):
        # @return: "es" or "en"
        from PySide6.QtCore import QLocale
        from ..config import config
        lang = config.get("language", "system")
        if lang == "system":
            lang = QLocale.system().name()[:2]
        return lang if lang in ("es", "en") else "en"

    def _txt(self, pair):
        # @args: pair - {"es","en"} dict
        # @return: the string in the active language
        return orbits.pick(pair, self._lang())

    def _orbit_rows(self, e):
        # @args: e - enriched dict
        # @return: list of {"param","value","level","es","en"} rows
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
                                           d.get("family"), moid,
                                           sigmas=sb.get("sigmas"),
                                           n_resids=sb.get("n_resids"),
                                           arc_days=sb.get("arc_days"))
        if d.get("unconfirmed"):
            return orbits.explain_neofixer(d["unconfirmed"])
        return []

    # ---------------- charts (D2, ADR-029) ----------------
    #
    # orbit / sky  — live vector widgets (OrbitChart / SkyChart).
    # field/transit — QLabel+QPixmap (no vector widget for cutout/light curve).
    # build_charts still runs (core/post.py unchanged); for the vector
    # slots it only acts as a "can I make this chart?" gate.

    def _render_charts(self, e):
        # Builds the 2×2 charts grid for this object.
        # @args: e - enriched dict
        from ..core import post
        outdir = self._chart_dir or paths.data_dir() / "posts"
        size = _RENDER2X if self._chart_zoom() == "re-render" else None
        try:
            charts = post.build_charts(e, outdir, "_overview_",
                                       cfg=self._chart_cfg(), fmt="panel",
                                       size=size)
        except Exception:
            charts = {}

        # Start from an empty grid (the panel can re-render on a new
        # object or after a resolution-mode change).
        self._empty_grid()

        for key in _CHART_SLOTS:
            chart = charts.get(key)
            if not chart:
                continue  # omit what is missing
            self._slot_titles[key] = self.tr(_TITLE[key])
            if key in _VECTOR_SLOTS:
                w = self._make_vector(key, e)
                if w is not None:
                    row, col = self._slot_rowcol(key)
                    w.setProperty("chart_key", key)
                    w.setCursor(Qt.PointingHandCursor)
                    w.installEventFilter(self._slot_click)
                    self._slot_data[key] = self._extract(key, e)
                    self._grid.addWidget(w, row, col)
            else:
                self._place_png(key, chart)

        self.grp_charts.setVisible(bool(charts))

    def _slot_rowcol(self, key):
        # @return: (row, col) of the slot in the 2×2 grid
        idx = _CHART_SLOTS.index(key)
        return (idx // 2, idx % 2)

    def _empty_grid(self):
        # Removes every widget from the 2×2 chart grid and clears slot state.
        gl = self._grid
        while gl.count():
            item = gl.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._slot_data.clear()
        self._slot_titles.clear()

    def _place_png(self, key, png_path):
        # Loads a chart PNG into a QLabel and places it in the grid.
        # @args: key - slot name, png_path - Path from build_charts
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setMinimumHeight(220)
        pix = QPixmap(str(png_path))
        if not pix.isNull():
            lbl.setPixmap(pix)
        lbl.setProperty("chart_key", key)
        lbl.setProperty("chart_png", str(png_path))
        lbl.setCursor(Qt.PointingHandCursor)
        lbl.setToolTip(self.tr("Click to zoom / export"))
        lbl.installEventFilter(self._slot_click)
        row, col = self._slot_rowcol(key)
        self._grid.addWidget(lbl, row, col)

    def _make_vector(self, key, e):
        # Builds the appropriate live chart widget for this slot.
        # @args: key - "orbit" | "sky", e - enriched dict
        # @return: a fully configured widget, or None when not possible
        if key == "orbit":
            from ..core import coords
            d = e.get("data") or {}
            sb = d.get("sbdb")
            els = (sb or {}).get("elements")
            if not els or not els.get("q") or (els.get("e", 1) or 1) > 1.0:
                return None
            jd = coords.jd_from_datetime(
                datetime.datetime.now(datetime.timezone.utc))
            from .widgets.orbit_widget import OrbitChart
            w = OrbitChart()
            w.set_elements(els, jd, e.get("name", ""))
            return w
        elif key == "sky":
            data = self._extract("sky", e)
            if data is None or data.get("ra") is None \
                    or data.get("lat") is None:
                return None
            from .widgets.sky_widget import SkyChart
            w = SkyChart()
            w.set_target(
                data["ra"], data["dec"], data["lat"], data["lon"],
                datetime.date.today(),
                obj_name=data.get("name", ""),
                safe_window=data.get("safe_window"),
                best_time=data.get("best_time"),
                horizon=data.get("horizon"),
                transit=data.get("transit"),
                margin=data.get("margin", 0.0))
            return w
        return None

    def _extract(self, key, e):
        # Extracts the data needed to rebuild a fresh widget on click.
        # @args: key - slot name, e - enriched dict
        # @return: a dict suitable for _rebuild_widget, or None
        from ..core import coords
        d = e.get("data") or {}

        if key == "orbit":
            sb = d.get("sbdb")
            els = (sb or {}).get("elements")
            if not els:
                return None
            jd = coords.jd_from_datetime(
                datetime.datetime.now(datetime.timezone.utc))
            return {"elements": els, "jd": jd, "name": e.get("name", "")}

        elif key == "sky":
            ra = dec = None
            eph = d.get("ephem")
            if eph:
                try:
                    ra = coords.ra_hms_to_deg(eph["ra"])
                    dec = coords.dec_dms_to_deg(eph["dec"])
                except (ValueError, AttributeError):
                    pass
            sim = d.get("simbad")
            if sim and ra is None:
                try:
                    ra = coords.ra_hms_to_deg(sim["ra"])
                    dec = coords.dec_dms_to_deg(sim["dec"])
                except (ValueError, AttributeError):
                    pass
            unc = d.get("unconfirmed")
            if ra is None and unc and unc.get("ra_deg") is not None:
                ra = float(unc["ra_deg"])
                dec = float(unc.get("dec_deg", 0.0))
            if ra is None and d.get("ra_deg") is not None:
                ra = float(d["ra_deg"])
                dec = float(d.get("dec_deg", 0.0))

            from ..config import config
            lat = config.get("lat")
            lon = config.get("lon")

            # horizon callable (ADR-020)
            horizon = None
            try:
                from ..core import horizon as _hor
                hor_obj = _hor.from_config(config)
                horizon = hor_obj.alt_at if hor_obj else None
            except Exception:
                horizon = None

            # safe window / best time (same source logic as post.py)
            src = d if d.get("safe_window") else (unc or {})
            sw = best = None
            raw = src.get("safe_window")
            if raw:
                s0, s1 = raw.split("|")
                sw = (datetime.datetime.fromisoformat(s0),
                      datetime.datetime.fromisoformat(s1))
            raw = src.get("best_time")
            if raw:
                best = datetime.datetime.fromisoformat(raw)

            margin = float(config.get("horizon_margin_deg", 0))
            tr = d.get("transit") or (unc or {}).get("transit")

            return {
                "ra": ra, "dec": dec, "lat": lat, "lon": lon,
                "name": e.get("name", ""),
                "horizon": horizon,
                "safe_window": sw, "best_time": best,
                "margin": margin, "transit": tr,
            }

        return None

    def _rebuild_widget(self, key, data):
        # Builds a fresh chart widget for the ChartViewer dialog.
        # @args: key - slot name, data - dict from _extract
        # @return: a fully configured widget
        if key == "orbit":
            from .widgets.orbit_widget import OrbitChart
            w = OrbitChart()
            w.set_elements(data["elements"], data["jd"],
                           data.get("name", ""))
            return w
        elif key == "sky":
            from .widgets.sky_widget import SkyChart
            w = SkyChart()
            w.set_target(
                data["ra"], data["dec"], data["lat"], data["lon"],
                datetime.date.today(),
                obj_name=data.get("name", ""),
                safe_window=data.get("safe_window"),
                best_time=data.get("best_time"),
                horizon=data.get("horizon"),
                transit=data.get("transit"),
                margin=data.get("margin", 0.0))
            return w
        return None

    def rebuild_charts(self):
        # Re-draws the charts with the active resolution mode.
        if self._e is None:
            return
        self._render_charts(self._e)

    def _chart_zoom(self):
        # @return: "scale" | "re-render" (config, default "scale")
        from ..config import config
        return config.get("chart_zoom", "scale")

    def _chart_cfg(self):
        # @return: the active Config
        from ..config import config
        return config

    # ---------------- capture / window block (D3) ----------------

    def _clear_chips(self):
        # Drops every chip the block currently shows.
        lay = self._chips
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _capture_chips(self, e):
        # Builds the chip definitions for this object.
        # @args: e - enriched dict
        chips = []
        ctx = self._ctx or self._fallback or {}
        kind = ctx.get("kind") or e.get("type")

        mag = ctx.get("mag")
        if mag is not None:
            try:
                mag = float(mag)
            except (TypeError, ValueError):
                mag = None
        if mag is not None:
            chips.append((
                f"{self.tr('Mag')} {mag:.1f}", theme.C_OK,
                self.tr("Predicted apparent magnitude tonight")))

        rate = None
        if kind in ("neo", "pccp") and ctx.get("rate_arcsec_min"):
            try:
                rate = float(ctx["rate_arcsec_min"])
            except (TypeError, ValueError):
                rate = None
        if rate:
            chips.append((
                f"{rate:.1f}″/min", theme.C_TEXT,
                self.tr("Sky rate tonight — it must outrun the stars")))
            from ..config import config
            scale = exposure.plate_scale(config.get("pixel_um"),
                                         config.get("focal_mm"))
            t_max = exposure.max_exposure_no_trail(rate, scale)
            if t_max:
                chips.append((
                    f"⚠ {self.tr('max')} {t_max:.0f}s", theme.C_WARN,
                    str(self.tr("Longest single exposure before the "
                                "target trails more than a pixel"))
                ))

        ws = ctx.get("window_start")
        we = ctx.get("window_end")
        if ws and we:
            ws_hm = ws[11:16]
            we_hm = we[11:16]
            chips.append((
                f"{ws_hm}–{we_hm}", theme.C_OK,
                self.tr("Times the object is safely above the limit")))
            hours = ctx.get("hours_up")
            if hours:
                try:
                    hours = float(hours)
                except (TypeError, ValueError):
                    hours = None
                if hours:
                    chips.append((
                        f"{hours:.1f} h", theme.C_TEXT,
                        self.tr("How long it stays a valid target")))

        if ctx.get("safe_window"):
            s0, s1 = ctx["safe_window"].split("|")
            s0h, s1h = s0[11:16], s1[11:16]
            bt = ctx.get("best_time")
            bt_hm = bt[11:16] if bt else None
            hint = self.tr("The capture window that still clears your "
                           "local limit — the telescope stays in safe "
                           "altitude through the whole session")
            if bt_hm:
                label = f"⊕ {s0h}–{s1h} · ≤ {bt_hm}"
                hint += self.tr(" · ≤ HH:MM is the latest safe start")
            else:
                label = f"⊕ {s0h}–{s1h}"
            chips.append((label, theme.C_GOOD, hint))
        elif (ctx.get("duration_s") and ctx.get("window_start")
                and ctx.get("window_end")):
            mins = int(round(int(ctx.get("duration_s", 0)) / 60))
            chips.append((
                f"⚠ {self.tr('does not fit')} · {mins} min",
                theme.C_WARN,
                self.tr("The planned {0} min session does not fit in the "
                        "time the object is above your local limit. "
                        "Do NOT force the instrument.").format(mins)))
        return chips

    def _render_capture(self, e):
        # Shows the block when it has at least one chip.
        # @args: e - enriched dict
        self._clear_chips()
        chips = self._capture_chips(e)
        if not chips:
            self.row_capture.hide()
            return
        for text, color, tip in chips:
            self._chips.insertWidget(self._chips.count() - 1,
                                     _chip(text, color, tip))
        self.row_capture.show()

    def _refill_params(self):
        # Fills the parameters table from the cached rows.
        rows = list(self._rows)
        if not self.chk_deep.isChecked():
            rows = [r for r in rows if r.get("level") == "basic"]
        tbl = self.tbl_params
        tbl.setRowCount(0)
        for r in rows:
            row = tbl.rowCount()
            tbl.insertRow(row)
            param = self._txt(r["param"]) if isinstance(r["param"], dict) \
                else str(r["param"])
            tbl.setItem(row, 0, QTableWidgetItem(param))
            tbl.setItem(row, 1, QTableWidgetItem(str(r["value"])))
            tbl.setItem(row, 2, QTableWidgetItem(self._txt(r)))
