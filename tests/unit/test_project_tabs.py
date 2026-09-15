############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - project page sections tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Unit tests: project page sections (UX, UD.3).

The project page's step tabs and wizard were replaced by collapsible
sections (docs/PLANS/ux/fase-d-project-flow.md, UD.3). These tests drive a
throwaway MainWindow offscreen and check the new contracts:

  * the page is a scroll area wrapping one content widget, and selecting a
    project builds every section (details first, then the three steps, and
    follow-up for the kinds that keep a multi-night journal)
  * rebuilds wipe the previous control set (no piled "Mark done" buttons)
  * the page accordion: a header click opening any section (object card
    included) closes the other open section, all-closed is a legal state,
    every deep link lands on the sole open section
  * the chip on each step header mirrors the step state (done <date> /
    skipped / pending); follow-up carries no chip at all

Same harness as test_projects_hub.py: a fake loader keeps the real
ExploreWorker out, and the db singleton is pointed at a temp file so no
test ever touches the real database.
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


def test_page_has_sections_instead_of_tabs(window, panel):
    _mk_project(window)
    assert hasattr(window.projects, "scroll_page")
    assert set(window._page_sections) >= {"details", "plan", "process",
                                          "publish", "followup"}


def test_sections_hold_exactly_one_control_set_after_rebuilds(window, panel):
    p = _mk_project(window)
    window._build_project_page(window._current_project)
    window._build_project_page(window._current_project)
    from PySide6.QtWidgets import QPushButton
    names = [b.text() for b in window.projects.page_container
             .findChildren(QPushButton)]
    assert names.count("Mark done") + names.count("Marcar hecho") == 3


def test_page_is_scroll_wrapped(window, panel):
    _mk_project(window)
    assert window.projects.scroll_page.widget() is \
        window.projects.page_container


def test_followup_section_only_for_followup_kinds(window, panel):
    _mk_project(window, kind="neo", name="2099 PG1")
    assert "followup" not in window._page_sections
    _mk_project(window, kind="sn", name="SN 2099pg2")
    assert "followup" in window._page_sections


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


def test_next_card_points_at_pending_section(window, panel):
    _mk_project(window)
    assert "Plan" in window.projects.lbl_next.text() or \
        "Planifica" in window.projects.lbl_next.text()
    secs = window._page_sections
    # fresh project: the next-action section (plan) is the only one open,
    # the object card starts folded like everything else
    assert secs["plan"].isCollapsed() is False
    for key in ("details", "process", "publish", "followup"):
        assert secs[key].isCollapsed() is True


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
    assert window._page_sections["followup"].isCollapsed() is False


def test_go_button_expands_target(window, panel):
    _mk_project(window)
    window._page_sections["plan"].setCollapsed(True)
    window.projects.btn_next_go.click()
    assert window._page_sections["plan"].isCollapsed() is False


# ------- page accordion: at most one section open at a time --------------


def test_header_click_closes_other_open_section(window, panel):
    # Opening a step closes the other open section (exclusive accordion),
    # object card included — one landing spot, no matter which one the
    # user clicks.
    _mk_project(window)
    secs = window._page_sections
    assert secs["plan"].isExpanded()
    assert secs["details"].isCollapsed()
    secs["process"]._btn.click()
    assert secs["process"].isExpanded()
    for key in ("plan", "details", "publish", "followup"):
        assert secs[key].isCollapsed()
    secs["publish"]._btn.click()
    assert secs["publish"].isExpanded()
    assert secs["process"].isCollapsed()
    assert secs["details"].isCollapsed()


def test_opening_object_card_closes_open_step(window, panel):
    # The object card belongs to the same accordion: clicking its header
    # while a step is open folds that step before expanding the card.
    _mk_project(window)
    secs = window._page_sections
    assert secs["plan"].isExpanded()
    secs["details"]._btn.click()
    assert secs["details"].isExpanded()
    for key in ("plan", "process", "publish", "followup"):
        assert secs[key].isCollapsed()


def test_all_sections_can_be_closed(window, panel):
    # Closing the only open section by hand is legal: nothing is forced
    # open again (a 0-section state is a resting state, not an error).
    _mk_project(window)
    secs = window._page_sections
    secs["plan"]._btn.click()
    for key in ("details", "plan", "process", "publish", "followup"):
        assert secs[key].isCollapsed()


