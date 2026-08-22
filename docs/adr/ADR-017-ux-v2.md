# ADR-017: UX v2 — menu bar, "right now", dynamic columns, single-language UI

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: tras probar la v1, el usuario señaló problemas de integración y
usabilidad: dos idiomas mezclados en pantalla, explicaciones técnicas poco
intuitivas (MOID), gráficos 2D escondidos al final del texto, vista solar sin
contexto, sin barra de menú, sin distinción "qué puedo observar AHORA", y tabla
única para tipos de objeto muy distintos.

**Decisión**:
- **Un solo idioma en pantalla** (el configurado); solo los posts generados siguen
  siendo bilingües ES+EN (ese es su propósito).
- **Barra de menú**: File/View/Tools/Help; Configuración pasa de pestaña a diálogo
  modal (Tools → Settings…); idioma desde View.
- **"Right now"** dentro de Esta noche: objetivos sobre el horizonte *en este
  instante* (alt-az propio), refrescables.
- **Columnas dinámicas** en la tabla según el filtro de tipo (NEOs: NEOfixer, NObs,
  MOID; SNs: tipo, galaxia, descubrimiento; etc.) + panel de detalle del
  seleccionado.
- **Explora v2**: pestañas Parameters (básico / In depth) + Orbit + Sky tonight +
  Families + Field; explicaciones reescritas con metáforas (MOID como dos
  carreteras que se cruzan).
- **Solar v2**: SDO con selector de canal + mapa propio de regiones + datos
  explicados + Luna (fase) + planetas visibles al ocaso + enlaces externos.

**Consecuencias**: la interfaz gana la coherencia que pedía el diseño
(DESIGN.md); `explain_elements` devuelve filas con `level` (basic/deep) y `param`
bilingüe; `orbits.pick()` centraliza la selección de idioma; los workers liberan
con `deleteLater` (aprendimos que los items subclaseados de QTableWidget +
sortItems provocaban segfault — se evita el patrón).

## English

**Context**: after testing v1, the user flagged integration and usability issues:
two languages mixed on screen, non-intuitive technical explanations (MOID), 2D
charts hidden at the bottom of the text, a context-less solar view, no menu bar,
no "what can I observe RIGHT NOW" distinction, and one table for very different
object kinds.

**Decision**:
- **Single on-screen language** (the configured one); only generated posts stay
  bilingual ES+EN (that is their purpose).
- **Menu bar**: File/View/Tools/Help; Settings moves from a tab to a modal dialog
  (Tools → Settings…); language under View.
- **"Right now"** inside Tonight: targets above the horizon *at this instant*
  (own alt-az), refreshable.
- **Dynamic columns** in the table per type filter (NEOs: NEOfixer, NObs, MOID;
  SNe: type, host, discovery; etc.) plus a detail panel for the selected target.
- **Explore v2**: Parameters (basic / In depth) + Orbit + Sky tonight + Families
  + Field tabs; explanations rewritten with metaphors (MOID as two crossing
  roads).
- **Solar v2**: SDO with channel selector + own region map + explained data +
  Moon (phase) + planets visible at dusk + external links.

**Consequences**: the interface gains the coherence the design asked for;
`explain_elements` returns rows with `level` (basic/deep) and bilingual `param`;
`orbits.pick()` centralises language selection; workers are released with
`deleteLater` (we learned that subclassed QTableWidgetItems + sortItems caused a
segfault — the pattern is avoided).
