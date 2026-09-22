############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE image state controller (ADR-044)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_state.py: loading both FITS fixtures,
auto limits, the clamped white > black invariant, gamma, inversion, the
2x2 downscale steps and the scene/data coordinate split. No network.
"""

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = Path(__file__).parents[1] / "fixtures"
MONO = FIXTURES / "sn2026zji_new_image.fits"          # 2047x2047, WCS TAN-SIP
AIJ = FIXTURES / "sample_annotated_image_from_aij.fits"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def state(qapp):
    from nightscribe.gui.ufe_state import UfeImageState
    return UfeImageState()


def test_load_mono_fixture(state):
    state.load(MONO)
    assert state.has_image
    assert state.plate_shape == (2047, 2047)
    assert state.d_min < state.d_max
    assert state.wcs is not None           # TAN-SIP is tolerated
    assert state.display_scale == 1        # under the 4096 cap
    assert state.d_min <= state.black < state.white <= state.d_max
    assert state.gamma == 1.0 and not state.inverted


def test_load_aij_fixture(state):
    state.load(AIJ)
    assert state.has_image
    assert state.plate_shape == (2048, 2048)
    assert state.data.ndim == 2            # RGB collapses to luminance
    assert state.black < state.white


def test_load_missing_file_raises(state):
    from nightscribe.core.fits_io import FitsError
    with pytest.raises(FitsError):
        state.load(FIXTURES / "no_such_file.fits")
    assert not state.has_image


def test_load_emits_image_loaded(state, qapp):
    seen = []
    state.image_loaded.connect(lambda: seen.append(True))
    state.load(MONO)
    assert seen == [True]


def test_auto_percentiles_are_robust(state):
    # a spike of hot pixels must not blow the white point away
    data = np.full((200, 200), 1000.0, dtype=np.float32)
    data[:2, :2] = 65000.0                 # 0.01 % of hot pixels
    state.data = data
    state.auto()
    assert state.black < state.white
    assert state.white < 65000.0


def test_set_stretch_clamps_white_above_black(state):
    state.load(MONO)
    state.set_stretch(black=5000.0, white=4000.0)
    assert state.white > state.black
    state.set_stretch(black=state.white + 10.0)
    assert state.white > state.black       # the invariant survives both ways


def test_set_stretch_emits_only_on_change(state):
    seen = []
    state.load(MONO)
    state.stretch_changed.connect(lambda: seen.append(True))
    state.set_stretch(black=state.black)   # no-op: no signal
    assert seen == []
    state.set_stretch(gamma=1.4)
    assert seen == [True]


def test_gamma_brightens_midtones(state):
    state.load(MONO)
    base = float(np.median(state.display_uint8()))
    state.set_stretch(gamma=0.4)           # <1 lifts the mid-tones
    lifted = float(np.median(state.display_uint8()))
    assert lifted > base


def test_invert_swaps_black_and_white(state):
    state.load(MONO)
    normal = state.display_uint8().astype(int)
    state.toggle_invert()
    inverted = state.display_uint8().astype(int)
    assert np.allclose(normal + inverted, 255, atol=1)


def test_downscale_steps_halve_until_the_cap(state):
    state.data = np.zeros((100, 80), dtype=np.float32)
    out = state._downscaled(cap=30)
    assert out.shape == (25, 20)           # 100->50->25, 80->40->20


def test_downscale_average_preserves_mean(state):
    rng = np.random.default_rng(42)
    state.data = rng.normal(500.0, 10.0, (64, 64)).astype(np.float32)
    out = state._downscaled(cap=16)
    assert out.shape == (16, 16)
    assert abs(float(out.mean()) - float(state.data.mean())) < 1.0


def test_display_cap_sets_scale(state):
    state.data = np.zeros((9000, 9000), dtype=np.float32)
    assert state._compute_scale() == 4     # 9000->4500->2250 <= 4096


def test_scene_data_roundtrip(state):
    state.load(MONO)
    col, row = state.scene_to_data(100.0, 200.0)
    x, y = state.data_to_scene(col, row)
    assert (x, y) == (100.0, 200.0)
    # the FITS flip: scene top is the last data row
    assert row == 2047 - 1 - 200.0


def test_probe_reports_pixel_dn_and_sky(state):
    state.load(MONO)
    hit, lines = state.probe_text(1023.5, 1023.5)
    assert hit
    assert "DN" in lines[0]
    assert lines[1].startswith("RA ") and "Dec " in lines[1]


def test_probe_outside_and_empty(state):
    assert state.probe_text(0, 0) == (False, None)
    state.load(MONO)
    assert state.probe_text(-1, 0) == (False, None)
    assert state.probe_text(0, 2047) == (False, None)


def test_clear_returns_to_empty(state):
    seen = []
    state.load(MONO)
    state.image_loaded.connect(lambda: seen.append(True))
    state.clear()
    assert not state.has_image
    assert seen == [True]


def test_keep_stretch_off_resets_on_load(state):
    state.load(MONO)
    state.set_stretch(black=3000.0, white=9000.0, gamma=0.7)
    state.toggle_invert()
    state.load(AIJ)                       # default: fresh auto stretch
    assert not state.inverted and state.gamma == 1.0
    assert (state.black, state.white) != (3000.0, 9000.0)


def test_keep_stretch_on_preserves_everything(state):
    state.load(MONO)
    state.set_stretch(black=3000.0, white=9000.0, gamma=0.7)
    state.toggle_invert()
    state.keep_stretch = True
    state.load(AIJ)
    assert state.black == 3000.0 and state.white == 9000.0
    assert state.gamma == pytest.approx(0.7) and state.inverted
