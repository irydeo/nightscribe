############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Social media post builder
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################

import datetime
import logging
import re
from pathlib import Path

from . import narrative

logger = logging.getLogger(__name__)


def render_post(e, cfg):
    # @args: e - dict from enrich.enrich(), cfg - Config
    # @return: {"es": md, "en": md, "tweet": str}
    obs = cfg.get("observatory_name", "our observatory")
    mpc = cfg.get("mpc_code", "")
    h = narrative.hook(e)
    facts = narrative.fact_bullets(e)
    tags = narrative.hashtags(e.get("type")) + f" #MPC{mpc}" if mpc else ""
    name = e.get("name", "")

    es = [h["es"], ""]
    es.append(f"Anoche, desde {obs} (MPC {mpc}), observamos *{name}*."
              if mpc else f"Anoche observamos *{name}*.")
    if facts:
        es.append("")
        es += [f"• {b['es']}" for b in facts]
    es += ["", "📡 Síguenos para más astronomía con datos reales.", "", tags]

    en = [h["en"], ""]
    en.append(f"Last night, from {obs} (MPC {mpc}), we observed *{name}*."
              if mpc else f"Last night we observed *{name}*.")
    if facts:
        en.append("")
        en += [f"• {b['en']}" for b in facts]
    en += ["", "📡 Follow us for more real-data astronomy.", "", tags]

    return {"es": "\n".join(es), "en": "\n".join(en),
            "tweet": _tweet(e, cfg)}


def _tweet(e, cfg):
    # 280-character version: hook + one fact (not repeating the hook) + hashtags.
    # @args: e - enriched dict, cfg - Config
    # @return: tweet text (<= 280 chars)
    h = narrative.hook(e)["en"]
    facts = narrative.fact_bullets(e)
    mpc = cfg.get("mpc_code", "")
    tag = f"#astronomy #MPC{mpc}" if mpc else "#astronomy"
    extra = next((f["en"] for f in facts if f["en"] != h), None)
    text = h + (f" {extra}" if extra else "")
    text += f"\n\n{tag}"
    if len(text) > 280:
        text = text[:277] + "..."
    return text


def suggest_caption(e):
    # Short Instagram caption (ES first line, EN after).
    # @args: e - enriched dict
    # @return: caption text
    h = narrative.hook(e)
    tags = narrative.hashtags(e.get("type"))
    return f"{h['es']}\n\n{h['en']}\n\n{tags}"


# chart labels per language: alt text and section headers
CHART_LABELS = {
    "orbit":    {"alt_es": "Órbita de %s", "alt_en": "Orbit of %s",
                 "es": "Órbita", "en": "Orbit"},
    "sky":      {"alt_es": "Posición celestial y tiempo óptimo",
                 "alt_en": "Sky position and best time to observe",
                 "es": "Posición en el cielo", "en": "Position on the sky"},
    "field":    {"alt_es": "Campo estelar alrededor de %s",
                 "alt_en": "Star field around %s",
                 "es": "Campo estelar", "en": "Star field"},
    "transit":  {"alt_es": "Curva de luz del tránsito de %s",
                  "alt_en": "Light curve of the %s transit",
                  "es": "Curva de luz", "en": "Light curve"},
    "lightcurve": {"alt_es": "Curva de luz de %s",
                 "alt_en": "Light curve of %s",
                 "es": "Curva de luz", "en": "Light curve"},
    "sun":      {"alt_es": "Estado del Sol: imagen SDO y regiones activas",
                 "alt_en": "Sun state: SDO image and active regions",
                 "es": "Estado del Sol", "en": "Sun state"},
}

