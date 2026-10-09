############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Object brief: the facts, with their why, in one place
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

"""Everything the app knows about ONE project, as a fact sheet (ADR-075).

The post used to be poor because it only saw the enriched catalogue entry:
the orbital data, never the observer's own work. This module gathers the
whole picture in one structured dict — the object and its explained facts,
the night it was planned for, the visits, the measured points and the
campaign verdict, the charts that were made — so a writer (a language model
or a template) can tell the real story instead of the catalogue's.

Two rules decide what goes in:

* Every figure carries its "why". The object's facts are not re-explained
  here: they come from the very same `orbits.explain_*` rows the object
  card shows (ADR-058), so the brief can never disagree with the card.
* Nothing is invented. A missing section is simply absent; the writer is
  told to use only what it finds.

No network and no Qt: `enrich` (when the caller has it) is passed in, and
everything else is local arithmetic on the project, the visits and the
photometry points. That keeps the brief usable from the CLI and testable
without a connection.
"""

import datetime
import logging

from . import explain, followup, kinds, orbits, project as project_mod, series
from ..config import config

logger = logging.getLogger(__name__)

# MJD of 1970-01-01: enough to turn a photometry point's time into a date
# without dragging in an astronomy library for a calendar subtraction.
_MJD_UNIX = 40587.0

# A project can hold hundreds of points. The writer needs the shape and the
# trend, not every row, and every row costs tokens: the summary always goes
# in full, the per-point list is capped and says when it was cut. The short
# post keeps a tight cap; the long report can afford far more of the curve
# (its whole point is to tell the story, and a local model pays no token).
_MAX_POINTS = 40
_MAX_POINTS_LONG = 200


def _pick(entry, lang):
    # @args: entry - a {"es","en"} pair from explain/orbits, lang - "es"|"en"
    # @return: the string in the wanted language, falling back to the other
    if not entry:
        return ""
    return entry.get(lang) or entry.get("en") or entry.get("es") or ""


def _mjd_date(mjd):
    # @args: mjd - a Modified Julian Date
    # @return: "YYYY-MM-DD" (UTC), or "" when the value is unusable
    try:
        d = datetime.datetime(1970, 1, 1) + datetime.timedelta(
            days=float(mjd) - _MJD_UNIX)
    except (TypeError, ValueError):
        return ""
    return d.strftime("%Y-%m-%d")


def explained_facts(enriched):
    # The object's parameters, each with its meaning, from the SAME
    # dispatch the object card uses (gui/overview.py): one home for the
    # "why", never two (ADR-058).
    # @args: enriched - an enrich.enrich() result, or None
    # @return: list of {"label","value","why","level"}
    if not enriched:
        return []
    d = enriched.get("data") or {}
    sb = d.get("sbdb")
    if sb:
        moid = sb.get("moid")
        try:
            moid = float(moid) if moid is not None else None
        except (TypeError, ValueError):
            moid = None
        rows = orbits.explain_elements(
            sb.get("elements") or {}, sb.get("phys") or {}, d.get("family"),
            moid, sigmas=sb.get("sigmas"), n_resids=sb.get("n_resids"),
            arc_days=sb.get("arc_days"), disc_date=sb.get("disc_date"))
    elif d.get("unconfirmed"):
        rows = orbits.explain_neofixer(d["unconfirmed"])
    elif enriched.get("type") == "transient":
        rows = orbits.explain_transient(d)
    elif enriched.get("type") == "exoplanet" or d.get("transit"):
        rows = orbits.explain_transit(
            d, aperture_in=config.get("aperture_inches"))
    elif enriched.get("type") == "hads" or d.get("hads"):
        rows = orbits.explain_hads(d)
    elif enriched.get("type") == "variable" or d.get("variable"):
        rows = orbits.explain_variable(d)
    else:
        rows = []
    return rows


