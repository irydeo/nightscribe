############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Screen injection probe module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################
"""ns_probe_swap.py — Probe REAL: ejecuta la función swap_vignette del
inyector en disco (ns_inject_screens) 13 veces sobre el index.html real
en memoria, y reporta tras cada swap el delta de `</div` para localizar
dónde se rompe el balance.

# No escribe nada — solo mide. La fuente de verdad es importar el módulo
# y llamar a la función REAL, no transcribir su lógica a mano.

# @args:  (ninguno)
# @return: 0 si el balance se mantiene 0 tras los 13 swaps; 1 si falla
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import ns_inject_screens as ns

INDEX = ns.INDEX


def deltas() -> int:
    html = INDEX.read_text(encoding="utf-8")
    before = len(re.findall(r"</div\b", html))
    base = before
    html = ns.swap_vignette(html, 'id="hero"', "hero.png",
                            "NightScribe — main window", lazy=False)
    after = len(re.findall(r"</div\b", html))
    print(f"[probe] hero      delta </div: {after - before}")
    before = after
    for n in range(1, 13):
        anchor = f'id="feat-{n}"'
        png = f"feat-{n}.png"
        alt = f"NightScribe — feature {n}"
        html = ns.swap_vignette(html, anchor, png, alt, lazy=True)
        after = len(re.findall(r"</div\b", html))
        print(f"[probe] feat-{n:<2d}   delta </div: {after - before}")
        before = after
    diff = after - base
    print(f"[probe] total delta </div: {diff} (esperado 0)")
    return 0 if diff == 0 else 1


def main() -> int:
    """# @args: (ninguno)
    # @return: código de salida
    """
    return deltas()


if __name__ == "__main__":
    sys.exit(main())
