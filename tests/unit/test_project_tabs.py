############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - project step tabs tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen tests for the project step tabs (UX v3, Plan & Captura).

The step tabs are rebuilt on every project switch (_build_step_tabs →
_clear_step_tabs). The plan tab mixes plain widgets with nested layout rows
(the CCDciel controls), and a wipe that only handled top-level widgets used
to leave those nested controls orphaned but still painted on top of the brand
new tab — the "lighter rectangle / piled buttons" bug. These tests drive a
throwaway MainWindow offscreen and assert the tabs hold exactly one copy of
every control after repeated rebuilds.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# The Qt headers mark the 3-arg QMouseEvent ctor (no device) as deprecated;
# it is still the right tool for a synthetic press test.
pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

FAKE_PROJECT = {
    "id": "prj-1",
    "object_name": "2016 XYZ",
    "kind": "neo",
    "context": {},
    "steps": [],
}

# One copy of every live control per step tab (kind "neo"):
# plan: sequence + 7 CCDciel + ephemeris + save plan
# process (neo): validate + save report + register FITS + register image +
#                motion animation (C0/C1)
# publish: generate post
PLAN_BUTTONS = 10
PROCESS_BUTTONS = 5
PUBLISH_BUTTONS = 1
PROJECT_WIDGETS = 25  # 21 plan + 2 MPC + products list + zoom spin (C0/C1)


@pytest.fixture(scope="module")
def window():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from nightscribe.gui import theme
    theme.apply_theme(app)
    from nightscribe import config as cfgmod
    from nightscribe.gui.main_window import MainWindow
    # Hide the configured flag so __init__ never schedules the network worker.
    real = cfgmod.config.is_configured
    cfgmod.config.is_configured = lambda: False
    w = MainWindow()
    cfgmod.config.is_configured = real
    yield w
    w.close()


def _rebuild(window):
    # Simulates a project switch: rebuild every step tab from scratch and let
    # the pending deleteLater() calls apply, so only live widgets remain.
    window._build_step_tabs(FAKE_PROJECT)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()


def _tab(window, name):
    from PySide6.QtWidgets import QWidget
    return window.projects.tabs_steps.findChild(QWidget, name)


def _buttons(tab):
    from PySide6.QtWidgets import QPushButton
    return tab.findChildren(QPushButton)


def _child_widgets(tab):
    # QWidget.children() includes the layout QObjects; keep only widgets, so
    # stray orphaned controls (parent still the tab) show up in the count.
    from PySide6.QtWidgets import QWidget as QWidgetClass
    return [c for c in tab.children() if isinstance(c, QWidgetClass)]


def test_step_tabs_hold_exactly_one_control_set_after_rebuilds(window):
    # Regression for the "lighter rectangle / piled buttons": orphaned CCDciel
    # buttons used to survive _clear_step_tabs and stack over the fresh tab,
    # gaining one extra copy on every project switch.
    _rebuild(window)
    plan = _tab(window, "tab_plan")
    first_texts = {b.text() for b in _buttons(plan)}
    assert len(first_texts) == len(_buttons(plan)), (
        "duplicated buttons in one build")
    # rebuild twice more: the control set must stay identical, never growing.
    _rebuild(window)
    _rebuild(window)
    for name, expected in (("tab_plan", PLAN_BUTTONS),
                           ("tab_process", PROCESS_BUTTONS),
                           ("tab_publish", PUBLISH_BUTTONS)):
        tab = _tab(window, name)
        btns = _buttons(tab)
        assert len(btns) == expected, (
            f"{name}: expected {expected} buttons, got {len(btns)}")
        texts = [b.text() for b in btns]
        assert len(texts) == len(set(texts)), f"{name}: duplicated buttons"
    # the plan-tab child list must not accumulate either
    assert len(_child_widgets(plan)) == len(
        _child_widgets(_tab(window, "tab_plan")))
    # the widgets dict holds one live set of handles (no stale ones)
    assert len(window._project_widgets) == PROJECT_WIDGETS


def test_clickable_frame_swallows_stale_object():
    # The row's C++ object may be deleteLater'd while its click runs a modal
    # dialog (explore) from inside mousePressEvent; the Python wrapper then
    # outlives the C++ frame. Pressing such a stale frame must not raise.
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui.main_window import _ClickableFrame

    app = QApplication.instance() or QApplication([])
    frame = _ClickableFrame()
    # Kill the C++ object while the Python wrapper stays reachable.
    frame.deleteLater()
    app.processEvents()
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(5, 5),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    frame.mousePressEvent(ev)  # must not raise RuntimeError
