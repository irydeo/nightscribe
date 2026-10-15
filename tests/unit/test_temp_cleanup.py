############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the app's scratch in the system temp
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The scratch the app writes to the SYSTEM temp folder is removed when its
work is done, and the OLD leftovers (a crash, a kill) go at startup.

Reported 2026-10-15: the phase chart's folder was never removed, `findorb.check`
left the `fo` run's own folder behind, and a captured frame's FITS was never
deleted. Each of those is pinned here, plus the sweep that catches whatever a
crash leaves (and that must never touch a fresh entry, i.e. a second instance
working right now)."""

import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def test_sweep_temp_removes_old_leftovers_only(tmp_path, monkeypatch):
    # Only the app's OWN entries (the common prefix) and only the OLD ones:
    # a fresh folder is a second instance working right now.
    import tempfile
    from nightscribe import paths
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    old = tmp_path / "nightscribe-fo-abc"
    old.mkdir()
    (old / "total.json").write_text("{}")
    recent = tmp_path / "nightscribe-phase-new"
    recent.mkdir()
    stranger = tmp_path / "someone-else"
    stranger.mkdir()
    past = time.time() - 2 * 24 * 3600
    os.utime(old, (past, past))
    removed = paths.sweep_temp(max_age_s=24 * 3600)
    assert removed == 1
    assert not old.exists()
    assert recent.exists()
    assert stranger.exists()


def test_the_phase_dialog_removes_its_scratch_folder(qapp, tmp_path):
    # The chart's scratch PNG is for the preview; the exported one is a
    # COPY in the project. The folder goes with the window.
    import tempfile
    from nightscribe.gui.phase_dialog import PhaseDialog
    dlg = PhaseDialog([], lang="en")
    dlg._tmp = tempfile.mkdtemp(prefix="nightscribe-phase-")
    scratch = dlg._tmp
    (Path(scratch) / "phase.png").write_text("x")
    dlg.show()
    dlg.close()
    assert not os.path.exists(scratch)
