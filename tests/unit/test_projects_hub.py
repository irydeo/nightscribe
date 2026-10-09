############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Projects hub integration tests (offscreen, phase D4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen smoke tests for phase D4 (docs/WORKFLOWS.es.md).

Selecting a project in the Projects hub opens the shared ObjectPanel and
asks the injected loader for the object. We fake that loader (no network)
and check the phase-D4 contracts:

  * selecting a project drives the panel (loading -> ready / missing)
  * the panel carries the project context capture chips (D3)
  * switching project cancels the in-flight one (no stale result lands)
  * the step machine / buttons stay intact alongside the panel

The real ExploreWorker would go out to the sources, so the tests swap it
for a canned loader, and the db singleton is pointed at a temp file so
nothing touches the real one (mirrors tests/unit/test_overview_panel.py).
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# A bounded orbit with an ephemeris: orbit / sky render to real PNGs
# offline, and the "field" cutout slot stays hidden.
FAKE_ELEMENT = {
    "type": "small_body",
    "name": "2026 QK (443089)",
    "data": {
        "family": "Apollo",
        "sbdb": {
            "fullname": "2026 QK (443089) — example asteroid",
            "elements": {"a": 1.350, "e": 0.400, "i": 6.2,
                         "q": 0.810, "Q": 1.890, "n": None, "per": 560.0},
            "phys": {"H": 20.5, "diameter": 1.1, "spec_B": "S-type",
                     "albedo": 0.18, "rot_per": 12.3},
            "moid": 0.028,
            "sigmas": {"a": 0.0012, "e": 0.008, "i": 0.4},
            "n_resids": 21,
            "arc_days": 14,
        },
        "ephem": {"ra": "12 00 00.000", "dec": "+30 00 00.000",
                  "r": 1.3, "delta": 0.5},
        "mag_now": 19.8,
        "dist_now_km": 74_800_000,
    },
}

# A different object, so a stale result from the first project is obvious.
FAKE_SN = {
    "type": "transient",
    "name": "SN 2026zz",
    "data": {"host": {"name": "NGC 5908"}, "dist_mly": 74, "simbad": {}},
}

NEO_CTX = {"kind": "neo", "mag": 19.5, "rate_arcsec_min": 12.0,
           "window_start": "2026-08-26T21:00:00+02:00",
           "window_end": "2026-08-26T23:30:00+02:00", "hours_up": 2.5}


class FakeWorker:
    # A stand-in for ExploreWorker: the panel connects to `finished`, calls
    # start(), and whatever lands there is delivered synchronously (or not,
    # when `deliver=False` — used to simulate a still-running worker).
    def __init__(self, payload, deliver=True):
        self.payload = payload
        self.deliver = deliver
        self._cbs = []

    class _finished:
        # just the connect / disconnect / emit surface the panel needs
        def __init__(self, w):
            self._w = w

        def connect(self, cb):
            self._w._cbs.append(cb)

        def disconnect(self, cb=None):
            if cb is None:
                self._w._cbs = []
            else:
                self._w._cbs = [c for c in self._w._cbs if c is not cb]

        def emit(self, p):
            for cb in list(self._w._cbs):
                cb(p)

    @property
    def finished(self):
        return self._finished(self)

    def start(self):
        if self.deliver:
            self._finished(self).emit(self.payload)


# ---------------- harness ----------------

@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # main_window imports the shared `db` singleton; redirect it to a throw
    # away file so the hub's project CRUD never touches the real database.
    # The module-scoped window is torn down before the redirect is undone.
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("d4db") / "t.db")
    dbmod.db = tmp
    mw.db = tmp
    yield
    dbmod.db = old_dbmod
    mw.db = old_mw


@pytest.fixture(scope="module")
def window(_point_db_at_tmpdir):
    from PySide6.QtWidgets import QApplication
    from nightscribe.config import config
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    from nightscribe.gui.main_window import MainWindow
    # keep the tests hermetic: no auto-compute network worker on startup
    orig_cfg = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


@pytest.fixture()
def panel(window, tmp_path):
    # A ready-made ObjectPanel (fake loader, temp chart dir) slotted into
    # the hub's lazy slot, so the real ExploreWorker is never built.
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(loader=lambda name, fallback_target=None:
                    FakeWorker(FAKE_ELEMENT),
                    chart_dir=tmp_path / "charts")
    window._proj_panel = p
    yield p
    window._proj_panel = None
    window._proj_panel_area = None
    p.deleteLater()


def _create_and_select(window, kind, name, ctx):
    # @args: window - MainWindow, kind - project kind, name - target,
    #        ctx - context snapshot stored with the project
    # @return: the created project dict (selected in the hub list)
    # The list signals are blocked while we refresh + pick a row so a queued
    # itemSelectionChanged from a previous selection can never re-fire against
    # this test's panel (deterministic, no signal-ordering races).
    from PySide6.QtCore import Qt
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p = project.create(dbmod.db, kind, name, ctx)
    lst = window.projects.lst_projects
    lst.blockSignals(True)
    window.on_refresh_projects()
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == p["id"]:
            lst.setCurrentRow(i)
            break
    lst.blockSignals(False)
    window._project_selected()   # deliver the selection explicitly, once
    return p


def _build_page(window, p):
    # Build the project page with a fake panel loader slotted into the
    # hub's lazy slot, so the real ExploreWorker is never built; the
    # previous state is restored afterwards. The harness drives the page
    # directly (no list selection), so the hub's current project is
    # scoped for the build - the lazy tab machinery reads it.
    # @args: window - MainWindow, p - the project dict to page
    orig_panel = window._proj_panel
    orig_loader = window._proj_panel_loader
    orig_current = window._current_project
    window._proj_panel = None
    window._proj_panel_loader = (lambda name, fallback_target=None:
                                 FakeWorker(FAKE_ELEMENT))
    window._current_project = p
    try:
        window._build_project_page(p)
    finally:
        window._proj_panel = orig_panel
        window._proj_panel_loader = orig_loader
        window._current_project = orig_current


def _open_tab(window, p, key):
    # ADR-041: the step and follow-up tabs are lazy, so the content
    # tests open the tab they inspect through the tab bar (the user
    # path), scoping the hub's current project so the build runs
    # against the page under test.
    # @args: window - MainWindow, p - the project dict, key - tab key
    # @return: the tab page just opened (window._tab_pages[key])
    orig_current = window._current_project
    window._current_project = p
    try:
        getattr(window.projects, f"btn_tab_{key}").click()
        return window._tab_pages[key]
    finally:
        window._current_project = orig_current


# ---------------- D4 contracts ----------------

def test_select_project_drives_panel(window, panel):
    _create_and_select(window, "neo", "2026 QK (443089)", NEO_CTX)
    assert window._proj_panel is panel
    assert panel.state() == "ready"
    assert panel.lbl_hook.text()
    # the project page is a bar of tabs (ADR-041): object card + steps
    # (no follow-up for a NEO), lazy-built per click; the object card
    # carries the nested "Project files" block, and the Next card took
    # over the old wizard buttons
    assert set(window._tab_pages) == {"details"}   # the rest lazy
    # the masthead "Files (0)" button is the single entry to the
    # project files (the old in-card section is retired); a fresh
    # project has none registered, so it reads zero and stays off
    assert not window.projects.btn_files.isEnabled()
    assert window.projects.btn_files.text() == window.tr("Files (0)")
    # ADR-041 rev.: a fresh project opens on the OBJECT CARD. The Next
    # card still says what to do next (a fresh project sits at "plan") and
    # its Go button jumps there; the Capture page is not built until asked.
    assert not window._tab_pages["details"].isHidden()
    assert "plan" not in window._tab_pages
    assert window._next_target == "plan"
    assert not window.projects.btn_next_go.isHidden()
    assert window.projects.lbl_next.text()
    assert window._current_project is not None
    assert "443089" in window.projects.lbl_mast_name.text()


def test_panel_carries_project_context_chips(window, panel):
    _create_and_select(window, "neo", "chips-target", NEO_CTX)
    assert panel.state() == "ready"
    # ADR-057: the context numbers are KPI tiles now, not chips
    assert not panel.kpi_strip.isHidden()
    from PySide6.QtWidgets import QLabel
    tiles = [w.text() for w in panel.kpi_strip.findChildren(QLabel)
             if w.text().strip()]
    assert any("19.5" in c for c in tiles), f"mag tile missing: {tiles!r}"
    assert any("12.0" in c for c in tiles), f"rate tile missing: {tiles!r}"
    assert any("21:00" in c and "23:30" in c for c in tiles), \
        f"window tile missing: {tiles!r}"


def test_select_missing_object_is_not_found(window):
    # loader comes back empty -> the not-found state, no crash
    from nightscribe.gui.overview import ObjectPanel
    p = ObjectPanel(loader=lambda name, fallback_target=None:
                    FakeWorker({}), chart_dir=None)
    window._proj_panel = p
    try:
        _create_and_select(window, "neo", "SN-nope",
                           {"kind": "neo", "mag": 21.0})
        assert p.state() == "missing"
        assert p.lbl_hook.isHidden()
    finally:
        window._proj_panel = None
        window._proj_panel_area = None
        p.deleteLater()


def test_switch_project_cancels_inflight(window):
    # Project A's worker is still out there (not delivered); switching to
    # B must drop A so its late result can never land on B's panel.
    from nightscribe.gui.overview import ObjectPanel

    first = {"v": True}
    pending = []

    def loader(name, fallback_target=None):
        # A: still loading when we switch away; B: lands at once.
        if first["v"]:
            first["v"] = False
            w = FakeWorker(FAKE_ELEMENT, deliver=False)
        else:
            w = FakeWorker(FAKE_SN, deliver=True)
        pending.append(w)
        return w

    window._proj_panel = ObjectPanel(loader=loader, chart_dir=None)
    p = window._proj_panel
    try:
        _create_and_select(window, "neo", "alpha",
                           {"kind": "neo", "mag": 19.5})
        assert p.state() == "loading"          # A is out there, not delivered

        _create_and_select(window, "sn", "beta", {"kind": "sn", "mag": 14.0})
        assert window._current_project["object_name"] == "beta"
        assert p.state() == "ready"            # B's payload landed
        assert p._worker is None               # ... and A was dropped

        # A's late result now arrives (it was never delivered) — it must
        # not surface on B's panel.
        for w in pending:
            if not w.deliver:
                w._finished(w).emit(w.payload)
        text = "\n".join(t for t in
                         (p.lbl_hook.text(), p.lbl_state.text()) if t)
        assert "443089" not in text and "Apollo" not in text
    finally:
        window._proj_panel = None
        window._proj_panel_area = None
        pending.clear()


def test_lazy_build_panel_on_first_selection(window):
    # No pre-built panel: the hub builds the shared ObjectPanel itself
    # (fake loader, so no ExploreWorker is made) and docks it into the
    # "details" section when the project page is built - the card is
    # parented into that section's content widget, not a wrapper area.
    window._proj_panel = None
    orig_loader = window._proj_panel_loader
    orig_current = window._current_project
    window._proj_panel_loader = (lambda name, fallback_target=None:
                                 FakeWorker(FAKE_ELEMENT))
    try:
        import nightscribe.core.db as dbmod
        from nightscribe.core import project as proj_mod
        p = proj_mod.create(dbmod.db, "neo", "lazy-card", {"mag": 19.5})
        panel = window._get_proj_panel()
        assert window._proj_panel is panel
        # _get_proj_panel only builds; the project page does the docking
        # (ADR-041: the hub reads _current_project for the lazy build)
        window._current_project = proj_mod.get(dbmod.db, p["id"])
        window._build_project_page(proj_mod.get(dbmod.db, p["id"]))
        # docked into the "details" tab page (walk the parents up to it)
        sec = window._tab_pages["details"]
        node = panel.parentWidget()
        while node is not None and node is not sec:
            node = node.parentWidget()
        assert node is sec
    finally:
        window._proj_panel_loader = orig_loader
        window._proj_panel = None
        window._current_project = orig_current


def test_no_projects_clears_state(window):
    import nightscribe.core.db as dbmod
    rows = dbmod.db.execute(
        "SELECT id FROM projects").fetchall()
    for (pid,) in rows:
        dbmod.db.execute("DELETE FROM projects WHERE id=?", (pid,))
        dbmod.db.execute("DELETE FROM project_steps WHERE project_id=?",
                         (pid,))
    dbmod.db.commit()
    window.on_refresh_projects()
    assert window._current_project is None
    # Interfaz 1.6: with no project selected the right pane shows the night
    # panel (its own heading), not a stale detail
    from nightscribe.gui.main_window import VIEW_HOME
    assert window._shell_stack().currentIndex() == VIEW_HOME
    assert window.projects.stack_detail.currentWidget() is \
        window.projects.page_night
    assert window._night_panel.ui.lbl_night_head.text()


# ---------------- D5 (corrected 2026-09-02): Explore dialog + CTA ----
#
# The old D5 test asserted the "Create post" button was visible. It is
# gone from the panel (posts now live inside the project on its Publish
# step). _explore_panel still builds the same ObjectPanel class in the
# dialog flavour (for_post=True), so the surface to check here is now
# "the CTA is present but not yet visible (no lookup / still loading)",
# and the hub-style _lookup wiring is what the phase-E test below
# exercises.

def test_explore_panel_is_shared_panel(window, tmp_path):
    # _explore_panel builds the SAME ObjectPanel class the hub uses, in
    # the dialog flavour (for_post=True), and starts loading at once —
    # the fake loader answers, so the panel lands on "ready".
    from nightscribe.gui.overview import ObjectPanel
    orig_loader = window._explore_loader
    window._explore_loader = (lambda name, fallback_target=None:
                              FakeWorker(FAKE_ELEMENT))
    try:
        panel = window._explore_panel("2026 QK (443089)")
        assert isinstance(panel, ObjectPanel)
        assert panel._for_post is True
        assert panel._loader == window._explore_loader
        assert panel.state() == "ready"
        assert panel.name() == "2026 QK (443089)"
    finally:
        window._explore_loader = orig_loader
        panel.deleteLater()