# extra (non-chart) resources: GIF/MP4/PNG from the blink pipeline, etc.
# shown in their own markdown section after the charts
MEDIA = {
    "gif":  {"alt_es": "Blink de %s", "alt_en": "Blink of %s",
             "es": "Blink", "en": "Blink"},
    "mp4":  {"alt_es": "Vídeo blink de %s", "alt_en": "Blink video of %s",
             "es": "Vídeo blink", "en": "Blink video"},
    "pair": {"alt_es": "Antes/después de %s",
              "alt_en": "Before/after of %s",
              "es": "Antes/después", "en": "Before/after"},
    "evo_gif":  {"alt_es": "Animación de la evolución de %s",
                 "alt_en": "Evolution animation of %s",
                 "es": "Animación", "en": "Evolution"},
    "evo_mp4":  {"alt_es": "Vídeo de la evolución de %s",
                 "alt_en": "Evolution video of %s",
                 "es": "Vídeo evolución", "en": "Evolution video"},
}


def chart_section(post, charts, lang):
    # Builds the markdown block listing every chart with a relative
    # image reference, so the post is ready to publish on a web page.
    # @args: post - dict from render_post(), charts - {key: path or str},
    #        lang - "es" or "en"
    # @return: list of markdown lines (empty when charts is empty)
    if not charts:
        return []
    name = post.get("_object_name") or ""
    head = ["", "## Galería" if lang == "es" else "## Gallery", ""]
    for key, p in charts.items():
        lbl = CHART_LABELS.get(key)
        if not lbl:
            continue
        alt = lbl[f"alt_{lang}"].replace("%s", name) if name else lbl[lang]
        head.append(f"![{alt}]({Path(p).name})")
        head.append("")
    return head


def media_section(post, resources, lang):
    # Builds the markdown block for the extra resources (blink GIF/MP4,
    # before/after PNG…) that are not drawn by the chart builder.
    # @args: post - dict from render_post(), resources - {key: path or str},
    #        lang - "es" or "en"
    # @return: list of markdown lines (empty when there is nothing to show)
    if not resources:
        return []
    name = post.get("_object_name") or ""
    head = ["", "## Recursos" if lang == "es" else "## Resources", ""]
    for key, p in resources.items():
        lbl = MEDIA.get(key)
        if not lbl:
            continue
        alt = lbl[f"alt_{lang}"].replace("%s", name) if name else lbl[lang]
        head.append(f"![{alt}]({Path(p).name})")
        head.append("")
    return head


def attach_charts(post, charts, resources=None):
    # Appends the chart and the extra-resource blocks to the ES and EN
    # texts (replacing old ones if present), right before the closing lines.
    # @args: post - dict from render_post(), charts - {key: path or str},
    #        resources - {key: path or str} for blink/extra files, or None
    # @return: the same post dict, texts updated
    if not charts and not resources:
        return post
    for lang in ("es", "en"):
        text = post[lang]
        cut = text.find("\n\n## ")
        if cut != -1:
            text = text[:cut]
        post[lang] = "\n".join([text,
                                *chart_section(post, charts, lang),
                                *media_section(post, resources, lang)])
    return post


