############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE Blink tab (ADR-044, phase E)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_blink_tab.py: pair preparation through a
fake BlinkWorker (no network), the live blink / fade frames, nudge and
balance, the WCS-mapped marker, the stage handoff (the view's frame
override) and the exports through a fake BlinkExportWorker. The legacy
blink dialog is untouched.
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
    d.tabs.setCurrentWidget(d.tab_blink)        # take the stage
    yield d
    d.tab_blink.shutdown()           # the blink timer never outlives it
    d.view._render_timer.stop()
    d.deleteLater()


def _pair(dlg, flipped=False, with_sn=True):
    # A synthetic aligned pair; the SN sits at the plate's centre of
    # light (and is the only hot pixel in obs).
    rng = np.random.default_rng(7)
    obs = rng.normal(5000, 30, (64, 64)).astype(np.float32)
    ref = rng.normal(4800, 30, (64, 64)).astype(np.float32)
    sn_xy = (32.0, 32.0) if with_sn else None
    if with_sn:
        obs[32, 32] = 30000
    ra, dec = dlg.state.wcs.center()
    return {"ref": ref, "obs": obs, "sn_xy": sn_xy, "name": "SN 2026zji",
            "ra": ra, "dec": dec, "ref_label": "PS1 g",
            "flipped": flipped}


class _FakePrepareWorker:
    # Synchronous BlinkWorker double: emits progress and finishes at once.
    def __init__(self, path, sn_name=None, ra=None, dec=None,
                 pair=None, errors=None):
        from PySide6.QtCore import QObject, Signal
        self._pair = pair
        self._errors = errors or {}
        self.sn_name = sn_name
        self.ra, self.dec = ra, dec

        class _Sig(QObject):
            finished = Signal(dict, dict)
            progress = Signal(dict)
        self._sig = _Sig()
        self.finished = self._sig.finished
        self.progress = self._sig.progress

    def start(self):
        self.progress.emit({"es": "etapa", "en": "stage"})
        self.finished.emit(self._pair or {}, self._errors)


class _FakeExportWorker:
    # Synchronous BlinkExportWorker double: records args, writes a byte.
    seen = None

    def __init__(self, kind, ref8, obs8, sn_xy, out, **kw):
        from PySide6.QtCore import QObject, Signal
        _FakeExportWorker.seen = {"kind": kind, "sn_xy": sn_xy,
                                  "out": out, **kw}
        self._out = out

        class _Sig(QObject):
            finished = Signal(str, str)
        self._sig = _Sig()
        self.finished = self._sig.finished

    def start(self):
        Path(self._out).write_bytes(b"x")
        self.finished.emit(self._out, "")

    def isRunning(self):
        return False


def test_tab_replaces_the_placeholder(dlg):
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Blink", "Compare", "Measure", "Annotate"]
    assert dlg.tabs.indexOf(dlg.tab_blink) == 0


def test_prepare_requires_a_plate_or_a_target(dlg):
    tab = dlg.tab_blink
    tab.edt_name.setText("")
    tab._on_prepare()
    assert "supernova" in tab.lbl_status.text() or "name" \
        in tab.lbl_status.text()
    tab.chk_manual.setChecked(True)
    tab.edt_ra.setText("999")                # out of range
    tab._on_prepare()
    assert "invalid" in tab.lbl_status.text().lower()


def test_prepare_runs_the_worker_and_fills_frames(dlg, monkeypatch):
    tab = dlg.tab_blink
    pair = _pair(dlg)
    monkeypatch.setattr("nightscribe.gui.workers.BlinkWorker",
                        lambda *a, **k: _FakePrepareWorker(*a, **k,
                                                           pair=pair))
    tab.edt_name.setText("2026zji")
    tab._on_prepare()
    # note: Signal(dict) crosses as a QVariantMap copy, so compare
    # content, not identity
    assert tab._pair["name"] == "SN 2026zji"
    assert np.array_equal(tab._pair["obs"], pair["obs"])
    assert tab._obs8.shape == (64, 64)       # stretched at work size
    assert "SN 2026zji" in tab.lbl_status.text()
    assert "PS1 g" in tab.lbl_status.text()
    assert dlg.view._frame_override is not None
    assert len(tab._items) == 6              # circle + ticks + name
    assert tab._timer.isActive()             # live blink started


def test_prepare_error_stays_on_the_status_line(dlg, monkeypatch):
    tab = dlg.tab_blink
    monkeypatch.setattr(
        "nightscribe.gui.workers.BlinkWorker",
        lambda *a, **k: _FakePrepareWorker(
            *a, errors={"es": "fallo de prueba", "en": "test failure"}))
    tab.edt_name.setText("2026zz9")
    tab._on_prepare()
    # the tab defaults to lang="es": the Spanish half shows
    assert "fallo de prueba" in tab.lbl_status.text()
    assert tab.lbl_status.text().startswith("⚠")
    assert tab._pair is None