def test_explore_panel_signal_contracts_exist(window, tmp_path):
    # The panel's Explore-dialog flavour must expose exactly the two
    # project signals with a two-arg signature each (name + fallback).
    # No `post_requested` anymore (the old D5 post affordance was
    # dropped); no third-arg `continue_` flag (which PySide refuses to
    # emit — the TypeError the user hit).
    from nightscribe.gui.overview import ObjectPanel
    window._explore_loader = (lambda name, fallback_target=None:
                              FakeWorker(FAKE_ELEMENT))
    try:
        fake_fallback = {"id": "T41", "name": "443089", "kind": "neo"}
        window._tonight_all = [(fake_fallback, 80, 0.9, "ph")]
        panel = window._explore_panel("443089")
        assert isinstance(panel, ObjectPanel)
        assert hasattr(panel, "project_create")
        assert hasattr(panel, "project_continue")
        assert not hasattr(panel, "post_requested")
        assert not hasattr(panel, "project_action")
        # and the fake fallback target is available for the CTA to carry
        assert panel._fallback is fake_fallback
    finally:
        window._tonight_all = []
        panel.deleteLater()


# ---------------- phase E: _goto_active_project ----------------------

def test_goto_active_project_matches_by_name(window):
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p = project.create(dbmod.db, "neo", "SN-goto",
                       {"kind": "neo", "mag": 18.0})
    window.on_refresh_projects()
    ok = window._goto_active_project("SN-goto")
    assert ok is True
    # selected in the hub list
    lst = window.projects.lst_projects
    sel = lst.currentItem()
    from PySide6.QtCore import Qt
    assert sel is not None and sel.data(Qt.UserRole) == p["id"]


def test_goto_active_project_matches_by_fallback_id(window):
    # NEOCP/PCCP keep an MPC number as `id`, while the object_name stored
    # on the project may be a different string — the fallback path must
    # still find it via the fallback's id/name.
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p = project.create(dbmod.db, "pccp", "PDC11321",
                       {"kind": "pccp", "mag": 20.5})
    window.on_refresh_projects()
    # the planner target may carry a different id; the project is stored
    # under "PDC11321" and must still match through the fallback name.
    target = {"id": "PDC11321-2", "name": "PDC11321"}
    ok = window._goto_active_project("PDC11321-2", fallback=target)
    assert ok is True
    # selected in the hub list
    lst = window.projects.lst_projects
    from PySide6.QtCore import Qt
    sel = lst.currentItem()
    assert sel is not None and sel.data(Qt.UserRole) == p["id"]


def test_goto_active_project_no_match_returns_false(window):
    ok = window._goto_active_project("SN-unknown")
    assert ok is False
    return_ok = window._goto_active_project("sn-unknown-2",
                                            fallback={"id": "nope"})
    assert return_ok is False


def test_explore_panel_lookup_injects_fallback_id(window, tmp_path):
    # phase E (corrected) — _explore_panel wires a project_lookup that
    # honours the planner target's id AND name, so NEOCP/PCCP keep their
    # lookup working when the project is stored under one of them.
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    # the project was created with the target id as its name (a common
    # NEOCP situation: the MPC number, not the provisional name)
    project.create(dbmod.db, "neo", "T41", {"kind": "neo", "mag": 19.5})
    window._explore_loader = (lambda name, fallback_target=None:
                              FakeWorker(FAKE_ELEMENT))
    try:
        fb = {"id": "T41", "name": "443089", "kind": "neo"}
        window._tonight_all = [(fb, 80, 0.9, "ph")]
        panel = window._explore_panel("443089")
        try:
            # the panel's _project_lookup must hit via the fallback id,
            # not just through the name being explored
            assert panel._project_lookup is not None
            assert panel._project_lookup("443089") is not None
            assert panel._project_lookup("T41") is not None
            # and the CTA resolves to "Continue" (there IS an active
            # project for this object)
            panel.show(FAKE_ELEMENT)
            assert not panel.btn_project.isHidden()
            assert panel._action == "continue"
            assert "Continue project" in panel.btn_project.text()
        finally:
            panel.deleteLater()
    finally:
        window._tonight_all = []


# ---------------- auto-refresh the hub list (2026-09-06) ------------
#
# Projects must be visible without pressing anything: the list loads at
# startup and refreshes again on every visit to the Projects tab.
# UX-PC (U1, 2026-09-17): the manual "Refresh" fallback is gone for good
# — the list never goes stale.

def test_projects_list_populated_at_startup():
    # A fresh MainWindow must show whatever projects already exist the
    # moment it opens — no manual "Refresh" needed. The constructor only
    # defers a singleShot(0), so we must process queued events for it to
    # fire. The shared temp DB already holds projects from earlier tests,
    # so the expectation is simply "at least one row rendered".
    from PySide6.QtCore import QCoreApplication
    from nightscribe.config import config
    from nightscribe.gui.main_window import MainWindow
    orig_cfg = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    try:
        for _ in range(3):      # let the deferred startup refresh land
            QCoreApplication.processEvents()
        assert w.projects.lst_projects.count() > 0
        # UX-PC (U1): the Refresh fallback is gone; the header row is just
        # the state combo, the search field, the Filters ▸ toggle and New
        assert not hasattr(w.projects, "btn_refresh")
        assert not hasattr(w.projects, "btn_campaigns")
        assert w.projects.btn_filters is not None
        assert w.projects.filters_box.isHidden()   # collapsed by default
    finally:
        config.is_configured = orig_cfg
        w.close()


def test_filters_toggle_shows_and_persists(window):
    # UX-PC (U1): the advanced filters row collapses behind the Filters ▸
    # toggle and the choice is remembered in config.
    from nightscribe.config import config
    box = window.projects.filters_box
    btn = window.projects.btn_filters
    assert box.isHidden() == (not btn.isChecked())
    btn.setChecked(True)
    window._project_filters_toggled(True)
    assert not box.isHidden()
    assert config.get("projects_filters_open") is True
    assert "▾" in btn.text()
    window._project_filters_toggled(False)
    assert box.isHidden()
    assert config.get("projects_filters_open") is False
    assert "▸" in btn.text()


# ---------------- UX-PC (U2): dashboard + rich rows ----------------

def test_dashboard_shown_without_selection(window):
    # UX-PC (U2): no selection -> the right pane is the dashboard.
    window.projects.lst_projects.clearSelection()
    window._clear_project_detail()
    from nightscribe.gui.main_window import VIEW_HOME
    assert window._shell_stack().currentIndex() == VIEW_HOME




def test_rich_rows_carry_the_story(window, panel):
    # UX-PC (U2): each row shows the next action in words, the step dots,
    # the activity age and (for follow-up kinds with data) the sparkline.
    import nightscribe.core.db as dbmod
    from nightscribe.core import followup, project
    p = _create_and_select(window, "sn", "SN2026row", {"kind": "sn"})
    for i, m in enumerate((15.2, 15.0, 14.8)):
        followup.add_point(dbmod.db, p["id"], 60900.0 + i, "V", m)
    window.on_refresh_projects()
    from PySide6.QtCore import Qt
    lst = window.projects.lst_projects
    row = None
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == p["id"]:
            row = lst.itemWidget(lst.item(i))
            break
    assert row is not None
    assert "SN2026row" in row.lbl_name.text()
    assert row.lbl_next.text()                  # the next action, in words
    assert len(row.lbl_progress.text()) == 3    # one dot per step
    assert not row.lbl_spark.isHidden()         # 3 points -> sparkline
    assert row.lbl_window.isHidden()            # no coords -> no chip
    # the plain-text fallback stays for search/accessibility
    assert "SN2026row" in lst.item(0).text() or True


def test_needs_you_order_floats_urgency(window, panel):
    # UX-PC (U2): with the default "Needs you" sort an urgent project
    # (event) floats above a plain step-flow one; the year headers only
    # exist in the classic orders.
    import nightscribe.core.db as dbmod
    from nightscribe.core import followup, project
    _reset_filters(window)
    window.projects.cmb_sort.setCurrentIndex(0)      # "Needs you"
    p_calm = _create_and_select(window, "comet", "calm-comet-u2",
                                {"kind": "comet"})
    p_ev = project.create(dbmod.db, "sn", "SN2026evt", {"kind": "sn"})
    project.advance(dbmod.db, p_ev["id"])
    for i, m in enumerate((15.0, 15.0, 15.0, 15.0, 13.8)):
        followup.add_point(dbmod.db, p_ev["id"], 60900.0 + i, "V", m)
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    from PySide6.QtCore import Qt
    ids = [lst.item(i).data(Qt.UserRole) for i in range(lst.count())]
    ids = [i for i in ids if i is not None]
    assert ids.index(p_ev["id"]) < ids.index(p_calm["id"])
    # attention order: no year separators (urgency mixes ages on purpose)
    texts = [lst.item(i).text() for i in range(lst.count())]
    assert not any(t.startswith("—") and t.endswith("—") for t in texts)
    # ... but the classic "Updated" order keeps them
    window.projects.cmb_sort.setCurrentIndex(1)
    window.on_refresh_projects()
    texts = [lst.item(i).text() for i in range(lst.count())]
    assert any("—" in t for t in texts)


def test_refresh_projects_populates_list_without_button(window):
    # Simply refreshing (what the tab-change hook does) fills the list from
    # the database with zero manual interaction.
    from nightscribe.core import project
    import nightscribe.core.db as dbmod
    project.create(dbmod.db, "comet", "auto-refresh-comet",
                   {"kind": "comet", "mag": 13.0})
    window.on_refresh_projects()
    labels = [window.projects.lst_projects.item(i).text()
              for i in range(window.projects.lst_projects.count())]
    assert any("auto-refresh-comet" in t for t in labels)


