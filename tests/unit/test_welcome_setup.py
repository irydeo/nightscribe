############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Welcome view tests (Interfaz 1.0, ADR-053)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Welcome view replaces the modal first-run/update wizard: it hosts
the three setup steps inline and gates navigation on the update's Data
step. These tests pin the decision (when Welcome is shown), the gate and
the CTA's site requirement. No network: the detect/resolve buttons are not
exercised here (they are the wizard's own, tested by hand)."""

import os
from pathlib import Path

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
    # a first run with no site: Welcome is due
    monkeypatch.setattr(config, "is_configured", lambda: False)
    # an "old" version forces the update path too
    config.set("app_version", "")
    windows = []

    def _make(snapshot=None):
        w = MainWindow(snapshot=snapshot)
        w._now_timer.stop()
        w._blink_timer.stop()
        w._blink_render_timer.stop()
        windows.append(w)
        return w

    yield _make
    for w in windows:
        w.close()


def test_first_run_shows_welcome(make_window):
    from nightscribe.gui.main_window import VIEW_WELCOME
    w = make_window(snapshot=None)
    assert w._welcome is not None
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
    # no database to report on: no gate
    assert w._welcome_gate is False


def test_first_run_stays_on_welcome_after_the_startup_refresh(make_window):
    # Regression: the deferred on_refresh_projects() found no selection and
    # _clear_project_detail -> _show_dashboard used to switch to Home,
    # yanking the observer out of Welcome on the very first frame.
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui.main_window import VIEW_WELCOME
    w = make_window(snapshot=None)
    for _ in range(6):
        QApplication.processEvents()
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
    assert w._welcome is not None


def test_update_is_a_gate_until_acknowledged(make_window):
    from nightscribe.gui.main_window import VIEW_WELCOME, VIEW_HOME
    snap = {"integrity": "ok", "file": Path("nightscribe-before.db"),
            "size": 1024, "schema_version": 0}
    w = make_window(snapshot=snap)
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
    assert w._welcome_gate is True
    # every other view is blocked while the report is unacknowledged
    w._goto_tab(VIEW_HOME)
    assert w._shell_stack().currentIndex() == VIEW_WELCOME
    # acknowledging unlocks and lands on Home
    w._welcome_finished()
    assert w._welcome_gate is False
    assert w._shell_stack().currentIndex() == VIEW_HOME


def test_cta_needs_a_site(make_window):
    w = make_window(snapshot=None)
    ws = w._welcome
    u = ws.ui
    u.spn_site_lat.setValue(0.0)
    u.spn_site_lon.setValue(0.0)
    u.edt_site_mpc.setText("")
    ws._refresh_create()
    assert not u.btn_create.isEnabled()
    u.spn_site_lat.setValue(40.41678)
    u.spn_site_lon.setValue(-3.70379)
    ws._refresh_create()
    assert u.btn_create.isEnabled()


def test_stepper_switches_panels(make_window):
    w = make_window(snapshot=None)
    u = w._welcome.ui
    w._welcome.show_step("kinds")
    assert u.setup_stack.currentIndex() == 1
    w._welcome.show_step("data")
    assert u.setup_stack.currentIndex() == 2
    assert u.btn_step_data.isChecked()
