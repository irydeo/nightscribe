############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - MPC report validator and packager (ADR-022)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Validates and packages pasted astrometric measurements for submission to
# the Minor Planet Center. NightScribe never generates measurements — the
# user pastes them from their astrometry software (Astrometrica, etc.).

# MPC 80-column format field positions (0-indexed, end-exclusive)
_DESIG = (0, 12)     # packed number (1-5) + packed provisional (6-12)
_DATE = (15, 32)     # packed date YYYY MM DD.dddddd
_RA = (32, 44)       # packed RA  HH MM SS.sss
_DEC = (44, 56)      # packed Dec sDD MM SS.ss
_MAG = (65, 70)      # magnitude
_BAND = (70, 72)     # photometric band
_STATION = (77, 80)  # observatory code

_NUM_RE = re.compile(r"^\d+$")
_PROV_RE = re.compile(r"^[A-Z]\d{4}[A-Z]$")  # packed provisional: CYYYY...

# MPC 1992 submission header keywords (ObsDetails.html). A batch that carries
# them must NOT have them counted as measurements (2026-10-11): the report we
# generate now includes the full header, and the round trip through this
# validator has to accept our own output.
_MPC80_HEADER = frozenset((
    "COD", "CON", "OBS", "MEA", "TEL", "NET", "BND", "COM", "NUM", "ACK",
    "AC2", "ACK",
))

# ADES PSV context blocks open with '#' (a section) and '!' (a sub-element).
_ADES_HEADER = ("#", "!")


def _is_header_line(line):
    # @args: line - a raw report line
    # @return: True when it is a header/context line, not a measurement
    st = line.strip()
    if not st:
        return True
    if st.startswith(_ADES_HEADER) or st.startswith("-----"):
        return True
    first = st.split(None, 1)[0].upper()
    return first in _MPC80_HEADER

# ADES PSV required fields (minimum for a valid observation row). The object
# identifier is one of _ADES_ID_FIELDS, checked separately (ADES uses
# permID/provID/trkSub, not the legacy objid).
_ADES_REQUIRED = ("mode", "stn", "obsTime", "ra", "dec")
_ADES_ID_FIELDS = ("objid", "permID", "provID", "trkSub", "artSat")


def detect_format(text):
    # @args: text - pasted measurements
    # @return: "mpc80" | "ades" | None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("!"):
            continue
        if _is_header_line(line):
            continue
        if "|" in s and len(s.split("|")) >= 6:
            return "ades"
        if len(line.rstrip()) == 80:
            return "mpc80"
        # no pipes and looks like a packed designation -> assume mpc80;
        # the per-line validator will catch length issues
        if "|" not in s and len(s) > 5 and s[0].isalnum():
            return "mpc80"
    return None


def first_obs_date(text):
    # The observing date of the first parseable measurement, ISO
    # "YYYY-MM-DD": the MPC 80-column packed date (cols 15-32,
    # "YYYY MM DD.dddddd") or the ADES obsTime field. Used to pre-fill a
    # visit's date from the report it carries (ADR-045).
    # @args: text - the pasted block
    # @return: "YYYY-MM-DD" or None
    fmt = detect_format(text)
    for line in text.splitlines():
        s = line.rstrip()
        if _is_header_line(line):
            continue
        if fmt == "mpc80":
            if len(s) < 80:
                continue
            raw = s[_DATE[0]:_DATE[1]].strip()
            m = re.match(r"^(\d{4})\s(\d{2})\s(\d{2})\.", raw)
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        else:
            parts = [p.strip() for p in s.split("|")]
            if all(p.isalpha() for p in parts):
                continue                       # the header row
            for p in parts:
                m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ]", p)
                if m:
                    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def validate(text, obs_code=None, expected_obj=None):
    # Validates pasted measurements line by line.
    # @args: text - the pasted block, obs_code - expected observatory code,
    #        expected_obj - object name/id from the project context
    # @return: {"format", "valid", "errors"[], "warnings"[], "n_lines",
    #           "designations" set}
    fmt = detect_format(text)
    if fmt is None:
        return {"format": None, "valid": False,
                "errors": ["Unrecognized format (need MPC 80-col or ADES PSV)"],
                "warnings": [], "n_lines": 0, "designations": set()}
    if fmt == "mpc80":
        return _validate_mpc80(text, obs_code, expected_obj)
    return _validate_ades(text, obs_code, expected_obj)


