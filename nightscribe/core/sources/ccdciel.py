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
from .observatory import ObservatoryError

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


class CCDcielError(ObservatoryError):
    # A CCDciel command came back with status "Failed!" (or an error) and we
    # have nothing to show but the failure itself. It subclasses the common
    # ObservatoryError so the GUI catches one type whatever the backend is.
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

    def capturing(self):
        # @return: True while a capture is running (live, uncached). The
        # Capture step uses it to stop watching the folder once the run ends.
        return bool(truthy(self.call("Capture_running")))

    def current_gain(self):
        # The camera's gain SETTING (its own index), not the system gain in
        # e-/ADU (that is a photometry quantity, in the profile).
        # @return: the gain (int) or None
        try:
            return int(self.call("Camera_GetGain"))
        except (CCDcielError, TypeError, ValueError):
            return None

    def current_offset(self):
        # @return: the camera's offset setting (int) or None
        try:
            return int(self.call("Camera_GetOffset"))
        except (CCDcielError, TypeError, ValueError):
            return None

    def last_frame_name(self):
        # @return: the full path of the last saved file (live), or None
        try:
            value = self.call("Capture_getLastfilename")
        except CCDcielError:
            return None
        return str(value) if value else None

    def last_frame_preview(self):
        # The last image CCDciel has on screen, as a JPEG, over its HTTP
        # server (the SAME host:port as the JSON-RPC; see pu_main.TCPgetimage,
        # which serves fullimage.jpg / scrimage.jpg / lastfocus.jpg). It is
        # NOT the FITS: CCDciel's web server only serves pictures, so the
        # thumbnail is its own render and the FITS is opened separately from
        # the file on disk when that path is reachable. Works local and remote.
        # @return: dict with image (JPEG bytes), name, path; or None when
        #          there is nothing to show
        url = f"http://{self.host}:{self.port}/fullimage.jpg"
        try:
            r = requests.get(url, timeout=self.timeout)
            r.raise_for_status()
            data = r.content
        except requests.RequestException as err:
            raise CCDcielError(f"fullimage.jpg: {err}") from err
        if not data:
            return None
        path = self.last_frame_name()
        name = path.replace("\\", "/").rsplit("/", 1)[-1] if path else None
        return {"image": data, "name": name, "path": path,
                "filter": None, "exptime_s": None, "date_obs": None}

    def abort_motion(self):
        # Safety stop: halt any telescope movement right now. CCDciel's
        # `Telescope_abortmotion` is the documented "stop any telescope
        # movement"; it is what the Stop-goto button calls when a slew or an
        # astrometric goto is heading somewhere wrong. It stops the MOUNT,
        # not the astrometry job, so the goto may still report a failure
        # afterwards (which is the honest outcome of an interrupted slew).
        # @return: True when the server accepted the stop
        self.call("Telescope_abortmotion")
        return True

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

    def push_plan(self, n_frames, exp_s, object_name, dither=None, gain=None,
                  offset=None, binning=None):
        # Stage a capture plan inside CCDciel: object name, exposure, count
        # and Light frame type, plus the capture options that CCDciel can take
        # live (ADR-083): binning, gain, offset and the dither count. The
        # autofocus cadence is not a live setting in CCDciel (only "focus
        # now"), so it stays in the sequence file.
        #
        # The CORE plan (object/exposure/count/type) must always land; the
        # OPTIONAL setters are best-effort: a rejected one (a binning CCDciel
        # does not know, a gain out of range) is collected as a warning and the
        # plan goes on, so "Send plan" never stops half-way. And CCDciel's
        # `Capture_setbinning` wants an INTEGER ("1x1" is rejected), unlike
        # NINA's string form, so the binning is converted here.
        # @args: n_frames - exposure count, exp_s - exposure (s),
        #        object_name - FITS OBJNAME, dither - recipe dict (or None),
        #        gain/offset/binning - recipe values (None = leave as is)
        # @return: {"warnings": [str, ...]} (empty when everything landed)
        warnings = []
        self.call("Capture_setobjectname", object_name or "NightScribe")
        self.call("Capture_setexposure", float(exp_s))
        self.call("Capture_setcount", int(n_frames))
        self.call("Capture_setframetype", "Light")

        def _try(label, fn):
            # @args: label - what failed (for the message), fn - the setter
            # @return: None. A failure is recorded, never raised: the plan is
            #          more important than the optional knob.
            try:
                fn()
            except CCDcielError as err:
                warnings.append(f"{label}: {err}")

        if binning:
            # CCDciel's Capture_setbinning sets the Binning combo's TEXT
            # (cmd_Capture_SetBinning -> Capture.Binning.Text := bin), so it
            # wants "1x1", not an integer (NINA wants the same string form)
            _try("binning", lambda: self.call("Capture_setbinning",
                                              str(binning)))
        if gain not in (None, ""):
            current = self.current_gain()
            if current is None or int(gain) != current:
                _try("gain", lambda: self.call("Camera_SetGain", int(gain)))
        if offset not in (None, ""):
            current = self.current_offset()
            if current is None or int(offset) != current:
                _try("offset", lambda: self.call("Camera_SetOffset", int(offset)))
        if dither is not None:
            count = int(dither.get("every") or 0) if dither.get("on") else 0
            _try("dither", lambda: self.call("Capture_setdither", count))
        return {"warnings": warnings}

    def stop_capture(self):
        # Stop a running capture (ADR-081): CCDciel's documented
        # "Stop a capture". It halts the capture module, not the mount (that is
        # abort_motion / the Stop-goto button).
        # @return: True when the server accepted the stop
        self.call("Capture_stop")
        return True

    def staged_plan(self):
        # Reads BACK the capture plan CCDciel is actually holding, so "Send
        # plan" can prove it did something instead of trusting that the
        # Capture_set* commands landed. A read-back is the only honest
        # confirmation: the server accepts a set and could still round it
        # (a count of 0, a frame type it does not know).
        # @return: dict with object/exposure_s/count/frame_type/filter, or
        #          None when the server does not answer the getters
        try:
            return {
                "object": self.call("Capture_getobjectname"),
                "exposure_s": self.call("Capture_getexposure"),
                "count": self.call("Capture_getcount"),
                "frame_type": self.call("Capture_getframetype"),
                "binning": self.call("Capture_getbinning"),
                "dither": self.call("Capture_getdither"),
                "filter": self.current_filter(),
                "persistent": True,
            }
        except CCDcielError:
            return None

    def start_capture(self):
        # Fire the staged capture plan (Capture_start returns immediately).
        self.call("Capture_start")