############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the assistant window (ADR-075)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The assistant window, offscreen. The LLM call is monkeypatched. What must
hold: the scopes offered follow the ground available, without an endpoint the
window says so and does not send, and a failure is shown instead of being
swallowed."""

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


def _win(monkeypatch, configured, object_name=None, editor=False):
    from nightscribe.gui import assistant_window as aw
    monkeypatch.setattr(aw.llm, "is_configured", lambda cfg: configured)
    monkeypatch.setattr(aw.llm, "is_enabled", lambda cfg: configured)
    return aw.AssistantWindow(
        object_name=object_name,
        editor_state_provider=(lambda: {"tab": "Photometry"}) if editor
        else None)


def _scopes(win):
    c = win._ui.cmb_scope
    return [c.itemData(i) for i in range(c.count())]


def test_scopes_follow_the_ground_available(qapp, monkeypatch):
    win = _win(monkeypatch, True, object_name="SN 2026abc", editor=True)
    assert _scopes(win) == ["object", "app", "editor"]
    win.deleteLater()
    win2 = _win(monkeypatch, True)
    assert _scopes(win2) == ["app"]
    win2.deleteLater()


def test_the_window_is_marked_experimental(qapp, monkeypatch):
    # ADR-075: the assistant is presented as experimental
    win = _win(monkeypatch, True, object_name="SN 2026abc")
    assert "experimental" in win.windowTitle().lower()
    win.deleteLater()


def test_without_endpoint_it_says_so_and_does_not_send(qapp, monkeypatch):
    win = _win(monkeypatch, False, object_name="X")
    assert not win._ui.btn_send.isEnabled()
    assert not win._ui.edt_question.isEnabled()
    assert "Settings" in win._ui.lbl_hint.text()
    win.deleteLater()


def test_send_appends_the_question_and_starts_a_worker(qapp, monkeypatch):
    from nightscribe.gui import workers
    seen = {}

    class _FakeWorker:
        def __init__(self, cfg, scope, question, history, brief_provider=None,
                     editor_state=None):
            seen["scope"] = scope
            seen["q"] = question

        done = type("D", (), {
            "connect": staticmethod(lambda fn: seen.__setitem__("fn", fn))})

        def start(self):
            seen["started"] = True

        def isRunning(self):
            return False

    monkeypatch.setattr(workers, "AssistantWorker", _FakeWorker)
    win = _win(monkeypatch, True, object_name="SN 2026abc")
    win._ui.edt_question.setText("¿puedo hacer la curva?")
    win._ui.btn_send.click()
    assert seen["started"]
    assert seen["q"] == "¿puedo hacer la curva?"
    assert "You" in win._ui.txt_log.toPlainText()
    assert not win._ui.btn_send.isEnabled()
    win.deleteLater()


def test_done_shows_the_answer_and_its_sources(qapp, monkeypatch):
    win = _win(monkeypatch, True)
    win._done("usa la pestaña Fotometría", ["user/06-photometry.es.md"], "")
    txt = win._ui.txt_log.toPlainText()
    assert "usa la pestaña Fotometría" in txt
    assert "06-photometry" in win._ui.lbl_sources.text()
    assert win._ui.btn_send.isEnabled()
    win.deleteLater()


def test_a_failure_is_shown_not_swallowed(qapp, monkeypatch):
    win = _win(monkeypatch, True)
    win._done("", [], "the endpoint answered 401")
    assert "401" in win._ui.txt_log.toPlainText()
    win.deleteLater()


def test_clear_forgets_the_conversation(qapp, monkeypatch):
    win = _win(monkeypatch, True)
    win._done("hola", ["x"], "")
    win._clear()
    assert win._ui.txt_log.toPlainText().strip() == ""
    assert win._history == []
    win.deleteLater()


def test_help_entry_opens_the_assistant(qapp, monkeypatch):
    from nightscribe.gui import main_window as mw
    from nightscribe.gui import assistant_window as aw
    seen = {}

    class _FakeWin:
        def __init__(self, object_name=None, brief_provider=None,
                     editor_state_provider=None, start_scope=None,
                     parent=None):
            seen["object_name"] = object_name
            seen["start"] = start_scope

        def show(self):
            seen["shown"] = True

        def raise_(self):
            pass

        def activateWindow(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(aw, "AssistantWindow", _FakeWin)
    from nightscribe.core.sources import llm
    monkeypatch.setattr(llm, "is_enabled", lambda cfg: True)
    win = mw.MainWindow.__new__(mw.MainWindow)
    win._current_project = None
    mw.MainWindow._open_assistant(win)
    assert seen["shown"] and seen["start"] == "app"
    assert seen["object_name"] is None


def test_help_entry_is_a_no_op_when_the_ai_is_off(qapp, monkeypatch):
    # ADR-075: with the master switch off, the Help action (disabled) must
    # not open any dialog even if it were somehow triggered
    from nightscribe.gui import main_window as mw
    from nightscribe.gui import assistant_window as aw
    from nightscribe.core.sources import llm
    opened = {"n": 0}

    class _FakeWin:
        def __init__(self, *a, **k):
            opened["n"] += 1

        def show(self):
            pass

        def raise_(self):
            pass

        def activateWindow(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(aw, "AssistantWindow", _FakeWin)
    monkeypatch.setattr(llm, "is_enabled", lambda cfg: False)
    win = mw.MainWindow.__new__(mw.MainWindow)
    win._current_project = None
    mw.MainWindow._open_assistant(win)
    assert opened["n"] == 0


def test_the_editor_bar_has_the_ask_button(qapp):
    from nightscribe.gui.ui_loader import load_ui
    ui = load_ui("ufe_dialog")
    assert hasattr(ui, "btn_ask")
    ui.deleteLater()
