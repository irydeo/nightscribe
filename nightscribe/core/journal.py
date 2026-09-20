############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Observing journal: the derived activity view (ADR-036)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""The observing journal (ADR-036, J1): a derived, read-only view of what
the observatory did, grouped by OBSERVING NIGHT (noon-to-noon local time —
a night crosses midnight). Nothing is marked by hand: the journal is the
UNION of what the app already records — projects created/closed, follow-up
visits, files written, photometry added, campaigns created/finished — plus
the legacy `observations` rows (which live on as a source; ADR-002: never
break existing databases). All functions are pure queries over SQLite.
"""

import datetime
import logging
import time

logger = logging.getLogger(__name__)

MJD_UNIX = 2440587.5 - 2400000.5    # MJD of the unix epoch

# event kinds (the GUI filter combo lists them in this order)
K_PROJECT = "project"       # created / closed (with outcome)
K_SESSION = "session"       # a follow-up visit logged
K_FILE = "file"             # an artefact written (sequence, FITS, post…)
K_PHOTOMETRY = "photometry"  # points added (aggregated per night+project)
K_CAMPAIGN = "campaign"     # created / finished
K_OBSERVATION = "observation"  # legacy "marked observed" rows

_KIND_LABELS = {
    K_PROJECT: {"es": "Proyectos", "en": "Projects"},
    K_SESSION: {"es": "Visitas", "en": "Visits"},
    K_FILE: {"es": "Ficheros", "en": "Files"},
    K_PHOTOMETRY: {"es": "Fotometría", "en": "Photometry"},
    K_CAMPAIGN: {"es": "Campañas", "en": "Campaigns"},
    K_OBSERVATION: {"es": "Marcas manuales", "en": "Manual marks"},
}

# project_files.kind -> readable pair (fallback: the raw kind)
_FILE_LABELS = {
    "sequence": ("Secuencia exportada", "Sequence exported"),
    "ephemeris": ("Efemérides exportadas", "Ephemeris exported"),
    "fits": ("FITS importado", "FITS imported"),
    "post": ("Borrador de post guardado", "Post draft saved"),
    "chart": ("Gráfico generado", "Chart rendered"),
    "report": ("Informe generado", "Report written"),
    "animation": ("Animación generada", "Animation rendered"),
    "image": ("Imagen registrada", "Image registered"),
}


def kind_label(kind, lang="es"):
    # @return: the human label of an event kind for the filter combo
    return _KIND_LABELS.get(kind, {}).get(lang, kind)


def night_of(ts):
    # The observing-night key of an instant: noon-to-noon LOCAL time, so
    # 23:59 and 00:30 of the same session share one night (ADR-036 JO-c).
    # @args: ts - unix epoch seconds
    # @return: "YYYY-MM-DD" of the night the instant belongs to
    dt = datetime.datetime.fromtimestamp(ts).astimezone()
    if dt.hour < 12:
        dt -= datetime.timedelta(days=1)
    return dt.date().isoformat()


def hm_local(ts):
    # @return: "HH:MM" local time of an instant
    return datetime.datetime.fromtimestamp(ts).astimezone().strftime(
        "%H:%M")


def _mjd_to_ts(mjd):
    # @return: unix epoch seconds of an MJD instant
    return (mjd + MJD_UNIX) * 86400.0


def _project_events(db):
    # projects: created, and closed (with its outcome)
    rows = db.execute(
        "SELECT id, kind, object_name, created, closed_at, outcome"
        " FROM projects").fetchall()
    out = []
    for pid, kind, name, created, closed_at, outcome in rows:
        out.append({"ts": created, "kind": K_PROJECT, "object": name,
                    "project_id": pid,
                    "text": (f"Proyecto creado ({kind})",
                             f"Project created ({kind})")})
        if closed_at:
            label = outcome or ""
            out.append({"ts": closed_at, "kind": K_PROJECT,
                        "object": name, "project_id": pid,
                        "text": (f"Proyecto cerrado — {label}".rstrip(" —"),
                                 f"Project closed — {label}".rstrip(" —"))})
    return out


def _session_events(db):
    # project_sessions joined to their project for the object name
    rows = db.execute(
        "SELECT s.created, s.notes, p.object_name, s.project_id"
        " FROM project_sessions s JOIN projects p ON p.id = s.project_id"
    ).fetchall()
    out = []
    for created, notes, name, pid in rows:
        extra = f" — {notes}" if notes else ""
        out.append({"ts": created, "kind": K_SESSION, "object": name,
                    "project_id": pid,
                    "text": (f"Visita de seguimiento{extra}",
                             f"Follow-up visit{extra}")})
    return out


def _file_events(db):
    # project_files joined to their project; the kind maps to a label
    rows = db.execute(
        "SELECT f.created, f.kind, p.object_name, f.project_id"
        " FROM project_files f JOIN projects p ON p.id = f.project_id"
    ).fetchall()
    out = []
    for created, kind, name, pid in rows:
        es, en = _FILE_LABELS.get(kind, (kind or "?",)*2)
        out.append({"ts": created, "kind": K_FILE, "object": name,
                    "project_id": pid, "text": (es, en)})
    return out


def _photometry_events(db):
    # points have no wall-clock of their own: the observation instant
    # (mjd) is what belongs to a night; aggregated per project per night
    rows = db.execute(
        "SELECT pp.project_id, p.object_name, pp.mjd, pp.filter"
        " FROM photometry_points pp JOIN projects p"
        " ON p.id = pp.project_id WHERE pp.mjd IS NOT NULL").fetchall()
    groups = {}
    for pid, name, mjd, filt in rows:
        key = (pid, night_of(_mjd_to_ts(mjd)))
        groups.setdefault(key, {"ts": 0.0, "name": name, "filters": set(),
                                "n": 0})
        g = groups[key]
        g["ts"] = max(g["ts"], _mjd_to_ts(mjd))
        g["filters"].add(filt or "?")
        g["n"] += 1
    out = []
    for (pid, _night), g in groups.items():
        filters = ", ".join(sorted(g["filters"]))
        out.append({"ts": g["ts"], "kind": K_PHOTOMETRY,
                    "object": g["name"], "project_id": pid,
                    "text": (f"Fotometría: {g['n']} punto(s) [{filters}]",
                             f"Photometry: {g['n']} point(s) [{filters}]")})
    return out


def _campaign_events(db):
    rows = db.execute(
        "SELECT name, created, closed_at FROM campaigns").fetchall()
    out = []
    for name, created, closed_at in rows:
        out.append({"ts": created, "kind": K_CAMPAIGN, "object": name,
                    "project_id": None,
                    "text": ("Campaña creada", "Campaign created")})
        if closed_at:
            out.append({"ts": closed_at, "kind": K_CAMPAIGN,
                        "object": name, "project_id": None,
                        "text": ("Campaña finalizada", "Campaign finished")})
    return out


def _legacy_observations(db):
    # the v2-era manual marks live on as journal entries (ADR-036 JO-d)
    rows = db.execute(
        "SELECT object, created, notes FROM observations").fetchall()
    out = []
    for name, created, notes in rows:
        extra = f" — {notes}" if notes else ""
        out.append({"ts": created, "kind": K_OBSERVATION, "object": name,
                    "project_id": None,
                    "text": (f"Marcado como observado{extra}",
                             f"Marked as observed{extra}")})
    return out


def build_journal(db, days=90, now=None):
    # The journal: every recorded event of the last N days, grouped by
    # observing night (newest night first, newest event first inside).
    # @args: db - Database, days - look-back window, now - epoch seconds
    #        (tests inject a fixed "now")
    # @return: [{"night": "YYYY-MM-DD", "events": [event dicts]}]
    now = now if now is not None else time.time()
    events = (_project_events(db) + _session_events(db)
              + _file_events(db) + _photometry_events(db)
              + _campaign_events(db) + _legacy_observations(db))
    cutoff = now - days * 86400
    events = [dict(e, night=night_of(e["ts"])) for e in events
              if e["ts"] is not None and e["ts"] >= cutoff]
    events.sort(key=lambda e: -e["ts"])
    nights = []
    for e in events:
        if not nights or nights[-1]["night"] != e["night"]:
            nights.append({"night": e["night"], "events": []})
        nights[-1]["events"].append(e)
    return nights
