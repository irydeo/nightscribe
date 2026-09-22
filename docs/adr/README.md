# Architecture Decision Records — NightScribe

*Decisiones de arquitectura y diseño, bilingües ES/EN. Ver ADR-000 para el proceso.*
*Architecture and design decisions, bilingual ES/EN. See ADR-000 for the process.*

| ADR | Decisión / Decision |
|---|---|
| [000](ADR-000-use-adrs.md) | Usar ADRs / Use ADRs |
| [001](ADR-001-pyside6.md) | PySide6 (Qt6) para la GUI / for the GUI |
| [002](ADR-002-sqlite.md) | SQLite para caché y estado / for cache and state |
| [003](ADR-003-neofixer.md) | NEOfixer fuente primaria de NEOs / as primary NEO source |
| [004](ADR-004-no-astropy.md) | Sin astropy/astroquery / No astropy dependency |
| [005](ADR-005-ui-designer-files.md) | `.ui` de Designer en runtime / Designer files at runtime |
| [006](ADR-006-suggestion-engine.md) | Motor de sugerencias por reglas / Rule-based suggestion engine |
| [007](ADR-007-code-style.md) | Estilo saas, voz humana / saas style, human voice |
| [008](ADR-008-own-visualizations.md) | Visualizaciones propias, copyright / Own visualizations |
| [009](ADR-009-schlyter-ephemerides.md) | Efemérides Schlyter / Schlyter ephemerides |
| [010](ADR-010-matplotlib.md) | matplotlib motor único / single render engine |
| [011](ADR-011-comets-cobs-sbdb.md) | Cometas: COBS + SBDB / Comets: COBS + SBDB |
| [012](ADR-012-pccp-scraping.md) | PCCP vía scraping MPC / PCCP via MPC scraping |
| [013](ADR-013-bilingual-docs.md) | Documentación bilingüe / Bilingual documentation |
| [014](ADR-014-i18n-qt-linguist.md) | i18n con Qt Linguist / UI i18n with Qt Linguist |
| [015](ADR-015-exoplanets.md) | Exoplanetas: ExoClock + Archive / Exoplanets: ExoClock + Archive |
| [016](ADR-016-sn-images.md) | Imágenes de SN propias / Own SN images |
| [017](ADR-017-ux-v2.md) | UX v2: menú, «ahora», columnas dinámicas / menu, "now", dynamic columns |
| [018](ADR-018-sn-blink-wcs.md) | Blink SN: FITS/WCS propio + cutouts casados / own FITS/WCS + matched cutouts |
| [019](ADR-019-projects-ux-v3.md) | UX v3: flujo centrado en proyectos / project-centric workflow |
| [020](ADR-020-local-horizon.md) | Horizonte local y restricciones / local horizon & observing constraints |
| [021](ADR-021-capture-exports.md) | Exportar secuencias y efemérides / capture & ephemeris exports |
| [022](ADR-022-mpc-report.md) | Reporte MPC: pegar y validar / MPC report: paste & validate |
| [023](ADR-023-neocp-preliminary-orbits.md) | Órbitas preliminares NEOCP vía NEOfixer /orbit/ / NEOCP preliminary orbits via NEOfixer |
| [024](ADR-024-post-references-resources.md) | Post autocontenido: el markdown referencia gráficos y blink / self-contained post: markdown references charts & blink |
| [025](ADR-025-mag-limit-hybrid.md) | Magnitud límite híbrida: duro donde se mide, aviso donde se predice / hybrid limiting mag: hard where measured, warned where predicted |
| [026](ADR-026-dark-global-theme.md) | Tema oscuro global: una hoja de estilos, una paleta / dark global theme: one stylesheet, one palette |
| [027](ADR-027-panel-context-fallback.md) | Ficha con contexto del planner: la historia no depende de SIMBAD/SBDB / panel context fallback: the story does not depend on SIMBAD/SBDB |
| [028](ADR-028-settings-tabs.md) | Configuración en cuatro pestañas / settings as four tabs |
| [029](ADR-029-qt-view-widgets.md) | Cartas vectoriales en la GUI (QGraphics, sin matplotlib) / vector chart widgets (QGraphics, no matplotlib) |
| [030](ADR-030-ccdciel-json-rpc.md) | Integración en vivo con CCDciel (JSON-RPC) / CCDciel live integration (JSON-RPC) |
| [031](ADR-031-object-card-unification.md) | Ficha de objeto unificada: coords copiables, tabla multilínea y por tipo, «Discovered» en NEOs, filtro de apertura / unified object card: copyable coords, per-type multi-line table, NEO "Discovered", aperture gate |
| [032](ADR-032-project-container-folder.md) | Carpeta contenedora de proyectos / project container folder |
| [033](ADR-033-versioning-setuptools-scm.md) | Versionado automático con setuptools-scm / automatic versioning with setuptools-scm |
| [034](ADR-034-hads-stars.md) | Estrellas HADS: catálogo empaquetado, observación continua sin fase / HADS stars: bundled catalogue, phase-free continuous observation |
| [035](ADR-035-variables-campaigns.md) | Variables de largo periodo y campañas de observación (kind `variable`, campaña 1:N, VSX/SIMBAD, HJD) / long-period variables and observing campaigns (`variable` kind, 1:N campaign, VSX/SIMBAD, HJD) |
| [036](ADR-036-journal-and-sunsky.md) | Historial → Diario de observación (menú, vista derivada) y Solar → «Sol y cielo» (divulgación) / History → observing journal (menu, derived view) & Solar → "Sun & sky" (outreach) |
| [037](ADR-037-campaign-signals.md) | Campañas = consola de señales; eventos de variables en tres pisos / Campaigns = signals console; variable-star events in three tiers |
| [038](ADR-038-ux-prominence-attention.md) | Prominencia de acciones, lenguaje llano y el dashboard «Necesita tu atención» / action prominence, plain language and the attention dashboard |
| [039](ADR-039-features-accordion.md) | *(reservado: acordeón de la web, stream paralelo / reserved: web accordion, parallel stream)* |
| [040](ADR-040-sky-calendar-events.md) | El sistema solar como fuente de eventos: «Calendario del cielo» y lunas de Júpiter / the solar system as an event source: "Sky calendar" & Jupiter's moons |
| [041](ADR-041-project-tab-bar.md) | La página del proyecto como barra de pestañas perezosas (5 pestañas planas, una visible a la vez, deep-links y tarjeta «Siguiente» intactos) / the project page as a lazy tab bar (5 flat tabs, one visible at a time, deep links and the "Next" card intact) |
| [042](ADR-042-photometric-sequences.md) | Secuencias fotométricas: VizieR (Gaia/APASS/VSX), transformaciones y propuesta automática de comparaciones / photometric sequences: VizieR (Gaia/APASS/VSX), transformations and automatic comparison proposal |
| [043](ADR-043-observatory-folded-into-capture.md) | La pestaña Observatory se pliega en el paso Captura; pasos renombrados (Captura/Seguimiento/Follow-up, Worklog/Bitácora) y plan autoguardado / the Observatory tab folds into the Capture step; steps renamed (Capture/Track/Follow-up, Worklog/Bitácora) and silent plan auto-save |
