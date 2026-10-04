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
from PySide6.QtWidgets import QPushButton

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = Path(__file__).parents[1] / "fixtures"
MONO = FIXTURES / "sn2026zji_new_image.fits"

W = H = 240
SIGMA = 3.0
ZP_TRUE = 22.31


def _card(key, value=None, comment=""):
    s = key.ljust(8) if value is None else f"{key.ljust(8)}= {value}"
    return (s + (f" / {comment}" if comment else ""))[:80].ljust(80)


def _write_plate(path, data, wcs=True, instrument=True, extra=()):
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
    cards += list(extra)
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
    d.tabs.setCurrentWidget(d.tab_photometry)   # take the stage
    # no modes: the closed manual window already arms the measuring
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
    assert titles == ["Blink", "Photometry", "Annotate",
                      "Calibration", "Track && Stack"]
    assert dlg.tab_measure.isEnabled()


def test_click_without_sequence_guides_to_sequence(dlg):
    _click(dlg, *dlg._test_target)
    assert "Build the sequence" in dlg.tab_measure.lbl_status.text()


def test_no_calibration_explains_why(dlg):
    # Every comp skipped: the bare headline is not enough; the causes
    # ride right under it (the breakdown used to drown at the bottom of
    # the notes, below the fold).
    entries = _sequence(dlg, dlg._test_comps)
    for e in entries:
        e["star"]["bands"] = []                # the catalog lacks the band
    _click(dlg, *dlg._test_target)
    panel = dlg.tab_measure.lbl_result.toPlainText()
    assert "no calibration" in panel
    assert "Why:" in panel and "without the V band" in panel


def test_full_measurement_calibrates(dlg):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab = dlg.tab_measure
    assert tab.lbl_status.text() == ""
    panel = tab.lbl_result.toPlainText()
    assert "Zero point:" in panel and "22." in panel
    assert "Magnitude:" in panel and "(V)" in panel
    # the aperture cancels in differential photometry (all stars share
    # the PSF): whatever radius the seeing picked, the catalog magnitude
    # comes back. Compute the invariant from the default-aperture flux.
    from nightscribe.core import photometry as phot
    r = phot.measure_point(dlg.state.data, *dlg._test_target)
    expected = -2.5 * math.log10(r["flux"]) + ZP_TRUE
    assert tab._last["mag"] == pytest.approx(expected, abs=0.02)
    # internal error plus total error, total never below internal
    assert tab._last["err"] is not None
    assert tab._last["err"] >= (tab._last["err_internal"] or 0.0)
    # aperture + annulus on the target and a ring per comp used
    assert len(tab._items) == 3 + 5
    assert tab.btn_csv.isEnabled() and tab.btn_eff.isEnabled()


def test_remeasure_keeps_painting_while_the_sequence_owns_the_stage(dlg, qapp):
    # Regression (ADR-044 rev): the overlays follow the Photometry tab's
    # stage, not the click ownership. Re-measuring (any recipe control
    # ends in _remeasure) with the manual window open (the picking owns
    # the clicks) used to drop the rings and paint nothing back.
    tab = dlg.tab_measure
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    assert len(tab._items) == 3 + 5
    # window open: picking owns the clicks, Measure stays on stage
    dlg.tab_compare.btn_manual.click()
    qapp.processEvents()
    dlg.tab_photometry._apply()
    assert not tab._active and tab._on_stage
    tab._remeasure()
    assert tab._last is not None and tab._last.get("mag") is not None
    assert len(tab._items) == 3 + 5
    # window closed: Measure re-arms, still coherent; a full leave drops
    dlg.tab_compare.manual.hide()
    qapp.processEvents()
    dlg.tab_photometry._apply()
    assert len(tab._items) == 3 + 5
    dlg.tabs.setCurrentWidget(dlg.tab_blink)
    assert tab._items == []


def test_save_in_project_button_follows_the_point_hook(dlg):
    # ADR-044: "Save…" shows only when the dialog was
    # opened from a project (a point hook is set), stays disabled until
    # there is a calibrated point, and hands the payload to the host.
    tab = dlg.tab_measure
    btn = tab.btn_save_project
    assert not btn.isVisible()          # ad-hoc open: no project attached
    assert dlg.notify_point({"mag": 1.0}) is False     # no hook, no save

    seen = []
    dlg.set_point_hook(seen.append)
    assert btn.isVisible()
    assert not btn.isEnabled()          # nothing measured yet
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    assert btn.isEnabled()
    btn.click()
    assert len(seen) == 1
    pay = seen[0]
    assert pay["mag"] == pytest.approx(tab._last["mag"])
    assert pay["filter"] == "V"
    assert pay["mjd"] is not None and pay["mjd"] > 60000
    assert "saved" in tab.lbl_status.text().lower()
    # every click sends the point: the host registers it per click
    btn.click()
    assert len(seen) == 2


def test_save_in_project_requires_an_observation_date(dlg, tmp_path):
    # ADR-044: without a DATE-OBS there is no MJD to register: the save
    # is refused and the status says why (never a silent drop).
    tab = dlg.tab_measure
    data, target, comps = _plate()
    plate = _write_plate(tmp_path / "nodate.fits", data, instrument=False)
    dlg.state.load(plate)
    _sequence(dlg, comps)
    _click(dlg, *target)
    seen = []
    dlg.set_point_hook(seen.append)
    tab.btn_save_project.click()
    assert seen == []                       # nothing left the tab
    assert "date" in tab.lbl_status.text().lower()


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
    panel = dlg.tab_measure.lbl_result.toPlainText()
    assert "photon noise is not in the error" in panel
    assert dlg.tab_measure._last["mag"] is not None


def test_new_plate_invalidates_the_measurement(dlg, tmp_path):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    assert dlg.tab_measure._last is not None
    data, _t, _c = _plate(seed=7)
    dlg.state.load(_write_plate(tmp_path / "other.fits", data))
    assert dlg.tab_measure._last is None
    assert dlg.tab_measure._items == []
    assert dlg.tab_measure.lbl_result.toPlainText() == "–"


# ---------------- phase H pieces ----------------


def test_seeing_checkbox_scales_the_apertures(dlg):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab = dlg.tab_measure
    assert tab._last["fwhm"] is not None
    assert "seeing FWHM" in tab.lbl_result.toPlainText()
    # the spins follow the measured seeing (and stay tweakable); the
    # spinbox shows one decimal, the state keeps full precision
    assert tab.spn_rap.value() == pytest.approx(
        tab._last["radii"][0], abs=0.06)
    # off: back to the user's/manual radii
    tab.chk_seeing.setChecked(False)
    tab.spn_rap.setValue(6.0)
    _click(dlg, *dlg._test_target)
    assert tab._last["fwhm"] is None
    assert tab._last["radii"][0] == 6.0


def test_sky_plane_on_a_strong_gradient(dlg, tmp_path):
    # a galactic-core ramp under the target: the plane is less biased
    from nightscribe.core import photometry as phot
    data, target, comps = _plate()
    yy, xx = np.ogrid[:H, :W]
    data = data + 30.0 * (xx - target[0])    # steep local ramp
    plate = _write_plate(tmp_path / "ramp.fits", data)
    dlg.state.load(plate)
    _sequence(dlg, comps)
    tab = dlg.tab_measure
    tab.cmb_sky.setCurrentIndex(0)           # median
    _click(dlg, *target)
    med_flux = tab._last["result"]["flux"]
    tab.cmb_sky.setCurrentIndex(1)           # plane
    _click(dlg, *target)
    pla_flux = tab._last["result"]["flux"]
    truth = phot.measure_point(data, *target, sky_mode="plane",
                               sigma_clip=True)["flux"]
    assert abs(pla_flux - truth) <= abs(med_flux - truth)


def test_colour_term_fit_uses_target_bv(dlg, tmp_path):
    # comps with a colour spread and a known slope: k and the target's
    # B-V land in the calibrated magnitude. The colour fit needs >=6
    # comps with spread, so this plate plants six.
    from nightscribe.core import photometry as phot
    k_true = -0.08
    data, target, comps = _plate(n_comps=6)
    dlg.state.load(_write_plate(tmp_path / "six.fits", data))
    # fixed default apertures everywhere: this test isolates the colour
    # term (the seeing scaling has its own test)
    dlg.tab_measure.chk_seeing.setChecked(False)
    entries = _sequence(dlg, comps)
    for j, e in enumerate(entries):
        bv = 0.3 + j * 0.2                   # 0.3 .. 1.3: real spread
        e["star"]["bv"] = bv
        r = phot.measure_point(dlg.state.data,
                               *dlg.state.wcs.sky_to_pixel(
                                   e["star"]["ra"], e["star"]["dec"]))
        inst = -2.5 * math.log10(r["flux"])
        # catalog carries the colour term: cat = inst + ZP + k*bv
        e["star"]["bands"][0]["value"] = inst + ZP_TRUE + k_true * bv
    dlg.tab_measure.spn_target_bv.setValue(0.8)
    _click(dlg, *target)
    tab = dlg.tab_measure
    assert tab._last["zp"]["color_used"]
    assert tab._last["zp"]["k"] == pytest.approx(k_true, abs=0.01)
    assert "colour slope" in tab.lbl_result.toPlainText()
    r = phot.measure_point(dlg.state.data, *target,
                           r_ap=tab._last["radii"][0],
                           r_ann_in=tab._last["radii"][1],
                           r_ann_out=tab._last["radii"][2])
    expected = -2.5 * math.log10(r["flux"]) + ZP_TRUE + k_true * 0.8
    assert tab._last["mag"] == pytest.approx(expected, abs=0.02)


def test_colour_term_falls_back_without_spread(dlg):
    _sequence(dlg, dlg._test_comps)          # all bv = 0.6: no spread
    _click(dlg, *dlg._test_target)
    assert not dlg.tab_measure._last["zp"]["color_used"]
    assert "plain zero point" in dlg.tab_measure.lbl_result.toPlainText()


def test_check_star_semaphore(dlg):
    entries = _sequence(dlg, dlg._test_comps)
    # a check star whose catalog value lies by half a magnitude
    entries[0]["kind"] = "check"
    entries[0]["star"]["bands"][0]["value"] += 0.5
    _click(dlg, *dlg._test_target)
    panel = dlg.tab_measure.lbl_result.toPlainText()
    assert "NOT reliable" in panel and "Comp1" in panel
    # and an honest check star confirms the night
    entries[0]["star"]["bands"][0]["value"] -= 0.5
    _click(dlg, *dlg._test_target)
    panel = dlg.tab_measure.lbl_result.toPlainText()
    assert "OK" in panel and "NOT reliable" not in panel


def test_saturation_ceiling_from_the_header(dlg, tmp_path):
    # a SATURATE card below the comps' peak: the tab refuses the bright
    # target with the honest reason (H4, end to end through the tab)
    data, target, comps = _plate()
    plate = _write_plate(tmp_path / "ceil.fits", data,
                         extra=[_card("SATURATE", "9000.0")])
    dlg.state.load(plate)
    _sequence(dlg, comps)
    _click(dlg, *target)
    assert dlg.tab_measure._last is None
    assert dlg.tab_measure.lbl_status.text() == "saturada"
    # raise the ceiling and the same plate measures fine
    plate2 = _write_plate(tmp_path / "ceil2.fits", data,
                          extra=[_card("SATURATE", "60000.0")])
    dlg.state.load(plate2)
    _sequence(dlg, comps)
    _click(dlg, *target)
    assert dlg.tab_measure._last is not None


class _FakeSubWorker:
    # Synchronous BlinkWorker double delivering a prepared pair.
    def __init__(self, path, sn_name=None, ra=None, dec=None, pair=None):
        from PySide6.QtCore import QObject, Signal

        class _Sig(QObject):
            finished = Signal(dict, dict)
            progress = Signal(dict)
        self._sig = _Sig()
        self.finished = self._sig.finished
        self.progress = self._sig.progress
        self._pair = pair

    def start(self):
        # like the real worker and the Blink tab's double: a stage, done
        self.progress.emit({"es": "Descargando la referencia del survey…",
                            "en": "Downloading the survey reference…"})
        self.finished.emit(self._pair, {})