def _facts(brief_lang, rows):
    # @args: brief_lang - "es"|"en", rows - explain_* rows (bilingual)
    # @return: the rows flattened to one language: label, value and why
    out = []
    for r in rows or []:
        out.append({
            "label": _pick(r.get("param"), brief_lang),
            "value": r.get("value"),
            "why": _pick(r, brief_lang),
            "level": r.get("level") or "basic",
        })
    return out


def _night(ctx, brief_lang):
    # The planning snapshot the project kept (planner target), worded so the
    # writer never shows a bare figure: the altitude gets its meaning from
    # the shared glossary, the window is a time span and reads itself.
    # @args: ctx - the project context dict, brief_lang - "es"|"en"
    # @return: dict (possibly empty)
    out = {}
    sw = ctx.get("safe_window")
    if sw:
        try:
            s0, s1 = str(sw).split("|")
            out["window"] = f"{s0[11:16]}–{s1[11:16]} UTC"
        except ValueError:
            out["window"] = str(sw)
    bt = ctx.get("best_time")
    if bt:
        out["best_time"] = f"{str(bt)[11:16]} UTC"
    if ctx.get("hours_up") is not None:
        out["hours_up"] = ctx.get("hours_up")
    if ctx.get("max_alt") is not None:
        out["max_alt"] = ctx.get("max_alt")
        out["max_alt_why"] = _pick(explain.ALTITUDE["short"], brief_lang)
    return out


def _observations(db, project, max_points=_MAX_POINTS):
    # The observer's own work: visits, the curve and the campaign verdict.
    # This is the half the old post never saw.
    # @args: db - Database, project - project dict, max_points - how many
    #        of the newest points to spell out (the long report keeps more)
    # @return: dict (possibly empty)
    pid = project["id"]
    sessions = followup.list_sessions(db, pid)
    points = followup.list_points(db, pid)
    out = {
        "sessions": [{"date": s.get("obs_date"), "notes": s.get("notes")}
                     for s in sessions],
    }
    if not points:
        return out
    mags = [p["mag"] for p in points if p.get("mag") is not None]
    filters = sorted({(p.get("filter") or "Clear") for p in points})
    nights = sorted({_mjd_date(p.get("mjd")) for p in points
                     if p.get("mjd") is not None})
    out.update({
        "n_points": len(points),
        "n_nights": len(nights),
        "filters": filters,
        "mag_min": min(mags) if mags else None,
        "mag_max": max(mags) if mags else None,
    })
    last = points[-1]
    out["latest"] = {
        "date": _mjd_date(last.get("mjd")),
        "filter": last.get("filter") or "Clear",
        "mag": last.get("mag"),
        "err": last.get("err"),
    }
    ctx = project.get("context") or {}
    sn_type = ctx.get("sn_type") or ctx.get("otype")
    out["campaign"] = series.analyze_campaign(points, sn_type=sn_type)
    rows = []
    for p in points[-max_points:]:
        rows.append({"date": _mjd_date(p.get("mjd")),
                     "filter": p.get("filter") or "Clear",
                     "mag": p.get("mag"), "err": p.get("err")})
    out["points"] = rows
    out["points_truncated"] = len(points) > max_points
    return out


