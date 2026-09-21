############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the SN annotated FITS dialog (Track B, B10)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Unit tests for gui.sn_annotate_dialog.

Small hand-made FITS plates (no network, no real observer data): the
frame selector lists the visits, the header WCS sets the pixel scale,
the north PA and the marker start position, the stretch points stay at
least one point apart, the observer owns the preview size, the marker
can be nudged or clicked into place, and saving writes the AIJ-ready
annotated copy without touching the input file.
"""

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF  # noqa: E402

from nightscribe.core import fits_io  # noqa: E402

_BLOCK = 2880


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    return app


@pytest.fixture(autouse=True)
def _reap_dialogs():
    # Destroy any dialog the test left behind: a top-level dialog keeps
    # its C++ object and its timer slots alive in the QApplication, and
    # letting garbage collection reclaim those wrappers later is a
    # window shiboken does not always survive. Close + delete them
    # while the test can still drive the event loop.
    yield
    from PySide6.QtWidgets import QApplication, QDialog
    app = QApplication.instance()
    if app is None:
        return
    for w in app.topLevelWidgets():
        if isinstance(w, QDialog) and w is not None:
            w.close()
            w.deleteLater()
    app.processEvents()


def _card(key, value=None, comment=""):
    # One 80-column FITS card with the "=" in column 9, the way AIJ
    # writes it.
    # @args: key - keyword (<= 8 chars), value - text with quotes for
    #        FITS strings (None for a key only, e.g. END), comment - text
    #        after " / "
    # @return: exactly 80 chars
    s = key.ljust(8) if value is None else f"{key.ljust(8)}= {value}"
    if comment:
        s += f" / {comment}"
    return s[:80].ljust(80)


def _make_plate(path, with_wcs=False):
    # 128 x 128 uint8 plate with a smooth gradient so the stretch has
    # something to work with; optionally a 0.5 arcsec/px WCS centred on
    # the plate.
    # @args: path - where to write, with_wcs - add the WCS cards
    # @return: the path
    n = 128
    cards = [_card("SIMPLE", "T"), _card("BITPIX", "8"), _card("NAXIS", "2"),
             _card("NAXIS1", str(n)), _card("NAXIS2", str(n))]
    if with_wcs:
        c = 0.00013888889  # 0.5 arcsec / pixel, in degrees
        cards += [_card("CTYPE1", "'RA---TAN'"), _card("CTYPE2", "'DEC--TAN'"),
                  _card("CRVAL1", "60.0"), _card("CRVAL2", "40.0"),
                  _card("CRPIX1", "64.5"), _card("CRPIX2", "64.5"),
                  _card("CD1_1", f"-{c}"), _card("CD1_2", "0.0"),
                  _card("CD2_1", "0.0"), _card("CD2_2", f"{c}"),
                  _card("CUNIT1", "'deg'"), _card("CUNIT2", "'deg'")]
    header = "".join(cards + [_card("END")]).encode("latin-1")
    header += b" " * ((_BLOCK - len(header) % _BLOCK) % _BLOCK)
    image = bytes((i * 31 + j * 17) % 256 for i in range(n) for j in range(n))
    path.write_bytes(header + image)
    return path


@pytest.fixture
def plate_wcs(tmp_path):
    # WCS plate: 0.5 arcsec/px, north PA 0, reference point at the centre.
    return _make_plate(tmp_path / "wcs.fits", with_wcs=True)


@pytest.fixture
def plate_plain(tmp_path):
    # Plain plate: image only, no WCS (an old or reduced frame).
    return _make_plate(tmp_path / "plain.fits")


def _make_dialog(qapp, plate_or_plates, project=None, name="SN 2026 test!",
                 ra_deg=None, dec_deg=None, notes=""):
    # @args: qapp - fixture, plate_or_plates - a path or the images list,
    #        the rest is passed through to the constructor
    # @return: the SnAnnotateDialog
    from nightscribe.gui.sn_annotate_dialog import SnAnnotateDialog
    if isinstance(plate_or_plates, list):
        images = plate_or_plates
    else:
        images = [{"fits_path": str(plate_or_plates), "date_obs": "2026-09-15"}]
    return SnAnnotateDialog(None, images, project, name,
                            ra_deg=ra_deg, dec_deg=dec_deg,
                            default_notes=notes)


class _Click:
    # Minimal stand-in for the QMouseEvent: the dialog only reads
    # .position() off it.

    def __init__(self, x, y):
        # @args: x, y - the clicked point in label pixels
        self._pos = QPointF(x, y)

    def position(self):
        # @return: the point, like QEvent.position()
        return self._pos


def test_rejects_empty_image_list(qapp):
    from nightscribe.gui.sn_annotate_dialog import SnAnnotateDialog
    with pytest.raises(ValueError):
        SnAnnotateDialog(None, [], None, "SN X")


def test_wcs_plate_sets_marker_scale_and_north(qapp, plate_wcs):
    dlg = _make_dialog(qapp, plate_wcs, ra_deg=60.0, dec_deg=40.0)
    assert dlg._data is not None
    assert (dlg._img_w, dlg._img_h) == (128, 128)
    # Reference point is the centre, so the marker starts on the SN.
    assert dlg._xy == [63.5, 63.5]
    assert dlg.scale == pytest.approx(0.5, rel=1e-4)
    assert dlg.north_pa == pytest.approx(0.0, abs=1e-6)
    assert dlg.chk_north.isChecked() and dlg.chk_north.isEnabled()
    assert dlg.chk_scale.isChecked() and dlg.chk_scale.isEnabled()
    assert dlg.fits_path_for(0) == str(plate_wcs)


def test_plain_plate_falls_back_to_centre(qapp, plate_plain):
    dlg = _make_dialog(qapp, plate_plain, ra_deg=60.0, dec_deg=40.0)
    assert dlg._data is not None
    assert dlg._xy == [64.0, 64.0]  # no WCS: field centre
    assert dlg.scale is None
    assert dlg.north_pa is None
    assert not dlg.chk_north.isEnabled()
    assert not dlg.chk_scale.isEnabled()


def test_selector_switches_frames(qapp, plate_wcs, plate_plain):
    dlg = _make_dialog(qapp, [
        {"fits_path": str(plate_wcs), "date_obs": "2026-09-10"},
        {"fits_path": str(plate_plain), "date_obs": "2026-09-15"},
    ], ra_deg=60.0, dec_deg=40.0)
    assert dlg.cmb_image.count() == 2
    assert dlg.cmb_image.itemText(0) == "SN 2026 test!  2026-09-10"
    assert dlg.fits_path_for(1) == str(plate_plain)
    # Over to the plain plate: no WCS, marker at the centre.
    dlg._on_image_changed(1)
    assert dlg._xy == [64.0, 64.0]
    assert dlg.scale is None
    # Back to the WCS plate: the SN position again.
    dlg._on_image_changed(0)
    assert dlg._xy == [63.5, 63.5]
    assert dlg.scale == pytest.approx(0.5, rel=1e-4)


def test_save_writes_aij_copy_and_keeps_input(qapp, plate_wcs, tmp_path):
    before = plate_wcs.read_bytes()
    dest = tmp_path / "out.fits"
    dlg = _make_dialog(qapp, plate_wcs, ra_deg=60.0, dec_deg=40.0,
                       notes="smoke test notes")
    dlg.edit_dest.setText(str(dest))
    fired = []
    dlg.saved.connect(fired.append)
    dlg._save()
    # The signal carries the written path and the dialog accepts.
    assert fired == [str(dest)]
    assert dlg.result() == 1  # QDialog.Accepted
    # AIJ ANNOTATE card and the NS_* tail, through the minimal reader.
    header, data = fits_io.read_fits(str(dest))
    assert header["ANNOTATE"] == "63.50,63.50,30,1,0,1,1,orange"
    assert float(header["NS_RA"]) == 60.0
    assert float(header["NS_DEC"]) == 40.0
    assert float(header["NS_SCALE"]) == pytest.approx(0.5, rel=1e-4)
    assert float(header["NS_NORTH"]) == 0.0
    assert header["NS_NOTES"] == "smoke test notes"
    # Image bytes preserved; the input file is untouched.
    src_data = fits_io.read_fits(str(plate_wcs))[1]
    assert np.array_equal(np.asarray(data), np.asarray(src_data))
    assert plate_wcs.read_bytes() == before


def test_save_failure_keeps_dialog_open(qapp, plate_wcs, monkeypatch):
    import nightscribe.gui.sn_annotate_dialog as dialog_mod

    class _QuietBox:
        # QMessageBox stand-ins so nothing blocks off-screen.
        @staticmethod
        def critical(*a, **k):
            pass

        @staticmethod
        def warning(*a, **k):
            pass

    monkeypatch.setattr(dialog_mod, "QMessageBox", _QuietBox)
    dlg = _make_dialog(qapp, plate_wcs, ra_deg=60.0, dec_deg=40.0)
    # Parent path is an existing file, so the folder can never be made.
    dest = Path(plate_wcs) / "child.fits"
    dlg.edit_dest.setText(str(dest))
    dlg._save()
    assert not dest.exists()
    assert dlg.result() != 1


def test_stretch_points_stay_apart(qapp, plate_wcs):
    dlg = _make_dialog(qapp, plate_wcs)
    # Defaults: 1.0 / 99.5 / gamma 1.0.
    assert (dlg._black_pct, dlg._white_pct, dlg._gamma) == (1.0, 99.5, 1.0)
    # The white point can be pulled down toward the black one.
    dlg._set_white(20.0)
    assert dlg._white_pct == 20.0
    assert dlg.spin_white.value() == 20.0
    # The black point cannot cross it: at least one point of headroom.
    dlg._set_black(19.6)
    assert dlg._black_pct == 19.0
    assert dlg.spin_black.value() == 19.0
    # The white point pushed onto the black one snaps back.
    dlg._set_white(18.0)
    assert dlg._white_pct == 20.0  # black at 19 plus the one point
    # Gamma is clamped at its edges.
    dlg._set_gamma(9.9)
    assert dlg._gamma == 3.0
    dlg._set_gamma(0.05)
    assert dlg._gamma == 0.2
    # "Auto stretch" returns to the known starting point.
    dlg._auto_stretch()
    assert (dlg._black_pct, dlg._white_pct, dlg._gamma) == (1.0, 99.5, 1.0)


def test_zoom_levels_scale_preview(qapp, plate_wcs):
    dlg = _make_dialog(qapp, plate_wcs)
    # 100 %: one plate pixel is one screen pixel.
    dlg.cmb_zoom.setCurrentIndex(2)
    dlg._render()
    assert (dlg.lbl_image.pixmap().width(),
            dlg.lbl_image.pixmap().height()) == (128, 128)
    # 200 % doubles it.
    dlg.cmb_zoom.setCurrentIndex(3)
    dlg._render()
    assert dlg.lbl_image.pixmap().width() == 256
    # Fit grows the plate to the window with a legibility floor (offscreen
    # the window is small, so the floor wins).
    dlg.cmb_zoom.setCurrentIndex(0)
    dlg._render()
    w = dlg.lbl_image.pixmap().width()
    assert 480 <= w <= 720


def test_nudge_shifts_and_clamps(qapp, plate_wcs):
    dlg = _make_dialog(qapp, plate_wcs, ra_deg=60.0, dec_deg=40.0)
    assert dlg._xy == [63.5, 63.5]
    dlg.spin_dx.setValue(3.0)
    dlg.spin_dy.setValue(-2.0)
    dlg._apply_nudge()
    assert dlg._xy == [66.5, 61.5]
    # Nudges that run off the plate are clamped to its edges.
    dlg.spin_dx.setValue(100.0)
    dlg.spin_dy.setValue(100.0)
    dlg._apply_nudge()
    assert dlg._xy == [127.0, 127.0]
    dlg.spin_dx.setValue(-100.0)
    dlg.spin_dy.setValue(-100.0)
    dlg._apply_nudge()
    assert dlg._xy == [27.0, 27.0]


def test_click_places_marker(qapp, plate_wcs):
    dlg = _make_dialog(qapp, plate_wcs, ra_deg=60.0, dec_deg=40.0)
    # 100 % zoom and a same-size label: the click pixel is the plate pixel.
    dlg.cmb_zoom.setCurrentIndex(2)
    dlg._render()
    dlg.lbl_image.resize(128, 128)
    dlg._image_clicked(_Click(10.0, 20.0))
    # Screen up is plate down: the y is flipped.
    assert dlg._xy == [10.0, 107.0]
    # Bigger label than the image: the centring margin is stripped off.
    dlg.lbl_image.resize(480, 480)
    dlg._image_clicked(_Click(186.0, 196.0))  # 176 margin + (10, 20)
    assert dlg._xy == [10.0, 107.0]
    # A click outside the image leaves the marker where it is.
    dlg._image_clicked(_Click(3000.0, 3000.0))
    assert dlg._xy == [10.0, 107.0]


def test_default_dest_name_and_folder(qapp, plate_wcs, tmp_path):
    dlg = _make_dialog(qapp, plate_wcs)
    solo = dlg._default_dest(None, "SN 2026 test!")
    assert solo.endswith("SN2026test_annotated.fits")
    # A project with its own storage dir gets it under that dir.
    proj = {"id": 7, "object_name": "SN 2026 test!", "root_dir": str(tmp_path)}
    under = dlg._default_dest(proj, "SN 2026 test!")
    assert under.startswith(str(tmp_path))
    assert under.endswith("SN2026test_annotated.fits")
