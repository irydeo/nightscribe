############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: comparison chart dialog (ADR-042, phase 4)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/seqchart_dialog.py: the table mirrors the
sequence, edits flow back to the chart, and "save into the project"
writes the CSV+PNG pair and hands the entries to the caller. No network.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

CENTER = (291.366, 42.784)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    existing = QApplication.instance()
    if existing is not None:
        return existing
    return QApplication([])


def _star(ra, dec, mag):
    return {"id": f"J{ra:.4f}{dec:+.4f}", "name": None, "ra": ra,
            "dec": dec, "mag": mag, "band": "G", "catalog": "Gaia EDR3",
            "bands": [{"label": "G", "value": mag, "err": 0.003,
                       "derived": False}],
            "bv": 0.6, "color_origin": "estimated", "vsx": None}


def _field():
    return {"stars": [_star(291.366, 42.790, 12.0),
                      _star(291.300, 42.780, 12.5),
                      _star(291.400, 42.800, 13.5)],
            "variables": [], "catalog": "gaia", "catalog_name": "Gaia EDR3",
            "band": "G", "center": CENTER, "fov_arcmin": 18.0,
            "vsx_warning": False}


def _entries():
    return [{"name": "Comp1", "kind": "comp", "star": _star(
                291.366, 42.790, 12.0),
             "why": {"es": "más brillante", "en": "brighter"}},
            {"name": "Comp2", "kind": "comp", "star": _star(
                291.300, 42.780, 12.5),
             "why": {"es": "más brillante", "en": "brighter"}},
            {"name": "Check", "kind": "check", "star": _star(
                291.400, 42.800, 13.5),
             "why": {"es": "más brillante", "en": "brighter"}}]


def _dialog(qapp, tmp_path, on_save=None):
    from nightscribe.gui.seqchart_dialog import SeqChartDialog
    return SeqChartDialog(None, "V0001 Cyg", _field(), _entries(),
                          lang="en", default_dir=tmp_path, on_save=on_save)


def test_table_mirrors_the_sequence(qapp, tmp_path):
    dlg = _dialog(qapp, tmp_path)
    assert dlg._table.rowCount() == 3
    assert dlg._table.item(0, 0).text() == "Comp1"
    assert dlg._table.item(2, 0).text() == "Check"
    combo = dlg._table.cellWidget(2, 1)
    assert combo.currentData() == "check"
    dlg.close()


def test_remove_and_rename_flow_to_the_chart(qapp, tmp_path):
    dlg = _dialog(qapp, tmp_path)
    dlg._remove(0)
    assert dlg._table.rowCount() == 2
    assert [e["name"] for e in dlg.chart.entries()] == ["Comp2", "Check"]
    # rename in the table and flush
    dlg._table.item(0, 0).setText("Mi Comp")
    dlg._flush_table()
    assert dlg._entries[0]["name"] == "Mi Comp"
    assert dlg.chart.entries()[0]["name"] == "Mi Comp"
    dlg.close()


def test_save_into_project_writes_and_hands_over(qapp, tmp_path):
    saved = []
    dlg = _dialog(qapp, tmp_path, on_save=lambda e, f: saved.append((e, f)))
    dlg._save_into_project()
    assert len(saved) == 1
    entries, files = saved[0]
    assert len(entries) == 3
    from pathlib import Path
    assert Path(files["csv"]).exists() and Path(files["png"]).exists()
    text = Path(files["csv"]).read_text(encoding="utf-8")
    assert "# target: V0001 Cyg" in text and "Comp1" in text
    assert Path(files["png"]).stat().st_size > 0
    assert dlg.saved_files() == files


def test_no_image_says_so_in_plain_words(qapp, tmp_path):
    # the fixture passes image=None and no source label: the side panel
    # must say what the background dots are instead of staying silent
    from PySide6.QtWidgets import QLabel
    dlg = _dialog(qapp, tmp_path)
    texts = [lbl.text() for lbl in dlg.findChildren(QLabel)]
    assert any("No field image could be downloaded" in t for t in texts)
    dlg.close()


def test_window_minimum_size_keeps_all_text_visible(qapp, tmp_path):
    # the window can never shrink below what its (translated) widgets need
    dlg = _dialog(qapp, tmp_path)
    hint = dlg.minimumSizeHint()
    assert dlg.minimumWidth() >= 1000 and dlg.minimumHeight() >= 680
    assert dlg.minimumWidth() >= hint.width()
    dlg.close()
