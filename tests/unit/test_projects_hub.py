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
    w._blink_timer.stop()
    w._blink_render_timer.stop()
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


# ---------------- D4 contracts ----------------

def test_select_project_drives_panel(window, panel):
    _create_and_select(window, "neo", "2026 QK (443089)", NEO_CTX)
    assert window._proj_panel is panel
    assert panel.state() == "ready"
    assert panel.lbl_hook.text()
    # step machine and buttons stayed intact ("Details" tab first, then the
    # four steps)
    assert window.projects.tabs_steps.count() == 5
    # a project opens on "Details": prev has no target there, next enters
    # step 1
    assert window.projects.tabs_steps.currentIndex() == 0
    assert not window.projects.btn_prev.isEnabled()
    assert window.projects.btn_next.isEnabled()
    assert not window.projects.btn_skip.isEnabled()
    assert not window.projects.btn_mark_done.isEnabled()
    assert window._current_project is not None
    assert "443089" in window.projects.lbl_header.text()


def test_panel_carries_project_context_chips(window, panel):
    _create_and_select(window, "neo", "chips-target", NEO_CTX)
    assert panel.state() == "ready"
    assert not panel.row_capture.isHidden()
    from PySide6.QtWidgets import QLabel
    chips = [w.text() for w in panel.row_capture.findChildren(QLabel)
             if w.text().strip()]
    assert any("19.5" in c for c in chips), f"mag chip missing: {chips!r}"
    assert any("12.0" in c for c in chips), f"rate chip missing: {chips!r}"
    assert any("21:00" in c and "23:30" in c for c in chips), \
        f"window chip missing: {chips!r}"


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
    # No pre-built panel: the hub builds the shared ObjectPanel itself,
    # wraps it in a scroll area, and docks it into the "Details" tab (the
    # first one) — the business card owns the whole tab, the steps keep
    # their own content (the real QScrollArea path).
    from PySide6.QtWidgets import QScrollArea, QWidget
    # point the built panel's loader at a fake so no ExploreWorker is made
    orig_loaders = window._proj_panel_loader
    window._proj_panel_loader = (lambda name, fallback_target=None:
                                 FakeWorker(FAKE_ELEMENT))
    window._proj_panel = None
    try:
        panel = window._get_proj_panel()
        assert window._proj_panel is panel
        assert window._proj_panel_area is not None
        assert isinstance(window._proj_panel_area, QScrollArea)
        assert window._proj_panel_area.widget() is panel
        # setWidget() re-parents the panel into the scroll area's viewport
        assert (panel.parentWidget()
                is window._proj_panel_area.viewport())
        # docked into the "Details" tab (index 0), not the step tabs
        tab = window.projects.tabs_steps.findChild(QWidget, "tab_details")
        assert window.projects.tabs_steps.currentIndex() == 0 or \
            window.projects.tabs_steps.tabIndex(tab) == 0
        lay = tab.layout()
        assert lay.indexOf(window._proj_panel_area) >= 0
    finally:
        window._proj_panel_loader = orig_loaders
        window._proj_panel = None
        window._proj_panel_area = None


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
    assert "No projects" in window.projects.lbl_header.text()


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
# Projects must be visible without pressing "Refresh": the list loads at
# startup and refreshes again on every visit to the Projects tab. The
# "Refresh" button stays as a just-in-case fallback.

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
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    try:
        for _ in range(3):      # let the deferred startup refresh land
            QCoreApplication.processEvents()
        assert w.projects.lst_projects.count() > 0
        # the manual fallback button is still there
        assert w.projects.btn_refresh is not None
        assert not w.projects.btn_refresh.isHidden()
    finally:
        config.is_configured = orig_cfg
        w.close()


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


def test_capture_tab_calibration_and_ccdciel_export(window, panel, tmp_path,
                                                    monkeypatch):
    # The Capture tab carries the CCDciel calibration group (ADR-021) and the
    # export button writes a real ".targets" list (CONFIG Version="5") with
    # Light + Dark + Bias steps, using the project safe window as the
    # informative StartTime/EndTime.
    import xml.etree.ElementTree as ET
    from PySide6.QtWidgets import QFileDialog
    ctx = dict(NEO_CTX)
    ctx.update({"ra_deg": 9.36667, "dec_deg": 72.3475,
                "safe_window": "2026-09-06T16:52:02+00:00|"
                               "2026-09-07T12:53:15+00:00"})
    _create_and_select(window, "neo", "seq-capture-target", ctx)
    w = window._project_widgets
    assert w["spn_darks"].value() == 25   # calibration group defaults
    assert w["spn_bias"].value() == 100
    assert w["spn_darkexp"].value() > 0.0  # follows the light exposure
    out = tmp_path / "seq-capture-target.targets"
    w["cmb_seqfmt"].setCurrentIndex(1)   # CCDciel (targets)
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
