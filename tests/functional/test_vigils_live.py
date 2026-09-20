############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Functional tests: live vigils & AAVSO channel (SC4, network)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import pytest

pytestmark = pytest.mark.network

from nightscribe.core import vigils
from nightscribe.core.sources import aavso, surveys


class _Cfg:
    def __init__(self, **extra):
        self._d = dict(extra)

    def get(self, k, default=None):
        return self._d.get(k, default)


def test_vigil_check_live_tcrb_aavso():
    # T CrB is BRIGHTER than ZTF's saturation limit (verified 2026-09-16:
    # no ALeRCE object at its position), so its vigil reads the AAVSO
    # community photometry — which needs the user's API token. Run with
    # AAVSO_API_TOKEN set to validate the live path.
    import os
    token = os.environ.get("AAVSO_API_TOKEN", "")
    if not token:
        pytest.skip("no AAVSO_API_TOKEN in the environment")
    from nightscribe.core.sources import aavso
    latest = aavso.latest_community_mag("T CrB", token, force=True)
    if latest is None:
        pytest.skip("AAVSO photometry API unreachable")
    assert latest["mag"] > 0 and latest["mjd"] > 50000
    # the alert is well-formed when it fires (a real T CrB eruption would
    # be news — we only check the machinery here)
    out = vigils.check_vigils(_Cfg(), fetch=lambda v: latest)
    for a in out:
        assert a["name"] == "T CrB" and a["direction"] == "rise"
        assert a["mag"] < a["baseline_mag"] - a["threshold"]


def test_vigil_check_live_faint_ztf():
    # The ZTF/ALeRCE path is the faint-star backend: a quiescent
    # cataclysmic well inside ZTF's range (V455 And, baseline ~16.4).
    # Coordinates resolved live via VSX, the same chain a vigil without
    # inline coordinates follows.
    from nightscribe.core.sources import vsx
    obj = vsx.lookup("V455 And", force=True)
    if not obj or obj.get("ra_deg") is None:
        pytest.skip("VSX unreachable")
    latest = surveys.latest_mag(obj["ra_deg"], obj["dec_deg"])
    if latest is None:
        pytest.skip("ALeRCE unreachable (or the conesearch is down again)")
    assert latest["mag"] > 0 and latest["mjd"] > 50000
    faint = {"name": "V455 And", "ra_deg": obj["ra_deg"],
             "dec_deg": obj["dec_deg"], "direction": "rise",
             "baseline_mag": 16.4, "threshold": 1.0}
    out = vigils.check_vigils(_Cfg(vigil_list=[faint]),
                              fetch=lambda v: latest)
    for a in out:      # an outburst would be news; check the shape only
        assert a["name"] == "V455 And" and a["direction"] == "rise"


def test_aavso_channel_live():
    # The live editorial channel: the forum JSON parses, and any extracted
    # star name has the expected shape.
    alerts = aavso.alerts(days=365)
    if not alerts:
        pytest.skip("forums.aavso.org unreachable")
    assert all(a["title"] and a["url"].startswith("https://") and a["date"]
               for a in alerts)
    assert all(not a.get("pinned") for a in alerts)
    named = [a for a in alerts if aavso.extract_star_name(a["title"])]
    assert named, "no star names extracted from the live alert titles"

    camps = aavso.campaigns()
    if camps is None:
        pytest.skip("apps.aavso.org unreachable")
    for c in camps:
        assert c["start"] <= c["end"] and c["title"]
