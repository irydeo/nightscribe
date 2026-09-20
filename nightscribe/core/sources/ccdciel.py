############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - CCDciel JSON-RPC source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import json
import logging
import time

import requests

from ..db import db

logger = logging.getLogger(__name__)

DEFAULT_PORT = 3277
_TIMEOUT = 4.0


def truthy(result):
    # Mount state replies drift between servers: a bare bool, an integer,
    # "False"/"True" as text, or an envelope around the value. Settle them to
    # a real bool (None when the payload does not say anything).
    # @args: result - the "result" member of a Telescope_* state reply
    # @return: True / False / None
    while isinstance(result, dict):
        for key in ("slewing", "tracking", "running", "value"):
            if key in result:
                result = result[key]
                break
        else:
            return None
    if isinstance(result, str):
        return result.strip().lower() not in ("", "false", "no", "0",
                                              "off", "idle", "stopped")
    if result is None:
        return None
    return bool(result)


class CCDcielError(Exception):
    # A CCDciel command came back with status "Failed!" (or an error) and we
    # have nothing to show but the failure itself.
    pass


class Client:
    # Thin JSON-RPC 2.0 client for a local CCDciel
    # (http://host:3277/jsonrpc, ADR-030). Reads go through the db.http_get
    # cache (source "ccdciel", 60 s TTL) so dashboards and filter lists do
    # not hammer the observatory software; state changes (slew, filter,
    # capture settings) go straight to the server through call().
    def __init__(self, host="127.0.0.1", port=DEFAULT_PORT, timeout=_TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout

    @property
    def url(self):
        return f"http://{self.host}:{self.port}/jsonrpc"

    # -- transport ------------------------------------------------------------

    def _rpc(self, method, params=None):
        # Raw JSON-RPC 2.0 POST. Method and response types follow the official
        # script reference (2026-05-25 revision). Params are positional.
        # @args: method - JSON-RPC method name, params - list (positional)
        # @return: the "result" member of the JSON-RPC response
        payload = {"jsonrpc": "2.0", "method": method, "id": 1}
        if params:
            payload["params"] = list(params)
        logger.debug("jsonrpc %s %s", method, payload.get("params"))
        try:
            r = requests.post(self.url, json=payload, timeout=self.timeout)
            r.raise_for_status()
            body = r.json()
        except (requests.RequestException, ValueError) as err:
            raise CCDcielError(f"{method}: no JSON-RPC response from {self.url}: {err}") from err
        if "error" in body:
            raise CCDcielError(f"{method}: {body['error'].get('message') or body['error']}")
        logger.debug("jsonrpc %s -> %s", method, body.get("result"))
        return body.get("result")

    @staticmethod
    def _ok(result, method="command"):
        # @args: result - the "result" member of a command response,
        #        method - JSON-RPC method name (shown on failure, for the log)
        # @return: result, or raise CCDcielError on an explicit failure
        if isinstance(result, dict) and result.get("status"):
            if result["status"] in ("OK!", "OK"):
                return result
            raise CCDcielError(f"{method}: {result.get('error') or result['status']}")
        if isinstance(result, dict) and result.get("error"):
            raise CCDcielError(f"{method}: {result['error']}")
        # Some servers answer a bare failure word instead of an envelope.
        if isinstance(result, str) and result.strip().lower() in (
                "failed", "failed!", "error", "busy"):
            raise CCDcielError(f"{method}: {result.strip()}")
        return result

    def call(self, method, *params):
        # Command / live state path: never cached.
        # @args: method - JSON-RPC method, params - positional arguments
        # @return: result member (status envelope already checked)
        result = self._rpc(method, params if params else None)
        return self._ok(result, method)

    def read(self, method, key, params=None):
        # Cached read path (db.http_get, "ccdciel" source, 60 s TTL).
        # Never use it for mount coordinates — the sky does not wait.
        # @args: method - JSON-RPC method, key - cache key, params - positional
        # @return: result of a return-value method, straight from the cache
        def fetch():
            result = self._rpc(method, params)
            return json.dumps(result).encode("utf-8"), "application/json"
        body, _ = db.http_get(f"ccdciel:{method}:{key}", "ccdciel", fetch)
        return json.loads(body.decode("utf-8"))

    # -- observatory status ----------------------------------------------------

    def ping(self):
        # Version read: proves the server speaks JSON-RPC 2.0.
        # @return: version string ("2.20.1") or None when unreachable
        try:
            v = self.read("CCDciel_Version", "version")
        except CCDcielError:
            return None
        if isinstance(v, (list, tuple)):
            return ".".join(str(x) for x in v)
        return str(v)

    def dashboard(self):
        # Aggregated status over the sections the Plan & Capture tab shows.
        # @return: dict of sections (devices, mount, camera, wheel, focuser,
        #          capture, sequence); empty dict on transport errors
        try:
            result = self.read("status", "dashboard",
                               ["devices", "mount", "camera", "wheel",
                                "focuser", "capture", "sequence"])
        except CCDcielError:
            return {}
        return result if isinstance(result, dict) else {}

    def filters(self):
        # @return: list of filter names in the wheel, or None if not connected
        try:
            names = self.read("Wheel_GetfiltersName", "filters")
        except CCDcielError:
            return None
        return list(names) if isinstance(names, list) else None

    def connected(self):
        # @return: True when every defined device reports connected
        return bool(self.read("Devices_connected", "connected"))

    def current_filter(self):
        # @return: wheel slot number of the current filter, or None
        try:
            return int(self.call("Wheel_getfilter"))
        except (CCDcielError, TypeError):
            return None

    def slewing(self):
        # @return: True while the mount is slewing (live, uncached)
        return bool(truthy(self.call("Telescope_slewing")))

    def tracking(self):
        # @return: True when the mount is tracking (live, uncached)
        return bool(truthy(self.call("Telescope_tracking")))

    # -- coordinates and motion -------------------------------------------------

    def apparent(self, ra_deg, dec_deg):
        # @args: ra_deg/dec_deg - J2000 target coordinates (degrees)
        # @return: (ra_hours, dec_deg) apparent, as the mount expects them
        # The server wants two flat positional scalars (RA hours, DEC
        # degrees), like Telescope_slewasync and Telescope_sync.
        result = self.call("J2000_to_Apparent", ra_deg / 15.0, dec_deg)
        if isinstance(result, (list, tuple)) and len(result) >= 2:
            return float(result[0]), float(result[1])
        return ra_deg / 15.0, dec_deg

    def slew_target(self, ra_deg, dec_deg):
        # Slew the mount to a J2000 target. Apparent RA is in hours.
        # @args: ra_deg/dec_deg - J2000 target coordinates (degrees)
        # @return: apparent (ra_hours, dec_deg) the mount was pointed at
        ra_h, dec = self.apparent(ra_deg, dec_deg)
        self.call("Telescope_slewasync", ra_h, dec)
        return ra_h, dec

    def sync_target(self, ra_deg, dec_deg):
        # @args: ra_deg/dec_deg - J2000 coordinates (degrees) to align the mount to
        # @return: apparent (ra_hours, dec_deg) the mount was synced to
        ra_h, dec = self.apparent(ra_deg, dec_deg)
        self.call("Telescope_sync", ra_h, dec)
        return ra_h, dec

    # -- astrometric pointing ------------------------------------------------------

    DEFAULT_ASTROMETRY_TIMEOUT_S = 120.0
    DEFAULT_ASTROMETRY_POLL_S = 1.0

    def astrometry_goto_async(self, ra_deg, dec_deg):
        # Fire the astrometric goto (slew + plate solve + correction) and
        # return as soon as CCDciel accepts it. The job finishes in the
        # background; poll astrometry_goto_running() for state.
        # @args: ra_deg/dec_deg - J2000 target coordinates (degrees)
        # @return: apparent (ra_hours, dec_deg) the mount was told to point at
        ra_h, dec = self.apparent(ra_deg, dec_deg)
        self.call("Astrometry_Goto_Async", ra_h, dec)
        return ra_h, dec

    def astrometry_goto_running(self):
        # @return: True while the astrometric goto job is still working
        return bool(truthy(self.call("Astrometry_Goto_Running")))

    def astrometry_goto_result(self):
        # Only meaningful once astrometry_goto_running() is False.
        # @return: bool -- True when the last job ended in a successful
        #          pointing, False on plate solve / correction failure,
        #          None when the server does not say either way
        return truthy(self.call("Astrometry_Goto_Result"))

    def astrometry_goto(self, ra_deg, dec_deg,
                        timeout_s=DEFAULT_ASTROMETRY_TIMEOUT_S,
                        poll_s=DEFAULT_ASTROMETRY_POLL_S):
        # High-level astrometric goto: fire the async job and poll its
        # running flag until it settles, then check the result flag.
        # @args: ra_deg/dec_deg - J2000 target (degrees),
        #        timeout_s - hard cap on waiting (default 120 s),
        #        poll_s - seconds between running-checks (default 1 s)
        # @return: (ra_hours, dec_deg) apparent coordinates the mount
        #          was told to point at
        # @raise: CCDcielError when the job is still running after the
        #         timeout, or when the job finished without a successful
        #         pointing
        ra_h, dec = self.astrometry_goto_async(ra_deg, dec_deg)
        deadline = time.monotonic() + timeout_s
        while self.astrometry_goto_running():
            if time.monotonic() >= deadline:
                raise CCDcielError(
                    f"Astrometry_Goto still running after {int(timeout_s)} s")
            time.sleep(poll_s)
        ok = self.astrometry_goto_result()
        if ok is False:
            raise CCDcielError(
                "Astrometry_Goto finished without a successful pointing")
        return ra_h, dec

    # -- filter wheel -------------------------------------------------------------

    def set_filter(self, index):
        # @args: index - slot number in the wheel (0-based)
        # @return: True when the wheel accepted the change
        self.call("Wheel_setfilter", int(index))
        return True

    # -- capture settings ----------------------------------------------------------

    def push_plan(self, n_frames, exp_s, object_name):
        # Stage a capture plan inside CCDciel: object name, exposure, count
        # and Light frame type. Returns as soon as the settings stick.
        # @args: n_frames - exposure count, exp_s - exposure (s),
        #        object_name - FITS OBJNAME
        # @return: True when all Capture_set* commands were accepted
        self.call("Capture_setobjectname", object_name or "NightScribe")
        self.call("Capture_setexposure", float(exp_s))
        self.call("Capture_setcount", int(n_frames))
        self.call("Capture_setframetype", "Light")
        return True

    def start_capture(self):
        # Fire the staged capture plan (Capture_start returns immediately).
        self.call("Capture_start")