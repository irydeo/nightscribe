############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Unit tests: NINA / PINS Advanced API v2 client (ADR-081)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The NINA/PINS client talks REST to the Advanced API v2 plugin
(http://host:1888/v2/api). No network here: requests.get is replaced by a
faker that records the framed calls and serves canned envelopes. Reads must
go through the db.http_get cache; commands must not.
"""

import requests
import pytest

from nightscribe.core.sources import nina


class _Resp:
    # Minimal stand-in for requests.Response
    def __init__(self, body, content=b"", headers=None, status_code=200):
        self._body = body
        self.content = content
        self.headers = headers or {"Content-Type": "application/json"}
        self.status_code = status_code

    def json(self):
        return self._body


def _ok(value):
    return {"Response": value, "Error": "", "StatusCode": 200,
            "Success": True, "Type": "API"}


def _err(message, code=409):
    return {"Response": None, "Error": message, "StatusCode": code,
            "Success": False, "Type": "API"}


class _FakeGet:
    # Records GET calls; serves bodies in order, one per call.
    def __init__(self, bodies=None):
        self.calls = []
        self.bodies = list(bodies or [])
        self.raises = None

    def __call__(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        if self.bodies:
            item = self.bodies.pop(0)
            return item if isinstance(item, _Resp) else _Resp(item)
        return _Resp(_ok(None))

    @property
    def paths(self):
        return [c["url"].split("/v2/api", 1)[1] for c in self.calls]


@pytest.fixture
def nina_db(tmp_db, monkeypatch):
    monkeypatch.setattr(nina, "db", tmp_db)
    return tmp_db


@pytest.fixture
def fake_get(monkeypatch):
    fake = _FakeGet()
    monkeypatch.setattr(nina.requests, "get", fake)
    return fake


@pytest.fixture
def client():
    return nina.Client("127.0.0.1", 1888)


# ---------------- transport / framing ----------------

def test_base_url(client, fake_get):
    client.abort_motion()
    assert fake_get.calls[0]["url"] == "http://127.0.0.1:1888/v2/api/equipment/mount/slew/stop"


def test_success_false_raises(client, fake_get):
    fake_get.bodies = [_err("Mount not connected")]
    with pytest.raises(nina.NinaError, match="Mount not connected"):
        client.abort_motion()


def test_transport_error_wrapped(client, fake_get):
    fake_get.raises = requests.ConnectionError("refused")
    with pytest.raises(nina.NinaError):
        client.abort_motion()


def test_error_is_observatory_error():
    # The GUI catches the base type, not the concrete one.
    from nightscribe.core.sources import observatory
    assert issubclass(nina.NinaError, observatory.ObservatoryError)


# ---------------- reads are cached ----------------

def test_ping_uses_cache(nina_db, client, fake_get):
    fake_get.bodies = [_ok("3.2 NIGHTLY #058")]
    assert client.ping() == "3.2 NIGHTLY #058"
    assert client.ping() == "3.2 NIGHTLY #058"
    assert len(fake_get.calls) == 1  # second read comes from the cache
    assert fake_get.calls[0]["params"] == {"friendly": "true"}


def test_ping_unreachable_returns_none(nina_db, client, fake_get):
    fake_get.raises = requests.ConnectionError("refused")
    assert client.ping() is None


def test_dashboard_maps_nina_fields(nina_db, client, fake_get):
    eq = {"Camera": {"Connected": True, "Temperature": -11.5},
          "Mount": {"Connected": True, "TrackingEnabled": True,
                    "Slewing": False},
          "FilterWheel": {"Connected": True}}
    fake_get.bodies = [_ok(eq)]
    dash = client.dashboard()
    assert dash["camera"]["temperature"] == -11.5
    assert dash["mount"]["tracking"] is True   # TrackingEnabled, not Tracking
    assert dash["mount"]["slewing"] is False
    assert client.dashboard() == dash
    assert len(fake_get.calls) == 1            # cached on repeat


def test_filters_from_available(nina_db, client, fake_get):
    fake_get.bodies = [_ok({"AvailableFilters": [{"Name": "L", "Id": 0},
                                                 {"Name": "Ha", "Id": 1},
                                                 {"Name": "", "Id": 2}]})]
    assert client.filters() == ["L", "Ha"]
    assert client.filters() == ["L", "Ha"]
    assert len(fake_get.calls) == 1


# ---------------- motion ----------------

def test_slew_sends_j2000_degrees(client, fake_get):
    fake_get.bodies = [_ok("Slew started")]
    client.slew_target(157.5, -20.0)
    assert fake_get.paths == ["/equipment/mount/slew"]
    assert fake_get.calls[0]["params"] == {"ra": 157.5, "dec": -20.0}


def test_astrometry_goto_centers_and_waits(client, fake_get):
    fake_get.bodies = [_ok("Slew finished")]
    client.astrometry_goto(157.5, -20.0)
    assert fake_get.paths == ["/equipment/mount/slew"]
    params = fake_get.calls[0]["params"]
    assert params["center"] == "true"
    assert params["waitForResult"] == "true"
    assert fake_get.calls[0]["timeout"] >= 60  # the solve needs room


def test_slewing_live_state_not_cached(client, fake_get):
    fake_get.bodies = [_ok({"Slewing": True}), _ok({"Slewing": False})]
    assert client.slewing() is True
    assert client.slewing() is False
    assert len(fake_get.calls) == 2


def test_abort_motion(client, fake_get):
    fake_get.bodies = [_ok("Stopped slew")]
    assert client.abort_motion() is True
    assert fake_get.paths == ["/equipment/mount/slew/stop"]


def test_capturing_reads_the_camera(client, fake_get):
    # ADR-082: the last-frame preview stops watching when the camera stops.
    fake_get.bodies = [_ok({"IsExposing": True}), _ok({"IsExposing": False})]
    assert client.capturing() is True
    assert client.capturing() is False
    assert fake_get.paths == ["/equipment/camera/info",
                              "/equipment/camera/info"]


def test_capture_dir_is_gone(client):
    # The capture-folder idea is gone (ADR-082 rev): the frame comes over HTTP.
    assert not hasattr(client, "capture_dir")


def test_last_frame_preview_streams_the_image(client, fake_get):
    # ADR-082: the thumbnail is the last image NINA saved, streamed as a PNG
    # (works remote), with the history entry's numbers for the caption.
    fake_get.bodies = [
        _ok(3),                                            # count
        _ok([{"Filename": "LIGHT_0003.fits", "Filter": "R",
              "ExposureTime": 45.0, "Date": "2026-10-13T22:00:00"}]),
        _Resp(None, content=b"\x89PNGdata",
              headers={"Content-Type": "image/png"}),      # the stream
    ]
    frame = client.last_frame_preview()
    assert frame["image"] == b"\x89PNGdata"
    assert frame["index"] == 2
    assert frame["name"] == "LIGHT_0003.fits"
    assert frame["filter"] == "R"
    assert frame["exptime_s"] == 45.0
    assert fake_get.paths[-1] == "/image/2"


def test_last_frame_preview_none_without_images(client, fake_get):
    fake_get.bodies = [_ok(0)]
    assert client.last_frame_preview() is None


def test_image_fits_bytes_decodes_base64(client, fake_get):
    import base64
    payload = b"FITS-CONTENT"
    fake_get.bodies = [_ok(base64.b64encode(payload).decode())]
    assert client.image_fits_bytes(2) == payload
    assert fake_get.calls[0]["params"] == {"raw_fits": "true"}


# ---------------- filter wheel ----------------

def test_set_filter(client, fake_get):
    fake_get.bodies = [_ok("Filter changed")]
    assert client.set_filter(2) is True
    assert fake_get.calls[0]["params"] == {"filterId": 2}


def test_stop_capture_aborts_the_exposure(client, fake_get):
    fake_get.bodies = [_ok("Exposure aborted")]
    assert client.stop_capture() is True
    assert fake_get.paths == ["/equipment/camera/abort-exposure"]


def test_current_gain_and_offset_from_the_camera(client, fake_get):
    # each reads camera/info (the second call needs its own body)
    fake_get.bodies = [_ok({"Gain": 120, "Offset": 30}),
                       _ok({"Gain": 120, "Offset": 30})]
    assert client.current_gain() == 120
    assert client.current_offset() == 30


# ---------------- capture ----------------

def test_start_capture_without_plan_raises(client, fake_get):
    with pytest.raises(nina.NinaError, match="Send plan"):
        client.start_capture()


def test_push_plan_then_start_capture(client, fake_get):
    st = client.push_plan(30, 45.0, "SN 2026ziz")
    assert st["count"] == 30 and st["persistent"] is False
    fake_get.bodies = [_ok("Capture started")]
    client.start_capture()
    assert fake_get.paths == ["/equipment/camera/capture"]
    params = fake_get.calls[0]["params"]
    assert params["duration"] == 45.0
    assert params["targetName"] == "SN 2026ziz"
    assert params["imageType"] == "LIGHT"
    assert params["save"] == "true"


def test_start_capture_survives_a_refused_filter(client, fake_get):
    # a refused wheel slot must not lose the capture (ADR-081/083)
    client.push_plan(1, 5.0, "X", filter_index=2)
    fake_get.bodies = [_err("filterwheel not connected"),
                       _ok("Capture started")]
    assert client.start_capture() is True
    assert "/equipment/camera/capture" in fake_get.paths


def test_staged_plan_is_a_copy(client):
    client.push_plan(5, 10.0, "X")
    copy = client.staged_plan()
    copy["count"] = 999
    assert client.staged_plan()["count"] == 5
