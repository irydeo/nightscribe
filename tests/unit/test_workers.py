############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: background workers (UX, U0.5)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen tests for the QThread workers added in U0.5 (UX-f):
ResolveWorker (VSX -> SIMBAD chain) and SurveyWorker (survey context
points). Both must emit a payload and must never let a network exception
escape run().
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest                                     # noqa: E402
from PySide6.QtTest import QSignalSpy             # noqa: E402
from PySide6.QtWidgets import QApplication        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_resolve_worker_vsx_hit(qapp, monkeypatch):
    from nightscribe.core.sources import vsx
    from nightscribe.gui.workers import ResolveWorker
    monkeypatch.setattr(vsx, "lookup",
                        lambda name: {"name": "T CrB", "period_d": 227.55})
    w = ResolveWorker("T CrB")
    spy = QSignalSpy(w.finished)
    w.run()                                       # same thread: synchronous
    assert spy.count() == 1
    assert spy.at(0)[0]["vsx"]["period_d"] == 227.55


def test_resolve_worker_falls_back_to_simbad(qapp, monkeypatch):
    from nightscribe.core.sources import simbad, vsx
    from nightscribe.gui.workers import ResolveWorker
    monkeypatch.setattr(vsx, "lookup", lambda name: None)
    monkeypatch.setattr(simbad, "query_id",
                        lambda name: {"ra": "01h02m03s", "otype": "Star"})
    w = ResolveWorker("WeSb 1")
    spy = QSignalSpy(w.finished)
    w.run()
    assert spy.at(0)[0]["vsx"] is None
    assert spy.at(0)[0]["simbad"]["otype"] == "Star"


def test_resolve_worker_never_raises(qapp, monkeypatch):
    from nightscribe.core.sources import vsx
    from nightscribe.gui.workers import ResolveWorker

    def boom(_name):
        raise OSError("network down")
    monkeypatch.setattr(vsx, "lookup", boom)
    w = ResolveWorker("X")
    spy = QSignalSpy(w.finished)
    w.run()
    assert spy.at(0)[0] == {"vsx": None, "simbad": None}


def test_survey_worker_payload(qapp, monkeypatch):
    from nightscribe.core.sources import surveys
    from nightscribe.gui.workers import SurveyWorker
    pts = [{"mjd": 60100.0, "filter": "g", "mag": 15.1, "err": 0.02,
            "source": "survey:ztf"}]
    monkeypatch.setattr(surveys, "fetch_points", lambda ra, dec: pts)
    w = SurveyWorker(15.2, 55.0)
    spy = QSignalSpy(w.finished)
    w.run()
    assert spy.at(0)[0][0]["source"] == "survey:ztf"


def test_survey_worker_failure_is_empty(qapp, monkeypatch):
    from nightscribe.core.sources import surveys
    from nightscribe.gui.workers import SurveyWorker

    def boom(_ra, _dec):
        raise OSError("network down")
    monkeypatch.setattr(surveys, "fetch_points", boom)
    w = SurveyWorker(0.0, 0.0)
    spy = QSignalSpy(w.finished)
    w.run()
    assert spy.at(0)[0] == []
