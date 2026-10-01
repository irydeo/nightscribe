"""Sonda temporal (se borra): mide en el runner las tres que fallan."""

import os
import time
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
    print("\nfont family:", app.font().family(),
          "| px:", app.font().pixelSize(), app.font().pointSize())
    return app


@pytest.fixture
def dlg(qapp):
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.state.load(MONO)
    d.tabs.setCurrentWidget(d.tab_photometry)
    qapp.processEvents()
    yield d
    d.tab_blink.shutdown()
    d.view._render_timer.stop()
    d.deleteLater()


def test_diag_series_block(dlg, qapp):
    from PySide6.QtWidgets import QLabel, QWidget
    tab = dlg.tab_measure
    dlg.set_series_hook(lambda: {"pid": 1, "session_id": 2, "paths": []})
    qapp.processEvents()
    for px in (13, 20):
        tab.grp_series.setStyleSheet("* { font-size: %dpx; }" % px)
        qapp.processEvents()
        print("\n== bloque a %dpx: %d ==" % (
            px, tab.grp_series.minimumSizeHint().width()))
        rows = []
        for w in tab.grp_series.findChildren(QWidget):
            if not w.isVisibleTo(tab.grp_series):
                continue
            text = w.text() if hasattr(w, "text") else ""
            rows.append((w.minimumSizeHint().width(),
                         type(w).__name__, w.objectName() or "-", text[:40]))
        for h, t, n, tx in sorted(rows, reverse=True)[:8]:
            print("   %5d %-14s %-20s %r" % (h, t, n, tx))
        for name in ("row_series_group", "row_series_doors",
                     "row_series_run", "row_series_scope",
                     "row_series_info"):
            lay = getattr(tab._ui, name, None)
            if lay is not None:
                print("   row %-18s minimumSize = %d" % (
                    name, lay.minimumSize().width()))


def test_diag_manual_window(dlg, qapp):
    dlg.tab_compare.btn_manual.click()
    qapp.processEvents()
    w = dlg.tab_compare.manual
    w.show()
    qapp.processEvents()
    time.sleep(0.3)
    qapp.processEvents()
    print("\nmanual: minimumHeight %d | minimumSizeHint %d | size %s" % (
        w.minimumHeight(), w.minimumSizeHint().height(), w.size()))
    last = w.btn_seq_open
    print("   btn_seq_open text=%r minHint=%s" % (
        last.text(), last.minimumSizeHint()))
    lay = w.layout()
    print("   layout minimumSize:", lay.minimumSize(), "sizeHint:", lay.sizeHint())
    print("   _fitted:", getattr(w, "_fitted", None))


def test_diag_band(dlg, qapp):
    import hashlib
    dlg.state.load(MONO)
    qapp.processEvents()

    def strip():
        img = dlg.view.grab().toImage()
        h = int(getattr(dlg.view, "_title_h", 0) or 0)
        crop = min((h + 4) if h > 0 else 60, img.height())
        return (h, crop, img.width(),
                hashlib.sha1(bytes(img.copy(0, 0, img.width(), crop).bits())
                             ).hexdigest())

    print("\nband: _title_h=%s" % getattr(dlg.view, "_title_h", "?"))
    dlg.set_object({"name": "AT 2026zji", "ra": 20.0, "dec": 62.0,
                    "mag": 17.1})
    a = strip()
    time.sleep(0.5)
    qapp.processEvents()
    b = strip()
    dlg.set_object({"name": "AT 2026zji", "ra": 20.0, "dec": 62.0,
                    "mag": 15.0})
    c = strip()
    time.sleep(0.5)
    qapp.processEvents()
    d = strip()
    print("   tras 17.1:", a)
    print("   +0.5 s  :", b)
    print("   tras 15.0:", c)
    print("   +0.5 s  :", d)
    band = dlg._chart_band()["lines"][0]
    print("   band lines:", [(s["field"], s["text"]) for s in band])
