# Plan — Concepto de proyecto v2 (documento padre)

> **Abierto (2026-09-09)** — documento transversal, sin implementar aún. Enlaza
> los cuatro planes hijos (uno por tipo de objeto / frente transversal) que se
> ejecutan de forma independiente. Un subplan = un commit cuando se ejecuten.
> **Enmendado 2026-09-09 (post-entrevista)**: tras una entrevista en profundidad
> con el observador (flujo real SN/NEO/tránsitos en el observatorio) se añaden
> las decisiones T9/T10, el horizonte de variables de corto periodo y ajustes
> de prioridad en los hijos (ver cada documento).

**rama de este documento**: `feature/exoplanet-transit-project` (merge a `feature/object-card` junto con los planes hijos)
**fecha**: 2026-09-09 · **autor**: FJC (con la IA)

## Visión

El proyecto pasa de «flujo de una noche» (Plan → Procesado → Publicar) a
**entidad con ciclo de vida completo y flujo especializado por tipo de objeto**:

- **Supernovas**: seguimiento fotométrico multi-noche (días/meses, e incluso
  revisitas «un año después» sobre el mismo proyecto), curva de luz por filtro,
  animación de la evolución y post vivo — espejo del flujo real ya practicado
  en el observatorio (p. ej. la página de AT2020sum/AT2020sun en irydeo.com,
  con fotometría AIJ y comparaciones Gaia).
- **NEOs/cometas/asteroides**: la versión actual es suficiente; solo se revisa
  la consistencia con el resto (registro de imágenes y productos Tycho, y la
  animación de movimiento como **prueba de fuego** de que el objeto es *ese*).
- **Tránsitos de exoplanetas**: captura guiada paso a paso pensada para quien
  **nunca ha capturado uno** — «que cualquiera se atreva» — y reducción externa
  con EXOTIC (handoff de `inits.json`).
- **Transversal**: los proyectos se pueden **cerrar/reabrir** (con resultado
  final), clasificar por año/tipo/etiquetas/favoritos, buscar, y sus ficheros
  generados son visibles.

**Diferenciador ya construido** (conviene decirlo): la *selección* — el paso
que en el flujo manual es el primer dolor («las SN no están en los
planetarios») — ya la resuelve NightScribe hoy: feeds (Rochester, NEOfixer,
PCCP, ExoClock), score unificado y goto con efeméride fresca. Los tracks de
abajo atacan los otros dos dolores declarados: **análisis y seguimiento**.

## Mapa de documentos (hijos)

| Track | Documento | Rama de ejecución | Orden |
|---|---|---|---|
| **A — Ciclo de vida y clasificación** | [project-lifecycle.md](project-lifecycle.md) | `feature/project-lifecycle` | 1º |
| **B — Supernova multi-noche** | [sn-followup.md](sn-followup.md) | `feature/sn-followup` | 2º |
| **C — NEO/cometa: consistencia** | [neo-consistency.md](neo-consistency.md) | `feature/neo-consistency` | 3º |
| **D — Exoplanetas: captura guiada** | [exoplanet-transit-project.md](exoplanet-transit-project.md) (ya existente, **enmendado 2026-09-09**) | `feature/exoplanet-transit-project` (ya existe) | 4º |

Cada hijo es autocontenido: objetivo, decisiones pactadas, contexto clave,
subplanes atómicos con tests, orden interno, fuera de alcance y riesgos.
Cada rama de track mergea a `feature/object-card` al cerrarse.

## Decisiones transversales pactadas (2026-09-09)

