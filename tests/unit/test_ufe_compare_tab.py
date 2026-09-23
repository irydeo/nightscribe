############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE Compare tab (ADR-044, phase F)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_compare_tab.py: the comparison-sequence
picker on the shared plate view. Field generation goes through a fake
UfeFieldWorker (no network); stars come from a synthetic catalog mapped
through the plate's real WCS. The legacy SeqChartDialog is untouched.
"""

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = Path(__file__).parents[1] / "fixtures"
MONO = FIXTURES / "sn2026zji_new_image.fits"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture
def dlg(qapp):
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.state.load(MONO)
    d.tabs.setCurrentWidget(d.tab_compare)      # take the stage
    yield d
    d.tab_blink.shutdown()
    d.view._render_timer.stop()
    d.deleteLater()


def _field(dlg, n=60, with_vsx=True):
    # A synthetic catalog field around the plate centre (real WCS), one
    # VSX variable matched to the 6th star.
    rng = np.random.default_rng(3)
    cra, cdec = dlg.state.wcs.center()
    stars = []
    for _i in range(n):
        ra = cra + rng.uniform(-0.15, 0.15)
        dec = cdec + rng.uniform(-0.15, 0.15)
        mag = 11.0 + rng.uniform(0, 5)
        stars.append({"id": f"J{ra:.4f}{dec:+.4f}", "name": None,
                      "ra": ra, "dec": dec, "mag": mag, "band": "G",
                      "catalog": "Gaia EDR3",
                      "bands": [{"label": "G", "value": mag, "err": 0.003,
                                 "derived": False}],
                      "bv": 0.8, "color_origin": "direct", "vsx": None})
    variables = []
    if with_vsx:
        stars[5]["vsx"] = {"name": "V0817 Cyg", "type": "DSCT"}
        variables.append({"star": stars[5]})
    return {"stars": stars, "variables": variables, "catalog": "gaia",
            "catalog_name": "Gaia EDR3", "band": "G",
            "center": (cra, cdec), "fov_arcmin": 36.0,
            "vsx_warning": False}


class _FakeFieldWorker:
    # Synchronous UfeFieldWorker double.
    def __init__(self, catalog, ra, dec, fov, field=None):
        from PySide6.QtCore import QObject, Signal
        self._field = field
        self.query = (catalog, ra, dec, fov)

        class _Sig(QObject):
            finished = Signal(object)
        self._sig = _Sig()
        self.finished = self._sig.finished

    def start(self):
        self.finished.emit(self._field or {})


def test_tab_is_real_and_enabled(dlg):
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Blink", "Compare", "Measure", "Annotate"]
    assert dlg.tab_compare.isEnabled()
    assert dlg.tab_compare.edt_target.text() == "sn2026zji_new_image"


def test_generate_needs_a_wcs(dlg, tmp_path):
    from test_fits_annotate import _make_fits
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    dlg.tab_compare._on_generate()
    assert "WCS" in dlg.tab_compare.lbl_status.text()
    assert dlg.tab_compare._worker is None


def test_generate_queries_around_the_plate_centre(dlg, monkeypatch):
    tab = dlg.tab_compare
    captured = {}

    def fake(catalog, ra, dec, fov):
        captured["args"] = (catalog, ra, dec, fov)
        return _FakeFieldWorker(catalog, ra, dec, fov, field=_field(dlg))
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker", fake)
    tab._on_generate()
    catalog, ra, dec, fov = captured["args"]
    assert catalog == "gaia"
    cra, cdec = dlg.state.wcs.center()
    assert ra == pytest.approx(cra) and dec == pytest.approx(cdec)
    # the FOV is the plate's long side in arcminutes (~36' at 1.07"/px)
    assert 30.0 < fov < 40.0
    assert len(tab._stars) == 60
    assert "60" in tab.lbl_status.text()
    assert len(tab._items) > 0                  # overlays on stage


def test_generate_failure_is_honest(dlg, monkeypatch):
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker",
                        lambda *a: _FakeFieldWorker(*a, field=None))
    dlg.tab_compare._on_generate()
    assert "failed" in dlg.tab_compare.lbl_status.text()


def test_click_toggles_comp_and_check(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    from PySide6.QtCore import QPointF
    s = tab._stars[0]
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert [(e["name"], e["kind"]) for e in tab._entries] == \
        [("Comp1", "comp")]
    tab.rdo_check.setChecked(True)
    s2 = tab._stars[1]
    dlg.view.scene_clicked.emit(QPointF(s2["_sx"], s2["_sy"]))
    assert tab._entries[1]["kind"] == "check"
    assert tab._entries[1]["name"] == "Check"
    # a second click on the same star removes it
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert len(tab._entries) == 1
    assert tab.table.rowCount() == 1


def test_vsx_star_is_refused_with_a_reason(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    from PySide6.QtCore import QPointF
    s5 = tab._stars[5]
    dlg.view.scene_clicked.emit(QPointF(s5["_sx"], s5["_sy"]))
    assert tab._entries == []
    assert "V0817 Cyg" in tab.lbl_status.text()


def test_propose_fills_comps_and_check(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab.spn_mag.setValue(12.5)
    tab._on_propose()
    kinds = [e["kind"] for e in tab._entries]
    assert kinds.count("comp") >= 6 and "check" in kinds
    assert tab.table.rowCount() == len(tab._entries)
    # the proposed stars carry the entry rings as overlays
    assert len(tab._entry_items) == 2 * len(tab._entries)


def test_table_edits_flow_to_the_sequence(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    tab.table.cellWidget(0, 1).setCurrentIndex(1)     # Comp -> Check
    assert tab._entries[0]["kind"] == "check"
    tab.table.item(0, 0).setText("MiComp")
    tab._flush_table()
    assert tab._entries[0]["name"] == "MiComp"
    tab._remove(0)
    assert tab.table.rowCount() == len(tab._entries)
    tab._on_clear()
    assert tab._entries == [] and tab.table.rowCount() == 0


def test_catalog_labels_toggle(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    assert any(it.isVisible() for it, _ in tab._catalog_items)
    tab.chk_labels.setChecked(False)
    assert all(not it.isVisible() for it, _ in tab._catalog_items)


def test_probe_star_info_and_pixel_fallback(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    s = tab._stars[0]
    hit, lines = tab._probe(s["_sx"], s["_sy"])
    assert hit and lines[0].startswith("Gaia EDR3")
    hit, lines = tab._probe(5.0, 5.0)
    assert hit and "DN" in lines[0]              # the state's pixel probe


def test_leaving_the_tab_restores_the_pixel_probe(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    assert dlg.view._hover_probe == tab._probe
    dlg.tabs.setCurrentIndex(0)
    assert dlg.view._hover_probe == dlg.state.probe_text
    assert tab._items == []
    dlg.tabs.setCurrentWidget(tab)
    assert len(tab._items) > 0


def test_csv_export_writes_the_sequence(dlg, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    out = tmp_path / "secuencia.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    tab._export_csv()
    text = out.read_text()
    assert "# target: sn2026zji_new_image" in text
    assert "Comparison" in text and "Check" in text
    assert "Written to" in tab.lbl_status.text()


def test_loading_a_new_plate_invalidates_the_field(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    dlg.state.load(MONO)
    assert tab._field is None and tab._entries == []
    assert tab.table.rowCount() == 0
