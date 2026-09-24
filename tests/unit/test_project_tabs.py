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
  * every deep link (Next-card Go, the follow-up entry point) lands
    on the right page and enforces the one-visible-page rule
  * the masthead "Files (n)" button (disabled at zero) opens the
    project files window: one persistent dialog, re-keyed to the
    current project on every show (the old nested "Project files"
    section inside the Object card is retired)
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
    for key in ("details", "plan", "analysis", "publish", "analysis"):
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
    for key in ("plan", "analysis", "publish"):
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


def test_analysis_tab_exists_for_every_kind(window, panel):
    # ADR-045: the Analysis tab (and its page) exists for EVERY kind —
    # the visits manager is its core for all; the photometry blocks
    # inside stay kind-gated. A deep link to it is always honoured.
    _mk_project(window, kind="neo", name="2099 PG1")
    assert not window.projects.btn_tab_analysis.isHidden()
    window._show_tab("analysis")
    assert window._active_tab == "analysis"
    assert "analysis" in window._tab_pages
    _mk_project(window, kind="sn", name="SN 2099pg2")
    assert not window.projects.btn_tab_analysis.isHidden()
    window._show_tab("analysis")
    assert window._active_tab == "analysis"
    assert "analysis" in window._tab_pages


def test_step_toggle_marks_done(window, panel):
    p = _mk_project(window)
    window._step_done("plan")
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, p["id"])["steps"]}
    assert steps["plan"] == "done"
    assert steps["analysis"] == "current"


def test_step_reopen(window, panel):
    p = _mk_project(window)
    window._step_done("plan")
    window._step_reopen("plan")
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, p["id"])["steps"]}
    assert steps["plan"] == "current"
    assert steps["analysis"] == "pending"


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
    assert window._active_tab == "analysis"
    assert not window._tab_pages["analysis"].isHidden()
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
    assert window._next_step_key == "analysis"


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
    assert window._next_step_key == "analysis"


def test_step_footer_reopens_a_legacy_skipped_step(window, panel):
    # ADR-043: the GUI can no longer produce a "skipped" step, but an old
    # database may carry one: its footer still offers "Reopen step", and
    # the click moves the flow back to it (single-current invariant).
    from PySide6.QtWidgets import QPushButton
    p = _mk_project(window, name="SN 2099rs")
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    proj_mod.set_step_status(mw.db, p["id"], "analysis",
                             proj_mod.STEP_SKIPPED)
    p = proj_mod.get(mw.db, p["id"])
    window._current_project = p
    window._build_project_page(p)
    window._show_tab("analysis")  # the skipped step's page builds on first open
    page = window._tab_pages["analysis"]
    btns = [b for b in page.findChildren(QPushButton)
            if "Reopen" in b.text() or "Reabrir" in b.text()]
    assert len(btns) == 1
    btns[0].click()
    steps = {s["step"]: s["status"]
             for s in proj_mod.get(mw.db, p["id"])["steps"]}
    assert steps["analysis"] == "current"
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
    window._show_tab("analysis")  # the Process page builds on first open
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
    window.projects.btn_tab_analysis.click()
    assert not pages["analysis"].isHidden()
    for key in ("plan", "details"):
        assert pages[key].isHidden()
    assert "publish" not in pages  # untouched tab: still unbuilt (lazy)
    window.projects.btn_tab_publish.click()
    assert not pages["publish"].isHidden()
    assert pages["analysis"].isHidden()
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
            for key in ("details", "plan", "analysis", "publish",
                        "analysis")}
    assert btns["plan"].isChecked()
    for key in ("details", "analysis", "publish", "analysis"):
        assert not btns[key].isChecked()
    window.projects.btn_tab_details.click()
    assert btns["details"].isChecked()
    assert not btns["plan"].isChecked()


def test_analysis_deep_link_lands_on_analysis(window, panel):
    # Cadence chips and the follow-up entry point land on the Analysis
    # page (ADR-045); every page built along the way hides behind the bar.
    p = _mk_project(window)
    window.projects.btn_tab_analysis.click()
    window.projects.btn_tab_details.click()
    assert window._active_tab == "details"
    window._goto_project_followup(p["id"])
    assert window._active_tab == "analysis"
    assert not window._tab_pages["analysis"].isHidden()
    for key in ("plan", "details"):
        assert window._tab_pages[key].isHidden()
    assert "publish" not in window._tab_pages  # lazy: never opened


def test_go_button_enforces_single_active_page(window, panel):
    # No matter what page you were on, Go lands on the next action's
    # tab and enforces the one-visible-page rule before it.
    _mk_project(window)
    window.projects.btn_tab_analysis.click()
    window.projects.btn_tab_details.click()
    assert window._active_tab == "details"
    window.projects.btn_next_go.click()
    assert window._active_tab == "plan"
    assert not window._tab_pages["plan"].isHidden()
    for key in ("analysis", "details"):
        assert window._tab_pages[key].isHidden()


