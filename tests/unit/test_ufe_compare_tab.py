############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: UFE Compare tab (ADR-044, phase F)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for gui/ufe_compare_tab.py: the comparison-sequence
picker on the shared plate view. Field generation goes through a fake
UfeFieldWorker (no network); stars come from a synthetic catalog mapped
through the plate's real WCS. The legacy SeqChartDialog is untouched.
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


def _spin_events(ms=20):
    # A plain processEvents() does NOT deliver a deleteLater, but a real
    # event loop does: let it run long enough for the deferred deletion.
    from PySide6.QtCore import QEventLoop, QTimer
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


@pytest.fixture
def dlg(qapp):
    from nightscribe.gui.ufe_dialog import UfeDialog
    d = UfeDialog()
    d.resize(1280, 860)
    d.show()
    d.state.load(MONO)
    d.tabs.setCurrentWidget(d.tab_photometry)   # take the stage
    d.tab_photometry.set_mode("sequence")
    yield d
    d.tab_blink.shutdown()
    d.view._render_timer.stop()
    d.deleteLater()


def _field(dlg, n=60, with_vsx=True):
    # A synthetic catalog field around the plate centre (real WCS), one
    # VSX variable matched to the 6th star.
    rng = np.random.default_rng(3)
    cra, cdec = dlg.state.wcs.center()
    stars = []
    for _i in range(n):
        ra = cra + rng.uniform(-0.15, 0.15)
        dec = cdec + rng.uniform(-0.15, 0.15)
        mag = 11.0 + rng.uniform(0, 5)
        stars.append({"id": f"J{ra:.4f}{dec:+.4f}", "name": None,
                      "ra": ra, "dec": dec, "mag": mag, "band": "G",
                      "catalog": "Gaia EDR3",
                      "bands": [{"label": "G", "value": mag, "err": 0.003,
                                 "derived": False}],
                      "bv": 0.8, "color_origin": "direct", "vsx": None})
    variables = []
    if with_vsx:
        stars[5]["vsx"] = {"name": "V0817 Cyg", "type": "DSCT"}
        variables.append({"star": stars[5]})
    return {"stars": stars, "variables": variables, "catalog": "gaia",
            "catalog_name": "Gaia EDR3", "band": "G",
            "center": (cra, cdec), "fov_arcmin": 36.0,
            "vsx_warning": False}


class _FakeFieldWorker:
    # Synchronous UfeFieldWorker double.
    def __init__(self, catalog, ra, dec, fov, field=None):
        from PySide6.QtCore import QObject, Signal
        self._field = field
        self.query = (catalog, ra, dec, fov)

        class _Sig(QObject):
            finished = Signal(object)
            progress = Signal(dict)
        self._sig = _Sig()
        self.finished = self._sig.finished
        self.progress = self._sig.progress

    def start(self):
        # like the real worker: a stage lands before the field arrives
        self.progress.emit({"es": "Consultando el catálogo Gaia EDR3…",
                            "en": "Querying the Gaia EDR3 catalog…"})
        self.finished.emit(self._field or {})


class _HoldingFieldWorker(_FakeFieldWorker):
    # same double, but it hands the field over when told instead of in
    # start(): lets the test observe the mid-flight state (the busy
    # dialog, the stage label) before the result lands
    def start(self):
        self.progress.emit({"es": "Consultando el catálogo Gaia EDR3…",
                            "en": "Querying the Gaia EDR3 catalog…"})

    def land(self):
        self.finished.emit(self._field or {})


def test_tab_is_real_and_enabled(dlg):
    titles = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert titles == ["Blink", "Photometry", "Annotate"]
    assert dlg.tab_compare.isEnabled()
    assert dlg.tab_compare.edt_target.text() == "sn2026zji_new_image"


def test_generate_needs_a_wcs(dlg, tmp_path):
    from test_fits_annotate import _make_fits
    dlg.state.load(_make_fits(tmp_path / "plain.fits"))
    dlg.tab_compare._on_generate()
    assert "WCS" in dlg.tab_compare.lbl_status.text()
    assert dlg.tab_compare._worker is None


