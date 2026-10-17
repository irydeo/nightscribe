############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the observatory console's own line
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The console says WHERE it will look, and that NINA/PINS is in test.

ADR-081 rev (2026-10-17): CCDciel is the complete observatory backend and the
NINA/PINS one still has gaps, so the observer has to read that BEFORE choosing,
not after the first failure. The console is where it is connected from, so its
line carries the status. Offscreen, no network.
"""

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


@pytest.fixture
def console(qapp):
    from nightscribe.gui.widgets.observatory_console import ObservatoryConsole
    w = ObservatoryConsole()
    yield w
    w.deleteLater()


def test_it_says_where_it_will_look(console):
    console.set_backend_hint("CCDciel", "localhost", 3277, True)
    line = console._ui.lbl_where.text()
    assert "localhost:3277" in line
    assert "Settings" in line            # the door to change it
    assert "test" not in line.lower()    # CCDciel is the complete one


def test_nina_says_it_is_in_test(console):
    # The status has to be read before the first click
    console.set_backend_hint("NINA / PINS", "localhost", 1888, True)
    line = console._ui.lbl_where.text()
    assert "localhost:1888" in line
    assert "test" in line.lower() and "0.2" in line


def test_without_a_backend_it_says_so(console):
    console.set_backend_hint("", "", 0, False)
    line = console._ui.lbl_where.text()
    assert "no backend configured" in line
