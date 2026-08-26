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
# parameters table with a wide, multi-line explanation column and the
# 2×2 charts grid (D2) rendered by core.post.build_charts. A slot that
# build_charts cannot produce keeps a «why not» line (hyperbolic,
# unconfirmed, no orbital elements) instead of a blank.
#
# The capture/window block (D3) will land in this same file. The
# Projects hub (D4) and the Explore dialog (D5) will both render it —
# single source of truth for "what do we know about this object".

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QHeaderView, QSizePolicy,
                               QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ..core import narrative, orbits
from .. import paths
from . import theme

# Viewer / slot titles, translated at the point of use.
_TITLE = {"orbit": "Orbit", "sky": "Sky tonight",
          "families": "Families", "field": "Field"}

# Grid order: orbit / sky on the first row, families / field on the second.
_CHART_SLOTS = ("orbit", "sky", "families", "field")

# Reasons a slot stays empty (build_charts left it out). Static pairs,
# chosen in the active language (orbits.pick). The orbit slot has three
# of them (hyperbolic / unconfirmed / no elements); the rest are one-liners.
_MSG = {
    "hyperbolic": {
        "es": "Órbita hiperbólica — no dibujable",
        "en": "Hyperbolic orbit — not plottable"},
    "unconfirmed": {
        "es": "Objeto no confirmado — sin elementos orbitales",
        "en": "Unconfirmed object — no orbital elements"},
    "no_elements": {
        "es": "Sin elementos orbitales",
        "en": "No orbital elements"},
    "no_family": {
        "es": "Sin familia orbital asignada",
        "en": "No orbital family assigned"},
    "no_position": {
        "es": "Sin posición celeste conocida",
        "en": "No known sky position"},
    "no_field": {
        "es": "Sin campo de referencia disponible",
        "en": "No reference field available"},
    "empty": {"es": "—", "en": "—"},
}


def _scale_png(label, png_path, max_w=820, max_h=620):
    # Fits a PNG into a chart slot, preserving the aspect ratio. Fixed
    # bounds because labels inside a not-yet-shown panel report a tiny
    # size (same rule as the Explore dialog's helper).
    pix = QPixmap(str(png_path))
    if pix.isNull():
        return False
    label.setPixmap(pix.scaled(max_w, max_h, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation))
    return True


class _SlotClick(QObject):
    # Opens the zoom/export viewer when a chart slot is released. Clicks
    # on an empty slot (no chart file) are ignored.

    def __init__(self, parent):
        super().__init__(parent)
        self._parent = parent

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonRelease:
            path = obj.property("chart_png")
            if path:
                from .chart_viewer import open_chart
                open_chart(self._parent, path,
                           title=obj.property("chart_title") or "")
                return True
        return False


