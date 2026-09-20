# ADR-039: Features accordion (single column, zigzag, native `<details>`) / Acordeón de features (columna única, zigzag, `<details>` nativo)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-17 · **Ejecutado / Executed**: 2026-09-17

## Español

### Contexto

La web de NightScribe usaba una cuadrícula masonry de 2 columnas (`.features-masonry` + `.feature-col` / `.feature-col--stagger`) para presentar las 12 características del programa. La revisión con el observador (2026-09-17) pidió:

1. **Una sola columna de filas** (adiós masonry 2 cols).
2. **Zigzag**: filas pares desplazadas a la derecha con margen fluido `clamp(24px, 6vw, 96px)` — en móvil no rompe.
3. **Acordeón nativo**: solo el titular visible al cargar; clic en la fila despliega todo el contenido.
4. **Todas cerradas al inicio**, varias abiertas a la vez (sin JS, `<details>`/`<summary>` lo permite de serie).
5. **Hero fijo arriba** como banner (LCP intacto, `fetchpriority="high"` eager, no lazy).
6. **Cero cadenas nuevas**: el `<summary>` reutiliza la misma clave i18n `feat.N.title` que el `h3` interior.
5. **No tocar** masonry/stagger/reveal/accordion-JS de otras secciones ni el `main.js` existente.

### Decisión

1. **Contenedor**: `.features-masonry` → `.feature-list` (flex column, 1 columna).
2. **Cada feature**: envuelto en `<details class="feature-row" id="feat-N">` con `<summary class="feature-summary">` que muestra:
   - `<span class="feature-number mono">NNN</span>` (reutiliza el número del bloque).
   - `<h3 class="feature-title" data-i18n="feat.N.title"></h3>` (misma clave i18n, sin cadenas nuevas).
   - Caret `▸/▾` como `::after` CSS (no texto i18n).
3. **Zigzag**: `.feature-list .feature-row:nth-child(even) { margin-left: clamp(24px, 6vw, 96px); }`.
4. **Todo cerrado al cargar**: ningún atributo `open`.
5. **Ocultar duplicados internos** (CSS): `.feature-list .feature-block .feature-title, .feature-list .feature-block .feature-number { display: none; }` — el bloque interno queda intacto para el JS/acordeón heredado.
6. **Validación contractual** (idempotente, autovalidada antes de escribir):
   - 12 `<details class="feature-row">` + 12 `<summary class="feature-summary">`
   - 13 imgs `feature-screenshot` con `width`/`height` reales (CLS-cero)
   - 0 wireframes, balance `<div`/`</div>` = 0
   - i18n `feat.N.title` × 24 (12 summary + 12 internos)
   - 0 `features-masonry`, 0 `feature-col` en la sección
6. **CSS añadido** (marca `/* ==== ADR-039 … */`): idempotente, no duplica al re-ejecutar.
7. **ADR-038 (ux-prominence)** queda intacto; este ADR documenta SOLO el acordeón de features.

### Consecuencias

- HTML: balance 0 garantizado (walker anclado en `id="feat-N"` único, 12/12).
- CLS: 13 imgs con `width`/`height` reales (hero eager, 12 lazy).
- i18n: 0 claves nuevas, 129 totales inmutables.
- JS: `main.js` sin cambios; acordeón interno `.feature-block.expanded` sigue operando en el bloque abierto (capa interior, no rompe el nativo).
- Serve-check: index 200, 13 PNGs 200, 0 404 en `127.0.0.1:8765`.

---

## English

### Context

NightScribe's website used a 2-column masonry grid (`.features-masonry` + `.feature-col` / `.feature-col--stagger`) to show the 12 program features. The observer review (2026-09-17) requested:

1. **Single-column rows** (no more 2-col masonry).
2. **Zigzag**: even rows shifted right with fluid margin `clamp(24px, 6vw, 96px)` — mobile-safe.
3. **Native accordion**: only the title visible on load; click the row to expand all content.
4. **All closed initially**, multiple open at once (no JS, native `<details>`/`<summary>` allows this).
5. **Hero fixed on top** as banner (LCP intact, `fetchpriority="high"` eager, no lazy).
6. **Zero new strings**: `<summary>` reuses the same i18n key `feat.N.title` as the inner `h3`.
7. **Don't touch** masonry/stagger/reveal/accordion-JS in other sections or existing `main.js`.

### Decision

1. **Container**: `.features-masonry` → `.feature-list` (flex column, single column).
2. **Each feature**: wrapped in `<details class="feature-row" id="feat-N">` with `<summary class="feature-summary">` showing:
   - `<span class="feature-number mono">NNN</span>` (reuses block's number).
   - `<h3 class="feature-title" data-i18n="feat.N.title"></h3>` (same i18n key, no new strings).
   - Caret `▸/▾` as CSS `::after` (no i18n text).
3. **Zigzag**: `.feature-list .feature-row:nth-child(even) { margin-left: clamp(24px, 6vw, 96px); }`.
4. **All closed on load**: no `open` attribute.
5. **Hide inner duplicates via CSS**: `.feature-list .feature-block .feature-title, .feature-list .feature-block .feature-number { display: none; }` — inner block stays intact for legacy JS/accordion.
6. **Contractual validation** (idempotent, self-validating before write):
   - 12 `<details class="feature-row">` + 12 `<summary class="feature-summary">`
   - 13 `feature-screenshot` imgs with real `width`/`height` (CLS-zero)
   - 0 wireframes, `<div`/`</div>` balance = 0
   - i18n `feat.N.title` × 24 (12 summary + 12 inner)
   - 0 `features-masonry`, 0 `feature-col` in section
7. **CSS appended** (marker `/* ==== ADR-039 … */`): idempotent, no duplicate on re-run.
8. **ADR-038 (ux-prominence)** untouched; this ADR documents ONLY the features accordion.

### Consequences

- HTML: balance 0 guaranteed (walker anchored on unique `id="feat-N"`, 12/12).
- CLS: 13 imgs with real `width`/`height` (hero eager, 12 lazy).
- i18n: 0 new keys, 129 total unchanged.
- JS: `main.js` unchanged; inner `.feature-block.expanded` accordion still works inside open row (inner layer, doesn't break native).
- Serve-check: index 200, 13 PNGs 200, 0 404 on `127.0.0.1:8765`.