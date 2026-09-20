############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Swap dump module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################
"""ns_dump_swap.py — Ejecuta swap_vignette REAL de disco sobre hero y feat-1
en memoria, y vuelca a /tmp/ns_dump_block.txt el fragmento del bloque feature
resultante (desde `<div class="feature-block"` hasta la apertura de
`feature-text`), SIN anclas de disco por ahora.

# @args:  (ninguno)
# @return: 0 si el dump se escribió; 1 si algo falló
"""
from __future__ import annotations

import sys
import re
from pathlib import Path

INDEX = Path("/mnt/nvme1n1p5/Develop/astronomy/nightscribe/website/index.html")
DUMP = Path("/tmp/ns_dump_block.txt")

import ns_inject_screens as ns


def main() -> int:
    html = INDEX.read_text(encoding="utf-8")
    html = ns.swap_vignette(html, 'id="hero"', "hero.png",
                            "NightScribe — ventana principal (Tonight)", lazy=False)
    html = ns.swap_vignette(html, 'id="feat-1"', "feat-1.png",
                            "NightScribe — Tonight: tarjetas de puntuación", lazy=True)

    i = html.find('<div class="feature-block" id="feat-1"')
    i_end = html.find('<div class="feature-text"', i)
    frag = html[i:i_end]
    w, c = len(re.findall(r"<div\b", frag)), len(re.findall(r"</div\b", frag))
    print(f"[dump] feat-1 fragmento {len(frag)} B, <div:{w} </div:{c} balance={c-w}")
    DUMP.write_text(frag, encoding="utf-8")
    print("[dump] escrito /tmp/ns_dump_block.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
