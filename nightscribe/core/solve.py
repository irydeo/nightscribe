############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Plate-solver dispatcher (ADR-051, series plan 9)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""One door to plate solving (ADR-051).

`solver = auto | astap | astrometry`. On "auto" the local ASTAP solver is
tried first (fast, no network) and the nova.astrometry.net client is the
fallback; "astap" and "astrometry" force one backend. Both backends share
the contract `solve(path, progress) -> cards|None` and the same WCS keys,
so the caller never knows which one answered.
"""

import logging
import threading

logger = logging.getLogger(__name__)


class SolveCancel:
    # The dialog's Cancel: a flag the solver polls plus the live process
    # it must kill. Shared by the GUI worker and the ASTAP source (the
    # astrometry.net client is network-bound and just ignores it).
    def __init__(self):
        self._event = threading.Event()
        self._proc = None
        self._lock = threading.Lock()

    def set(self):
        # Marks the solve cancelled and kills the running process now.
        self._event.set()
        with self._lock:
            proc = self._proc
        if proc is not None:
            from .sources.astap import _terminate
            _terminate(proc)

    def is_set(self):
        return self._event.is_set()

    def attach(self, proc):
        # @args: proc - the subprocess.Popen the solver just started; if
        #        Cancel landed first, kill it immediately.
        with self._lock:
            self._proc = proc
        if self._event.is_set():
            from .sources.astap import _terminate
            _terminate(proc)


def cached(path):
    # A WCS this app already solved for the exact file (content hash),
    # WITHOUT invoking a solver: the cache keeps a plate solved across
    # frame switches even when the FITS carries none (solve_save off).
    # @args: path - FITS Path
    # @return: dict of WCS cards, or None
    import hashlib
    import json
    from pathlib import Path
    from .db import db
    try:
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None
    for key in (f"astap:wcs:{digest}", f"astrometry:wcs:{digest}"):
        row = db.cache_get(key)
        if not row:
            continue
        try:
            return json.loads(row[0].decode("utf-8"))
        except (ValueError, AttributeError):
            continue
    return None


def solve(path, progress=None, solver=None, astap_path=None, update=False,
          cancel=None):
    # @args: path - FITS Path, progress - optional callable(stage_text),
    #        solver - "auto"|"astap"|"astrometry" (None reads the setting),
    #        astap_path - the configured ASTAP binary (None reads settings),
    #        update - let a local solve rewrite the FITS header (opt-in),
    #        cancel - a SolveCancel for the dialog's Cancel, or None
    # @return: dict of WCS cards, or None
    from ..config import config
    from .sources import astap, astrometry
    choice = (solver or config.get("solver") or "auto").lower()
    if astap_path is None:
        astap_path = config.get("astap_path") or None
    if choice == "astap":
        return astap.solve(path, progress=progress, astap_path=astap_path,
                           update=update, cancel=cancel)
    if choice == "astrometry":
        return astrometry.solve(path, progress=progress)
    # auto: local first, nova as the fallback
    cards = astap.solve(path, progress=progress, astap_path=astap_path,
                        update=update, cancel=cancel)
    if cards:
        return cards
    if cancel is not None and cancel.is_set():
        return None             # the observer cancelled: no nova fallback
    logger.info("ASTAP did not solve; falling back to nova.astrometry.net")
    return astrometry.solve(path, progress=progress)
