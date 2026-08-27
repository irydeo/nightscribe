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


def _chip(text, color, tip=""):
    # @return: a small pill label, the same idiom the Tonight rows use
    #          (mag / rate / window chips)
    lbl = QLabel(text)
    lbl.setStyleSheet(theme.chip_style(color))
    if tip:
        lbl.setToolTip(tip)
    return lbl


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
    # post_requested(name, fallback_target) — the optional "Create post"
    # button fired it (shown only when loaded with for_post, i.e. the
    # Explore dialog of D5; the Projects hub keeps it hidden).
    post_requested = Signal(str, object)
    # Entry points:
    #   show(e, ctx)      — render an already-enriched dict (hub, tests)
    #   explore(name,...) — ask the injected loader for a worker and
    #                       render its result when it lands
    #   cancel()          — drop a running worker (the hub calls it when the
    #                       user switches to another project)

    def __init__(self, loader=None, chart_dir=None, for_post=False,
                 parent=None):
        # @args: loader - callable(name, fallback_target) returning a
        #                     QThread-like worker with finished=Signal(dict)
        #                     and start(); None means the ExploreWorker
        #                     over the global config
        #         chart_dir - directory where the PNG charts are written;
        #                     defaults to the user data dir's "posts".
        #                     Injectable so tests can point at tmp_path.
        #         for_post - the Explore-dialog flavour (D5): show the
        #                    "Create post" button next to the panel
        #         parent - parent widget
        super().__init__(parent)
        self._loader = loader or self._default_loader
        self._chart_dir = chart_dir
        self._worker = None
        self._slot = None
        self._ctx = None
        self._rows = []
        self._state = "empty"
        self._name = None        # identifier currently being shown/fetched
        self._fallback = None    # planner target (unconfirmed NEOCP/PCCP)
        self._for_post = False   # the Explore dialog wants the post affordance

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._for_post = for_post

        # top row: the "Create post" affordance (D5, Explore dialog only)
        self.btn_post = QPushButton(self.tr("Create post"))
        self.btn_post.setToolTip(self.tr(
            "Build the bilingual drafts + charts for this object"))
        self.btn_post.clicked.connect(self._ask_post)
        if not for_post:
            self.btn_post.hide()
        layout.addWidget(self.btn_post, 0, Qt.AlignRight)

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

        # capture/window block (D3): the night facts about this object —
        # magnitude, apparent rate, max no-trail exposure (NEO/PCCP only),
        # the window above the horizon and how many hours it stays up.
        # Each chip is built from the project context snapshot (main_window
        # _create_project) and omitted when the data is missing.
        self.row_capture = QFrame()
        self.row_capture.setStyleSheet(
            f"background: {theme.C_BASE}; border-radius: 8px;"
            f" border: 1px solid {theme.C_LINE};")
        self._chips = QHBoxLayout(self.row_capture)
        self._chips.setContentsMargins(10, 6, 10, 6)
        self._chips.setSpacing(8)
        self._chips.addStretch(1)  # pushed left, rebuilt below
        self.row_capture.hide()
        layout.addWidget(self.row_capture)

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
        self.row_capture.hide()
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
        self.row_capture.hide()
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
        self._render_capture(e)
        self._state = "ready"

    # ---------------- public API ----------------

    def name(self):
        # @return: the identifier this panel is showing (or was showing),
        #          for the Explore dialog's "Create post" flow (D5)
        return self._name

    def _ask_post(self):
        # @return: asks the owner (the Explore dialog's window) to build
        #          post drafts for the object currently on the panel
        if self._worker is not None:
            return  # still loading — nothing to build a post from yet
        if self._name is None:
            return
        self.post_requested.emit(self._name, self._fallback)

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
        if self._name is None and e.get("name"):
            self._name = str(e["name"])
        self._state_ready(e)

    def explore(self, name, fallback_target=None, ctx=None):
        # Kicks off the injected loader; the panel renders whatever lands.
        # @args: name - object identifier, fallback_target - planner target
        #         dict (unconfirmed NEOCP/PCCP), like ExploreWorker,
        #         ctx - project context snapshot, kept for the capture block
        if self._worker is not None:
            return  # a worker is still out there; ignore the second ask
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
        # Drops a running worker so its result (if any) can never land on
        # this panel: the slot disconnects and the reference drops. The hub
        # owns the worker and deletes it (via _keep); the panel goes blank
        # so the next project starts from a clean state.
        worker, slot = self._worker, self._slot
        self._worker = None
        self._slot = None
        if worker is not None and slot is not None:
            try:
                worker.finished.disconnect(slot)
            except RuntimeError:
                pass  # the worker was already gone — nothing left to detach
        self._blank()

    def _blank(self):
        # Puts the panel back to the pre-load state (all parts hidden) — the
        # hub calls it when the selection moves to another project.
        self._state = "empty"
        self._ctx = None
        self._rows = []
        self._name = None
        self._fallback = None
        self._clear_chips()
        self.lbl_state.hide()
        self.lbl_hook.hide()
        self.lbl_facts.hide()
        self.row_capture.hide()
        self.grp_params.hide()
        self.grp_charts.hide()
        for lbl in self._labels.values():
            lbl.hide()
            lbl.setPixmap(QPixmap())
            lbl.setProperty("chart_png", None)

    def _worker_done(self, w, e):
        # @args: w - the worker that finished, e - its enriched payload
        if w is not self._worker:
            return  # a cancel() dropped it, or it is a stale one
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

    # ---------------- capture / window block (D3) ----------------

    def _clear_chips(self):
        # Drops every chip the block currently shows (kept in one place so
        # show() can be called again with a different object).
        lay = self._chips
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
                w = None

    def _capture_chips(self, e):
        # Builds the chip definitions for this object, all from the project
        # context snapshot (the numbers a capture plan actually uses):
        # magnitude, apparent rate (NEO/PCCP only), max no-trail exposure
        # (rate + camera profile) and the hours-above-horizon window.
        # Returns an empty list when nothing applies, which hides the block.
        # @args: e - enriched dict (only for the object type as a fallback)
        chips = []
        ctx = self._ctx or {}
        kind = ctx.get("kind") or e.get("type")

        # magnitude: the context's live, tonight figure (omitted if absent)
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

        # apparent rate (arcsec/min): NEO / PCCP only, from context
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
            # max no-trail exposure: needs the camera profile's plate scale;
            # omitted when the profile is incomplete (missing is acceptable)
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

        # window above the horizon: start–end (HH:MM, same as the Tonight
        # rows; ctx stores ISO strings with a UTC offset, so HH:MM is safe)
        ws = ctx.get("window_start")
        we = ctx.get("window_end")
        if ws and we:
            ws_hm = ws[11:16]
            we_hm = we[11:16]
            chips.append((
                f"{ws_hm}–{we_hm}", theme.C_OK,
                self.tr("Times the object is safely above the horizon")))
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
        return chips

    def _render_capture(self, e):
        # Shows the capture/window block when it has at least one chip, keeps
        # it hidden otherwise (empty context, SN with no window, …). This is
        # the «omitting what is missing» rule from phase D3.
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