def test_exactly_one_page_visible(window, panel):
    # The invariant across every path — step actions, tab clicks, deep
    # links — is one and only one visible page in the scroll area.
    p = _mk_project(window)
    window._step_done("plan")
    window.projects.btn_tab_analysis.click()
    window.projects.btn_tab_details.click()
    window._goto_project_followup(p["id"])
    shown = [k for k, pg in window._tab_pages.items() if not pg.isHidden()]
    assert shown == ["analysis"]


# ---------------- A4: the masthead "Files (n)" button and its window --


def test_files_button_off_for_an_empty_project(window, panel):
    # The button mirrors the file count: a fresh project has none, so
    # it is disabled and reads "Files (0)"; the old in-card section
    # attributes are gone for good.
    _mk_project(window)
    btn = window.projects.btn_files
    assert not btn.isEnabled()
    assert btn.text() == window.tr("Files (0)")
    assert not hasattr(window, "_proj_files_section")
    assert not hasattr(window, "_proj_files_list")


def test_files_button_opens_the_files_window(window, panel):
    # With files registered the button is on and shows its live count;
    # clicking it opens the files window for the current project with
    # the files in registration order.
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p = _mk_project(window)
    project.add_file(dbmod.db, p["id"], "/tmp/tab_seq.targets", "sequence")
    project.add_file(dbmod.db, p["id"], "/tmp/tab_blink.gif", "chart")
    window._populate_project_files(p["id"])
    btn = window.projects.btn_files
    assert btn.isEnabled()
    assert btn.text() == window.tr("Files (2)")
    btn.click()
    dlg = window._proj_files_dlg
    assert dlg is not None
    assert dlg.isVisible()
    assert dlg.project_id == p["id"]
    assert dlg.tbl.rowCount() == 2
    kinds = {dlg.tbl.item(i, 0).text() for i in range(dlg.tbl.rowCount())}
    assert kinds == {"sequence", "chart"}


def test_files_window_survives_project_switch_and_rekeys(window, panel):
    # The dialog is one persistent instance: a project switch leaves it
    # open and still attached to the first project, and a re-show
    # re-keys it onto the project open at that moment (not whichever
    # one first opened it).
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p1 = _mk_project(window)
    project.add_file(dbmod.db, p1["id"], "/tmp/a1.targets", "sequence")
    window._populate_project_files(p1["id"])
    window.projects.btn_files.click()
    dlg = window._proj_files_dlg
    assert dlg.isVisible()
    assert dlg.project_id == p1["id"]
    assert dlg.tbl.rowCount() == 1
    # switch to a second project while the window is open...
    p2 = _mk_project(window, name="SN 2100qh")
    project.add_file(dbmod.db, p2["id"], "/tmp/b1.gif", "chart")
    window._populate_project_files(p2["id"])
    # ...the window stays, still attached to the first project...
    assert dlg.isVisible()
    assert dlg.project_id == p1["id"]
    # ...until it is shown again, when it re-keys onto the current one.
    window.projects.btn_files.click()
    assert window._proj_files_dlg is dlg     # one dialog, never rebuilt
    assert dlg.project_id == p2["id"]
    assert dlg.tbl.rowCount() == 1
    assert dlg.tbl.item(0, 0).text() == "chart"


# ---------------- chips: the step state on the tab page headers --------


def test_chips_fresh_project(window, panel):
    # pending on the three real step pages, nothing on the object card
    # (ADR-045: Analysis is a step now, so it carries the chip).
    _mk_project(window)
    for key in ("analysis", "publish", "analysis"):
        window._show_tab(key)  # the pages build on first open
    pages = window._tab_pages
    for key in ("plan", "analysis", "publish"):
        assert not pages[key]._chip.isHidden()
        assert pages[key]._chip.text() == window.tr("pending")
    assert pages["details"]._chip.isHidden()


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
    window._show_tab("analysis")
    assert pages["analysis"]._chip.text() == window.tr("pending")
    window._show_tab("publish")
    assert pages["publish"]._chip.text() == window.tr("pending")


def test_skipped_chip(window, panel):
    # No skip control in the GUI (ADR-043): a "skipped" step can only
    # come from an old database, and the chip still has to mirror it.
    p = _mk_project(window)
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    proj_mod.set_step_status(mw.db, p["id"], "analysis",
                             proj_mod.STEP_SKIPPED)
    p = proj_mod.get(mw.db, p["id"])
    window._current_project = p
    window._build_project_page(p)
    window._show_tab("analysis")
    pages = window._tab_pages
    assert pages["analysis"]._chip.text() == window.tr("skipped")
    window._show_tab("plan")
    assert pages["plan"]._chip.text() == window.tr("pending")
    window._show_tab("publish")
    assert pages["publish"]._chip.text() == window.tr("pending")
