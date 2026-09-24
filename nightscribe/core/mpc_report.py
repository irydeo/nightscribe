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
_DESIG = (0, 5)      # packed designation
_DATE = (15, 32)     # packed date YYYY MM DD.dddddd
_RA = (32, 44)       # packed RA  HH MM SS.sss
_DEC = (44, 56)      # packed Dec sDD MM SS.ss
_MAG = (65, 70)      # magnitude
_BAND = (70, 72)     # photometric band
_STATION = (77, 80)  # observatory code

_NUM_RE = re.compile(r"^\d+$")
_PROV_RE = re.compile(r"^[A-Z]\d{4}[A-Z]$")  # packed provisional: CYYYY...

# ADES PSV required fields (minimum for a valid observation row)
_ADES_REQUIRED = ("objid", "mode", "stn", "obsTime", "ra", "dec")


def detect_format(text):
    # @args: text - pasted measurements
    # @return: "mpc80" | "ades" | None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
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
        if not s.strip() or s.strip().startswith("#"):
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
        if not s or s.startswith("#"):
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
        if not s or s.startswith("#"):
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
        for key in ("objid", "provID", "permID"):
            if key in row and row[key]:
                desigs.add(row[key])
                break
        # required fields
        for field in _ADES_REQUIRED:
            if field not in row or not row[field]:
                errors.append(f"Line {i}: missing field '{field}'")
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
    # Best-effort packing of a provisional designation for the cross-check.
    # "2021EQ3" -> "J01EQ3" (year 2000+ -> first char I=2000, J=2001...)
    # "2026ziz" -> packed minor planet provisional (not SN)
    name = name.strip().upper().replace(" ", "")
    # strip SN/AT prefix if present
    name = re.sub(r"^(SN|AT)\d*", "", name)
    if len(name) < 5:
        return None
    # try provisional: YYYY + 4-char half-month/number
    m = re.match(r"^(\d{4})([A-Z])(\w+)$", name)
    if m:
        year = int(m.group(1))
        if 1800 <= year <= 1899:
            c = chr(65 + (year - 1800))  # A=1800
        elif 1900 <= year <= 1999:
            c = chr(74 + (year - 1900))  # J=1900, but A=1800, I=1808...
        elif 2000 <= year <= 2099:
            c = chr(65 + (year - 2000) + 18)  # I=1808... actually:
        else:
            return None
        rest = m.group(2) + m.group(3)
        if len(rest) >= 4:
            return f"{c}{rest[:4]}"
    return None