def _analysis(db, project, lang):
    # The work that is NOT the light curve: a saved period, the transit
    # event, the astrometry runs and the photometry recipe. It is all in the
    # app already; the long report is the one place that tells it whole. The
    # short post does not carry it (every extra figure costs tokens and the
    # social post is not where a residual belongs).
    # @args: db - Database, project - project dict, lang - "es"|"en"
    # @return: dict (possibly empty)
    ctx = project.get("context") or {}
    out = {}
    if ctx.get("period_d"):
        out["period"] = {
            "days": ctx.get("period_d"),
            "method": ctx.get("period_method"),
            "fap": ctx.get("period_fap"),
            "cycles": ctx.get("period_cycles"),
            "source": ctx.get("period_source"),
            "why": _pick(explain.PERIOD["short"], lang),
        }
    tr = ctx.get("transit") or {}
    if tr.get("depth_mmag") is not None or tr.get("mid"):
        out["transit"] = {
            "depth_mmag": tr.get("depth_mmag"),
            "duration_min": tr.get("duration_min"),
            "mid": tr.get("mid"),
            "why": _pick(explain.DEPTH["short"], lang),
        }
    # astrometry runs (ADR-062): the measured positions and their residual
    try:
        from . import astrometry_store
        runs = astrometry_store.list_runs(db, project["id"])
    except Exception:
        runs = []
    arows = []
    for r in runs:
        if r.get("status") not in (None, "complete", "ok"):
            continue
        pts = astrometry_store.points_for_run(db, r["id"])
        arows.append({
            "date": _mjd_date(pts[0].get("mjd") if pts else None),
            "method": r.get("method"),
            "n_obs": len(pts),
            "detected": r.get("detected"),
            "rate_arcsec_min": r.get("rate_arcsec_min"),
            "points": [{"ra": p.get("ra"), "dec": p.get("dec"),
                        "rms_ra": p.get("rms_ra"), "rms_dec": p.get("rms_dec"),
                        "mag": p.get("mag"), "snr": p.get("snr")}
                       for p in pts],
        })
    if arows:
        out["astrometry"] = arows
    # the photometry recipe: the newest run that has points. The band and
    # whatever scalar knobs it stored travel so the report can say how the
    # brightness was measured, not only what it came out as.
    try:
        run = followup.latest_curve_run(db, project["id"])
    except Exception:
        run = None
    if run:
        series = (run.get("cfg") or {}).get("series") or {}
        recipe = {k: v for k, v in series.items()
                  if isinstance(v, (str, int, float, bool))}
        out["photometry"] = {
            "band": series.get("band"),
            "n_points": run.get("points"),
            "recipe": recipe,
        }
    return out


def _campaign(db, project):
    # The campaign this project hangs from (ADR-035), when it does: the
    # effort the observation belongs to, with the agreed protocol. The
    # report tells that context; the short post does not.
    # @args: db - Database, project - project dict
    # @return: dict (possibly empty)
    cid = project.get("campaign_id")
    if not cid:
        return {}
    try:
        from . import campaign as campaign_mod
        c = campaign_mod.get(db, cid)
    except Exception:
        c = None
    if not c:
        return {}
    return {"name": c.get("name"), "coordinator": c.get("coordinator"),
            "goal": c.get("goal"), "protocol": c.get("protocol") or {},
            "report_url": c.get("report_url")}


def _assets(db, project):
    # The files that hang from the project, grouped by kind: the writer may
    # want to mention that a chart exists; the caller attaches the paths.
    # @args: db - Database, project - project dict
    # @return: list of {"kind","name"}
    out = []
    for f in project_mod.list_files(db, project["id"]):
        path = f.get("path") or ""
        out.append({"kind": f.get("kind") or "",
                    "name": path.rsplit("/", 1)[-1]})
    return out


