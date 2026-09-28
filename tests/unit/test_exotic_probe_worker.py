############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the EXOTIC probe runs off the GUI thread
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The EXOTIC interpreter probe must never run on the GUI thread
(stability review P1 #6): exotic_env.probe spawns a subprocess that
imports exotic's whole stack (minutes on a cold machine), which used to
freeze the app. ProbeExoticWorker moves detect_python + probe into a
QThread; «Test» in Settings disables its button while the probe runs,
and the project's «Reduce with EXOTIC» flow puts up a wait cursor and
continues when the report lands.

No real subprocesses anywhere: exotic_env.detect_python/probe are
monkeypatched to explode if the GUI thread ever calls them, and the
worker class is swapped for a canned fake at the entry points (the
test_followup_sequence.py pattern). Offscreen, temp db.
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
    tmp = dbmod.Database(tmp_path_factory.mktemp("probedb") / "t.db")
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


@pytest.fixture(autouse=True)
def _no_sync_probing(monkeypatch):
    # Any synchronous detect/probe call on the GUI thread fails the test.
    from nightscribe.core import exotic_env

    def _boom(*a, **k):
        raise AssertionError(
            "exotic_env must not run on the GUI thread (P1 #6)")

    monkeypatch.setattr(exotic_env, "detect_python", _boom)
    monkeypatch.setattr(exotic_env, "probe", _boom)


@pytest.fixture(autouse=True)
def _cursor_guard(qapp):
    # A failed assertion must not leak the wait cursor into other tests.
    from PySide6.QtWidgets import QApplication
    yield
    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()


class _Sig:
    # The connect/emit surface the entry points need from a worker signal.
    def __init__(self):
        self._cbs = []

    def connect(self, cb):
        self._cbs.append(cb)

    def emit(self, *a):
        for cb in list(self._cbs):
            cb(*a)


class FakeProbe:
    # A stand-in for ProbeExoticWorker: never runs, records the start.
    def __init__(self, preferred=None):
        self.preferred = preferred
        self.finished = _Sig()
        self.started = False

    def start(self):
        self.started = True

    def deleteLater(self, *a):    # _keep() wires it to finished; Qt would
        pass                      # drop the signal's extra args, so does this


def _fake_probe_factory(made):
    # @args: made - list the created fakes land in
    # @return: a ProbeExoticWorker replacement for monkeypatch
    def _factory(preferred=None):
        w = FakeProbe(preferred)
        made.append(w)
        return w
    return _factory


def test_probe_worker_detects_then_probes(qapp, monkeypatch):
    # The worker itself: detect_python + probe inside run(), one report
    # out (the probe's dict plus the interpreter it validated).
    from nightscribe.core import exotic_env
    from nightscribe.gui.workers import ProbeExoticWorker
    monkeypatch.setattr(exotic_env, "detect_python",
                        lambda preferred=None: "/py/python3.10")
    monkeypatch.setattr(exotic_env, "probe", lambda p: {
        "ok": True, "version": "4.0.0", "message": "EXOTIC 4.0.0"})
    got = []
    w = ProbeExoticWorker("/cfg/py")
    w.finished.connect(got.append)
    w.run()                        # synchronously; no thread needed
    assert got == [{"ok": True, "version": "4.0.0",
                    "message": "EXOTIC 4.0.0", "python": "/py/python3.10"}]


def test_settings_test_button_probes_off_thread(window, qapp, monkeypatch):
    # «Test» (Settings → EXOTIC): returns at once, starts the worker and
    # disables the button while it runs; the report re-arms the button.
    import nightscribe.gui.workers as workers_mod
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.gui.main_window import _load_ui
    made = []
    monkeypatch.setattr(workers_mod, "ProbeExoticWorker",
                        _fake_probe_factory(made))
    dlg = _load_ui("settings_dialog")
    dlg.edt_exotic_python.setText("/cfg/python3.10")
    try:
        window._test_exotic(dlg)
        # the entry point returned without probing: a worker is in flight
        assert made and made[0].started
        assert made[0].preferred == "/cfg/python3.10"
        assert not dlg.btn_exotic_test.isEnabled()
        shown = []
        monkeypatch.setattr(
            QMessageBox, "information",
            staticmethod(lambda parent, title, text: shown.append(text)))
        made[0].finished.emit({"ok": True, "version": "4.0.0",
                               "message": "EXOTIC 4.0.0",
                               "python": "/cfg/python3.10"})
        assert dlg.btn_exotic_test.isEnabled()
        assert shown == ["EXOTIC 4.0.0"]
        assert window._exotic_probe is None
    finally:
        dlg.deleteLater()


def test_exotic_reduce_probes_off_thread(window, qapp, monkeypatch):
    # «Reduce with EXOTIC»: the environment check moves to the worker
    # (wait cursor while it runs); the flow continues when the report
    # lands: here it stops at the missing-frames warning, which proves
    # the continuation ran with the probe's interpreter.
    import nightscribe.core.db as dbmod
    import nightscribe.gui.workers as workers_mod
    from PySide6.QtWidgets import QApplication, QMessageBox
    from nightscribe.core import project
    made = []
    monkeypatch.setattr(workers_mod, "ProbeExoticWorker",
                        _fake_probe_factory(made))
    warns = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda parent, title, text: warns.append(text)))
    p = project.create(dbmod.db, "transit", "WASP-12 b",
                       {"kind": "transit"})
    e = {"data": {"period": 1.099}}

    window._exotic_reduce(p["id"], e)
    assert made and made[0].started            # probe off the GUI thread
    assert QApplication.overrideCursor() is not None   # wait cursor up

    # no interpreter: the first warning path, cursor back down
    made[0].finished.emit({"ok": False, "version": None,
                           "message": "no Python <=3.10 found",
                           "python": ""})
    assert QApplication.overrideCursor() is None
    assert any("3.10" in w for w in warns)

    # interpreter found but exotic missing: the second warning path
    window._exotic_reduce(p["id"], e)
    made[-1].finished.emit({"ok": False, "version": None,
                            "message": "ModuleNotFoundError",
                            "python": "/py/python3.10"})
    assert any("pip install" in w for w in warns)

    # environment ok: the orchestration continues (the fresh project has
    # no FITS, so it stops at the frames warning: no crash, no block)
    window._exotic_reduce(p["id"], e)
    made[-1].finished.emit({"ok": True, "version": "4.0.0",
                            "message": "EXOTIC 4.0.0",
                            "python": "/py/python3.10"})
    assert any("FITS" in w for w in warns)
    assert getattr(window, "_exotic_worker", None) is None


