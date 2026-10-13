############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - NINA / PINS Advanced API v2 source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""NINA (and PINS, its Linux build) through the Advanced API v2 plugin.

NINA has no JSON-RPC server like CCDciel: it exposes a REST API through the
community plugin "N.I.N.A. Advanced API" (christian-photo/ninaAPI). PINS, the
Linux port of NINA, ships the same plugin, so ONE client drives both; only
host and port change. This module is the NINA half of the observatory
abstraction: it answers the same method names as `ccdciel.Client` and raises
`NinaError`, a subclass of `ObservatoryError`, so the GUI never branches on
the backend.

Two facts shape the code:

* Every reply is wrapped: `{"Response": ..., "Error": "", "StatusCode": 200,
  "Success": true, "Type": "API"}`. A `Success: false` (or a non-empty
  `Error`) is the plugin telling us the command did not happen; it becomes a
  `NinaError` with the plugin's own message, never a silent no-op.
* Reads go through the db cache (source "nina", TTL 60 s) so the dashboard
  does not hammer NINA; commands (slew, stop, filter, capture) go straight to
  the server. Never cache the mount state: the sky does not wait.

The mount takes J2000 degrees directly, so unlike CCDciel there is no
`J2000_to_Apparent` conversion here: the plugin builds a `Coordinates(...,
Epoch.J2000)` itself.
"""

import base64
import json
import logging

import requests

from ..db import db
from .observatory import ObservatoryError

logger = logging.getLogger(__name__)

DEFAULT_PORT = 1888
_TIMEOUT = 6.0
# An astrometric goto is a slew PLUS a plate solve PLUS a correction: the
# plugin holds the HTTP call open while it happens. 6 s would cut it off, so
# that one call gets its own, generous ceiling.
_SLEW_TIMEOUT = 240.0


def truthy(result):
    # @args: result - a value the plugin may send as bool, int or "true"/"false"
    # @return: True / False / None when it says nothing
    if isinstance(result, str):
        return result.strip().lower() not in ("", "false", "no", "0", "off")
    if result is None:
        return None
    return bool(result)


class NinaError(ObservatoryError):
    # A NINA/PINS command failed (the plugin answered Success=false) or the
    # API could not be reached. Subclasses ObservatoryError so the GUI and
    # the worker catch it without knowing which backend is in use.
    pass


class Client:
    # Thin REST client for the Advanced API v2 plugin at
    # http://host:1888/v2/api. Reads are cached; commands are direct.
    def __init__(self, host="127.0.0.1", port=DEFAULT_PORT, timeout=_TIMEOUT):
        self.host = host
        self.port = port
        self.timeout = timeout
        # The staged capture plan lives here, not in NINA: the snapshot
        # endpoint is stateless, so "Send plan" remembers what "Start
        # capture" must fire. See push_plan/start_capture.
        self._staged = {}

    @property
    def base(self):
        return f"http://{self.host}:{self.port}/v2/api"

    # -- transport ------------------------------------------------------------

    def _get(self, path, params=None, timeout=None):
        # Raw GET plus envelope unwrapping.
        # @args: path - API path ("/equipment/mount/info"),
        #        params - query dict, timeout - per-call override (s)
        # @return: the "Response" member
        # @raise: NinaError on transport trouble or Success=false
        url = f"{self.base}{path}"
        logger.debug("nina GET %s %s", path, params)
        try:
            r = requests.get(url, params=params or None,
                             timeout=timeout or self.timeout)
            body = r.json()
        except (requests.RequestException, ValueError) as err:
            raise NinaError(f"{path}: no answer from {url}: {err}") from err
        if not isinstance(body, dict):
            return body
        if body.get("Success") is False or body.get("Error"):
            raise NinaError(f"{path}: {body.get('Error') or body.get('StatusCode')}")
        return body.get("Response")

    def call(self, path, params=None, timeout=None):
        # Command / live-state path: never cached.
        # @args: path - API path, params - query dict, timeout - per-call (s)
        # @return: the "Response" member
        return self._get(path, params, timeout)

    def read(self, path, key, params=None):
        # Cached read path (db.http_get, "nina" source, 60 s TTL).
        # @args: path - API path, key - cache key, params - query dict
        # @return: the "Response" member, straight from the cache
        def fetch():
            result = self._get(path, params)
            return json.dumps(result).encode("utf-8"), "application/json"
        body, _ = db.http_get(f"nina:{path}:{key}", "nina", fetch)
        return json.loads(body.decode("utf-8"))

    def _get_bytes(self, path, params=None, timeout=None):
        # Raw GET that returns BINARY (an image stream). The plugin answers
        # image/png or image/jpeg on success and a JSON error envelope on
        # failure, so the content type decides which one we are looking at.
        # @args: path - API path, params - query dict, timeout - per-call (s)
        # @return: the response body as bytes
        # @raise: NinaError on transport trouble or a JSON error
        url = f"{self.base}{path}"
        try:
            r = requests.get(url, params=params or None,
                             timeout=timeout or self.timeout)
        except requests.RequestException as err:
            raise NinaError(f"{path}: no answer from {url}: {err}") from err
        if r.headers.get("Content-Type", "").startswith("image"):
            return r.content
        try:
            body = r.json()
        except ValueError:
            raise NinaError(f"{path}: HTTP {r.status_code}")
        raise NinaError(f"{path}: {body.get('Error') or r.status_code}")

    # -- observatory status ----------------------------------------------------

    def ping(self):
        # NINA's own version, in friendly form ("3.2 NIGHTLY #058"). Proves
        # the plugin is installed and answering.
        # @return: version string, or None when unreachable
        try:
            v = self.read("/version/nina", "version", {"friendly": "true"})
        except NinaError:
            return None
        return str(v) if v is not None else None

    def dashboard(self):
        # Aggregated status shaped like CCDciel's dashboard, so the Capture
        # panel renders both backends with one piece of code.
        # @return: dict with camera/mount/filterwheel sections; {} on error
        try:
            eq = self.read("/equipment/info", "equipment") or {}
        except NinaError:
            return {}
        cam = eq.get("Camera") or {}
        mount = eq.get("Mount") or {}
        wheel = eq.get("FilterWheel") or {}
        return {
            "camera": {"temperature": cam.get("Temperature"),
                       "connected": cam.get("Connected")},
            # the plugin names it TrackingEnabled, not Tracking: reading the
            # wrong key would show "Stopped" on a tracking mount
            "mount": {"tracking": mount.get("TrackingEnabled"),
                      "slewing": mount.get("Slewing"),
                      "connected": mount.get("Connected")},
            "filterwheel": {"connected": wheel.get("Connected")},
        }

    def filters(self):
        # The filter names the profile defines (they come from the wheel
        # settings, so they are the real ones even before the wheel is
        # connected: the list is the observer's, not a guess).
        # @return: list of filter names, or None if the API does not answer
        try:
            info = self.read("/equipment/filterwheel/info", "filters") or {}
        except NinaError:
            return None
        names = [f.get("Name") for f in (info.get("AvailableFilters") or [])]
        names = [n for n in names if n]
        return names or None

    def connected(self):
        # @return: True when both the mount and the camera report connected
        dash = self.dashboard()
        mount = dash.get("mount") or {}
        cam = dash.get("camera") or {}
        return bool(mount.get("connected")) and bool(cam.get("connected"))

    def _mount_info(self):
        # @return: the mount info dict, or {} when the call fails
        try:
            return self.call("/equipment/mount/info") or {}
        except NinaError:
            return {}

    def slewing(self):
        # @return: True while the mount is slewing (live, uncached)
        return bool(truthy(self._mount_info().get("Slewing")))

    def tracking(self):
        # @return: True when the mount is tracking (live, uncached)
        return bool(truthy(self._mount_info().get("TrackingEnabled")))

    def capturing(self):
        # @return: True while the camera is exposing (live, uncached). The
        # Capture step uses it to stop watching the folder once the run ends.
        try:
            cam = self.call("/equipment/camera/info") or {}
        except NinaError:
            return False
        return bool(truthy(cam.get("IsExposing")))

    def current_gain(self):
        # The camera's gain SETTING (its own index), not the system gain in
        # e-/ADU (a photometry quantity, in the profile).
        # @return: the gain (int) or None
        try:
            cam = self.call("/equipment/camera/info") or {}
            value = cam.get("Gain")
            return int(value) if value is not None else None
        except (NinaError, TypeError, ValueError):
            return None

    def current_offset(self):
        # @return: the camera's offset setting (int) or None
        try:
            cam = self.call("/equipment/camera/info") or {}
            value = cam.get("Offset")
            return int(value) if value is not None else None
        except (NinaError, TypeError, ValueError):
            return None

    def stop_capture(self):
        # Stop a running capture (ADR-081): abort the exposure in progress.
        # This is the exact analogue of the snapshot that "Start capture"
        # fires; when sequences are loaded through the API, /sequence/stop will
        # be the pair. It stops the CAMERA, not the mount (that is
        # abort_motion / the Stop-goto button).
        # @return: True when the plugin accepted the abort
        self.call("/equipment/camera/abort-exposure")
        return True

    def last_frame_preview(self):
        # The last frame NINA saved, as a small PNG, with the numbers the
        # Capture step shows. Works local and remote: the image comes over the
        # same HTTP API as everything else. NINA keeps an image history; the
        # last entry is the frame to show.
        # @return: dict with image (PNG bytes), index, name, filter, exptime_s,
        #          date_obs; or None when there is no image yet
        count = self.call("/image-history", {"count": "true"})
        try:
            count = int(count)
        except (TypeError, ValueError):
            return None
        if count <= 0:
            return None
        index = count - 1
        rows = self.call("/image-history",
                         {"index": index, "all": "false"}) or []
        meta = rows[0] if isinstance(rows, list) and rows else {}
        image = self._get_bytes(
            f"/image/{index}",
            {"stream": "true", "resize": "true", "size": "200x200",
             "quality": "-1"})
        return {"image": image, "index": index,
                "name": meta.get("Filename"),
                "filter": meta.get("Filter"),
                "exptime_s": meta.get("ExposureTime"),
                "date_obs": meta.get("Date")}

    def image_fits_bytes(self, index):
        # The raw FITS of one history entry, so "Open in the editor" works
        # against a remote observatory. The plugin returns it base64-encoded;
        # it is the one place this client touches base64, and the plugin warns
        # the flag may be withdrawn (documented in ADR-082).
        # @args: index - the image's position in NINA's history
        # @return: the FITS bytes
        resp = self.call(f"/image/{int(index)}", {"raw_fits": "true"})
        try:
            return base64.b64decode(resp)
        except (TypeError, ValueError) as err:
            raise NinaError(f"raw_fits: not base64 ({err})") from err

    def abort_motion(self):
        # Safety stop: abort the current slew (and, for a center/rotate, its
        # job token). This is what the Stop-goto button calls.
        # @return: True when the plugin accepted the stop
        self.call("/equipment/mount/slew/stop")
        return True

    # -- coordinates and motion -------------------------------------------------

    def slew_target(self, ra_deg, dec_deg):
        # Slew to a J2000 target. No apparent conversion: the plugin builds
        # a J2000 Coordinates itself.
        # @args: ra_deg/dec_deg - J2000 target coordinates (degrees)
        # @return: (ra_deg, dec_deg) the mount was told to point at
        self.call("/equipment/mount/slew",
                  {"ra": float(ra_deg), "dec": float(dec_deg)})
        return ra_deg, dec_deg

    def sync_target(self, ra_deg, dec_deg):
        # @args: ra_deg/dec_deg - J2000 coordinates (degrees)
        # @return: (ra_deg, dec_deg) the mount was synced to
        self.call("/equipment/mount/sync",
                  {"ra": float(ra_deg), "dec": float(dec_deg)})
        return ra_deg, dec_deg

    # -- astrometric pointing ---------------------------------------------------

    def astrometry_goto(self, ra_deg, dec_deg):
        # Slew + plate-solve + correct. NINA's "Center" instruction is the
        # exact equivalent of CCDciel's astrometric goto: it points, solves
        # the frame and re-points to the true sky position. `waitForResult`
        # makes the plugin hold the call until the job ends, so the worker
        # stays busy exactly as long as the mount does; the solve failing
        # comes back as Success=false and becomes a NinaError.
        # @args: ra_deg/dec_deg - J2000 target coordinates (degrees)
        # @return: (ra_deg, dec_deg) the mount was told to point at
        self.call("/equipment/mount/slew",
                  {"ra": float(ra_deg), "dec": float(dec_deg),
                   "center": "true", "waitForResult": "true"},
                  timeout=_SLEW_TIMEOUT)
        return ra_deg, dec_deg

    # -- filter wheel -----------------------------------------------------------

    def set_filter(self, index):
        # @args: index - slot number in the wheel (0-based)
        # @return: True when the wheel accepted the change
        self.call("/equipment/filterwheel/change-filter",
                  {"filterId": int(index)})
        return True

    # -- capture ------------------------------------------------------------------

    def push_plan(self, n_frames, exp_s, object_name, dither=None, gain=None,
                  offset=None, binning=None, filter_index=None):
        # NINA's snapshot endpoint has no persistent "staged capture" the way
        # CCDciel's Capture module does, and no frame count at all: it takes
        # one exposure and fires. So "staging" means remembering the plan
        # here, and the count is shown as information (the guide says so out
        # loud). The returned dict is what the panel prints, with
        # persistent=False so the text can be honest about it. ADR-083: the
        # camera options ride along and start_capture applies what it can.
        # @args: n_frames - exposure count (advisory on NINA), exp_s -
        #        exposure (s), object_name - FITS OBJNAME, dither/gain/
        #        offset/binning - recipe values (None = leave as is),
        #        filter_index - wheel slot to move to (None = leave as is)
        # @return: dict describing the staged plan
        self._staged = {"object": object_name or "NightScribe",
                        "exposure_s": float(exp_s),
                        "count": int(n_frames),
                        "frame_type": "Light",
                        "persistent": False,
                        "dither": dict(dither or {}),
                        "gain": gain,
                        "offset": offset,
                        "binning": binning,
                        "filter_index": filter_index}
        return dict(self._staged)

    def staged_plan(self):
        # @return: the plan held for the next Start capture (or {})
        return dict(self._staged)

    def start_capture(self):
        # Fires ONE snapshot with the staged exposure and object name (NINA's
        # `equipment/camera/capture`). `save=true` writes the FITS; the frame
        # type is a Light. Without a staged plan there is nothing to fire.
        # @return: True when the plugin accepted the capture
        # @raise: NinaError when no plan was staged
        st = self._staged
        if not st:
            raise NinaError("stage a plan first (Send plan)")
        # the wheel is best-effort: a refused slot must not lose the capture
        if st.get("filter_index") is not None:
            try:
                self.set_filter(int(st["filter_index"]))
            except (NinaError, TypeError, ValueError):
                pass
        if st.get("binning"):
            self.call("/equipment/camera/set-binning",
                      {"binning": str(st["binning"])})
        params = {"duration": float(st.get("exposure_s", 1.0)),
                  "targetName": st.get("object") or "NightScribe",
                  "imageType": "LIGHT", "save": "true"}
        if st.get("gain") not in (None, ""):
            params["gain"] = int(st["gain"])
        self.call("/equipment/camera/capture", params)
        return True