def build_brief(project, db, enriched=None, lang="es", cfg=None, long=False,
                gallery=None):
    # Assembles the fact sheet for one project.
    # @args: project - a project dict (project.get), db - Database,
    #        enriched - an enrich.enrich() result when the caller has one
    #        (the post flow does; without it the object's facts are omitted
    #        rather than half-told), lang - "es"|"en" for the explanations,
    #        cfg - Config, or None to use the shared one,
    #        long - True for the LONG report: adds the analysis, the campaign
    #        and the gallery, and keeps far more of the curve,
    #        gallery - [{"key","name","caption"}] the app rendered, so the
    #        report can cite the exact image files
    # @return: the brief dict
    cfg = cfg or config
    kind_id = project.get("kind") or ""
    k = kinds.by_id(kind_id) or {}
    ctx = project.get("context") or {}
    max_points = _MAX_POINTS_LONG if long else _MAX_POINTS
    brief = {
        "language": lang,
        "object": {
            "name": project.get("object_name") or "",
            "kind": kind_id,
            "kind_label": k.get("label") or kind_id,
            "status": project.get("status") or "",
            "created": project.get("created"),
        },
        "object_facts": _facts(lang, explained_facts(enriched)),
        "night": _night(ctx, lang),
        "observations": _observations(db, project, max_points),
        "assets": _assets(db, project),
        "observatory": {
            "name": cfg.get("observatory_name") or "",
            "mpc": cfg.get("mpc_code") or "",
        },
    }
    if long:
        brief["analysis"] = _analysis(db, project, lang)
        brief["campaign"] = _campaign(db, project)
        if gallery:
            brief["gallery"] = gallery
    return brief


# ---------------- rendering for the prompt ----------------

