############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the workbench's tool windows (ADR-044 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Blink, Calibration, Annotate and the photometric series left the tab
column and became non-modal windows opened from the top bar (asked for
2026-10-06).

What these tests pin: the column keeps the two panels an observer lives in,
the four tools are windows of their own, ONE at a time owns the plate (the
blink frame, the annotate clicks), the door button opens and closes, a deep
link opens the right one, leaving the workbench hides them (they must not
hang over the project the observer went back to) and closing the workbench
takes them with it.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures")
MONO = os.path.join(FIXTURES, "sn2026zji_new_image.fits")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture
def dlg(qapp):
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    yield d
    d.tab_blink.shutdown()
    d.view._render_timer.stop()
    d.deleteLater()


def test_the_column_keeps_the_two_panels_and_the_tools_are_windows(dlg):
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Photometry", "Astrometry"]
    for key in ("blink", "calibrate", "annotate", "series"):
        window = dlg._tools[key]
        assert window.isModal() is False
        assert window.panel is not None
        assert not window.isVisible()       # built, not shown


def test_a_tool_opens_from_its_button_and_the_door_closes_it(dlg):
    assert not dlg._tools["blink"].isVisible()
    dlg.btn_tool_blink.click()
    assert dlg._tools["blink"].isVisible()
    assert dlg._active_tool == "blink"
    dlg.btn_tool_blink.click()              # the door, not a one-way trip
    assert not dlg._tools["blink"].isVisible()
    assert dlg._active_tool is None


def test_one_tool_at_a_time(dlg):
    # Two windows owning the plate at once would be two answers to "what
    # does a click do": opening one closes the others.
    dlg.open_tool("blink")
    dlg.open_tool("annotate")
    assert not dlg._tools["blink"].isVisible()
    assert dlg._tools["annotate"].isVisible()
    assert dlg._active_tool == "annotate"


def test_the_stage_comes_back_to_the_panel_when_the_tool_closes(dlg):
    # The panel in the column had the plate; the tool takes it while its
    # window is open and gives it back when it closes.
    dlg.tabs.setCurrentWidget(dlg.tab_photometry)
    assert dlg.tab_photometry._on_stage
    dlg.open_tool("blink")
    assert not dlg.tab_photometry._on_stage
    dlg._tools["blink"].close_panel()
    assert dlg.tab_photometry._on_stage


def test_a_deep_link_opens_the_tool_window(dlg):
    # The host deep-links with show_tab("annotate") / ("blink") /
    # ("calibration") and with the panel widget itself: all of them open the
    # window (they used to select the tab).
    dlg.show_tab("annotate")
    assert dlg._tools["annotate"].isVisible()
    dlg.show_tab(dlg.tab_blink)
    assert dlg._tools["blink"].isVisible()
    assert not dlg._tools["annotate"].isVisible()
    # and the panels that DID stay are still selected by name
    dlg.show_tab("trackstack")
    assert dlg.tabs.currentWidget() is dlg.tab_trackstack


def test_leaving_the_workbench_hides_the_windows_without_losing_them(dlg):
    # The shell switches to another view: the windows are children of the
    # workbench page and would hang over the project. HIDDEN, never
    # destroyed (the blink pair and the annotation in progress survive).
    dlg.open_tool("blink")
    dlg.leave_view()
    assert not dlg._tools["blink"].isVisible()
    assert dlg._active_tool is None
    dlg.open_tool("blink")
    assert dlg._tools["blink"].isVisible()


def test_shutdown_takes_the_windows_away(dlg):
    dlg.open_tool("annotate")
    dlg.shutdown()
    assert not dlg._tools["annotate"].isVisible()


def test_the_window_is_sized_to_its_content(dlg):
    # The panels were laid out for a 380 px column; in a window they get a
    # width they can breathe in and the height their rows really need (the
    # size hints lie about a form's height, so the window measures the
    # laid-out rows, like UfeManualDialog documents).
    window = dlg.open_tool("blink")
    window.resize(window.minimumWidth(), 200)
    window._fit_to_content()
    assert window.width() >= 460
    assert window.height() >= 160
    assert window.height() < 900          # a form, not a full screen
    assert window.panel.parent() is window


def test_the_series_door_is_armed_by_the_visit(dlg):
    # D8: without a visit there is no series, and the button says why
    # instead of opening an empty window (ADR-038).
    assert not dlg.btn_tool_series.isEnabled()
    assert "visit" in dlg.btn_tool_series.toolTip()
    dlg.set_series_hook(lambda scope="visit": {"pid": 1, "session_id": 2,
                                               "paths": []})
    assert dlg.btn_tool_series.isEnabled()
    dlg.btn_tool_series.click()
    assert dlg._tools["series"].isVisible()
    dlg.set_series_hook(None)              # the visit went away
    assert not dlg._tools["series"].isVisible()
    assert not dlg.btn_tool_series.isEnabled()


def test_a_closed_door_is_not_opened_by_a_deep_link(dlg):
    # The series needs a visit (D8): its button is disabled and says why. A
    # deep link must respect that, or the observer gets an empty panel over
    # the plate with no explanation.
    assert dlg.open_tool("series") is None
    dlg.show_tab("series")
    assert not dlg._tools["series"].isVisible()
    dlg.set_series_hook(lambda scope="visit": {"pid": 1, "session_id": 2,
                                               "paths": []})
    assert dlg.open_tool("series") is not None
    assert dlg._tools["series"].isVisible()


def test_only_the_tools_that_need_the_plate_take_it(dlg):
    # Blink (it puts its own frame on the view) and Annotate (it marks and
    # takes the clicks) own the plate while their window is open. Calibration
    # is a recipe panel and the series is a run panel: taking the stage from
    # the Photometry panel would drop the sequence's rings exactly when a
    # series is being measured, which is when they are wanted.
    assert dlg.tab_photometry._on_stage
    dlg.open_tool("calibrate")
    assert dlg.tab_photometry._on_stage
    dlg.open_tool("series")
    assert dlg.tab_photometry._on_stage
    dlg.open_tool("blink")
    assert not dlg.tab_photometry._on_stage
    dlg._tools["blink"].close_panel()
    assert dlg.tab_photometry._on_stage
