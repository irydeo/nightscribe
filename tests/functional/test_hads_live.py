############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Functional tests: live HADS sheet (network, subplan H0.3)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import csv
import logging
from pathlib import Path

import pytest

pytestmark = pytest.mark.network

from nightscribe.core import coords
from nightscribe.core.sources import hads_sheet

logger = logging.getLogger(__name__)

BUNDLED = (Path(__file__).parent.parent.parent
           / "nightscribe" / "assets" / "HADS-stars.csv")


def _bundled_periods():
    # @return: {primary_name: period_h} from the packaged snapshot
    out = {}
    with open(BUNDLED, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = row["Name"].split(" (")[0].split(" =")[0].strip()
            try:
                out[name] = float(row["Period_h"])
            except (ValueError, TypeError):
                pass
    return out


def test_hads_sheet_live():
    # The real workbook: fresh download (both cache levels bypassed)
    data = hads_sheet.parsed(force=True)
    assert data is not None, "HADS sheet unreachable or unparseable"
    stars = data["stars"]
    assert len(stars) >= 150
    assert any(s["sheet_name"].startswith("GP And") for s in stars)
    # legend classes present (blue may be absent in practice: every star
    # currently in the programme has been observed at least once)
    assert any(s["priority"] == "period_change" for s in stars)
    assert any(s["priority"] == "period_change_possible" for s in stars)
    assert any(s["multiperiodic_sheet"] for s in stars)
    years = data["coverage"]
    assert min(int(y) for y in years) <= 2011
    assert max(int(y) for y in years) >= 2025

    # Drift report (informational, never fails): periods of the packaged
    # snapshot vs the live sheet, matched by primary name
    bundle = _bundled_periods()
    drift = []
    for s in stars:
        name = s["sheet_name"].split(" (")[0].split(" =")[0].strip()
        old = bundle.get(name)
        if old is not None and s["period_h"] is not None \
                and abs(old - s["period_h"]) > 0.011:
            drift.append(f"{name}: bundle {old} h -> sheet {s['period_h']} h")
    if drift:
        logger.info("HADS snapshot drift (%d): %s", len(drift),
                    "; ".join(drift[:10]))
        print("\nHADS snapshot drift report:")
        print("\n".join(drift))


def test_hads_sheet_coordinates_parse():
    # spot-check that sheet coordinates survive coords.py conversion
    data = hads_sheet.parsed()       # cached by the previous test
    assert data is not None
    gp = next(s for s in data["stars"]
              if s["sheet_name"].startswith("GP And"))
    ra = coords.ra_hms_to_deg(gp["ra"])
    dec = coords.dec_dms_to_deg(gp["dec"])
    assert abs(ra - 13.8) < 0.1 and abs(dec - 23.16) < 0.1
