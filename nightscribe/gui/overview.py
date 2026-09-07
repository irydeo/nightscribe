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
# docs/WORKFLOWS.es.md §7ter): hook phrase, a coordinates block with
# copyable RA/Dec (decimal + sexagesimal, object-card plan subplan 0),
# fact bullets, the parameters table with a wide, multi-line
# explanation column and a charts group (D2) rendered by
# core.post.build_charts. A slot that build_charts cannot produce is
# hidden (the «omit what is missing» rule); when no chart can be made,
# the whole charts group disappears instead of leaving a grid of
# «why not» lines.
#
# The charts group shows every produced chart on its OWN TAB (each tab
# carries the chart's title, e.g. "Orbit", "Sky tonight"): with a single
# chart the tab bar auto-hides and the chart stands alone; with several
# they group side by side behind tabs. The orbit, sky and approach slots
# are live vector widgets (OrbitChart / SkyChart / ApproachChart,
# ADR-029 Fase 2-3) that the user can zoom, pan and hover. The transit
# (light curve) and field (cutout) slots have no vector widget yet and
# keep the QLabel+QPixmap route. Clicking any slot opens the same
# ChartViewer dialog (widget mode or pixmap mode).

import datetime

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QFrame, QGroupBox,
                                QHBoxLayout, QLabel, QHeaderView, QPushButton,
                                QSizePolicy, QTabWidget, QTableWidget,
                                QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import exposure, narrative, orbits
from .. import paths
from . import theme

# Viewer / slot titles, translated at the point of use.
_TITLE = {"orbit": "Orbit", "sky": "Sky tonight",
          "approach": "Approach",
          "field": "Reference field", "transit": "Light curve"}

# Grid order, left to right; the ones build_charts actually produced are
# laid out in this order (the rest stay hidden).
_CHART_SLOTS = ("orbit", "sky", "approach", "field", "transit")

# Slots that get a live vector widget (OrbitChart / SkyChart /
# ApproachChart); the rest keep the QLabel+QPixmap route (light curve
# / cutout have no widget yet).
_VECTOR_SLOTS = frozenset({"orbit", "sky", "approach"})


def _chip(text, color, tip=""):
    # @return: a small pill label, the same idiom the Tonight rows use
    lbl = QLabel(text)
    lbl.setStyleSheet(theme.chip_style(color))
    if tip:
        lbl.setToolTip(tip)
    return lbl


# Reading-size floors for the Explore dialog (resize_to_panel_content):
# wide enough that the hook line and the "What it means" column read
# comfortably; tall enough that the CTA button at the panel's foot never
# hides under the scroll area. The height gets an extra delta because
# resize() sizes the WHOLE window (title bar + frame + layout margins),
# so the panel's full height needs a little headroom to fit without a
# vertical scrollbar.
_MIN_READ_W = 780     # comfortable reading width (px)
_MIN_READ_H = 640     # minimum usable height (px)
_DLG_CHROME = 60      # title bar / frame / margins headroom (px)


# Width cap for the Parameter/Value columns (object-card plan, subplan
# 1): without it a long value steals the room the multi-line
# "What it means" column needs.
_PARAM_COL_MAX_W = 280


# Resizes `parent` so the `panel` fits its content, keeping it wide and
# tall enough to read and to show the whole panel (CTA included). Used by
# the Explore dialog and tested in isolation.
# @args: parent - the container widget (e.g. an Explora QDialog)
#        panel  - the ObjectPanel whose sizeHint sets the new size
def resize_to_panel_content(parent, panel):
    hint = panel.sizeHint()
    w = max(int(hint.width()), _MIN_READ_W)
    h = max(int(hint.height()) + _DLG_CHROME, _MIN_READ_H)
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
        obj_name = p._name or ""
        if key in _VECTOR_SLOTS:
            data = p._slot_data.get(key)
            if data is None:
                return False
            rebuilt = p._rebuild_widget(key, data)
            if rebuilt:
                from .chart_viewer import open_chart_widget
                open_chart_widget(p, rebuilt, title=title,
                                  obj_name=obj_name, chart_key=key)
                return True
        else:
            png = obj.property("chart_png")
            if not png:
                return False
            from .chart_viewer import open_chart
            open_chart(p, png, title=title, obj_name=obj_name,
                       chart_key=key)
            return True
        return False


