#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NightScribe - feature accordion validator (probe)
# Python v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################
"""
NsFeaturesAccordionValidator - checks that website/index.html holds the
ADR-038 accordion state and that website/css/style.css has the zigzag rules.

Deterministic, reads only. Exit 0 = all pass, exit 1 = any fail.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
INDEX = ROOT / "website" / "index.html"
CSS = ROOT / "website" / "css" / "style.css"


def hx_count(text, pat):
    return len(re.findall(pat, text))


def error(msg):
    print(f"[feat-validator] ERROR: {msg}")
    return False


def main():
    if not INDEX.exists():
        return error(f"{INDEX} no existe")
    if not CSS.exists():
        return error(f"{CSS} no existe")
    html = INDEX.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    checks = {
        "features-masonry (0)": "features-masonry" not in html,
        "detail rows 12": hx_count(html, r'<details class="feature-row"') == 12,
        "summary rows 12": hx_count(html, r'<summary class="feature-summary"') == 12,
        "feature list container": hx_count(html, r'<div class="feature-list"') == 1,
        "feats 01..12 balance": hx_count(html, r'class="feature-number mono">(?:0\d|1[0-2])') == 12,
        "12 id feat-": hx_count(html, r'id="feat-\d+"') == 12,
        "13 captured": hx_count(html, r'<img[^>]*feature-screenshot') == 13,
        "13 with width/height": hx_count(html, r'<img[^>]*feature-screenshot[^>]*width="\d+"[^>]*height="\d+"') == 13,
        "wireframe 0": hx_count(html, r'field-ring|class="fw-|class="fv-cross') == 0,
        "wireframe-vignette 0": hx_count(html, r'class="feature-vignette|class="feature-scrim') == 0,
        "balance 0": html.count("<div") - html.count("</div>") == 0,
        "i18n 129": hx_count(html, r'data-i18n="') == 129,
        "accordion CSS marca": "/* ==== ADR-038 features accordion (detail rows) ==== */" in css,
        "zigzag CSS": hx_count(css, r'\.feature-list \.feature-row:nth-child\(even\)') >= 1,
        "summary caret CSS": "feature-summary::after" in css,
        "no .expanded CSS residual": "feature-block.expanded .feature-details" not in css,
    }
    bad = [k for k, v in checks.items() if not v]
    if bad:
        print("[feat-validator] FALLÓ — disco NO cumple ADR-038:")
        for k in bad:
            print(f"   - {k}: {checks[k]}")
        return False
    print("[feat-validator] OK — ADR-038 accordion completo y validado en disco.")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
