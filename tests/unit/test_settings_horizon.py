############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Settings dialog horizon chunk tests (offscreen)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen tests for the settings dialog horizon chunk (ADR-020, phase B).

The precedence rule, made visible: while a horizon file loads, it IS the
safety reference, so the flat minimum altitude is greyed out and a stats
line (min/max altitude, peak azimuth, point count) is shown; if the path
is empty or the file cannot be read, the minimum altitude takes back the
wheel. The browse box also offers the .hrz name first.

The real preview lives on MainWindow, so the tests load the same .ui
file it loads (nightscribe/gui/ui/settings_dialog.ui) and drive the
method with a minimal tr()-capable host: no full window, no network.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# The canonical TheSkyX export in the repo (same ground truth as
# tests/unit/test_horizon.py): 20.0° floor, 77.5° peak at azimuth 268,
# 360 points.
HRZ = Path(__file__).parents[2] / "docs" / "limits-sample.hrz"

assert HRZ.is_file(), "docs/limits-sample.hrz must exist for these tests"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture()
def dlg(qapp):
    # the exact dialog the settings flow loads — the test drives the
    # same widget on_open_settings drives (same object names)
    from nightscribe.gui.main_window import _load_ui
    d = _load_ui("settings_dialog")
    yield d
    d.deleteLater()


class _Host:
    # The smallest stand-in for the MainWindow that owns the preview:
    # only tr() is used, and the base language in code is English
    # (ADR-014), so passing the string through is the contract.
    def tr(self, s):
        return s


def _preview(dlg):
    # The real method, unbound, on the minimal host (the method reads
    # only dlg + self.tr, no window state).
    from nightscribe.gui.main_window import MainWindow
    MainWindow._horizon_file_preview(_Host(), dlg)


def test_preview_no_file_keeps_min_alt_active(dlg):
    dlg.edt_horizon_file.setText("")
    _preview(dlg)
    assert dlg.spn_min_alt.isEnabled()
    assert dlg.lbl_horizon_stats.text() == "", \
        "with no file there is nothing to summarise"


def test_preview_valid_file_disables_min_alt_and_shows_stats(dlg):
    # the file is the safety reference: the flat floor is off and the
    # summary line carries the golden values of the sample TheSkyX file
    dlg.edt_horizon_file.setText(str(HRZ))
    _preview(dlg)
    assert not dlg.spn_min_alt.isEnabled()
    text = dlg.lbl_horizon_stats.text()
    assert "20.0°" in text, f"min altitude missing from summary: {text!r}"
    assert "77.5°" in text, f"max altitude missing from summary: {text!r}"
    assert "268" in text, f"peak azimuth missing from summary: {text!r}"
    assert "360" in text, f"point count missing from summary: {text!r}"


def test_preview_broken_file_goes_back_to_min_alt(dlg, tmp_path):
    # a path that exists but is not a horizon file (and one that does
    # not exist at all): both fall back to the flat minimum altitude,
    # with a message that names the fallback (the «does not fit», but
    # for the file, rule: never silent)
    bad = tmp_path / "horizon.txt"
    bad.write_text("this is not a horizon file", encoding="utf-8")
    for path in (str(bad), str(tmp_path / "nope.hrz")):
        dlg.edt_horizon_file.setText(path)
        _preview(dlg)
        assert dlg.spn_min_alt.isEnabled(), \
            f"broken file must hand back the flat altitude: {path}"
        text = dlg.lbl_horizon_stats.text().lower()
        assert "minimum altitude" in text, \
            f"broken-file message must name the fallback: {text!r}"
    # and clearing the path restores the clean state
    dlg.edt_horizon_file.setText("")
    _preview(dlg)
    assert dlg.spn_min_alt.isEnabled()
    assert dlg.lbl_horizon_stats.text() == ""


def test_browse_filter_offers_hrz_first(dlg, monkeypatch):
    # the file box dialog must offer TheSkyX .hrz (not just *.txt) —
    # patch the Qt call so the test stays offscreen with no real dialog
    import nightscribe.gui.main_window as mw

    captured = {}

    class _FakeFileDialog:
        @staticmethod
        def getOpenFileName(parent, title, start, fltr):
            captured["title"] = title
            captured["filter"] = fltr
            return str(HRZ), fltr

    monkeypatch.setattr(mw, "QFileDialog", _FakeFileDialog)
    mw.MainWindow._horizon_browse_into(_Host(), dlg)
    assert "*.hrz" in captured["filter"], \
        f"browse filter must offer .hrz files: {captured['filter']!r}"
    # and picking the file lands in the box (the preview reacts through
    # the textChanged connection the settings flow makes when it runs)
    assert dlg.edt_horizon_file.text() == str(HRZ)


def test_new_strings_are_translated(qapp):
    # the five new strings of the horizon chunk must resolve in
    # Spanish (the .qm built with lrelease), the same way the overview
    # panel ones do — the .ts and .qm must not drift apart silently
    from PySide6.QtCore import QTranslator

    qm = Path(__file__).parents[2] / "nightscribe" / "gui" / "i18n" \
        / "nightscribe_es.qm"
    tr = QTranslator(qapp)
    assert tr.load(str(qm)), "nightscribe_es.qm must load"
    qapp.installTranslator(tr)
    try:
        # code strings live in the MainWindow context, the .ui tooltips
        # in SettingsDialog — check each against its own context
        checks = {
            "MainWindow": {
                "Could not be read as a limit file — the flat "
                "minimum altitude is used instead":
                "No se ha podido leer como fichero de límites",
                "peak at azimuth %1°":
                "pico en el azimut %1°",
            },
            "SettingsDialog": {
                # ADR-028: help now lives below the field (lblH_minalt),
                # not as a tooltip on the stats label.
                "Flat altitude floor, used only when no limit file is "
                "loaded":
                "Piso fijo de altitud",
            },
        }
        for ctx, pairs in checks.items():
            for src, fragment in pairs.items():
                out = tr.translate(ctx, src)
                # translated (not the English source) and carrying the
                # expected Spanish, without demanding the exact full string
                assert out != src, \
                    f"[{ctx}] Spanish translation missing for: {src!r}"
                assert fragment in out, \
                    f"[{ctx}] drifted for: {src!r} -> {out!r}"
    finally:
        qapp.removeTranslator(tr)