def test_host_subtraction_recovers_the_target(dlg, monkeypatch):
    from nightscribe.core import photometry as phot
    _sequence(dlg, dlg._test_comps)
    # the reference: the same field WITHOUT the target (a fresh plate)
    data, target, comps = _plate()
    ref, _t, _c = _plate(target_amp=0.0)
    pair = {"obs": dlg.state.data, "ref": ref, "sn_xy": target,
            "name": "SN x", "ra": 0.0, "dec": 0.0, "ref_label": "PS1 g",
            "flipped": False}
    monkeypatch.setattr("nightscribe.gui.workers.BlinkWorker",
                        lambda *a, **k: _FakeSubWorker(*a, pair=pair))
    tab = dlg.tab_measure
    tab.chk_subtract.setChecked(True)
    assert tab._diff is not None
    assert dlg.view._frame_override is not None
    assert "Host subtracted" in tab.lbl_status.text()
    _click(dlg, *target)
    # the target on the difference image: the host is gone, the flux is
    # the SN's alone; compare at the tab's (seeing-scaled) apertures
    r = tab._last["radii"]
    truth = phot.measure_point(dlg.state.data, *target, r_ap=r[0],
                               r_ann_in=r[1], r_ann_out=r[2])["flux"]
    assert tab._last["result"]["flux"] == pytest.approx(truth, rel=0.05)
    assert "Host galaxy subtracted" in tab.lbl_result.toPlainText()
    # toggle off: the plate comes back
    tab.chk_subtract.setChecked(False)
    assert tab._diff is None
    assert dlg.view._frame_override is None


def test_subtraction_without_a_sequence_reverts(dlg, monkeypatch):
    pair = {"obs": dlg.state.data, "ref": dlg.state.data,
            "sn_xy": None, "name": "", "ra": 0.0, "dec": 0.0,
            "ref_label": "PS1 g", "flipped": False}
    monkeypatch.setattr("nightscribe.gui.workers.BlinkWorker",
                        lambda *a, **k: _FakeSubWorker(*a, pair=pair))
    tab = dlg.tab_measure
    tab.chk_subtract.setChecked(True)
    assert tab._diff is None
    assert not tab.chk_subtract.isChecked()
    assert "no usable comparison star" in tab.lbl_status.text()


def test_subtraction_reports_the_pipeline_stages(dlg, monkeypatch):
    # the PS1 reference download takes a while: its stages must reach the
    # status line. Regression: the UFE review dropped the .progress wiring
    # that the legacy dialog and the Blink tab's prepare both keep.
    _sequence(dlg, dlg._test_comps)
    ref, _t, _c = _plate(target_amp=0.0)
    target = dlg._test_target
    pair = {"obs": dlg.state.data, "ref": ref, "sn_xy": target,
            "name": "SN x", "ra": 0.0, "dec": 0.0, "ref_label": "PS1 g",
            "flipped": False}
    created = {}

    def _factory(*a, **k):
        created["w"] = _FakeSubWorker(*a, pair=pair)
        return created["w"]

    monkeypatch.setattr("nightscribe.gui.workers.BlinkWorker", _factory)
    tab = dlg.tab_measure
    tab.chk_subtract.setChecked(True)
    assert tab._diff is not None
    # the finished handler overwrites the stage; re-emit it after the fact
    # to prove the progress connection is still alive
    w = created["w"]
    w.progress.emit({"es": "Descargando la referencia del survey (PS1 g)…",
                     "en": "Downloading the survey reference (PS1 g)…"})
    # the tab defaults to lang="es": the Spanish half must show
    assert "Descargando la referencia del survey" in tab.lbl_status.text()


# ---------------- review fixes (apertures) ----------------


def test_hand_edited_aperture_remeasures_and_wins(dlg):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab = dlg.tab_measure
    seeing_r = tab._last["radii"][0]
    assert seeing_r != 4.0                  # the seeing sized it first
    tab.spn_rap.setValue(4.0)               # the observer takes over
    assert tab._radii_manual
    # the current point was re-measured with the new radius at once
    assert tab._last["radii"][0] == 4.0
    assert "set by hand" in tab.lbl_result.toPlainText()
    # and a fresh click does NOT stomp the manual radius
    _click(dlg, *dlg._test_target)
    assert tab._last["radii"][0] == 4.0
    # re-arming the seeing checkbox hands the radii back
    tab.chk_seeing.setChecked(False)
    tab.chk_seeing.setChecked(True)
    assert not tab._radii_manual
    assert tab._last["radii"][0] != 4.0


def test_new_plate_rearms_the_seeing(dlg, tmp_path):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    dlg.tab_measure.spn_rap.setValue(4.0)
    assert dlg.tab_measure._radii_manual
    data, _t, _c = _plate(seed=9)
    dlg.state.load(_write_plate(tmp_path / "fresh.fits", data))
    assert not dlg.tab_measure._radii_manual


# ---------------- phase I: the Suggest button ----------------


def test_suggest_applies_and_explains(dlg):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab = dlg.tab_measure
    assert tab.chk_seeing.isChecked()           # seeing was on
    tab._on_suggest()
    # the suggestion applied, the seeing stepped aside, no manual flag
    assert not tab.chk_seeing.isChecked()
    assert not tab._radii_manual
    assert tab._last_suggestions                 # reasons in the panel
    assert tab._last_suggestions[0] in tab.lbl_result.toPlainText()
    r = tab._last["radii"]
    assert r == (round(r[0] * 2) / 2, round(r[1] * 2) / 2,
                 round(r[2] * 2) / 2)            # the spins show it


def test_suggest_without_a_measurement_guides(dlg):
    dlg.tab_measure._on_suggest()
    assert "Measure the target first" in dlg.tab_measure.lbl_status.text()


def _innermost_row_of(tab, target):
    # the nearest layout that holds `target`, walking the tab's layout
    # tree (rows are QHBoxLayouts nested in the main QVBoxLayout)
    if tab.layout() is None:
        return None
    stack = [tab.layout()]
    while stack:
        lay = stack.pop()
        for i in range(lay.count()):
            it = lay.itemAt(i)
            if it.widget() is target:
                return lay
            sub = it.layout()
            if sub is not None and sub is not lay:
                stack.append(sub)
    return None


def test_suggest_sits_on_its_own_row_below_the_apertures(dlg):
    # The daily flow is band, apertures, then Suggest on its own line
    # right under them (ADR-044 rev, 2026-09-27): the button left the
    # apertures row so the radii line never overflows on wide-font
    # platforms. The recipe knobs open in the Advanced window, not here.
    tab = dlg.tab_measure
    apt_row = _innermost_row_of(tab, tab.spn_rin)
    assert apt_row is not None
    apt_widgets = [apt_row.itemAt(i).widget() for i in range(apt_row.count())
                   if apt_row.itemAt(i).widget() is not None]
    for spn in (tab.spn_rap, tab.spn_rin, tab.spn_rout):
        assert spn in apt_widgets                   # all three radii
    assert any(w.text().startswith("Apertures") for w in apt_widgets)
    assert tab.btn_suggest not in apt_widgets       # its own row now
    assert tab.btn_advanced not in apt_widgets      # off the daily line
    # the radius spins stay narrow so the radii row never overflows
    for spn in (tab.spn_rap, tab.spn_rin, tab.spn_rout):
        assert spn.minimumWidth() == 70 == spn.maximumWidth()
    # Suggest on its own row, never sharing it with Advanced
    sug_row = _innermost_row_of(tab, tab.btn_suggest)
    assert sug_row is not None and sug_row is not apt_row
    sug_widgets = [sug_row.itemAt(i).widget() for i in range(sug_row.count())
                   if sug_row.itemAt(i).widget() is not None]
    assert tab.btn_advanced not in sug_widgets


# ---------------- review round 2 (subtract + options re-measure) -----


def test_subtraction_measures_on_a_consistent_scale(dlg, monkeypatch):
    # the pair at half resolution (blink downsamples big plates): the
    # target on the difference and the comps on the work frame share one
    # DN scale, so the magnitude matches the plain-plate measurement
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    plain_mag = dlg.tab_measure._last["mag"]
    data, target, comps = _plate()
    obs = data[::2, ::2].copy()
    ref, _t, _c = _plate(target_amp=0.0)
    ref = ref[::2, ::2].copy()
    pair = {"obs": obs, "ref": ref,
            "sn_xy": (target[0] / 2, target[1] / 2), "name": "SN x",
            "ra": 0.0, "dec": 0.0, "ref_label": "PS1 g",
            "flipped": False}
    monkeypatch.setattr("nightscribe.gui.workers.BlinkWorker",
                        lambda *a, **k: _FakeSubWorker(*a, pair=pair))
    tab = dlg.tab_measure
    tab.chk_subtract.setChecked(True)
    assert tab._diff is not None
    frame = tab._display_diff()
    assert frame.min() == 0 and frame.max() == 255   # visible, not black
    _click(dlg, *target)
    assert tab._last is not None
    assert tab._last["mag"] == pytest.approx(plain_mag, abs=0.05)
    tab.chk_subtract.setChecked(False)


def test_options_remeasure_the_live_point(dlg):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab = dlg.tab_measure
    assert tab._last["sky_mode"] == "median"
    # sky mode: flipping to plane re-measures with it
    tab.cmb_sky.setCurrentIndex(1)
    assert tab._last["sky_mode"] == "plane"
    # sigma-clip off re-measures without it
    tab.chk_sigmaclip.setChecked(False)
    assert tab._last["sigma_clip"] is False
    # colour term off re-measures with the plain zero point
    tab.chk_color.setChecked(False)
    assert tab._last["zp"]["color_used"] is False
    # target B-V re-measures with it
    tab.spn_target_bv.setValue(0.4)
    assert tab._last is not None


# ---------------- the 2026-09 review: clipping, identity, colour -------

def _sequence_static(dlg, comps, band="V", mag=12.0, bvs=None):
    # Sequence entries without measuring the plate (for plates whose
    # comps cannot be measured, e.g. clipped): catalog values arbitrary.
    entries = []
    for j, (cx, cy) in enumerate(comps):
        ra, dec = dlg.state.wcs.pixel_to_sky(cx, cy)
        bv = bvs[j] if bvs else 0.6
        entries.append({"name": f"Comp{j + 1}", "kind": "comp",
                        "star": {"ra": ra, "dec": dec, "mag": mag,
                                 "band": band, "catalog": "synthetic",
                                 "bands": [{"label": band, "value": mag,
                                            "err": 0.01,
                                            "derived": False}],
                                 "bv": bv}})
    dlg.tab_compare._entries = entries
    return entries


def test_field_crossmatch_line_and_bv_autofill(dlg):
    # The Compare tab's loaded field carries a star exactly where the
    # target sits: the panel must identify it (catalog magnitude and Δ
    # against our measurement) and its colour pre-fills the B-V spin.
    from nightscribe.core import photometry as phot
    tab = dlg.tab_measure
    tab.chk_seeing.setChecked(False)     # default radii: reproducible
    _sequence(dlg, dlg._test_comps)
    r = phot.measure_point(dlg.state.data, *dlg._test_target)
    mag_expected = -2.5 * math.log10(r["flux"]) + ZP_TRUE
    ra, dec = dlg.state.wcs.pixel_to_sky(*dlg._test_target)
    dlg.tab_compare._stars = [
        {"ra": ra, "dec": dec, "mag": mag_expected, "band": "V",
         "catalog": "synthetic", "id": "T1", "bv": 1.20,
         "bands": [{"label": "V", "value": mag_expected, "err": 0.01,
                    "derived": False}]}]
    _click(dlg, *dlg._test_target)
    panel = tab.lbl_result.toPlainText()
    assert "Field:" in panel and "T1" in panel
    assert "Δ" in panel                     # measured vs catalog, live
    assert tab.spn_target_bv.value() == pytest.approx(1.20)
    assert tab._bv_source == "catalog"


