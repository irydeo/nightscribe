############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE Track & Stack tab (astrometry plan,
# phase 7)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_trackstack_tab.py: the tab is built
standalone against a host double that provides the visit context (no
network, and no worker is ever started here: the pipeline's physics lives
in test_track_stack_*). What is proven is the wiring (D22): the expected
SNR table recalculates when the number of observations changes, the stack
button stays disabled without a visit, the workers carry their cancel,
and no widget declared in the Designer file is left orphaned."""

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

UI = Path(__file__).parents[2] / "nightscribe" / "gui" / "ui" \
    / "ufe_trackstack_tab.ui"


def _write_frames(tmp_path, n=4):
    # @args: tmp_path - where, n - how many
    # @return: n small FITS paths with DATE-OBS/EXPTIME (headers are all
    #          load_sequence reads, so the frames stay tiny)
    from astropy.io import fits
    out = []
    for i in range(n):
        hdu = fits.PrimaryHDU(np.zeros((64, 64), dtype=np.float32))
        h = hdu.header
        h["DATE-OBS"] = f"2026-09-20T23:{30 + i}:00"
        h["EXPTIME"] = 30.0
        h["GAIN"] = 2.0
        h["INSTRUME"] = "TestCam"
        p = tmp_path / f"frame{i}.fits"
        hdu.writeto(str(p), overwrite=True)
        out.append(str(p))
    return out


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


def _tab(qapp, tmp_path, visit=True, n=4):
    # @args: qapp - the offscreen app, tmp_path - where the frames go,
    #        visit - False builds the tab with no visit behind it, n -
    #        frames of the visit
    # @return: (tab, host): the tab over a host double with
    #          astrometry_context(), which is what the real dialog exposes
    #          (the tab asks its window(), so a plain parentless QWidget
    #          with the method is a faithful double)
    from PySide6.QtWidgets import QWidget
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    host = QWidget()           # parentless: it IS the tab's window()
    if visit:
        paths = _write_frames(tmp_path, n)
        ctx = {"pid": 1, "session_id": 2, "paths": paths,
               "object_name": "2026 QX"}
    else:
        ctx = None
    host.astrometry_context = lambda: ctx
    state = UfeImageState(host)
    tab = UfeTrackStackTab(state, "en", parent=host)
    tab.set_active(True)
    return tab, host


# ------------------------------------------------------------ the visit

def test_stack_button_disabled_without_visit(qapp, tmp_path):
    # D15: without a visit there is no sequence. The button does not
    # pretend otherwise, and the object line says what is missing.
    tab, _host = _tab(qapp, tmp_path, visit=False)
    assert tab.btn_stack.isEnabled() is False
    assert tab.spn_nobs.isEnabled() is False
    assert tab.tbl_snr.rowCount() == 0
    assert tab.lbl_object.text()          # says why, never empty


def test_visit_arms_the_tab(qapp, tmp_path):
    tab, _host = _tab(qapp, tmp_path)
    assert tab.btn_stack.isEnabled() is True
    assert tab.spn_nobs.isEnabled() is True
    assert tab.spn_nobs.maximum() == 4    # never more groups than frames
    assert "2026 QX" in tab.lbl_object.text()


# ------------------------------------------------- the expected SNR (D22)

def test_preview_table_follows_n_obs(qapp, tmp_path):
    # The user says how many observations; the table shows the split
    # (contiguous groups, as equal as they can be) on every change.
    tab, _host = _tab(qapp, tmp_path)
    tab.spn_nobs.setValue(2)
    assert tab.tbl_snr.rowCount() == 2
    assert [tab.tbl_snr.item(r, 1).text() for r in range(2)] == ["2", "2"]
    tab.spn_nobs.setValue(3)
    assert tab.tbl_snr.rowCount() == 3
    assert [tab.tbl_snr.item(r, 1).text() for r in range(3)] == \
        ["2", "1", "1"]
    # every group carries its own middle-of-exposure instant
    assert tab.tbl_snr.item(0, 2).text() != "–"


def test_expected_snr_splits_with_sqrt_n(qapp, tmp_path):
    # SNR grows with sqrt(n): with a measured base SNR of 40 for the four
    # frames, two observations get 40*sqrt(2/4) and four get 40*sqrt(1/4).
    tab, _host = _tab(qapp, tmp_path)
    tab.spn_nobs.setValue(2)
    # before the first run there is no measurement: the column stays "–"
    # (an estimate without a base would be invented)
    assert tab.tbl_snr.item(0, 3).text() == "–"
    tab._base_snr = 40.0
    tab._refresh_preview()
    assert tab.tbl_snr.item(0, 3).text() == "28.3"
    tab.spn_nobs.setValue(4)
    assert [tab.tbl_snr.item(r, 3).text() for r in range(4)] == \
        ["20.0"] * 4


def test_low_snr_group_is_marked_before_stacking(qapp, tmp_path):
    # D26: a group below the submission floor is SEEN before the run,
    # with the reason in the cell's tooltip (a figure is never shown
    # without its explanation, ADR-058).
    tab, _host = _tab(qapp, tmp_path)
    tab._base_snr = 20.0
    tab.spn_nobs.setValue(4)      # 20*sqrt(1/4) = 10.0, floor is 20
    text = tab.tbl_snr.item(0, 3).text()
    assert text.startswith("10.0")
    assert "⚠" in text
    assert tab.tbl_snr.item(0, 3).toolTip()


# ------------------------------------------------------------- no orphans

def test_no_orphan_widgets(qapp, tmp_path):
    # Every widget the Designer file declares resolves to a real widget
    # (the load that came back wrong is retried by ui_loader, and this
    # reads the .ui itself so nothing can be guessed away), and the
    # viewer's placeholder gave its slot to the real view: a visible
    # placeholder floats at (0, 0) over the first row and eats its
    # clicks (ADR-005).
    from PySide6.QtWidgets import QWidget
    tab, _host = _tab(qapp, tmp_path)
    tree = ET.parse(UI).getroot()
    root = tree.find("widget")
    names = [w.get("name") for w in tree.iter("widget")
             if w.get("name") and w.get("name") != root.get("name")]
    assert names, "the Designer file declares its widgets"
    for name in names:
        w = getattr(tab._ui, name, None)
        assert isinstance(w, QWidget), name
    assert not tab._ui.ph_stack_view.isVisibleTo(tab)
    assert tab._stack_view.parentWidget() is tab
    # and the tab's own viewer never touches the dialog's plate state
    assert tab._stack_state is not tab._state


# ------------------------------------------------------------- workers

def test_workers_carry_their_cancel(qapp):
    # No thread may be left hanging (the trap every tab documents): the
    # workers are cancellable before, during and after a run, and cancel
    # on a worker that never started is a no-op, not a crash.
    from nightscribe.gui.workers import CalibrationWorker, TrackStackWorker
    w = TrackStackWorker(["missing.fits"], "2026 QX", 2)
    assert w.isRunning() is False
    w.cancel()
    assert w._cancel is True
    c = CalibrationWorker(["missing.fits"], None)
    c.cancel()
    assert c._cancel is True
    assert c.isRunning() is False
    # shutdown() on a tab with no worker behind it is safe too
    from nightscribe.gui.ufe_state import UfeImageState
    from nightscribe.gui.ufe_trackstack_tab import UfeTrackStackTab
    tab = UfeTrackStackTab(UfeImageState(), "en")
    tab.shutdown()
