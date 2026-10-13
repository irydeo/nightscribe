############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Observatory backend selector module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""One observatory, two programs.

CCDciel and NINA/PINS are different programs with different transports (a
JSON-RPC 2.0 server on one side, a REST API on the other), but from the
Capture step they do the same five things: report what the mount and the
camera are doing, point the telescope, do an astrometric goto, set the
filter wheel and stage a capture plan. The GUI must not care which one is
on the other end, so both clients answer the SAME method names and raise
the SAME error type; this module picks one from the settings and hands it
over. The rule of AGENTS.md is respected: `requests` still lives only in
`core/sources/`.

Why a selector and not two copies of the panel: a second code path that
does the same thing drifts. If the Stop-goto button or the filter list
were written twice, one of the two would keep the old behaviour the day
the other changed. The GUI talks to `ObservatoryError` and to a fixed set
of methods; each client translates its own protocol into them.
"""


class ObservatoryError(Exception):
    # Base error of any observatory backend. The GUI and the worker catch
    # this one, never the concrete `CCDcielError`/`NinaError`, so a new
    # backend does not have to touch the panel.
    pass


# The backends the observer can pick in Settings -> Integrations.
BACKENDS = ("ccdciel", "nina")

# Config key that carries the choice. Default "ccdciel": the integration
# that existed first, so an existing installation keeps working untouched.
BACKEND_KEY = "observatory_backend"


def backend(cfg):
    # @args: cfg - the Config
    # @return: "ccdciel" or "nina" (unknown values fall back to ccdciel)
    kind = str(cfg.get(BACKEND_KEY, "ccdciel") or "ccdciel").strip().lower()
    return kind if kind in BACKENDS else "ccdciel"


def make_client(cfg):
    # Builds the client for the configured backend.
    # @args: cfg - the Config (host/port live under the backend's own keys)
    # @return: a ccdciel.Client or nina.Client, both with the same surface
    # The imports are local on purpose: each client imports this module for
    # `ObservatoryError`, and a top-level import here would close a circle.
    if backend(cfg) == "nina":
        from . import nina
        return nina.Client(
            host=str(cfg.get("nina_host", "127.0.0.1")),
            port=int(cfg.get("nina_port", nina.DEFAULT_PORT)))
    from . import ccdciel
    return ccdciel.Client(
        host=str(cfg.get("ccdciel_host", "127.0.0.1")),
        port=int(cfg.get("ccdciel_port", ccdciel.DEFAULT_PORT)))
