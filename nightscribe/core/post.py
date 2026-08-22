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

import logging
import re

from . import narrative

logger = logging.getLogger(__name__)

# Assembles bilingual post drafts + a 280-char tweet from enriched data.
# Templates follow estrategia.md; texts come from narrative.py.


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


def save_outputs(post, outdir, base_name):
    # Writes the drafts to disk.
    # @args: post - dict from render_post(), outdir - Path, base_name - prefix
    # @return: dict of written Paths
    from pathlib import Path
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.-]+", "_", base_name)
    written = {}
    for key, fname in (("es", f"{safe}_ES.md"), ("en", f"{safe}_EN.md"),
                       ("tweet", f"{safe}_tweet.txt")):
        p = outdir / fname
        p.write_text(post[key], encoding="utf-8")
        written[key] = p
    return written
