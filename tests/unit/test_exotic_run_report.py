############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the EXOTIC run report and its progress dialog
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""An EXOTIC run takes up to two hours, and it used to end in one of two
dead ends (usability review P2 #21): a failure reported the log's PATH
instead of what EXOTIC actually said, and the run had no progress dialog
and no way out but quitting the app.

The failure box now carries the tail of the run log (its last lines are
where the error is), and the run gets a non-modal QProgressDialog whose
Cancel asks the worker to stop: ExoticRunWorker already cancels and
takes EXOTIC's process tree down, only the wiring was missing. A run the
user cancelled reports plainly on the status bar, not as an error.

No subprocesses: the worker is the real class with a spy on cancel(),
never started. Offscreen, no network, temp db (the
test_settings_exotic_prepare.py harness pattern).
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # main_window imports the shared `db` singleton; redirect it to a
    # throwaway file so nothing touches the real database.
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("exorep") / "t.db")
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


def _write_log(path, n_info=30, error=True):
    # @args: path - the log file, n_info - filler lines before the error,
    #        error - append a traceback-shaped failure at the end
    # @return: the log path, as exotic_run.run leaves it (line by line)
    lines = [f"INFO {i}: reducing the frame\n" for i in range(n_info)]
    if error:
        lines += ["Traceback (most recent call last):\n",
                  "ValueError: the target is not in the field of view\n"]
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _boxes(monkeypatch):
    # The failure box is recorded instead of opened (a modal box would
    # hang the suite); @return: the list it records its text into
    from PySide6.QtWidgets import QMessageBox
    shown = []

    def _warning(parent, title, text):
        shown.append(text)

    monkeypatch.setattr(QMessageBox, "warning", staticmethod(_warning))
    return shown


def _spy_cancel(worker):
    # @return: a list the worker's cancel() appends to; the real cancel
    #          still runs, so the worker really is asked to stop
    calls = []
    real = worker.cancel
    worker.cancel = lambda: (calls.append(True), real())[1]
    return calls


# ---------------- the failure report (P2 #21) ----------------

def test_failed_run_reports_the_log_tail_not_the_path(window, qapp,
                                                      monkeypatch, tmp_path):
    # The reported symptom: the box showed the log's path, which is
    # useless after a two-hour run. It must show what EXOTIC said: the
    # last lines of the log, and not the whole log either.
    from nightscribe.gui import main_window as mw
    log = _write_log(tmp_path / "exotic_run.log")
    shown = _boxes(monkeypatch)
    window._exotic_done({"ok": False, "returncode": 1,
                         "log_path": str(log), "out_dir": str(tmp_path),
                         "cancelled": False})
    assert len(shown) == 1
    text = shown[0]
    assert "did not finish" in text
    assert "ValueError: the target is not in the field of view" in text
    assert "Traceback (most recent call last):" in text
    assert "INFO 0:" not in text          # the tail, not the whole log
    assert str(log) not in text           # ... and no path in the report
    assert window._exotic_worker is None
    assert mw._exotic_log_tail(str(log), lines=1).endswith(
        "the target is not in the field of view")


def test_log_tail_reads_the_end_of_a_big_log(tmp_path):
    # A two-hour log is bigger than the chunk the tail reads: the seek
    # path must still land on the last lines (and drop the half-cut one).
    from nightscribe.gui.main_window import _exotic_log_tail
    log = tmp_path / "big.log"
    with log.open("w", encoding="utf-8") as fh:
        for i in range(20000):
            fh.write(f"INFO {i}: a long line to fill the log up\n")
        fh.write("RuntimeError: EXOTIC gave up\n")
    tail = _exotic_log_tail(str(log), lines=3)
    assert tail.endswith("RuntimeError: EXOTIC gave up")
    assert "INFO 19999" in tail
    assert "INFO 0:" not in tail
    assert _exotic_log_tail(None) == ""             # no log at all
    assert _exotic_log_tail(str(tmp_path / "nope.log")) == ""


def test_failed_run_without_a_log_says_so(window, qapp, monkeypatch):
    # The worker could not even start EXOTIC (no log written): the box
    # says the log is empty instead of showing a blank.
    shown = _boxes(monkeypatch)
    window._exotic_done({"ok": False, "returncode": None,
                         "log_path": None, "out_dir": None,
                         "cancelled": False})
    assert len(shown) == 1
    assert "(the log is empty)" in shown[0]