def test_generate_queries_around_the_plate_centre(dlg, monkeypatch):
    tab = dlg.tab_compare
    captured = {}

    def fake(catalog, ra, dec, fov):
        captured["args"] = (catalog, ra, dec, fov)
        return _FakeFieldWorker(catalog, ra, dec, fov, field=_field(dlg))
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker", fake)
    tab._on_generate()
    catalog, ra, dec, fov = captured["args"]
    assert catalog == "gaia"
    cra, cdec = dlg.state.wcs.center()
    assert ra == pytest.approx(cra) and dec == pytest.approx(cdec)
    # the FOV is the plate's long side in arcminutes (~36' at 1.07"/px)
    assert 30.0 < fov < 40.0
    assert len(tab._stars) == 60
    assert "60" in tab.lbl_status.text()
    assert len(tab._items) > 0                  # overlays on stage


def test_generate_failure_is_honest(dlg, monkeypatch):
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker",
                        lambda *a: _FakeFieldWorker(*a, field=None))
    dlg.tab_compare._on_generate()
    assert "failed" in dlg.tab_compare.lbl_status.text()


def test_generate_reports_the_pipeline_stages(dlg, monkeypatch):
    # The catalog queries take a while; their stages must reach the
    # status line in the observer's language. Regression: the UFE
    # rewrite dropped the .progress wiring that the legacy sequence
    # dialog kept (Blink and Measure still report theirs).
    created = {}

    def fake(catalog, ra, dec, fov):
        w = _FakeFieldWorker(catalog, ra, dec, fov, field=_field(dlg))
        created["worker"] = w
        return w
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker", fake)
    tab = dlg.tab_compare
    tab._on_generate()
    assert len(tab._stars) == 60
    # the finished handler overwrote the first stage: emit the second
    # one to prove the progress connection is live, not just declared
    created["worker"].progress.emit(
        {"es": "Comprobando variables conocidas (VSX)…",
         "en": "Checking known variables (VSX)…"})
    text = tab.lbl_status.text()
    assert "Comprobando variables conocidas" in text     # Spanish by default
    assert "Checking known variables" not in text


def test_generate_runs_behind_the_busy_dialog(dlg, monkeypatch):
    # The catalog queries take seconds: the legacy sequence flow covered
    # them with a modal, cancel-less busy dialog (a status line alone
    # reads as "nothing is happening"), and the UFE rewrite dropped it.
    # It must follow the stages and be reaped when the field lands.
    created = {}

    def fake(catalog, ra, dec, fov):
        w = _HoldingFieldWorker(catalog, ra, dec, fov, field=_field(dlg))
        created["worker"] = w
        return w
    monkeypatch.setattr("nightscribe.gui.workers.UfeFieldWorker", fake)
    tab = dlg.tab_compare

    from PySide6.QtWidgets import QProgressDialog, QPushButton
    tab._on_generate()
    waits = tab.findChildren(QProgressDialog)
    assert len(waits) == 1
    wait = waits[0]
    assert wait.windowTitle() == "Comparison field"
    assert not wait.findChildren(QPushButton)  # no cancel button: nothing to abort
    assert wait.maximum() == 0               # indeterminate
    assert "Consultando el catálogo Gaia EDR3" in wait.labelText()
    assert "Consultando el catálogo Gaia EDR3" in tab.lbl_status.text()
    # the field lands: the dialog is reaped before the result is taken
    created["worker"].land()
    _spin_events()                              # let the deleteLater run
    assert not tab.findChildren(QProgressDialog)
    assert len(tab._stars) == 60             # the result still landed