_FAKE_WCS = {"CRVAL1": 120.0, "CRVAL2": -20.0, "CRPIX1": 64.0,
             "CRPIX2": 64.0, "CTYPE1": "RA---TAN", "CTYPE2": "DEC--TAN",
             "CD1_1": -0.0003, "CD1_2": 0.0, "CD2_1": 0.0, "CD2_2": 0.0003}


def _fake_solve_factory(made, cards, qapp):
    from PySide6.QtCore import QObject, Signal

    class _FakeSolve(QObject):
        finished = Signal(dict)
        progress = Signal(str)

        def __init__(self, path):
            super().__init__()
            self._path = path
            self._cancelled = False

        def start(self):
            made.append(self)
            self.finished.emit(cards)

        def cancel(self):
            self._cancelled = True

        def cancelled(self):
            return self._cancelled

    return _FakeSolve


def test_exotic_solves_the_first_frame_not_asks_pixels(window, qapp,
                                                       monkeypatch, tmp_path):
    # ADR-051 rev: the first frame without a WCS is solved with the
    # configured solver and the reduction continues; the pixel prompt is
    # gone for good.
    from nightscribe.gui import workers
    from nightscribe.core import fits_io
    from test_fits_annotate import _make_fits
    assert not hasattr(window, "_ask_exotic_pixels")
    plate = _make_fits(tmp_path / "first.fits")     # no WCS
    header, _ = fits_io.read_fits(plate)
    made, reached = [], []
    monkeypatch.setattr(workers, "UfeSolveWorker",
                        _fake_solve_factory(made, _FAKE_WCS, qapp))
    monkeypatch.setattr(window, "_persist_solution", lambda *a, **k: True)
    monkeypatch.setattr(window, "_exotic_launch_final",
                        lambda *a, **k: reached.append(a))
    window._exotic_solve_first(1, {"data": {}}, "/py", [str(plate)], 7,
                               header)
    assert made and str(made[0]._path) == str(plate)
    assert reached and reached[0][5] is not None      # a usable WCS


def test_exotic_solve_failure_says_so(window, qapp, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    from nightscribe.gui import workers
    from test_fits_annotate import _make_fits
    warns = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *a, **k: warns.append(a))
    plate = _make_fits(tmp_path / "first.fits")
    made, reached = [], []
    monkeypatch.setattr(workers, "UfeSolveWorker",
                        _fake_solve_factory(made, {}, qapp))
    monkeypatch.setattr(window, "_exotic_launch_final",
                        lambda *a, **k: reached.append(a))
    window._exotic_solve_first(1, {"data": {}}, "/py", [str(plate)], 7, {})
    assert warns and not reached


def test_ufe_exotic_reduce_uses_the_open_frame_and_sequence(window, qapp,
                                                            monkeypatch):
    # The editor's reduce hook (ADR-048 follow-up): the open frame and
    # the loaded sequence travel to the launch, not a re-derived first
    # frame and the project's possibly empty context.
    seen = {}
    monkeypatch.setattr(window, "_transit_reduce_exotic",
                        lambda pid=None: seen.update(pid=pid))

    class _State:
        has_image = True
        path = "/data/frame_042.fits"

    class _Compare:
        @staticmethod
        def entries():
            return [{"name": "A", "kind": "comp", "star": {"ra": 1.0}}]

    class _Dlg:
        state = _State()
        tab_compare = _Compare()

    window._ufe = _Dlg()
    try:
        window._ufe_exotic_reduce(7, 9)
    finally:
        window._ufe = None
    assert seen["pid"] == 7
    over = window._exotic_overrides
    assert over["ref"] == "/data/frame_042.fits"
    assert over["session_id"] == 9
    assert over["entries"][0]["name"] == "A"


def test_exotic_solve_first_forwards_the_sequence(window, qapp, monkeypatch,
                                                  tmp_path):
    # Regression: when the reference frame had no WCS, the solve path used
    # to continue WITHOUT the sequence the UFE had loaded, so the reduce
    # failed with "no comparison stars" though it was built.
    from nightscribe.gui import workers
    from nightscribe.core import fits_io
    from test_fits_annotate import _make_fits
    plate = _make_fits(tmp_path / "first.fits")
    header, _ = fits_io.read_fits(plate)
    made, got = [], []
    monkeypatch.setattr(workers, "UfeSolveWorker",
                        _fake_solve_factory(made, _FAKE_WCS, qapp))
    monkeypatch.setattr(window, "_persist_solution", lambda *a, **k: True)
    monkeypatch.setattr(window, "_exotic_launch_final",
                        lambda *a, **k: got.append(a))
    entries = [{"name": "A", "kind": "comp", "star": {"ra": 1.0}}]
    window._exotic_solve_first(1, {"data": {}}, "/py", [str(plate)], 7,
                               header, str(plate), entries)
    assert got and got[0][-1] == entries
