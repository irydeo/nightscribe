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


def test_save_in_project_button_follows_the_point_hook(dlg):
    # ADR-044: "Save in the project" shows only when the dialog was
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
    panel = dlg.tab_measure.lbl_result.text()
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
    assert dlg.tab_measure.lbl_result.text() == "–"


# ---------------- phase H pieces ----------------


def test_seeing_checkbox_scales_the_apertures(dlg):
    _sequence(dlg, dlg._test_comps)
    _click(dlg, *dlg._test_target)
    tab = dlg.tab_measure
    assert tab._last["fwhm"] is not None
    assert "seeing FWHM" in tab.lbl_result.text()
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
    assert "colour slope" in tab.lbl_result.text()
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
    assert "plain zero point" in dlg.tab_measure.lbl_result.text()


def test_check_star_semaphore(dlg):
    entries = _sequence(dlg, dlg._test_comps)
    # a check star whose catalog value lies by half a magnitude
    entries[0]["kind"] = "check"
    entries[0]["star"]["bands"][0]["value"] += 0.5
    _click(dlg, *dlg._test_target)
    panel = dlg.tab_measure.lbl_result.text()
    assert "NOT reliable" in panel and "Comp1" in panel
    # and an honest check star confirms the night
    entries[0]["star"]["bands"][0]["value"] -= 0.5
    _click(dlg, *dlg._test_target)
    panel = dlg.tab_measure.lbl_result.text()
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
    assert "Host galaxy subtracted" in tab.lbl_result.text()
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
    assert "set by hand" in tab.lbl_result.text()
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
    assert tab._last_suggestions[0] in tab.lbl_result.text()
    r = tab._last["radii"]
    assert r == (round(r[0] * 2) / 2, round(r[1] * 2) / 2,
                 round(r[2] * 2) / 2)            # the spins show it


def test_suggest_without_a_measurement_guides(dlg):
    dlg.tab_measure._on_suggest()
    assert "Measure the target first" in dlg.tab_measure.lbl_status.text()


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
