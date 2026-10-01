############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit-suite guard: no network, ever
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Unit tests are offline by definition (AGENTS.md), but nothing enforced
it: a forgotten source call inside a test (post.build_charts pulling a
reference cutout for an SN fixture in test_overview_panel) did real HTTP.
It stayed green while the host answered fast and hung the Windows CI gate
for its whole 12-minute budget the day legacysurvey.org stalled on connect
(2026-09-23). This fixture makes every requests call fail in milliseconds,
naming the URL, so a leak fails the gate fast instead of freezing it.
Network tests belong to tests/functional; everything else fakes its source
at the function level (test_followup_sequence.py shows the pattern).
"""

import os

import pytest
import requests

# Every worker (and the plain run) creates a QApplication: offscreen keeps
# it headless without depending on a display, set before any Qt import. An
# EMPTY value counts as unset: the CI passes the platform through a dispatch
# input, and an empty string there would leave Qt with no platform at all
# (and the per-module setdefault below would keep it).
os.environ["QT_QPA_PLATFORM"] = os.environ.get("QT_QPA_PLATFORM") or "offscreen"

# Before any nightscribe module imports the `db`/`config` singletons, point
# the per-OS paths at a throwaway tree: Config.save() and every Database
# write used to land on the developer's real files during a test run (his
# camera profile and solve_save reverted, and the 190 MB db grew). The
# conftest is imported before the test modules, so this wins.
import tempfile as _tempfile
from pathlib import Path as _Path

from nightscribe import paths as _paths

_TEST_ROOT = _Path(_tempfile.mkdtemp(prefix="nightscribe-tests-"))
(_TEST_ROOT / "data").mkdir(parents=True, exist_ok=True)
(_TEST_ROOT / "config").mkdir(parents=True, exist_ok=True)
_paths.data_dir = lambda: _TEST_ROOT / "data"
_paths.config_dir = lambda: _TEST_ROOT / "config"


@pytest.fixture(autouse=True)
def _fake_solve_worker(monkeypatch):
    # ADR-051 rev: any action that needs a WCS now starts a solve worker
    # by itself. In unit tests the solver is stubbed: no subprocess, no
    # network, and no thread finishing during the NEXT test (the real one
    # would fire a QMessageBox and abort an offscreen run). A test that
    # cares about solving patches it on top.
    from PySide6.QtCore import QObject, Signal
    import nightscribe.gui.workers as workers

    class _FakeSolveWorker(QObject):
        finished = Signal(dict)
        progress = Signal(str)

        def __init__(self, path, pointing=None):
            super().__init__()
            self._path = path
            # the field the window knows (a project's target): a test that
            # cares about it reads it back from the worker it captured
            self.pointing = pointing
            self._cancelled = False

        def start(self):
            pass

        def isRunning(self):
            return False

        def cancel(self):
            self._cancelled = True

        def cancelled(self):
            return self._cancelled

    monkeypatch.setattr(workers, "UfeSolveWorker", _FakeSolveWorker)


@pytest.fixture(autouse=True)
def _isolated_config_file(tmp_path, monkeypatch):
    # Config.save() writes the WHOLE in-memory _data to the real file. The
    # pins below plus any config.set() during a test (closing a chart
    # viewer writes chart_viewer_sizes) used to clobber the developer's
    # real config: his camera profile and solve_save reverted after a test
    # run. Point the singleton at a throwaway file for every test.
    from nightscribe.config import config
    monkeypatch.setattr(config, "_file", tmp_path / "nightscribe.json")


@pytest.fixture(autouse=True)
def _chart_style_defaults(monkeypatch):
    # The GUI reads the chart-annotation settings (ADR-046) live from the
    # config singleton, which loads the DEVELOPER'S real config file: a
    # saved marker_style/chart_boxes there silently rewrites what the
    # drawing tests see (the classic-marker tests failed on the author's
    # machine the day he tried the feature for real). Pin the feature's
    # keys to their defaults so tests are host-independent; a test that
    # cares still monkeypatches on top.
    from nightscribe.config import DEFAULTS, config
    for key in ("marker_style", "chart_boxes", "observer_name",
                "measurer_name", "telescope_desc", "camera_model",
                "ufe_bar_icons"):
        monkeypatch.setitem(config._data, key, DEFAULTS[key])
    # the camera profile (ADR-042 follow-up) is also read live from the
    # real config: a saved preset/linearity silently changed the
    # saturated/non-linear verdicts in the measure tests (they failed on
    # the author's machine with his GSENSE400 profile). Pin them too.
    for key in ("ccd_gain", "ccd_read_noise", "ccd_saturate",
                "flat_resid_mag", "cam_preset", "cam_full_well_e",
                "cam_linearity_adu", "cam_dark_current_e_s",
                "cam_dark_temp_c", "cam_max_exposure_s", "cam_regime"):
        monkeypatch.setitem(config._data, key, DEFAULTS[key])
    # ADR-051 rev: solving persists the WCS into the FITS by default. In
    # unit tests the "plates" are repo fixtures, so keep the write off; a
    # test that wants it turns it on with a tmp copy.
    monkeypatch.setitem(config._data, "solve_save", False)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    # @return: None. Any requests call (requests.get/post go through
    # Session.request too) raises ConnectionError at once. It is a
    # RequestException, so the sources' own offline fallbacks engage
    # (cutouts returns None, the "field" chart stays absent, etc.); a
    # source that forgot its guard fails the test loudly, which is the
    # point.
    def _blocked(session, method, url, **kwargs):
        raise requests.ConnectionError(
            f"unit tests are offline: {method} {url} (fake the source, "
            f"like test_followup_sequence.py, or move the test to "
            f"tests/functional)")

    monkeypatch.setattr(requests.sessions.Session, "request", _blocked)