def test_no_field_match_says_new_object(dlg):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    assert "No catalogued source" in dlg.tab_measure.lbl_result.toPlainText()


def test_compressed_comps_are_excluded_and_named(dlg, tmp_path):
    # The review case: a plate that clips at 10500 ADU. Every comp core
    # is flat there; the hot corner lets the guard infer the ceiling.
    # The zero point must refuse them out loud instead of lying low:
    # with no calibration left, the causes ride under the headline.
    data, target, comps = _plate()
    data = np.minimum(data, 10500.0)
    data[5:8, 5:40] = 10500.0
    plate = _write_plate(tmp_path / "clipped.fits", data)
    dlg.state.load(plate)
    _sequence_static(dlg, comps)
    _click(dlg, *target)
    tab = dlg.tab_measure
    panel = tab.lbl_result.toPlainText()
    assert "no calibration" in panel
    assert "Why:" in panel and "5 saturated/clipped" in panel
    assert "too bright for this plate" in panel
    assert not tab.btn_csv.isEnabled()


def test_overlay_and_pixel_line_follow_the_measured_centroid(dlg):
    _sequence(dlg, dlg._test_comps)
    tx, ty = dlg._test_target
    _click(dlg, tx + 2.5, ty + 1.5)      # deliberately off-centre
    tab = dlg.tab_measure
    assert tab._last["col"] == pytest.approx(tx, abs=0.6)
    assert tab._last["row"] == pytest.approx(ty, abs=0.6)
    assert "centroid landed" in tab.lbl_result.toPlainText()


def test_calibration_in_gaia_g_says_so(dlg):
    _sequence_static(dlg, dlg._test_comps, band="G")
    _click(dlg, *dlg._test_target)
    assert "no Johnson V" in dlg.tab_measure.lbl_result.toPlainText()


def test_assumed_bv_warns_when_the_colour_term_matters(dlg, tmp_path):
    # Six comps with a colour trend (cat = inst + ZP + 0.4 * BV): the
    # fit finds k = 0.4 and the target's B-V is still the assumed 0.00,
    # so the panel must quantify the risk, not just note the value.
    from nightscribe.core import photometry as phot
    data, target, comps = _plate(n_comps=6, seed=7)
    plate = _write_plate(tmp_path / "six.fits", data)
    dlg.state.load(plate)
    entries = []
    for (cx, cy), bv in zip(comps, (0.2, 0.4, 0.6, 0.8, 1.0, 1.2)):
        r = phot.measure_point(dlg.state.data, cx, cy)
        cat = -2.5 * math.log10(r["flux"]) + ZP_TRUE + 0.4 * bv
        ra, dec = dlg.state.wcs.pixel_to_sky(cx, cy)
        entries.append({"name": f"C{len(entries)}", "kind": "comp",
                        "star": {"ra": ra, "dec": dec, "mag": cat,
                                 "band": "V", "catalog": "synthetic",
                                 "bands": [{"label": "V", "value": cat,
                                            "err": 0.01,
                                            "derived": False}],
                                 "bv": bv}})
    dlg.tab_compare._entries = entries
    _click(dlg, *target)
    tab = dlg.tab_measure
    panel = tab.lbl_result.toPlainText()
    assert tab._bv_source == "assumed"
    assert "(assumed)" in panel
    assert "+0.40" in panel and "too bright" in panel


def _real_plate_entries(dlg):
    # The sequence for the real AT2026acka plate: six healthy
    # mid-brightness comps, two comps clipped by the full well and a
    # healthy check. Catalog values are bootstrapped from the plate's
    # own truth scale (27.85), the one the three reported Gaia matches
    # implied to a hundredth; the clipped two carry a dummy value, they
    # are excluded before contributing.
    from nightscribe.core import photometry as phot
    zp_true = 27.85
    healthy = [(539.9, 300.8), (924.2, 438.1), (1732.8, 1741.9),
               (492.9, 1737.0), (657.1, 1311.0), (1185.8, 1038.2)]
    clipped = [(1159.2, 629.8), (1105.8, 1127.2)]
    check_xy = (1050.0, 1591.7)

    def _entry(cx, cy, kind, mag=None):
        r = phot.measure_point(dlg.state.data, cx, cy)
        cat = (-2.5 * math.log10(r["flux"]) + zp_true) if mag is None \
            else mag
        ra, dec = dlg.state.wcs.pixel_to_sky(cx, cy)
        return {"name": kind, "kind": kind,
                "star": {"ra": ra, "dec": dec, "mag": cat, "band": "V",
                         "catalog": "bootstrapped",
                         "bands": [{"label": "V", "value": cat,
                                    "err": 0.01, "derived": False}],
                         "bv": 0.6}}

    entries = [_entry(x, y, "comp") for x, y in healthy]
    entries += [_entry(x, y, "comp", mag=12.0) for x, y in clipped]
    entries.append(_entry(*check_xy, "check"))
    return entries


def test_at2026acka_end_to_end_zp_recovers(dlg):
    # The field report replayed whole: the real AT2026acka plate (10 s,
    # Clear, no SATURATE card), a sequence mixing six healthy
    # mid-brightness comps with two stars that sit at the full well, and
    # the reported target. The clipped comps must be excluded and named,
    # the zero point must recover (~27.85), and the target must land on
    # its Gaia value (16.39).
    tab = dlg.tab_measure
    tab.chk_seeing.setChecked(False)     # default radii: reproducible
    dlg.state.load(FIXTURES / "AT2026acka.fit")
    dlg.tab_compare._entries = _real_plate_entries(dlg)
    _click(dlg, 989.1, 1012.7)
    assert tab._last is not None
    panel = tab.lbl_result.toPlainText()
    assert tab._last["mag"] == pytest.approx(16.39, abs=0.08)
    assert tab._last["zp"]["zp"] == pytest.approx(27.85, abs=0.1)
    assert "2 of 9" in panel and "saturated/clipped" in panel
    assert "clipping level" in panel      # the plain-language warning
    assert "Check star" in panel and "OK" in panel
    assert tab.btn_csv.isEnabled()


def test_at2026acka_sn_centroid_locks_on_the_galaxy(dlg):
    # The SN in its host galaxy at (1039, 1010): faint, on a rising
    # background, a bright star 7 px away. The centroid must lock the
    # faint bump (the plate's seeing anchors the template), not wander
    # to the bright neighbour - the exact 2026-09 field report.
    tab = dlg.tab_measure
    dlg.state.load(FIXTURES / "AT2026acka.fit")
    dlg.tab_compare._entries = _real_plate_entries(dlg)
    _click(dlg, 1039.0, 1010.0)
    assert tab._last is not None
    last = tab._last
    assert last["col"] == pytest.approx(1039.7, abs=1.0)
    assert last["row"] == pytest.approx(1011.5, abs=1.0)
    # the faint bump's flux, not the bright neighbour's (~122k ADU)
    assert last["result"]["flux"] < 60000
    assert "no source could be locked" not in tab.lbl_result.toPlainText()


# ---------------- series plan, phase 5 ----------------

def _wait_series(tab, qapp, timeout=30.0):
    import time
    t0 = time.time()
    while tab._series_worker is not None and time.time() - t0 < timeout:
        qapp.processEvents()
        time.sleep(0.02)
    qapp.processEvents()


def test_series_block_is_hidden_without_a_visit(dlg):
    tab = dlg.tab_measure
    assert not tab.grp_series.isVisible()      # ad-hoc open: no series
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab._on_measure_series()
    assert "No visit" in tab.lbl_status.text()


def test_series_block_shows_with_a_visit_and_runs(dlg, qapp, tmp_path):
    tab = dlg.tab_measure
    rows_seen = {}

    def points_hook(rows, cfg):
        rows_seen["rows"] = rows
        rows_seen["cfg"] = cfg
        return 55

    def undo_hook(run_id):
        rows_seen["undone"] = run_id
        return 4

    frames = []
    for i in range(4):
        frames.append(_write_plate(tmp_path / f"ser{i}.fits",
                                   dlg.state.data))
    entries = _sequence(dlg, dlg._test_comps)
    assert entries
    _click(dlg, *dlg._test_target)              # the series target
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": frames})
    assert tab.grp_series.isVisible()
    dlg.set_points_hook(points_hook)
    dlg.set_run_undo_hook(undo_hook)
    tab._on_measure_series()
    _wait_series(tab, qapp)
    assert tab._series_worker is None
    assert len(rows_seen["rows"]) == 4          # one point per frame
    assert rows_seen["cfg"]["group_n"] == 1
    assert tab._series_run_id == 55
    assert tab.btn_series_undo.isEnabled()
    assert tab.chart_series._points              # the curve is drawn
    # undo touches only this run
    tab._on_series_undo()
    assert rows_seen["undone"] == 55
    assert not tab.btn_series_undo.isEnabled()
    # detaching the visit hides the block again
    dlg.set_series_hook(None)
    assert not tab.grp_series.isVisible()


def test_series_worker_offscreen_measures_a_synthetic_series(qapp, tmp_path):
    from PySide6.QtWidgets import QApplication
    from nightscribe.core import series_measure as sm
    from nightscribe.gui.workers import SeriesWorker
    from nightscribe.core import wcs as wcs_mod
    from nightscribe.core import fits_io
    data, target, comps = _plate()
    plate = _write_plate(tmp_path / "ref.fits", data)
    header, _d = fits_io.read_fits(plate)
    wcs = wcs_mod.Wcs.from_header(header)
    entries = []
    for j, (cx, cy) in enumerate(comps):
        r = __import__("nightscribe.core.photometry", fromlist=["x"]) \
            .measure_point(data, cx, cy)
        import math as _m
        inst = -2.5 * _m.log10(r["flux"])
        ra, dec = wcs.pixel_to_sky(cx, cy)
        entries.append({"name": f"C{j}", "kind": "comp",
                        "star": {"ra": ra, "dec": dec, "band": "V",
                                 "bands": [{"label": "V",
                                            "value": inst + ZP_TRUE,
                                            "err": 0.01, "derived": False}],
                                 "bv": 0.6}})
    paths = [_write_plate(tmp_path / f"w{i}.fits", data) for i in range(3)]
    cfg = sm.SeriesConfig(wcs=wcs, target_xy=target, comp_set=tuple(entries),
                          band="V", site_gain=2.0, site_ron=5.0)
    got = {}
    w = SeriesWorker(paths, cfg)
    w.finished.connect(lambda res: got.update(res=res))
    w.start()
    assert w.wait(30000)
    QApplication.processEvents()
    assert got["res"].status == "complete"
    assert len(got["res"].points) == 3


# ---------------- worker lifecycle on close (P0 stability) ----------------

def _spy_cancel(worker):
    # @return: a list the worker's cancel() appends to; the real cancel
    #          still runs, so the engine really stops
    calls = []
    real = worker.cancel
    worker.cancel = lambda: (calls.append(True), real())[1]
    return calls