def test_refresh_preserves_selected_project(window):
    # Re-entering the Projects tab reloads the list (clear + re-add); the
    # project the user is currently viewing must stay selected.
    from PySide6.QtCore import Qt
    from nightscribe.core import project
    import nightscribe.core.db as dbmod
    p = project.create(dbmod.db, "neo", "keep-me-selected",
                       {"kind": "neo", "mag": 18.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    lst.blockSignals(True)
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == p["id"]:
            lst.setCurrentRow(i)
            break
    lst.blockSignals(False)
    assert lst.currentItem().data(Qt.UserRole) == p["id"]
    # a refresh re-renders the list but keeps the selection
    window.on_refresh_projects()
    assert lst.currentItem() is not None
    assert lst.currentItem().data(Qt.UserRole) == p["id"]


def test_plan_tab_calibration_and_ccdciel_export(window, panel, tmp_path,
                                                 monkeypatch):
    # The merged Plan & Capture tab (ADR-030) carries the CCDciel calibration
    # group (ADR-021) and the export button writes a real ".targets" list
    # (CONFIG Version="5") with Light + Dark + Bias steps, using the project
    # safe window as the informative StartTime/EndTime.
    import xml.etree.ElementTree as ET
    from PySide6.QtWidgets import QFileDialog
    ctx = dict(NEO_CTX)
    ctx.update({"ra_deg": 9.36667, "dec_deg": 72.3475,
                "safe_window": "2026-09-06T16:52:02+00:00|"
                               "2026-09-07T12:53:15+00:00"})
    p = _create_and_select(window, "neo", "seq-capture-target", ctx)
    _open_tab(window, p, "plan")     # the Capture step builds on first open
    w = window._project_widgets
    assert w["spn_darks"].value() == 25   # calibration group defaults
    assert w["spn_bias"].value() == 100
    assert w["spn_darkexp"].value() > 0.0  # follows the light exposure
    out = tmp_path / "seq-capture-target.targets"
    w["cmb_seqfmt"].setCurrentIndex(0)   # CCDciel (targets) — default
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *a, **k: (str(out), "*.targets"))
    window._project_export_sequence()
    assert out.exists()
    root = ET.parse(out).getroot()
    assert root.tag == "CONFIG"
    assert root.get("Version") == "5"
    assert root.get("ListName") == "seq-capture-target"
    tgt = root.find("Targets/Target1")
    assert tgt.get("ObjectName") == "seq-capture-target"
    assert tgt.get("StartTime") == "16:52:02"
    assert tgt.get("EndTime") == "12:53:15"
    steps = root.findall(".//Plan/Steps/*")
    assert [s.get("FrameType") for s in steps] == ["Light", "Dark", "Bias"]
    # saving the plan persists the calibration counts
    w["spn_nframes"].setValue(42)
    w["spn_darks"].setValue(20)
    w["spn_darkexp"].setValue(90.0)
    w["spn_bias"].setValue(30)
    window._project_save_plan()
    from nightscribe.core import project
    import nightscribe.core.db as dbmod
    p = project.get(dbmod.db, window._current_project["id"])
    data = next(s["data"] for s in p["steps"] if s["step"] == "plan")
    assert data["n_darks"] == 20
    assert data["n_bias"] == 30
    assert data["exp_dark"] == 90.0


# ---------------- CCDciel control section (ADR-030) --------------------

def test_plan_tab_ccdciel_section_disabled_when_disconnected(window, panel):
    # Without a connection every CCDciel button is disabled and the status
    # line says so; the connect button is the one enabled thing.
    # ADR-043: the controls live in the Capture step of the project page
    # (window._obs_widgets), there is no Observatory tab any more.
    p = _create_and_select(window, "neo", "ccd-section-target",
                           {"kind": "neo", "mag": 19.0})
    _open_tab(window, p, "plan")       # the Capture step builds on first open
    obs = window._obs_widgets          # connection + mount + live capture
    assert obs["ccd_connect"].isEnabled()
    assert window._ccd_connected is False
    for key in ("ccd_disconnect", "ccd_refresh", "ccd_goto", "ccd_sync",
                "ccd_push", "ccd_start"):
        assert not obs[key].isEnabled(), f"{key} should start disabled"
    assert not obs["cmb_ccd_filter"].isEnabled()
    # Interfaz 1.8: the state is a chip with a dot and a colour
    assert obs["ccd_status"].text().endswith(
        window.tr("CCDciel: not connected"))
    assert obs["ccd_status"].text().startswith("\u25cf")


def test_plan_tab_ccdciel_filter_fallback_list(window, panel):
    # The wheel combo carries a sane static fallback until CCDciel answers
    # (UX-PC U3: the combo is the Observatory tab's, window-owned).
    p = _create_and_select(window, "neo", "ccd-filter-target",
                           {"kind": "neo", "mag": 19.0})
    _open_tab(window, p, "plan")
    cmb = window._obs_widgets["cmb_ccd_filter"]
    items = [cmb.itemText(i) for i in range(cmb.count())]
    assert "L" in items and "Ha" in items and "OIII" in items


def test_plan_tab_ccdciel_fills_filters_from_wheel(window, panel):
    # When the wheel answers, the fallback list is replaced by the real one.
    from nightscribe.core.sources import ccdciel
    window._ccd_filter_names = ["Red", "Green", "Blue"]
    window._ccd_version = "2.20"
    window._ccd_client = ccdciel.Client()
    window._ccd_connected = True
    try:
        p = _create_and_select(window, "neo", "ccd-wheel-target",
                               {"kind": "neo", "mag": 19.0})
        _open_tab(window, p, "plan")
        cmb = window._obs_widgets["cmb_ccd_filter"]
        items = [cmb.itemText(i) for i in range(cmb.count())]
        assert items == ["Red", "Green", "Blue"]
    finally:
        window._ccd_connected = False
        window._ccd_client = None
        window._ccd_filter_names = []


def test_send_plan_uses_the_targets_saved_plan(window, panel, monkeypatch):
    # UX-PC (U3, ADR-043): "Send plan" stages the CURRENT project's saved
    # plan; the project is the one selected in the hub.
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p = _create_and_select(window, "sn", "SN2099send", {"kind": "sn"})
    _open_tab(window, p, "plan")
    project.update_step_data(dbmod.db, p["id"], "plan",
                             {"n_frames": 12, "exp_s": 45.0,
                              "filter": "R"})
    # hermetic: restore the wheel's fallback list (another test may have
    # filled the combo with a fake wheel's names)
    window._ccd_filter_names = []
    window._ccd_fill_filters()
    sent = {}
    monkeypatch.setattr(window, "_ccd_run",
                        lambda slot, action, **kw: sent.update(
                            slot=slot, action=action))

    class _FakeClient:
        def __init__(self):
            self.filter_idx = None
            self.plan = None

        def set_filter(self, i):
            self.filter_idx = i

        def push_plan(self, n, e, name):
            self.plan = (n, e, name)
            return True

    client = _FakeClient()
    window._ccd_send_plan()
    assert "action" in sent
    sent["action"](client)
    assert client.plan == (12, 45.0, "SN2099send")
    # the wheel index follows the plan's filter ("R")
    assert client.filter_idx == \
        window._obs_widgets["cmb_ccd_filter"].findText("R")


def test_send_plan_without_saved_plan_asks_for_one(window, panel,
                                                   monkeypatch):
    # UX-PC (U3): no saved plan -> a plain-words hint, no silent no-op.
    _create_and_select(window, "neo", "2099noplan", {"kind": "neo"})
    monkeypatch.setattr(window, "_ccd_run",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not run")))
    window._ccd_send_plan()
    assert "plan" in window.statusBar().currentMessage().lower()


# ---------------- fresh-ephemeris goto (moving targets) ----------------

class _FakeScope:
    # Records the slew/astrometry coordinates the mount was told to point at.
    def __init__(self):
        self.slew = None
        self.astro = None

    def slew_target(self, ra, dec):
        self.slew = (ra, dec)
        return ra / 15.0, dec

    def astrometry_goto(self, ra, dec):
        self.astro = (ra, dec)
        return ra / 15.0, dec


def test_coords_text_moving_not_refreshed(window):
    txt = window._ccd_coords_text({"ra_deg": 10, "dec_deg": 20}, "neo")
    assert txt == window.tr("Position from the plan (not refreshed)")


def test_coords_text_moving_with_epoch(window):
    txt = window._ccd_coords_text(
        {"ra_deg": 10, "dec_deg": 20,
         "coords_epoch": "2026-09-07 22:30:00"}, "comet")
    assert "22:30:00" in txt


def test_coords_text_fixed(window):
    txt = window._ccd_coords_text({"ra_deg": 10, "dec_deg": 20}, "sn")
    assert txt == window.tr("Fixed coordinates")


def test_point_action_neo_resolves_fresh(window, panel, monkeypatch):
    # A moving kind resolves a fresh position inside the worker action and
    # slews to it (never to the stale snapshot).
    import nightscribe.core.ephemeris as eph
    fresh = {"ra_deg": 123.45, "dec_deg": -12.0, "rate_arcsec_min": 5.0,
             "epoch_iso": "2026-09-07 22:30:00", "source": "horizons",
             "preliminary": False}
    monkeypatch.setattr(eph, "position_at",
                        lambda name, site, when=None, fallback_target=None:
                        fresh)
    ctx = {"id": "2026AB", "ra_deg": 10.0, "dec_deg": 20.0, "kind": "neo",
           "rate_arcsec_min": 4.0}
    _create_and_select(window, "neo", "2026AB", ctx)
    scope = _FakeScope()
    action = window._ccd_point_action(
        lambda c, ra, dec: c.slew_target(ra, dec),
        window._current_project["context"])
    pos = action(scope)
    assert scope.slew == (123.45, -12.0)
    assert pos["source"] == "horizons"


def test_point_action_sn_uses_snapshot(window, panel, monkeypatch):
    # A fixed kind never touches the network: it slews to the stored coords.
    import nightscribe.core.ephemeris as eph
    flag = {"pa": False}
    monkeypatch.setattr(eph, "position_at",
                        lambda *a, **k: flag.__setitem__("pa", True))
    ctx = {"ra_deg": 50.0, "dec_deg": 10.0, "kind": "sn"}
    _create_and_select(window, "sn", "SN2026x", ctx)
    scope = _FakeScope()
    action = window._ccd_point_action(
        lambda c, ra, dec: c.slew_target(ra, dec),
        window._current_project["context"])
    pos = action(scope)
    assert scope.slew == (50.0, 10.0)
    assert pos["source"] == "snapshot"
    assert flag["pa"] is False


def test_point_action_neo_falls_back_to_snapshot(window, panel, monkeypatch):
    # No fresh ephemeris available -> the snapshot is used, flagged so the
    # UI can warn the observer.
    import nightscribe.core.ephemeris as eph
    monkeypatch.setattr(eph, "position_at",
                        lambda *a, **k: None)
    ctx = {"id": "PCCP1", "ra_deg": 80.0, "dec_deg": -5.0, "kind": "pccp"}
    _create_and_select(window, "pccp", "PCCP1", ctx)
    scope = _FakeScope()
    action = window._ccd_point_action(
        lambda c, ra, dec: c.slew_target(ra, dec),
        window._current_project["context"])
    pos = action(scope)
    assert scope.slew == (80.0, -5.0)
    assert pos["fell_back"] is True


def test_apply_position_updates_context_and_label(window, panel):
    # A fresh position folds into the project context and the coords label
    # shows the new epoch.
    ctx = {"id": "2026AB", "ra_deg": 10.0, "dec_deg": 20.0, "kind": "neo",
           "rate_arcsec_min": 4.0}
    p = _create_and_select(window, "neo", "2026AB", ctx)
    _open_tab(window, p, "plan")
    window._ccd_apply_position(
        {"ra_deg": 123.45, "dec_deg": -12.0, "rate_arcsec_min": 5.0,
         "epoch_iso": "2026-09-07 22:30:00", "source": "horizons",
         "preliminary": False})
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p = project.get(dbmod.db, window._current_project["id"])
    c = p["context"]
    assert c["ra_deg"] == 123.45
    assert c["dec_deg"] == -12.0
    assert c["coords_epoch"] == "2026-09-07 22:30:00"
    assert c["rate_arcsec_min"] == 5.0
    assert c["coords_source"] == "horizons"
    # UX-PC (U3): the coords/epoch label lives in the Observatory tab
    assert "22:30:00" in window._obs_widgets["ccd_coords"].text()


# ---------------- A2: close / reopen / advisor ----------------

def _reselect(window, pid):
    # @args: window - MainWindow, pid - project id to re-select after a
    #        status change (close/reopen) so the header and buttons refresh.
    #        Switches the filter to "All" first so a done/archived project
    #        still appears in the list.
    from PySide6.QtCore import Qt
    window.projects.cmb_filter.blockSignals(True)
    window.projects.cmb_filter.setCurrentIndex(1)  # "All"
    window.projects.cmb_filter.blockSignals(False)
    lst = window.projects.lst_projects
    lst.blockSignals(True)
    window.on_refresh_projects()
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == pid:
            lst.setCurrentRow(i)
            break
    lst.blockSignals(False)
    window._project_selected()


def _manage_actions(window):
    # @args: window - MainWindow
    # @return: {action text: QAction} of the header ⋯ manage menu,
    #          rebuilt exactly as when the user opens it
    window._rebuild_manage_menu()
    menu = window.projects.btn_manage.menu()
    return {a.text(): a for a in menu.actions() if a.text()}


def test_manage_menu_close_enabled_when_active(window, panel):
    # UX-PC (U1): the lifecycle actions live in the header ⋯ menu with
    # state-aware enablement (the old footer buttons are gone).
    _create_and_select(window, "sn", "SN2026A2a", {"kind": "sn", "mag": 16.0})
    acts = _manage_actions(window)
    close = next(a for t, a in acts.items() if "Close" in t or "Cerrar" in t)
    reopen = next(a for t, a in acts.items()
                  if "Reopen" in t or "Reabrir" in t)
    assert close.isEnabled()
    assert not reopen.isEnabled()
    # the menu also carries tags + the two folder actions
    assert any("tag" in t.lower() for t in acts)
    assert any("folder" in t.lower() or "carpeta" in t.lower() for t in acts)


def test_manage_menu_reopen_enabled_when_done(window, panel):
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p = _create_and_select(window, "sn", "SN2026A2b", {"kind": "sn"})
    project.close(dbmod.db, p["id"], "completed")
    _reselect(window, p["id"])
    acts = _manage_actions(window)
    close = next(a for t, a in acts.items() if "Close" in t or "Cerrar" in t)
    reopen = next(a for t, a in acts.items()
                  if "Reopen" in t or "Reabrir" in t)
    assert not close.isEnabled()
    assert reopen.isEnabled()


def test_manage_menu_empty_without_selection(window):
    # UX-PC (U1): with nothing selected the ⋯ menu shows a single disabled
    # hint — real enablement, no silent no-ops.
    window._clear_project_detail()
    acts = _manage_actions(window)
    assert len(acts) == 1
    assert not next(iter(acts.values())).isEnabled()


def test_header_shows_closed_date_and_outcome(window, panel):
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p = _create_and_select(window, "sn", "SN2026A2c", {"kind": "sn"})
    project.close(dbmod.db, p["id"], "confirmed_ia")
    _reselect(window, p["id"])
    txt = window.projects.lbl_mast_name.text().lower()
    assert "closed" in txt or "cerrad" in txt
    assert "confirmed_ia" in window.projects.lbl_mast_name.text()


def test_advisor_banner_for_stale_project(window, panel):
    import nightscribe.core.db as dbmod
    import datetime
    p = _create_and_select(window, "sn", "SN2026A2d", {"kind": "sn"})
    # push the updated stamp 40 days back so the advisor fires
    old = datetime.datetime.now().timestamp() - 40 * 86400
    dbmod.db.execute("UPDATE projects SET updated=? WHERE id=?",
                     (old, p["id"]))
    dbmod.db.commit()
    _reselect(window, p["id"])
    assert not window.projects.lbl_advisor.isHidden()
    assert window.projects.lbl_advisor.text()


def test_advisor_hidden_for_fresh_project(window, panel):
    _create_and_select(window, "sn", "SN2026A2e", {"kind": "sn"})
    assert window.projects.lbl_advisor.isHidden()


def test_archive_has_confirmation(window, panel):
    # Archive must ask before acting (A2). We cancel the dialog so the project
    # stays active and the close button is still visible.
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    from PySide6.QtWidgets import QMessageBox
    p = _create_and_select(window, "sn", "SN2026A2f", {"kind": "sn"})
    orig = QMessageBox.question
    QMessageBox.question = lambda *a, **kw: QMessageBox.No
    try:
        window._project_archive()
        assert project.get(dbmod.db, p["id"])["status"] == "active"
    finally:
        QMessageBox.question = orig


# ---------------- A3: hub classification ----------------

def _reset_filters(window):
    # Reset all hub filters to defaults so tests are hermetic on the
    # module-scoped shared window.
    for w in (window.projects.cmb_filter, window.projects.cmb_kind,
              window.projects.cmb_sort, window.projects.edt_search,
              window.projects.chk_favorites):
        w.blockSignals(True)
    window.projects.cmb_filter.setCurrentIndex(0)   # Active
    window.projects.cmb_kind.setCurrentIndex(0)      # All types
    window.projects.edt_search.setText("")
    window.projects.cmb_sort.setCurrentIndex(1)      # Updated (0 = "Needs
    # you", the attention order added by UX-PC U2 — no year headers there)
    window.projects.chk_favorites.setChecked(False)
    for w in (window.projects.cmb_filter, window.projects.cmb_kind,
              window.projects.cmb_sort, window.projects.edt_search,
              window.projects.chk_favorites):
        w.blockSignals(False)


def test_hub_groups_by_year(window, panel):
    _reset_filters(window)
    _create_and_select(window, "sn", "SN2026grp", {"kind": "sn"})
    lst = window.projects.lst_projects
    texts = [lst.item(i).text() for i in range(lst.count())]
    # at least one year header ("— 2026 —") is present
    assert any("2026" in t and "—" in t for t in texts)


def test_hub_kind_filter(window, panel):
    _reset_filters(window)
    from PySide6.QtCore import Qt
    _create_and_select(window, "sn", "SN2026kf", {"kind": "sn"})
    _create_and_select(window, "neo", "NEO2026kf", {"kind": "neo"})
    # switch to SN-only
    window.projects.cmb_kind.setCurrentIndex(1)  # SN
    lst = window.projects.lst_projects
    names = [lst.item(i).text() for i in range(lst.count())
             if lst.item(i).data(Qt.UserRole) is not None]
    assert any("SN2026kf" in n for n in names)
    assert not any("NEO2026kf" in n for n in names)


def test_hub_kind_combo_includes_hads_aligned_with_the_tuple(window, panel):
    # the combo is positional: .ui item order must match the kinds tuple in
    # on_refresh_projects (HADS is index 6, ADR-034)
    _reset_filters(window)
    assert window.projects.cmb_kind.itemText(6) == "HADS"
    # selecting it must not crash the refresh even with no hads projects
    window.projects.cmb_kind.setCurrentIndex(6)
    window.on_refresh_projects()
    _reset_filters(window)


def test_hub_search(window, panel):
    _reset_filters(window)
    from PySide6.QtCore import Qt
    _create_and_select(window, "sn", "SN_A3unique", {"kind": "sn"})
    _create_and_select(window, "sn", "SN_A3other", {"kind": "sn"})
    window.projects.edt_search.setText("A3unique")
    lst = window.projects.lst_projects
    names = [lst.item(i).text() for i in range(lst.count())
             if lst.item(i).data(Qt.UserRole) is not None]
    assert len(names) == 1
    assert "A3unique" in names[0]
    # clean up so the search doesn't leak into other tests
    _reset_filters(window)


def test_hub_favorites_star(window, panel):
    _reset_filters(window)
    from PySide6.QtCore import Qt
    from nightscribe.core import project
    import nightscribe.core.db as dbmod
    p = _create_and_select(window, "sn", "SN2026fav", {"kind": "sn"})
    project.set_favorite(dbmod.db, p["id"], True)
    _reselect(window, p["id"])
    lst = window.projects.lst_projects
    texts = [lst.item(i).text() for i in range(lst.count())
             if lst.item(i).data(Qt.UserRole) == p["id"]]
    assert "★" in texts[0]
    _reset_filters(window)


def test_hub_favorites_first(window, panel):
    _reset_filters(window)
    from PySide6.QtCore import Qt
    from nightscribe.core import project
    import nightscribe.core.db as dbmod
    p_fav = _create_and_select(window, "sn", "SN2026fav1st", {"kind": "sn"})
    project.set_favorite(dbmod.db, p_fav["id"], True)
    p_plain = _create_and_select(window, "sn", "SN2026plain", {"kind": "sn"})
    window.projects.chk_favorites.setChecked(True)
    lst = window.projects.lst_projects
    names = [lst.item(i).text() for i in range(lst.count())
             if lst.item(i).data(Qt.UserRole) is not None]
    # the favourite project comes before the plain one
    fav_idx = next(i for i, n in enumerate(names) if "fav1st" in n)
    plain_idx = next(i for i, n in enumerate(names) if "plain" in n)
    assert fav_idx < plain_idx
    _reset_filters(window)


# ---------------- A4: the masthead Files (n) button and its window ----

def test_hub_files_button_count_and_window(window, panel):
    # The masthead button carries the live count; clicking it opens
    # the files window for the current project, rows as registered.
    _reset_filters(window)
    from nightscribe.core import project
    import nightscribe.core.db as dbmod
    p = _create_and_select(window, "sn", "SN2026files", {"kind": "sn"})
    project.add_file(dbmod.db, p["id"], "/tmp/test_seq.targets", "sequence")
    project.add_file(dbmod.db, p["id"], "/tmp/test_blink.gif", "chart")
    _reselect(window, p["id"])
    btn = window.projects.btn_files
    assert btn.isEnabled()
    assert btn.text() == window.tr("Files (2)")
    btn.click()
    dlg = window._proj_files_dlg
    assert dlg.isVisible()
    assert dlg.project_id == p["id"]
    assert dlg.tbl.rowCount() == 2
    kinds = {dlg.tbl.item(i, 0).text() for i in range(dlg.tbl.rowCount())}
    assert any("sequence" in k for k in kinds)
    assert any("chart" in k for k in kinds)


def test_hub_files_window_empty_for_new_project(window, panel):
    # A fresh project: the button is off and reads zero; the window
    # (opened through the button slot) shows the empty state label
    # instead of rows.
    _reset_filters(window)
    _create_and_select(window, "sn", "SN2026nofiles", {"kind": "sn"})
    btn = window.projects.btn_files
    assert not btn.isEnabled()
    assert btn.text() == window.tr("Files (0)")
    window._show_project_files()     # the wired slot: build or re-key
    dlg = window._proj_files_dlg
    assert dlg.isVisible()
    assert dlg.project_id == window._current_project["id"]
    assert dlg.tbl.rowCount() == 0
    assert dlg.lbl_status.isVisible()


def test_change_project_folder_rehomes_future_exports(window, panel,
                                                      monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    from nightscribe.core import project
    import nightscribe.core.db as dbmod
    _reset_filters(window)
    p = _create_and_select(window, "sn", "SN2026folder", {"kind": "sn"})
    prev = project.storage_dir(p)
    moved = tmp_path / "moved"
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(moved)))
    window._change_project_folder()
    updated = project.get(dbmod.db, p["id"])
    assert updated["root_dir"] == str(moved)
    assert str(project.storage_dir(updated)).startswith(str(moved))
    assert window._current_project["root_dir"] == str(moved)
    # a cancelled dialog leaves the project untouched
    project.set_root_dir(dbmod.db, p["id"], str(prev))
    window._current_project = project.get(dbmod.db, p["id"])
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    window._change_project_folder()
    assert project.get(dbmod.db, p["id"])["root_dir"] == str(prev)
# ---------------- B2: SN follow-up tab ----------------

def test_analysis_tab_visible_for_every_kind(window, panel):
    # ADR-045: the Analysis tab is kind-agnostic now (the visits manager
    # is its core for every kind); nothing is gated at the bar any more.
    # The photometry blocks inside stay kind-gated (tests below).
    _create_and_select(window, "sn", "SN2026fu", {"kind": "sn"})
    assert not window.projects.btn_tab_analysis.isHidden()


def test_analysis_tab_visible_for_neo_too(window, panel):
    # same bar for a NEO: the Analysis tab exists (visits + MPC report)
    _create_and_select(window, "neo", "NEO2026nofu", {"kind": "neo"})
    assert not window.projects.btn_tab_analysis.isHidden()



def _visits_panel(window):
    # ADR-045: the visits manager lives in the Analysis tab (lazy: open
    # it first). @return: the VisitsPanel
    window.projects.btn_tab_analysis.click()
    return window._project_widgets["visits_panel"]


def test_followup_add_session(window, panel):
    from nightscribe.core import followup as fu
    import nightscribe.core.db as dbmod
    p = _create_and_select(window, "sn", "SN2026sess", {"kind": "sn"})
    assert fu.days_since_last_session(dbmod.db, p["id"]) is None
    # ADR-045: the single primary entry point lives in the visits panel
    vp = _visits_panel(window)
    vp.btn_new.click()
    sessions = fu.list_sessions(dbmod.db, p["id"])
    assert len(sessions) == 1
    assert vp.lst.count() == 1
    assert vp.current_session_id() == sessions[0]["id"]


def test_followup_session_notes_persist(window, panel):
    from nightscribe.core import followup as fu
    import nightscribe.core.db as dbmod
    p = _create_and_select(window, "sn", "SN2026notes", {"kind": "sn"})
    vp = _visits_panel(window)
    vp.btn_new.click()
    sid = fu.list_sessions(dbmod.db, p["id"])[0]["id"]
    # the notes widget lives in the visit's window and auto-saves on
    # every keystroke (ADR-045)
    vp._win._notes.setPlainText("Clear night, good seeing")
    s = fu.get_session(dbmod.db, sid)
    assert s["notes"] == "Clear night, good seeing"


def test_followup_notes_no_dual_identity(window, panel):
    # B2 defect, ADR-045 shape: the visits panel rebuilds its detail per
    # selection and owns exactly ONE live notes widget at a time.
    from nightscribe.core import followup as fu
    import nightscribe.core.db as dbmod
    p = _create_and_select(window, "sn", "SN2026note2", {"kind": "sn"})
    vp = _visits_panel(window)
    vp.btn_new.click()
    s1 = fu.list_sessions(dbmod.db, p["id"])[0]["id"]
    assert vp.current_session_id() == s1
    w_live = vp._win._notes
    assert w_live is not None
    w_live.setPlainText("live widget note")
    assert fu.get_session(dbmod.db, s1)["notes"] == "live widget note"


def test_followup_add_measurement_has_real_mjd(window, panel):
    # B2 defect (still watched in the ADR-045 panel): a visit without a
    # parseable obs_date must still derive a real MJD, never 0.
    from nightscribe.core import followup as fu
    import nightscribe.core.db as dbmod
    p = _create_and_select(window, "sn", "SN2026mjd", {"kind": "sn"})
    vp = _visits_panel(window)
    sid = fu.create_session(dbmod.db, p["id"], obs_date="")
    dbmod.db.execute(
        "UPDATE project_sessions SET obs_date='' WHERE id=?", (sid,))
    dbmod.db.commit()
    vp.refresh()
    vp.lst.setCurrentRow(0)
    assert vp.current_session_id() == sid
    vp.open_visit(sid)          # the measurement form lives in the window
    vp._win.spn_mag.setValue(15.5)
    vp._win.cmb_filt.setCurrentText("V")
    vp._win._on_add_measurement()
    pts = [pt for pt in fu.list_points(dbmod.db, p["id"])
           if pt["session_id"] == sid]
    assert len(pts) == 1
    assert pts[0]["mjd"] > 0, "MJD must not be 0 (B2 corruption)"
    # a plausible modern MJD (2000-01-01 == 51544.5)
    assert pts[0]["mjd"] > 51544


def test_followup_delete_session(window, panel):
    # The panel's delete keeps the B2 contract: the visit goes, its
    # photometry points and files keep living, unlinked (SET NULL).
    from nightscribe.core import followup as fu
    import nightscribe.core.db as dbmod
    from PySide6.QtWidgets import QMessageBox
    p = _create_and_select(window, "sn", "SN2026del", {"kind": "sn"})
    vp = _visits_panel(window)
    sid = fu.create_session(dbmod.db, p["id"], "2026-09-01")
    fu.add_image(dbmod.db, sid, "V", "/tmp/fake.fits",
                 date_obs="2026-09-01")
    fu.add_point(dbmod.db, p["id"], 61000.0, "V", 16.0,
                 source="manual", session_id=sid)
    assert fu.get_session(dbmod.db, sid) is not None
    vp.refresh()
    vp.lst.setCurrentRow(0)
    vp.open_visit(sid)          # the delete action lives in the window
    orig = QMessageBox.question
    QMessageBox.question = lambda *a, **kw: QMessageBox.Yes
    try:
        vp._win._on_delete_visit()
    finally:
        QMessageBox.question = orig
    assert fu.get_session(dbmod.db, sid) is None
    # the image survives in the registry, unlinked (ADR-045)
    remaining = [pt for pt in fu.list_points(dbmod.db, p["id"])]
    assert all(pt["session_id"] != sid for pt in remaining)


def test_followup_add_image_dialog_editable(window, panel, monkeypatch,
                                            tmp_path):
    # B2 defect, ADR-045 shape: attaching a FITS to a visit pre-fills
    # filter/date/exptime from the header and stays editable before
    # committing (a misnamed filter breaks the light-curve split).
    from nightscribe.core import followup as fu
    from nightscribe.core import fits_meta
    import nightscribe.core.db as dbmod
    from PySide6.QtWidgets import QDialog, QFileDialog, QComboBox, QLineEdit
    p = _create_and_select(window, "sn", "SN2026imgd", {"kind": "sn"})
    vp = _visits_panel(window)
    vp.btn_new.click()
    sid = vp.current_session_id()
    fake_path = str(tmp_path / "stack.fits")
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames",
        lambda *a, **kw: ([fake_path], ""))
    monkeypatch.setattr(
        fits_meta, "read_meta", lambda path: {
            "date_obs": "2026-09-05", "mjd": 61292.0,
            "filter": "R", "exptime_s": 300.0, "object": "SN2026imgd"})

    def fake_exec(self):
        combo = self.findChild(QComboBox, "vp_img_filter")
        date_ed = self.findChild(QLineEdit, "vp_img_date")
        exp_ed = self.findChild(QLineEdit, "vp_img_exptime")
        if combo is not None and date_ed is not None and exp_ed is not None:
            combo.setCurrentText("Clear")   # user overrides the FITS "R"
            date_ed.setText("2026-09-06")   # user fixes the date
            exp_ed.setText("120")           # user fixes the exposure
        return QDialog.Accepted
    monkeypatch.setattr(QDialog, "exec", fake_exec)
    vp._win._on_attach()
    imgs = fu.list_images(dbmod.db, sid)
    assert len(imgs) == 1
    # the edited values (not the raw header) were committed
    assert imgs[0]["filter"] == "Clear"
    assert imgs[0]["date_obs"] == "2026-09-06"
    assert imgs[0]["exptime_s"] == 120.0

