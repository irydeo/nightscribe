############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - New-project flow tests (Interfaz 1.0, ADR-053)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The new-project view: Tonight is computed on demand (never at start),
and the search bar / manual form build a target the app turns into a
project. No network: the resolve worker is not exercised here."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(autouse=True)
def _empty_db(tmp_path):
    # The unit suite shares ONE database for the whole session, so "is this
    # the first project?" would depend on what another module (or another
    # test in this one) created. These tests are about exactly that
    # question, so each gets its own empty file.
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path / "newproject.db")
    dbmod.db = tmp
    mw.db = tmp
    yield
    dbmod.db = old_dbmod
    mw.db = old_mw


@pytest.fixture()
def make_window(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    from nightscribe.config import config
    from nightscribe.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    monkeypatch.setattr(config, "is_configured", lambda: False)
    w = MainWindow()
    w._now_timer.stop()
    yield w
    w.close()


def test_tonight_is_not_computed_when_unconfigured(make_window):
    from nightscribe.gui.main_window import VIEW_TONIGHT
    w = make_window
    assert w._tonight_loaded is False
    w._goto_tab(VIEW_TONIGHT)
    # no site: nothing is computed, the header explains why
    assert w._tonight_running is False
    assert w._tonight_loaded is False
    assert w.tonight.lbl_context.text()


def test_manual_target_creates_and_opens_the_project(make_window,
                                                     monkeypatch):
    from nightscribe.config import config
    from nightscribe.gui.main_window import VIEW_DETAIL
    # a configured observatory: the first project needs one (see below)
    monkeypatch.setattr(config, "is_configured", lambda: True)
    w = make_window
    p = w._new_project_from_target(
        {"name": "X 2099", "kind": "sn", "ra_deg": 10.0, "dec_deg": 20.0})
    assert p is not None
    assert p["object_name"] == "X 2099"
    # the creation path lands on the project's full-screen view
    assert w._shell_stack().currentIndex() == VIEW_DETAIL


def test_the_first_project_needs_the_observatory(make_window):
    # Reported 2026-10-17: with the setup unfinished the app still let a
    # first project be created, because the funnel every path goes through
    # (_create_project) did not check anything. A project is planned,
    # exposed and reported FROM THE SITE, so it is refused, said, and the
    # setup opens on the step that unblocks it.
    from nightscribe.gui.main_window import VIEW_WELCOME
    w = make_window
    assert w._setup_blocker()
    p = w._new_project_from_target(
        {"name": "X 2099", "kind": "sn", "ra_deg": 10.0, "dec_deg": 20.0})
    assert p is None
    assert w.projects.lst_projects.count() == 0
    # the refusal has a door: Welcome, on its first step
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
    assert w._welcome is not None
    # and the funnel refuses on its own, so Explore, the campaigns and any
    # deep link cannot slip past it
    assert w._create_project({"name": "Y 2099", "kind": "sn"}) is None
    assert w.projects.lst_projects.count() == 0


def test_a_second_project_is_not_blocked(make_window):
    # The lock is on the FIRST one: the site is a global setting, so an
    # observer who already has projects is never held back (this is not a
    # jail, and their existing projects must keep working).
    from nightscribe.core import project as project_mod
    import nightscribe.gui.main_window as mw
    w = make_window
    project_mod.create(mw.db, "sn", "Already here")
    assert w._setup_blocker() is None
    p = w._create_project({"name": "Z 2099", "kind": "sn"})
    assert p is not None and p["object_name"] == "Z 2099"


def test_bar_exists_on_the_tonight_view(make_window):
    w = make_window
    assert w._newbar is not None
    assert w._newbar.parent() is not None