def test_dialog_close_cancels_a_running_series(dlg, qapp, tmp_path):
    # Regression (P0): the tab's shutdown() was dead code, nothing called
    # it; closing the editor mid-series cancelled nothing and the worker
    # kept measuring. The closeEvent must shut the Measure tab down:
    # cancel asked, thread waited on and finished, reference dropped.
    tab = dlg.tab_measure
    frames = [_write_plate(tmp_path / f"cl{i}.fits", dlg.state.data)
              for i in range(60)]          # still running at close time
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": frames})
    dlg.set_points_hook(lambda rows, cfg: 77)
    tab._on_measure_series()
    worker = tab._series_worker
    assert worker is not None and worker.isRunning()
    calls = _spy_cancel(worker)
    dlg.close()
    qapp.processEvents()
    cancelled_by_close = bool(calls)
    running_after_close = worker.isRunning()
    # safety net: never hand a live thread to the teardown, whatever the
    # close did or did not do
    worker.cancel()
    finished = worker.wait(10000)
    assert cancelled_by_close              # the close asked it to stop
    assert not running_after_close         # ... and waited for the thread
    assert finished and not worker.isRunning()
    assert tab._series_worker is None      # the reference is dropped


def test_dialog_close_cancels_a_running_live_watch(dlg, qapp, tmp_path):
    # Same regression, Live mode (the reported symptom: a Live watch left
    # behind keeps writing runs into the DB forever). The closeEvent must
    # cancel the live worker too and wait for its thread.
    tab = dlg.tab_measure
    frames = [_write_plate(tmp_path / f"lv{i}.fits", dlg.state.data)
              for i in range(4)]
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": frames})
    dlg.set_points_hook(lambda rows, cfg: 78)
    tab.chk_series_live.setChecked(True)   # starts the folder watch
    worker = tab._live_worker
    assert worker is not None and worker.isRunning()
    calls = _spy_cancel(worker)
    dlg.close()
    qapp.processEvents()
    cancelled_by_close = bool(calls)
    # safety net: the watch loop polls every 2 s, so give the thread a
    # generous window; the teardown must never see it running
    worker.cancel()
    finished = worker.wait(10000)
    assert cancelled_by_close              # the close asked it to stop
    assert finished and not worker.isRunning()
    assert tab._live_worker is None        # the reference is dropped


# ---------------- the run button doubles as Cancel (P1 #12) ----------------

def test_series_button_cancels_a_running_series(dlg, qapp, tmp_path):
    # Regression (P1 #12): a long series had no way out, the button was
    # disabled while the worker ran. The same button must become the
    # Cancel: one click mid-run asks the worker to stop, the engine
    # answers "incomplete" with the points measured so far (D18: they are
    # kept as one undoable run) and the button comes back to its label.
    import time
    tab = dlg.tab_measure
    label = tab.btn_series.text()              # the .ui's run label
    rows_seen = []
    echo_seen = []

    def points_hook(rows, cfg):
        rows_seen.append(rows)
        echo_seen.append(cfg)
        return 91

    frames = [_write_plate(tmp_path / f"cn{i}.fits", dlg.state.data)
              for i in range(60)]          # still running at click time
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": frames})
    dlg.set_points_hook(points_hook)
    tab._on_measure_series()
    worker = tab._series_worker
    assert worker is not None and worker.isRunning()
    assert tab.btn_series.text() == tab.tr("Cancel")   # it IS the Cancel
    assert tab.btn_series.isEnabled()                  # ... and clickable
    # mid-run: a few frames are already measured when the click lands
    t0 = time.time()
    while tab.prg_series.value() < 3 and time.time() - t0 < 30.0:
        qapp.processEvents()
        time.sleep(0.01)
    assert tab.prg_series.value() >= 3
    calls = _spy_cancel(worker)
    tab.btn_series.click()                     # one click, mid-run
    assert calls                               # the worker was asked to stop
    assert "Cancelling" in tab.lbl_status.text()
    _wait_series(tab, qapp)
    assert tab._series_worker is None
    result = tab._series_result
    assert result.status == "incomplete"       # cancelled, not lost (D18)
    assert 0 < len(result.points) < len(frames)
    # the points measured so far are kept: one run, persisted and undoable
    kept = [p for p in result.points if p.mjd is not None]
    assert kept and rows_seen and len(rows_seen[0]) == len(kept)
    # P2 #23a (D18): the run's real status rides in the echo, so the host
    # stores the run "incomplete" instead of the column's "complete"
    assert echo_seen and echo_seen[0]["status"] == "incomplete"
    assert echo_seen[0]["group_n"] == 1          # the config echo survives
    assert tab._series_run_id == 91
    assert tab.btn_series_undo.isEnabled()
    # and the button is the run button again
    assert tab.btn_series.text() == label
    assert tab.btn_series.isEnabled()
    assert "Series cancelled" in tab.lbl_status.text()


# ---------------- series plan, phase 8: ExoClock ----------------

def test_exoclock_button_writes_files_and_records_outcome(
        dlg, qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from PySide6.QtGui import QDesktopServices
    tab = dlg.tab_measure
    assert not tab.btn_series_exoclock.isEnabled()   # nothing measured yet
    frames = [_write_plate(tmp_path / f"e{i}.fits", dlg.state.data,
                           extra=[_card("EXPTIME", "10.0")])
              for i in range(4)]
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": frames})
    dlg.set_points_hook(lambda rows, cfg: 9)
    tab._on_measure_series()
    _wait_series(tab, qapp)
    assert tab.btn_series_exoclock.isEnabled()
    out = tmp_path / "HATP-32b.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(lambda url: opened.append(url.toString())))
    seen = []
    dlg.set_exoclock_hook(lambda payload: seen.append(payload))
    tab._on_series_exoclock()
    assert out.exists()
    assert (tmp_path / "ExoClock_info.txt").exists()
    assert "JD_UTC" in (tmp_path / "ExoClock_info.txt").read_text()
    assert len(out.read_text().strip().splitlines()) == 4   # one per frame
    assert opened and "exoclock.space/upload" in opened[0]
    assert seen and seen[0]["points"] == 4


# ------- P2 #19: live batches say their failures, and undo -------

def _fast_live(monkeypatch):
    # The tab builds its live worker with the watch's real 2 s poll; an
    # offscreen test cannot wait for it, so the class it imports polls
    # fast instead (same worker, same signals).
    # @return: the replacement class (also patched into gui.workers)
    from nightscribe.gui import workers

    class _FastLive(workers.LiveSeriesWorker):
        def __init__(self, folder, cfg, batch_n=5, batch_s=10.0):
            super().__init__(folder, cfg, poll_s=0.05, batch_n=batch_n,
                             batch_s=batch_s)

    monkeypatch.setattr(workers, "LiveSeriesWorker", _FastLive)
    return _FastLive


def _stop_live(tab):
    # The fixture never closes the dialog, so the test itself must not
    # hand a running thread to the teardown.
    # @return: the live worker, cancelled and waited on
    worker = tab._live_worker
    tab.chk_series_live.setChecked(False)
    if worker is not None:
        worker.cancel()
        assert worker.wait(20000)
    return worker


def _wait_live_runs(tab, qapp, n, timeout=30.0):
    import time
    t0 = time.time()
    while len(tab._live_run_ids) < n and time.time() - t0 < timeout:
        qapp.processEvents()
        time.sleep(0.02)
    qapp.processEvents()


def _arm_live(dlg, tmp_path, prefix, n=3):
    # A visit with frames in tmp_path, a sequence and a measured target:
    # everything Live mode asks for before it starts watching.
    # @return: the visit's frame paths
    frames = [_write_plate(tmp_path / f"{prefix}{i}.fits", dlg.state.data)
              for i in range(n)]
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": frames})
    return frames


def test_live_batch_failure_reaches_the_status_line(
        dlg, qapp, tmp_path, monkeypatch):
    # Regression (P2 #19): a batch whose measure raised was logged and
    # dropped, and the tab said nothing at all. The observer must read
    # that those frames were not measured, in their own language.
    import time
    from nightscribe.core import series_measure as sm
    tab = dlg.tab_measure
    _arm_live(dlg, tmp_path, "lf")
    dlg.set_points_hook(lambda rows, cfg: 78)

    def boom(paths, cfg, progress=None, cancel=None):
        raise RuntimeError("engine down")

    monkeypatch.setattr(sm, "measure_series", boom)
    _fast_live(monkeypatch)
    tab.chk_series_live.setChecked(True)
    t0 = time.time()
    while "engine down" not in tab.lbl_status.text() \
            and time.time() - t0 < 20.0:
        qapp.processEvents()
        time.sleep(0.02)
    text = tab.lbl_status.text()
    _stop_live(tab)
    assert "engine down" in text
    assert "were not measured" in text          # the tab's own wording
    assert tab._live_run_ids == []              # nothing was persisted


def test_live_session_is_one_undoable_run(dlg, qapp, tmp_path, monkeypatch):
    # Regression (P2 #19 / ADR-050): the live batches were written and
    # their run ids thrown away, so a live session could never be undone.
    # Its batches pile up behind the same Undo button as a normal series.
    #
    # And since 2026-09-30 they pile up in ONE run, not one per batch: the
    # tab tells the host to continue the run its session opened
    # (`append_run`), which is what makes the curve reloaded from the
    # project the WHOLE live session instead of its last batch.
    tab = dlg.tab_measure
    undone = []
    echoes = []
    _arm_live(dlg, tmp_path, "lu")

    def fake_points(rows, cfg):
        echoes.append(dict(cfg))
        return 79

    dlg.set_points_hook(fake_points)
    dlg.set_run_undo_hook(lambda run_id: (undone.append(run_id), 2)[1])
    _fast_live(monkeypatch)
    tab.chk_series_live.setChecked(True)
    _wait_live_runs(tab, qapp, 1)
    # a second wave: the session keeps piling its batches into one run
    for i in (3, 4):
        _write_plate(tmp_path / f"lu{i}.fits", dlg.state.data)
    _wait_live_runs(tab, qapp, 2)
    _stop_live(tab)
    ids = list(tab._live_run_ids)
    assert ids == [79]                        # one run, whatever the batches
    assert "append_run" not in echoes[0]      # the first batch opened it
    assert all(e.get("append_run") == 79 for e in echoes[1:])
    assert tab.btn_series_undo.isEnabled()
    assert tab._live_points                    # the curve grew live
    tab._on_series_undo()
    assert undone == ids                       # every batch, one click
    assert "Run undone" in tab.lbl_status.text()
    assert not tab.btn_series_undo.isEnabled()
    assert tab._live_run_ids == [] and tab._live_points == []
    assert tab.chart_series._points == []


# ---------------- P2 #20: the aperture sweep is reachable ----------------

def test_auto_aperture_checkbox_hands_the_radii_to_the_engine(
        dlg, qapp, tmp_path, monkeypatch):
    # Regression (P2 #20): the tab always passed its spins as radii, so
    # the engine's auto path (radii None) never ran even with the box
    # checked. Checked, the engine owns the apertures and its chosen k per
    # night reaches the panel; unchecked, the spins still rule.
    from nightscribe.core import series_measure as sm
    tab = dlg.tab_measure
    seen = []

    def fake(paths, cfg, progress=None, cancel=None):
        seen.append(cfg)
        return sm.SeriesResult(
            points=[sm.SeriesPoint(index=0, path=str(paths[0]),
                                   mjd=60900.5, mag=15.0, err=0.01,
                                   inst=14.0, filter="V")],
            apertures={"2026-09-20": {"k": 1.4, "rms": 0.0123,
                                      "radii": (5.4, 9.0, 13.0),
                                      "fwhm": 3.2}})

    monkeypatch.setattr(sm, "measure_series", fake)
    frames = [_write_plate(tmp_path / f"ap{i}.fits", dlg.state.data)
              for i in range(2)]
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": frames})
    dlg.set_points_hook(lambda rows, cfg: 31)
    tab._advanced.chk_auto_aperture.setChecked(True)
    tab._on_measure_series()
    _wait_series(tab, qapp)
    assert seen and seen[0].radii is None       # the sweep can run now
    assert seen[0].auto_aperture is True
    panel = tab.lbl_result.toPlainText()
    assert "Night 2026-09-20: aperture k = 1.4" in panel
    assert "seeing 3.2 px" in panel and "0.0123" in panel
    # unchecked: the observer's spins are never stomped
    tab._advanced.chk_auto_aperture.setChecked(False)
    tab._on_measure_series()
    _wait_series(tab, qapp)
    assert seen[-1].auto_aperture is False
    assert seen[-1].radii == (tab.spn_rap.value(), tab.spn_rin.value(),
                              tab.spn_rout.value())


# ---------------- P2 #22: nothing drops without a word ----------------

def test_series_panel_names_the_frames_that_never_made_it(dlg, qapp, tmp_path):
    # Regression (P2 #22): frames without DATE-OBS and frames the engine
    # could not read were discarded in silence. The panel must name them.
    tab = dlg.tab_measure
    good = _write_plate(tmp_path / "ok0.fits", dlg.state.data)
    nodate = _write_plate(tmp_path / "nodate0.fits", dlg.state.data,
                          instrument=False)
    broken = tmp_path / "broken0.fits"
    broken.write_text("this is not a FITS file")
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": [good, nodate, broken]})
    rows_seen = []
    dlg.set_points_hook(lambda rows, cfg: (rows_seen.append(rows), 21)[1])
    tab._on_measure_series()
    _wait_series(tab, qapp)
    panel = tab.lbl_result.toPlainText()
    assert "1 frame(s) had no DATE-OBS" in panel
    assert "1 frame(s) could not be read" in panel
    assert "broken0.fits" in panel
    # the technical English of the engine is said in plain language
    assert "truncated" in panel
    assert "Truncated FITS header block" not in panel
    # and the undated frame really stayed off the persisted run
    assert rows_seen and all(r["mjd"] is not None for r in rows_seen[0])
    assert len(rows_seen[0]) == 1


# ---------------- P2 #23b: the ExoClock write is guarded ----------------

def test_exoclock_write_failure_is_reported(dlg, qapp, tmp_path, monkeypatch):
    # Regression (P2 #23b): write_submission raises on a locked file, a
    # full disk or a folder without write permission, and the tab let the
    # exception escape. It must say why and stop there.
    from PySide6.QtWidgets import QFileDialog
    from PySide6.QtGui import QDesktopServices
    from nightscribe.core import exoclock_export
    tab = dlg.tab_measure
    frames = [_write_plate(tmp_path / f"xf{i}.fits", dlg.state.data,
                           extra=[_card("EXPTIME", "10.0")])
              for i in range(2)]
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": frames})
    dlg.set_points_hook(lambda rows, cfg: 9)
    tab._on_measure_series()
    _wait_series(tab, qapp)
    assert tab.btn_series_exoclock.isEnabled()
    out = tmp_path / "locked.txt"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl",
                        staticmethod(
                            lambda url: opened.append(url.toString())))
    saved = []
    dlg.set_save_hook(lambda paths, kind, payload: saved.append(paths))
    exo_seen = []
    dlg.set_exoclock_hook(lambda payload: exo_seen.append(payload))

    def boom(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(exoclock_export, "write_submission", boom)
    tab._on_series_exoclock()                  # must not raise
    text = tab.lbl_status.text()
    assert "could not be written" in text
    assert "Permission denied" in text
    assert opened == []                        # the upload page stays shut
    assert saved == [] and exo_seen == []      # nothing is registered
    assert not out.exists()


# ---------------- P3: the series buttons on wide fonts ----------------

def test_the_series_block_stays_narrow_and_keeps_its_actions_reachable(
        dlg, qapp):
    # Regression (P3) plus U6. P3 was about the four series buttons on one
    # row escaping the dialog on Windows, where the fonts are wide. U6 has
    # changed where they live: the block keeps ONE action (Measure/Cancel)
    # and the six occasional ones moved into the "Series" menu, so the row
    # cannot be dragged wide by them any more.
    #
    # What must hold now: the block stays narrow with a 1.5x font, and the
    # six actions are still THERE, reachable behind their door.
    tab = dlg.tab_measure
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2, "paths": []})
    assert tab.grp_series.isVisible()          # the block is armed
    # the theme pins the font size in px through a stylesheet, so the
    # 1.5x simulation goes through the same channel: 13px -> 20px
    tab.grp_series.setStyleSheet("* { font-size: 20px; }")
    qapp.processEvents()
    assert tab.btn_series.font().pixelSize() == 20
    assert _innermost_row_of(tab.grp_series, tab.btn_series) is not None
    # the block's own width stays sane: the six moved ones cannot add to it
    assert tab.grp_series.minimumSizeHint().width() <= 560
    # and the door holds them all, one item per button (not a dead list)
    names = [a.data() for a in tab.btn_series_more.menu().actions()]
    for name in ("btn_series_undo", "btn_series_exoclock",
                 "btn_series_night", "btn_series_sci", "btn_series_phase",
                 "btn_series_help"):
        assert name in names, name


