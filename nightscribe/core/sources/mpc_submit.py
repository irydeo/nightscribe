############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Minor Planet Center submission source
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Submit an astrometry report to the Minor Planet Center.

Three endpoints, each with a test twin (commandlinesubmissions.html):

    submit_obs  / submit_obs_test   MPC 1992 (80 columns)
    submit_psv  / submit_psv_test   ADES PSV
    submit_xml  / submit_xml_test   ADES XML

The MPC 1992 endpoint takes the batch alone (it carries AC2 in its own
header); the ADES endpoints take `ack`, `ac2` and `obj_type` as form fields.
The submitted batch must carry a valid observational header, exactly as an
e-mail submission would.

A submission is a POST and cannot be cached, so it does NOT go through
core/db.py: it lives here, the only place allowed to import requests (AGENTS).
The caller is never silent: it shows the server's own answer (the CurlID or
the error list) to the observer.
"""

import logging

import requests

logger = logging.getLogger(__name__)

_BASE = "https://minorplanetcenter.net"
_ENDPOINTS = {
    "mpc80": "submit_obs",
    "ades": "submit_psv",
    "xml": "submit_xml",
}

# The target keyword the MPC needs to route the batch (ObsDetails.html). It
# rides the ACK line in MPC 1992 and the `obj_type` form field in ADES.
TARGETS = (
    "Unclassified", "NEOCP", "PCCP", "NEW NEO", "NEW COMET",
    "NEW NATURAL SATELLITE", "NEW TNO", "NEW KBO", "NEW DISTANT",
    "NEW CENTAUR",
)


def submit(fmt, text, ack="", email="", obj_type="", test=False, timeout=60):
    # @args: fmt - "mpc80" | "ades" | "xml", text - the report, ack - the
    #        acknowledgement text, email - the ac2 address, obj_type - the
    #        target keyword, test - use the *_test endpoint, timeout - seconds
    # @return: {"ok", "status", "text", "url"}: ok is True when the server
    #          answered 200 and the body carries no "error"; text is the
    #          server's own answer (the CurlID or the error list)
    name = _ENDPOINTS.get(fmt)
    if name is None:
        return {"ok": False, "status": 0, "text":
                f"Unknown submission format: {fmt!r}", "url": ""}
    url = f"{_BASE}/{name}" + ("_test" if test else "")
    files = {"source": ("report.txt", text.encode("utf-8"), "text/plain")}
    data = {}
    if fmt != "mpc80":
        data = {"ack": ack or "", "ac2": email or "",
                "obj_type": obj_type or ""}
    try:
        resp = requests.post(url, files=files, data=data, timeout=timeout)
    except requests.RequestException as err:
        logger.warning("MPC submission failed: %s", err)
        return {"ok": False, "status": 0, "url": url,
                "text": f"Could not reach the MPC: {err}"}
    body = (resp.text or "").strip()
    ok = resp.status_code == 200 and "error" not in body.lower()[:400]
    if not ok:
        logger.warning("MPC rejected the submission (HTTP %s): %s",
                       resp.status_code, body[:200])
    return {"ok": ok, "status": resp.status_code, "url": url,
            "text": body or f"HTTP {resp.status_code}"}