def build_charts(e, outdir, safe, cfg=None, fmt="instagram", size=None,
                 lang=None):
    # Renders the object's charts into outdir (one PNG each). The prefix
    # must end in "_" so the file name reads e.g. "4443_Atlas_orbit.png".
    # @args: e - enriched dict, outdir - Path, safe - file name prefix,
    #        cfg - Config (horizon settings) or None,
    #        fmt - size preset of style.SIZES ("instagram" for posts,
    #              "panel" for the in-GUI overview),
    #        size - (w, h) px override of the preset (panel re-render mode),
    #        lang - "es"|"en" for the chart strings; defaults to the
    #               configured UI language via cfg.ui_language()
    # @return: dict {chart_key: Path} of the charts actually produced
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from . import coords
    from ..viz import orbit_view, sky_view, sn_view
    outdir = Path(outdir)  # callers may pass a str (panel chart_dir, CLI)
    if lang is None:
        lang = cfg.ui_language() if (cfg and hasattr(cfg, "ui_language")) \
               else "es"
    d = e.get("data") or {}
    jd = coords.jd_from_datetime(
        datetime.datetime.now(datetime.timezone.utc))
    sb = d.get("sbdb")
    els = sb.get("elements") if sb else None
    unc = d.get("unconfirmed")
    # exoplanet transit event: resolved once, used by both the sky chart
    # (to shade ingress/egress) and the transit light-curve slot.
    tr = d.get("transit") or (unc or {}).get("transit")
    charts = {}
    # orbit chart: bound (e<1) and parabolic (e=1) orbits
    if els and els.get("q") and els.get("e", 1) <= 1.0:
        p = outdir / f"{safe}orbit.png"
        orbit_view.draw_orbit(dict(els), jd=jd,
                              obj_name=e["name"],
                              approach=d.get("next_approach"), out=str(p),
                              fmt=fmt, size=size, lang=lang)
        charts["orbit"] = p
    # sky position: ephemeris, then SIMBAD, then the unconfirmed dict
    ra_deg = dec_deg = None
    eph = d.get("ephem")
    if eph:
        try:
            ra_deg = coords.ra_hms_to_deg(eph["ra"])
            dec_deg = coords.dec_dms_to_deg(eph["dec"])
        except (ValueError, AttributeError):
            pass
    sim = d.get("simbad")
    if sim and ra_deg is None:
        try:
            ra_deg = coords.ra_hms_to_deg(sim.get("ra", ""))
            dec_deg = coords.dec_dms_to_deg(sim.get("dec", ""))
        except (ValueError, AttributeError):
            pass
    if ra_deg is None and unc and unc.get("ra_deg") is not None:
        ra_deg = float(unc["ra_deg"])
        dec_deg = float(unc.get("dec_deg", 0.0))
    if ra_deg is None and d.get("ra_deg") is not None:
        # ADR-027: a degraded transient (SIMBAD does not know it) still has
        # the planner's coordinates — enough for the sky chart
        ra_deg = float(d["ra_deg"])
        dec_deg = float(d.get("dec_deg") or 0.0)
    if ra_deg is None and d.get("ra") is not None:
        # Exoplanet Archive (and the ExoClock planner target) hand us
        # `ra`/`dec` as plain floats (degrees) — no `ra_deg` twin. A string
        # slips in the same try as above, so a non-numeric value just
        # skips the sky slot without crashing the whole chart build.
        try:
            ra_deg = float(d["ra"])
            dec_deg = float(d.get("dec") or 0.0)
        except (TypeError, ValueError):
            pass
    if ra_deg is not None:
        p = outdir / f"{safe}sky.png"
        hor = None
        if cfg:
            from . import horizon as _horizon
            hor = _horizon.from_config(cfg)
        # safe span from the planner target (data dict, or the unconfirmed
        # fallback for objects SBDB does not know); None when not planned
        src = d if d.get("safe_window") else (unc or {})
        sw = best = None
        raw = src.get("safe_window")
        if raw:
            s0, s1 = raw.split("|")
            sw = (datetime.datetime.fromisoformat(s0),
                  datetime.datetime.fromisoformat(s1))
        raw = src.get("best_time")
        if raw:
            best = datetime.datetime.fromisoformat(raw)
        try:
            sky_view.draw_sky(ra_deg, dec_deg,
                              cfg.get("lat") if cfg else None,
                              cfg.get("lon") if cfg else None,
                               obj_name=e["name"], out=str(p), fmt=fmt,
                               horizon=hor.alt_at if hor else None,
                               margin=float(cfg.get("horizon_margin_deg", 0))
                                if cfg else 0.0, safe_window=sw,
                               best_time=best, size=size, lang=lang,
                               transit=tr
                                if e.get("type") in ("transit", "exoplanet")
                                else None)
        except Exception:
            # no site/lat-lon to plot from: omit the slot rather than fail
            logger.exception("sky chart skipped for %s", e["name"])
        else:
            charts["sky"] = p
    if sim and ra_deg is not None:
        from .sources import cutouts
        img = cutouts.reference_cutout(ra_deg, dec_deg)
        if img:
            p = outdir / f"{safe}field.png"
            sn_view.draw_sn_field(img, sn_name=e["name"], out=str(p),
                                  fmt=fmt, size=size, lang=lang)
            charts["field"] = p
    # exoplanet transit: light curve of the event (planner target's dict;
    # `tr` was resolved once above, shared with the sky chart)
    if tr and tr.get("mid") and e.get("type") in ("transit", "exoplanet"):
        from ..viz import transit_view
        p = outdir / f"{safe}transit.png"
        transit_view.draw_transit(tr, out=str(p), fmt=fmt, size=size,
                                  lang=lang)
        charts["transit"] = p
    # B9: SN follow-up light curve; ADR-034 (D.5): a HADS with photometry
    # gets its curve folded by the catalog period + the schematic sawtooth
    fu = d.get("followup") or {}
    fu_points = fu.get("points") or []
    if fu_points and e.get("type") in ("transient", "sn", "hads",
                                       "variable"):
        from ..viz import lightcurve_view
        p = outdir / f"{safe}lightcurve.png"
        try:
            kw = {}
            if e.get("type") == "hads":
                from . import hads as hads_mod
                h = d.get("hads") or {}
                if h.get("period_h"):
                    kw["fold_period_d"] = h["period_h"] / 24.0
                    amp = h.get("amp")
                    if amp is None and h.get("max") is not None \
                            and h.get("min") is not None:
                        amp = h["min"] - h["max"]
                    if amp and h.get("max") is not None:
                        kw["schematic"] = hads_mod.sawtooth_template(
                            h["period_h"], amp, (h["max"] + h["min"]) / 2)
            if e.get("type") == "variable":
                v = d.get("variable") or {}
                if v.get("period_d"):
                    kw["fold_period_d"] = v["period_d"]
                    if v.get("epoch_mjd") is not None:
                        kw["epoch_mjd"] = v["epoch_mjd"]
                    amp = v.get("amp")
                    if amp is None and v.get("max") is not None \
                            and v.get("min") is not None:
                        amp = v["min"] - v["max"]     # inverted axis
                    if amp and v.get("max") is not None:
                        from . import hads as hads_mod
                        kw["schematic"] = hads_mod.sawtooth_template(
                            v["period_d"] * 24.0, amp,
                            (v["max"] + v["min"]) / 2)
            lightcurve_view.draw_lightcurve(
                fu_points, out=str(p), fmt=fmt, size=size, lang=lang,
                sn_type=(d.get("simbad") or {}).get("otype"),
                peak_mjd=fu.get("peak_mjd"), peak_mag=fu.get("peak_mag"),
                **kw)
            charts["lightcurve"] = p
        except Exception:
            logger.exception("light curve skipped for %s", e["name"])
    plt.close("all")
    return charts