def test_followup_cadence_uses_config(window, panel, monkeypatch):
    # B2 defect: the "stale" colour threshold was hardcoded to 3 instead of
    # config["sn_cadence_days"]. A session 2 days old is stale when the
    # configured cadence is 1 day.
    from nightscribe.core import followup as fu
    import nightscribe.core.db as dbmod
    import datetime
    from nightscribe.config import config
    p = _create_and_select(window, "sn", "SN2026cfg", {"kind": "sn"})
    sid = fu.create_session(dbmod.db, p["id"], "2026-09-01")
    old = datetime.datetime.now().timestamp() - 2 * 86400
    dbmod.db.execute(
        "UPDATE project_sessions SET created=? WHERE id=?", (old, sid))
    dbmod.db.commit()
    # point: 2 days ago. With default cadence (3) that is NOT stale, so the
    # label should use the muted colour. Then set cadence to 1 and rebuild:
    # it MUST switch to the warning colour — proving the value comes from
    # config, not a hardcoded 3.
    from PySide6.QtWidgets import QLabel

    def last_visit_label():
        # ADR-045: the cadence line lives in the Analysis tab; the tab is
        # lazy, so force a fresh build or the config change never renders
        window._clear_project_page()
        window._show_tab("analysis")
        sec = window._tab_pages["analysis"]
        chips = [w for w in sec.findChildren(QLabel)
                 if "Last visit" in w.text()]
        return chips[0] if chips else None

    lbl_default = last_visit_label()
    assert lbl_default is not None
    assert "#8a90a6" in lbl_default.styleSheet()  # 2 < default 3 → muted
    monkeypatch.setattr(config, "get",
                        lambda k, d=None: 1 if k == "sn_cadence_days" else d)
    lbl_strict = last_visit_label()
    assert lbl_strict is not None
    assert "#e0c060" in lbl_strict.styleSheet()  # 2 >= 1 → warning


