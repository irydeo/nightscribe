############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the AI master switch (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The AI master switch, off by default. What must hold: an endpoint alone
does not turn the AI on (the observer may have turned it off), and when it is
off every surface is closed, not left to fail: the Help action and the
editor's "?" button are disabled, with the reason in their tooltip."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def _refresh(monkeypatch, on):
    # @return: a fake MainWindow after one _refresh_ai_availability() pass
    from nightscribe.gui import main_window as mw
    from nightscribe.core.sources import llm
    monkeypatch.setattr(llm, "is_enabled", lambda cfg: on)
    win = mw.MainWindow.__new__(mw.MainWindow)
    win.tr = lambda s: s

    class _Act:
        def __init__(self):
            self.enabled = None
            self.tip = None

        def setEnabled(self, v):
            self.enabled = v

        def toolTip(self):
            return "the original tip"

        def setToolTip(self, t):
            self.tip = t

    class _Menus:
        action_assistant = _Act()

    class _Ufe:
        def set_ai_available(self, v):
            self.on = v

    win._menus = _Menus()
    win._assistant_tip = "the original tip"
    win._ufe = _Ufe()
    mw.MainWindow._refresh_ai_availability(win)
    return win


def test_refresh_closes_every_surface_when_the_ai_is_off(qapp, monkeypatch):
    win = _refresh(monkeypatch, on=False)
    assert win._menus.action_assistant.enabled is False
    assert "Settings" in win._menus.action_assistant.tip
    assert win._ufe.on is False


def test_refresh_reopens_them_when_the_ai_is_on(qapp, monkeypatch):
    win = _refresh(monkeypatch, on=True)
    assert win._menus.action_assistant.enabled is True
    # the reason is swapped back for the real tooltip
    assert win._menus.action_assistant.tip == "the original tip"
    assert win._ufe.on is True