def _validate_mpc80(text, obs_code, expected_obj):
    errors, warnings = [], []
    desigs = set()
    n = 0
    for i, line in enumerate(text.splitlines(), 1):
        s = line.rstrip()
        if _is_header_line(line):
            continue
        n += 1
        if len(s) < 80:
            errors.append(f"Line {i}: too short ({len(s)} chars, need 80)")
            continue
        desig = s[_DESIG[0]:_DESIG[1]].strip()
        date = s[_DATE[0]:_DATE[1]].strip()
        ra = s[_RA[0]:_RA[1]].strip()
        dec = s[_DEC[0]:_DEC[1]].strip()
        station = s[_STATION[0]:_STATION[1]].strip()
        desigs.add(desig)
        # designation must be non-empty
        if not desig or desig == "     ":
            errors.append(f"Line {i}: empty designation")
        # date must look like YYYY MM DD.dddddd
        if not re.match(r"^\d{4}\s\d{2}\s\d{2}\.\d+$", date):
            errors.append(f"Line {i}: bad date format '{date}'")
        # RA must look like HH MM SS.sss
        if not re.match(r"^\d{2}\s\d{2}\s\d{2}\.\d+$", ra):
            errors.append(f"Line {i}: bad RA format '{ra}'")
        # Dec must look like sDD MM SS.ss
        if not re.match(r"^[+-]\d{2}\s\d{2}\s\d{2}\.\d+$", dec):
            errors.append(f"Line {i}: bad Dec format '{dec}'")
        # observatory code
        if obs_code and station.upper() != obs_code.upper():
            errors.append(f"Line {i}: station code '{station}' != '{obs_code}'")
    if expected_obj and desigs:
        # the packed designation should match the expected object
        packed = _pack_desig(expected_obj)
        if packed and packed not in desigs:
            warnings.append(
                f"Designation(s) {desigs} do not match expected '{expected_obj}'"
                f" (packed '{packed}')")
    return {"format": "mpc80", "valid": len(errors) == 0,
            "errors": errors, "warnings": warnings,
            "n_lines": n, "designations": desigs}


def _validate_ades(text, obs_code, expected_obj):
    errors, warnings = [], []
    desigs = set()
    n = 0
    header = None
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("!"):
            continue
        parts = s.split("|")
        if header is None:
            # first data line could be the header or a data row
            if all(p.strip().isalpha() for p in parts):
                header = [p.strip() for p in parts]
                continue
        n += 1
        if header:
            row = dict(zip(header, [p.strip() for p in parts]))
        else:
            row = {f"col{j}": p.strip() for j, p in enumerate(parts)}
        # collect the object id
        for key in ("objid", "permID", "provID", "trkSub", "artSat"):
            if key in row and row[key]:
                desigs.add(row[key])
                break
        # required fields
        for field in _ADES_REQUIRED:
            if field not in row or not row[field]:
                errors.append(f"Line {i}: missing field '{field}'")
        if not any(row.get(f) for f in _ADES_ID_FIELDS):
            errors.append(
                f"Line {i}: no object identifier "
                "(permID/provID/trkSub/artSat)")
        # observatory code
        if obs_code and "stn" in row:
            if row["stn"].upper() != obs_code.upper():
                errors.append(
                    f"Line {i}: station '{row['stn']}' != '{obs_code}'")
    if expected_obj and desigs:
        if expected_obj not in desigs:
            warnings.append(
                f"Object ID(s) {desigs} do not match expected '{expected_obj}'")
    return {"format": "ades", "valid": len(errors) == 0,
            "errors": errors, "warnings": warnings,
            "n_lines": n, "designations": desigs}


def package(text, out, obs_code=None, expected_obj=None):
    # Validates and writes the measurements to a file ready to email to the
    # MPC. Returns the path on success or None on validation failure.
    # @args: text - pasted block, out - output path, obs_code - station,
    #        expected_obj - from project context
    # @return: (path, result) or (None, result)
    result = validate(text, obs_code, expected_obj)
    if not result["valid"]:
        return None, result
    Path(out).write_text(text.rstrip() + "\n", encoding="ascii",
                         errors="replace")
    logger.info("MPC report packaged: %s (%d lines)", out, result["n_lines"])
    return str(out), result


def _pack_desig(name):
    # Best-effort packing of a designation for the cross-check.
    # @args: name - the designation, e.g. "2021 EQ3" or "2026 AB12"
    # @return: the packed form, or None
    # It delegates to the full packer (mpc_astrometry._pack_provisional): the
    # old local mapping counted letters from 1800 and dropped the year, so
    # 2026 packed as "mAB12" instead of "K26A12B" (QA-11) and the validator's
    # warning showed a designation that does not exist. The import is local
    # because mpc_astrometry imports this module.
    name = (name or "").strip()
    if not name:
        return None
    name = re.sub(r"^(?:SN|AT)\s*\d*", "", name.upper())
    try:
        from . import mpc_astrometry
        return mpc_astrometry._pack_provisional(name)
    except Exception:
        return None
