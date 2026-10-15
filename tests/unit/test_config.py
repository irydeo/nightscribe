############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: config defaults & kind migrations (HADS B.2,
# Track V VB.3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import json

from nightscribe import config as cfgmod

_OLD_SIX = ["neo", "sn", "comet", "pccp", "transit", "alert"]
_OLD_SEVEN = _OLD_SIX + ["hads"]


def _cfg_with_stored(tmp_path, stored):
    # @return: a Config whose file holds the given dict
    f = tmp_path / "nightscribe.json"
    f.write_text(json.dumps(stored), encoding="utf-8")
    cfg = cfgmod.Config()
    cfg._file = f
    cfg.load()
    return cfg


def test_default_enabled_kinds_include_hads_and_variable():
    assert "hads" in cfgmod.DEFAULTS["enabled_kinds"]
    assert "variable" in cfgmod.DEFAULTS["enabled_kinds"]
    assert len(cfgmod.DEFAULTS["enabled_kinds"]) == 8


def test_pre_hads_default_migrates_for_free(tmp_path):
    cfg = _cfg_with_stored(tmp_path, {"enabled_kinds": list(_OLD_SIX)})
    assert "hads" in cfg.get("enabled_kinds")
    assert "variable" in cfg.get("enabled_kinds")


def test_pre_variable_default_migrates_for_free(tmp_path):
    cfg = _cfg_with_stored(tmp_path, {"enabled_kinds": list(_OLD_SEVEN)})
    assert "variable" in cfg.get("enabled_kinds")


def test_customised_kind_list_is_never_touched(tmp_path):
    custom = ["neo", "sn"]
    cfg = _cfg_with_stored(tmp_path, {"enabled_kinds": custom})
    assert cfg.get("enabled_kinds") == ["neo", "sn"]


def test_migration_is_not_written_back_until_a_save(tmp_path):
    f = tmp_path / "nightscribe.json"
    cfg = _cfg_with_stored(tmp_path, {"enabled_kinds": list(_OLD_SEVEN)})
    assert "variable" in cfg.get("enabled_kinds")
    # the file still holds the old list: the migration is in-memory only
    assert json.loads(f.read_text())["enabled_kinds"] == _OLD_SEVEN


def test_event_mag_threshold_default():
    assert cfgmod.DEFAULTS["event_mag_threshold"] == 0.5


def test_save_is_atomic_and_a_corrupt_file_is_kept(tmp_path):
    # save() used to open the real file for writing and truncate it first, so
    # a cut during a set() left a torn JSON and the next load fell back to the
    # defaults in silence (QA-05). Now it is a temp file plus os.replace, and
    # an unreadable file is kept next to it and reported.
    cfg = cfgmod.Config()
    cfg._file = tmp_path / "nightscribe.json"
    cfg._data = dict(cfgmod.DEFAULTS)
    cfg._data["lat"] = 40.5
    cfg.save()
    assert json.loads(cfg._file.read_text(encoding="utf-8"))["lat"] == 40.5

    cfg._file.write_text("{not json", encoding="utf-8")
    cfg2 = cfgmod.Config()
    cfg2._file = cfg._file
    cfg2.load()
    assert cfg2.load_error
    assert (tmp_path / "nightscribe.json.corrupt").exists()
