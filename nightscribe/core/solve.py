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

logger = logging.getLogger(__name__)


def solve(path, progress=None, solver=None, astap_path=None, update=False):
    # @args: path - FITS Path, progress - optional callable(stage_text),
    #        solver - "auto"|"astap"|"astrometry" (None reads the setting),
    #        astap_path - the configured ASTAP binary (None reads settings),
    #        update - let a local solve rewrite the FITS header (opt-in)
    # @return: dict of WCS cards, or None
    from ..config import config
    from .sources import astap, astrometry
    choice = (solver or config.get("solver") or "auto").lower()
    if astap_path is None:
        astap_path = config.get("astap_path") or None
    if choice == "astap":
        return astap.solve(path, progress=progress, astap_path=astap_path,
                           update=update)
    if choice == "astrometry":
        return astrometry.solve(path, progress=progress)
    # auto: local first, nova as the fallback
    cards = astap.solve(path, progress=progress, astap_path=astap_path,
                        update=update)
    if cards:
        return cards
    logger.info("ASTAP did not solve; falling back to nova.astrometry.net")
    return astrometry.solve(path, progress=progress)
