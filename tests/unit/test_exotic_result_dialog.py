############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the EXOTIC result window (ADR-052 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The window an observer opens after a reduction: its numbers, the light
curve EXOTIC drew and every file it wrote, each one a double click from
the system. It must never invent a number (a failed run says so) and never
hide a file (the list is built from what is on disk). Offscreen, no
network.
"""

import datetime
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


_PARAMS = {"tmid": 2458107.7146, "tmid_err": 0.0011, "rprs": 0.1612,
           "rprs_err": 0.0037, "depth": 0.026, "depth_err": 0.0012,
           "inc": 85.1, "inc_err": 0.48, "duration_d": 0.137,
           "duration_err": 0.0023, "scatter_pct": 0.61,
           "aperture": 3.95, "annulus": 6.64, "best_comp": None}


def _products(tmp_path, figure=True, size=(200, 120)):
    # @return: a work folder shaped like a real reduction's (2026-10-01)
    out = tmp_path / "exotic"
    temp = out / "temp"
    temp.mkdir(parents=True)
    if figure:
        from PySide6.QtGui import QColor, QPixmap
        pix = QPixmap(*size)
        pix.fill(QColor("#202020"))
        pix.save(str(out / "FinalLightCurve_HAT-P-32 b_20-December-2017.png"))
    (temp / "FinalLightCurve_HAT-P-32 b_20-December-2017.csv").write_text("x")
    (temp / "FinalParams_HAT-P-32 b_20-December-2017.json").write_text("{}")
    (temp / "FOV_HAT-P-32 b_20-December-2017_LinearStretch.png").write_bytes(
        b"x")
    (out / "AAVSO_HAT-P-32 b_20-December-2017.txt").write_text("x")
    return out


_BADGE = {"kind_label": "Transit", "kind_color": "#6ab0ff",
          "name": "HAT-P-32 b", "next_text": "Publish the result",
          "activity_text": "measured yesterday", "progress_text": "●●○"}


def _rows(dlg):
    # @return: [(text, path), ...] of the file list
    return [(dlg._ui.lst_files.item(i).text(),
             dlg._ui.lst_files.item(i).data(Qt.UserRole))
            for i in range(dlg._ui.lst_files.count())]


def test_the_window_shows_the_numbers_and_every_file(qapp, tmp_path):
    from nightscribe.gui.exotic_result_dialog import ExoticResultDialog
    dlg = ExoticResultDialog(_products(tmp_path), params=_PARAMS,
                             title="HAT-P-32 b")
    try:
        text = dlg._ui.txt_params.toPlainText()
        assert "2458107.71460" in text and "0.00110" in text
        assert "0.1612" in text and "0.0037" in text
        assert "2.60" in text and "0.12" in text          # depth, percent
        assert "85.10" in text and "0.1370" in text
        assert "0.61" in text                             # scatter
        assert "3.95" in text and "6.64" in text          # chosen aperture
        rows = _rows(dlg)
        joined = " | ".join(t for t, _p in rows)
        assert dlg.tr("Light curve").upper() in joined
        assert dlg.tr("Field and diagnostics").upper() in joined
        assert "FinalLightCurve_HAT-P-32 b_20-December-2017.png" in joined
        assert "AAVSO_HAT-P-32 b_20-December-2017.txt" in joined
        # every row carries its path (a title does not), and the full path is
        # in the tooltip so nobody has to guess where it lives
        paths = [p for _t, p in rows if p]
        assert any(p.endswith("FOV_HAT-P-32 b_20-December-2017_LinearStretch"
                              ".png") for p in paths)
        assert any(p.endswith("FinalParams_HAT-P-32 b_20-December-2017.json")
                   for p in paths)
        assert dlg._ui.lbl_chart.pixmap() is not None
    finally:
        dlg.close()


def test_none_is_not_a_comparison_star(qapp, tmp_path):
    # EXOTIC writes the string "None" when it kept no comparison star: the
    # window must not present that as a name (seen on the reference run)
    from nightscribe.gui.exotic_result_dialog import ExoticResultDialog
    par = dict(_PARAMS, best_comp="None")
    dlg = ExoticResultDialog(_products(tmp_path), params=par, title="X")
    try:
        text = dlg._ui.txt_params.toPlainText()
        assert "comparison star" not in text
        assert "aperture 3.95" in text          # the rest still shows
    finally:
        dlg.close()


def test_a_run_without_a_result_says_so(qapp, tmp_path):
    # a failed reduction leaves no parameters and no figure: the window says
    # it, instead of showing zeros and an empty chart
    from nightscribe.gui.exotic_result_dialog import ExoticResultDialog
    out = tmp_path / "exotic"
    out.mkdir()
    dlg = ExoticResultDialog(out, params={}, title="X")
    try:
        assert "did not leave a fitted result" in \
            dlg._ui.txt_params.toPlainText()
        assert "no files" in dlg._ui.lbl_files.text()
        assert "No figure" in dlg._ui.lbl_chart.text()
        assert not dlg._ui.btn_save.isVisibleTo(dlg)   # no visit to save into
    finally:
        dlg.close()


def test_save_registers_and_reports(qapp, tmp_path):
    from nightscribe.gui.exotic_result_dialog import ExoticResultDialog
    calls = []

    def save():
        calls.append(True)
        return 3

    dlg = ExoticResultDialog(_products(tmp_path), params=_PARAMS,
                             title="X", save_fn=save)
    try:
        assert dlg._ui.btn_save.isVisibleTo(dlg)
        dlg._ui.btn_save.click()
        assert calls
        assert "3" in dlg._ui.lbl_files.text()
    finally:
        dlg.close()


def test_save_never_leaves_a_dead_window(qapp, tmp_path):
    # the host may fail (a locked database, a removed folder): the window
    # says it instead of dying
    from nightscribe.gui.exotic_result_dialog import ExoticResultDialog

    def boom():
        raise OSError("disk on fire")

    dlg = ExoticResultDialog(_products(tmp_path), params=_PARAMS,
                             title="X", save_fn=boom)
    try:
        dlg._ui.btn_save.click()
        assert "disk on fire" in dlg._ui.lbl_files.text()
    finally:
        dlg.close()


def test_a_double_click_opens_the_file_with_the_system(qapp, tmp_path,
                                                       monkeypatch):
    from nightscribe.gui import exotic_result_dialog as erd

    opened = []

    class _Fake:
        @staticmethod
        def openUrl(url):
            opened.append(url.toString())

    monkeypatch.setattr(erd, "QDesktopServices", _Fake)
    dlg = erd.ExoticResultDialog(_products(tmp_path), params=_PARAMS)
    try:
        row = next(i for i in range(dlg._ui.lst_files.count())
                   if dlg._ui.lst_files.item(i).data(Qt.UserRole))
        dlg._ui.lst_files.itemDoubleClicked.emit(
            dlg._ui.lst_files.item(row))
        assert opened and opened[0].startswith("file://")
        # a group title is not a file: clicking it opens nothing
        n = len(opened)
        dlg._ui.lst_files.itemDoubleClicked.emit(
            dlg._ui.lst_files.item(0))
        assert len(opened) == n
        # and the folder door opens the work folder itself (the URL, not the
        # path: on Windows the two spell the same folder differently)
        from PySide6.QtCore import QUrl
        dlg._ui.btn_folder.click()
        assert opened[-1] == QUrl.fromLocalFile(str(dlg._out_dir)).toString()
    finally:
        dlg.close()


# ---------------- breathing room and the title (2026-10-01) ----------------

def test_the_controls_breathe_and_the_chart_fits(qapp, tmp_path):
    # Reported: the chart barely fitted and the bottom buttons sat on the
    # edge. Measured before: zero margins (the Close button ended at
    # y=860 of a 860 window) and a 609x429 figure in a 960x412 label, its
    # bottom 17 px cut off. The figure now fits its label, at any size.
    from nightscribe.gui.exotic_result_dialog import ExoticResultDialog
    dlg = ExoticResultDialog(_products(tmp_path, size=(1600, 1000)),
                             params=_PARAMS, badge=_BADGE, title="X")
    try:
        for size in ((1020, 940), (720, 700)):
            dlg.resize(*size)
            dlg.show()
            qapp.processEvents()
            m = dlg.layout().contentsMargins()
            assert (m.left(), m.top(), m.right(), m.bottom()) == (11,) * 4
            btn = dlg._ui.btn_close.geometry()
            assert dlg.height() - (btn.y() + btn.height()) == 11
            pm = dlg._ui.lbl_chart.pixmap()
            box = dlg._ui.lbl_chart.geometry()
            assert pm.width() <= box.width() and pm.height() <= box.height()
        # a small figure is never blown up: it stays as it is
        dlg.close()
        small = ExoticResultDialog(_products(tmp_path / "small",
                                             size=(200, 120)),
                                   params=_PARAMS, badge=_BADGE, title="X")
        try:
            small.resize(1020, 940)
            small.show()
            qapp.processEvents()
            assert small._ui.lbl_chart.pixmap().size() == \
                small._chart_pixmap.size()
        finally:
            small.close()
    finally:
        dlg.close()


def test_the_title_is_the_projects_own_badge(qapp, tmp_path):
    # The window's title is the project's identity in the list's own
    # language (same widget and payload as the workbench's badge), and the
    # next action stays out: this window shows a finished reduction, so
    # "what is next" belongs to the workbench.
    from nightscribe.gui.exotic_result_dialog import ExoticResultDialog
    dlg = ExoticResultDialog(_products(tmp_path), params=_PARAMS,
                             badge=_BADGE, title="HAT-P-32 b",
                             when=datetime.datetime(2026, 10, 1, 4, 35))
    try:
        assert dlg.windowTitle() == \
            dlg.tr("EXOTIC reduction of {0}").format("HAT-P-32 b")
        assert dlg.badge.isVisibleTo(dlg)
        assert dlg.badge.lbl_name.text() == "HAT-P-32 b"
        assert dlg.badge.lbl_kind.text() == "Transit"
        assert "#6ab0ff" in dlg.badge.lbl_kind.styleSheet()   # the kind's hue
        assert not dlg.badge.lbl_next.isVisibleTo(dlg)
        assert "Publish the result" not in dlg.badge.toolTip()
        assert "Transit" in dlg.badge.toolTip()               # the identity stays
        # the window says what it is, when it ran and where the files are
        sub = dlg._ui.lbl_subtitle.text()
        assert "EXOTIC reduction" in sub and "2026-10-01 04:35" in sub
        assert str(dlg._out_dir) in sub
    finally:
        dlg.close()


def test_without_a_project_the_badge_hides_itself(qapp, tmp_path):
    from nightscribe.gui.exotic_result_dialog import ExoticResultDialog
    dlg = ExoticResultDialog(_products(tmp_path), params=_PARAMS, badge=None)
    try:
        assert not dlg.badge.isVisibleTo(dlg)
        assert dlg.windowTitle() == dlg.tr("EXOTIC reduction")
    finally:
        dlg.close()
