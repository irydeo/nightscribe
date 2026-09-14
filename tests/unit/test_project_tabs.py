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
  * the per-section toggle row drives the core step machine (done /
    reopen flip the current step exactly as core/project.py promises)

Same harness as test_projects_hub.py: a fake loader keeps the real
ExploreWorker out, and the db singleton is pointed at a temp file so no
test ever touches the real database.
"""

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
