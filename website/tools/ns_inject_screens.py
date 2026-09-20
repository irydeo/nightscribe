############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - Screen injection module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################
"""ns_inject_screens.py — Inyecta las capturas reales (hero + feat-1..feat-12)
de `website/img/screens/` en `website/index.html`.

Reemplaza el `field-wrap` completo de cada bloque anclado (wireframe
decorativo `field-vignette` + `field-ring` + `fw-*`) por el mismo `field-wrap`
con un `<img class="feature-screenshot">` real dentro, conservando la
`field-caption` verbatim (i18n + patrón de reserva CLS intactos).

# Cómo lo hace (determinista, SIN escaneo balanceado de divs)
Cada `field-wrap` cierra con el `</div>` INMEDIATO después del `</span>` de su
`field-caption` (la caption es el último hijo del wrap). Por tanto:

    i_cap = html.find('<span class="field-caption mono">', i_wrap)
    cap_end = html.index('</span>', i_cap)
    i_close = html.index('</div>', cap_end + 7)   # cierre del field-wrap

Ese `[i_wrap : i_close+6]` es un elemento balanceado si el HTML fuente es
válido → lo verificamos ANTES de sustituir: `<div` == `</div` en el slice,
si no, aborto ruidoso sin tocar disco.

Autovalida el resultado GLOBAL antes de escribir (13 imgs, 13 con width+height,
0 wireframes sobrantes, balance `<div`/`</div` = 0). Si algo falla → aborto,
no se escribe nada.

Idempotente: si ya hay `feature-screenshot` en el HTML, no re-editás (exit 0).

# @args:  (ninguno)
# @return: 0 si OK; != 0 si falla (sin escribir nada)
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
INDEX = ROOT / "website" / "index.html"
CSS = ROOT / "website" / "css" / "style.css"
IMG_DIR = ROOT / "website" / "img" / "screens"

EXPECTED = 13  # hero + feat-1..feat-12

# anchor único del bloque, png en img/screens, alt en español, lazy bool.
# El hero es LCP → eager + fetchpriority=high (sin lazy).
BLOCKS = [
    ('id="hero"',   "hero.png",   "NightScribe — pestaña Tonight del observatorio", False),
    ('id="feat-1"', "feat-1.png", "NightScribe — pestaña Tonight: tarjetas de puntuación", True),
    ('id="feat-2"', "feat-2.png", "NightScribe — pestaña Projects", True),
    ('id="feat-3"', "feat-3.png", "NightScribe — vista orbital (SBDB)", True),
    ('id="feat-4"', "feat-4.png", "NightScribe — blink de supernova (PS1)", True),
    ('id="feat-5"', "feat-5.png", "NightScribe — ventana de tránsito de exoplaneta", True),
    ('id="feat-6"', "feat-6.png", "NightScribe — curva de luz de variable (VSX)", True),
    ('id="feat-7"', "feat-7.png", "NightScribe — borrador de post (ES+EN)", True),
    ('id="feat-8"', "feat-8.png", "NightScribe — flujo del proyecto", True),
    ('id="feat-9"', "feat-9.png", "NightScribe — panel de campañas", True),
    ('id="feat-10"', "feat-10.png", "NightScribe — panel solar", True),
    ('id="feat-11"', "feat-11.png", "NightScribe — observatorio, CCDciel (JSON-RPC)", True),
    ('id="feat-12"', "feat-12.png", "NightScribe — módulos de visualización", True),
]

CSS_RULE = (
    "\n"
    "/* ============================================================ */\n"
    "/* Capturas reales dentro del marco de campo (inyectadas)         */\n"
    "/* ============================================================ */\n"
    ".feature-screenshot {\n"
    "  display: block;\n"
    "  width: 100%;\n"
    "  max-width: 100%;\n"
    "  height: auto;\n"
    "  max-height: 100%;\n"
    "  object-fit: contain;\n"
    "  border: 1px solid var(--line);\n"
    "  border-radius: calc(var(--radius) * 0.55);\n"
    "  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);\n"
    "  background: var(--bg-panel);\n"
    "}\n"
)

_DIV = re.compile(r"</?div\b")


def png_size(path: Path) -> tuple[int, int]:
    """Lee (width, height) reales del PNG en la cabecera IHDR (stdlib).

    # @args: path al PNG
    # @return: (ancho, alto) en píxeles
    """
    with open(path, "rb") as fh:
        head = fh.read(26)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError(f"no es un PNG válido: {path.name}")
    return struct.unpack(">II", head[16:24])


def indent_of(html: str, pos: int) -> str:
    """Devuelve el whitespace de indentación de la línea que contiene `pos`.

    # @args: html; pos = índice dentro de la línea actual
    # @return: string de espacios previos al contenido en esa línea
    """
    nl = html.rfind("\n", 0, pos)
    return html[nl + 1 : pos] if nl != -1 else ""


def swap_wrap(html: str, anchor: str, png: str, alt: str, lazy: bool) -> str:
    """Sustituye el `field-wrap` completo del bloque anclado por un wrap real.

    Ancla el cierre en la caption (último hijo del wrap): `</span>` de la
    caption → `</div>` inmediato = cierre del wrap. Sin escaneo balanceado;
    el slice [i_wrap : i_close+6] debe estar balanceado (se verifica: si no,
    aborto sin escribir).

    # @args: html actual; anchor único del bloque; png en img/screens;
    #        alt en español; lazy (bool)
    # @return: html con el <img> inyectado (balance global intacto)
    """
    i_a = html.find(anchor)
    if i_a == -1:
        raise SystemExit(f"[swap] no se halló el ancla {anchor!r}")
    i_w = html.find('<div class="field-wrap">', i_a)
    if i_w == -1:
        raise SystemExit(f"[swap] sin field-wrap tras {anchor!r}")
    i_cap = html.find('<span class="field-caption mono">', i_w)
    if i_cap == -1:
        raise SystemExit(f"[swap] sin field-caption tras {anchor!r}")
    cap_end = html.index("</span>", i_cap)  # fin del span de la caption
    i_close = html.index("</div>", cap_end + 7)  # cierre del field-wrap

    old = html[i_w : i_close + 6]
    opened = len(_DIV.findall(old)) - len(re.findall(r"<div\b", old))  # placeholder
    # Conteo simple y explícito (verificable):
    opened = len(re.findall(r"<div\b", old))
    closed = len(re.findall(r"</div\b", old))
    if opened != closed:
        raise SystemExit(
            f"[swap] field-wrap desbalanceado tras {anchor!r} "
            f"(<div {opened} != </div {closed}) — aborto"
        )

    caption = html[i_cap : cap_end + 7]  # span verbatim (i18n intacta)
    w, h = png_size(IMG_DIR / png)
    lazy_attr = ' loading="lazy"' if lazy else ' fetchpriority="high"'
    img = (
        f'<img class="feature-screenshot" src="img/screens/{png}" '
        f'width="{w}" height="{h}" alt="{alt}"{lazy_attr}>'
    )
    pad = indent_of(html, i_w)
    new = (
        f'<div class="field-wrap">\n'
        f"{pad}  {img}\n"
        f"{pad}  {caption}\n"
        f"{pad}</div>"
    )
    return html[:i_w] + new + html[i_close + 6 :]


def add_css_rule(css: str) -> str:
    """Añade la regla `.feature-screenshot` a style.css (idempotente).

    # @args: css actual
    # @return: css con la regla al final (sin duplicar)
    """
    if ".feature-screenshot {" in css:
        return css
    return css.rstrip() + "\n" + CSS_RULE


def main() -> int:
    html = INDEX.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")

    if "feature-screenshot" in html:
        print("[inject] ya inyectado (idempotente) — sin cambios")
        return 0

    for anchor, png, alt, lazy in BLOCKS:
        html = swap_wrap(html, anchor, png, alt, lazy)

    # ---- Autovalidación global ANTES de escribir ----
    n_img = len(re.findall(r'<img class="feature-screenshot"', html))
    n_wh = len(
        re.findall(
            r'<img class="feature-screenshot"[^>]*width="\d+"[^>]*height="\d+"',
            html,
        )
    )
    n_wire = len(re.findall(r'class="field-ring"', html)) + len(
        re.findall(r'class="fw-', html)
    )
    opened = len(re.findall(r"<div\b", html))
    closed = len(re.findall(r"</div\b", html))
    balance = closed - opened

    print(f"[inject] imgs      : {n_img}/{EXPECTED}")
    print(f"[inject] con wh    : {n_wh}/{EXPECTED}")
    print(f"[inject] wireframe : {n_wire} (esperado 0)")
    print(f"[inject] balance   : {balance} (esperado 0)")

    if all((n_img == EXPECTED, n_wh == EXPECTED, n_wire == 0, balance == 0)):
        INDEX.write_text(html, encoding="utf-8")
        CSS.write_text(add_css_rule(css), encoding="utf-8")
        print("[inject] OK — index.html + css/style.css actualizados")
        return 0

    print("[inject] FALLO de validación — no se escribe nada", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