class ObjectPanel(QWidget):
    # Fixed panel describing the project's object. Three states:
    #   loading — a worker is still out there
    #   missing — the loader came back empty
    #   ready   — hook + bullets + parameters table
    # Entry points:
    #   show(e, ctx)      — render an already-enriched dict (hub, tests)
    #   explore(name,...) — ask the injected loader for a worker and
    #                       render its result when it lands

    def __init__(self, loader=None, chart_dir=None, parent=None):
        # @args: loader - callable(name, fallback_target) returning a
        #                     QThread-like worker with finished=Signal(dict)
        #                     and start(); None means the ExploreWorker
        #                     over the global config
        #         chart_dir - directory where the PNG charts are written;
        #                     defaults to the user data dir's "posts".
        #                     Injectable so tests can point at tmp_path.
        #         parent - parent widget
        super().__init__(parent)
        self._loader = loader or self._default_loader
        self._chart_dir = chart_dir
        self._worker = None
        self._ctx = None
        self._rows = []
        self._state = "empty"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

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
        # the explanation column owns the leftover width, multi-line
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        tbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        gl.addWidget(tbl)

        self.grp_params.hide()
        layout.addWidget(self.grp_params)

        # charts 2×2 (D2): orbit / sky over families / field
        self.grp_charts = QGroupBox(self.tr("Charts"))
        gl2 = QGridLayout(self.grp_charts)
        gl2.setSpacing(8)
        self._labels = {}
        self._slot_click = _SlotClick(self)
        for i, key in enumerate(_CHART_SLOTS):
            lbl = QLabel("—")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumHeight(220)
            lbl.setProperty("chart_key", key)
            lbl.setCursor(Qt.PointingHandCursor)
            lbl.setToolTip(self.tr("Click to zoom / export"))
            lbl.installEventFilter(self._slot_click)
            self._labels[key] = lbl
            lbl.hide()
            gl2.addWidget(lbl, i // 2, i % 2)
        self.grp_charts.hide()
        layout.addWidget(self.grp_charts)

    # ---------------- states ----------------

    def state(self):
        # @return: "empty" | "loading" | "missing" | "ready"
        return self._state

    def _state_loading(self, name=None):
        # @args: name - identifier being fetched (keeps the state line honest)
        self._state = "loading"
        self._name = name
        self.lbl_state.setText(self.tr("Loading…"))
        self.lbl_state.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        self.lbl_state.show()
        self.lbl_hook.hide()
        self.lbl_facts.hide()
        self.grp_params.hide()
        self.grp_charts.hide()

    def _state_missing(self, name=None):
        # @args: name - identifier, shown when given (falls back to the one
        #        that was being loaded, so the state names the object)
        self._state = "missing"
        self._name = name or getattr(self, "_name", None)
        self.lbl_state.setText(self.tr("Not found: %1").replace(
            "%1", self._name or self.tr("the requested object")))
        self.lbl_state.setStyleSheet(f"color: {theme.C_WARN};")
        self.lbl_state.show()
        self.lbl_hook.hide()
        self.lbl_facts.hide()
        self.grp_params.hide()
        self.grp_charts.hide()

    def _state_ready(self, e):
        # @args: e - enriched dict from enrich.enrich()
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
        self._state = "ready"

    # ---------------- public API ----------------

    def show(self, e, ctx=None):
        # Renders the ready state from an enriched dict; an empty dict is
        # the «not found» state (matches ExploreWorker's {} on failure).
        # @args: e - dict from enrich.enrich() (or {} when nothing was found)
        #        ctx - project context snapshot, kept for the capture block
        #              of D3
        self._ctx = ctx
        if not e or not e.get("data"):
            self._state_missing()
            return
        self._state_ready(e)

    def explore(self, name, fallback_target=None):
        # Kicks off the injected loader; the panel renders whatever lands.
        # @args: name - object identifier, fallback_target - planner target
        #         dict (unconfirmed NEOCP/PCCP), like ExploreWorker
        self._state_loading(name)
        worker = self._loader(name, fallback_target)
        self._worker = worker
        worker.finished.connect(lambda e, w=worker: self._worker_done(w, e))
        worker.start()

    def _worker_done(self, w, e):
        # @args: w - the worker that finished, e - its enriched payload
        if w is not self._worker:
            return  # a newer explore() replaced it; drop the stale result
        self.show(e)

    # ---------------- internals ----------------

    @staticmethod
    def _default_loader(name, fallback_target=None):
        # The same ExploreWorker the Explore dialog uses today.
        # @args: name - object identifier, fallback_target - planner target
        # @return: a not-yet-started ExploreWorker
        from ..config import config
        from .workers import ExploreWorker
        return ExploreWorker(config, name, fallback_target=fallback_target)

    def _lang(self):
        # Active UI language ("es" | "en"), same rule as MainWindow._lang.
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
        # Same extraction the Explore dialog uses (D5 delegates there).
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

    def _render_charts(self, e):
        # Paints the 2×2 grid from core.post.build_charts, falling back to
        # a «why not» line on any slot the builder left empty (D2).
        # @args: e - enriched dict
        from ..core import post
        d = e.get("data") or {}
        sb = d.get("sbdb")
        els = sb.get("elements") if sb else None
        unc = d.get("unconfirmed")
        outdir = self._chart_dir or paths.data_dir() / "posts"
        try:
            charts = post.build_charts(e, outdir, "_overview_",
                                       cfg=self._chart_cfg())
        except Exception:
            charts = {}
        for key in _CHART_SLOTS:
            self._paint_slot(key, charts.get(key), els, unc, d)
        self.grp_charts.show()

    def _paint_slot(self, key, png, els, unc, d):
        # A slot shows either the chart (pixmap only; QLabel.setText()
        # would reset it) or a «why not» line. The slot's title lives in
        # the chart viewer; the slot itself carries no caption.
        # @args: key - slot name, png - Path from build_charts (or None),
        #        els - SBDB elements, unc - unconfirmed dict, d - enrich data
        lbl = self._labels[key]
        lbl.hide()
        lbl.setText("")
        lbl.setPixmap(QPixmap())
        lbl.setProperty("chart_png", None)
        if png and _scale_png(lbl, png):
            lbl.setProperty("chart_png", str(png))
            lbl.setProperty("chart_title", self.tr(_TITLE[key]))
            lbl.show()
            return
        lbl.setText(self._txt(_MSG[self._why_not(key, els, unc, d)]))
        lbl.show()

    @staticmethod
    def _why_not(key, els, unc, d):
        # @args: key - slot, els - elements, unc - unconfirmed dict,
        #         d - enrich data
        # @return: a _MSG key explaining why this slot is empty. Mirrors the
        #          same guards core/post.py:build_charts uses, so the panel
        #          explains the builder's decision.
        if key == "orbit":
            if els and els.get("q") and els.get("e", 1) > 1.0:
                return "hyperbolic"
            if unc:
                return "unconfirmed"
            return "no_elements"
        if key == "families":
            return "no_family"
        if key == "sky":
            has = (d.get("ephem") or d.get("simbad")
                   or (unc and unc.get("ra_deg") is not None))
            return "no_position" if not has else "empty"
        if key == "field":
            return "no_field"
        return "empty"

    def _chart_cfg(self):
        # @return: the active Config for the sky chart's site/horizon
        #          (mirrors the Explore dialog's build_charts call)
        from ..config import config
        return config

    def _refill_params(self):
        # Fills the parameters table from the cached rows, honoring the
        # in-depth toggle: without it only the "basic" rows are shown.
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
