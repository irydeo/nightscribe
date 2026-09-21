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
    def detailed(ra, dec, radius_arcsec=3.0, force=False):
        return {"status": "ok", "points": pts, "error": None}
    monkeypatch.setattr(surveys, "fetch_points_detailed", detailed)
    w = SurveyWorker(15.2, 55.0)
    spy = QSignalSpy(w.finished)
    w.run()
    out = spy.at(0)[0]
    assert out["status"] == "ok"
    assert out["points"][0]["source"] == "survey:ztf"
    assert out["error"] is None


def test_survey_worker_failure_reports_error(qapp, monkeypatch):
    # A dead network must not crash the GUI thread: the worker catches it
    # and reports status="error" with the reason
    from nightscribe.core.sources import surveys
    from nightscribe.gui.workers import SurveyWorker

    def boom(_ra, _dec, radius_arcsec=3.0, force=False):
        raise OSError("network down")
    monkeypatch.setattr(surveys, "fetch_points_detailed", boom)
    w = SurveyWorker(0.0, 0.0)
    spy = QSignalSpy(w.finished)
    w.run()
    out = spy.at(0)[0]
    assert out["status"] == "error"
    assert out["points"] == []
    assert "network down" in out["error"]


def _seq_star():
    return {"id": "s1", "name": None, "ra": 238.786, "dec": 25.92,
            "mag": 11.0, "band": "G", "catalog": "Gaia EDR3",
            "bands": [{"label": "G", "value": 11.0, "err": 0.003,
                       "derived": False}],
            "bv": 0.5, "color_origin": "direct", "vsx": None}


def test_sequence_worker_emits_a_crossmatched_field(qapp, monkeypatch):
    # Regression for the segfault on the follow-up's "Generate": the field
    # of a field WITH a VSX cross-match must cross the finished signal
    # intact. The old var<->star reference cycle recursed the Signal(dict)
    # QVariant conversion into a C stack overflow.
    from nightscribe.core import compstars
    from nightscribe.core.sources import cutouts
    from nightscribe.gui.workers import SequenceWorker

    stars = [_seq_star()]
    variables = [{"oid": "1", "name": "T CrB", "type": "NR",
                  "period_d": None, "ra": 238.786, "dec": 25.92}]
    compstars.match_vsx(stars, variables)
    field = {"stars": stars, "variables": variables, "catalog": "gaia",
             "catalog_name": "Gaia EDR3", "band": "G",
             "center": (238.786, 25.92), "fov_arcmin": 18.0,
             "vsx_warning": False}
    monkeypatch.setattr(compstars, "load_field", lambda *a, **k: field)
    monkeypatch.setattr(cutouts, "reference_cutout", lambda *a, **k:
                        (None, None))

    w = SequenceWorker("T CrB", 238.786, 25.92, "gaia", 18.0, 8, 10.0,
                       None, "en")
    spy = QSignalSpy(w.finished)
    w.run()                                       # same thread: synchronous
    assert spy.count() == 1
    out = spy.at(0)[0]
    assert out["status"] == "ok"
    # both directions of the cross-match survive the trip
    assert out["field"]["variables"][0]["star"]["id"] == "s1"
    assert out["field"]["stars"][0]["vsx"]["name"] == "T CrB"


def test_sequence_worker_field_failure_reports_error(qapp, monkeypatch):
    # VizieR down: an honest error payload, never an exception
    from nightscribe.core import compstars
    from nightscribe.gui.workers import SequenceWorker

    def boom(*_a, **_k):
        raise OSError("network down")
    monkeypatch.setattr(compstars, "load_field", boom)
    w = SequenceWorker("T CrB", 238.786, 25.92, "gaia", 18.0, 8, 10.0,
                       None, "en")
    spy = QSignalSpy(w.finished)
    w.run()
    out = spy.at(0)[0]
    assert out["status"] == "error"
    assert "VizieR" in out["error"]
