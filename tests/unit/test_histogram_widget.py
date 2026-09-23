############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE visual histogram strip (ADR-044, phase B)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/widgets/histogram_widget.py: the 256-bin
histogram lands on load, the draggable handles and the fine-DN spins push
absolute DN into the state, gamma and Auto and Invert stay in sync, and
the empty state disables itself. No network.
"""

import os
from pathlib import Path

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
def strip(qapp):
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.widgets.histogram_widget import HistogramWidget
    state = UfeImageState()
    w = HistogramWidget(state)
    w.resize(900, 140)
    w.show()
    yield w
    w.deleteLater()


def test_empty_state_disables_controls(strip):
    assert not strip.spn_black.isEnabled()
    assert not strip.btn_auto.isEnabled()
    assert strip.canvas._edges is None


def test_load_computes_histogram_and_ranges(strip):
    strip._state.load(MONO)
    assert strip.canvas._counts is not None
    assert len(strip.canvas._counts) == 256
    lo, hi = strip._state.d_min, strip._state.d_max
    assert strip.spn_black.minimum() == lo
    assert strip.spn_black.maximum() == hi
    assert strip.spn_black.value() == pytest.approx(strip._state.black)
    assert strip.spn_white.value() == pytest.approx(strip._state.white)
    assert strip.spn_gamma.value() == pytest.approx(1.0)


def test_spin_edits_push_absolute_dn(strip):
    strip._state.load(MONO)
    strip.spn_black.setValue(strip._state.black + 50.0)
    strip._on_dn_edited(strip.spn_black.value())
    assert strip._state.black == pytest.approx(strip.spn_black.value())
    # the clamp keeps white above black even from a hostile spin
    strip.spn_white.setValue(strip._state.black - 100.0)
    strip._on_dn_edited(strip.spn_white.value())
    assert strip._state.white > strip._state.black


def test_gamma_spin_reaches_the_state(strip):
    strip._state.load(MONO)
    strip.spn_gamma.setValue(0.6)
    strip._on_gamma_edited(0.6)
    assert strip._state.gamma == pytest.approx(0.6)


def test_auto_button_restores_percentiles(strip):
    strip._state.load(MONO)
    auto_black = strip._state.black
    strip._state.set_stretch(black=strip._state.black + 500.0)
    strip.btn_auto.click()
    assert strip._state.black == pytest.approx(auto_black)


def test_invert_button_mirrors_state(strip):
    strip._state.load(MONO)
    strip.btn_invert.setChecked(True)
    assert strip._state.inverted
    # and a state-side toggle reflects back into the button
    strip._state.toggle_invert()
    assert not strip.btn_invert.isChecked()


def _mouse(evtype, x, y, buttons):
    # @return: a QMouseEvent in the full local/scene/global form (the
    #          short ctors are deprecated in this Qt build)
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QPointingDevice
    pos = QPointF(x, y)
    return QMouseEvent(evtype, pos, pos, pos, Qt.LeftButton, buttons,
                       Qt.NoModifier, QPointingDevice.primaryPointingDevice())


def test_handle_drag_sets_black_dn(strip, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QMouseEvent
    strip._state.load(MONO)
    canvas = strip.canvas
    x0, _y0, w, _h = canvas._plot_rect()
    target_x = x0 + w * 0.25
    before = strip._state.black
    canvas.mousePressEvent(_mouse(QMouseEvent.MouseButtonPress,
                                  target_x, 20, Qt.LeftButton))
    assert canvas._drag == "black"     # nearest handle jumped and grabbed
    canvas.mouseMoveEvent(_mouse(QMouseEvent.MouseMove,
                                 target_x + 30, 20, Qt.LeftButton))
    expected = canvas.x_to_dn(target_x + 30)
    assert strip._state.black == pytest.approx(expected, rel=1e-4)
    assert strip._state.black != before
    canvas.mouseReleaseEvent(_mouse(QMouseEvent.MouseButtonRelease,
                                    target_x + 30, 20, Qt.NoButton))
    assert canvas._drag is None


def test_handle_grab_near_white_handle(strip):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QMouseEvent
    strip._state.load(MONO)
    canvas = strip.canvas
    xw = canvas.dn_to_x(strip._state.white)
    canvas.mousePressEvent(_mouse(QMouseEvent.MouseButtonPress,
                                  xw + 2, 20, Qt.LeftButton))
    assert canvas._drag == "white"     # grabbed, no jump
    assert strip._state.white == pytest.approx(
        canvas.x_to_dn(xw), rel=1e-4)


def test_clear_empties_the_strip(strip):
    strip._state.load(MONO)
    strip._state.clear()
    assert strip.canvas._edges is None
    assert not strip.spn_black.isEnabled()


def test_dn_x_roundtrip(strip):
    strip._state.load(MONO)
    canvas = strip.canvas
    dn = strip._state.d_min + 0.3 * (strip._state.d_max -
                                     strip._state.d_min)
    assert canvas.x_to_dn(canvas.dn_to_x(dn)) == pytest.approx(dn, rel=1e-4)


def test_strip_has_room_for_its_rows(strip):
    # the four control rows (black, white, gamma, buttons + keep) must
    # never be squeezed: the strip's floor covers their natural height
    assert strip.minimumHeight() >= 170
    assert strip.canvas.minimumHeight() >= 100
    assert strip.sizeHint().height() >= 170