# ---------------- P3: nights are named by their civil date ----------------

def test_series_panel_names_nights_by_their_civil_date(
        dlg, qapp, tmp_path, monkeypatch):
    # Regression (P3): the per-night lines printed the engine's raw MJD
    # night key ("Night 61303"), which no observer reads. The night
    # boundary sits at noon (ADR-048), so the panel says the civil date
    # of the evening, in the aperture-sweep and the detrend lines alike.
    from nightscribe.core import series_measure as sm
    tab = dlg.tab_measure

    def fake(paths, cfg, progress=None, cancel=None):
        return sm.SeriesResult(
            points=[sm.SeriesPoint(index=0, path=str(paths[0]),
                                   mjd=61303.98, mag=15.0, err=0.01,
                                   inst=14.0, filter="V", airmass=1.2)],
            apertures={61303: {"k": 1.4, "rms": 0.0123,
                               "radii": (5.4, 9.0, 13.0), "fwhm": 3.2}},
            detrend={"policy": "airmass",
                     "nights": [{"night": 61303, "a1": 1.0, "a2": 0.1,
                                 "a3": 0.0, "n": 1, "fallback": None,
                                 "rms_before": 0.02, "rms_after": 0.01}]})

    monkeypatch.setattr(sm, "measure_series", fake)
    frames = [_write_plate(tmp_path / f"nd{i}.fits", dlg.state.data)
              for i in range(2)]
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": frames})
    dlg.set_points_hook(lambda rows, cfg: 41)
    tab._on_measure_series()
    _wait_series(tab, qapp)
    panel = tab.lbl_result.toPlainText()
    assert "Night 2026-09-20: aperture k = 1.4" in panel
    assert "Night 2026-09-20: a1=1.000, a2=+0.100, a3=0.000" in panel
    assert "Night 61303" not in panel           # the raw MJD is gone


def test_series_lives_in_a_left_pane_shown_with_a_visit(dlg):
    # The series block sits in its own pane at the left of the image
    # (hidden unless a visit arms it), not cramped in the Measure tab.
    tab = dlg.tab_measure
    assert hasattr(dlg, "series_pane")
    assert not dlg.series_pane.isVisible()
    # the group is reparented into the pane
    assert tab.grp_series.parent() is dlg.visit_panel
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2, "paths": []})
    assert dlg.series_pane.isVisible()
    assert tab.grp_series.isVisible()
    dlg.set_series_hook(None)
    assert not dlg.series_pane.isVisible()


# ------------------------------------- the curve in the centre (ADR-051 rev.)

def test_the_curve_lives_in_the_centre_of_the_window(dlg):
    # V2: the measured curve is not a small box you have to click, nor a
    # second copy in another window: it is the other page of the centre,
    # beside the image, and it is the SAME chart the tab measures into.
    tab = dlg.tab_measure
    stack = dlg.stack_centre
    assert stack.count() == 2
    assert dlg.view is stack.widget(0).layout().itemAt(0).widget()
    assert tab.chart_series is stack.widget(1).layout().itemAt(0).widget()
    # the switch drives the pages
    dlg.show_curve()
    assert stack.currentIndex() == 1
    assert dlg.btn_page_curve.isChecked()
    dlg.show_image()
    assert stack.currentIndex() == 0
    assert dlg.btn_page_image.isChecked()


def test_a_click_on_the_curve_brings_it_to_the_front(dlg):
    # "Show me this properly" now means the centre's curve page: no second
    # copy in another window to disagree with it (V2).
    import nightscribe.gui.chart_viewer as cv
    seen = []
    orig = cv.open_chart_widget
    cv.open_chart_widget = lambda *a, **k: seen.append(1)
    try:
        tab = dlg.tab_measure
        dlg.show_image()
        tab._series_payload = [{"mjd": 1.0, "mag": 12.0, "err": 0.05,
                                "filter": "V", "source": "measure",
                                "flags": []}]
        tab.chart_series.enlarge_requested.emit()
        assert dlg.stack_centre.currentIndex() == 1
        assert seen == []           # no window, ever
    finally:
        cv.open_chart_widget = orig


def test_the_curve_page_does_not_open_without_data(dlg):
    dlg.show_image()
    dlg.tab_measure._series_payload = []
    dlg.tab_measure.chart_series.enlarge_requested.emit()
    assert dlg.stack_centre.currentIndex() == 0


def test_lightcurve_double_click_asks_for_the_big_view(dlg):
    from PySide6.QtCore import Qt
    seen = []
    dlg.tab_measure.chart_series.enlarge_requested.connect(
        lambda: seen.append(1))

    class _Ev:
        def button(self):
            return Qt.LeftButton

        def accept(self):
            pass

    dlg.tab_measure.chart_series.mouseDoubleClickEvent(_Ev())
    assert seen == [1]


def test_group_frames_quick_mirrors_advanced(dlg):
    # the series block's quick knob and the Advanced… one are the same
    # value in two places
    tab = dlg.tab_measure
    tab.spn_group_quick.setValue(5)
    assert tab._advanced.spn_group_n.value() == 5
    tab._advanced.spn_group_n.setValue(3)
    assert tab.spn_group_quick.value() == 3


def test_a_plain_click_on_the_curve_does_not_hide_the_image(dlg):
    # A click on a point selects it; on the empty space it brings the curve
    # to the front, which is where it already is when you are looking at it.
    # What it must never do is open a second copy or move the page: the
    # observer's place is not to be taken away by a click.
    from PySide6.QtCore import QPointF
    tab = dlg.tab_measure
    tab._series_payload = [{"mjd": 1.0, "mag": 12.0, "err": 0.05,
                            "filter": "V", "source": "measure",
                            "flags": []}]
    dlg.show_curve()
    tab.chart_series.scene_clicked.emit(QPointF(0.0, 0.0))
    assert dlg.stack_centre.currentIndex() == 1


def test_a_failed_series_does_not_leave_the_tab_looking_hung(dlg):
    # What the observer actually saw: a 142-frame run died at frame ~18 and
    # the tab kept the progress bar frozen there, which reads as a hang.
    # The failure was real and had a reason (a comparison star off the
    # frame); the UI must say so and put itself back.
    tab = dlg.tab_measure
    tab.prg_series.setRange(0, 142)
    tab.prg_series.setValue(18)
    tab._on_series_failed("negative dimensions are not allowed")
    assert tab.prg_series.value() == 0            # not frozen at 13 %
    assert tab.btn_series.text() == tab._btn_series_label   # not "Cancel"
    assert tab._series_worker is None
    assert "negative dimensions" in tab.lbl_status.text()


# ---------------- the panel follows the chart (issue report) ----------

