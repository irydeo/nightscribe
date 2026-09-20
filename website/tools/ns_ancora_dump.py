############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Ancora to dump module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################
"""ns_ancora_dump.py — Vuelca a /tmp el interior REAL de la field-wrap
de `hero` y `feat-1` del index.html en disco (puro, sin swap), entre
marcadores BEGIN/END, para examen directo.

# @args:  (ninguno)
# @return: 0 si se escribió el dump
"""
from __future__ import annotations

from pathlib import Path

INDEX = Path("website/index.html")


def anchor_block(html: str, anchor: str) -> str:
    """Extrae la field-wrap del bloque anclado, marcada con BEGIN/END.

    # @args: html; anchor único ('id="hero"' o 'id="feat-1"')
    # @return: texto del interior de la field-wrap, marcado
    """
    i_a = html.find(anchor)
    i_w = html.find('<div class="field-wrap">', i_a)
    i_open = html.index(">", i_w) + 1
    # cierre balanceado de la field-wrap
    depth, pos = 0, i_open
    while True:
        i_c = html.find("</div", pos)
        if i_c == -1:
            raise SystemExit(f"sin cierre para {anchor!r}")
        depth -= 1
        if depth == 0:
            return "BEGIN " + anchor + "\n" + html[i_open:i_c] + "\nEND " + anchor
        # buscar siguiente apertura
        nxt = html.find("<div", pos, i_c)
        while nxt != -1:
            depth += 1
            pos = nxt + 4
            nxt = html.find("<div", pos, i_c)
        pos = i_c + 4


def main() -> int:
    html = INDEX.read_text(encoding="utf-8")
    out = []
    for anchor in ('id="hero"', 'id="feat-1"'):
        out.append(anchor_block(html, anchor))
    Path("/tmp/ns_ancora_dump.txt").write_text("\n\n".join(out), encoding="utf-8")
    print("[dump] OK — /tmp/ns_ancora_dump.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
