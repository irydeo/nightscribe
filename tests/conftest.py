############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Shared pytest fixtures
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_path():
    # @return: the fixtures dir
    return FIXTURES


@pytest.fixture
def tmp_db(tmp_path):
    # @return: a Database on a temp file (never touches the real one)
    from nightscribe.core.db import Database
    return Database(tmp_path / "test.db")


@pytest.fixture
def fake_cfg():
    # @return: a config-like object for scoring tests
    class Cfg:
        _v = {"lat": 40.55, "lon": -3.37, "min_alt": 30.0, "limit_mag": 20.0,
              "mpc_code": "Z41", "observatory_name": "Test Observatory"}
        def get(self, k, d=None):
            return self._v.get(k, d)
    return Cfg()


@pytest.fixture
def sbdb_apophis():
    # @return: decoded real SBDB reply for Apophis
    return json.loads((FIXTURES / "sbdb_apophis.json").read_text(encoding="utf-8"))


@pytest.fixture
def exoclock_sample():
    # @return: two real ExoClock catalogue entries
    return json.loads((FIXTURES / "exoclock_sample.json").read_text(encoding="utf-8"))