# ---------------- the progress dialog and its Cancel (P2 #21) ----------------

def test_progress_dialog_cancel_calls_the_worker_cancel(window, qapp,
                                                        tmp_path):
    # A run of up to hours needs a way out: the dialog's Cancel asks the
    # worker to stop (it kills EXOTIC's process tree and reports
    # "cancelled"). The dialog is non-modal: the window stays usable.
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton
    from nightscribe.gui.workers import ExoticRunWorker
    worker = ExoticRunWorker("/usr/bin/python3", str(tmp_path),
                             str(tmp_path / "inits.json"))
    calls = _spy_cancel(worker)
    window._exotic_worker = worker
    wait = window._exotic_progress_dialog()
    try:
        assert window._exotic_wait is wait
        assert wait.windowModality() == Qt.NonModal
        assert wait.maximum() == 0               # indeterminate
        btn = wait.findChild(QPushButton)        # ... and cancellable
        assert btn is not None and btn.text() == window.tr("Cancel")
        assert not calls
        btn.click()                              # one click, mid-run
        assert calls                             # the worker was asked
        assert "Cancelling" in window.statusBar().currentMessage()
        assert "Cancelling" in wait.labelText()
    finally:
        window._exotic_reap_wait()
        window._exotic_worker = None
    assert window._exotic_wait is None


def test_progress_line_updates_the_dialog_and_the_status_bar(window, qapp):
    # EXOTIC streams its log: the dialog's label and the status bar say
    # where the run is, so a silent hour does not read as a hung app.
    window._exotic_progress_dialog()
    try:
        window._exotic_progress_line("Loading the comparison stars")
        assert window._exotic_wait.labelText() == \
            "Loading the comparison stars"
        assert window.statusBar().currentMessage() == \
            "Loading the comparison stars"
    finally:
        window._exotic_reap_wait()
    assert window._exotic_wait is None


def test_the_spinner_is_not_shown_as_progress(window, qapp):
    # "Thinking | ..." repeats for minutes while EXOTIC waits on something
    # slow, and that is exactly what read as a hang (2026-09-30, the
    # astrometry.net wait). It must not overwrite the last real stage.
    window._exotic_progress_dialog()
    try:
        window._exotic_progress_line("Finding transformation 3 of 142 : a.fits")
        stage = window._exotic_wait.labelText()
        for spin in ("Thinking | ...", "Thinking / ...", "Thinking ... DONE!"):
            window._exotic_progress_line(spin)
            assert window._exotic_wait.labelText() == stage
    finally:
        window._exotic_reap_wait()


def test_frame_progress_becomes_a_plain_counter(window, qapp):
    # EXOTIC's own per-frame line is the only real progress it prints
    window._exotic_progress_dialog()
    try:
        window._exotic_progress_line(
            "Finding transformation 7 of 142 : /data/HATP-32171220013912.FITS")
        assert window._exotic_wait.labelText() == \
            window.tr("Reducing frame {0} of {1}…").format(7, 142)
    finally:
        window._exotic_reap_wait()


def test_the_mid_transit_warning_becomes_a_neutral_stage(window, qapp):
    # EXOTIC repeats this once per aperture / comparison-star combination that
    # does not straddle the transit: 1143 times in a 142-frame run (measured
    # 2026-09-30) and the observer read it as a failure. It is its own
    # diagnostic about that combination, so the label says what is happening.
    window._exotic_progress_dialog()
    try:
        window._exotic_progress_line(
            "\x1b[33m  Estimated mid-transit time is not within the "
            "observations\x1b[0m")
        assert window._exotic_wait.labelText() == \
            window.tr("Comparing apertures and comparison stars…")
    finally:
        window._exotic_reap_wait()


def test_the_label_drops_exotic_colour_escapes(window, qapp):
    # the warnings arrive coloured; the raw escapes used to show up in the
    # label ("[33m  Comparison star #2 star beyond edge of file")
    window._exotic_progress_dialog()
    try:
        window._exotic_progress_line(
            "\x1b[33m Comparison star #2 star beyond edge of file\x1b[0m")
        assert window._exotic_wait.labelText() == \
            "Comparison star #2 star beyond edge of file"
    finally:
        window._exotic_reap_wait()


