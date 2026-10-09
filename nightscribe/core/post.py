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


def _strip_previous_gallery(text, lang):
    # Removes a gallery this module appended BEFORE, identified by its own
    # exact headings (Galería/Gallery, Recursos/Resources), so a second call
    # replaces it instead of duplicating it.
    #
    # Why not cut at the first "##" like before: the LONG REPORT is an
    # article with its own "##" section headings (the prompt asks for them).
    # Cutting at the first "##" threw the whole body away and left only the
    # title plus the gallery (the defect the observer saw: the report looked
    # like a title, "the short report in the long slot"). The report's own
    # headings must survive; only our gallery is stripped.
    # @args: text - the post/report text, lang - "es"|"en"
    # @return: the text without a previously appended gallery
    for head in (f"\n\n## {'Galería' if lang == 'es' else 'Gallery'}",
                 f"\n\n## {'Recursos' if lang == 'es' else 'Resources'}"):
        cut = text.find(head)
        if cut != -1:
            return text[:cut]
    return text


def attach_charts(post, charts, resources=None):
    # Appends the chart and the extra-resource blocks to the ES and EN
    # texts (replacing old ones if present), right before the closing lines.
    # The long report's texts (report_es / report_en) get the same gallery:
    # the model cites the images inside the article, and this block is the
    # complete gallery at the end.
    # @args: post - dict from render_post() (or the report), charts -
    #        {key: path or str}, resources - {key: path or str} or None
    # @return: the same post dict, texts updated
    if not charts and not resources:
        return post
    for key in ("es", "en", "report_es", "report_en"):
        text = post.get(key)
        if not text:
            continue
        lang = "en" if key.endswith("en") else "es"
        text = _strip_previous_gallery(text, lang)
        post[key] = "\n".join([text,
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
        img, _src = cutouts.reference_cutout(ra_deg, dec_deg)
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
    # B9: SN follow-up light curve; the fold/schematic/sn_type logic now
    # lives in core/lightcurve_data.py (one place, 2026-09-17) — including
    # the project's own sn_type taking priority over the catalog otype.
    if e.get("type") in ("transient", "sn", "hads", "variable"):
        from . import lightcurve_data
        payload = lightcurve_data.build_payload(
            d.get("followup"),
            sn_type_fallback=(d.get("simbad") or {}).get("otype"),
            hads=d.get("hads"), variable=d.get("variable"))
        if payload["points"]:
            from ..viz import lightcurve_view
            p = outdir / f"{safe}lightcurve.png"
            try:
                lightcurve_view.draw_lightcurve(
                    payload["points"], out=str(p), fmt=fmt, size=size,
                    lang=lang, sn_type=payload["sn_type"],
                    peak_mjd=payload["peak_mjd"],
                    peak_mag=payload["peak_mag"],
                    fold_period_d=payload.get("fold_period_d"),
                    epoch_mjd=payload.get("epoch_mjd"),
                    schematic=payload.get("schematic"))
                charts["lightcurve"] = p
            except Exception:
                logger.exception("light curve skipped for %s", e["name"])
    plt.close("all")
    return charts


def collect_assets(e, outdir, safe, cfg=None, charts=None):
    # Renders the object's charts (unless already given) and finds the extra
    # resources already in the folder (blink gif/mp4, before/after, the
    # evolution animations). One place for the template path and the AI
    # report, so the two can never disagree on which files exist.
    # @args: e - enriched dict, outdir - Path, safe - file name prefix
    #        WITHOUT the trailing "_", cfg - Config, charts - prebuilt dict
    # @return: (charts {key: Path}, resources {key: Path})
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    prefix = safe + "_"
    if charts is None:
        charts = build_charts(e, outdir, prefix, cfg=cfg)
    resources = {}
    try:
        for f in sorted(outdir.iterdir()):
            n = f.name.lower()
            if not n.startswith(prefix.lower()):
                continue
            # the _evo_ check comes FIRST: the evolution gif/mp4 also end in
            # ".gif"/".mp4", and the old order labelled them "Blink" (the
            # generic branch won). Fixed here while the scan moved in, so the
            # report shows the right caption.
            if n.endswith("_evo.gif"):
                resources.setdefault("evo_gif", f)
            elif n.endswith("_evo.mp4"):
                resources.setdefault("evo_mp4", f)
            elif n.endswith("_before_after.png"):
                resources.setdefault("pair", f)
            elif n.endswith(".gif"):
                resources.setdefault("gif", f)
            elif n.endswith(".mp4"):
                resources.setdefault("mp4", f)
    except OSError:
        pass
    return charts, resources


def gallery_entries(charts, resources, obj_name=""):
    # The images a report may reference, each with its EXACT file name and a
    # caption in both languages. The captions come from CHART_LABELS / MEDIA
    # (their single home), so a report and a gallery cannot name a file two
    # different ways.
    # @args: charts - {key: Path}, resources - {key: Path}, obj_name - object
    # @return: [{"key","name","caption": {"es","en"}}]
    out = []
    for source, labels in ((charts, CHART_LABELS), (resources, MEDIA)):
        for key, p in (source or {}).items():
            lbl = labels.get(key)
            if not lbl:
                continue
            caption = {}
            for lang in ("es", "en"):
                alt = lbl.get(f"alt_{lang}") or lbl.get(lang) or ""
                caption[lang] = alt.replace("%s", obj_name) if obj_name else alt
            out.append({"key": key, "name": Path(p).name, "caption": caption})
    return out


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
    drafts = [("es", f"{safe}_ES.md"), ("en", f"{safe}_EN.md"),
              ("tweet", f"{safe}_tweet.txt")]
    # the long report's own files, when the AI wrote one
    if post.get("report_es"):
        drafts.append(("report_es", f"{safe}_report_ES.md"))
    if post.get("report_en"):
        drafts.append(("report_en", f"{safe}_report_EN.md"))
    for key, fname in drafts:
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
