############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Date helpers tests
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Unit tests for core.dates (object-card plan, subplan 5d): one parser
for every discovery-date format our sources speak, and the days-since
helper the freshness score and the SN card share. No network.
"""

import datetime

from nightscribe.core import dates


def test_normalize_rochester_format():
    # Rochester: "2026/08/30.5" (fractional day appended)
    assert dates.normalize_date("2026/08/30.5") == "2026-08-30"
    assert dates.normalize_date("2026/08/30") == "2026-08-30"


def test_normalize_iso_format():
    # TNS / SBDB first_obs / PCCP: already ISO
    assert dates.normalize_date("2004-03-15") == "2004-03-15"


def test_normalize_sbdb_discovery_format():
    # SBDB discovery record: "2004-Mar-15" (English month abbrev)
    assert dates.normalize_date("2004-Mar-15") == "2004-03-15"
    assert dates.normalize_date("1997-Dec-02") == "1997-12-02"


def test_normalize_rejects_garbage():
    assert dates.normalize_date("") is None
    assert dates.normalize_date(None) is None
    assert dates.normalize_date("unknown") is None
    assert dates.normalize_date("2026-13-01") is None   # no month 13
    assert dates.normalize_date("2026/08") is None      # not a full date


def test_days_since_counts_backwards():
    ten_days_ago = (datetime.date.today()
                    - datetime.timedelta(days=10)).isoformat()
    assert dates.days_since(ten_days_ago) == 10
    # and every source format lands on the same number
    assert dates.days_since(ten_days_ago.replace("-", "/")) == 10


def test_days_since_garbage_is_none():
    assert dates.days_since("not a date") is None
    assert dates.days_since(None) is None