def test_the_panel_always_describes_the_chart_on_screen(dlg, qapp):
    # Reported: "if I mark outliers the messages stack on the chart and do
    # not update". The chart does not accumulate anything (it rebuilds its
    # scene), but the PANEL was written once per run: marking outliers, or
    # hiding the flagged points, left it describing a chart that was no
    # longer there. It is rebuilt now — summary plus the chart's own notes —
    # on every change, and a full rewrite cannot accumulate.
    tab = dlg.tab_measure
    tab._panel_summary = ["Serie: 3 puntos"]
    tab.chart_series.set_data([
        {"mjd": 60600.0, "mag": 12.34, "err": 0.01, "err_internal": 0.008,
         "filter": "V", "source": "measure", "flags": ["cosmic"]},
        {"mjd": 60601.0, "mag": 12.36, "err": 0.01, "err_internal": 0.008,
         "filter": "V", "source": "measure", "flags": []}])
    tab._render_panel()
    before = tab.lbl_result.toPlainText()
    assert "Serie: 3 puntos" in before
    # hiding the flagged points changes what the chart does: the panel must
    # say it WITHOUT a new run
    tab.btn_series_hideflags.setChecked(True)
    qapp.processEvents()
    after = tab.lbl_result.toPlainText()
    assert after != before
    assert "Serie: 3 puntos" in after            # the summary is not lost
    assert after.count("Serie: 3 puntos") == 1   # and it never stacks
    tab.btn_series_hideflags.setChecked(False)
    qapp.processEvents()
    assert "Serie: 3 puntos" in tab.lbl_result.toPlainText()


def test_the_result_box_has_room_and_a_scrollbar(dlg):
    # Reported twice: the "Photometric series" messages needed more height
    # and a scrollbar "just in case". The summary of a night with four
    # flags, a per-night detrend and two warnings is LONG, and with wide
    # system fonts the box was cramped (the observer asked for more height
    # again: 150 -> 240 px).
    from PySide6.QtCore import Qt
    box = dlg.tab_measure.lbl_result
    assert box.minimumHeight() >= 240
    assert box.verticalScrollBarPolicy() != Qt.ScrollBarAlwaysOff
    assert box.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert box.isReadOnly()


# ---------------- D: the visit's curve is not regenerated ------------

def _visit_points(n=5):
    return [{"mjd": 60600.0 + 0.01 * i, "mag": 12.34 + 0.004 * i,
             "err": 0.01, "err_internal": 0.008, "mag_raw": -9.5,
             "filter": "V", "flags": [], "source": "measure"}
            for i in range(n)]


def test_the_visit_s_curve_is_drawn_without_measuring_anything(dlg):
    # The observer's ask: a light curve that was generated must not have to
    # be generated again. Opening the visit draws what the project already
    # has, read from the database: no frame is touched.
    tab = dlg.tab_measure
    tab.set_visit_curve_hooks(lambda: _visit_points(5), None)
    assert len(tab.chart_series._points) == 5
    assert tab._curve_from_visit is True
    assert "curve" in tab.lbl_result.toPlainText().lower()
    assert "5" in tab.lbl_status.text()
    # the curve is on the chart, not measured: nothing claims a run
    assert tab._series_result is None


def test_measuring_again_replaces_the_visit_s_curve(dlg):
    # The loaded curve is a starting point, not a lock: a real run replaces
    # it (and the panel goes back to describing the run).
    tab = dlg.tab_measure
    tab.set_visit_curve_hooks(lambda: _visit_points(5), None)
    assert tab._curve_from_visit
    tab._series_result = object()          # a run landed
    assert tab.load_visit_curve() == 0     # the visit's copy is not redrawn
    tab._series_result = None


def test_discarding_the_visit_s_curve_clears_it_and_says_what_it_did(dlg,
                                                                    monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    tab = dlg.tab_measure
    calls = []
    tab.set_visit_curve_hooks(
        lambda: _visit_points(4),
        lambda: (calls.append(True), (2, 4))[1])
    assert tab.chart_series._points
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.Yes))
    tab._on_discard_curve()
    assert calls == [True]                 # the project undid the runs
    assert tab.chart_series._points == []  # the chart starts from scratch
    assert tab._curve_from_visit is False
    assert "2" in tab.lbl_status.text() and "4" in tab.lbl_status.text()


def test_discarding_asks_first_and_a_no_is_a_no(dlg, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    tab = dlg.tab_measure
    removed = []
    tab.set_visit_curve_hooks(lambda: _visit_points(3),
                              lambda: (removed.append(True), (1, 3))[1])
    monkeypatch.setattr(QMessageBox, "question",
                        staticmethod(lambda *a, **k: QMessageBox.No))
    tab._on_discard_curve()
    assert removed == []                   # nothing was touched
    assert tab.chart_series._points       # and the curve is still there


def test_a_visit_without_points_opens_with_an_empty_chart(dlg):
    tab = dlg.tab_measure
    tab.set_visit_curve_hooks(lambda: [], None)
    assert tab.chart_series._points == []
    assert tab._curve_from_visit is False


def test_the_trend_is_on_by_default(dlg):
    # The observer's ask: the trend is the first thing to read on a curve.
    # It comes on (window 5) and the raw points stay on the chart: nothing
    # is hidden, and the panel's notes say the line is a guide.
    tab = dlg.tab_measure
    assert tab.chk_series_mean.isChecked()
    assert tab.spn_series_meanwin.value() == 5


# ---------------- the series doors, and the trend that was ticked ------

def test_every_button_of_the_row_lands_in_the_series_menu(dlg, qapp):
    # Reported: the "discard the visit's curve" button came out broken and
    # totally out of place. The panel moves the row's buttons into the
    # "Series" menu from a list of NAMES, and the new button was not on the
    # list: it stayed inside the row while the row itself was removed from
    # the panel, so it had no layout to place it. The row is read now, not
    # guessed, so a button added to the Designer file cannot be orphaned:
    # this test reads the .ui itself, which is where the row is defined.
    import re
    import xml.etree.ElementTree as ET
    from pathlib import Path
    from PySide6.QtWidgets import QPushButton
    ui = Path(__file__).parents[2] / "nightscribe" / "gui" / "ui" \
        / "ufe_measure_tab.ui"
    text = ui.read_text(encoding="utf-8")
    row = re.search(r'<layout class="QHBoxLayout" name="row_series_out">'
                    r'(.*?)</layout>', text, re.S)
    from_row = re.findall(r'name="(btn_[\w]+)"', row.group(1))
    assert from_row, "la fila del Designer tenía botones"
    tab = dlg.tab_measure
    names = [a.data() for a in tab.btn_series_more.menu().actions()]
    for name in from_row:
        assert name in names, name
    assert "btn_series_discard" in names           # the one that was lost
    assert "btn_series_undo" in names              # the one from the run row
    # and the door holds exactly those, nothing more and nothing less: the
    # invariant is about which button each item drives
    assert set(names) == set(from_row) | {"btn_series_undo"}
    # and none of them can reach the screen: the row that held them is gone
    # (Qt deletes a layout removed from its parent) and they sit in the door's
    # hidden holder, inside the block's subtree but out of every layout that
    # shows. This is the reported bug: one came out floating over the window
    # and read as a duplicate (2026-10-01).
    for name in from_row:
        btn = getattr(tab._ui, name, None) or getattr(tab, name, None)
        if btn is not None:
            assert not btn.isVisible(), name


def test_the_trend_is_painted_when_the_curve_is_generated(dlg, qapp):
    # Reported: "the mean is ticked but it is not painted when the curve is
    # generated". The controls are wired to their slots, but a slot only
    # fires when the control CHANGES: their initial state was never pushed,
    # so a fresh series came out with no trend, no errors and no binning.
    tab = dlg.tab_measure
    assert tab.chk_series_mean.isChecked()           # on by default
    tab._series_result = None
    tab._series_payload = list(_visit_points(12))
    tab._draw_series(tab._series_result.points if tab._series_result else
                     [])
    # with a payload, drawing it must leave the chart saying what the
    # controls say
    tab._series_payload = list(_visit_points(12))
    tab.chart_series.set_data(tab._series_payload)
    tab._apply_chart_presentation()
    assert tab.chart_series._mean_window == tab.spn_series_meanwin.value()
    assert tab.chart_series._mean_window >= 2


# ---------------- U5: the doors and what is inside them ---------------

def test_the_export_door_follows_the_measurement(dlg):
    # A door that opens onto two grey buttons is a lie, and one that stays
    # lit with nothing to export is a trap: the door and its two contents
    # are switched by ONE place, so they cannot drift apart.
    tab = dlg.tab_measure
    assert not tab.btn_export_more.isEnabled()      # nothing measured yet
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    assert tab.btn_export_more.isEnabled()
    assert tab.btn_csv.isEnabled() and tab.btn_eff.isEnabled()
    # a plate with no target measured takes it back
    dlg.state.load(dlg.state.path)
    assert not tab.btn_export_more.isEnabled()
    assert not tab.btn_csv.isEnabled()


def test_the_buttons_inside_the_doors_still_do_what_they_did(dlg, tmp_path,
                                                              monkeypatch):
    # The doors are a move, not a rewrite: clicking the CSV inside the
    # "Export" panel writes the same file the old button wrote, and the
    # reset inside "Reset" reaches the same handler.
    from PySide6.QtWidgets import QFileDialog
    tab = dlg.tab_measure
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    out = tmp_path / "medida.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    # the "Export" door's CSV item drives the button that writes the file,
    # and the items of "Reset" reach the same handlers
    acts = {a.data(): a for a in tab.btn_export_more.menu().actions()}
    acts["btn_csv"].trigger()
    assert out.exists() and out.read_text().count("\n") >= 3
    seen = []
    monkeypatch.setattr(tab, "_on_reset_state",
                        lambda: seen.append("state"))
    monkeypatch.setattr(tab, "_on_reset_points",
                        lambda: seen.append("points"))
    resets = {a.data(): a for a in tab.btn_reset_more.menu().actions()}
    resets["btn_reset_state"].trigger()
    resets["btn_reset_points"].trigger()
    assert seen == ["state", "points"]


# ---------------- the chart's PNG exports (reported) ------------------

def test_the_visit_s_curve_can_be_exported_as_a_png(dlg, tmp_path,
                                                    monkeypatch):
    # Reported: "the PNG export of the chart does not work, the save dialog
    # does not even appear". A curve loaded from the visit has no run of this
    # session behind it, and the export demanded one: it returned BEFORE
    # opening the dialog. The button saves the chart IN THE VISIT, which is
    # exactly the curve on screen.
    from PySide6.QtWidgets import QFileDialog
    tab = dlg.tab_measure
    tab.set_visit_curve_hooks(lambda: _visit_points(6), None)
    assert tab._series_result is None and tab._series_payload
    out = tmp_path / "curva.png"
    asked = []
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        staticmethod(lambda *a, **k: (asked.append(True), (str(out), ""))[1]))
    tab._on_series_sci()
    assert asked                              # the dialog was reached
    assert out.exists() and out.stat().st_size > 0
    assert "written" in tab.lbl_status.text().lower()


def test_the_night_figures_use_what_the_visit_s_curve_carries(
        dlg, tmp_path, monkeypatch):
    # The airmass and the measured position travel with the point now, so a
    # curve read back from the database draws its own night without
    # measuring anything again.
    from nightscribe.viz import night_view
    tab = dlg.tab_measure
    points = [dict(p, airmass=1.2 + 0.01 * i, x=800.0 + i, y=600.0 + i)
              for i, p in enumerate(_visit_points(6))]
    tab.set_visit_curve_hooks(lambda: points, None)
    written = []
    monkeypatch.setattr(
        night_view, "draw_airmass",
        lambda pts, out=None, **k: (written.append("air"), out)[1])
    monkeypatch.setattr(
        night_view, "draw_drift",
        lambda pts, out=None, **k: (written.append("drift"), out)[1])
    monkeypatch.setattr("nightscribe.gui.chart_viewer.open_chart",
                        lambda *a, **k: None)
    tab._on_series_night()
    assert written == ["air", "drift"]
    assert "Night figures written" in tab.lbl_status.text()


