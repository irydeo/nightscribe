############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the EXOTIC prepare worker outlives the
#               Settings dialog safely
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The PrepareExoticWorker's report must never land on a destroyed
Settings dialog (stability review P1 #7): the environment build takes
minutes, the modal dialog is long gone when the worker finishes, and
writing into its widgets (or parenting a message box to it) crashed the
app. The handler now guards every widget touch (Shiboken.isValid, this
codebase's QPointer, PySide6 ships none) and reports on the status bar
instead.

The fake worker never builds anything: it just captures the handlers so
the test can reject and destroy the dialog first and deliver «finished»
after. No subprocesses: detect_python is canned. Offscreen, temp db.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # main_window imports the shared `db` singleton; redirect it to a
    # throwaway file so nothing touches the real database.
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("prepdb") / "t.db")
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
    orig_cfg = config.is_configured
    config.is_configured = lambda: False   # no auto-compute network worker
    w = MainWindow()
    w._now_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


class _Sig:
    # The connect/emit surface the entry point needs from a worker signal.
    def __init__(self):
        self._cbs = []

    def connect(self, cb):
        self._cbs.append(cb)

    def emit(self, *a):
        for cb in list(self._cbs):
            cb(*a)


class FakePrepare:
    # A stand-in for PrepareExoticWorker: never builds, records the start.
    def __init__(self, install, python):
        self.install = install
        self.python = python
        self.progress = _Sig()
        self.finished = _Sig()
        self.started = False

    def start(self):
        self.started = True


@pytest.fixture
def prepared(window, qapp, monkeypatch, tmp_path):
    # A settings dialog with a prepare worker in flight (no subprocess:
    # detect_python is canned and the worker class is faked).
    # @return: (dlg, fake worker)
    import nightscribe.gui.workers as workers_mod
    from nightscribe.core import exotic_env
    from nightscribe.gui.main_window import _load_ui
    monkeypatch.setattr(exotic_env, "detect_python",
                        lambda preferred=None: "/usr/bin/python3.10")
    made = []

    def _factory(install, python):
        w = FakePrepare(install, python)
        made.append(w)
        return w

    monkeypatch.setattr(workers_mod, "PrepareExoticWorker", _factory)
    dlg = _load_ui("settings_dialog")
    dlg.edt_exotic_python.setText("/usr/bin/python3.10")
    dlg.edt_exotic_install.setText(str(tmp_path / "exotic-venv"))
    window._prepare_exotic(dlg)
    assert made and made[0].started
    return dlg, made[0]


def _destroy(qapp, dlg):
    # What the app teardown does to a closed dialog: delete the C++ side
    # while the worker's handler still holds the (now dead) wrapper.
    from PySide6.QtCore import QEvent
    dlg.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _guard_boxes(monkeypatch, shown):
    # Message boxes must never be parented to a destroyed dialog; the
    # recorder asserts it instead of opening a modal (which would hang).
    from PySide6 import Shiboken
    from PySide6.QtWidgets import QMessageBox

    def _recorder(kind):
        def _box(parent, title, text):
            assert Shiboken.isValid(parent), \
                f"QMessageBox.{kind} parented to a destroyed dialog"
            shown.append(text)
        return _box

    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(_recorder("information")))
    monkeypatch.setattr(QMessageBox, "warning",
                        staticmethod(_recorder("warning")))


def test_finished_after_dialog_destroyed_does_not_crash(window, qapp,
                                                        prepared,
                                                        monkeypatch):
    from PySide6 import Shiboken
    dlg, worker = prepared
    shown = []
    _guard_boxes(monkeypatch, shown)
    dlg.reject()                    # the user gave up on the dialog
    _destroy(qapp, dlg)
    assert not Shiboken.isValid(dlg)
    # The build finishes long after: the old handler wrote into the
    # destroyed dialog's widgets here (RuntimeError); now it reports on
    # the status bar and leaves the corpse alone.
    worker.finished.emit(True, "ok")
    assert window._exotic_worker is None
    assert shown == []              # no box parented to the dead dialog
    assert "EXOTIC" in window.statusBar().currentMessage()


def test_failed_after_dialog_destroyed_reports_on_status_bar(window, qapp,
                                                             prepared,
                                                             monkeypatch):
    from PySide6 import Shiboken
    dlg, worker = prepared
    shown = []
    _guard_boxes(monkeypatch, shown)
    dlg.reject()
    _destroy(qapp, dlg)
    assert not Shiboken.isValid(dlg)
    worker.finished.emit(
        False, "$ pip install exotic\nNo matching distribution found")
    assert window._exotic_worker is None
    assert shown == []
    msg = window.statusBar().currentMessage()
    assert "EXOTIC" in msg and "No matching distribution" in msg


def test_finished_with_live_dialog_updates_its_fields(window, qapp,
                                                      prepared,
                                                      monkeypatch):
    # The unchanged happy path: a dialog still alive gets the new venv
    # path and the ready box.
    dlg, worker = prepared
    shown = []
    _guard_boxes(monkeypatch, shown)
    worker.finished.emit(True, "ok")
    assert dlg.edt_exotic_install.text().endswith("exotic-venv")
    assert "exotic-venv" in dlg.edt_exotic_python.text()
    assert shown and "ready" in shown[0].lower()
    assert window._exotic_worker is None
    dlg.deleteLater()
