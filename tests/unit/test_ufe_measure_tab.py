############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE Measure tab (phase G2, calibrated
# single-plate photometry)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_measure_tab.py: a synthetic plate with a
real WCS and planted gaussian stars (fixed seed), the Compare tab's
sequence injected, and one click measuring the target against them. The
physics is proven in test_photometry.py; here the wiring is: click,
comps measured on the same plate, ZP, panel, guards, and the CSV/EFF
exports. No network.
"""

import math
import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = Path(__file__).parents[1] / "fixtures"
MONO = FIXTURES / "sn2026zji_new_image.fits"

W = H = 240
SIGMA = 3.0
ZP_TRUE = 22.31


def _card(key, value=None, comment=""):
    s = key.ljust(8) if value is None else f"{key.ljust(8)}= {value}"
    return (s + (f" / {comment}" if comment else ""))[:80].ljust(80)


def _write_plate(path, data, wcs=True, instrument=True):
    # @return: a minimal float32 FITS with a TAN WCS and a DATE-OBS
    cards = [_card("SIMPLE", "T"), _card("BITPIX", "-32"),
             _card("NAXIS", "2"), _card("NAXIS1", str(data.shape[1])),
             _card("NAXIS2", str(data.shape[0]))]
    if wcs:
        cards += [_card("CTYPE1", "'RA---TAN'"), _card("CTYPE2", "'DEC--TAN'"),
                  _card("CRVAL1", "300.0"), _card("CRVAL2", "60.0"),
                  _card("CRPIX1", str(data.shape[1] / 2)),
                  _card("CRPIX2", str(data.shape[0] / 2)),
                  _card("CD1_1", "-0.0003"), _card("CD1_2", "0.0"),
                  _card("CD2_1", "0.0"), _card("CD2_2", "0.0003")]
    if instrument:
        cards += [_card("GAIN", "2.0"), _card("RDNOISE", "5.0"),
                  _card("DATE-OBS", "'2026-09-20T23:30:00'")]
    header = "".join(cards + [_card("END")]).encode("latin-1")
    header += b" " * ((2880 - len(header) % 2880) % 2880)
    raw = np.ascontiguousarray(data, dtype=">f4").tobytes()
    raw += b"\0" * ((2880 - len(raw) % 2880) % 2880)
    Path(path).write_bytes(header + raw)
    return path


def _plate(target_amp=7000.0, n_comps=5, comp_amp=10000.0, seed=42,
           clip_target=None):
    # @return: (data, target_xy, comp_xy_list): flat sky + gaussians
    rng = np.random.default_rng(seed)
    data = np.full((H, W), 1000.0) + rng.normal(0.0, 1.0, (H, W))
    yy, xx = np.ogrid[:H, :W]
    target = (120.0, 120.0)
    data += target_amp * np.exp(-((xx - target[0]) ** 2
                                  + (yy - target[1]) ** 2)
                                / (2 * SIGMA ** 2))
    comps = [(120 + 60 * math.cos(j * 2 * math.pi / n_comps),
              120 + 60 * math.sin(j * 2 * math.pi / n_comps))
             for j in range(n_comps)]
    for cx, cy in comps:
        data += comp_amp * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2)
                                  / (2 * SIGMA ** 2))
    if clip_target is not None:
        data = np.minimum(data, clip_target)
    return data, target, comps


def _sequence(dlg, comps):
    # The Compare tab's entries: each star's catalog V is its measured
    # instrumental magnitude plus the known ZP (the wiring test; the
    # physics lives in test_photometry.py).
    from nightscribe.core import photometry as phot
    entries = []
    for j, (cx, cy) in enumerate(comps):
        r = phot.measure_point(dlg.state.data, cx, cy)
        inst = -2.5 * math.log10(r["flux"])
        ra, dec = dlg.state.wcs.pixel_to_sky(cx, cy)
        entries.append({"name": f"Comp{j + 1}", "kind": "comp",
                        "star": {"ra": ra, "dec": dec, "mag": inst + ZP_TRUE,
                                 "band": "V", "catalog": "synthetic",
                                 "bands": [{"label": "V",
                                            "value": inst + ZP_TRUE,
                                            "err": 0.01,
                                            "derived": False}],
                                 "bv": 0.6}})
    dlg.tab_compare._entries = entries
    return entries


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture
def dlg(qapp, tmp_path):
    from nightscribe.gui.ufe_dialog import UfeDialog
    data, target, comps = _plate()
    plate = _write_plate(tmp_path / "plate.fits", data)
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.state.load(plate)
    d._test_target = target
    d._test_comps = comps
    d.tabs.setCurrentWidget(d.tab_measure)
    yield d
    d.tab_blink.shutdown()
    d.view._render_timer.stop()
    d.deleteLater()


def _click(dlg, x, y):
    from PySide6.QtCore import QPointF
    sx, sy = dlg.state.data_to_scene(x, y)
    dlg.view.scene_clicked.emit(QPointF(sx, sy))


def test_tab_present_and_enabled(dlg):
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Blink", "Compare", "Measure", "Annotate"]
    assert dlg.tab_measure.isEnabled()


def test_click_without_sequence_guides_to_compare(dlg):
    _click(dlg, *dlg._test_target)
    assert "Compare" in dlg.tab_measure.lbl_status.text()
    assert dlg.tab_measure.btn_go_compare.isVisible()


def test_full_measurement_calibrates(dlg):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab = dlg.tab_measure
    assert tab.lbl_status.text() == ""
    panel = tab.lbl_result.text()
    assert "Zero point: 22.310" in panel
    assert "Magnitude:" in panel and "(V)" in panel
    from nightscribe.core import photometry as phot
    r = phot.measure_point(dlg.state.data, *dlg._test_target)
    expected = -2.5 * math.log10(r["flux"]) + ZP_TRUE
    assert tab._last["mag"] == pytest.approx(expected, abs=0.01)
    assert tab._last["err"] < 0.05
    # aperture + annulus on the target and a ring per comp used
    assert len(tab._items) == 3 + 5
    assert tab.btn_csv.isEnabled() and tab.btn_eff.isEnabled()


def test_saturated_target_is_refused_with_a_reason(dlg, tmp_path):
    data, target, comps = _plate(target_amp=60000.0, clip_target=30000.0)
    plate = _write_plate(tmp_path / "saturated.fits", data)
    dlg.state.load(plate)
    _sequence(dlg, comps)
    _click(dlg, *target)
    assert dlg.tab_measure._last is None
    # the guard reason is a bilingual pair; the tab defaults to lang="es"
    assert dlg.tab_measure.lbl_status.text() == "saturada"
    assert not dlg.tab_measure.btn_csv.isEnabled()


def test_no_wcs_says_so(dlg, tmp_path):
    from test_fits_annotate import _make_fits
    plate = _make_fits(tmp_path / "nowcs.fits")
    dlg.state.load(plate)
    _click(dlg, 8.0, 8.0)
    assert "WCS" in dlg.tab_measure.lbl_status.text()


def test_csv_export_one_row_with_hjd_and_comps(dlg, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    out = tmp_path / "medida.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    dlg.tab_measure._export("csv")
    text = out.read_text()
    assert text.count("\n") >= 3          # headers + one row
    row = [ln for ln in text.splitlines() if not ln.startswith("#")][1]
    assert "Comp1+Comp2+Comp3" in row     # the comps travel in one cell
    assert row.split(",")[1] != ""        # HJD from DATE-OBS
    assert "Written to" in dlg.tab_measure.lbl_status.text()


def test_eff_export_fills_comp_and_check(dlg, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    entries = _sequence(dlg, dlg._test_comps)
    entries[0]["kind"] = "check"          # one check star in the sequence
    _click(dlg, *dlg._test_target)
    out = tmp_path / "medida.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    dlg.tab_measure._export("eff")
    text = out.read_text()
    assert "#TYPE=EXTENDED" in text
    data_line = [ln for ln in text.splitlines()
                 if not ln.startswith("#")][1]
    assert ",Comp2," in data_line         # first true comp as CNAME
    assert ",Comp1," in data_line         # the check as KNAME


def test_without_gain_the_error_is_comps_scatter_only(dlg, tmp_path):
    data, target, comps = _plate()
    plate = _write_plate(tmp_path / "nogain.fits", data, instrument=False)
    dlg.state.load(plate)
    _sequence(dlg, comps)
    _click(dlg, *target)
    panel = dlg.tab_measure.lbl_result.text()
    assert "scatter" in panel
    assert dlg.tab_measure._last["mag"] is not None


def test_new_plate_invalidates_the_measurement(dlg, tmp_path):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    assert dlg.tab_measure._last is not None
    data, _t, _c = _plate(seed=7)
    dlg.state.load(_write_plate(tmp_path / "other.fits", data))
    assert dlg.tab_measure._last is None
    assert dlg.tab_measure._items == []
    assert dlg.tab_measure.lbl_result.text() == "–"
