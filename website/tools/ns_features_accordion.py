############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Features accordion module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################
"""Deterministic features accordion (ADR-038).

Turns the 2-column features masonry into a single column of native
<details>/<summary> rows (accordion): every row closed on load, several
may open at once, even rows shift right (zigzag) with a fluid margin.

The walker is anchored on `id="feat-N"` (12 unique ids — the same anchor
as the injector), NOT on a raw `<div` scan (which can mis-tokenize
`<div`, `<divider`, `<details`, etc.).

Idempotent + self-validating: aborts (and touches NOTHING) unless every
check passes; writes only then.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
INDEX = ROOT / "website" / "index.html"
CSS = ROOT / "website" / "css" / "style.css"

CSS_MARK = "/* ==== ADR-038 features accordion (detail rows) ==== */"

ZIGZAG_CSS = """

/* ==== ADR-038 features accordion (detail rows) ==== */
/* Single column list; even rows shift right (zigzag), fluid 24px..96px. */
.feature-list {
  display: flex;
  flex-direction: column;
  gap: var(--section-gap);
  max-width: min(960px, 100%);
  margin-inline: auto;
}

.feature-row {
  border-radius: var(--radius);
}
.feature-row:nth-child(even) {
  margin-left: clamp(24px, 6vw, 96px);
}

/* Summary header: caret is CSS ::after (no i18n text, no new strings). */
.feature-summary {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 20px 24px;
  cursor: pointer;
  list-style: none;                 /* hide the native triangle */
  appearance: none;
  background: linear-gradient(180deg, rgba(25, 23, 28, 0.55) 0%, rgba(13, 12, 16, 0.55) 100%);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  transition: border-color 0.35s var(--ease), background 0.35s var(--ease);
}
.feature-summary::-webkit-details-marker { display: none; }
.feature-summary:hover {
  border-color: var(--line-bright);
  background: linear-gradient(180deg, rgba(25, 23, 28, 0.72) 0%, rgba(13, 12, 16, 0.72) 100%);
}
.feature-row[open] .feature-summary {
  border-color: var(--terracotta);
}

/* CSS caret — pure styling, i18n untouched. */
.feature-summary::after {
  content: "\u25B8";                 /* ▸  (CSS, not i18n text) */
  margin-left: auto;
  color: var(--terracotta);
  font-size: 0.8rem;
  transition: transform 0.3s var(--ease);
}
.feature-row[open] .feature-summary::after {
  transform: rotate(90deg);
}
"""


def error(msg):
    print(f"[accordion] ERROR: {msg}")
    return False


def balanced_div(html, open_idx):
    """# @args: html=str, open_idx=int index of a '<div' token
       # @return: (start, end_after) of that balanced <div>...</div>, or None.
       # Token-scan using the stdlib-safe probe (no stray <divider)."""
    i = open_idx
    depth = 0
    while True:
        o = html.find("<div", i)
        c = html.find("</div>", i)
        if o == -1 and c == -1:
            return None
        if c == -1 or (o != -1 and o < c):
            # advance past this <div ...> open tag
            gt = html.find(">", o)
            if gt == -1:
                return None
            depth += 1
            i = gt + 1
        else:
            depth -= 1
            if depth == 0:
                return open_idx, c + len("</div>")
            i = c + len("</div>")


def find_block(html, start):
    """# @args: html=str, start=int scan origin
       # @return: (n, b0, b1) for the NEXT <div ... id="feat-N" ...> block,
       #   or None. Anchored on the unique id, then balanced back to the
       #   enclosing <div> (open token that contains the id)."""
    m = re.search(r'\bid="feat-(\d+)"', html[start:])
    if not m:
        return None
    n = m.group(1)
    ref = start + m.start()
    # The enclosing <div ...> whose '>' comes AFTER ref.
    d0 = html.rfind("<div", 0, ref + 1)
    while d0 != -1:
        gt = html.find(">", d0)
        if gt > ref:               # this div's open tag covers the id
            break
        d0 = html.rfind("<div", 0, d0)
    else:
        return None
    if d0 == -1:
        return None
    span = balanced_div(html, d0)
    if not span:
        return None
    return n, d0, span[1]