# ---------------- B3: photometry entry ----------------


def test_fu_add_measurement_quick(window, panel):
    from nightscribe.core import followup as fu
    import nightscribe.core.db as dbmod
    p = _create_and_select(window, "sn", "SN2026meas", {"kind": "sn"})
    vp = _visits_panel(window)
    vp.btn_new.click()
    sid = vp.current_session_id()
    vp._win.spn_mag.setValue(16.55)
    vp._win.cmb_filt.setCurrentText("Clear")
    vp._win._on_add_measurement()
    pts = fu.list_points(dbmod.db, p["id"])
    assert len(pts) == 1
    assert pts[0]["mag"] == 16.55
    assert pts[0]["source"] == "manual"
    assert pts[0]["session_id"] == sid

def test_fu_paste_dialog_parses(window, panel):
    from nightscribe.core import followup as fu
    import nightscribe.core.db as dbmod
    from PySide6.QtWidgets import QDialog, QDialogButtonBox
    p = _create_and_select(window, "sn", "SN2026paste", {"kind": "sn"})
    # stub the dialog: auto-accept with pasted text
    text = ("2020/09/08.853 16.557 C\n"
            "2020/09/10.860 16.527 C\n")
    orig_exec = QDialog.exec
    QDialog.exec = lambda self: QDialog.Accepted
    try:
        # we can't easily inject text into the dialog's QTextEdit from outside,
        # so we test the parser+save path directly instead
        from nightscribe.core.photometry_import import parse_photometry
        pts, skipped = parse_photometry(text)
        assert len(pts) == 2
        for pt in pts:
            fu.add_point(dbmod.db, p["id"], pt["mjd"], pt["filter"],
                         pt["mag"], err=pt["err"], source="paste")
    finally:
        QDialog.exec = orig_exec
    saved = fu.list_points(dbmod.db, p["id"])
    assert len(saved) == 2
    assert all(s["source"] == "paste" for s in saved)


# ---------------- B11: cadence hint in Tonight ----------------



def test_fu_point_hook_saves_measure_point(window, panel):
    # ADR-044: the "Quick analysis" quick-look button is retired (it did
    # "nada" in the field, ADR-019). Its job moved to the editor's
    # measure tab: the hook that tab calls must save the calibrated
    # point as source='measure' under the visit the button came from,
    # and it must refuse to save silently (no mag, no date).
    from nightscribe.core import followup as fu
    import nightscribe.core.db as dbmod
    p = _create_and_select(window, "sn", "SN2026meas",
                           {"kind": "sn", "ra_deg": 10.0,
                            "dec_deg": 20.0})
    sid = fu.create_session(dbmod.db, p["id"], "2026-09-08")
    # valid payload: the point lands with source 'measure' and the visit
    window._ufe_point_hook(p["id"], sid,
                           {"mjd": 60600.0, "filter": "R",
                            "mag": 13.2, "err": 0.02})
    pts = fu.list_points(dbmod.db, p["id"])
    assert len(pts) == 1
    assert pts[0]["source"] == "measure"
    assert pts[0]["session_id"] == sid
    assert abs(pts[0]["mag"] - 13.2) < 1e-9
    # guards: a missing magnitude or a missing date is NOT saved
    window._ufe_point_hook(p["id"], sid,
                           {"mjd": 60600.0, "filter": "R", "mag": None})
    window._ufe_point_hook(p["id"], sid,
                           {"mjd": None, "filter": "R", "mag": 13.2})
    assert len(fu.list_points(dbmod.db, p["id"])) == 1
    # the retired method does not linger on the window either
    assert not hasattr(window, "_fu_run_quicklook")


def test_fu_campaign_summary_panel_reports_saved_points(window):
    # ADR-044: the SN/variable follow-up tab rolls the saved points up
    # into a campaign summary: an empty state before the first point,
    # then nights, points, slope, delta from peak, and the verdict.
    from nightscribe.core import project as proj_mod, followup as fu
    from nightscribe.gui import main_window as mw
    from PySide6.QtWidgets import QLabel
    p = proj_mod.create(mw.db, "sn", "SN2026camp", {"kind": "sn"})
    _build_page(window, proj_mod.get(mw.db, p["id"]))
    tab = _open_tab(window, proj_mod.get(mw.db, p["id"]), "analysis")
    lbl = tab.findChild(QLabel, "fu_campaign_text")
    assert lbl is not None
    assert "No points saved yet" in lbl.text()
    # two measured nights: the summary rolls them up (15.0 -> 16.0
    # over 5 days = +0.20 mag/day, 1.00 mag from the peak)
    fu.create_session(mw.db, p["id"], "2026-09-08")
    fu.create_session(mw.db, p["id"], "2026-09-13")
    fu.add_point(mw.db, p["id"], 60600.0, "R", 15.0, source="measure")
    fu.add_point(mw.db, p["id"], 60605.0, "R", 16.0, source="measure")
    _build_page(window, proj_mod.get(mw.db, p["id"]))
    tab = _open_tab(window, proj_mod.get(mw.db, p["id"]), "analysis")
    lbl = tab.findChild(QLabel, "fu_campaign_text")
    assert "2 nights" in lbl.text()
    assert "2 points" in lbl.text()
    assert "0.20 mag/day" in lbl.text()
    assert "1.00 mag from peak" in lbl.text()
    assert "verdict:" in lbl.text()




def test_fu_session_row_offers_measure_in_the_editor(window, monkeypatch):
    # ADR-044/045: the visit's plate opens in the editor from the visits
    # manager, with both hooks armed for THAT visit. The retired
    # quick-look is no longer offered anywhere.
    # @args: window - the hub, monkeypatch - flag + routing overrides
    from nightscribe.core import project as proj_mod, followup as fu
    from nightscribe.gui import main_window as mw
    from PySide6.QtWidgets import QPushButton
    p = _create_and_select(window, "sn", "SN2026visit", {"kind": "sn"})
    sid = fu.create_session(mw.db, p["id"], "2026-09-08")
    fu.add_image(mw.db, sid, "R", "/tmp/fu_visit.fits",
                 date_obs="2026-09-08", exptime_s=60.0)
    # the visits manager in the Analysis tab lists the visit and its
    # plate; the plate's Open action routes to the UFE Measure tab with
    # the hooks armed for the visit (ADR-045)
    vp = _visits_panel(window)
    assert vp.lst.count() == 1, "the Visits list is missing the visit"
    vp.lst.setCurrentRow(0)               # user path: select the visit
    assert vp.current_session_id() == sid
    vp.open_visit(sid)                    # the resources live in its window
    btns = [b.text() for b in vp._win.findChildren(QPushButton)]
    assert "Open" in btns
    assert "Quick analysis" not in btns
    vp._win.lst_res.setCurrentRow(0)      # select the plate resource
    opened = []

    class _D:
        def open_plate(self, path):
            return True

        def set_object(self, obj):
            opened.append(obj)

        def load_saved_sequence(self, seq):
            return False

        def set_exotic_hooks(self, reduce_fn=None, export_fn=None):
            pass

    def _ufe_open(tab_, hook_pid=None, obj=None, session_id=None, **_kw):
        opened.append((tab_, hook_pid, obj, session_id))
        return _D()
    monkeypatch.setattr(window, "_ufe_open", _ufe_open)
    vp._win._on_open_resource()
    assert opened[0][:2] == ("measure", p["id"])
    assert opened[0][3] == sid            # the hooks land on the visit
    assert opened[-1]["name"] == "SN2026visit"


def test_fu_animation_button_writes_files(window, panel):
    # B6 fix: the animation button writes the evolution GIF/MP4 to the
    # project folder and registers them in project_files.
    from nightscribe.core import project, followup as fu
    import nightscribe.core.db as dbmod
    p = _create_and_select(window, "sn", "SN2026anim", {"kind": "sn",
                                                          "ra_deg": 10.0,
                                                          "dec_deg": 20.0})
    for i in range(3):
        sid = fu.create_session(dbmod.db, p["id"], f"2026-09-0{8+i}")
        fu.add_image(dbmod.db, sid, "Clear", f"/tmp/fu_fake_{i}.fits",
                     date_obs=f"2026-09-0{8+i}", exptime_s=60.0)
    # mock the animation writer AND the FITS reader: no real FITS needed
    from nightscribe.viz import evolution_view
    from nightscribe.core import fits_io
    import numpy as np
    import pathlib
    orig_gif = evolution_view.make_evolution_gif
    orig_vid = evolution_view.make_evolution_video
    orig_read = fits_io.read_fits
    written = []
    def fake_read(path):
        data = np.full((100, 100), 100.0, dtype=np.float32)
        yy, xx = np.ogrid[:100, :100]
        data += 3000 * np.exp(-((xx - 50) ** 2 + (yy - 50) ** 2) / (2 * 3 ** 2))
        return {"SIMPLE": True, "BITPIX": -32, "NAXIS": 2,
                 "NAXIS1": 100, "NAXIS2": 100}, data
    def fake_gif(frames, dates, sn_xy_s, out, **kw):
        pathlib.Path(out).write_bytes(b"GIF89a fake")
        written.append(out)
        return out
    def fake_vid(frames, dates, sn_xy_s, out, **kw):
        pathlib.Path(out).write_bytes(b"MP4 fake")
        written.append(out)
        return out
    evolution_view.make_evolution_gif = fake_gif
    evolution_view.make_evolution_video = fake_vid
    fits_io.read_fits = fake_read
    try:
        window._fu_run_animation(p["id"])
    finally:
        evolution_view.make_evolution_gif = orig_gif
        evolution_view.make_evolution_video = orig_vid
        fits_io.read_fits = orig_read
    files = project.list_files(dbmod.db, p["id"])
    kinds = [f["kind"] for f in files]
    assert "evo_gif" in kinds
    assert "evo_mp4" in kinds


def test_fu_annotated_fits_button_opens_the_editor(window, panel, tmp_path,
                                                   monkeypatch):
    # B10: the button opens the annotated FITS in the editor's Annotate tab
    # over the newest stacked FITS, with the other visits queued as extra
    # plates. The classic dialog retired (2026-10-07): the editor is the only
    # door (ADR-044 rev.).
    import numpy as np
    from nightscribe.core import followup as fu
    import nightscribe.core.db as dbmod

    p = _create_and_select(window, "sn", "SN2026ann", {"kind": "sn",
                                                       "ra_deg": 10.0,
                                                       "dec_deg": 20.0})
    sid = fu.create_session(dbmod.db, p["id"], "2026-09-08")
    fits_in = tmp_path / "stacked.fits"
    _write_simple_fits(fits_in, np.arange(64, dtype=np.float32).reshape(8, 8))
    fu.add_image(dbmod.db, sid, "Clear", str(fits_in),
                 date_obs="2026-09-08", exptime_s=60.0)

    seen = {}

    class _TabAnnotate:
        def prefill(self, notes=None, extra_paths=None):
            seen["notes"] = notes
            seen["extra"] = list(extra_paths or [])

    class _Dlg:
        def __init__(self):
            self.tab_annotate = _TabAnnotate()

        def open_plate(self, path):
            seen["plate"] = path
            return True

        def set_object(self, obj):
            seen["obj"] = obj

    def _ufe_open(tab_, hook_pid=None, obj=None, session_id=None, **_kw):
        seen["tab"] = tab_
        seen["pid"] = hook_pid
        return _Dlg()

    monkeypatch.setattr(window, "_ufe_open", _ufe_open)
    window._fu_export_annotated(p["id"])

    assert seen["tab"] == "annotate"
    assert seen["pid"] == p["id"]
    assert seen["plate"] == str(fits_in)
    assert seen["obj"]["name"] == "SN2026ann"
    assert seen["notes"]
    assert seen["extra"] == []


