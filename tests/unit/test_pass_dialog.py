############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the campaign pass dialog (E5c)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The dialog that prepares a campaign pass.

It decides no science: the grouping by field, the sequence precedence and
the "no usable pointing" refusal belong to core.campaign and to the
reference frame, and this dialog shows them. What is tested here is that it
shows them HONESTLY: who travels, who stays out and why, and that it
refuses to accept a pass it cannot place on the pixels.
"""

import os
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import test_series_measure as series_t          # noqa: E402
from nightscribe.core import campaign as camp_mod          # noqa: E402
from nightscribe.core import followup as fu                # noqa: E402
from nightscribe.core import project as proj_mod           # noqa: E402
from nightscribe.core.db import Database                   # noqa: E402
from nightscribe.gui.pass_dialog import PassDialog         # noqa: E402


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def _card(key, value=None):
    s = key.ljust(8) if value is None else f"{key.ljust(8)}= {value}"
    return s[:80].ljust(80)


def _write_no_wcs(path, data, date_obs="2026-09-20T23:30:00"):
    # A frame with no pointing at all: the real V0526 Per series looks
    # like this, and it is the case the dialog must refuse.
    cards = [_card("SIMPLE", "T"), _card("BITPIX", "-32"),
             _card("NAXIS", "2"), _card("NAXIS1", str(series_t.W)),
             _card("NAXIS2", str(series_t.H)), _card("EXPTIME", "10.0"),
             _card("DATE-OBS", f"'{date_obs}'")]
    header = "".join(cards + [_card("END")]).encode("latin-1")
    header += b" " * ((2880 - len(header) % 2880) % 2880)
    raw = np.ascontiguousarray(data, dtype=">f4").tobytes()
    raw += b"\0" * ((2880 - len(raw) % 2880) % 2880)
    Path(path).write_bytes(header + raw)
    return str(path)


def _build(tmp_path, wcs_ok=True, second_offset_arcmin=0.0, n=3):
    # A campaign of three projects: A (the source visit's project, on the
    # target), B (a second object of the field, or one pushed outside the
    # frame when asked) and C (a degree away: another field entirely).
    db = Database(str(tmp_path / "t.db"))
    wcs = series_t._reference_wcs()
    seq = {"catalog": "APASS DR9", "entries": series_t._comp_set(wcs),
           "fov_arcmin": 30.0}
    cid = camp_mod.create(db, "Watch")
    camp_mod.set_sequence(db, cid, seq)
    ra_a, dec_a = wcs.pixel_to_sky(*series_t.TARGET_XY)
    ra_b, dec_b = wcs.pixel_to_sky(*series_t.SECOND_XY)
    if second_offset_arcmin:
        # still inside the 30' field, but past the edge of the 160 px
        # frame (~3'): the case the frame check must catch
        dec_b = dec_a + second_offset_arcmin / 60.0
        ra_b = ra_a
    pid_a = proj_mod.create(db, "variable", "A",
                            {"ra_deg": ra_a, "dec_deg": dec_a},
                            campaign_id=cid)["id"]
    pid_b = proj_mod.create(db, "variable", "B",
                            {"ra_deg": ra_b, "dec_deg": dec_b},
                            campaign_id=cid)["id"]
    pid_c = proj_mod.create(db, "variable", "C",
                            {"ra_deg": ra_a + 1.0, "dec_deg": dec_a},
                            campaign_id=cid)["id"]
    sid = fu.create_session(db, pid_a, obs_date="2026-09-20")
    paths = []
    for i in range(n):
        p = tmp_path / f"f{i:03d}.fits"
        data = series_t._plate_two(seed=1 + i)
        date = f"2026-09-20T23:{30 + i:02d}:00"
        if wcs_ok:
            series_t._write_plate(p, data, date_obs=date, exptime=10.0)
        else:
            _write_no_wcs(p, data, date_obs=date)
        proj_mod.add_file(db, pid_a, str(p), "fits", session_id=sid)
        paths.append(str(p))
    return db, camp_mod.get(db, cid), pid_a, pid_b, pid_c, paths, seq


def test_the_dialog_prepares_the_pass_and_says_who_stays_out(qapp, tmp_path):
    db, camp, pid_a, pid_b, pid_c, paths, _seq = _build(tmp_path)
    dlg = PassDialog(None, db_obj=db, camp=camp, lang="es")
    # the source visit is the only one with frames
    assert dlg.source() is not None
    assert dlg.source()["pid"] == pid_a
    assert sorted(dlg.source()["paths"]) == sorted(paths)
    # the pointing comes from the reference frame's own header
    assert dlg.wcs() is not None
    # A and B travel; C is another field and the dialog SAYS so
    assert sorted(t["label"] for t in dlg.targets()) == ["A", "B"]
    left = {e["project"]["object_name"]: e["reason"] for e in dlg.left_out()}
    assert "C" in left
    assert "fuera del campo" in left["C"]["es"]
    # the sequence is the campaign's (no project has its own here)
    seq, source = dlg.sequence()
    assert source == "campaign" and seq is not None
    assert dlg.band() == "V"


def test_the_source_projects_own_sequence_wins_by_default(qapp, tmp_path):
    # The precedence of core.campaign, shown: the project that owns the
    # frames built its sequence for THAT object, so it is the one offered.
    db, camp, pid_a, pid_b, pid_c, paths, seq = _build(tmp_path)
    camp_mod.set_sequence(db, camp["id"], None)
    proj_mod.update_context(db, pid_a, {"sequence": {
        "catalog": "APASS DR9", "entries": seq["entries"][:3],
        "fov_arcmin": 30.0}})
    dlg = PassDialog(None, db_obj=db, camp=camp_mod.get(db, camp["id"]),
                     lang="es")
    got, source = dlg.sequence()
    assert source == "project"
    assert len(got["entries"]) == 3


def test_without_a_pointing_the_dialog_refuses_to_promise(qapp, tmp_path):
    # The real V0526 Per series has no WCS in its headers: without a
    # pointing there is no way to know where an object falls on the
    # pixels, so the dialog says it and does not let the pass start.
    db, camp, pid_a, pid_b, pid_c, paths, _seq = _build(
        tmp_path, wcs_ok=False)
    dlg = PassDialog(None, db_obj=db, camp=camp, lang="es")
    assert dlg.wcs() is None
    assert "pointing" in dlg.lbl_wcs.text() or "WCS" in dlg.lbl_wcs.text()
    ok = dlg._ui.buttonBox.button(QDialogButtonBox.StandardButton.Ok)
    assert ok.isEnabled() is False


def test_a_target_inside_the_field_but_outside_the_frame_is_not_offered(
        qapp, tmp_path):
    # The field of view of a sequence is not the frame: an object can be a
    # perfectly good sibling in the campaign and still land outside the
    # pixels of the reference shot. It is reported, not measured.
    db, camp, pid_a, pid_b, pid_c, paths, _seq = _build(
        tmp_path, second_offset_arcmin=2.0)
    dlg = PassDialog(None, db_obj=db, camp=camp, lang="es")
    labels = [t["label"] for t in dlg.targets()]
    assert labels == ["A"]
    left = {e["project"]["object_name"]: e["reason"] for e in dlg.left_out()}
    assert "B" in left
    assert "encuadre" in left["B"]["es"]
    # and the row is there, unchecked and disabled: the observer sees the
    # object, not just its absence
    rows = [dlg.lst_targets.item(i) for i in range(dlg.lst_targets.count())]
    row_b = next(r for r in rows if r.text().startswith("B"))
    from PySide6.QtCore import Qt
    assert row_b.checkState() == Qt.Unchecked
