############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - unit tests: reference cutouts (flat-tile fallback)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Offscreen checks for core/sources/cutouts.py: a flat "no coverage"
Legacy Survey tile (a valid 200 of uniform gray) must fall through to the
DSS2 source, and a field with no usable image anywhere answers
(None, None) instead of an empty pane. No network: db.http_get is faked,
JPEGs are built in memory.
"""

import io
from pathlib import Path

import pytest


def _jpeg(fill=32, stars=False):
    # @return: JPEG bytes: a flat gray tile, or one with bright stars
    from PIL import Image
    im = Image.new("L", (64, 64), fill)
    if stars:
        for x, y in ((10, 10), (40, 30), (25, 50), (55, 55)):
            im.putpixel((x, y), 255)
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def fake_cache(monkeypatch, tmp_path):
    # http_get serves canned bytes per source; the image cache lands in tmp
    from nightscribe.core.sources import cutouts
    bodies = {}
    monkeypatch.setattr(cutouts.paths, "image_cache_dir", lambda: tmp_path)

    def serve(ls=None, dss=None):
        bodies["ls"], bodies["dss"] = ls, dss

        def fake_http_get(key, source, fetch, force=False):
            return (bodies["ls"] if ":ls:" in key
                    else bodies["dss"]), "image/jpeg"
        monkeypatch.setattr(cutouts.db, "http_get", fake_http_get)

    return serve


def test_flat_ls_tile_falls_back_to_dss(fake_cache):
    # the V0001 Cyg report: LS answers a uniform gray tile, DSS2 has sky
    fake_cache(ls=_jpeg(32), dss=_jpeg(stars=True))
    from nightscribe.core.sources import cutouts
    path, label = cutouts.reference_cutout(291.366, 42.784, size=1000,
                                           pixscale=1.08)
    assert label == "DSS2 color (CDS)"
    assert path is not None and Path(path).exists()


def test_real_ls_image_is_served_first(fake_cache):
    fake_cache(ls=_jpeg(stars=True), dss=_jpeg(stars=True))
    from nightscribe.core.sources import cutouts
    path, label = cutouts.reference_cutout(238.786, 25.92, size=1000,
                                           pixscale=1.08)
    assert label == "Legacy Survey DR10"
    assert path is not None and Path(path).exists()


def test_everything_flat_returns_none(fake_cache):
    fake_cache(ls=_jpeg(32), dss=_jpeg(24))
    from nightscribe.core.sources import cutouts
    path, label = cutouts.reference_cutout(10.0, 20.0, size=1000,
                                           pixscale=1.08)
    assert (path, label) == (None, None)


def test_network_down_returns_none(monkeypatch, tmp_path):
    import requests
    from nightscribe.core.sources import cutouts
    monkeypatch.setattr(cutouts.paths, "image_cache_dir", lambda: tmp_path)

    def failing(key, source, fetch, force=False):
        raise requests.RequestException("down")
    monkeypatch.setattr(cutouts.db, "http_get", failing)
    assert cutouts.reference_cutout(10.0, 20.0) == (None, None)


def test_undecodable_body_counts_as_flat(fake_cache):
    fake_cache(ls=b"<html>service error</html>", dss=_jpeg(stars=True))
    from nightscribe.core.sources import cutouts
    _path, label = cutouts.reference_cutout(10.0, 20.0)
    assert label == "DSS2 color (CDS)"
