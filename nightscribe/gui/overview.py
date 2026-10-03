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
# docs/WORKFLOWS.es.md §7ter), redesigned as a DOSSIER in ADR-057: the
# hero (glyph, name, kind chip, hook, score ring with its "why tonight"
# phrase), the "tonight" KPI strip, the alert-flags row, a coordinates
# block with copyable RA/Dec (decimal + sexagesimal), the night ribbon,
# the parameters grouped in themed section cards (core/orbits.py rows
# carry a "group" key) and a charts group rendered by
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
# ADR-029 Fase 2-3) that the user can hover; in the panel they are
# passive previews (wheel and drag scroll the page, click opens the
# ChartViewer where zoom / pan / export live — see _mark_embedded). The transit
# (light curve) and field (cutout) slots have no vector widget yet and
# keep the QLabel+QPixmap route. Clicking any slot opens the same
# ChartViewer dialog (widget mode or pixmap mode).
#
# ADR-057 layout note: the panel is a VERTICAL dossier and may scroll
# (the parent pages are scroll areas). The two-column numbers|pictures
# layout of Interfaz 1.8 is gone, and with it the parameters QTableWidget:
# the section cards are label-based definition lists, which wrap and size
# themselves (the table needed ~90 lines of manual row-fitting because Qt
# does not auto-size a wrapped cell that spans columns).

import datetime

from PySide6.QtCore import (QEvent, QObject, QT_TRANSLATE_NOOP, Qt,
                            Signal)
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from ..core import explain, exposure, kinds, narrative, orbits
from .. import paths
from . import theme
from .ui_loader import adopt_ui, drop_in
from .widgets.kpi_tile import KpiTile
from .widgets.object_hero import ObjectHero
from .widgets.section_card import SectionCard

# Viewer / slot titles, translated at the point of use (tr() at the tab
# site; QT_TRANSLATE_NOOP marks them here so lupdate can see them).
_TITLE = {"orbit": QT_TRANSLATE_NOOP("ObjectPanel", "Orbit"),
          "sky": QT_TRANSLATE_NOOP("ObjectPanel", "Sky tonight"),
          "approach": QT_TRANSLATE_NOOP("ObjectPanel", "Approach"),
          "field": QT_TRANSLATE_NOOP("ObjectPanel", "Reference field"),
          "transit": QT_TRANSLATE_NOOP("ObjectPanel", "Light curve"),
          "lightcurve": QT_TRANSLATE_NOOP("ObjectPanel", "Light curve")}

# Grid order, left to right; the ones build_charts actually produced are
# laid out in this order (the rest stay hidden).
_CHART_SLOTS = ("orbit", "sky", "approach", "field", "transit",
                "lightcurve")

# Slots that get a live vector widget (OrbitChart / SkyChart /
# ApproachChart / LightCurveChart); the rest keep the QLabel+QPixmap
# route (the reference-field cutout has no widget yet).
_VECTOR_SLOTS = frozenset({"orbit", "sky", "approach", "lightcurve"})


def _chip(text, color, tip=""):
    # @return: a small pill label, the same idiom the Tonight rows use
    lbl = QLabel(text)
    lbl.setStyleSheet(theme.chip_style(color))
    # A pill is sized by its text. Without this the vertical policy lets the
    # layout stretch it into a slab when the panel has room to spare (seen
    # on the object card: three chips 80 px tall).
    lbl.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
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
# Below this panel width the parameters/charts row stacks vertically
# (ADR-057 rev.). The charts' own floor is 300 px (the tab widget) plus the
# group's margins, and the section cards need ~300 to read; 660 leaves both
# their minimum and a little air.
_BODY_STACK_W = 660

_MIN_READ_W = 780     # comfortable reading width (px)
_MIN_READ_H = 640     # minimum usable height (px)
_DLG_CHROME = 60      # title bar / frame / margins headroom (px)


# The "tonight" strip shows at most this many KPI tiles: past that the
# eye stops scanning values and starts skimming shapes. The strip's
# builder orders tiles by decision weight, so the cap only ever drops
# the least informative ones.
_KPI_MAX = 6


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


