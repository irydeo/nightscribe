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
# The capture/window block (D3) will land in this same file. The
# Projects hub (D4) and the Explore dialog (D5) will both render it —
# single source of truth for "what do we know about this object".

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
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


def _chip(text, color, tip=""):
    # @return: a small pill label, the same idiom the Tonight rows use
    #          (mag / rate / window chips)
    lbl = QLabel(text)
    lbl.setStyleSheet(theme.chip_style(color))
    if tip:
        lbl.setToolTip(tip)
    return lbl


# The re-render mode (Settings > Charts) draws 2× the panel preset: the
# PNG keeps its 16:9 shape, so a big slot stays crisp without re-running
# matplotlib on every resize.
_RENDER2X = (2400, 1350)


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
    #
    # Single CTA at the bottom of the panel (Phase E, corrected
    # 2026-09-02, docs/WORKFLOWS.es.md §7ses): one button, not a row of
    # three. It reads the _project_lookup (injected callable(name) ->
    # dict-or-None) and presents either
    #      project_create(name, fallback_target)     — no active project
    #      project_continue(name, fallback_target)   — one already exists
    # so the owner (the Explore dialog's glue in MainWindow) always knows
    # which intent fired. The "Create post" affordance was dropped (the
    # Posts dialog lives where it belongs: inside the project on its
    # *Publish* step, and ad-hoc under Tools).
    #
    # The CTA stays hidden while the hub is showing (for_post=False),
    # while the object is still loading, or while no project_lookup was
    # injected — the panel stays testable and free from the core.db
    # import.
    project_create = Signal(str, object)
    project_continue = Signal(str, object)
    # Entry points:
    #   show(e, ctx)      — render an already-enriched dict (hub, tests)
    #   explore(name,...) — ask the injected loader for a worker and
    #                       render its result when it lands
    #   cancel()          — drop a running worker (the hub calls it when the
    #                       user switches to another project)

    def __init__(self, loader=None, chart_dir=None, for_post=False,
                 project_lookup=None, parent=None):
        # @args: loader - callable(name, fallback_target) returning a
        #                     QThread-like worker with finished=Signal(dict)
        #                     and start(); None means the ExploreWorker
        #                     over the global config
        #         chart_dir - directory where the PNG charts are written;
        #                     defaults to the user data dir's "posts".
        #                     Injectable so tests can point at tmp_path.
        #         for_post  - the Explore-dialog flavour (Phase E): expose
        #                     the project CTA; the hub keeps this False
        #         project_lookup - optional callable(name) -> dict-of-active
        #                     project or None. When given AND for_post
        #                     AND the object is loaded, the CTA shows the
        #                     "Continue project" or "Create project"
        #                     variant depending on the lookup result.
        #        parent - parent widget
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
        self._for_post = for_post   # the Explore dialog exposes the CTA
        self._project_lookup = project_lookup

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._e = None          # last enriched dict (re-render on mode change)
        self._orig_pngs = {}    # slot key -> chart PNG path, for re-fitting

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

        # charts 2×2 (D2): orbit / sky over field / transit, in grid order
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

        # single CTA at the very bottom (phase E): the one action of the
        # Explore-dialog flavour. Hidden right away; _refresh_cta() gives
        # it its "Create project" / "Continue project" face (and only then
        # shows it) once the object is on the panel.
        self.btn_project = QPushButton(self.tr("Create project"))
        self.btn_project.setCursor(Qt.PointingHandCursor)
        self.btn_project.setMinimumHeight(46)
        self.btn_project.setSizePolicy(QSizePolicy.Expanding,
                                       QSizePolicy.Fixed)
        self._action = "create"    # which intent the CTA currently fires
        self.btn_project.clicked.connect(self._cta_clicked)
        self.btn_project.hide()
        layout.addSpacing(6)
        layout.addWidget(self.btn_project)

    def resizeEvent(self, event):
        # The panel resizes with its window: re-fit every chart slot on
        # top (the pixmap was rendered once, we only re-scale it).
        super().resizeEvent(event)
        self._fit_slots()

    def _fit_slots(self):
        # Fits each placed chart to its slot's own size, keeping the
        # aspect ratio. Slots that have no chart (hidden slot) are no-ops.
        for key, lbl in self._labels.items():
            if lbl.isHidden() or lbl.pixmap().isNull():
                continue
            path = self._orig_pngs.get(key)
            pix = QPixmap(path) if path else lbl.pixmap()
            if pix.isNull():
                continue
            w = max(lbl.width(), 320)
            h = max(lbl.height(), 240)
            scaled = pix.scaled(w, h, Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)
            if scaled.width() != lbl.pixmap().width() or \
                    scaled.height() != lbl.pixmap().height():
                lbl.setPixmap(scaled)

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
        # the object is not yet resolved, so the CTA must not be on
        # screen (it needs a name and a lookup hit/miss to pick a face)
        self.btn_project.hide()

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

    # ---------------- public API ----------------

    def name(self):
        # @return: the identifier this panel is showing (or was showing);
        #          tests and the owner (dialog glue) use it to assert state
        return self._name

    def _cta_clicked(self):
        # @return: fires the matching signal. `_action` is the intent the
        #          CTA is currently presenting ("create" | "continue"),
        #          decided by _refresh_cta from the lookup result, so the
        #          owner needs zero bookkeeping to know which one fired.
        if self._worker is not None:
            return  # still loading — the panel does not yet know the intent
        if self._name is None or not self._for_post:
            return
        if self._action == "continue":
            self.project_continue.emit(self._name, self._fallback)
        else:
            self.project_create.emit(self._name, self._fallback)

    def _refresh_cta(self):
        # Gives the CTA its face — "Create project" or "Continue project"
        # — or leaves it hidden when the panel is not in the Explore
        # flavour, no lookup was injected, or the object is not loaded.
        # Called from _state_ready / _state_loading / _blank / _state_missing.
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
        self._e = None
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
        self.btn_project.hide()
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
        # Lays out a row of the charts build_charts could actually produce
        # (compact "panel" size); the group disappears when there is none.
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
        for key in _CHART_SLOTS:
            self._paint_slot(key, charts.get(key))
        self.grp_charts.setVisible(bool(charts))
        if charts:
            # the slots only reach their final size once the layout is up:
            # fit them against the real geometry in the next paint round
            QTimer.singleShot(0, self._fit_slots)

    def _paint_slot(self, key, png):
        # A slot shows its chart (pixmap only) and stays hidden when the
        # builder did not produce one — no «why not» lines, so the grid
        # never keeps space for a chart that is not there.
        # @args: key - slot name, png - Path from build_charts (or None)
        lbl = self._labels[key]
        lbl.hide()
        lbl.setText("")
        lbl.setPixmap(QPixmap())
        lbl.setProperty("chart_png", None)
        if png:
            self._orig_pngs[key] = str(png)
            lbl.setProperty("chart_png", str(png))
            lbl.setProperty("chart_title", self.tr(_TITLE[key]))
            self._fit_slot(key)
            lbl.show()
        else:
            self._orig_pngs.pop(key, None)

    def _fit_slot(self, key):
        # Fits one placed chart to its slot's real size (same rule as
        # _fit_slots, but the label is being placed right now).
        # @args: key - slot name
        lbl = self._labels.get(key)
        if lbl is None:
            return
        path = self._orig_pngs.get(key)
        pix = QPixmap(path) if path else QPixmap()
        if pix.isNull():
            return
        w = max(lbl.width(), 320)
        h = max(lbl.height(), 240)
        lbl.setPixmap(pix.scaled(w, h, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation))

    def rebuild_charts(self):
        # Re-draws the current object's charts with the active resolution
        # mode (Settings > Charts) — called when the panel is already on
        # screen and the user has just switched modes.
        if self._e is None:
            return
        self._render_charts(self._e)

    def _chart_zoom(self):
        # @return: "scale" | "re-render" (config, default "scale")
        from ..config import config
        return config.get("chart_zoom", "scale")

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
        # ADR-027: prefer the context passed to show() but fall back to the
        # planner target that the hub / explore-flow gave us, so an SN or
        # comet explored without a project still shows mag/window chips.
        # @args: e - enriched dict (only for the object type as a fallback)
        chips = []
        ctx = self._ctx or self._fallback or {}
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

        # safe window (ADR-020): the run of the night where the planned
        # capture session still clears the local horizon; only set when a
        # project's capture plan was saved, and always with the latest-safe-
        # start. The red "does not fit" chip is the one safety warning.
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
            # a session was planned but it does not fit tonight's span
            mins = int(round(int(ctx.get("duration_s", 0)) / 60))
            chips.append((
                f"⚠ {self.tr('does not fit')} · {mins} min",
                theme.C_WARN,
                self.tr("The planned {0} min session does not fit in the "
                        "time the object is above your local limit. "
                        "Do NOT force the instrument.").format(mins)))
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