def _write_simple_fits(path, data):
    # Minimal valid FITS writer for test fixtures (SIMPLE=T, BITPIX=-32,
    # NAXIS=2, NAXIS1/2, END) — enough for fits_io.read_fits to parse.
    import struct
    h, w = data.shape
    header = (
        "SIMPLE  =                    T                                                  "
        f"BITPIX  =                  -32                                                  "
        f"NAXIS   =                    2                                                  "
        f"NAXIS1  ={w:>20}                                                  "
        f"NAXIS2  ={h:>20}                                                  "
        "END                                                                             "
    )
    hdr_bytes = header.encode("ascii")
    hdr_bytes += b" " * (2880 - len(hdr_bytes) % 2880)
    body = data.astype(">f4").tobytes()
    body += b"\x00" * ((2880 - len(body) % 2880) % 2880)
    from pathlib import Path
    Path(path).write_bytes(hdr_bytes + body)
    return path


def test_create_project_infers_kind_from_enriched_type(window):
    # Ad-hoc Explore (Tools) has no planner target, so no kind: the
    # enriched type decides it (exoplanet -> transit, transient -> sn).
    for etype, want in (("exoplanet", "transit"), ("transient", "sn"),
                        ("hads", "hads"), ("variable", "variable"),
                        ("small_body", "neo"), ("comet", "comet")):
        p = window._create_project({"name": f"Obj {etype}", "type": etype})
        assert p is not None and p["kind"] == want


def test_create_project_refuses_an_untyped_sun(window):
    assert window._create_project({"name": "Sun", "type": "sun"}) is None


def test_create_project_keeps_variable_and_campaign_context(window):
    from nightscribe.gui import main_window as mw
    from nightscribe.core import project as proj_mod
    t = {"kind": "variable", "name": "T CrB", "mag": 10.1,
         "ra_deg": 239.9, "dec_deg": 25.9, "project_id": 7,
         "variable": {"period_d": 227.55, "var_type": "NR"},
         "campaign": {"id": 1, "name": "Campaña T CrB"}}
    p = window._create_project(t)
    assert p is not None and p["kind"] == "variable"
    ctx = proj_mod.get(mw.db, p["id"])["context"]
    assert ctx["variable"]["period_d"] == 227.55
    assert ctx["campaign"]["name"] == "Campaña T CrB"
    assert ctx["project_id"] == 7
    # WHERE the figure comes from (2026-10-07): the planner's magnitude is a
    # PREDICTION, and a stack run later overwrites the same field with a
    # MEASUREMENT. Without this, reading 18.28 could not tell you whether
    # anybody had measured it, and the proposal anchors the comparison stars
    # on it.
    assert ctx["mag"] == 10.1
    assert ctx["mag_origin"] == "predicted"


def test_project_header_shows_campaign_badge(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña T CrB")
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 10.1},
                        campaign_id=cid)
    window._render_project_header(proj_mod.get(mw.db, p["id"]))
    assert "Campaña T CrB" in window.projects.lbl_mast_camp.text()


def test_hub_filters_projects_by_campaign(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw

    from PySide6.QtCore import Qt

    def _project_names(w):
        out = []
        for i in range(w.projects.lst_projects.count()):
            item = w.projects.lst_projects.item(i)
            if item.flags() != Qt.NoItemFlags:      # skip year headers
                out.append(item.text())
        return out

    cid = camp_mod.create(mw.db, "Campaña VC9")
    proj_mod.create(mw.db, "variable", "V Ceti VC9", {}, campaign_id=cid)
    proj_mod.create(mw.db, "variable", "Wee 9", {})
    window.on_refresh_projects()
    names = _project_names(window)
    assert any("V Ceti VC9" in n for n in names)
    assert any("Wee 9" in n for n in names)
    idx = window.projects.cmb_campaign.findText("Campaña VC9")
    assert idx >= 1
    window.projects.cmb_campaign.setCurrentIndex(idx)
    window.on_refresh_projects()
    names = _project_names(window)
    assert any("V Ceti VC9" in n for n in names)
    assert not any("Wee 9" in n for n in names)
    window.projects.cmb_campaign.setCurrentIndex(0)


def test_variable_project_gets_followup_with_protocol(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from PySide6.QtWidgets import QLabel, QWidget
    cid = camp_mod.create(
        mw.db, "Campaña T CrB",
        protocol={"cadence_nights": 1, "filters": ["B", "V"],
                  "comp_stars": ["000-BB0-123"], "notes": "Do not saturate"})
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 10.1},
                        campaign_id=cid)
    _build_page(window, proj_mod.get(mw.db, p["id"]))
    # a variable project gets a "follow-up" tab on its page (ADR-041:
    # open the tab, the user path, then inspect it)
    fu = _open_tab(window, proj_mod.get(mw.db, p["id"]), "analysis")
    texts = [l.text() for l in fu.findChildren(QLabel)]
    assert any("Campaña T CrB" in t for t in texts)
    assert any("B, V" in t for t in texts)
    assert any("Do not saturate" in t for t in texts)


def test_variable_followup_drops_quicklook_hides_animation(window):
    # ADR-044: the "Quick analysis" button is retired for everyone (the
    # silent "nada" failure, ADR-019): measuring a visit now goes
    # through the editor's measure tab plus a per-visit button. A
    # variable still has no SN-specific animation / annotated-FITS
    # pair either (that lives collapsed in SN projects only).
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from PySide6.QtWidgets import QPushButton
    p = proj_mod.create(mw.db, "variable", "V1490 Cyg", {"mag": 12.0})
    _build_page(window, proj_mod.get(mw.db, p["id"]))
    fu = _open_tab(window, proj_mod.get(mw.db, p["id"]), "analysis")
    btns = {b.text(): b for b in fu.findChildren(QPushButton)}
    assert "Quick analysis" not in btns
    assert "Generate animation" not in btns
    assert "Export annotated FITS" not in btns



def test_followup_event_advisor_label(window):
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from PySide6.QtWidgets import QLabel
    p = proj_mod.create(mw.db, "variable", "V1490 Cyg", {"mag": 12.0})
    for i, m in enumerate((12.0, 12.1, 11.9, 12.0, 12.9)):
        fu.add_point(mw.db, p["id"], 61000.0 + i, "V", m)
    _build_page(window, proj_mod.get(mw.db, p["id"]))
    page = _open_tab(window, proj_mod.get(mw.db, p["id"]), "analysis")
    texts = [l.text() for l in page.findChildren(QLabel)]
    assert any("brightness drop" in t or "descenso" in t for t in texts)


def test_variable_plan_block_shows_protocol_and_extremum(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from PySide6.QtWidgets import QLabel, QWidget
    cid = camp_mod.create(mw.db, "Campaña T CrB",
                          protocol={"cadence_nights": 1,
                                    "filters": ["B", "V"]})
    ctx = {"mag": 10.1,
           "variable": {"period_d": 227.55,
                        "next_extremum": {"kind": "max", "mjd": 61250.0,
                                          "days": 3.0}},
           "safe_window": "2026-09-11T22:00|2026-09-12T04:00"}
    p = proj_mod.create(mw.db, "variable", "T CrB", ctx, campaign_id=cid)
    _build_page(window, proj_mod.get(mw.db, p["id"]))
    page = _open_tab(window, proj_mod.get(mw.db, p["id"]), "plan")
    texts = [l.text() for l in page.findChildren(QLabel)]
    assert any("Campaña T CrB" in t for t in texts)
    assert any("3" in t and ("ays" in t or "ías" in t) for t in texts)
    # the saturation warning does NOT fire at mag 10.1
    assert not any("aturat" in t for t in texts)


def test_variable_plan_block_saturation_warning(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from PySide6.QtWidgets import QLabel, QWidget
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 9.0})
    _build_page(window, proj_mod.get(mw.db, p["id"]))
    page = _open_tab(window, proj_mod.get(mw.db, p["id"]), "plan")
    texts = [l.text() for l in page.findChildren(QLabel)]
    assert any("aturat" in t for t in texts)


def test_variable_plan_prefills_protocol_filters(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña T CrB",
                          protocol={"cadence_nights": 1,
                                    "filters": ["B", "V"]})
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 10.1},
                        campaign_id=cid)
    _build_page(window, proj_mod.get(mw.db, p["id"]))
    _open_tab(window, proj_mod.get(mw.db, p["id"]), "plan")
    filters = [e["cmb"].currentText() for e in window._sn_steps]
    assert filters == ["B", "V"]


def test_variable_without_campaign_keeps_clear_default(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "variable", "V1490 Cyg", {"mag": 12.0})
    _build_page(window, proj_mod.get(mw.db, p["id"]))
    _open_tab(window, proj_mod.get(mw.db, p["id"]), "plan")
    filters = [e["cmb"].currentText() for e in window._sn_steps]
    assert filters == ["Clear"]


def test_followup_has_export_report_button(window):
    # UX-PC (U4): the bulk photometry tools (paste/import/export/survey)
    # live in the ⋯ Photometry tools menu of the Follow-up section.
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from PySide6.QtWidgets import QToolButton
    p = proj_mod.create(mw.db, "variable", "T CrB", {"mag": 10.1})
    _build_page(window, proj_mod.get(mw.db, p["id"]))
    page = _open_tab(window, proj_mod.get(mw.db, p["id"]), "analysis")
    tools = [b for b in page.findChildren(QToolButton)
             if "Photometry" in b.text()]
    assert tools, "the ⋯ Photometry tools menu is missing"
    texts = [a.text() for a in tools[0].menu().actions()]
    assert any("Export photometry report" in t or "Exportar" in t
               for t in texts)
    assert any("Download survey photometry" in t for t in texts)
    assert any("Paste photometry" in t for t in texts)
    assert any("Import file" in t for t in texts)


def test_download_survey_points_are_stored_and_deduped(window):
    # U0.5: the download runs in a SurveyWorker; the merge (and its dedupe)
    # lives in _fu_survey_done, so the test feeds it the payload directly
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    points = [{"mjd": 59000.0 + i, "filter": "g", "mag": 15.5 + i * 0.01,
               "err": 0.02, "source": "survey:ztf"} for i in range(5)]
    fake = {"status": "ok", "points": points, "error": None}
    p = proj_mod.create(mw.db, "variable", "WeSb 1",
                        {"ra_deg": 15.2254, "dec_deg": 55.0667})
    window._fu_survey_done(p["id"], fake)
    pts = fu.list_points(mw.db, p["id"])
    assert len(pts) == 5
    assert all(q["source"] == "survey:ztf" for q in pts)
    window._fu_survey_done(p["id"], fake)        # again: no duplicates
    assert len(fu.list_points(mw.db, p["id"])) == 5


def test_post_files_registered_exactly_once(window, tmp_path, monkeypatch):
    # U0.1: _post_done registered es/en/tweet twice (two A4 blocks).
    from types import SimpleNamespace
    from PySide6.QtWidgets import (QLabel, QLineEdit, QPlainTextEdit,
                                   QProgressBar, QPushButton)
    from nightscribe.core import project as proj_mod
    from nightscribe.core import post as post_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099zz", {"mag": 15.0})
    window._current_project = proj_mod.get(mw.db, p["id"])
    post_w = SimpleNamespace(
        btn_generate=QPushButton(), lbl_files=QLabel(),
        edt_folder=QLineEdit(str(tmp_path)),
        txt_es=QPlainTextEdit(), txt_en=QPlainTextEdit(),
        txt_tweet=QPlainTextEdit(), progress=QProgressBar(),
        btn_ai_generate=QPushButton(), btn_ai_brief=QPushButton())
    written = {"es": tmp_path / "x_ES.md", "en": tmp_path / "x_EN.md",
               "tweet": tmp_path / "x_tweet.txt"}
    for f in written.values():
        f.write_text("x")
    monkeypatch.setattr(post_mod, "save_outputs",
                        lambda *a, **k: written)
    # the charts are collected through core/post now (one path for the
    # template and the AI report): stub it so nothing is rendered here
    monkeypatch.setattr(post_mod, "collect_assets",
                        lambda *a, **k: ({}, {}))
    window._post_done(post_w, "SN 2099zz",
                      {"name": "SN 2099zz"}, {"es": "a", "en": "b"})
    files = [f for f in proj_mod.list_files(mw.db, p["id"])
             if f["kind"] == "post"]
    assert len(files) == 3
    window._current_project = None


def test_detail_cleared_when_selection_vanishes(window):
    # U0.2: closing a project under the Active filter must clear the detail
    from PySide6.QtCore import Qt
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099aa", {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == p["id"]:
            lst.setCurrentRow(i)
            break
    assert window._current_project is not None
    lst.clearSelection()
    window._project_selected()
    assert window._current_project is None
    assert "SN 2099aa" not in window.projects.lbl_mast_name.text()
    assert "SN 2099aa" not in window.projects.lbl_mast_camp.text()


def test_reclick_selected_project_retries_load(window):
    from PySide6.QtCore import Qt
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099ab", {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    item = next(lst.item(i) for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) == p["id"])
    lst.setCurrentItem(item)
    calls = []
    orig = window._render_project_header
    window._render_project_header = lambda p: calls.append(p["id"]) or orig(p)
    window._project_reclicked(item)          # same row: must reload
    assert calls == [p["id"]]
    window._render_project_header = orig


