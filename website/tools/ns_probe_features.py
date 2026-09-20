#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NightScribe - probe module (transient)
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################
"""ns_probe_features — probe determinista de la sección features.

Usa html.parser (stdlib) para reportar la estructura REAL de disco:
offsets y líneas del masonry, sus columnas y los feature-block, más
counts de validación (imgs, width/height, wireframe, balance, i18n).
No toca disco: solo lee y reporta.
"""
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = ROOT / "website" / "index.html"


class Probe(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.masonry = None          # offset de apertura features-masonry
        self.masonry_line = None
        self.cols = []               # (class, offset)
        self.blocks = []             # (id, offset)
        self.section_start = None

    def handle_starttag(self, tag, attrs):
        off = self.getoffset()
        pos = self.getpos()
        cls = ""
        for k, v in attrs:
            if k == "class":
                cls = v or ""
            if k == "id" and tag == "section" and (v or "").startswith("features"):
                self.section_start = (off, pos)
        if tag == "div":
            if "features-masonry" in cls.split():
                self.masonry = off
                self.masonry_line = pos[0]
            if "features-masonry" not in cls.split() and any(
                c.startswith("feature-col") for c in cls.split()
            ):
                self.cols.append((cls, off))
            for c in cls.split():
                if c == "feature-block":
                    bid = None
                    for k, v in attrs:
                        if k == "id":
                            bid = v
                    self.blocks.append((bid, off))
                    break


def main():
    html = INDEX.read_text(encoding="utf-8")
    p = Probe()
    p.feed(html)
    p.close()

    opens = html.count("<div")
    closes = html.count("</div>")
    print(f"== masonry @offset {p.masonry} (línea {p.masonry_line})")
    print(f"feature-col      : {len(p.cols)}")
    for cls, off in p.cols:
        print(f"   - {cls} @{off}")
    print(f"feature-block    : {len(p.blocks)}")
    for bid, off in p.blocks:
        print(f"   - {bid} @{off}")
    print(f"balance div      : {opens} / {closes} -> delta {closes - opens}")
    print(f"imgs feature-screenshot: {html.count('feature-screenshot')}")
    wh = len(
        [
            m
            for m in __import__("re").finditer(
                r'<img[^>]*feature-screenshot[^>]*width="\d+"[^>]*height="\d+"', html
            )
        ]
    )
    print(f"imgs con wh real : {wh}")
    wire = len(
        __import__("re").findall(r'class="[^"]*(?:ff-ring|fw-[a-z]|[^"]*wireframe)[^"]*"', html)
    )
    print(f"wireframe        : {wire}")
    print(f"i18n data-i18n   : {html.count('data-i18n=')}")


if __name__ == "__main__":
    main()
