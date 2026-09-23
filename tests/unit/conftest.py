############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit-suite guard: no network, ever
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Unit tests are offline by definition (AGENTS.md), but nothing enforced
it: a forgotten source call inside a test (post.build_charts pulling a
reference cutout for an SN fixture in test_overview_panel) did real HTTP.
It stayed green while the host answered fast and hung the Windows CI gate
for its whole 12-minute budget the day legacysurvey.org stalled on connect
(2026-09-23). This fixture makes every requests call fail in milliseconds,
naming the URL, so a leak fails the gate fast instead of freezing it.
Network tests belong to tests/functional; everything else fakes its source
at the function level (test_followup_sequence.py shows the pattern).
"""

import pytest
import requests


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    # @return: None. Any requests call (requests.get/post go through
    # Session.request too) raises ConnectionError at once. It is a
    # RequestException, so the sources' own offline fallbacks engage
    # (cutouts returns None, the "field" chart stays absent, etc.); a
    # source that forgot its guard fails the test loudly, which is the
    # point.
    def _blocked(session, method, url, **kwargs):
        raise requests.ConnectionError(
            f"unit tests are offline: {method} {url} (fake the source, "
            f"like test_followup_sequence.py, or move the test to "
            f"tests/functional)")

    monkeypatch.setattr(requests.sessions.Session, "request", _blocked)
