# ADR-059: La captura como consola de misión / Capture as a mission console

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-02 ·
**ejecutado / executed**: 2026-10-02 (suite unitaria green, i18n 2160
cadenas, 0 unfinished)

**Ver / See**: ADR-057 (el dossier de la ficha, cuyo lenguaje visual
extiende esta ADR) · ADR-058 (nada sin explicación) · ADR-041 (la barra
de pestañas y el contrato sin scroll) · ADR-043 (CCDciel vive en Captura)
· ADR-030 (el control de CCDciel) · ADR-021 (exportaciones)

## Español

**Contexto.** ADR-057 rediseñó la Ficha como dossier (hero, tira KPI,
tarjetas de sección) y ADR-058 hizo que ningún código o cifra vaya sin
explicación. La pestaña Captura, en cambio, seguía siendo un formulario
vertical de `QGroupBox` y etiquetas sueltas: un título "Capture plan"
flotante, una fila de spins sin tarjeta, cajas separadas por tipo, el
panel CCDciel como una caja más y la exportación en filas sueltas. El
observador pidió aplicar a Captura el mismo plan de mejora de estilo.

**Decisión** (pactada con el observador, 2026-10-02): Captura pasa a ser
una **consola de misión**, con el mismo lenguaje visual que el dossier:

1. **Tira resumen** al abrir: tres teselas KPI (`KpiTile`, ADR-057) con
   la integración total (N × exposición), el filtro activo y el veredicto
   de encaje antes del alba. Se actualizan en vivo desde los mismos spins
   que alimentan la banda, así que la tira y la banda nunca se contradicen.
2. **Franja de vuelo**: la `NightRibbon` sigue dibujando la noche real con
   el plan como un bloque y el veredicto; ahora va justo bajo la tira, a
   todo el ancho.
3. **Tarjetas (`PanelCard`, nuevo)**: los bloques de control se agrupan en
   tarjetas con título y la misma piel que las secciones de la ficha:
   "Plan de exposición" (frames/exposición/filtro + calculadora NEO),
   el bloque por tipo (tránsito/HADS/variable, que deja de ser `QGroupBox`
   para ser `PanelCard`), "Secuencia" (multi-filtro + exportaciones) y
   "Telescopio y cámara" (el panel CCDciel, antes `QGroupBox`). El
   `PanelCard` es el hermano genérico de `SectionCard`: cuerpo libre para
   formularios y filas de botones, no solo listas de definición.
4. **Calibración** sigue siendo un bloque plegable (`CollapsibleSection`),
   por decisión de UX-PC U3: es secundaria al plan y vive recogida.
5. **Sin cambios de comportamiento**: mismas claves de widget
   (`plan_spins`, `spn_nframes`, `cmb_seqfmt`, `_obs_widgets`, ...), mismos
   constructores por tipo, mismo autoguardado silencioso. El rediseño es de
   contenedores y jerarquía, no de lógica.
6. **Se mantiene el contrato sin scroll** de Captura a 1360x860 con
   CCDciel conectado (Interfaz 1.8): el ritmo de las tarjetas se apretó
   (márgenes 12/6/12/6, espaciado 4) lo justo para que las cuatro tarjetas
   más la tira quepan en el viewport. La Ficha sí puede desplazarse
   (ADR-057); Captura, que es una consola de acciones, no.

**Consecuencias.** La página se lee como tarjetas y no como una pared de
cajas; el veredicto y la integración están a la vista sin bajar. Se añade
un widget reutilizable (`PanelCard`) que Análisis podrá usar en su propio
rediseño. i18n: 7 cadenas nuevas, `.ts`/`.qm` regenerados. Los tests que
fijaban la estructura (pertenencia de `_obs_widgets`, exportación,
calibración, timeline de tránsito, checklist HADS) siguen verdes porque no
se renombró ninguna clave.

## English

**Context.** ADR-057 redesigned the Object card as a dossier (hero, KPI
strip, section cards) and ADR-058 made no code or figure arrive without an
explanation. The Capture tab, however, was still a vertical form of
`QGroupBox` and loose labels: a floating "Capture plan" title, a spin row
with no card, per-kind boxes, the CCDciel panel as one more box and the
exports in loose rows. The observer asked to apply the same style plan to
Capture.

**Decision** (agreed with the observer, 2026-10-02): Capture becomes a
**mission console**, in the same visual language as the dossier:

1. **Summary strip** on open: three `KpiTile`s (ADR-057) with the total
   integration (N × exposure), the active filter and the fit-before-dawn
   verdict. They update live from the same spins that feed the band, so
   strip and band never disagree.
2. **Flight strip**: the `NightRibbon` still draws the real night with the
   plan as a block and the verdict; it now sits right under the strip,
   full width.
3. **Cards (`PanelCard`, new)**: the control blocks group into titled
   cards with the same skin as the dossier's sections: "Exposure plan"
   (frames/exposure/filter + the NEO calculator), the per-kind block
   (transit/HADS/variable, `QGroupBox` no longer, now `PanelCard`),
   "Sequence" (multi-filter + exports) and "Telescope and camera" (the
   CCDciel panel, formerly a `QGroupBox`). `PanelCard` is `SectionCard`'s
   generic sibling: a free body for forms and button rows, not only
   definition lists.
4. **Calibration** stays a collapsible block (`CollapsibleSection`), by
   the UX-PC U3 decision: secondary to the plan, so it lives folded.
5. **No behaviour change**: same widget keys (`plan_spins`,
   `spn_nframes`, `cmb_seqfmt`, `_obs_widgets`, ...), same per-kind
   builders, same silent autosave. The redesign is containers and
   hierarchy, not logic.
6. **The no-scroll contract stays** for Capture at 1360x860 with CCDciel
   connected (Interfaz 1.8): the cards' rhythm was tightened (margins
   12/6/12/6, spacing 4) just enough for the four cards plus the strip to
   fit the viewport. The Object card may scroll (ADR-057); Capture, an
   action console, does not.

**Consequences.** The page reads as cards, not as a wall of boxes; the
verdict and the integration are visible without scrolling. A reusable
widget is added (`PanelCard`) that Analysis can use in its own redesign.
i18n: 7 new strings, `.ts`/`.qm` regenerated. The tests that pinned the
structure (`_obs_widgets` membership, export, calibration, transit
timeline, HADS checklist) stay green because no key was renamed.
