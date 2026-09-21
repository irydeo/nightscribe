############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: comparison chart in the Follow-up tab
# (ADR-042, phase 3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for the follow-up integration of the photometric
sequence (ADR-042):

  * the Follow-up tab of a photometric project shows the primary
    «Comparison chart…» button and the plain-language status line;
  * a landed SequenceWorker payload registers the files, saves the
    sequence into the project context and refreshes the status line.

No network anywhere: the worker's load_field is faked and the chart
viewer is replaced by a capture stub.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module", autouse=True)
def _point_db_at_tmpdir(tmp_path_factory):
    # the shared db singleton goes to a throwaway file (test_projects_hub
    # pattern), so project CRUD never touches the real database
    import nightscribe.core.db as dbmod
    import nightscribe.gui.main_window as mw
    old_dbmod, old_mw = dbmod.db, mw.db
    tmp = dbmod.Database(tmp_path_factory.mktemp("seqdb") / "t.db")
    dbmod.db = tmp
    mw.db = tmp
    yield
    dbmod.db = old_dbmod
    mw.db = old_mw


@pytest.fixture(scope="module")
def window(_point_db_at_tmpdir):
    from PySide6.QtWidgets import QApplication
    from nightscribe.config import config
    from nightscribe.gui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply_theme(app)
    from nightscribe.gui.main_window import MainWindow
    orig_cfg = config.is_configured
    config.is_configured = lambda: False
    w = MainWindow()
    w._now_timer.stop()
    w._blink_timer.stop()
    w._blink_render_timer.stop()
    yield w
    config.is_configured = orig_cfg
    w.close()


VAR_CTX = {"ra_deg": 291.366, "dec_deg": 42.784, "mag": 13.5}


def _variable_project():
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    return project.create(dbmod.db, "variable", "V0001 Cyg",
                          dict(VAR_CTX))


def _fake_entry(i, kind="comp"):
    return {"name": "Check" if kind == "check" else f"Comp{i}",
            "kind": kind,
            "star": {"id": f"2100{i}", "name": None, "ra": 291.36,
                     "dec": 42.78, "mag": 12.0 + 0.1 * i, "band": "G",
                     "catalog": "Gaia EDR3", "bands": [
                         {"label": "G", "value": 12.0 + 0.1 * i,
                          "err": 0.003, "derived": False}],
                     "bv": 0.6, "color_origin": "estimated", "vsx": None},
            "why": {"es": "más brillante", "en": "brighter"}}


def _fake_payload(tmp_path, n=4):
    import nightscribe.core.db as dbmod
    from nightscribe.core import compstars
    entries = [_fake_entry(i) for i in range(1, n + 1)]
    entries.append(_fake_entry(0, "check"))
    return {"status": "ok", "entries": entries, "target_mag": 13.5,
            "catalog": "gaia", "catalog_name": "Gaia EDR3",
            "fov_arcmin": 18.0, "n_variables": 1, "vsx_warning": False,
            "image": None, "wcs": None, "img_label": "DSS2 color (CDS)",
            "field": {"stars": [e["star"] for e in entries],
                      "variables": [], "catalog": "gaia",
                      "catalog_name": "Gaia EDR3", "band": "G",
                      "center": (291.366, 42.784), "fov_arcmin": 18.0,
                      "vsx_warning": False}}


def _open_followup(window, p):
    # Selects the project and opens its Follow-up tab (no list signals, no
    # object-panel worker: the page build only needs _current_project).
    window._current_project = p
    window._build_project_page(p)
    window._show_tab("followup")


def test_followup_shows_the_primary_button(window):
    p = _variable_project()
    _open_followup(window, p)
    from PySide6.QtWidgets import QPushButton
    buttons = window._tab_pages["followup"].findChildren(QPushButton)
    labels = [b.text() for b in buttons]
    assert any("Comparison chart" in b for b in labels)
    # the status line starts empty, in plain words
    lbl = window._project_widgets.get("fu_sequence")
    assert lbl is not None
    assert "No comparison sequence yet" in lbl.text()


