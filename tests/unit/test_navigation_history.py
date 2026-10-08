############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Navigation history tests (Interfaz 1.1, ADR-056)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The navigation history: from any screen, back returns to the previous
one (Alt+Left, the bar button or the mouse side button); Home is the root
(back disabled there); a project's tab is part of the location; the
new-project flow replaces Tonight so back goes to the hub; a manual visit
to Welcome does not seal the version. No network: _open_project is
stubbed to a light version (the panel is not what these tests check)."""

import os
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture()
def window(monkeypatch):
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    from nightscribe.config import config
    from nightscribe.core import project as proj_mod
    from nightscribe.core.db import db
    from nightscribe.version import base_version
    from nightscribe.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    config.set("lat", 40.0)
    config.set("lon", -3.0)
    config.set("app_version", base_version())
    p = proj_mod.create(db, "sn", "SN nav", {"ra_deg": 10.0, "dec_deg": 20.0})
    w = MainWindow()
    w.resize(1400, 900)
    w.show()
    w._now_timer.stop()
    for _ in range(6):
        app.processEvents()

    def _light_open(self, pid):
        row = proj_mod.get(db, pid)
        if not row:
            return False
        self._current_project = row
        self._goto_tab(__import__("nightscribe.gui.main_window",
                                  fromlist=["VIEW_DETAIL"]).VIEW_DETAIL)
        return True

    monkeypatch.setattr(w, "_open_project", types.MethodType(_light_open, w))
    yield w, p["id"], p
    w.close()


def _views():
    from nightscribe.gui import main_window as mw
    return mw


def test_home_is_the_root(window):
    w, _pid, _p = window
    mw = _views()
    assert w._shell_stack().currentIndex() == mw.VIEW_HOME
    assert w._nav_back == []
    assert not w._menus.btn_nav_back.isEnabled()


def test_project_and_back_and_forward(window):
    w, pid, _p = window
    mw = _views()
    w.navigate(mw.VIEW_DETAIL, pid=pid)
    assert w._shell_stack().currentIndex() == mw.VIEW_DETAIL
    assert w._menus.btn_nav_back.isEnabled()
    w.back()
    assert w._shell_stack().currentIndex() == mw.VIEW_HOME
    assert w._menus.btn_nav_fwd.isEnabled()
    w.forward()
    assert w._shell_stack().currentIndex() == mw.VIEW_DETAIL


def test_tab_change_is_in_the_history(window):
    w, pid, _p = window
    mw = _views()
    w.navigate(mw.VIEW_DETAIL, pid=pid, tab="plan")
    assert w._active_tab == "plan"
    w.navigate(mw.VIEW_DETAIL, pid=pid, tab="analysis")
    assert w._active_tab == "analysis"
    w.back()
    assert w._active_tab == "plan"          # the previous tab comes back
    w.back()
    assert w._shell_stack().currentIndex() == mw.VIEW_HOME


def test_ufe_returns_to_its_origin(window):
    w, pid, _p = window
    mw = _views()
    w.navigate(mw.VIEW_DETAIL, pid=pid)
    w._tools_ufe()
    assert w._shell_stack().currentIndex() == mw.VIEW_UFE
    w._ufe_back()
    assert w._shell_stack().currentIndex() == mw.VIEW_DETAIL


def test_campaigns_and_new_project_return(window):
    w, _pid, _p = window
    mw = _views()
    w.navigate(mw.VIEW_CAMPAIGNS)
    assert w._shell_stack().currentIndex() == mw.VIEW_CAMPAIGNS
    w.back()
    assert w._shell_stack().currentIndex() == mw.VIEW_HOME
    w._new_project_view()
    assert w._shell_stack().currentIndex() == mw.VIEW_TONIGHT
    w.back()
    assert w._shell_stack().currentIndex() == mw.VIEW_HOME


def test_welcome_entry_goes_back(window):
    w, pid, _p = window
    mw = _views()
    w.navigate(mw.VIEW_DETAIL, pid=pid)
    w.navigate(mw.VIEW_WELCOME)
    assert w._shell_stack().currentIndex() == mw.VIEW_WELCOME
    w.back()
    assert w._shell_stack().currentIndex() == mw.VIEW_DETAIL


def test_welcome_manual_ack_does_not_seal_version(window):
    from nightscribe.config import config
    from nightscribe.version import base_version
    w, _pid, _p = window
    mw = _views()
    # not an update: _update_due is False, so "Got it" just goes back
    assert w._update_due is False
    before = config.get("app_version")
    w.navigate(mw.VIEW_WELCOME)
    w._welcome_finished()
    assert config.get("app_version") == before
    assert w._shell_stack().currentIndex() == mw.VIEW_HOME


def test_deleted_project_in_history_falls_back_home(window):
    from nightscribe.core import project as proj_mod
    from nightscribe.core.db import db
    w, pid, _p = window
    mw = _views()
    w.navigate(mw.VIEW_DETAIL, pid=pid)
    w.back()                                # Home; Detail stays in forward
    proj_mod.delete(db, pid)
    w.forward()                             # to the now-deleted project
    assert w._shell_stack().currentIndex() == mw.VIEW_HOME


def test_breadcrumb_links(window):
    w, pid, _p = window
    mw = _views()
    w.navigate(mw.VIEW_DETAIL, pid=pid, tab="plan")
    html = w._menus.lbl_crumbs.text()
    # Home and the project are clickable; the active tab is the plain tail
    assert "nav:home" in html and f"nav:project:{pid}" in html
    w._crumb_clicked("nav:home")
    assert w._shell_stack().currentIndex() == mw.VIEW_HOME
