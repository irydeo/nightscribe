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
