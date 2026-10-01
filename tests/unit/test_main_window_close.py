############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: MainWindow closeEvent worker shutdown
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Quitting with live workers must not end in «QThread destroyed while
running» (stability review P1 #5): MainWindow.closeEvent cancels and
bound-waits every worker the window tracks (the _keep list plus the
_exotic_worker attribute), and closes the non-modal UFE dialog so its
own closeEvent shuts the Measure tab's series/live workers down.

The live threads here are REAL QThreads (a loop-until-cancelled stand-in
with the same cancel() surface as SeriesWorker/LiveSeriesWorker/
ExoticRunWorker, and a real LiveSeriesWorker parked inside a real
UfeDialog's Measure tab), so the assertions are about actual thread
termination, not fakes. Offscreen, no network, temp db (the
test_projects_hub.py harness pattern).
"""

import os

import pytest

from PySide6.QtCore import QThread

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # main_window imports the shared `db` singleton; redirect it to a
    # throwaway file so nothing touches the real database.
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("closedb") / "t.db")
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
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


class LoopWorker(QThread):
    # Stand-in for the app's long workers (SeriesWorker / LiveSeriesWorker
    # / ExoticRunWorker share this surface): loops until cancelled, so it
    # is still running when the window closes.
    def __init__(self):
        super().__init__()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        while not self._cancel:
            self.msleep(20)


def test_close_event_cancels_and_waits_a_kept_worker(window, qapp):
    # A worker registered through _keep (the generic tracking list) is
    # cancelled and waited inside closeEvent: after close() returns the
    # thread has finished, so nothing is destroyed while running.
    w = LoopWorker()
    window._keep(w)
    w.start()
    assert w.isRunning()              # a worker that never ends by itself
    try:
        window.show()
        window.close()
        assert not w.isRunning()      # cancelled and waited by closeEvent
    finally:
        w.cancel()
        w.wait(3000)


def test_close_event_cancels_the_exotic_worker(window, qapp):
    # PrepareExoticWorker / ExoticRunWorker live on _exotic_worker, not
    # in _workers: closeEvent must sweep that attribute too.
    w = LoopWorker()
    window._exotic_worker = w
    w.start()
    try:
        window.show()
        window.close()
        assert not w.isRunning()
    finally:
        w.cancel()
        w.wait(3000)
        window._exotic_worker = None


def test_close_event_closes_the_non_modal_ufe(window, qapp):
    # The UFE dialog is non-modal and kept on self._ufe; its own
    # closeEvent shuts the Measure tab's workers down, so MainWindow
    # must close it when the app quits.
    closed = []

    class _FakeUfe:
        def close(self):
            closed.append(True)

    window._ufe = _FakeUfe()
    try:
        window.show()
        window.close()
    finally:
        window._ufe = None
    assert closed == [True]


def test_close_event_shuts_down_a_live_series_worker(window, qapp, tmp_path):
    # The issue's exact scenario: quitting while the Measure tab's Live
    # watch runs. The worker lives inside the UfeDialog; closing the
    # dialog from MainWindow.closeEvent runs the tab's shutdown
    # (cancel + wait), so the thread has finished when close returns.
    from nightscribe.gui.ufe_dialog import UfeDialog
    from nightscribe.gui.workers import LiveSeriesWorker
    ufe = UfeDialog(lang="en", parent=window)
    live = LiveSeriesWorker(str(tmp_path), None, poll_s=0.05)
    ufe.tab_measure._live_worker = live
    live.start()
    window._ufe = ufe
    ufe.show()
    try:
        window.show()
        window.close()
        assert not live.isRunning()
    finally:
        live.cancel()
        live.wait(3000)
        window._ufe = None
        ufe.view._render_timer.stop()
        ufe.deleteLater()