def test_the_night_figures_say_what_an_old_curve_cannot_give(dlg,
                                                             monkeypatch):
    # A curve measured before the app stored them carries neither the
    # airmass nor the position: the button says it instead of going quiet.
    from nightscribe.viz import night_view
    tab = dlg.tab_measure
    tab.set_visit_curve_hooks(lambda: _visit_points(4), None)
    called = []
    monkeypatch.setattr(night_view, "draw_airmass",
                        lambda *a, **k: called.append("air"))
    monkeypatch.setattr(night_view, "draw_drift",
                        lambda *a, **k: called.append("drift"))
    tab._on_series_night()
    assert called == []
    assert "neither the airmass nor the measured position" \
        in tab.lbl_status.text()


# ---------------- the band's magnitude comes from the curve -----------

def test_the_band_takes_the_measured_point_of_this_frame(dlg):
    # Reported: "the colour code for the photometric measurements in the top
    # band is not being respected". Part of it was this: with a series
    # measured (the normal flow) the band kept showing the CATALOGUE
    # magnitude, in white, because it only read a single-plate measurement.
    # The point of the curve IS the measurement of this plate.
    tab = dlg.tab_measure
    frame = str(dlg.state.path)
    tab._series_payload = [
        {"mjd": 60000.0, "mag": 12.0, "err": 0.3, "filter": "V",
         "source": "measure", "path": "/otra/toma.fit", "comps": 5,
         "flags": []},
        {"mjd": 60001.0, "mag": 12.44, "err": 0.04, "filter": "V",
         "source": "measure", "path": frame, "comps": 5, "flags": []}]
    point = tab.series_point_for(frame)
    assert point and point["mag"] == 12.44        # the one of THIS frame
    # by time when the curve carries no paths (loaded from the database)
    tab._series_payload = [{"mjd": 60001.0, "mag": 12.5, "err": 0.03,
                            "filter": "V", "source": "measure",
                            "comps": 4, "flags": []}]
    assert tab.series_point_for(None, 60001.0, 40.0)["mag"] == 12.5
    assert tab.series_point_for(None, 60005.0, 40.0) is None
    # the detrended twin of a point is not "the measured magnitude"
    tab._series_payload = [{"mjd": 60001.0, "mag": 12.5, "err": 0.03,
                            "filter": "V", "source": "detrend",
                            "comps": 4, "flags": []}]
    assert tab.series_point_for(None, 60001.0, 40.0) is None


def test_every_control_that_affects_the_measurement_measures_again(
        dlg, monkeypatch):
    # Reported: "if I measure again, changing the band for instance, the
    # magnitude does not update". THREE controls were not wired (the band,
    # the saturation ceiling and the sequence), and that is how such a thing
    # appears: silently. This walks EVERY control that is part of the recipe,
    # changes it and demands the measurement to run again, so a new knob
    # cannot be left out without a red test.
    from nightscribe.core import photometry as phot
    tab = dlg.tab_measure
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    assert tab._last is not None
    runs = []
    real = phot.measure_plate

    def spy(*a, **k):
        runs.append(True)
        return real(*a, **k)
    monkeypatch.setattr(phot, "measure_plate", spy)

    def changed(label, act):
        runs.clear()
        act()
        assert runs, label

    if tab.cmb_band.count() < 2:
        tab.cmb_band.addItem("R")
    changed("band", lambda: tab.cmb_band.setCurrentIndex(1))
    changed("aperture", lambda: tab.spn_rap.setValue(
        tab.spn_rap.value() + 1.0))
    changed("sky model", lambda: tab.cmb_sky.setCurrentIndex(
        0 if tab.cmb_sky.currentIndex() else 1))
    changed("sigma clip", tab.chk_sigmaclip.toggle)
    changed("colour term", tab.chk_color.toggle)
    changed("target B-V", lambda: tab.spn_target_bv.setValue(0.75))
    changed("saturation ceiling", lambda: tab.spn_saturate.setValue(100000.0))

    def edit_the_sequence():
        # a real edit (the kind of a comp): it leaves the zero point. The
        # table is filled from the sequence first, because the helper above
        # sets the entries directly
        compare = dlg.tab_compare
        compare._reload_table()
        combo = compare.table.cellWidget(0, 1)
        combo.setCurrentIndex(1 if combo.currentIndex() == 0 else 0)
    changed("the sequence", edit_the_sequence)
    changed("another click on the plate", lambda: _click(
        dlg, *dlg._test_target))


def test_the_panel_paints_the_magnitude_with_the_colour_code(dlg):
    # The colour code is not only the plate's band: the measurement's panel
    # wears it too, from the same rule and the same palette, so the two
    # cannot disagree about what the measurement says.
    from nightscribe.core import chart_annotate as ca
    from nightscribe.viz import palette
    tab = dlg.tab_measure
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    assert tab._last is not None
    role = ca.magnitude_role(tab.measured_facts())
    assert role in (ca.ROLE_MAG, ca.ROLE_MAG_FAIR, ca.ROLE_MAG_DOUBT)
    assert palette.MEASURE_COLOURS[role] in tab.lbl_result.toHtml()
    # and the panel's PLAIN text is what it always was (what the observer
    # copies and the tests read)
    assert "Magnitude:" in tab.lbl_result.toPlainText()
    assert "<span" not in tab.lbl_result.toPlainText()


def test_the_panel_paints_a_catalogue_magnitude_in_white(dlg):
    # The cross-matched source's magnitude is NOT a measurement of this
    # plate: it wears the catalogue's white, the same role the band gives it.
    from nightscribe.core import chart_annotate as ca
    from nightscribe.viz import palette
    tab = dlg.tab_measure
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab._last["match"] = ({"id": "J1234", "catalog": "Gaia EDR3",
                           "mag": 12.4, "band": "G",
                           "bands": [{"label": "G", "value": 12.4}]}, 1.2)
    tab._fill_panel(tab._last["band"], 5, 4, {}, False, None)
    html = tab.lbl_result.toHtml()
    assert palette.MEASURE_COLOURS[ca.ROLE_MAG_CAT] in html


def test_saturation_box_overrides_and_shows_what_auto_resolves(dlg,
                                                               monkeypatch):
    # one knob for measure and series: a positive value wins, 0 means the
    # config (SATURATE card then ccd_saturate), and the line at its right
    # says what 0 resolves to, so it never looks like it ignores the config
    from nightscribe import config as cfgmod
    from nightscribe.core import photometry as phot
    tab = dlg.tab_measure
    _sequence(dlg, dlg._test_comps)
    seen = []
    real = phot.measure_plate
    monkeypatch.setattr(
        phot, "measure_plate",
        lambda image, cfg: (seen.append(cfg), real(image, cfg))[1])
    # auto: the box is 0 and the config has no ccd_saturate
    tab.spn_saturate.setValue(0.0)
    _click(dlg, *dlg._test_target)
    assert seen[-1].site_saturate is None
    assert "auto" in tab._advanced.lbl_saturate_auto.text()
    # the hint names the config value when there is one
    monkeypatch.setitem(cfgmod.config._data, "ccd_saturate", 60000)
    tab._update_saturate_hint()
    assert "60000" in tab._advanced.lbl_saturate_auto.text()
    # the override wins, for a single measurement too
    tab.spn_saturate.setValue(45000.0)
    _click(dlg, *dlg._test_target)
    assert seen[-1].site_saturate == 45000.0
    assert "override" in tab._advanced.lbl_saturate_auto.text()


# ------------- one night, one curve: the passes door (asked) ----------
#
# The observer's own question: "why do we keep the old passes if there is
# then no way to get them back?". A visit can hold several series runs and
# only ONE is drawn (drawing them all at once was the reported corruption);
# this door is where they are seen and where the drawn one is chosen.

def _passes(curve_id=2, undone_empty=0):
    # @args: curve_id - which pass the visit says it is showing,
    #        undone_empty - the undone passes the host counted instead of
    #        listing (they have no points left)
    # @return: the payload the host hands the tab
    return {"undone_empty": undone_empty, "runs": [
        {"id": 1, "created": 1790750000.0, "band": "V", "points": 10,
         "mjd0": 60297.77, "mjd1": 60297.79, "status": "complete"},
        {"id": 2, "created": 1790751000.0, "band": "G", "points": 5,
         "mjd0": 60297.77, "mjd1": 60297.79, "status": "complete"}],
        "curve_run_id": curve_id}


def test_the_panel_says_which_pass_is_drawn_and_that_others_exist(dlg):
    # Nothing is hidden: the curve that came from the project says which
    # pass it is AND that the visit holds others that are not drawn, naming
    # the door where they are chosen.
    tab = dlg.tab_measure
    dlg.set_visit_passes_hooks(lambda: _passes(2), lambda run_id: None)
    tab.set_visit_curve_hooks(
        lambda: {"points": _visit_points(5), "zp_mode": "catalog"}, None)
    panel = tab.lbl_result.toPlainText()
    assert "earlier pass" in panel
    assert "Passes of this visit" in panel
    assert "10" in panel                       # the points of the other one


def test_a_visit_with_one_pass_keeps_the_plain_line(dlg):
    # With a single pass there is nothing to choose and nothing to warn
    # about: the panel says what it always said.
    tab = dlg.tab_measure
    payload = _passes(1)
    payload["runs"] = payload["runs"][:1]
    dlg.set_visit_passes_hooks(lambda: payload, lambda run_id: None)
    tab.set_visit_curve_hooks(
        lambda: {"points": _visit_points(5), "zp_mode": "catalog"}, None)
    panel = tab.lbl_result.toPlainText()
    assert "earlier pass" not in panel
    assert "already measured" in panel


def test_the_passes_door_lists_them_and_going_back_redraws(dlg):
    tab = dlg.tab_measure
    chosen = []
    # what the host answers with: the pass the visit is showing. The test
    # moves it when it presses "Make this the curve", and the chart
    # following it is the proof that the reload happened.
    state = {"n": 5}

    def load():
        return {"points": _visit_points(state["n"]), "zp_mode": "catalog"}

    dlg.set_visit_passes_hooks(lambda: _passes(2), chosen.append)
    tab.set_visit_curve_hooks(load, None)
    tab.load_visit_curve()
    assert len(tab.chart_series._points) == 5
    tab._open_passes()
    door = tab._passes_dlg
    assert door.tbl_passes.rowCount() == 2
    assert "The chart is showing" in door.lbl_passes_shown.text()
    assert door.lbl_passes_trail.text() == ""      # nothing hidden
    assert "the curve" in door.tbl_passes.item(1, 4).text()
    assert door.btn_passes_use.isEnabled() is False   # row 1 IS the curve
    door.tbl_passes.selectRow(0)
    assert door.btn_passes_use.isEnabled() is True
    state["n"] = 2                              # the pass it goes back to
    door.btn_passes_use.click()
    assert chosen == [1]                        # the visit was told
    assert len(tab.chart_series._points) == 2   # and the chart followed
    door.close()


def test_the_door_counts_the_undone_passes_instead_of_listing_them(dlg):
    # A real visit had 26 undone passes against 4 that mattered. They are
    # counted, not listed, and the window says so: the trail keeps them and
    # nothing was deleted.
    tab = dlg.tab_measure
    dlg.set_visit_passes_hooks(lambda: _passes(2, undone_empty=26),
                               lambda run_id: None)
    tab._open_passes()
    door = tab._passes_dlg
    assert door.tbl_passes.rowCount() == 2          # only the ones with data
    assert "26" in door.lbl_passes_trail.text()
    assert "nothing was deleted" in door.lbl_passes_trail.text()
    door.close()


def test_undoing_a_pass_from_the_door_says_what_it_did(dlg):
    tab = dlg.tab_measure
    undone = []
    dlg.set_visit_passes_hooks(lambda: _passes(2), lambda run_id: None)
    dlg.set_run_undo_hook(lambda run_id: (undone.append(run_id), 7)[1])
    tab.set_visit_curve_hooks(
        lambda: {"points": _visit_points(3), "zp_mode": "catalog"}, None)
    tab.load_visit_curve()
    tab._undo_pass(2)
    assert undone == [2]
    assert "7" in tab.lbl_status.text()