def main():
    if not INDEX.exists():
        return error(f"{INDEX} no existe")
    html = INDEX.read_text(encoding="utf-8")

    # Idempotent: already applied?
    if '<div class="feature-list"' in html:
        print("[accordion] ya aplicado (feature-list presente) -> no-op exit 0")
        return True

    # Region: balance the features-masonry container (deterministic).
    mbox = re.search(r'<div [^>]*class="[^"]*features-masonry[^"]*"', html)
    if not mbox:
        return error("no se encuentra .features-masonry")
    region = balanced_div(html, mbox.start())
    if not region:
        return error("features-masonry no balanceado")
    (region_start, region_end) = region

    # Walk the 12 blocks anchored by unique ids, inside the region.
    blocks = []
    cursor = mbox.end()
    while True:
        hit = find_block(html, cursor)
        if not hit or not (region_start <= hit[1] and hit[2] <= region_end):
            break
        blocks.append(hit)
        cursor = hit[2]
    if len(blocks) != 12:
        return error(f"esperaba 12 feature-block, hay {len(blocks)}")

    # Build the accordion rows; the block keeps its inner id-free content.
    rows = []
    seen = set()
    for (n, b0, b1) in blocks:
        if n in seen:
            return error(f"id feat-{n} duplicado")
        seen.add(n)
        seg = html[b0:b1]
        # Number caption inside the block (reuse, no new i18n).
        mnum = re.search(r'<span class="feature-number[^"]*">\s*([^<]+?)\s*</span>', seg)
        num = mnum.group(1).strip() if mnum else f"FEAT-{n}".upper()
        seg = re.sub(r'\s+\bid="feat-\d+"', "", seg, count=1)
        rows.append(
            "\n"
            f'<details class="feature-row" id="feat-{n}">\n'
            f'  <summary class="feature-summary">\n'
            f'    <span class="feature-number mono">{num}</span>\n'
            f'    <h3 class="feature-title" data-i18n="feat.{n}.title"></h3>\n'
            "  </summary>\n"
            f"{seg}\n"
            "</details>"
        )

    new_region = "\n  <div class=\"feature-list\">\n" + "\n".join(rows) + "\n  </div>\n"
    new_html = html[:region_start] + new_region + html[region_end:]

    # ---------------- Validate before writing ----------------
    import re as _re

    def hx(txt, pat):
        return len(_re.findall(pat, txt))

    checks = {
        "feature-row details (12)": hx(new_html, r'<details class="feature-row"') == 12,
        "feature-summary (12)": hx(new_html, r'<summary class="feature-summary"') == 12,
        "imgs feature-screenshot (13)": hx(new_html, r'<img [^>]*feature-screenshot') == 13,
        "imgs width+height (13)": hx(
            new_html, r'<img [^>]*feature-screenshot[^>]*width="\d+"[^>]*height="\d+"') == 13,
        "wireframe 0": hx(new_html, r'field-ring|class="fw-|class="fv-cross') == 0,
        "balance 0": new_html.count("<div") - new_html.count("</div>") == 0,
        "sin features-masonry": "features-masonry" not in new_html,
        "sin feature-col en la sección": "feature-col" not in new_html,
        "ids feat-1..12 (12)": hx(new_html, r'id="feat-(\d+)"') == 12,
        "i18n feat.N.title (24: 12 en summary + 12 bloques)": hx(
            new_html, r'data-i18n="feat\.\d+\.title"') == 24,
    }
    bad = [k for k, v in checks.items() if not v]
    if bad:
        print("[accordion] validación FALLÓ — no se escribe nada:")
        for k in bad:
            print(f"   - {k}")
        return False

    css = CSS.read_text(encoding="utf-8")
    if CSS_MARK not in css:
        css = css.rstrip() + "\n" + ZIGZAG_CSS.rstrip() + "\n"

    INDEX.write_text(new_html, encoding="utf-8")
    CSS.write_text(css, encoding="utf-8")
    print("[accordion] OK — index.html + css/style.css actualizados (ADR-038)")
    for k in checks:
        print(f"   + {k}: OK")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