class ObjectPanel(QWidget):
    # Fixed panel describing the project's object. Three states:
    #   loading — a worker is still out there
    #   missing — the loader came back empty
    #   ready   — hook + bullets + parameters table
    #
    # Charts (D2): one tab per produced chart — orbit/sky/approach are
    # live vector widgets (ADR-029), transit/field keep QLabel+QPixmap;
    # a single chart hides the tab bar. Clicking any of them opens
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

        # coordinates block (object-card plan, subplan 0): RA/Dec in
        # decimal AND sexagesimal, with a one-click copy button. Hidden
        # for objects without a known position (e.g. ESA alerts).
        self.row_coords = QFrame()
        self.row_coords.setStyleSheet(
            f"background: {theme.C_BASE}; border-radius: 8px;"
            f" border: 1px solid {theme.C_LINE};")
        co_lay = QHBoxLayout(self.row_coords)
        co_lay.setContentsMargins(10, 6, 10, 6)
        self.lbl_coords = QLabel()
        self.lbl_coords.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_coords.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        co_lay.addWidget(self.lbl_coords, 1)
        self.btn_copy_coords = QPushButton("⧉  " + self.tr("Copy"))
        self.btn_copy_coords.setCursor(Qt.PointingHandCursor)
        self.btn_copy_coords.setToolTip(self.tr(
            "Copy the coordinates (decimal and sexagesimal)"))
        self.btn_copy_coords.setStyleSheet(
            f"QPushButton {{ color: {theme.C_TEXT_DIM};"
            f" background: transparent; border: 1px solid {theme.C_LINE};"
            f" border-radius: 4px; padding: 2px 10px; }}"
            f"QPushButton:hover {{ color: {theme.C_TEXT}; }}")
        self.btn_copy_coords.clicked.connect(self._copy_coords)
        co_lay.addWidget(self.btn_copy_coords)
        self.row_coords.hide()
        layout.addWidget(self.row_coords)
        self._coords_clip = ""

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
        # multi-line cells (object-card plan, subplan 1): the explanation
        # wraps and the row grows — no more vertically clipped text
        tbl.setWordWrap(True)
        hdr = tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        # multi-line rows must follow the stretch column when the window
        # resizes: re-fit them every time the explanation column changes
        # width (the header stretches AFTER the viewport's Resize event,
        # so watching the section itself is the reliable hook)
        self._rows_busy = False
        hdr.sectionResized.connect(self._param_section_resized)
        tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        gl.addWidget(tbl)
        self.grp_params.hide()
        layout.addWidget(self.grp_params)

        # charts tabs (D2): each produced chart gets its own tab labelled
        # with the chart's title; with a single chart the tab bar hides and
        # the chart stands alone. orbit/sky/approach are vector widgets;
        # field/transit are QLabel+QPixmap. The tabs are (re)filled in
        # _render_charts and emptied by _empty_tabs (state transitions:
        # ready -> blank -> ready).
        self.grp_charts = QGroupBox(self.tr("Charts"))
        self._tabs = QTabWidget(self.grp_charts)
        self._tabs.setTabBarAutoHide(True)
        self._tabs.setDocumentMode(True)
        # a sane floor so the auto-fit dialog does not collapse a chart
        self._tabs.setMinimumSize(480, 340)
        lay = QVBoxLayout(self.grp_charts)
        lay.setContentsMargins(6, 4, 6, 6)
        lay.addWidget(self._tabs)
        self._slot_data = {}    # key -> data dict (for rebuild on click)
        self._slot_titles = {}  # key -> translated title (for tabs + viewer)
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
        self.row_coords.hide()
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
        self.row_coords.hide()
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

        ra, dec = self._coords_from(e)
        if ra is not None and dec is not None:
            self._show_coords(ra, dec)
        else:
            self.row_coords.hide()
            self._coords_clip = ""

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
        self._empty_tabs()
        self.lbl_state.hide()
        self.lbl_hook.hide()
        self.lbl_facts.hide()
        self.row_coords.hide()
        self._coords_clip = ""
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

    # ---------------- coordinates block (object-card plan, subplan 0) --

    @staticmethod
    def _coords_from(e):
        # Resolves the object's sky position trying the same source chain
        # the sky chart uses: ephemeris, SIMBAD, NEOfixer unconfirmed,
        # planner degrees, exoplanet archive degrees.
        # @args: e - enriched dict
        # @return: (ra_deg, dec_deg) floats, or (None, None) when unknown
        from ..core import coords
        d = e.get("data") or {}
        for holder in (d.get("ephem"), d.get("simbad")):
            if not holder:
                continue
            try:
                return (coords.ra_hms_to_deg(holder["ra"]),
                        coords.dec_dms_to_deg(holder["dec"]))
            except (ValueError, AttributeError, KeyError):
                pass
        unc = d.get("unconfirmed")
        if unc and unc.get("ra_deg") is not None:
            try:
                return float(unc["ra_deg"]), float(unc.get("dec_deg") or 0.0)
            except (TypeError, ValueError):
                pass
        for ra_key in ("ra_deg", "ra"):
            if d.get(ra_key) is None:
                continue
            dec_key = "dec_deg" if ra_key == "ra_deg" else "dec"
            try:
                return float(d[ra_key]), float(d.get(dec_key) or 0.0)
            except (TypeError, ValueError):
                pass
        return None, None

    def _show_coords(self, ra_deg, dec_deg):
        # Paints the coordinates block; both formats go to the clipboard.
        # @args: ra_deg, dec_deg - J2000 degrees
        from ..core import coords
        h, m, s = coords.ra_deg_to_hms(ra_deg).split()
        ra_sex = f"{h}h {m}m {s}s"
        sd, dm, ds = coords.dec_deg_to_dms(dec_deg).split()
        dec_sex = f"{sd[0]}{sd[1:]}° {dm}′ {ds}″"
        ra_dec, dec_dec = f"{ra_deg:.5f}°", f"{dec_deg:+.5f}°"
        self.lbl_coords.setText(
            f"{self.tr('RA')}  {ra_dec}  =  {ra_sex}\n"
            f"{self.tr('Dec')} {dec_dec}  =  {dec_sex}")
        self._coords_clip = (f"RA {ra_dec} = {ra_sex}\n"
                             f"Dec {dec_dec} = {dec_sex}")
        self.row_coords.show()

    def _copy_coords(self):
        # Copies the coordinates (decimal + sexagesimal) to the clipboard.
        if not self._coords_clip:
            return
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self._coords_clip)
        self.btn_copy_coords.setText("✓  " + self.tr("Copied"))
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, self._reset_copy_button)

    def _reset_copy_button(self):
        # Restores the copy button's face after the «copied» feedback.
        self.btn_copy_coords.setText("⧉  " + self.tr("Copy"))

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
        if e.get("type") == "transient":
            return orbits.explain_transient(d)
        if e.get("type") == "exoplanet" or d.get("transit"):
            from ..config import config
            return orbits.explain_transit(
                d, aperture_in=config.get("aperture_inches"))
        return []

    # ---------------- charts (D2, ADR-029) ----------------
    #
    # Each produced chart lands on its OWN tab, labelled with the chart's
    # title; with a single chart the tab bar auto-hides.
    # orbit / sky / approach — live vector widgets (OrbitChart, SkyChart,
    # ApproachChart). field/transit — QLabel+QPixmap (no vector widget for
    # cutout/light curve). build_charts still runs (core/post.py unchanged);
    # for the vector slots it only acts as a "can I make this chart?" gate.

    def _render_charts(self, e):
        # Builds the charts tabs for this object.
        # @args: e - enriched dict
        from ..core import post
        outdir = self._chart_dir or paths.data_dir() / "posts"
        try:
            charts = post.build_charts(e, outdir, "_overview_",
                                       cfg=self._chart_cfg(), fmt="panel")
        except Exception:
            charts = {}

        # Start from empty tabs (the panel re-renders when the object
        # changes).
        self._empty_tabs()

        for key in _CHART_SLOTS:
            # "approach" is a pure-vector slot: build_charts never returns
            # an "approach" PNG, so gate on orbital elements directly.
            if key == "approach":
                self._slot_titles[key] = self.tr(_TITLE[key])
                w = self._make_vector(key, e)
                if w is not None:
                    w.setProperty("chart_key", key)
                    w.setCursor(Qt.PointingHandCursor)
                    w.installEventFilter(self._slot_click)
                    self._slot_data[key] = self._extract(key, e)
                    self._tabs.addTab(w, self._slot_titles[key])
                continue
            chart = charts.get(key)
            if not chart:
                continue  # omit what is missing
            self._slot_titles[key] = self.tr(_TITLE[key])
            if key in _VECTOR_SLOTS:
                w = self._make_vector(key, e)
                if w is not None:
                    w.setProperty("chart_key", key)
                    w.setCursor(Qt.PointingHandCursor)
                    w.installEventFilter(self._slot_click)
                    self._slot_data[key] = self._extract(key, e)
                    self._tabs.addTab(w, self._slot_titles[key])
            else:
                self._place_png(key, chart)

        # "approach" is purely vector: the group must stay visible even
        # when build_charts produced no PNG (elements without an ephemeris).
        self.grp_charts.setVisible(bool(charts) or bool(self._slot_data))

    def _empty_tabs(self):
        # Removes every chart tab and clears the slot state.
        while self._tabs.count():
            w = self._tabs.widget(0)
            self._tabs.removeTab(0)
            if w is not None:
                w.deleteLater()
        self._slot_data.clear()
        self._slot_titles.clear()

    def _place_png(self, key, png_path):
        # Loads a chart PNG into a QLabel and places it in its own tab.
        # @args: key - slot name, png_path - Path from build_charts
        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setMinimumHeight(300)
        pix = QPixmap(str(png_path))
        if not pix.isNull():
            lbl.setPixmap(pix)
        lbl.setProperty("chart_key", key)
        lbl.setProperty("chart_png", str(png_path))
        lbl.setCursor(Qt.PointingHandCursor)
        lbl.setToolTip(self.tr("Click to zoom / export"))
        lbl.installEventFilter(self._slot_click)
        self._tabs.addTab(lbl, self._slot_titles[key])

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
        elif key == "approach":
            # A pure vector slot: needs elements that can actually be
            # propagated (a/q plus the time data); the widget itself
            # degrades gracefully, but without those we cannot draw.
            from ..core import coords
            d = e.get("data") or {}
            sb = d.get("sbdb")
            els = (sb or {}).get("elements")
            if not els or (els.get("a") is None and els.get("q") is None):
                return None
            jd = coords.jd_from_datetime(
                datetime.datetime.now(datetime.timezone.utc))
            from .widgets.approach_widget import ApproachChart
            w = ApproachChart()
            w.set_elements(els, jd, e.get("name", ""))
            return w
        return None

    def _extract(self, key, e):
        # Extracts the data needed to rebuild a fresh widget on click.
        # @args: key - slot name, e - enriched dict
        # @return: a dict suitable for _rebuild_widget, or None
        d = e.get("data") or {}

        if key == "orbit":
            from ..core import coords
            sb = d.get("sbdb")
            els = (sb or {}).get("elements")
            if not els:
                return None
            jd = coords.jd_from_datetime(
                datetime.datetime.now(datetime.timezone.utc))
            return {"elements": els, "jd": jd, "name": e.get("name", "")}

        elif key == "sky":
            ra, dec = self._coords_from(e)
            unc = d.get("unconfirmed")

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

        elif key == "approach":
            from ..core import coords
            d = e.get("data") or {}
            sb = d.get("sbdb")
            els = (sb or {}).get("elements")
            if not els or (els.get("a") is None and els.get("q") is None):
                return None
            jd = coords.jd_from_datetime(
                datetime.datetime.now(datetime.timezone.utc))
            return {"elements": els, "jd": jd, "name": e.get("name", "")}

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
        elif key == "approach":
            from .widgets.approach_widget import ApproachChart
            w = ApproachChart()
            w.set_elements(data["elements"], data["jd"],
                            data.get("name", ""))
            return w
        return None

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

    def _param_section_resized(self, index, _old, new):
        # Re-fits the wrapped rows after the explanation column changed
        # width (window resize / column fit). The signal fires BEFORE
        # columnWidth() reports the new size, so the section is nudged
        # to `new` first (a no-op for the header, which is already
        # setting it); _rows_busy breaks the recursion (new row heights
        # can toggle the scrollbar, which resizes the sections again).
        if index != 2 or self._rows_busy:
            return
        self._rows_busy = True
        try:
            self.tbl_params.setColumnWidth(2, new)
            self.tbl_params.resizeRowsToContents()
        finally:
            self._rows_busy = False

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
        # Fit Parameter/Value to their content, capped so the explanation
        # keeps its air; NEVER resizeToContents on the stretch column —
        # with word wrap the hint is the full one-line width and the
        # column would balloon past the viewport. The stretch column
        # takes what is left; _RowResizer re-fits rows on real resizes.
        for col in (0, 1):
            tbl.resizeColumnToContents(col)
            if tbl.columnWidth(col) > _PARAM_COL_MAX_W:
                tbl.setColumnWidth(col, _PARAM_COL_MAX_W)
        tbl.resizeRowsToContents()
