############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the Explore object entry dialog and its doors
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Explore object entry dialog (2026-10-08) and the two doors that use
it: the Tools-menu dialog and the always-visible top-bar search.

The lookup itself (_open_explore_dialog) is not touched by this work, so
these tests fake it and check only the NEW surfaces: the dialog returns a
trimmed name and refuses an empty one, the top-bar field hands its text
over and clears itself, and the Tools dialog delegates when accepted.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---------------- harness ----------------

@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # main_window imports the shared `db` singleton; redirect it so building
    # the window never touches the real database.
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("explore-dlg") / "t.db")
    dbmod.db = tmp
    mw.db = tmp
    yield
    dbmod.db = old_dbmod
    mw.db = old_mw


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture(scope="module")
def window(_point_db_at_tmpdir, qapp):
    from nightscribe.config import config
    from nightscribe.gui.main_window import MainWindow
    # keep it hermetic: no auto-compute network worker on startup
    orig_cfg = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


# ---------------- the entry dialog ----------------

def test_explore_dialog_returns_the_trimmed_name(qapp):
    from nightscribe.gui.explore_dialog import ExploreDialog
    d = ExploreDialog()
    try:
        assert d.name() == ""
        d.edt_name.setText("  2026 QK  ")
        assert d.name() == "2026 QK"
    finally:
        d.deleteLater()


def test_explore_dialog_refuses_an_empty_name(qapp):
    from nightscribe.gui.explore_dialog import ExploreDialog
    d = ExploreDialog()
    try:
        d._accept()
        assert d.result() == 0            # still open: nothing to look up
        d.edt_name.setText("C/2025 K1")
        d._accept()
        assert d.result() == 1            # accepted
    finally:
        d.deleteLater()


def test_explore_dialog_enter_is_the_same_as_the_button(qapp):
    from nightscribe.gui.explore_dialog import ExploreDialog
    d = ExploreDialog()
    try:
        d.edt_name.setText("V CrB")
        d.edt_name.returnPressed.emit()
        assert d.result() == 1
    finally:
        d.deleteLater()


# ---------------- the top-bar search ----------------

def test_nav_field_exists_and_carries_a_help(window):
    edt = window._menus.edt_nav_explore
    assert edt is not None
    assert edt.placeholderText()
    assert edt.toolTip()


def test_nav_explore_opens_the_card_and_clears_the_field(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window, "_open_explore_dialog",
                        lambda name: seen.append(name))
    edt = window._menus.edt_nav_explore
    edt.setText("2026 QK")
    edt.returnPressed.emit()
    assert seen == ["2026 QK"]
    assert edt.text() == ""


def test_nav_explore_ignores_an_empty_field(window, monkeypatch):
    seen = []
    monkeypatch.setattr(window, "_open_explore_dialog",
                        lambda name: seen.append(name))
    edt = window._menus.edt_nav_explore
    edt.setText("   ")
    edt.returnPressed.emit()
    assert seen == []


# ---------------- the Tools-menu dialog ----------------

def test_tools_explore_hands_the_name_over(window, monkeypatch):
    import nightscribe.gui.explore_dialog as edmod
    from PySide6.QtWidgets import QDialog
    seen = []

    class _Accepted:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.Accepted

        def name(self):
            return "C/2025 K1"

    monkeypatch.setattr(edmod, "ExploreDialog", _Accepted)
    monkeypatch.setattr(window, "_open_explore_dialog",
                        lambda name: seen.append(name))
    window._tools_explore()
    assert seen == ["C/2025 K1"]


def test_tools_explore_cancelled_does_nothing(window, monkeypatch):
    import nightscribe.gui.explore_dialog as edmod
    from PySide6.QtWidgets import QDialog
    seen = []

    class _Rejected:
        def __init__(self, parent=None):
            pass

        def exec(self):
            return QDialog.Rejected

        def name(self):
            return "C/2025 K1"

    monkeypatch.setattr(edmod, "ExploreDialog", _Rejected)
    monkeypatch.setattr(window, "_open_explore_dialog",
                        lambda name: seen.append(name))
    window._tools_explore()
    assert seen == []
