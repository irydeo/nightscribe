############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: the remembered gain (ADR-072 rev)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The gain remembered per camera and setting: the key comes out of the
header, a measurement is stored and read back, a plate that does not say
its setting falls back to the camera's latest (flagged), a second
measurement updates instead of piling up, and two cameras never collide.
No network: the store is pure SQL over a throwaway Database.
"""

import pytest

from nightscribe.core import gain as gn
from nightscribe.core import gain_store as gs
from nightscribe.core.db import Database

_HDR = {"INSTRUME": "QHY42PRO-1d74db", "GAIN": 5, "XBINNING": 1}


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "gain.db"))


def test_key_of_names_the_camera_the_setting_and_the_binning():
    assert gs.key_of(_HDR) == {"camera": "QHY42PRO-1d74db",
                               "gain_setting": 5.0, "binning": 1}
    # no camera, no key: the store cannot name whose gain it is
    assert gs.key_of({"GAIN": 5}) is None
    assert gs.key_of({}) is None
    assert gs.key_of(None) is None
    # a header without a binning still keys (1x1), and a setting that is not
    # a number degrades to None instead of guessing
    assert gs.key_of({"INSTRUME": "X"})["binning"] == 1
    assert gs.key_of({"INSTRUME": "X", "GAIN": "high"})["gain_setting"] is None


def test_remember_then_recall_the_exact_key(db):
    rec = gs.remember(db, _HDR, {"gain": 0.11, "ron": 1.7,
                                 "n_boxes": 10, "n_kept": 9})
    assert rec["gain"] == 0.11 and rec["matched"] is True
    again = gs.recall(db, _HDR)
    assert again["gain"] == 0.11 and again["source"] == "remembered"
    assert again["gain_setting"] == 5.0 and again["ron"] == 1.7


def test_a_plate_without_the_setting_gets_the_camera_latest(db):
    gs.remember(db, _HDR, {"gain": 0.11, "ron": None})
    stack = {"INSTRUME": "QHY42PRO-1d74db", "XBINNING": 1}   # no GAIN card
    rec = gs.recall(db, stack)
    assert rec["gain"] == 0.11 and rec["matched"] is False
    assert "no dice su ajuste" in gs.summary(rec)["es"]
    assert "does not say its setting" in gs.summary(rec)["en"]


def test_remember_updates_instead_of_piling_up(db):
    gs.remember(db, _HDR, {"gain": 0.11, "ron": None})
    gs.remember(db, _HDR, {"gain": 0.12, "ron": None})
    n = db.execute("SELECT COUNT(*) FROM gains").fetchone()[0]
    assert n == 1
    assert gs.recall(db, _HDR)["gain"] == 0.12


def test_two_cameras_never_collide(db):
    gs.remember(db, _HDR, {"gain": 0.11, "ron": None})
    other = {"INSTRUME": "OTHER-CAM", "GAIN": 5}
    assert gs.recall(db, other) is None
    gs.remember(db, other, {"gain": 1.5, "ron": None})
    assert gs.recall(db, other)["gain"] == 1.5
    assert gs.recall(db, _HDR)["gain"] == 0.11


def test_nothing_to_store_is_none(db):
    assert gs.remember(db, _HDR, {"gain": None}) is None
    assert gs.remember(db, {}, {"gain": 1.0}) is None
    assert gs.remember(db, _HDR, {"gain": -1.0}) is None
    assert gs.recall(db, {}) is None
    assert gs.summary(None) is None


def test_the_remembered_gain_beats_the_header_in_the_chain():
    # The chain the callers walk (ADR-072): Ajustes -> frames -> remembered
    # -> header. A remembered measurement is a real measurement and beats a
    # card that can be the camera's setting or a placeholder.
    rem = {"gain": 0.11, "ron": 1.7, "matched": True}
    out = gn.resolve(header={"EGAIN": 1.0}, remembered=rem)
    assert out["gain"] == 0.11 and out["source"] == "remembered"
    assert out["ron"] == 1.7
    # a fresh measurement of the frames in hand still wins over it
    est = {"gain": 0.5, "ron": None, "notes": []}
    out = gn.resolve(header={"EGAIN": 1.0}, estimate=est, remembered=rem)
    assert out["gain"] == 0.5 and out["source"] == "frames"
    # and Ajustes beats both
    out = gn.resolve(settings_gain=0.9, header={"EGAIN": 1.0},
                     remembered=rem)
    assert out["gain"] == 0.9 and out["source"] == "settings"
    # with no remembered value the header is still the last word
    out = gn.resolve(header={"EGAIN": 1.0})
    assert out["gain"] == 1.0 and out["source"] == "header"