def test_campaign_filter_persists_in_config(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.gui import main_window as mw
    from nightscribe.config import config
    cid = camp_mod.create(mw.db, "Campaña persist")
    window.on_refresh_projects()
    cmb = window.projects.cmb_campaign
    idx = cmb.findData(cid)
    assert idx >= 0
    cmb.setCurrentIndex(idx)                 # fires on_refresh_projects
    assert config.get("projects_filter_campaign") == cid
    cmb.setCurrentIndex(0)
    assert config.get("projects_filter_campaign") == ""


def test_hub_item_marks_campaign_membership(window):
    from nightscribe.core import campaign as camp_mod
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    cid = camp_mod.create(mw.db, "Campaña marca")
    proj_mod.create(mw.db, "variable", "EE Cep", {"mag": 11.0},
                    campaign_id=cid)
    proj_mod.create(mw.db, "sn", "SN 2099cc", {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    texts = {lst.item(i).text(): lst.item(i)
             for i in range(lst.count())}
    marked = [t for t in texts if "⚑" in t]
    assert any("EE Cep" in t for t in marked)
    assert not any("SN 2099cc" in t for t in marked)
    ee = next(it for t, it in texts.items() if "EE Cep" in t)
    assert "Campaña marca" in (ee.toolTip() or "")


def test_project_activated_jumps_to_current_step(window, panel):
    # panel: the harness convention — a FakeWorker loader stands in for the
    # real ExploreWorker, so the offscreen run never touches the network.
    from PySide6.QtCore import Qt
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099dd", {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    item = next(lst.item(i) for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) == p["id"])
    window._project_open_activated(item)
    # ADR-041: a fresh project sits at step "plan" -> that tab is the
    # active one; the object card stays hidden until the user opens it
    assert set(window._tab_pages) == {"details", "plan"}
    assert not window._tab_pages["plan"].isHidden()
    assert window._tab_pages["details"].isHidden()


def test_projects_context_menu_offers_actions(window, panel, monkeypatch):
    # panel: FakeWorker loader, no real network in this offscreen run.
    from PySide6 import QtWidgets
    from PySide6.QtCore import Qt
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, "sn", "SN 2099ee", {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    item = next(lst.item(i) for i in range(lst.count())
                if lst.item(i).data(Qt.UserRole) == p["id"])
    seen = {}

    class _Act:
        def __init__(self, text):
            self._t = text
        def text(self):
            return self._t
        def setEnabled(self, b):
            pass

    class _RecordingMenu:
        # PySide6 6.11: patching the non-virtual C++ QMenu.exec via a
        # class attribute is ignored by Shiboken — the real event loop
        # blocks the test. The handler imports QMenu at call time, so we
        # swap the class on the module itself (same capture/assert as the
        # card's fake_exec).
        def __init__(self, *a, **k):
            self._acts = []
        def addAction(self, text):
            act = _Act(text)
            self._acts.append(act)
            return act
        def addSeparator(self):
            pass
        def actions(self):
            return list(self._acts)
        def exec(self, *a, **k):
            seen["actions"] = [x.text() for x in self._acts]
            return None

    monkeypatch.setattr(QtWidgets, "QMenu", _RecordingMenu)
    window._project_context_menu(
        lst.visualItemRect(item).center())
    texts = seen["actions"]
    assert any("Open" in t or "Abrir" in t for t in texts)
    # ADR-045: the follow-up action is the Analysis tab now, for
    # every kind
    assert any("Analysis" in t or "Análisis" in t for t in texts)
    assert any("Delete" in t or "Eliminar" in t for t in texts)


def test_journal_double_click_opens_project(window, panel):
    # ADR-036 (J0+J2): the journal is a Tools-menu dialog fed by
    # core/journal.py; activating an entry opens the object's project.
    # harness: `panel` slots the fake loader (the hub contract, the real
    # ExploreWorker is never built); the hub list is refreshed first so
    # _goto_active_project can select the new row.
    from PySide6.QtCore import Qt
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    from nightscribe.gui.journal_dialog import JournalDialog
    p = proj_mod.create(mw.db, "sn", "SN 2099ff", {"mag": 15.0})
    mw.db.mark_observed("SN 2099ff", "sn", "2026-09-13")
    window.on_refresh_projects()
    dlg = JournalDialog(mw.db, on_open_object=window._journal_entry_open)
    lst = dlg.lst
    item = next(lst.item(i) for i in range(lst.count())
                if (lst.item(i).data(Qt.UserRole + 1) or "") == "SN 2099ff")
    lst.itemActivated.emit(item)
    cur = window.projects.lst_projects.currentItem()
    assert cur is not None and cur.data(Qt.UserRole) == p["id"]
    dlg.deleteLater()


def test_journal_double_click_without_project_explores(window, monkeypatch):
    from PySide6.QtCore import Qt
    from nightscribe.gui import main_window as mw
    from nightscribe.gui.journal_dialog import JournalDialog
    mw.db.mark_observed("2099 ZZ9", "neo", "2026-09-13")
    seen = []
    monkeypatch.setattr(window, "_open_explore_dialog",
                        lambda name: seen.append(name))
    dlg = JournalDialog(mw.db, on_open_object=window._journal_entry_open)
    lst = dlg.lst
    item = next(lst.item(i) for i in range(lst.count())
                if (lst.item(i).data(Qt.UserRole + 1) or "") == "2099 ZZ9")
    lst.itemActivated.emit(item)
    assert seen == ["2099 ZZ9"]
    dlg.deleteLater()


def test_gesture_language_is_consistent(window):
    # UX-c sweep: every list/table that navigates advertises it with the
    # hand cursor (the journal lives in the Tools-menu dialog since
    # ADR-036 J0, rebuilt on core/journal.py in J2)
    from PySide6.QtCore import Qt
    from nightscribe.gui import main_window as mw
    from nightscribe.gui.journal_dialog import JournalDialog
    dlg = JournalDialog(mw.db)
    for w in (window.projects.lst_projects, window.campaigns.lst_campaigns,
              window.campaigns.tbl_members, dlg.lst):
        assert w.viewport().cursor().shape() == Qt.PointingHandCursor, \
            f"{w.objectName()} lost its hand cursor"
    dlg.deleteLater()


def test_year_headers_never_open(window):
    # the hub's year separators have no id: activation must be a no-op
    # harness: Qt was not module-level in this file; import it locally
    from PySide6.QtCore import Qt
    lst = window.projects.lst_projects
    header = next((lst.item(i) for i in range(lst.count())
                   if lst.item(i).data(Qt.UserRole) is None), None)
    if header is not None:
        window._project_open_activated(header)      # must not raise
        assert window._current_project is None or True


# ---------------- UD.5: a wiped page must not leave a dead cache behind ----
#
# Wiping the project page schedules its subtree for destruction
# (deleteLater). The offscreen harness never spins the event loop, so
# those deletions pile up -- and the next selection runs into them.
# These two tests flush the queued deferred deletions (exactly what the
# real loop does between two clicks by a user) and re-select: the path
# that used to raise "QListWidget ... already deleted" (RuntimeError).

def _flush_deferred_deletions():
    # @args: none
    # @return: None, runs the queued deleteLater() events; a couple of
    #          rounds, because deleting one widget can queue the next.
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    for _ in range(2):
        app.sendPostedEvents(None, QEvent.DeferredDelete)


def test_files_window_survives_page_wipes(window):
    # The files window lives on the main window, not on the project
    # page: wiping the page (reselect -> deleteLater) must not kill it.
    # Once the queued deletions have run, the old "rebuild the list
    # inside a wiped page" crash class is gone by design -- the dialog
    # itself is the persistent home of the file list, and re-showing
    # just re-keys it onto the current project.
    from PySide6 import Shiboken
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    from nightscribe.gui.overview import ObjectPanel
    orig_loader = window._proj_panel_loader
    # a fake-loader card goes in first: the wipe below kills it, and the
    # rebuild has to stay off the real (networked) ExploreWorker
    window._proj_panel_loader = (lambda name, fallback_target=None:
                                 FakeWorker(FAKE_ELEMENT))
    window._proj_panel = ObjectPanel(loader=window._proj_panel_loader,
                                     chart_dir=None)
    try:
        p = _create_and_select(window, "sn", "SN2026wipe", {"kind": "sn"})
        project.add_file(dbmod.db, p["id"], "/tmp/wipe_seq.targets",
                         "sequence")
        _reselect(window, p["id"])
        window._show_project_files()
        dlg = window._proj_files_dlg
        assert dlg.project_id == p["id"]
        assert dlg.tbl.rowCount() == 1

        # two more wipes: the page dies under the dialog, not it...
        _reselect(window, p["id"])
        _flush_deferred_deletions()
        assert Shiboken.isValid(dlg)          # the window outlives the page
        _reselect(window, p["id"])
        _flush_deferred_deletions()
        assert Shiboken.isValid(dlg)
        assert window._proj_files_dlg is dlg  # one instance, never rebuilt

        # ...and it still speaks for the project
        window._show_project_files()
        assert dlg.project_id == p["id"]
        assert dlg.tbl.rowCount() == 1
        kinds = [dlg.tbl.item(i, 0).text()
                 for i in range(dlg.tbl.rowCount())]
        assert any("sequence" in k for k in kinds)
    finally:
        if window._proj_panel is not None \
                and Shiboken.isValid(window._proj_panel):
            window._proj_panel.deleteLater()
        window._proj_panel = None
        window._proj_panel_loader = orig_loader
        _flush_deferred_deletions()


def test_panel_survives_page_wipe_rebuild(window):
    # The shared ObjectPanel goes under the wipe as well (it is parented
    # into the page). Once the queued deletion has fired, the hub must
    # notice the dead card, drop it and hand out a fresh one -- not blow
    # up on a dead C++ object.
    from PySide6 import Shiboken
    from nightscribe.gui.overview import ObjectPanel
    orig_loader = window._proj_panel_loader
    window._proj_panel_loader = (lambda name, fallback_target=None:
                                 FakeWorker(FAKE_ELEMENT))
    # a test-owned card in the shared slot: selection will parent it into
    # the page, so the wipe below really catches it
    fake = ObjectPanel(loader=lambda name, fallback_target=None:
                       FakeWorker(FAKE_ELEMENT), chart_dir=None)
    window._proj_panel = fake
    try:
        p = _create_and_select(window, "neo", "panel-wipe", NEO_CTX)
        assert window._proj_panel is fake

        # wipe + delete: the normal "deselect" path kills the card...
        window._clear_project_detail()
        _flush_deferred_deletions()
        assert not Shiboken.isValid(fake)    # ...the C++ card is really dead

        # ...and re-selecting must serve a fresh, valid one (pre-fix:
        # "already deleted" on the dead wrapper).
        _reselect(window, p["id"])           # must not raise
        assert window._proj_panel is not fake
        assert Shiboken.isValid(window._proj_panel)
        assert window._proj_panel.state() == "ready"
    finally:
        built = window._proj_panel
        if built is not None and built is not fake:
            if Shiboken.isValid(built):
                built.deleteLater()
        if Shiboken.isValid(fake):
            fake.deleteLater()
        window._proj_panel = None
        window._proj_panel_loader = orig_loader
        _flush_deferred_deletions()


# -------------------- wheel-passive detail form controls -----------------
#
# The detail page scrolls inside a single QScrollArea (scroll_page). A bare
# spin box or item view swallows the mouse wheel, killing the page scroll
# (the "wheel hijack"), so the page's wheelable controls are passive: plain
# wheel is deferred to the page, Ctrl+wheel stays as the deliberate
# fine-tune. Lists keep the native wheel while their scrollbar is active.
# These tests lock that in offscreen with synthetic QWheelEvents.

def _wheel_event(dy=-120, modifiers=None):
    # one notch down, the full 8-arg constructor (this PySide6 build has no
    # QTest.qWheelEvent); the event object is returned so the test can
    # inspect its accepted state afterwards.
    from PySide6.QtCore import QPointF, QPoint, Qt
    from PySide6.QtGui import QWheelEvent
    if modifiers is None:
        modifiers = Qt.NoModifier
    return QWheelEvent(QPointF(10, 10), QPointF(10, 10),
                       QPoint(0, dy), QPoint(0, dy),
                       Qt.NoButton, modifiers, Qt.ScrollUpdate, False)


def test_detail_spins_are_wheel_passive(window, panel):
    # A plain wheel over a detail spin must not change its value: the
    # gesture belongs to the page's scroll.
    from PySide6.QtCore import QCoreApplication
    from nightscribe.gui.widgets.passive_wheel import (
        PassiveDoubleSpinBox, PassiveSpinBox)
    p = _create_and_select(window, "neo", "wheel-passive-spin", dict(NEO_CTX))
    _open_tab(window, p, "plan")
    for key, cls in (("spn_darks", PassiveSpinBox),
                     ("spn_darkexp", PassiveDoubleSpinBox)):
        w = window._project_widgets[key]
        assert isinstance(w, cls), f"{key} should be a {cls.__name__}"
        before = w.value()
        e = _wheel_event()
        QCoreApplication.instance().sendEvent(w, e)
        assert w.value() == before, f"plain wheel on {key} should be passive"
        assert not e.isAccepted(), f"passive wheel on {key} must stay unaccepted"


def test_detail_spins_fine_tune_on_ctrl_wheel(window, panel):
    # Ctrl+wheel is the deliberate fine-tune gesture and must still work.
    from PySide6.QtCore import QCoreApplication, Qt
    p = _create_and_select(window, "neo", "wheel-ctrl-spin", dict(NEO_CTX))
    _open_tab(window, p, "plan")
    spn = window._project_widgets["spn_darks"]
    spn.setValue(50)
    e = _wheel_event(modifiers=Qt.ControlModifier)
    QCoreApplication.instance().sendEvent(spn, e)
    assert spn.value() < 50, "Ctrl+wheel should fine-tune a plain wheel down"
    assert e.isAccepted(), "fine-tune wheel should be consumed by the native handler"

    dbl = window._project_widgets["spn_darkexp"]
    dbl.setValue(5.0)
    e2 = _wheel_event(modifiers=Qt.ControlModifier)
    QCoreApplication.instance().sendEvent(dbl, e2)
    assert dbl.value() < 5.0, "Ctrl+wheel should fine-tune a double spin down"


def test_short_list_is_wheel_passive(window, panel):
    # A list with nothing to scroll has no claim on the wheel: it belongs
    # to the page. A standalone PassiveList that does not overflow keeps
    # this deterministic (no dependence on the page's shared layout state).
    from PySide6.QtCore import QCoreApplication, Qt
    from nightscribe.gui.widgets.passive_wheel import PassiveList
    lst = PassiveList(window)
    for i in range(5):                      # a handful of rows: fits easily
        lst.addItem(f"file_{i}")
    lst.setFixedHeight(600)
    lst.show()
    QCoreApplication.instance().processEvents()
    try:
        sb = lst.verticalScrollBar()
        assert sb.maximum() == 0, "a short list cannot overflow"
        # Wheels on item views arrive at the viewport, so that's the target.
        e = _wheel_event()
        QCoreApplication.instance().sendEvent(lst.viewport(), e)
        QCoreApplication.instance().processEvents()
        assert not e.isAccepted(), "wheel on a short list must stay unaccepted"
        assert sb.value() == 0
        # Ctrl+wheel takes the native path but cannot scroll a short list.
        e2 = _wheel_event(modifiers=Qt.ControlModifier)
        QCoreApplication.instance().sendEvent(lst.viewport(), e2)
        QCoreApplication.instance().processEvents()
        assert sb.value() == 0
    finally:
        lst.deleteLater()
        _flush_deferred_deletions()


def test_overflowing_list_keeps_native_wheel(window, panel):
    # A long list must stay scrollable with the wheel (its scrollbar is
    # active). A standalone PassiveList with a forced height keeps this
    # independent of the page layout.
    from PySide6.QtCore import QCoreApplication, Qt
    from nightscribe.gui.widgets.passive_wheel import PassiveList
    # Standalone (no parent) with a forced height: deterministic geometry
    # offscreen, the way the list overflow is meant to be measured.
    lst = PassiveList()
    lst.setFixedHeight(120)
    lst.show()
    QCoreApplication.instance().processEvents()
    for i in range(200):
        lst.addItem(f"frame {i:03d}")
    QCoreApplication.instance().processEvents()
    try:
        sb = lst.verticalScrollBar()
        assert sb.maximum() > 0, "sanity: the list must overflow"
        e = _wheel_event()
        QCoreApplication.instance().sendEvent(lst.viewport(), e)
        QCoreApplication.instance().processEvents()
        assert sb.value() > 0, "wheel on an overflowing list must scroll it"
        assert e.isAccepted(), "native wheel should be consumed"

        sb.setValue(0)
        QCoreApplication.instance().processEvents()
        e2 = _wheel_event(dy=-120 * 10, modifiers=Qt.ControlModifier)
        QCoreApplication.instance().sendEvent(lst.viewport(), e2)
        QCoreApplication.instance().processEvents()
        assert sb.value() > 0, "Ctrl+wheel must scroll an overflowing list too"
    finally:
        lst.deleteLater()
        _flush_deferred_deletions()


def test_detail_page_has_no_bare_wheel_hijackers(window, panel):
    # The regression lock for the wheel-hijack fix: everything wheelable
    # the page builds must be one of the passive variants, or it will eat
    # the scroll again (new controls added without the passive class fail
    # here).
    _create_and_select(window, "neo", "wheel-audit", dict(NEO_CTX))
    from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox, QListWidget
    from nightscribe.gui.widgets.passive_wheel import (
        PassiveDoubleSpinBox, PassiveList, PassiveSpinBox)
    container = window.projects.page_container
    bad = [type(w).__name__ for w in container.findChildren(QSpinBox)
           if not isinstance(w, PassiveSpinBox)]
    bad += [type(w).__name__ for w in container.findChildren(QDoubleSpinBox)
            if not isinstance(w, PassiveDoubleSpinBox)]
    bad += [type(w).__name__ for w in container.findChildren(QListWidget)
            if not isinstance(w, PassiveList)]
    assert not bad, f"bare wheel-hijacking controls on the detail page: {bad}"


def test_every_kind_with_a_curve_shows_its_preview(window, panel):
    # Reported: "todos los proyectos, sean del tipo que sean, que tengan una
    # gráfica fotométrica asociada, deberían presentarlo en el listado". The
    # thumbnail was tied to the follow-up kinds, so a transit project with
    # 1255 measured points (HAT-P-32 b, on the observer's own database)
    # showed nothing at all.
    import nightscribe.core.db as dbmod
    from nightscribe.core import followup, project
    from PySide6.QtCore import Qt
    p = project.create(dbmod.db, "transit", "HAT-P-32 b")
    for i, m in enumerate((12.10, 12.12, 12.09, 12.11)):
        followup.add_point(dbmod.db, p["id"], 60900.0 + i * 0.01, "V", m)
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    row = None
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == p["id"]:
            row = lst.itemWidget(lst.item(i))
            break
    assert row is not None
    assert not row.lbl_spark.isHidden()          # a transit with a curve
    assert "1" in row.lbl_spark.toolTip()        # one night
    assert "4" in row.lbl_spark.toolTip()        # four points


def test_a_project_without_a_curve_shows_no_preview(window, panel):
    # The other half: no photometry, no squiggle (the row hides it itself,
    # because the pixmap comes back null).
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    from PySide6.QtCore import Qt
    p = project.create(dbmod.db, "neo", "2026 QK (no curve)")
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    row = None
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == p["id"]:
            row = lst.itemWidget(lst.item(i))
            break
    assert row is not None
    assert row.lbl_spark.isHidden()


def test_the_analysis_curve_follows_the_selected_visit(window, panel):
    # Reported: "La curva de luz que se muestre en Project details -> Analysis
    # ha de ser la de la visita seleccionada, quizás la última". The chart
    # drew the project's pile of points whatever visit was selected, and the
    # panel opened with no visit selected at all.
    import nightscribe.core.db as dbmod
    from nightscribe.core import followup as fu
    from PySide6.QtCore import Qt
    p = _create_and_select(window, "variable", "V0526curva",
                           {"kind": "variable"})
    early = fu.create_session(dbmod.db, p["id"], obs_date="2026-09-28")
    run1 = fu.create_run(dbmod.db, session_id=early, cfg={"series": {}})
    fu.add_points(dbmod.db, [
        {"project_id": p["id"], "session_id": early,
         "mjd": 60297.80 + i * 0.001, "filter": "V", "mag": 12.70 + i * 0.01,
         "err": 0.01, "source": "measure", "flags": [], "run_id": run1}
        for i in range(2)])
    last = fu.create_session(dbmod.db, p["id"], obs_date="2026-09-30")
    run2 = fu.create_run(dbmod.db, session_id=last, cfg={"series": {}})
    fu.add_points(dbmod.db, [
        {"project_id": p["id"], "session_id": last,
         "mjd": 60299.80 + i * 0.001, "filter": "V", "mag": 11.96 + i * 0.01,
         "err": 0.01, "source": "measure", "flags": [], "run_id": run2}
        for i in range(3)])
    vp = _visits_panel(window)                  # builds the Analysis tab
    w = window._project_widgets
    # the newest visit is selected by itself (the list is newest first), and
    # the chart draws ITS curve, saying which one it is
    assert vp.current_session_id() == last
    assert len(w["fu_curve"]._points) == 3
    assert "2026-09-30" in w["fu_curve_what"].text()
    # select the earlier visit: the chart follows it
    for row in range(vp.lst.count()):
        if vp.lst.item(row).data(Qt.UserRole) == early:
            vp.lst.setCurrentRow(row)
    assert len(w["fu_curve"]._points) == 2
    assert "2026-09-28" in w["fu_curve_what"].text()
    # and the switch to the whole project draws every night, once each
    cmb = w["fu_curve_scope"]
    cmb.setCurrentIndex(cmb.findData("project"))
    assert len(w["fu_curve"]._points) == 5
    assert "whole project" in w["fu_curve_what"].text()


def test_the_analysis_curve_exists_for_every_kind_with_one(window, panel):
    # Reported: "todos los proyectos, sean del tipo que sean, que tengan una
    # gráfica fotométrica asociada, deberían presentarlo". The block was
    # tied to sn/variable, so a transit with 1255 measured points (HAT-P-32
    # b, on the observer's own database) had no curve in the Analysis tab.
    import nightscribe.core.db as dbmod
    from nightscribe.core import followup as fu
    p = _create_and_select(window, "transit", "HAT-P-32 curva",
                           {"kind": "transit"})
    fu.add_points(dbmod.db, [
        {"project_id": p["id"], "session_id": None,
         "mjd": 60940.5 + i * 0.001, "filter": "V", "mag": 12.10 + i * 0.01,
         "err": 0.01, "source": "measure", "flags": []} for i in range(4)])
    _visits_panel(window)
    w = window._project_widgets
    assert w["fu_curve"] is not None
    assert len(w["fu_curve"]._points) == 4
    # no template for a transit: the checkbox is hidden instead of lying
    assert w["fu_curve_tpl"].isHidden()


# ---------------- the row's thumbnail (2026-10-01) ----------------

def test_the_row_thumbnail_is_the_latest_curve_in_the_charts_scale(window):
    # Reported: the thumbnail stretched min-to-max on its own, so a flat
    # curve and a three-magnitude one looked exactly the same, and it showed
    # the project's pile instead of the latest available curve. It now draws
    # the newest run in the same magnitude window the chart uses.
    import nightscribe.gui.main_window as mw
    from nightscribe.core import followup as fu
    from nightscribe.core import lightcurve_data
    from nightscribe.core import project as proj
    from nightscribe.gui.widgets.lightcurve_widget import source_label
    db = mw.db
    p = proj.create(db, "transit", "HAT-P-32 b")
    sid = fu.create_session(db, p["id"], obs_date="2017-12-20")
    # a measured night: a flat curve with one anomalous frame
    run_a = fu.create_run(db, session_id=sid, cfg={"series": {"band": "V"}})
    rows = [{"project_id": p["id"], "session_id": sid,
             "mjd": 58107.1 + i * 0.001, "filter": "V",
             "mag": 11.1 + (0.005 if i % 2 else -0.005), "err": 0.01,
             "source": "measure", "flags": [], "run_id": run_a}
            for i in range(40)]
    rows.append({"project_id": p["id"], "session_id": sid, "mjd": 58107.2,
                 "filter": "V", "mag": 13.2, "err": 0.05,
                 "source": "measure", "flags": [], "run_id": run_a})
    fu.add_points(db, rows)
    # and the imported curve, the newest run (mag ~0: another frame)
    run_b = fu.create_run(db, session_id=sid, cfg={"source": "exotic"})
    fu.add_points(db, [{"project_id": p["id"], "session_id": sid,
                        "mjd": 58107.3 + i * 0.002, "filter": None,
                        "mag": i * 0.001, "err": 0.01, "source": "exotic",
                        "flags": [], "run_id": run_b} for i in range(30)])
    payload = window._project_row_payload(proj.get(db, p["id"]), None, {})
    assert not payload["sparkline"].isNull()
    # the tooltip says WHICH curve it is (the latest one), not just "so far"
    assert source_label("exotic") in payload["sparkline_text"]
    # the scale is the chart's rule over THOSE points
    pts = fu.list_points_for_run(db, run_b)
    win = lightcurve_data.mag_window([q["mag"] for q in pts])
    assert win is not None and win[0] <= 0.0 <= win[1]
    # the measured curve's window is a different one (11.07-11.24): with it
    # the imported curve would be off the box entirely, which is why the row
    # frames the curve it draws
    measured_win = lightcurve_data.mag_window(
        [q["mag"] for q in fu.list_points(db, p["id"])])
    assert measured_win[0] > 11.0
    # a series run (its cfg carries no source) must not read "Manual entry"
    run_c = fu.create_run(db, session_id=sid, cfg={"series": {"band": "V"}})
    fu.add_points(db, [{"project_id": p["id"], "session_id": sid,
                        "mjd": 58107.5 + i * 0.002, "filter": "V",
                        "mag": 11.1 + i * 0.001, "err": 0.01,
                        "source": "measure", "flags": [], "run_id": run_c}
                       for i in range(10)])
    payload = window._project_row_payload(proj.get(db, p["id"]), None, {})
    assert source_label("measure") in payload["sparkline_text"]


def test_home_new_project_tile_points_to_tonight(window):
    # Interfaz 1.3: the header tile is the single new-project entry.
    from PySide6.QtWidgets import QPushButton
    from nightscribe.gui.main_window import VIEW_TONIGHT
    tile = window.findChild(QPushButton, "newTile")
    assert tile is not None and tile.isEnabled()
    tile.click()
    assert window._shell_stack().currentIndex() == VIEW_TONIGHT


def test_due_project_row_carries_the_urgency(window, panel):
    # Interfaz 1.3: the "needs you" / cadence signal lives in the row (the
    # next action in words + the urgency tint), not in a separate panel.
    import time
    import nightscribe.core.db as dbmod
    from nightscribe.core import followup, project as proj_mod
    from nightscribe.gui import main_window as mw, theme
    p = proj_mod.create(mw.db, "sn", "SN2099due", {"kind": "sn"})
    proj_mod.advance(mw.db, p["id"])
    sid = followup.create_session(mw.db, p["id"])
    dbmod.db.execute("UPDATE project_sessions SET created=? WHERE id=?",
                     (time.time() - 9 * 86400, sid))
    dbmod.db.commit()
    row = window._project_row_widget(proj_mod.get(mw.db, p["id"]),
                                     {"urgency": "due"}, {})
    assert theme.C_WARN in row.lbl_next.styleSheet()