def to_text(brief, lang=None, deep=False):
    # Renders the brief as a compact, readable dossier for a prompt (and
    # for the "what will be sent" preview). Only the sections that carry
    # something are printed.
    # @args: brief - build_brief's dict, lang - override the language,
    #        deep - True for the long report: keep the "deep" facts too
    #        (the short post skips them to save tokens)
    # @return: the text
    lang = lang or brief.get("language") or "es"
    o = brief.get("object") or {}
    L = []
    head = o.get("name") or "?"
    if o.get("kind_label"):
        head += f" ({o['kind_label']})"
    L.append(head)

    facts = brief.get("object_facts") or []
    if facts:
        L.append("")
        L.append("WHAT WE KNOW (each figure with its meaning):")
        for f in facts:
            if f.get("level") == "deep" and not deep:
                continue
            L.append(f"- {f['label']}: {f['value']}")
            if f.get("why"):
                L.append(f"  {f['why']}")

    night = brief.get("night") or {}
    if night:
        L.append("")
        L.append("THE NIGHT (the plan):")
        if night.get("window"):
            L.append(f"- Safe window: {night['window']}")
        if night.get("best_time"):
            L.append(f"- Best time: {night['best_time']}")
        if night.get("hours_up") is not None:
            L.append("- Hours above the minimum altitude: "
                     f"{night['hours_up']}")
        if night.get("max_alt") is not None:
            L.append(f"- Maximum altitude: {night['max_alt']} deg")
            if night.get("max_alt_why"):
                L.append(f"  {night['max_alt_why']}")

    obs = brief.get("observations") or {}
    if obs:
        L.append("")
        L.append("OUR OBSERVATIONS:")
        if obs.get("sessions"):
            dates = ", ".join(s.get("date") or "?" for s in obs["sessions"])
            L.append(f"- Visits ({len(obs['sessions'])}): {dates}")
        if obs.get("n_points"):
            line = (f"- {obs['n_points']} points over {obs['n_nights']} "
                    f"nights, filters: {', '.join(obs.get('filters') or [])}")
            if obs.get("mag_min") is not None:
                line += (f", magnitude range {obs['mag_min']:.2f} to "
                         f"{obs['mag_max']:.2f}")
            L.append(line)
        c = obs.get("campaign") or {}
        if c.get("points"):
            bits = []
            if c.get("slope_mag_per_day") is not None:
                bits.append(f"{c['slope_mag_per_day']:+.3f} mag/day")
            if c.get("delta_from_peak") is not None:
                bits.append(f"{c['delta_from_peak']:+.2f} mag from peak")
            if c.get("verdict"):
                bits.append(f"verdict: {c['verdict']}")
            L.append("- Campaign: " + ", ".join(bits))
        lt = obs.get("latest")
        if lt and lt.get("mag") is not None:
            err = f" ± {lt['err']:.3f}" if lt.get("err") is not None else ""
            L.append(f"- Latest: {lt['date']} {lt['filter']} "
                     f"mag {lt['mag']:.2f}{err}")

    an = brief.get("analysis") or {}
    if an:
        L.append("")
        L.append("THE ANALYSIS:")
        per = an.get("period") or {}
        if per:
            bits = [f"{per['days']:.4g} days"]
            if per.get("method"):
                bits.append(f"method {per['method']}")
            if per.get("cycles") is not None:
                bits.append(f"{per['cycles']} cycles")
            if per.get("fap") is not None:
                bits.append(f"false-alarm probability {per['fap']:.3g}")
            L.append("- Period: " + ", ".join(bits))
            if per.get("why"):
                L.append(f"  {per['why']}")
        tr = an.get("transit") or {}
        if tr:
            bits = []
            if tr.get("depth_mmag") is not None:
                bits.append(f"depth {tr['depth_mmag']:.1f} mmag")
            if tr.get("duration_min") is not None:
                bits.append(f"duration {tr['duration_min']:.0f} min")
            if bits:
                L.append("- Transit: " + ", ".join(bits))
            if tr.get("why"):
                L.append(f"  {tr['why']}")
        for run in an.get("astrometry") or []:
            line = (f"- Astrometry {run.get('date') or '?'}: "
                    f"{run.get('n_obs')} observation(s)")
            if run.get("method"):
                line += f", method {run['method']}"
            if run.get("rate_arcsec_min") is not None:
                line += f", rate {run['rate_arcsec_min']} arcsec/min"
            if run.get("detected") is not None:
                line += ", detected" if run["detected"] else ", not detected"
            L.append(line)
            for p in run.get("points") or []:
                piece = f"    {p.get('ra')} {p.get('dec')}"
                if p.get("rms_ra") is not None or p.get("rms_dec") is not None:
                    piece += (f" ± {p.get('rms_ra')}/{p.get('rms_dec')} "
                              "arcsec")
                if p.get("mag") is not None:
                    piece += f", mag {p['mag']:.2f}"
                if p.get("snr") is not None:
                    piece += f", SNR {p['snr']:.0f}"
                L.append(piece)
        ph = an.get("photometry") or {}
        if ph:
            bits = []
            if ph.get("band"):
                bits.append(f"band {ph['band']}")
            if ph.get("n_points"):
                bits.append(f"{ph['n_points']} points")
            for k in sorted(ph.get("recipe") or {}):
                bits.append(f"{k}={ph['recipe'][k]}")
            if bits:
                L.append("- Photometry recipe: " + ", ".join(bits))

    camp = brief.get("campaign") or {}
    if camp:
        L.append("")
        L.append("CAMPAIGN:")
        who = camp.get("name") or "?"
        if camp.get("coordinator"):
            who += f" (coordinator {camp['coordinator']})"
        L.append(f"- {who}")
        if camp.get("goal"):
            L.append(f"  {camp['goal']}")
        prot = camp.get("protocol") or {}
        if prot:
            L.append("- Protocol: " + ", ".join(
                f"{k}={prot[k]}" for k in sorted(prot)))

    gal = brief.get("gallery") or []
    if gal:
        L.append("")
        L.append("IMAGES WE MADE (reference them by their EXACT file name, "
                 "in the section where they belong):")
        for g in gal:
            cap = _pick(g.get("caption") or {}, lang)
            L.append(f"- {g['name']} ({g.get('key')}): {cap}")

    assets = brief.get("assets") or []
    if assets:
        L.append("")
        L.append("ASSETS (files we made):")
        for a in assets:
            L.append(f"- {a['kind']}: {a['name']}")

    obsr = brief.get("observatory") or {}
    if obsr.get("name") or obsr.get("mpc"):
        L.append("")
        who = obsr.get("name") or "our observatory"
        if obsr.get("mpc"):
            who += f" (MPC {obsr['mpc']})"
        L.append(f"OBSERVATORY: {who}")
    return "\n".join(L)