def test_followup_deep_link_is_the_sole_open_section(window, panel):
    # Cadence chips and the follow-up entry point land on Follow-up
    # with every other section closed (the plan opened by the build
    # and the object card are silenced, not echoed).
    p = _mk_project(window)
    window._page_sections["process"].setCollapsed(False)
    window._page_sections["details"].setCollapsed(False)
    window._goto_project_followup(p["id"])
    secs = window._page_sections
    assert secs["followup"].isExpanded()
    for key in ("plan", "process", "publish", "details"):
        assert secs[key].isCollapsed()


def test_go_button_closes_accidental_siblings(window, panel):
    # Leaving several sections open by hand and then pressing Go for
    # the next action enforces the invariant before landing.
    _mk_project(window)
    secs = window._page_sections
    secs["process"].setCollapsed(False)
    secs["details"].setCollapsed(False)
    assert secs["plan"].isExpanded() and secs["process"].isExpanded()
    window.projects.btn_next_go.click()
    assert secs["plan"].isExpanded()
    assert secs["process"].isCollapsed()
    assert secs["details"].isCollapsed()


def test_opening_files_closes_open_step(window, panel):
    # The nested "Project files" section joins the same accordion: a
    # click opens it and folds the open step, but its parent object
    # card stays open — the files list lives inside it.
    _mk_project(window)
    secs = window._page_sections
    assert secs["plan"].isExpanded()
    secs["details"].setCollapsed(False)  # files is visible once the card opens
    secs["files"]._btn.click()
    assert secs["files"].isExpanded()
    assert secs["details"].isExpanded()
    for key in ("plan", "process", "publish", "followup"):
        assert secs[key].isCollapsed()


def test_opening_a_step_closes_files(window, panel):
    # The other way round: leaving the files section opened and clicking
    # any other header (step or card) folds the files again.
    _mk_project(window)
    secs = window._page_sections
    secs["details"].setCollapsed(False)
    secs["files"]._btn.click()
    assert secs["files"].isExpanded()
    secs["process"]._btn.click()
    assert secs["process"].isExpanded()
    assert secs["files"].isCollapsed()
    assert secs["details"].isCollapsed()


def test_step_toggled_signal_fires_only_on_user_click(window, panel):
    # setCollapsed() stays silent (programmatic); a real header click
    # emits the new state. The accordion recursion guard rests on this.
    _mk_project(window)
    sec = window._page_sections["process"]
    fires = []
    sec.sectionToggled.connect(fires.append)
    try:
        sec.setCollapsed(False)
        sec.setCollapsed(True)
        assert fires == []
        sec._btn.click()
        sec._btn.click()
        assert fires == [True, False]
    finally:
        sec.sectionToggled.disconnect(fires.append)


# ---------------- header chip: the step state on the accordion header ---


def test_chips_fresh_project(window, panel):
    # pending on the three real steps, nothing on the follow-up section.
    _mk_project(window)
    secs = window._page_sections
    for key in ("plan", "process", "publish"):
        assert secs[key].headerBadge() == window.tr("pending")
    assert secs["followup"].headerBadge() == ""
    assert secs["followup"]._badge.isHidden()


def test_done_chip_carries_the_date(window, panel):
    p = _mk_project(window)
    window._step_done("plan")
    secs = window._page_sections  # the step action rebuilds the page
    from nightscribe.core import project as proj_mod
    from nightscribe.gui import main_window as mw
    step = next(s for s in proj_mod.get(mw.db, p["id"])["steps"]
                if s["step"] == "plan")
    date = datetime.datetime.fromtimestamp(step["updated"]).strftime(
        "%Y-%m-%d")
    assert secs["plan"].headerBadge() == \
        window.tr("done %1").replace("%1", date)
    assert secs["process"].headerBadge() == window.tr("pending")
    assert secs["publish"].headerBadge() == window.tr("pending")


def test_skipped_chip(window, panel):
    _mk_project(window)
    window._step_skip("process")
    secs = window._page_sections
    assert secs["process"].headerBadge() == window.tr("skipped")
    assert secs["plan"].headerBadge() == window.tr("pending")
    assert secs["publish"].headerBadge() == window.tr("pending")