def test_timed_out_run_says_it_ran_past_the_limit(window, qapp, monkeypatch,
                                                  tmp_path):
    # Killed by the time cap, not crashed: the box must not send the
    # observer hunting a traceback that is not there.
    log = _write_log(tmp_path / "exotic_run.log", n_info=3, error=False)
    shown = _boxes(monkeypatch)
    window._exotic_done({"ok": False, "returncode": -15,
                         "log_path": str(log), "out_dir": str(tmp_path),
                         "cancelled": False, "timed_out": True})
    assert len(shown) == 1
    assert "time limit" in shown[0]
    assert "did not finish" not in shown[0]
    assert window._exotic_worker is None


def test_the_reduction_lands_as_visit_resources_and_a_result_window(
        window, qapp, tmp_path):
    # The reported gap (2026-10-01): the run finished, the box said T_mid
    # once, and then nobody could find the figure, the report or the
    # numbers. Now the products are resources of the visit (they open from
    # its window) and the result window opens with the numbers and the
    # curve.
    from nightscribe.core import followup as fu
    from nightscribe.core import project as proj
    db = window_db(window)
    p = proj.create(db, "transit", "HAT-P-32 b")
    sid = fu.create_session(db, p["id"], obs_date="2017-12-20")
    work = Path(proj.storage_dir(p)) / "exotic"
    (work / "temp").mkdir(parents=True, exist_ok=True)
    (work / "FinalLightCurve_HAT-P-32 b_20-December-2017.png").write_bytes(b"p")
    (work / "FinalLightCurve_HAT-P-32 b_20-December-2017.pdf").write_bytes(b"p")
    (work / "AAVSO_HAT-P-32 b_20-December-2017.txt").write_text("a")
    (work / "temp" / "FinalParams_HAT-P-32 b_20-December-2017.json").write_text(
        "{}")
    fu.create_run(db, session_id=sid,
                  cfg={"source": "exotic",
                       "params": {"tmid": 2458107.7146, "tmid_err": 0.0011,
                                  "rprs": 0.1612, "rprs_err": 0.0037}})
    # the numbers come back to the editor's block
    text = window._exotic_result_text(p["id"], sid)
    assert "2458107.71460" in text and "0.1612" in text
    assert window._exotic_last_run(p["id"], sid)["params"]["tmid"] == \
        2458107.7146
    # the products become the visit's resources, once each (png and pdf of
    # the same figure, and the log, stay out)
    assert window._register_exotic_products(p["id"], sid, str(work)) == 3
    assert window._register_exotic_products(p["id"], sid, str(work)) == 0
    kinds = {f["kind"] for f in proj.files_for_session(db, sid)}
    assert kinds == {"exotic_figure", "exotic_aavso", "exotic_params"}
    # ... and the result window opens with them listed
    dlg = window._open_exotic_result(p["id"], sid)
    try:
        assert dlg is not None and not dlg.isModal()
        names = [dlg._ui.lst_files.item(i).text()
                 for i in range(dlg._ui.lst_files.count())]
        assert any("AAVSO" in n for n in names)
        assert any("FinalLightCurve" in n for n in names)
    finally:
        dlg.close()


def test_the_block_and_the_window_without_a_reduction(window, qapp):
    # a visit with no reduction: an empty line, dead buttons and no window
    from nightscribe.core import project as proj
    db = window_db(window)
    p = proj.create(db, "transit", "HAT-P-32 b")
    assert window._exotic_result_text(p["id"]) == ""
    assert window._exotic_last_run(p["id"]) is None
    assert window._open_exotic_result(p["id"]) is None


def window_db(window):
    # @return: the database the window fixture is bound to
    from nightscribe.gui import main_window as mw
    return mw.db


def test_cancelled_run_reports_plainly_and_reaps_the_dialog(window, qapp,
                                                            monkeypatch,
                                                            tmp_path):
    # The user stopped it: no error box (nothing went wrong), the dialog
    # is reaped before the report, and the status bar says what happened.
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QProgressDialog
    shown = _boxes(monkeypatch)
    window._exotic_worker = object()
    window._exotic_progress_dialog()
    assert window.findChildren(QProgressDialog)
    window._exotic_done({"ok": False, "returncode": None,
                         "log_path": str(tmp_path / "exotic_run.log"),
                         "out_dir": str(tmp_path), "cancelled": True})
    assert shown == []
    assert window._exotic_wait is None
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert not window.findChildren(QProgressDialog)   # closed and reaped
    assert window._exotic_worker is None
    msg = window.statusBar().currentMessage()
    assert "cancelled" in msg.lower() and "EXOTIC" in msg