def test_the_door_needs_a_visit_and_says_so(dlg):
    # An ad-hoc open (the Tools menu) has no visit: the door says why
    # instead of showing an empty window.
    tab = dlg.tab_measure
    tab._open_passes()
    assert "does not belong to a visit" in tab.lbl_status.text()
    assert tab._passes_dlg.isVisible() is False


def test_undoing_the_last_pass_brings_the_previous_one_back(dlg):
    # The reason the visit remembers its pass: after undoing the run, the
    # chart has to show the pass before it (a visit with a single pass
    # simply ends up empty).
    tab = dlg.tab_measure
    state = {"n": 4}

    def load():
        return {"points": _visit_points(state["n"]), "zp_mode": "catalog"}

    tab.set_visit_curve_hooks(load, None)
    dlg.set_run_undo_hook(lambda run_id: 4)
    assert len(tab.chart_series._points) == 4
    state["n"] = 2                       # the pass before the undone one
    tab._series_run_id = 9
    tab._on_series_undo()
    assert len(tab.chart_series._points) == 2      # the pass before it
    assert tab._series_result is None
    assert tab.btn_series_exoclock.isEnabled() is False


def test_the_reloaded_curve_keeps_the_axis_it_was_measured_on(dlg):
    # A relative run already gives differences: the chart has to come back
    # on the differential axis it was drawn on, or the reload would show
    # the same numbers on another scale.
    from nightscribe.gui.widgets.lightcurve_widget import (MAG_CALIBRATED,
                                                           MAG_DIFFERENTIAL)
    tab = dlg.tab_measure
    tab.set_visit_curve_hooks(
        lambda: {"points": _visit_points(4), "zp_mode": "relative"}, None)
    assert tab.chart_series._mag_mode == MAG_DIFFERENTIAL
    tab._reload_visit_curve()
    tab._series_result = None
    tab.set_visit_curve_hooks(
        lambda: {"points": _visit_points(4), "zp_mode": "catalog"}, None)
    assert tab.chart_series._mag_mode == MAG_CALIBRATED


def test_centre_nudge_moves_the_measurement(dlg, monkeypatch):
    # like the blink's alignment: 0.5 px steps move the measurement centre
    # and the point is measured again from there
    from nightscribe.core import photometry as phot
    tab = dlg.tab_measure
    _sequence(dlg, dlg._test_comps)
    seen = []
    real = phot.measure_plate
    monkeypatch.setattr(
        phot, "measure_plate",
        lambda image, cfg: (seen.append(cfg.target_xy), real(image, cfg))[1])
    _click(dlg, *dlg._test_target)
    click = tab._last["click"]
    assert seen[-1] == pytest.approx(click)
    tab._nudge_step(0.1, 0.0)
    assert seen[-1][0] == pytest.approx(click[0] + 0.1)
    assert seen[-1][1] == pytest.approx(click[1])
    assert tab.lbl_nudge.text() == "(+0.1, +0.0)"
    # the reset button goes back to the clicked centre and re-measures
    tab._nudge_step(0.0, -0.1)
    tab._on_nudge_reset()
    assert tab._nudge == [0.0, 0.0]
    assert seen[-1] == pytest.approx(click)
    # a new click starts at (0, 0) too
    tab._nudge_step(0.1, 0.1)
    _click(dlg, *dlg._test_target)
    assert tab._nudge == [0.0, 0.0]
    assert seen[-1] == pytest.approx(click)


def test_manual_centre_pins_the_measurement(dlg):
    # "Manual centre": the measurement sits EXACTLY where the observer puts
    # it, with no centroid search, for a very faint SN the algorithm would
    # drag to a neighbour
    tab = dlg.tab_measure
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab.chk_manual_centre.setChecked(True)
    tab._nudge_step(0.1, 0.0)
    click = tab._last["click"]
    assert tab._last["col"] == pytest.approx(click[0] + 0.1, abs=1e-6)
    assert tab._last["row"] == pytest.approx(click[1], abs=1e-6)
    assert "manual centre" in tab.lbl_result.toPlainText()
    # and the mode survives a capture/restore of the plate state
    st = tab.capture_state()
    assert st["manual_centre"] is True
    tab.chk_manual_centre.setChecked(False)
    tab.apply_state(st)
    assert tab.chk_manual_centre.isChecked() is True


# ------------- the multi-night scope (asked 2026-09-30) ---------------

def test_the_scope_selector_is_always_there_and_explains_itself(dlg):
    # "En las secuencias multi-noche se han de cargar las imágenes de todas
    # las visitas": the scope is offered when the project really has more
    # than one visit with frames (the host says how many).
    #
    # And it is ALWAYS in the block, on its own row: the observer asked
    # "no veo lo del modo multinoche, ¿dónde está?", so with one visit it
    # stays visible and DISABLED, saying why, instead of disappearing (a
    # control that hides teaches nobody that the feature exists).
    tab = dlg.tab_measure

    def ctx(scope="visit"):
        return {"pid": 1, "session_id": 2, "paths": ["/tmp/a.fits"],
                "visits": 1, "scope": scope}

    dlg.set_series_hook(ctx)
    assert not tab.cmb_series_scope.isHidden()
    assert not tab.lbl_series_scope.isHidden()
    assert not tab.cmb_series_scope.isEnabled()
    assert "one visit with frames" in tab.cmb_series_scope.toolTip()
    # on its own row, and wide enough to read its options whole
    row = tab.cmb_series_scope.parent().layout()
    assert row is not None and row.indexOf(tab.lbl_series_frames) < 0
    need = tab.cmb_series_scope.fontMetrics().horizontalAdvance("all visits")
    assert tab.cmb_series_scope.minimumSizeHint().width() >= need

    def ctx2(scope="visit"):
        return {"pid": 1, "session_id": 2, "paths": ["/tmp/a.fits"],
                "visits": 3, "scope": scope}

    dlg.set_series_hook(ctx2)
    assert tab.cmb_series_scope.isEnabled()
    assert "all the visits" in tab.cmb_series_scope.toolTip().lower()


def test_the_multi_night_scope_steps_aside_live_and_draws_the_project(dlg):
    # With «all visits» the frames come from every night: live mode watches
    # ONE folder, so it is turned off and disabled SAYING WHY, discarding is
    # per visit (there is no single night to undo) and the chart reloads the
    # project's curve.
    tab = dlg.tab_measure

    def ctx(scope="visit"):
        return {"pid": 1, "session_id": 2, "paths": ["/tmp/a.fits"],
                "visits": 2, "nights": 2, "scope": scope}

    dlg.set_series_hook(ctx)
    dlg.set_visit_curve_hooks(
        lambda scope="visit": {
            "points": _visit_points(5 if scope == "project" else 2),
            "zp_mode": "catalog"}, None)
    tab.cmb_series_scope.setCurrentIndex(
        tab.cmb_series_scope.findData("project"))
    assert not tab.chk_series_live.isEnabled()
    assert "one visit" in tab.chk_series_live.toolTip().lower()
    assert len(tab.chart_series._points) == 5      # the project's curve
    assert not tab.btn_series_discard.isEnabled()
    assert "per visit" in tab.btn_series_discard.toolTip()
    # and back: the visit's own curve, live offered again
    tab.cmb_series_scope.setCurrentIndex(0)
    assert tab.chk_series_live.isEnabled()
    assert len(tab.chart_series._points) == 2


def test_the_passes_door_says_when_a_night_belongs_to_a_pass(dlg):
    # A run of a multi-night pass says so: that is what "undo this pass"
    # will take with it.
    tab = dlg.tab_measure
    payload = _passes(2)
    payload["runs"][1]["cfg"] = {"series": {"pass": {"group": "abc",
                                                     "nights": 3}}}
    dlg.set_visit_passes_hooks(lambda: payload, lambda run_id: None)
    tab._open_passes()
    door = tab._passes_dlg
    assert "3-night pass" in door.tbl_passes.item(1, 4).text()
    assert "3-night pass" not in door.tbl_passes.item(0, 4).text()
    door.close()


def test_manual_centre_dialog_follows_the_checkbox(dlg):
    # the tab keeps only the checkbox; the pad lives in its own non-modal
    # window, opened by checking and closed by unchecking
    tab = dlg.tab_measure
    assert not tab._centre.isVisible()
    assert not tab._centre.isModal()
    tab.chk_manual_centre.setChecked(True)
    assert tab._centre.isVisible()
    # the arrows live there now and still move the measurement centre
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab._centre.btn_right.click()
    assert tab._nudge[0] == pytest.approx(0.1)
    tab.chk_manual_centre.setChecked(False)
    assert not tab._centre.isVisible()


def test_the_block_header_is_never_cut(dlg, qapp):
    # Reported: "haz más grande la caja de texto (más altura) del grupo, la
    # que está al principio". The header of the block is a word-wrapped
    # label, and Qt does not always ask for the height its text needs (the
    # sizeHint is computed for a width that changes later: measured, 54 px
    # for a text of four lines, so the last one came out half cut). The
    # block refits it at its REAL width.
    tab = dlg.tab_measure
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2,
                                 "paths": ["/tmp/a.fits"], "visits": 1})
    qapp.processEvents()
    lbl = tab.lbl_series_hint
    assert lbl.isVisible()
    assert lbl.width() >= 50
    assert lbl.height() >= lbl.heightForWidth(lbl.width())


def test_the_night_figures_work_with_a_project_behind_them(dlg, tmp_path,
                                                           monkeypatch):
    # Reported: "el botón Night Conditions (PNG) no hace nada". With a VISIT
    # context (a project behind the editor, which is the normal case) the
    # handler called `project.get(db, pid)` and **`db` does not exist in this
    # module**: the slot raised a NameError, Qt swallowed it and nothing
    # happened at all (no figure, no message). The test above passed because
    # its context had no pid, so the broken branch was never walked.
    #
    # The tab asks the HOST where to write now, like its sibling export does.
    from nightscribe.viz import night_view
    tab = dlg.tab_measure
    dlg.set_series_hook(lambda scope="visit": {"pid": 7, "session_id": 2,
                                               "paths": ["/tmp/a.fits"]})
    dlg.set_export_folder_hook(lambda: str(tmp_path))
    points = [dict(p, airmass=1.2 + 0.01 * i, x=800.0 + i, y=600.0 + i)
              for i, p in enumerate(_visit_points(6))]
    tab.set_visit_curve_hooks(lambda: points, None)
    written = []
    monkeypatch.setattr(
        night_view, "draw_airmass",
        lambda pts, out=None, **k: (written.append(out), out)[1])
    monkeypatch.setattr(
        night_view, "draw_drift",
        lambda pts, out=None, **k: (written.append(out), out)[1])
    monkeypatch.setattr("nightscribe.gui.chart_viewer.open_chart",
                        lambda *a, **k: None)
    tab._on_series_night()                     # must not raise
    assert len(written) == 2                   # the two figures, not one
    assert all(str(tmp_path) in str(out) for out in written)
    assert "Night figures written" in tab.lbl_status.text()


def test_the_passes_door_opens_with_room_to_read_it(dlg):
    # Reported: "ajusta el tamaño de Passes of this visit, que al abrirlo
    # apenas se ve nada". Measured with real data: 533 x 434, a table of
    # 511 x 174 and a sizeHint of 660 wide, so the state column (which says
    # "complete · the curve · part of a 3-night pass") fell outside the
    # window and the useful rows were the ones you had to scroll to.
    tab = dlg.tab_measure
    dlg.set_visit_passes_hooks(lambda: _passes(2), lambda run_id: None)
    tab._open_passes()
    door = tab._passes_dlg
    assert door.width() >= 880
    assert door.tbl_passes.height() >= 200
    assert door.tbl_passes.horizontalHeader().stretchLastSection()
    door.close()