def save_outputs(post, outdir, base_name, e=None, charts=None, cfg=None,
                 resources=None):
    # Writes the drafts to disk. Makes the ES/EN posts reference every
    # chart and extra resource with relative markdown links, so the files
    # can be published directly on a web page (images sit next to the md).
    # @args: post - dict from render_post(), outdir - Path, base_name - prefix
    #        e - enriched object dict or None, charts - {key: Path} or None
    #        cfg - Config (horizon settings) or None,
    #        resources - {key: Path} of extra files (blink gif/mp4, ...)
    # @return: dict of written Paths (es, en, tweet, plus chart_* / res_*)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.-]+", "_", base_name)
    written = {}

    # --- build the charts when the object is known and they were not made ---
    if e is not None and charts is None:
        charts = build_charts(e, outdir, safe + "_", cfg=cfg)

    # --- let the post reference its charts and resources (relative md links) ---
    if e:
        post["_object_name"] = e.get("name", "")
    if charts or resources:
        attach_charts(post, charts, resources)

    # --- write text drafts ---
    for key, fname in (("es", f"{safe}_ES.md"), ("en", f"{safe}_EN.md"),
                        ("tweet", f"{safe}_tweet.txt")):
        p = outdir / fname
        p.write_text(post[key], encoding="utf-8")
        written[key] = p

    if charts:
        for k, p in charts.items():
            written[f"chart_{k}"] = p
    if resources:
        for k, p in resources.items():
            written[f"res_{k}"] = p

    return written
