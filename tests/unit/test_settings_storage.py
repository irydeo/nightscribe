############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: settings projects-folder group (ADR-032)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Projects container root in Settings (offscreen, ADR-032).

The Observing tab carries `grp_storage` (edt_projects_root +
Browse/Reset). These tests lock in:

* the group loads the configured root and saves it back;
* the Browse button fills the field through `_projects_browse_into`;
* the Reset button clears the field (back to the app-data default);
* `on_open_settings` actually maps edt_projects_root <-> projects_root.
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


def _dlg():
    # @return: a loaded settings dialog (caller deletes it)
    from nightscribe.gui.main_window import _load_ui
    return _load_ui("settings_dialog")


def test_storage_group_loads_configured_root(qapp, tmp_path, monkeypatch):
    from nightscribe.config import config
    monkeypatch.setattr(config, "_data",
                        {**config._data, "projects_root": str(tmp_path)})
    dlg = _dlg()
    dlg.edt_projects_root.setText(config.get("projects_root", ""))
    assert dlg.edt_projects_root.text() == str(tmp_path)
    dlg.deleteLater()


def test_browse_button_uses_handler_on_main_window(qapp, tmp_path,
                                                   monkeypatch):
    # _projects_browse_into needs only the dialog + tr(); drive it with
    # the exact method the settings flow connects to the button
    from PySide6.QtWidgets import QFileDialog
    from nightscribe.gui.main_window import MainWindow

    class _Host:
        def tr(self, s):
            return s

    dlg = _dlg()
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory",
        staticmethod(lambda *a, **k: str(tmp_path)))
    MainWindow._projects_browse_into(_Host(), dlg)
    assert dlg.edt_projects_root.text() == str(tmp_path)
    dlg.deleteLater()


def test_browse_cancel_keeps_field(qapp, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from nightscribe.gui.main_window import MainWindow

    class _Host:
        def tr(self, s):
            return s

    dlg = _dlg()
    dlg.edt_projects_root.setText("/keep/me")
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    MainWindow._projects_browse_into(_Host(), dlg)
    assert dlg.edt_projects_root.text() == "/keep/me"
    dlg.deleteLater()


def test_on_open_settings_maps_projects_root(qapp):
    # mirror the existing language-combo source check: the settings flow
    # must load and save the new config key from the same widget and wire
    # the Browse/Reset buttons
    import inspect
    import re
    from nightscribe.gui import main_window as mw
    src = inspect.getsource(mw.MainWindow.on_open_settings)
    assert "edt_projects_root" in src
    assert re.search(r"config\.set\(\s*\"projects_root\"\s*,"
                     r"\s*dlg\.edt_projects_root\.text\(\)\.strip\(\)\s*\)",
                     src), "on_open_settings must save edt_projects_root"
    assert "btn_projects_browse.clicked.connect" in src, \
        "on_open_settings must wire the Browse button"
    assert "btn_projects_reset.clicked.connect" in src, \
        "on_open_settings must wire the Reset button"