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


def test_manual_target_creates_and_opens_the_project(make_window):
    from nightscribe.gui.main_window import VIEW_DETAIL
    w = make_window
    p = w._new_project_from_target(
        {"name": "X 2099", "kind": "sn", "ra_deg": 10.0, "dec_deg": 20.0})
    assert p is not None
    assert p["object_name"] == "X 2099"
    # the creation path lands on the project's full-screen view
    assert w._shell_stack().currentIndex() == VIEW_DETAIL


def test_bar_exists_on_the_tonight_view(make_window):
    w = make_window
    assert w._newbar is not None
    assert w._newbar.parent() is not None
