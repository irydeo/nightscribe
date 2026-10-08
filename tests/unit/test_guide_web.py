############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: Help > User guide (web)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The application's other door to the guide (ADR-070).

The in-app browser (Help > Technical Documentation) is the offline door and
renders the markdown. This one hands the PUBLISHED page to the OS browser, in
the app's own language, and it exists so the guide can be read on a phone or
sent to somebody. The two read the same `docs/user`, which is the point of
the ADR: what is tested here is the seam, not the site (that is
test_site_build.py).

Offscreen, no network: the browser is replaced by a stub.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp):
    from nightscribe.config import config
    from nightscribe.gui.main_window import MainWindow
    orig = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    yield w
    config.is_configured = orig
    w.close()


def test_the_help_menu_carries_the_web_guide(window):
    # The entry lives in the Designer file like every other one (ADR-005),
    # next to the in-app documentation browser.
    action = window._menus.action_guide_web
    assert action is not None
    assert action.text()
    assert action.toolTip()


def test_the_web_guide_opens_in_the_app_language(window, monkeypatch):
    # A Spanish observer lands on the Spanish pages: the site is generated in
    # both languages from the same markdown they read in the app.
    from nightscribe.gui import main_window as mw
    opened = []

    class _Browser:
        @staticmethod
        def openUrl(url):
            opened.append(url.toString())

    monkeypatch.setattr("PySide6.QtGui.QDesktopServices", _Browser)
    monkeypatch.setattr(mw, "GUIDE_WEB_URL", "https://example.test/g/index")
    monkeypatch.setattr(window, "_lang", lambda: "es")
    window.on_guide_web()
    assert opened == ["https://example.test/g/index.es.html"]

    opened.clear()
    monkeypatch.setattr(window, "_lang", lambda: "en")
    window.on_guide_web()
    assert opened == ["https://example.test/g/index.html"]
