############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - project detail tab bar tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Unit tests: the project detail tab bar (ADR-041, offscreen).

The step accordion was replaced by a 5-tab bar in the masthead
(Object card, the three steps, and Follow-up for the kinds that keep
a multi-night journal). One page is visible at a time, each page
builds lazily on first open, and a rebuild (project change or step
action) wipes all of them:

  * lazy build + cache: a selection yields {"details", next-action
    tab}; the rest build on first open and are cached in
    `window._tab_pages`
  * exactly one page visible at a time (object card included); the
    tab bar buttons mirror the active page
  * "Mark done" lives once, on the global Next card; the only step
    control left on a step page is the "Reopen step" link of an
    already finished step (skipping a step interactively is gone — a
    "skipped" row can only come from an old database); rebuilds never
    pile controls up
  * the Follow-up tab is hidden for kinds outside FOLLOWUP_KINDS; a
    deep link to it there is a safe no-op
  * every deep link (Next-card Go, the follow-up entry point, the
    nested "Project files" list) lands on the right page and enforces
    the one-visible-page rule
  * the chip on each step page header mirrors the step state (done
    <date> / skipped / pending); the object card and the follow-up
    page carry no chip

Same harness as test_projects_hub.py: a fake loader keeps the real
ExploreWorker out, and the db singleton is pointed at a temp file so
no test ever touches the real database.
"""

import datetime
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402

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
    tmp = dbmod.Database(tmp_path_factory.mktemp("ud3db") / "t.db")
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
    p.deleteLater()


def _mk_project(window, kind="sn", name="SN 2099pg"):
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    p = proj_mod.create(mw.db, kind, name, {"mag": 15.0})
    window.on_refresh_projects()
    lst = window.projects.lst_projects
    for i in range(lst.count()):
        if lst.item(i).data(Qt.UserRole) == p["id"]:
            lst.setCurrentRow(i)
            break
    return p


def test_pages_build_lazily_per_selection(window, panel):
    # ADR-041: on selection the page is wiped and rebuilt with the
    # Object card (eager) plus the next-action tab auto-opened; the
    # rest of the tab bar waits for its first click.
    _mk_project(window)
    assert hasattr(window.projects, "scroll_page")
    assert window.projects.scroll_page.widget() is \
        window.projects.page_container
    for key in ("details", "plan", "process", "publish", "followup"):
        assert hasattr(window.projects, f"btn_tab_{key}")
    assert set(window._tab_pages) == {"details", "plan"}
    assert window._active_tab == "plan"


def test_page_is_scroll_wrapped(window, panel):
    _mk_project(window)
    assert window.projects.scroll_page.widget() is \
        window.projects.page_container


def test_pages_hold_exactly_one_control_set_after_rebuilds(window, panel):
    # UX-PC (U3) + ADR-041: "Mark done" lives once, on the Next card.
    # The interactive skip went out with the UX (ADR-043): a fresh
    # project's pending step pages carry NO footer action. Rebuilds and
    # lazy builds must never pile controls up: open every page, rebuild
    # the page twice, open everything again.
    p = _mk_project(window)
    window._build_project_page(window._current_project)
    window._build_project_page(window._current_project)
    for key in ("plan", "process", "publish"):
        window._show_tab(key)
    from PySide6.QtWidgets import QPushButton
    names = [b.text() for b in window.projects.page_container
             .findChildren(QPushButton)]
    assert names.count(window.tr("Mark done")) == 0
    # the Next card carries the single "Mark done" command (ADR-043: the
    # card-level Skip is gone; "Mark done" lives once)
    assert not window.projects.btn_next_done.isHidden()
    # and none of the fresh step pages carries skip UI any more: no
    # "Skip step", no "Reopen step" (the footer only appears on
    # finished steps, and footers never leak into other pages)
    assert names.count(window.tr("Skip step")) == 0
    assert names.count(window.tr("Reopen step")) == 0


def test_followup_tab_only_for_followup_kinds(window, panel):
    # ADR-041: the Follow-up tab (and its page) exists only for the
    # kinds that keep a multi-night journal; for the rest the button
    # is hidden and a deep link to it is a safe no-op.
    _mk_project(window, kind="neo", name="2099 PG1")
    assert window.projects.btn_tab_followup.isHidden()
    window._show_tab("followup")  # off-kind: no page, no active switch
    assert window._active_tab != "followup"
    assert "followup" not in window._tab_pages
    _mk_project(window, kind="sn", name="SN 2099pg2")
    assert not window.projects.btn_tab_followup.isHidden()
    window._show_tab("followup")
    assert window._active_tab == "followup"
    assert "followup" in window._tab_pages


def test_step_toggle_marks_done(window, panel):
    p = _mk_project(window)
    window._step_done("plan")
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, p["id"])["steps"]}
    assert steps["plan"] == "done"
    assert steps["process"] == "current"


def test_step_reopen(window, panel):
    p = _mk_project(window)
    window._step_done("plan")
    window._step_reopen("plan")
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, p["id"])["steps"]}
    assert steps["plan"] == "current"
    assert steps["process"] == "pending"


def test_next_card_lands_on_next_action_tab(window, panel):
    # ADR-041: a fresh project's Next card points at Plan, and the Plan
    # tab is the one open — the Object card hides behind the bar.
    _mk_project(window)
    assert "Plan" in window.projects.lbl_next.text() or \
        "Planifica" in window.projects.lbl_next.text()
    assert window._active_tab == "plan"
    assert not window._tab_pages["plan"].isHidden()
    assert window._tab_pages["details"].isHidden()


def test_next_card_followup_when_cadence_due(window, panel):
    p = _mk_project(window)
    window._step_done("plan")
    from nightscribe.core import followup as fu
    from nightscribe.gui import main_window as mw
    fu.create_session(mw.db, p["id"])
    mw.db.execute("UPDATE project_sessions SET created=? WHERE"
                  " project_id=?", (1_700_000_000, p["id"]))
    mw.db.commit()
    window._build_project_page(window._current_project)
    assert "Measure" in window.projects.lbl_next.text() or \
        "Mide" in window.projects.lbl_next.text()
    assert window._active_tab == "followup"
    assert not window._tab_pages["followup"].isHidden()
    # UX-PC (U3): follow-up is not a step — the Next card hides "Mark done"
    # (ADR-043: there is no card-level Skip any more)
    assert window.projects.btn_next_done.isHidden()


def test_next_card_done_advances_the_step(window, panel):
    # UX-PC (U3): the Next card's "✔ Mark done" drives the step machine —
    # it acts on the step the card points at (a fresh project: plan).
    _mk_project(window, name="SN 2099nd")
    assert window._next_step_key == "plan"
    window.projects.btn_next_done.click()
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, window._current_project["id"])
             ["steps"]}
    assert steps["plan"] == "done"
    assert window._next_step_key == "process"


def test_skipped_step_moves_the_flow_forward(window, panel):
    # The GUI no longer offers skipping (ADR-043), but the step machine
    # still has to absorb the legacy "skipped" rows of an old database:
    # the flow lands past them, on the next step.
    p = _mk_project(window, name="SN 2099ns")
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    proj_mod.set_step_status(mw.db, p["id"], "plan", proj_mod.STEP_SKIPPED)
    p = proj_mod.get(mw.db, p["id"])
    window._current_project = p
    window._build_project_page(p)
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, p["id"])["steps"]}
    assert steps["plan"] == "skipped"
    assert window._next_step_key == "process"


def test_step_footer_reopens_a_legacy_skipped_step(window, panel):
    # ADR-043: the GUI can no longer produce a "skipped" step, but an old
    # database may carry one: its footer still offers "Reopen step", and
    # the click moves the flow back to it (single-current invariant).
    from PySide6.QtWidgets import QPushButton
    p = _mk_project(window, name="SN 2099rs")
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    proj_mod.set_step_status(mw.db, p["id"], "process",
                             proj_mod.STEP_SKIPPED)
    p = proj_mod.get(mw.db, p["id"])
    window._current_project = p
    window._build_project_page(p)
    window._show_tab("process")  # the skipped step's page builds on first open
    page = window._tab_pages["process"]
    btns = [b for b in page.findChildren(QPushButton)
            if "Reopen" in b.text() or "Reabrir" in b.text()]
    assert len(btns) == 1
    btns[0].click()
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, p["id"])["steps"]}
    assert steps["process"] == "current"
    assert steps["plan"] == "pending"


def test_step_footer_reopens_a_done_step(window, panel):
    # UX-PC (U3): a done step shows its state + a discreet "Reopen step"
    # at the FOOT of its tab page (the only step control left inside).
    from PySide6.QtWidgets import QPushButton
    p = _mk_project(window, name="SN 2099rf")
    window._step_done("plan")
    window._show_tab("plan")  # the done step's page builds on first open
    page = window._tab_pages["plan"]
    btns = [b for b in page.findChildren(QPushButton)
            if "Reopen" in b.text() or "Reabrir" in b.text()]
    assert len(btns) == 1
    btns[0].click()
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, p["id"])["steps"]}
    assert steps["plan"] == "current"


def test_calibration_and_products_start_collapsed(window, panel):
    # UX-PC (U3): the advanced blocks (Calibration in the Plan page,
    # "what you kept" in the Process page) are collapsed by default.
    from nightscribe.gui.widgets.collapsible_section import \
        CollapsibleSection
    _mk_project(window, kind="neo", name="2099 Coll")
    window._show_tab("process")  # the Process page builds on first open
    secs = window.projects.page_container.findChildren(CollapsibleSection)
    titles = {s._btn.text(): s for s in secs}
    cal = next((s for t, s in titles.items() if "alibr" in t.lower()), None)
    assert cal is not None and cal.isCollapsed()
    kept = next((s for t, s in titles.items()
                 if "kept" in t.lower() or "guardaste" in t.lower()), None)
    assert kept is not None and kept.isCollapsed()


def test_go_button_lands_on_target_tab(window, panel):
    # ADR-041: Go = activate the next-action's tab, no matter what
    # page is open now.
    _mk_project(window)
    window.projects.btn_tab_details.click()
    assert window._active_tab == "details"
    window.projects.btn_next_go.click()
    assert window._active_tab == "plan"
    assert not window._tab_pages["plan"].isHidden()
    assert window._tab_pages["details"].isHidden()


# ---------------- tab bar: one page visible at a time (ADR-041) --------


def test_activating_a_tab_hides_the_others(window, panel):
    # Opening any tab page hides the rest (one landing spot, no matter
    # which button the user clicks).
    _mk_project(window)
    pages = window._tab_pages
    assert not pages["plan"].isHidden()
    window.projects.btn_tab_process.click()
    assert not pages["process"].isHidden()
    for key in ("plan", "details"):
        assert pages[key].isHidden()
    assert "publish" not in pages  # untouched tab: still unbuilt (lazy)
    window.projects.btn_tab_publish.click()
    assert not pages["publish"].isHidden()
    assert pages["process"].isHidden()
    assert pages["details"].isHidden()
    assert pages["plan"].isHidden()


def test_opening_object_card_hides_open_step(window, panel):
    # The Object card is a tab like the steps: clicking it while a step
    # is active lands on the card and hides the step.
    _mk_project(window)
    assert window._active_tab == "plan"
    window.projects.btn_tab_details.click()
    assert window._active_tab == "details"
    assert not window._tab_pages["details"].isHidden()
    assert window._tab_pages["plan"].isHidden()


def test_tab_bar_buttons_mirror_the_active_tab(window, panel):
    # The bar is the "you are here" vocabulary: the active button is
    # checked, the others are not.
    _mk_project(window)
    btns = {key: getattr(window.projects, f"btn_tab_{key}")
            for key in ("details", "plan", "process", "publish",
                        "followup")}
    assert btns["plan"].isChecked()
    for key in ("details", "process", "publish", "followup"):
        assert not btns[key].isChecked()
    window.projects.btn_tab_details.click()
    assert btns["details"].isChecked()
    assert not btns["plan"].isChecked()


def test_followup_deep_link_lands_on_followup(window, panel):
    # Cadence chips and the follow-up entry point land on the Follow-up
    # page; every page built along the way hides behind the bar.
    p = _mk_project(window)
    window.projects.btn_tab_process.click()
    window.projects.btn_tab_details.click()
    assert window._active_tab == "details"
    window._goto_project_followup(p["id"])
    assert window._active_tab == "followup"
    assert not window._tab_pages["followup"].isHidden()
    for key in ("plan", "process", "details"):
        assert window._tab_pages[key].isHidden()
    assert "publish" not in window._tab_pages  # lazy: never opened


def test_go_button_enforces_single_active_page(window, panel):
    # No matter what page you were on, Go lands on the next action's
    # tab and enforces the one-visible-page rule before it.
    _mk_project(window)
    window.projects.btn_tab_process.click()
    window.projects.btn_tab_details.click()
    assert window._active_tab == "details"
    window.projects.btn_next_go.click()
    assert window._active_tab == "plan"
    assert not window._tab_pages["plan"].isHidden()
    for key in ("process", "details"):
        assert window._tab_pages[key].isHidden()


def test_exactly_one_page_visible(window, panel):
    # The invariant across every path — step actions, tab clicks, deep
    # links — is one and only one visible page in the scroll area.
    p = _mk_project(window)
    window._step_done("plan")
    window.projects.btn_tab_process.click()
    window.projects.btn_tab_details.click()
    window._goto_project_followup(p["id"])
    shown = [k for k, pg in window._tab_pages.items() if not pg.isHidden()]
    assert shown == ["followup"]


def test_files_section_lives_in_the_object_card(window, panel):
    # The nested "Project files" section lives inside the Object card's
    # tab page: it starts folded and a header click expands it without
    # moving the active tab.
    _mk_project(window)
    window.projects.btn_tab_details.click()
    sec = window._proj_files_section
    assert sec is not None and sec.isCollapsed()
    sec._btn.click()
    assert sec.isExpanded()
    assert window._active_tab == "details"
    assert not window._tab_pages["details"].isHidden()
    assert window._tab_pages["plan"].isHidden()


def test_switching_tabs_keeps_inner_fold_state(window, panel):
    # ADR-041: each tab page is its own world — the fold state of the
    # files list inside the Object card survives a round trip through
    # another tab; only one page is visible at any moment.
    _mk_project(window)
    window.projects.btn_tab_details.click()
    sec = window._proj_files_section
    sec._btn.click()  # expand the files list inside the card
    assert sec.isExpanded()
    window.projects.btn_tab_process.click()
    assert window._active_tab == "process"
    assert not window._tab_pages["process"].isHidden()
    assert window._tab_pages["details"].isHidden()
    assert sec.isExpanded()  # the card's fold state is kept, not reset
    window.projects.btn_tab_details.click()
    assert not window._tab_pages["details"].isHidden()
    assert sec.isExpanded()


def test_files_toggled_signal_fires_only_on_user_click(window, panel):
    # setCollapsed() stays silent (programmatic); a real header click
    # emits the new state (the section's recursion guard rests on this).
    _mk_project(window)
    sec = window._proj_files_section
    fires = []
    sec.sectionToggled.connect(fires.append)
    try:
        sec.setCollapsed(True)
        sec.setCollapsed(False)
        assert fires == []
        sec._btn.click()
        assert fires == [False]
        sec._btn.click()
        assert fires == [False, True]
    finally:
        sec.sectionToggled.disconnect(fires.append)


# ---------------- chips: the step state on the tab page headers --------


def test_chips_fresh_project(window, panel):
    # pending on the three real step pages, nothing on the object card
    # or the follow-up page.
    _mk_project(window)
    for key in ("process", "publish", "followup"):
        window._show_tab(key)  # the pages build on first open
    pages = window._tab_pages
    for key in ("plan", "process", "publish"):
        assert not pages[key]._chip.isHidden()
        assert pages[key]._chip.text() == window.tr("pending")
    assert pages["details"]._chip.isHidden()
    assert pages["followup"]._chip.isHidden()


def test_done_chip_carries_the_date(window, panel):
    p = _mk_project(window)
    window._step_done("plan")  # rebuilds: the next target (process) builds
    window._show_tab("plan")   # the done step's page builds on first open
    pages = window._tab_pages
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    step = next(s for s in proj_mod.get(mw.db, p["id"])["steps"]
                if s["step"] == "plan")
    date = datetime.datetime.fromtimestamp(step["updated"]).strftime(
        "%Y-%m-%d")
    assert pages["plan"]._chip.text() == \
        window.tr("done %1").replace("%1", date)
    window._show_tab("process")
    assert pages["process"]._chip.text() == window.tr("pending")
    window._show_tab("publish")
    assert pages["publish"]._chip.text() == window.tr("pending")


def test_skipped_chip(window, panel):
    # No skip control in the GUI (ADR-043): a "skipped" step can only
    # come from an old database, and the chip still has to mirror it.
    p = _mk_project(window)
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    proj_mod.set_step_status(mw.db, p["id"], "process",
                             proj_mod.STEP_SKIPPED)
    p = proj_mod.get(mw.db, p["id"])
    window._current_project = p
    window._build_project_page(p)
    window._show_tab("process")
    pages = window._tab_pages
    assert pages["process"]._chip.text() == window.tr("skipped")
    window._show_tab("plan")
    assert pages["plan"]._chip.text() == window.tr("pending")
    window._show_tab("publish")
    assert pages["publish"]._chip.text() == window.tr("pending")