def _mark_embedded(w):
    # The panel's live charts are passive previews: the wheel and the
    # drag belong to the page (the enclosing QScrollArea scrolls), hover
    # keeps working, and clicking opens the dedicated ChartViewer for
    # zoom / pan / export. The viewer builds its own widgets separately,
    # so they stay in the default, fully interactive mode.
    # @args: w - the panel widget (a composite exposing `.view`, or a
    #        ChartView itself, e.g. LightCurveChart)
    from .widgets.base_chart import ChartView
    view = getattr(w, "view", None)
    if view is None and isinstance(w, ChartView):
        view = w
    if isinstance(view, ChartView):
        view.set_embedded(True)


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

        # The structure is the Designer file's (ADR-005): every block
        # starts hidden and the states show them; the skins come from
        # theme.py, and the hero texts / tiles / section rows / chart
        # tabs are data.
        self._ui = adopt_ui(self, "object_panel")
        self._e = None          # last enriched dict (re-render on mode change)

        # state line (loading / not found); hidden when ready
        self.lbl_state = self._ui.lbl_state
        self.lbl_state.setStyleSheet(f"color: {theme.C_TEXT_DIM};")

        # ADR-057: the hero carries the identity (glyph, name, kind, hook)
        # and the tonight score ring; the old bare 15 px hook line is gone
        self.hero = ObjectHero()
        drop_in(self._ui.vbox_panel, self._ui.heroHost, self.hero)
        self.hero.hide()
        # lbl_hook stays as an attribute alias: the hook now lives in the
        # hero, and the alias keeps the panel's contract (and its tests)
        # reading the same name
        self.lbl_hook = self.hero.lbl_hook

        self.lbl_facts = self._ui.lbl_facts
        self.lbl_facts.setStyleSheet(f"color: {theme.C_TEXT_DIM};")

        # ADR-057: the "tonight" KPI strip (tiles are data, added in code)
        self.kpi_strip = self._ui.kpi_strip
        self._kpi_lay = self._ui.kpi_lay

        # alert-flags row (the old capture-chips row, now only flags:
        # period change, campaign, does-not-fit...; the numbers moved to
        # the KPI strip)
        self.row_capture = self._ui.row_capture
        self.row_capture.setSizePolicy(QSizePolicy.Preferred,
                                       QSizePolicy.Maximum)
        self._chips = self._ui.chips

        # coordinates block (object-card plan, subplan 0): RA/Dec in
        # decimal AND sexagesimal, with a one-click copy button. Hidden
        # for objects without a known position (e.g. ESA alerts).
        self.row_coords = self._ui.row_coords
        self.row_coords.setStyleSheet(
            f"background: {theme.C_BASE}; border-radius: 8px;"
            f" border: 1px solid {theme.C_LINE};")
        self.lbl_coords = self._ui.lbl_coords
        self.lbl_coords.setStyleSheet(f"color: {theme.C_TEXT_DIM};")
        self.btn_copy_coords = self._ui.btn_copy_coords
        self.btn_copy_coords.setText("⧉  " + self.btn_copy_coords.text())
        self.btn_copy_coords.setStyleSheet(
            f"QPushButton {{ color: {theme.C_TEXT_DIM};"
            f" background: transparent; border: 1px solid {theme.C_LINE};"
            f" border-radius: 4px; padding: 2px 10px; }}"
            f"QPushButton:hover {{ color: {theme.C_TEXT}; }}")
        self.btn_copy_coords.clicked.connect(self._copy_coords)
        self._coords_clip = ""

        # The night of THIS object, drawn (the same trick as the Welcome
        # hero: a painted sky with real numbers). ADR-057: full width,
        # between the coordinates and the parameter sections.
        from .widgets.night_ribbon import NightRibbon
        self._ribbon = NightRibbon()
        drop_in(self._ui.vbox_panel, self._ui.ribbonHost, self._ribbon)

        # parameters: a header row (title + "In depth" switch) and the
        # section cards built under sectionsHost (ADR-057)
        self.grp_params = self._ui.grp_params
        self.chk_deep = self._ui.chk_deep
        self.chk_deep.toggled.connect(lambda: self._refill_sections())
        self._sections_lay = self._ui.sections_lay
        self._section_cards = []

        # ADR-057 rev.: the parameters and the charts share one row, 50/50.
        # The columns are WIDGETS so that hiding one gives the other the
        # whole width (a hidden widget takes no space in a layout; a hidden
        # child inside a visible column would leave the column standing).
        self.col_params = self._ui.col_params
        self.col_charts = self._ui.col_charts
        self._row_body = self._ui.row_body
        self._row_body.setStretch(0, 1)
        self._row_body.setStretch(1, 1)
        self._body_direction = None      # what the row is laid out as now
        self._apply_body_direction()

        # charts tabs (D2): each produced chart gets its own tab labelled
        # with the chart's title; with a single chart the tab bar hides and
        # the chart stands alone. orbit/sky/approach are vector widgets;
        # field/transit are QLabel+QPixmap. The tabs are (re)filled in
        # _render_charts and emptied by _empty_tabs (state transitions:
        # ready -> blank -> ready).
        self.grp_charts = self._ui.grp_charts
        self._tabs = self._ui.tabs_charts
        self._slot_data = {}    # key -> data dict (for rebuild on click)
        self._slot_titles = {}  # key -> translated title (for tabs + viewer)
        self._slot_click = _SlotClick(self)

        # single CTA at the very bottom
        self.btn_project = self._ui.btn_project
        self._action = "create"
        self.btn_project.clicked.connect(self._cta_clicked)

        # the panel is born empty: the blocks are hidden by the .ui and the
        # columns follow them, so an untouched panel shows no empty row
        self._sync_body_columns()

    # ---------------- states ----------------

    def _sync_body_columns(self):
        # @return: None. A column is shown only when its block is.
        #
        # The block's own hidden flag stays the single source of truth (the
        # .ui starts both hidden, the states and _render_charts toggle them,
        # the tests read them). The COLUMN has to follow, and that is the
        # whole point of the widget: a hidden block inside a visible column
        # still leaves the column standing, taking its half of the row and
        # squeezing the other one for nothing.
        self.col_params.setVisible(not self.grp_params.isHidden())
        self.col_charts.setVisible(not self.grp_charts.isHidden())

    def _apply_body_direction(self):
        # @return: None. Below _BODY_STACK_W the row turns vertical.
        #
        # Two 390 px columns do not fit a narrow pane, and the charts carry
        # a 300 px floor: squeezed past it the row clips instead of
        # shrinking. Stacked, the parameters keep their full width (their
        # explanations wrap less) and the charts get the page, which is
        # what the card did before the row existed.
        row = getattr(self, "_row_body", None)
        if row is None:
            return
        from PySide6.QtWidgets import QBoxLayout
        stacked = self.width() < _BODY_STACK_W
        want = QBoxLayout.TopToBottom if stacked else QBoxLayout.LeftToRight
        if want == self._body_direction:
            return
        self._body_direction = want
        row.setDirection(want)

    def resizeEvent(self, event):
        # @args: event - the QResizeEvent
        super().resizeEvent(event)
        self._apply_body_direction()

    def showEvent(self, event):
        # @args: event - the QShowEvent
        # A widget is born 640 px wide (Qt's default) and the real width
        # only arrives with the layout: without this the first paint of a
        # wide panel could come out stacked.
        super().showEvent(event)
        self._apply_body_direction()

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
        self.hero.set_hook("")      # the hook label's own flag drops too:
        self.hero.hide()            # hero.hide() alone leaves it "shown"
        self.lbl_facts.hide()       # inside a hidden parent
        self.kpi_strip.hide()
        self.row_coords.hide()
        self.row_capture.hide()
        self.grp_params.hide()
        self._clear_sections()
        self.grp_charts.hide()
        self._sync_body_columns()
        self.btn_project.hide()
        # the previous object's arc is dropped while it loads (a bare
        # night is honest; the last object's curve over a "Loading" line
        # is not)
        self._refresh_ribbon(None, None)

    def _state_missing(self, name=None):
        # @args: name - identifier, shown when given
        self._state = "missing"
        self._name = name or getattr(self, "_name", None)
        self.lbl_state.setText(self.tr("Not found: %1").replace(
            "%1", self._name or self.tr("the requested object")))
        self.lbl_state.setStyleSheet(f"color: {theme.C_WARN};")
        self.lbl_state.show()
        self.hero.set_hook("")
        self.hero.hide()
        self.lbl_facts.hide()
        self.kpi_strip.hide()
        self.row_coords.hide()
        self.row_capture.hide()
        self.grp_params.hide()
        self._clear_sections()
        self.grp_charts.hide()
        self._sync_body_columns()
        self._refresh_cta()

    def _state_ready(self, e):
        # @args: e - enriched dict from enrich.enrich()
        self._e = e
        self.lbl_state.hide()

        kind = self._kind_of(e)
        self.hero.set_object(self._name or e.get("name") or "", kind,
                             subtitle=self._subtitle_for(e),
                             pha=self._pha_of(e))
        self.hero.set_hook(self._txt(narrative.hook(e)))
        score, why = self._score_for(e)
        self.hero.set_score(score, why)
        self.hero.show()

        bullets = [b for b in (narrative.fact_bullets(e) or []) if self._txt(b)]
        if bullets:
            # One flowing line under the hero, not four bullets: the same
            # sentences for 36 px less of vertical rhythm.
            self.lbl_facts.setText(
                "   ·   ".join(self._txt(b) for b in bullets))
            self.lbl_facts.show()
        else:
            self.lbl_facts.hide()

        ra, dec = self._coords_from(e)
        if ra is not None and dec is not None:
            epoch = (e.get("data") or {}).get("ephem_epoch")
            self._show_coords(ra, dec, epoch)
        else:
            self.row_coords.hide()
            self._coords_clip = ""
        self._refresh_ribbon(ra, dec)

        self._rows = self._orbit_rows(e)
        self.grp_params.setVisible(bool(self._rows))
        self._refill_sections()
        self._render_charts(e)
        self._sync_body_columns()
        self._render_kpis(e)
        self._render_flags(e)
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
        self._inject_followup(e)
        self._state_ready(e)

    def _inject_followup(self, e):
        # Fills data["followup"]["points"] for SNs and HADS stars with a
        # project context: core/enrich has no project knowledge, so the GUI
        # layer pulls the photometry from the project's db (B4/D3).
        # @args: e - enriched dict (mutated in place)
        if e.get("type") not in ("transient", "sn", "hads", "variable"):
            return
        fu = (e.get("data") or {}).get("followup") or {}
        if fu.get("points"):
            return
        pid = (self._ctx or {}).get("project_id")
        if not pid:
            return
        try:
            from ..core import db, followup
            conn = db.Database()
            pts = followup.list_points(conn, pid)
            conn.close()
        except Exception:
            pts = []
        if pts:
            d = e.setdefault("data", {})
            d.setdefault("followup", {}).setdefault("points", pts)

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
        self._clear_flags()
        self._clear_kpis()
        self._empty_tabs()
        self.lbl_state.hide()
        self.hero.set_hook("")
        self.hero.hide()
        self.lbl_facts.hide()
        self.kpi_strip.hide()
        self.row_coords.hide()
        self._coords_clip = ""
        self.row_capture.hide()
        self.grp_params.hide()
        self._clear_sections()
        self.grp_charts.hide()
        self._sync_body_columns()
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

    # ---------------- hero: identity + tonight score (ADR-057) --------

    def _kind_of(self, e):
        # @args: e - enriched dict
        # @return: the project kind id ("neo", "sn", ...): the context's
        #          kind wins (the planner knows), else the enriched type
        #          is mapped through core/kinds.py
        ctx = self._ctx or self._fallback or {}
        return ctx.get("kind") or kinds.project_kind(e) or ""

    @staticmethod
    def _subtitle_for(e):
        # @return: a secondary designation for the hero, when it adds
        #          anything to the name: the SBDB fullname for small
        #          bodies, the AUID for variables; "" otherwise
        d = e.get("data") or {}
        name = e.get("name") or ""
        full = ((d.get("sbdb") or {}).get("fullname") or "").strip()
        if full and full != name:
            return full
        auid = ((d.get("variable") or {}).get("auid") or "").strip()
        if auid and auid != name:
            return auid
        return ""

    @staticmethod
    def _pha_of(e):
        # @return: True for a potentially hazardous asteroid (SBDB flag,
        #          or a sub-0.05 AU MOID when the flag is absent)
        d = e.get("data") or {}
        sb = d.get("sbdb") or {}
        if sb.get("pha"):
            return True
        try:
            moid = sb.get("moid")
            return moid is not None and float(moid) < 0.05
        except (TypeError, ValueError):
            return False

    def _score_target(self, e):
        # Builds the planner-shaped target dict core/suggest.py scores.
        # @args: e - enriched dict
        # @return: a target dict, or None when the kind is not scorable
        #
        # The panel never sees the planner's original target (it sees the
        # enriched dict plus the project context), so the score's inputs
        # are reassembled here: context keys win (they are tonight's
        # planner values), enriched facts fill the gaps.
        ctx = self._ctx or self._fallback or {}
        d = e.get("data") or {}
        kind = self._kind_of(e)
        if kind not in ("neo", "sn", "comet", "pccp", "transit", "hads",
                        "variable", "alert"):
            return None
        t = {"kind": kind, "id": ctx.get("id") or e.get("name"),
             "name": e.get("name")}
        for k in ("mag", "max_alt", "safe_max_alt", "hours_up", "hads",
                  "variable", "transit", "campaign", "disc_date", "sn_type",
                  "host", "nf_score", "nf_priority", "nf_urgency",
                  "nf_cost_min", "pccp_score", "moid", "rate_arcsec_min",
                  "ra_deg", "dec_deg", "neocp", "impact", "arc_days",
                  "nobs", "perihelion_date", "delta_au", "r_au", "vigil",
                  "aavso"):
            v = ctx.get(k)
            if v is None:
                v = d.get(k)
            if v is not None:
                t[k] = v
        # unconfirmed candidates keep their NEOfixer facts one level down
        unc = d.get("unconfirmed") or {}
        for k in ("nf_score", "nf_priority", "nf_cost_min", "nobs",
                  "arc_days", "moid", "pccp_score", "mag"):
            if t.get(k) is None and unc.get(k) is not None:
                t[k] = unc[k]
        if t.get("ra_deg") is None:
            ra, dec = self._coords_from(e)
            t["ra_deg"], t["dec_deg"] = ra, dec
        return t

    @staticmethod
    def _hm_of(dt):
        # @args: dt - datetime or ISO-8601 string
        # @return: "HH:MM" string, or None (same contract as orbits._hm;
        #          kept local so the panel never reaches into a private)
        if isinstance(dt, str):
            try:
                dt = datetime.datetime.fromisoformat(dt)
            except ValueError:
                return None
        if isinstance(dt, datetime.datetime):
            return dt.strftime("%H:%M")
        return None

    def _score_for(self, e):
        # @args: e - enriched dict
        # @return: (score_0_100, why_text) or (None, "") — None when the
        #          object is not scorable (the hero hides the ring then:
        #          a missing number is honest, a made-up one is not)
        from ..core import suggest
        t = self._score_target(e)
        if t is None:
            return None, ""
        # No planner signal, no ring: a bare name from Explore would score
        # a flat 0, and a 0 ring reads as "bad object" when the truth is
        # "we know nothing about tonight". Absent, not zero.
        if not any(t.get(k) is not None for k in (
                "mag", "max_alt", "safe_max_alt", "hours_up", "nf_score",
                "pccp_score", "transit", "hads", "variable", "campaign",
                "window_start")):
            return None, ""
        try:
            from ..config import config
            score, _parts = suggest.score_target(t, config)
            why = self._txt(suggest.why_phrase(t, config))
        except Exception:
            # the score is a bonus, never a blocker: a half-filled context
            # (a manual project) must not take the card down with it
            return None, ""
        return score, why

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

    def _show_coords(self, ra_deg, dec_deg, epoch=None):
        # Paints the coordinates block; both formats go to the clipboard.
        # When an ephemeris epoch is known (moving kinds) a third line shows
        # the validity instant so the observer sees how fresh the position is.
        # @args: ra_deg, dec_deg - J2000 degrees, epoch - "YYYY-Mon-DD HH:MM"
        #        or ISO string (optional)
        from ..core import coords
        h, m, s = coords.ra_deg_to_hms(ra_deg).split()
        ra_sex = f"{h}h {m}m {s}s"
        sd, dm, ds = coords.dec_deg_to_dms(dec_deg).split()
        dec_sex = f"{sd[0]}{sd[1:]}° {dm}′ {ds}″"
        ra_dec, dec_dec = f"{ra_deg:.5f}°", f"{dec_deg:+.5f}°"
        text = (f"{self.tr('RA')}  {ra_dec}  =  {ra_sex}\n"
                f"{self.tr('Dec')} {dec_dec}  =  {dec_sex}")
        clip = f"RA {ra_dec} = {ra_sex}\nDec {dec_dec} = {dec_sex}"
        iso = self._epoch_iso(epoch) if epoch else None
        if iso:
            text += f"\n{self.tr('Epoch')}: {iso} UT"
            clip += f"\nEpoch: {iso} UT"
        self.lbl_coords.setText(text)
        self._coords_clip = clip
        self.row_coords.show()

    @staticmethod
    def _epoch_iso(epoch):
        # Normalises a Horizons-style "YYYY-Mon-DD HH:MM" epoch to the ISO
        # "YYYY-MM-DD HH:MM" form; passes through anything else unchanged.
        # @args: epoch - string
        # @return: ISO-style string
        import datetime
        try:
            t = datetime.datetime.strptime(epoch, "%Y-%b-%d %H:%M")
            return t.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return epoch

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
                                           arc_days=sb.get("arc_days"),
                                           disc_date=sb.get("disc_date"))
        if d.get("unconfirmed"):
            return orbits.explain_neofixer(d["unconfirmed"])
        if e.get("type") == "transient":
            return orbits.explain_transient(d)
        if e.get("type") == "exoplanet" or d.get("transit"):
            from ..config import config
            return orbits.explain_transit(
                d, aperture_in=config.get("aperture_inches"))
        if e.get("type") == "hads" or d.get("hads"):
            return orbits.explain_hads(d)
        if e.get("type") == "variable" or d.get("variable"):
            return orbits.explain_variable(d)
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
            # "approach" and "lightcurve" are pure-vector slots: gate on
            # the underlying data directly (elements / photometry points).
            if key in ("approach", "lightcurve"):
                self._slot_titles[key] = self.tr(_TITLE[key])
                w = self._make_vector(key, e)
                if w is not None:
                    w.setProperty("chart_key", key)
                    w.setCursor(Qt.PointingHandCursor)
                    w.installEventFilter(self._slot_click)
                    _mark_embedded(w)
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
                    _mark_embedded(w)
                    self._slot_data[key] = self._extract(key, e)
                    self._tabs.addTab(w, self._slot_titles[key])
            else:
                self._place_png(key, chart)

        # "approach" is purely vector: the group must stay visible even
        # when build_charts produced no PNG (elements without an ephemeris).
        has_charts = bool(charts) or bool(self._slot_data)
        self.grp_charts.setVisible(has_charts)
        self._sync_body_columns()

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
        elif key == "lightcurve":
            # Pure vector (B4): needs photometry points already injected
            # into the enriched dict (see _inject_followup_data).
            data = self._extract("lightcurve", e)
            if not data or not data.get("points"):
                return None
            from .widgets.lightcurve_widget import LightCurveChart
            w = LightCurveChart()
            w.set_data(data["points"], sn_type=data.get("sn_type"),
                       peak_mjd=data.get("peak_mjd"),
                       peak_mag=data.get("peak_mag"),
                       fold_period_d=data.get("fold_period_d"),
                       epoch_mjd=data.get("epoch_mjd"),
                       schematic=data.get("schematic"))
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

        elif key == "lightcurve":
            # One shared payload builder (2026-09-17): the fold, schematic
            # and sn_type priority now live in core/lightcurve_data.py so
            # this path, the Follow-up inline curve and the PNG cannot drift.
            from ..core import lightcurve_data
            out = lightcurve_data.build_payload(
                d.get("followup"),
                sn_type_fallback=(d.get("simbad") or {}).get("otype"),
                hads=d.get("hads") or (self._ctx or {}).get("hads"),
                variable=d.get("variable")
                or (self._ctx or {}).get("variable"))
            if not out.get("points"):
                return None
            return out

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
        elif key == "lightcurve":
            from .widgets.lightcurve_widget import LightCurveChart
            w = LightCurveChart()
            w.set_data(data["points"], sn_type=data.get("sn_type"),
                       peak_mjd=data.get("peak_mjd"),
                       peak_mag=data.get("peak_mag"),
                       fold_period_d=data.get("fold_period_d"),
                       epoch_mjd=data.get("epoch_mjd"),
                       schematic=data.get("schematic"))
            return w
        return None

    def _chart_cfg(self):
        # @return: the active Config
        from ..config import config
        return config

    # ---------------- "tonight" KPI strip + alert flags (ADR-057) ------
    #
    # The strip replaces the old capture-chips row: the same numbers, but
    # as value-over-caption tiles the eye can scan. Only the ALERTS stay
    # as pills (period change, campaign, does-not-fit...): a flag is a
    # badge, not a measurement.

    def _clear_kpis(self):
        # Drops every tile the strip currently shows.
        while self._kpi_lay.count():
            item = self._kpi_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _clear_flags(self):
        # Drops every flag pill the row currently shows.
        lay = self._chips
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _kpi_tiles(self, e):
        # Builds the tile definitions for this object, decision weight
        # first (the strip caps at _KPI_MAX, so order is what survives).
        # @args: e - enriched dict
        # @return: list of (value, caption, accent_or_None, tooltip)
        tiles = []
        ctx = self._ctx or self._fallback or {}
        kind = self._kind_of(e)
        d = e.get("data") or {}

        # the safety verdict leads: a session that does not fit is the ONE
        # number that must never scroll off the strip
        if (ctx.get("duration_s") and ctx.get("window_start")
                and ctx.get("window_end") and not ctx.get("safe_window")):
            mins = int(round(int(ctx.get("duration_s", 0)) / 60))
            tiles.append((
                f"⚠ {mins} min", self.tr("does not fit"), theme.C_WARN,
                self.tr("The planned {0} min session does not fit in the "
                        "time the object is above your local limit. "
                        "Do NOT force the instrument.").format(mins)))

        mag = ctx.get("mag")
        if mag is None:
            mag = d.get("mag") or d.get("mag_now") \
                or ((d.get("simbad") or {}).get("vmag"))
        if mag is not None:
            try:
                mag = float(mag)
            except (TypeError, ValueError):
                mag = None
        if mag is not None:
            tiles.append((
                f"{mag:.1f}", self.tr("Mag"), theme.C_OK,
                self.tr("Predicted apparent magnitude tonight") + " "
                + self._txt(explain.short(explain.MAGNITUDE))))

        # kind-specific extras (object-card plan, subplan 4): every family
        # fills its strip with the same grammar — the card of an SN or a
        # transit must not look sparse next to a NEO's
        rate = None
        if kind in ("neo", "pccp") and ctx.get("rate_arcsec_min"):
            try:
                rate = float(ctx["rate_arcsec_min"])
            except (TypeError, ValueError):
                rate = None
        if rate:
            tiles.append((
                f"{rate:.1f}″/min", self.tr("Sky rate"), theme.C_TEXT,
                self.tr("Sky rate tonight — it must outrun the stars") + " "
                + self._txt(explain.short(explain.RATE))))
            from ..config import config
            scale = exposure.plate_scale(config.get("pixel_um"),
                                         config.get("focal_mm"))
            t_max = exposure.max_exposure_no_trail(rate, scale)
            if t_max:
                tiles.append((
                    f"{t_max:.0f} s", self.tr("Max exposure"), theme.C_WARN,
                    str(self.tr("Longest single exposure before the "
                                "target trails more than a pixel")) + " "
                    + self._txt(explain.short(explain.EXPOSURE))))

        is_sn = kind in ("sn", "transient")
        if is_sn:
            otype = (((d.get("simbad") or {}).get("otype"))
                     or d.get("otype") or "").strip()
            if otype:
                tiles.append((
                    otype, self.tr("Event type"), theme.C_TEXT,
                    self.tr("Type of stellar explosion") + " "
                    + self._txt(explain.short(explain.sn_type(otype)))))
            days = orbits.days_since(d["disc_date"]) \
                if d.get("disc_date") else None
            if days is not None and days >= 0:
                tiles.append((
                    f"{days} d", self.tr("Since discovery"),
                    theme.C_GOOD if days <= 14 else theme.C_TEXT,
                    self.tr("Days since discovery — a young light curve "
                            "is gold for science")))

        tr = d.get("transit") or ctx.get("transit") or {}
        if kind == "transit" or tr:
            depth = tr.get("depth_mmag")
            if depth:
                tiles.append((
                    f"{float(depth):.1f}", self.tr("Depth (mmag)"),
                    theme.C_TEXT,
                    self.tr("How much the star dims at mid-transit") + " "
                    + self._txt(explain.short(explain.DEPTH))))
            mid = self._hm_of(tr.get("mid"))
            if mid:
                tiles.append((
                    f"{mid} UTC", self.tr("Mid-transit"), theme.C_TEXT,
                    self.tr("The planet blocks the most light at this "
                            "instant: plan around it")))
            dur = tr.get("duration_h")
            if dur:
                tiles.append((
                    f"{float(dur):.1f} h", self.tr("Duration"),
                    theme.C_TEXT,
                    self.tr("How long the full crossing lasts")))

        h = d.get("hads") or ctx.get("hads") or {}
        if kind == "hads" or h:
            per = h.get("period_h")
            if per:
                tiles.append((
                    f"{float(per):.2f} h", self.tr("Period"),
                    theme.KIND_COLORS["hads"],
                    self.tr("Pulsation period — several full cycles fit in "
                            "one night") + " "
                    + self._txt(explain.short(explain.PERIOD))))
            amp = h.get("amp")
            if amp is None and h.get("max") is not None \
                    and h.get("min") is not None:
                amp = h["min"] - h["max"]   # inverted magnitude axis
            if amp:
                tiles.append((
                    f"{float(amp):.1f} mag", self.tr("Amplitude"),
                    theme.C_TEXT,
                    self.tr("Peak-to-peak brightness swing of the "
                            "pulsation")))
            if h.get("cycles"):
                tiles.append((
                    f"×{float(h['cycles']):.1f}", self.tr("Cycles tonight"),
                    theme.KIND_COLORS["hads"],
                    self.tr("Complete cycles that fit above your limit "
                            "tonight")))

        v = d.get("variable") or ctx.get("variable") or {}
        if kind == "variable" or v:
            per = v.get("period_d")
            if per:
                tiles.append((
                    f"{float(per):.1f} d", self.tr("Period"),
                    theme.KIND_COLORS["variable"],
                    self.tr("Variability period, in days") + " "
                    + self._txt(explain.short(explain.PERIOD))))
            amp = v.get("amp")
            if amp is None and v.get("max") is not None \
                    and v.get("min") is not None:
                amp = v["min"] - v["max"]
            if amp:
                tiles.append((
                    f"{float(amp):.1f} mag", self.tr("Amplitude"),
                    theme.C_TEXT,
                    self.tr("Peak-to-peak brightness swing")))
            nxt = v.get("next_extremum") or {}
            if nxt.get("days") is not None:
                lab = self.tr("max") if nxt.get("kind") == "max" \
                    else self.tr("min")
                tiles.append((
                    f"{lab} ~{float(nxt['days']):.0f} d",
                    self.tr("Next extremum"), theme.KIND_COLORS["variable"],
                    self.tr("Next expected extremum (VSX epoch)")))

        ws = ctx.get("window_start")
        we = ctx.get("window_end")
        if ws and we:
            tiles.append((
                f"{ws[11:16]}–{we[11:16]}", self.tr("Window"), theme.C_OK,
                self.tr("Times the object is safely above the limit")))

        if ctx.get("safe_window"):
            s0, s1 = ctx["safe_window"].split("|")
            bt = ctx.get("best_time")
            caption = self.tr("Safe window")
            hint = self.tr("The capture window that still clears your "
                           "local limit — the telescope stays in safe "
                           "altitude through the whole session")
            if bt:
                caption += f" · ≤ {bt[11:16]}"
                hint += self.tr(" · ≤ HH:MM is the latest safe start")
            tiles.append((
                f"{s0[11:16]}–{s1[11:16]}", caption, theme.C_GOOD, hint))

        hours = ctx.get("hours_up")
        if hours:
            try:
                hours = float(hours)
            except (TypeError, ValueError):
                hours = None
            if hours:
                tiles.append((
                    f"{hours:.1f} h", self.tr("Above the limit"),
                    theme.C_TEXT,
                    self.tr("How long it stays a valid target")))

        alt = ctx.get("safe_max_alt")
        if alt is None:
            alt = ctx.get("max_alt")
        if alt is not None:
            try:
                alt = float(alt)
            except (TypeError, ValueError):
                alt = None
        if alt:
            tiles.append((
                f"{alt:.0f}°", self.tr("Max altitude"), theme.C_TEXT,
                self.tr("Highest altitude over your horizon tonight") + " "
                + self._txt(explain.short(explain.ALTITUDE))))

        # the Moon, when the user cares about it (Settings > limits): its
        # separation and illumination decide the faint end of the night
        t = self._score_target(e)
        if t is not None:
            try:
                from ..config import config
                from ..core import suggest
                moon = suggest.moon_info(t, config)
            except Exception:
                moon = None
            if moon:
                tiles.append((
                    f"{moon['sep_deg']:.0f}° · {moon['illum']:.0%}",
                    self.tr("Moon"),
                    theme.C_WARN if moon.get("warning") else None,
                    self.tr("Moon separation and illumination tonight") + " "
                    + self._txt(explain.short(explain.MOON))))

        return tiles[:_KPI_MAX]

    def _render_kpis(self, e):
        # Shows the strip when it has at least one tile.
        # @args: e - enriched dict
        self._clear_kpis()
        tiles = self._kpi_tiles(e)
        if not tiles:
            self.kpi_strip.hide()
            return
        for value, caption, accent, tip in tiles:
            self._kpi_lay.addWidget(KpiTile(value, caption, accent, tip))
        # the tiles hug their content on the left; the stretch absorbs the
        # slack (re-added on every fill: _clear_kpis takes it away too)
        self._kpi_lay.addStretch(1)
        self.kpi_strip.show()

    def _flag_chips(self, e):
        # Builds the ALERT flags for this object (ADR-057): the pills that
        # are a badge, not a measurement.
        # @args: e - enriched dict
        # @return: list of (text, color, tooltip)
        chips = []
        ctx = self._ctx or self._fallback or {}
        kind = self._kind_of(e)
        d = e.get("data") or {}

        is_hads = kind == "hads" or bool(d.get("hads"))
        if is_hads:
            h = d.get("hads") or ctx.get("hads") or {}
            if h.get("priority") in ("period_change",
                                     "period_change_possible"):
                chips.append((
                    self.tr("Period change!"), theme.C_WARN,
                    self.tr("The Wils monitoring programme flags period "
                            "changes — tonight's curve counts double")))
            if h.get("observed") is False:
                chips.append((
                    self.tr("Not yet observed"), theme.C_OK,
                    self.tr("The monitoring programme has no measurement of "
                            "this star yet")))
            if h.get("multiperiodic"):
                chips.append((
                    self.tr("Multiperiodic"), theme.KIND_COLORS["hads"],
                    self.tr("Several pulsation modes — observe on "
                            "consecutive nights")))

        camp = d.get("campaign") or ctx.get("campaign") or {}
        if camp.get("name"):
            chips.append((
                self.tr("Campaign: %1").replace("%1", camp["name"]),
                theme.C_OK,
                self.tr("This object belongs to an observing campaign")))
        return chips

    def _render_flags(self, e):
        # Shows the flags row when it has at least one pill.
        # @args: e - enriched dict
        self._clear_flags()
        chips = self._flag_chips(e)
        if not chips:
            self.row_capture.hide()
            return
        for text, color, tip in chips:
            self._chips.addWidget(_chip(text, color, tip))
        # The pills sit at the LEFT and the row keeps the rest. The trailing
        # stretch has to be re-added on every fill: _clear_flags() takes
        # every item away, spacer included, and without it three chips
        # spread themselves across the whole width.
        self._chips.addStretch(1)
        self.row_capture.show()

    def _refresh_ribbon(self, ra=None, dec=None):
        # @args: ra, dec - the object in degrees, or None for a bare night
        # @return: None. The site comes from the settings, so the band
        #          answers for THIS observatory.
        ribbon = getattr(self, "_ribbon", None)
        if ribbon is None:
            return
        from ..config import config
        try:
            lat = float(config.get("lat") or 0.0)
            lon = float(config.get("lon") or 0.0)
        except (TypeError, ValueError):
            lat = lon = 0.0
        if not (lat or lon):
            lat = lon = None
        ribbon.set_site(lat, lon)
        ribbon.set_object(ra, dec, self._name or "")
        kind = (self._ctx or {}).get("kind")
        ribbon.set_accent(theme.KIND_COLORS.get(kind, theme.C_ACCENT))

    # ---------------- parameter sections (ADR-057) ----------------

    def _clear_sections(self):
        # Drops every section card the panel currently shows.
        while self._sections_lay.count():
            item = self._sections_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._section_cards = []

    def _refill_sections(self):
        # Rebuilds the section cards from the cached rows, honouring the
        # "In depth" switch. Sections keep their first-seen order (the
        # interpreter's own order: the story's, not the alphabet's).
        self._clear_sections()
        rows = list(self._rows)
        if not self.chk_deep.isChecked():
            rows = [r for r in rows if r.get("level") == "basic"]
        order, by_group = [], {}
        for r in rows:
            g = r.get("group") or "orbit"
            if g not in by_group:
                order.append(g)
                by_group[g] = []
            by_group[g].append(r)
        accent = theme.KIND_COLORS.get(self._kind_of(self._e or {}),
                                       theme.C_ACCENT)
        for g in order:
            title = self._txt(orbits.SECTION_TITLES.get(
                g, {"es": g, "en": g}))
            card = SectionCard(title, accent)
            for r in by_group[g]:
                param = self._txt(r["param"]) if isinstance(r["param"], dict) \
                    else str(r["param"])
                # a row value may be bilingual too (e.g. HADS pulsation
                # modes): pick the active language instead of leaking EN
                value = self._txt(r["value"]) if isinstance(r["value"], dict) \
                    else str(r["value"])
                card.add_row(param, value, self._txt(r))
            self._sections_lay.addWidget(card)
            self._section_cards.append(card)