def test_click_toggles_comp_and_check(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    from PySide6.QtCore import QPointF
    s = tab._stars[0]
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert [(e["name"], e["kind"]) for e in tab._entries] == \
        [("Comp1", "comp")]
    tab.rdo_check.setChecked(True)
    s2 = tab._stars[1]
    dlg.view.scene_clicked.emit(QPointF(s2["_sx"], s2["_sy"]))
    assert tab._entries[1]["kind"] == "check"
    assert tab._entries[1]["name"] == "Check"
    # a second click on the same star removes it
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert len(tab._entries) == 1
    assert tab.table.rowCount() == 1


def test_vsx_star_is_refused_with_a_reason(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    from PySide6.QtCore import QPointF
    s5 = tab._stars[5]
    dlg.view.scene_clicked.emit(QPointF(s5["_sx"], s5["_sy"]))
    assert tab._entries == []
    assert "V0817 Cyg" in tab.lbl_status.text()


def test_propose_fills_comps_and_check(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab.spn_mag.setValue(12.5)
    tab._on_propose()
    kinds = [e["kind"] for e in tab._entries]
    assert kinds.count("comp") >= 6 and "check" in kinds
    assert tab.table.rowCount() == len(tab._entries)
    # the proposed stars carry the entry rings as overlays
    assert len(tab._entry_items) == 2 * len(tab._entries)


def test_propose_without_a_field_points_the_way(dlg):
    # No field yet: the button used to do nothing and stay silent, which
    # the observer read as "it is thinking". It must now say what to do.
    tab = dlg.tab_compare
    assert tab._field is None
    tab._on_propose()
    assert "Generate the field first" in tab.lbl_status.text()


def test_table_edits_flow_to_the_sequence(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    tab.table.cellWidget(0, 1).setCurrentIndex(1)     # Comp -> Check
    assert tab._entries[0]["kind"] == "check"
    tab.table.item(0, 0).setText("MiComp")
    tab._flush_table()
    assert tab._entries[0]["name"] == "MiComp"
    tab._remove(0)
    assert tab.table.rowCount() == len(tab._entries)
    tab._on_clear()
    assert tab._entries == [] and tab.table.rowCount() == 0


def test_catalog_labels_toggle(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    assert any(it.isVisible() for it, _ in tab._catalog_items)
    tab.chk_labels.setChecked(False)
    assert all(not it.isVisible() for it, _ in tab._catalog_items)


def test_probe_star_info_and_pixel_fallback(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    s = tab._stars[0]
    hit, lines = tab._probe(s["_sx"], s["_sy"])
    assert hit and lines[0].startswith("Gaia EDR3")
    hit, lines = tab._probe(5.0, 5.0)
    assert hit and "DN" in lines[0]              # the state's pixel probe


def test_leaving_the_tab_restores_the_pixel_probe(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    assert dlg.view._hover_probe == tab._probe
    dlg.tabs.setCurrentIndex(0)
    assert dlg.view._hover_probe == dlg.state.probe_text
    assert tab._items == []
    dlg.tabs.setCurrentWidget(dlg.tab_photometry)   # back: sequence resumes
    assert len(tab._items) > 0


def test_csv_export_writes_the_sequence(dlg, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    out = tmp_path / "secuencia.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(out), "")))
    tab._export_csv()
    text = out.read_text()
    assert "# target: sn2026zji_new_image" in text
    assert "Comparison" in text and "Check" in text
    assert "Written to" in tab.lbl_status.text()


def test_loading_a_new_plate_invalidates_the_field(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_propose()
    dlg.state.load(MONO)
    assert tab._field is None and tab._entries == []
    assert tab.table.rowCount() == 0


def test_sequence_overlays_survive_switching_to_measure(dlg):
    # the sequence is the Measure section's input: switching sections keeps
    # rings and labels visible (with clicks disarmed); only leaving the
    # Photometry tab for real drops them
    from PySide6.QtCore import QPointF
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    s = tab._stars[0]
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert len(tab._entries) == 1
    assert len(tab._items) > 0
    dlg.tab_photometry.set_mode("measure")
    assert len(tab._items) > 0                  # still drawn
    assert not tab._active                      # but disarmed
    # and the star probe still answers while measuring
    hit, lines = dlg.view._hover_probe(s["_sx"], s["_sy"])
    assert hit and "Gaia EDR3" in lines[0]
    # coming back to the sequence restores everything
    dlg.tab_photometry.set_mode("sequence")
    assert len(tab._items) > 0
    dlg.tabs.setCurrentWidget(dlg.tab_annotate)
    assert tab._items == []


# ------------------------------------------------- target mark (toggleable)

def _target_mark(tab):
    # The amber ring that marks the target. The ticks and the name share
    # the colour, but only the ring is an ellipse at pen width 2.2.
    # @return: the ring item, or None when the mark is not drawn
    from PySide6.QtWidgets import QGraphicsEllipseItem
    from nightscribe.viz import palette
    for it in tab._items:
        if isinstance(it, QGraphicsEllipseItem) and it.pen().widthF() == 2.2 \
                and it.pen().color().name().lower() == palette.ACCENT.lower():
            return it
    return None


def test_target_mark_is_on_by_default_at_the_plate_centre(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    assert tab.chk_target.isChecked()
    w, h = dlg.state.plate_shape
    mark = _target_mark(tab)
    assert mark is not None
    assert mark.rect().center().x() == pytest.approx(w / 2.0)
    assert mark.rect().center().y() == pytest.approx(h / 2.0)


def test_target_mark_toggleable(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    assert _target_mark(tab) is not None
    tab.chk_target.setChecked(False)
    assert _target_mark(tab) is None
    tab.chk_target.setChecked(True)
    assert _target_mark(tab) is not None
    # the catalogue and the sequence are untouched by the toggle
    assert any(it.isVisible() for it, _ in tab._catalog_items)


def test_move_target_refuses_without_a_field(dlg):
    tab = dlg.tab_compare
    assert tab._field is None
    tab._on_move_requested()
    assert "Load a plate and build the field first" in tab.lbl_status.text()
    assert not tab._moving_target
    assert tab.chk_target.isChecked()            # visibility unchanged


def test_move_target_arms_and_places_on_click(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_move_requested()
    assert tab._moving_target
    assert "Click the plate where the target really is" in \
        tab.lbl_status.text()
    # the armed mode is readable in the hover probe
    hit, lines = tab._probe(5.0, 5.0)
    assert hit and lines == ["Click: move the target mark here"]
    # the click lands the mark there, disarms, and touches no star
    from PySide6.QtCore import QPointF
    dlg.view.scene_clicked.emit(QPointF(40.0, 60.0))
    assert not tab._moving_target
    assert tab._target_pos == (40.0, 60.0)
    assert "Target mark placed at (40, 60)" in tab.lbl_status.text()
    assert tab._entries == []
    mark = _target_mark(tab)
    assert mark is not None
    assert mark.rect().center().x() == pytest.approx(40.0)
    assert mark.rect().center().y() == pytest.approx(60.0)


def test_move_target_clamps_inside_the_plate(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_move_requested()
    from PySide6.QtCore import QPointF
    dlg.view.scene_clicked.emit(QPointF(-50.0, 1e6))
    w, h = dlg.state.plate_shape
    assert tab._target_pos == (0.0, float(h))


def test_placement_disarms_and_normal_clicks_resume(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_move_requested()
    from PySide6.QtCore import QPointF
    dlg.view.scene_clicked.emit(QPointF(20.0, 20.0))
    assert not tab._moving_target
    s = tab._stars[0]
    dlg.view.scene_clicked.emit(QPointF(s["_sx"], s["_sy"]))
    assert [(e["name"], e["kind"]) for e in tab._entries] == \
        [("Comp1", "comp")]


def test_new_plate_resets_the_target_mark(dlg):
    tab = dlg.tab_compare
    tab._on_field_ready(_field(dlg))
    tab._on_move_requested()
    assert tab._moving_target
    from PySide6.QtCore import QPointF
    dlg.view.scene_clicked.emit(QPointF(123.0, 321.0))
    assert tab._target_pos == (123.0, 321.0)
    dlg.state.load(MONO)
    assert tab._target_pos is None               # back to the plate centre
    assert not tab._moving_target
    # an armed placement never survives into the new plate either
    tab._on_field_ready(_field(dlg))
    tab._on_move_requested()
    assert tab._moving_target
    dlg.state.load(MONO)
    assert not tab._moving_target