| # | Decisión | Valor |
|---|----------|-------|
| T1 | **Fotometría SN = importar + quick-look** | La fotometría «de publicación» se hace fuera (AIJ / Tycho-Tracker — flujo real del observatorio) y se **registra sin fricción** (entrada rápida: solo teclear la magnitud; pegado tolerante CSV/TSV/AIJ/Tycho; fichero opcional). Además NightScribe calcula un **quick-look diferencial indicativo** propio (B5) para ver la evolución sin salir de la app. No hay fotometría absoluta propia (términos de color = proyecto científico aparte). |
| T2 | **Comparaciones automáticas** | El quick-look selecciona solo las estrellas de comparación (criba estadística: no saturadas, aisladas, constantes en la serie; filtro Gaia DR3 de variables si hay red). El usuario **nunca selecciona a mano**; como mucho excluye una con un clic. |
| T3 | **EXOTIC = handoff, nunca embebido** | La reducción de tránsitos es 100% externa (ADR-004: no astropy; portar EXOTIC = reescribirlo). NightScribe exporta el `inits.json`; no se ejecuta ni se lee su salida en esta iteración. |
| T4 | **Ficheros del proyecto visibles** | `project_files` (hoy invisible en la GUI) se lista en el proyecto con abrir/mostrar-en-carpeta; exports a subcarpeta por proyecto `data_dir()/projects/<id>-<slug>/`. **Las rutas se registran; los FITS nunca se copian** (excepción: el FITS *anotado* de B10 es una copia nueva generada por la app). |
| T5 | **Cierre real de proyectos** | `close()/reopen()` con fecha de cierre y resultado; «Mark done» en el último paso propone cerrar. Hub clasificable por **año/tipo/etiquetas/favoritos + búsqueda**. Reabrir es un caso de uso real (revisita «un año después» sobre el mismo proyecto y la misma curva). |
| T6 | **Quick-look ≠ publicación** | Todo punto `source='quicklook'` se dibuja con estilo diferenciado (hueco) y etiqueta «indicativo». AIJ/Tycho/EXOTIC siguen siendo las fuentes científicas. |
| T7 | **Contexto de surveys (opcional)** | ASASSN/ZTF (vía ALeRCE) como puntos grises de contexto en la curva SN; subplan opcional B12. |
| T8 | **Un subplan = un commit**; cada subplan deja la app funcional con sus tests. Ramas `feature/*` → merge a `feature/object-card`. | |
| T9 | **Cadencia con memoria** (post-entrevista) | El seguimiento SN real es cada 2-3 días y «puede caer en el olvido»: el proyecto muestra «última visita hace N noches» y *Tonight* avisa cuando un proyecto SN activo toca revisita. Conecta proyectos abiertos con el planificador (B11). |
| T10 | **El asesor está en el ADN** (post-entrevista) | La app **sugiere, nunca decide**: sugerir cerrar un proyecto cuando la evolución es normal desde N días (señal del track B), sugerir revisita (T9), sugerir exposición. El usuario siempre tiene la última palabra. |

## Reglas de ejecución (de WORKFLOWS, vigentes en los 4 tracks)

- Tests offscreen, sin red, patrón `tests/unit/test_overview_panel.py`.
- Cabecera GPL en todo `.py`; código en inglés; cadenas GUI por `self.tr()`;
  pares ES/EN por `orbits.pick`.
- Toda consulta de red pasa por `core/db.py` (caché); nunca `requests` fuera
  de `core/sources/`.
- Sin astropy ni photutils (ADR-004); numpy/PIL sí.
- i18n (`lupdate` incluye `gui/widgets/*.py`, ADR-014) y docs al cierre de cada
  track; sección nueva en `docs/WORKFLOWS.es/.md` por track.
- Migraciones SQLite con `user_version` incremental (hoy v3 → A0 trae v4, B0
  trae v5); nunca romper bases existentes.

## PUNTO DE ENTRADA (para humanos o IAs que retomen esto)

1. Leer, en este orden: este padre, `docs/WORKFLOWS.es.md` (§7 completa),
   ADR-019 (proyectos), ADR-021 (exports), ADR-029 (widgets Qt) y ADR-030
   (CCDciel). Luego **solo el hijo del track que vayas a ejecutar**.
2. Empezar por el **track A, subplan A0** (migración v4). Los tracks se
   ejecutan en orden A → B → C → D; dentro de cada hijo, seguir su propio
   «Orden de ejecución».
3. **No mezclar tracks en un commit**. Si surge algo que contradice una
   decisión T1–T10, detenerse y abrir ADR nuevo antes de escribir el mínimo.
4. Estado de los tracks: marcar aquí «Hecho (fecha)» al cerrar cada uno.

| Track | Estado |
|---|---|
| A — project-lifecycle | **Hecho (2026-09-09)** |
| B — sn-followup | **Hecho (2026-09-09)** — 14 commits en `feature/sn-followup`, mergeado a `object-card` |
| C — neo-consistency | **Hecho (2026-09-10)** — C0/C1/C2 en `feature/neo-consistency`, mergeado a `object-card`; extra: fix del afín de B6 |
| D — exoplanet-transit-project | **Hecho (2026-09-10)** — subplanes 0-5 en `feature/exoplanet-transit-project`, mergeado a `object-card`; esquema EXOTIC re-verificado contra el repo vivo |

## Fuera de alcance global (v2+)

- Fotometría absoluta propia (términos de color, validación de meses).
- Monitor de flujo en vivo sobre `core/series.py` (solo monitorización, nunca
  curva científica — la reducción de tránsitos es EXOTIC). **Horizonte**:
  abriría la puerta a la observación de **estrellas variables de corto
  periodo** — condición puesta por el observador: ha de ser *tremendamente
  simple de usar*.
- Leer salida de EXOTIC (Mid-Transit Time → O-C, marca observed).
- Lanzar EXOTIC/AIJ/Tycho como subproceso.
- SNR fotométrico real (read noise/gain/cielo en config).
- `Sequence_start` vía JSON-RPC de CCDciel (ADR-030, requiere instancia real).
