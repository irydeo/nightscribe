############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: observatory backend selector (ADR-081)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The Capture step drives one observatory program at a time, chosen in
Settings. These tests pin the selector: the config decides which client is
built, unknown values fall back to CCDciel, and both errors share the base
type the GUI catches.
"""

from nightscribe.core.sources import ccdciel, nina, observatory


def test_default_backend_is_ccdciel():
    assert observatory.backend({}) == "ccdciel"
    client = observatory.make_client({})
    assert isinstance(client, ccdciel.Client)
    assert client.port == ccdciel.DEFAULT_PORT


def test_unknown_backend_falls_back_to_ccdciel():
    assert observatory.backend({"observatory_backend": "ekos"}) == "ccdciel"


def test_nina_backend_builds_the_nina_client():
    cfg = {"observatory_backend": "nina", "nina_host": "10.0.0.2",
           "nina_port": 1234}
    client = observatory.make_client(cfg)
    assert isinstance(client, nina.Client)
    assert client.host == "10.0.0.2"
    assert client.port == 1234


def test_both_errors_are_observatory_errors():
    assert issubclass(ccdciel.CCDcielError, observatory.ObservatoryError)
    assert issubclass(nina.NinaError, observatory.ObservatoryError)