def test_sequence_done_opens_the_picker(window, tmp_path, monkeypatch):
    # on the worker's ok payload the interactive dialog opens; nothing is
    # saved until the user confirms inside it
    import nightscribe.gui.seqchart_dialog as sd
    seen = []

    class FakeDialog:
        def __init__(self, *args, **kwargs):
            seen.append((args, kwargs))

        def exec(self):
            return 0

    monkeypatch.setattr(sd, "SeqChartDialog", FakeDialog)
    p = _variable_project()
    _open_followup(window, p)
    out = _fake_payload(tmp_path)
    window._fu_sequence_done(p["id"], out, save_campaign=False)
    assert len(seen) == 1
    args, kwargs = seen[0]
    # (parent, target_name, field, entries, ...)
    assert args[2] is out["field"] and args[3] is out["entries"]
    # nothing persisted yet
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p2 = project.get(dbmod.db, p["id"])
    assert "sequence" not in (p2.get("context") or {})


def test_sequence_save_registers_and_updates(window, tmp_path):
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p = _variable_project()
    _open_followup(window, p)
    out = _fake_payload(tmp_path)
    csv_path = tmp_path / "seq.csv"
    csv_path.write_text("# test\n", encoding="utf-8")
    png_path = tmp_path / "carta.png"
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n")
    window._fu_sequence_save(p["id"], out["entries"],
                             {"csv": str(csv_path), "png": str(png_path)},
                             out, save_campaign=False)
    # the context carries the sequence
    p2 = project.get(dbmod.db, p["id"])
    seq = p2["context"]["sequence"]
    assert seq["catalog"] == "gaia"
    assert len(seq["entries"]) == 5
    # both files are registered
    files = project.list_files(dbmod.db, p["id"])
    kinds = sorted(f["kind"] for f in files)
    assert kinds == ["chart", "report"]
    # the status line now names the sequence
    lbl = window._project_widgets.get("fu_sequence")
    assert "4" in lbl.text() and "Gaia EDR3" in lbl.text()


def test_sequence_done_error_only_warns(window, tmp_path):
    p = _variable_project()
    _open_followup(window, p)
    window._fu_sequence_done(p["id"], {"status": "error",
                                       "error": "VizieR down"}, False)
    # nothing saved, nothing broken
    import nightscribe.core.db as dbmod
    from nightscribe.core import project
    p2 = project.get(dbmod.db, p["id"])
    assert "sequence" not in (p2.get("context") or {})


def _fake_field(catalog, ra, dec, fov):
    # the field built from the synthetic Gaia fixture (no network)
    from pathlib import Path as _P
    from nightscribe.core import compstars
    from nightscribe.core.sources import vizier
    fix = _P(__file__).resolve().parent.parent / "fixtures"
    center = (291.366, 42.784)
    text = (fix / "vizier_gaia.tsv").read_bytes().decode("utf-8")
    spec = vizier.CATALOGS["gaia"]
    rows = vizier.parse_tsv(text, spec["required"], spec["ra"],
                            spec["dec"])[1]
    stars = compstars.build_stars(rows, center, fov / 60.0, "gaia")
    return {"stars": stars, "variables": [], "catalog": "gaia",
            "catalog_name": "Gaia EDR3", "band": "G",
            "center": center, "fov_arcmin": fov, "vsx_warning": False}


def test_sequence_worker_with_faked_field(tmp_path, monkeypatch):
    # the worker runs field + proposal + background off-GUI with the
    # network parts faked, and writes no files (the dialog owns exports)
    from nightscribe.core import compstars
    from nightscribe.core.sources import cutouts
    monkeypatch.setattr(compstars, "load_field", _fake_field)
    monkeypatch.setattr(cutouts, "reference_cutout", lambda *a, **k: None)
    from nightscribe.gui.workers import SequenceWorker
    center = (291.366, 42.784)
    w = SequenceWorker("V0001 Cyg", center[0], center[1], "gaia", 18.0,
                       4, 13.5, None, "en")
    seen = []
    w.finished.connect(seen.append)
    w.run()
    assert len(seen) == 1
    out = seen[0]
    assert out["status"] == "ok"
    assert len(out["entries"]) == 5          # 4 comps + check
    assert out["field"]["stars"]
    assert out["image"] is None and out["wcs"] is None
    assert "csv" not in out and "png" not in out