def test_tick_swaps_obs_and_ref(dlg):
    tab = dlg.tab_blink
    tab._on_pair_ready(_pair(dlg), {})
    first = tab._display_frame().copy()
    tab._tick()
    second = tab._display_frame().copy()
    assert not np.array_equal(first, second)
    assert np.array_equal(second, np.flipud(tab._ref8))
    tab._tick()
    assert np.array_equal(tab._display_frame(), first)


def test_fade_blends_and_honours_the_slider(dlg):
    tab = dlg.tab_blink
    tab._on_pair_ready(_pair(dlg), {})
    tab.rdo_fade.setChecked(True)
    assert not tab._timer.isActive()         # fade stops the swap
    tab.sld_fade.setValue(100)
    assert np.array_equal(tab._display_frame(), np.flipud(tab._ref8))
    tab.sld_fade.setValue(0)
    assert np.array_equal(tab._display_frame(), np.flipud(tab._obs8))


def test_nudge_shifts_only_the_reference(dlg):
    tab = dlg.tab_blink
    tab._on_pair_ready(_pair(dlg), {})
    obs_before = tab._obs8.copy()
    ref_col = tab._ref8[32].copy()
    tab.spin_dx.setValue(5.0)
    tab.btn_nudge.click()
    assert np.array_equal(tab._obs8, obs_before)
    assert not np.array_equal(tab._ref8[32], ref_col)
    assert tab.lbl_nudge.text() == "(+5.0, +0.0)"


def test_balance_auto_sets_the_gain(dlg):
    tab = dlg.tab_blink
    tab._on_pair_ready(_pair(dlg), {})
    tab._on_balance_auto()
    assert 25 <= tab.sld_balance.value() <= 400
    assert tab._gain == pytest.approx(tab.sld_balance.value() / 100.0)


def test_shared_stretch_drives_the_blink(dlg):
    tab = dlg.tab_blink
    tab._on_pair_ready(_pair(dlg), {})
    before = tab._obs8.copy()
    dlg.state.toggle_invert()                # the common Invert reaches
    assert not np.array_equal(tab._obs8, before)   # the blink frames
    dlg.state.toggle_invert()


def test_marker_maps_through_the_plate_wcs(dlg):
    tab = dlg.tab_blink
    tab._on_pair_ready(_pair(dlg), {})
    pos = tab._sn_scene()
    assert pos is not None
    # the SN sits at the plate centre: centre of the scene too
    w, h = dlg.state.plate_shape
    assert abs(pos[0] - w / 2) < 2 and abs(pos[1] - h / 2) < 2
    tab.chk_marker.setChecked(False)
    assert tab._items == []


def test_leaving_the_tab_hands_the_plate_back(dlg):
    tab = dlg.tab_blink
    tab._on_pair_ready(_pair(dlg), {})
    assert dlg.view._frame_override is not None
    dlg.tabs.setCurrentIndex(1)              # the Compare placeholder
    assert dlg.view._frame_override is None
    assert not tab._timer.isActive()
    assert tab._items == []
    dlg.tabs.setCurrentWidget(tab)           # back: blink resumes
    assert dlg.view._frame_override is not None
    assert tab._timer.isActive()


def test_loading_a_new_plate_invalidates_the_pair(dlg):
    tab = dlg.tab_blink
    tab._on_pair_ready(_pair(dlg), {})
    assert tab._pair is not None
    dlg.state.load(MONO)                     # same file, fresh load
    assert tab._pair is None
    assert dlg.view._frame_override is None
    assert not tab._timer.isActive()


def test_export_gif_through_the_worker(dlg, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    tab = dlg.tab_blink
    tab._on_pair_ready(_pair(dlg), {})
    out = tmp_path / "sn_blink.gif"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    monkeypatch.setattr("nightscribe.gui.workers.BlinkExportWorker",
                        _FakeExportWorker)
    tab._export("gif")
    seen = _FakeExportWorker.seen
    assert seen["kind"] == "gif"
    assert seen["sn_xy"] == (32.0, 32.0)     # un-flipped export frame
    assert seen["effect"] == "blink"
    assert seen["name"] == "SN 2026zji"
    assert out.exists()
    assert "Written to" in tab.lbl_status.text()
    assert tab._export_workers == []         # finished workers pruned


def test_export_unflips_the_sn_position(dlg, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    tab = dlg.tab_blink
    pair = _pair(dlg, flipped=True)
    tab._on_pair_ready(pair, {})
    out = tmp_path / "x.png"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    monkeypatch.setattr("nightscribe.gui.workers.BlinkExportWorker",
                        _FakeExportWorker)
    tab._export("png")
    assert _FakeExportWorker.seen["sn_xy"] == (64 - 1 - 32.0, 32.0)
