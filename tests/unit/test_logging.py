############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the application log
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The log has to leave a trace (reported: "a dialog appears and disappears
and I do not know what happens").

A GUI launched from a menu has no console, so the app writes a rotating file
in its own data folder and Help > Open the log shows it: a report can then be
answered with what really happened instead of with a guess.
"""

import logging
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                   # noqa: E402


@pytest.fixture()
def log_dir(tmp_path, monkeypatch):
    # the app's data folder, redirected: the real one is the observer's
    from nightscribe import paths
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    return tmp_path


def _drop_handlers():
    # _setup_logging attaches handlers to the ROOT logger and marks them: a
    # test that leaves them behind would write into a folder that is about
    # to be deleted.
    root = logging.getLogger()
    for handler in [h for h in root.handlers
                    if getattr(h, "_nightscribe", False)]:
        root.removeHandler(handler)
        handler.close()


def test_the_log_lands_in_a_file_the_observer_can_open(log_dir):
    from nightscribe.__main__ import _setup_logging
    from nightscribe import paths
    _setup_logging(False)
    try:
        logging.getLogger("nightscribe.test").warning("algo pasó")
        path = paths.log_path()
        assert path.exists() and path.parent == log_dir
        text = path.read_text(encoding="utf-8")
        assert "algo pasó" in text
        # with the time and the level: a log line that cannot be placed in
        # time is half a log line
        assert "WARNING" in text and "nightscribe.test" in text
        # and it does not double up on a second call
        _setup_logging(False)
        assert len([h for h in logging.getLogger().handlers
                    if getattr(h, "_nightscribe", False)]) == 2
    finally:
        _drop_handlers()


def test_a_log_that_cannot_be_written_never_stops_the_app(log_dir,
                                                          monkeypatch):
    # A read-only home is a real case (an old ~/.local owned by root): the
    # app keeps running with the console handler only.
    from logging.handlers import RotatingFileHandler
    from nightscribe.__main__ import _setup_logging

    def boom(*_a, **_k):
        raise OSError("read-only")
    monkeypatch.setattr(RotatingFileHandler, "__init__", boom)
    _setup_logging(False)                 # must not raise
    try:
        assert any(getattr(h, "_nightscribe", False)
                   for h in logging.getLogger().handlers)
    finally:
        _drop_handlers()


def test_the_help_menu_can_open_the_log(log_dir, monkeypatch):
    # Help > Open the log: it hands the file to the OS and says where it is
    # (so a file manager can be used instead).
    from PySide6.QtWidgets import QApplication
    from nightscribe.config import config
    from nightscribe.gui import theme
    from nightscribe.gui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    orig = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    try:
        from nightscribe import paths
        assert w._menus.action_log.text()          # the menu entry exists
        # no log yet: it says so instead of opening nothing
        w.on_open_log()
        assert "No log yet" in w.statusBar().currentMessage()
        # with a log: it is handed over and the path is said
        path = paths.log_path()
        path.write_text("hola\n", encoding="utf-8")
        opened = []
        monkeypatch.setattr(
            "PySide6.QtGui.QDesktopServices.openUrl",
            staticmethod(lambda url: opened.append(url.toLocalFile())))
        w.on_open_log()
        assert opened and Path(opened[0]) == path
        assert str(path) in w.statusBar().currentMessage()
    finally:
        config.is_configured = orig
        w.close()
