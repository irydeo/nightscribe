# AGENTS.md — NightScribe

*Guía del proyecto para personas y agentes de IA / Project guide for humans and AI agents.*

---

## Español

### Qué es esto

**NightScribe** es una aplicación de escritorio (GUI PySide6 + CLI) para observatorios
astronómicos amateur. Tres misiones:

1. **Planificar la noche**: sugiere los mejores objetivos (NEOs, cometas, candidatos PCCP,
   supernovas, tránsitos de exoplanetas) visibles desde el observatorio.
2. **Entender cada objeto**: traduce los parámetros orbitales y físicos a explicaciones
   precisas y divulgativas.
3. **Contarlo**: genera borradores de posts bilingües (ES/EN) + tuit + gráficos PNG listos
   para redes sociales.

Autor: Francisco José Calvo Fernández (Observatorio Irydeo, MPC Z41). Licencia GPL v3.

### Reglas de código (obligatorias)

- **Código siempre en inglés**: identificadores, comentarios, cabeceras. La documentación
  vive en `docs/` en español e inglés.
- **Cabecera en TODOS los ficheros `.py`** (copiar tal cual, adaptando el nombre del módulo):

```
############################################################
# -*- coding: utf-8 -*-
#
# NightScribe - <Module name> module
# Python  v3.12
#
# Francisco José Calvo Fernández
# (c) 2026
#
# Licence GPL v3
#
############################################################
```

- **Voz humana**: comentarios cortos sobre cada método con `# @args:` / `# @return:`,
  como en el proyecto hermano `saas/`. Nada de docstrings robóticos ni sobre-ingeniería.
  Los TODOs se escriben como `# TODO: ...` donde apliquen.
- **Mantenible por personas**: funciones cortas, dependencias mínimas, sin magia.
- **Toda cadena visible en la GUI pasa por `self.tr()`** (ver CONTRIBUTING).
- **Toda consulta de red pasa por `core/db.py` (caché)**: nunca llamar a `requests` desde
  fuera de `core/sources/`.

### Estructura

```
nightscribe/
  __main__.py        # CLI: tonight | explore | post | solar | blink | history | gui
  config.py          # configuración persistente (observatorio, idioma, claves)
  paths.py           # rutas por SO (platformdirs)
  core/
    db.py            # SQLite: caché HTTP, listas, observaciones, settings
    coords.py        # alt-az, hora sidereal, crepúsculos (math puro)
    ephem_minor.py   # Sol/Luna/planetas (Schlyter) + kepler para cuerpos menores
    planner.py       # construye la lista de objetivos de la noche
    suggest.py       # score unificado 0-100 + Top N + frases "por qué esta noche"
    orbits.py        # familias orbitales + parámetros explicados
    hads.py          # HADS: catálogo híbrido (snapshot+sheet), merge, mat. de sesión
    variables.py     # variables: extremos VSX, HJD (Sol Schlyter), asesor de eventos
    campaign.py      # campañas 1:N ortogonales (CRUD, protocolo, due_campaigns,
                     #   project_signal, tonight_listable, signals_report — ADR-037)
    vigils.py        # vigilias de variables (ADR-037 SC4a): lista curada editable
                     #   (T CrB/R CrB), chequeo ZTF vs basal (caché propia 12 h)
    photometry_export.py  # reporte fotométrico: CSV + AAVSO EFF (TTL n/a, local)
    solar.py         # estado del Sol agregado
    transits.py      # tránsitos de exoplanetas (t0 + n*P, visibilidad, ventana de captura)
    exotic.py        # handoff EXOTIC: inits.json pre-rellenado (Track D; nunca embebido)
    enrich.py        # orquesta fuentes -> datos crudos de un objeto
    narrative.py     # prosa divulgativa ES/EN
    post.py          # plantillas -> post_ES / post_EN / tuit
    fits_io.py       # lector FITS mínimo (numpy, sin astropy — ADR-018)
    wcs.py           # WCS TAN mínimo (pixel<->cielo, escala, rotación)
    blink.py         # blink de SN: resuelve nombre->coords, pareja alineada PS1-g
    sources/         # una clase/módulo por fuente externa (ver docs/DATA_SOURCES)
                     # + hads_sheet.py: libro HADS de P. Wils (Google Sheets XLSX,
                     #   TTL 12 h, parseo stdlib; ver ADR-034)
                      # + ccdciel.py: cliente JSON-RPC local del observatorio (ADR-030,
                      #   solo comanda con CCDciel abierto; lecturas cacheadas TTL 60s)
                      # + vsx.py: AAVSO VSX (subdominio vsx.aavso.org, TTL 7 d; ADR-035)
                      # + surveys.py: contexto ALeRCE/ZTF en curvas (TTL 30 d; ADR-035)
                      #   y última magnitud para vigilias (claves "vigils:", TTL 12 h)
                      # + aavso.py: canal editorial AAVSO — alertas del foro (JSON
                      #   Discourse) + campañas activas (TTL 12 h; ADR-037 SC4b)
                     #   + fotometría de la comunidad con token (vigilias brillantes)
    journal.py       # Diario de observación: vista derivada por noche (ADR-036)
  viz/               # matplotlib: style, orbit_view, sky_view,
                     # sun_panel, transit_view, sn_view, blink_view (GIF/MP4/PNG blink)
                     # + evolution_view (evolución SN) y motion_view (movimiento NEO —
                     #   la "prueba de fuego", Track C)
   gui/               # app, main_window, workers (QThread), wizard, ui/ (*.ui Designer);
                      # cinco pestañas: Tonight, Projects, **Campaigns**, **Sun & sky**,
                      # Observatory (ADR-019/035/036 rev.) — el **Diario de observación**
                      # vive en el menú Herramientas (journal_dialog.py, ADR-036)
                      # + widgets/ (QGraphicsView chart widgets — ADR-029, sin matplotlib;
                      #   incl. timeline_widget: línea de tiempo del tránsito, Track D)
tests/
  unit/              # sin red
  functional/        # con red; verifican cada funcionalidad de punta a punta
docs/                # diseño, arquitectura, fuentes, scoring, órbitas, viz, ADRs
```

### Cómo trabajar

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest tests/unit     # rápido, sin red
.venv/bin/python -m pytest tests/functional  # con red, verifica funcionalidades
.venv/bin/python -m nightscribe gui    # arranca la GUI
```

### Decisiones

Toda decisión de arquitectura/diseño está en `docs/adr/` (ADR-000 a ADR-037, bilingües).
Antes de cambiar una decisión, lee el ADR; si la cambias, actualiza el ADR.

**Rediseño activo (2026-08-24)**: la app migra a un flujo centrado en proyectos
(UX v3: ADR-019 a ADR-022). El documento maestro con los flujos, las fases y el
**punto de entrada del próximo trabajo** es `docs/WORKFLOWS.es.md` — léelo antes de
escribir código nuevo.

---

## English

**NightScribe** is a desktop application (PySide6 GUI + CLI) for amateur astronomical
observatories. Three missions: **plan the night** (NEOs, comets, PCCP candidates,
supernovae, exoplanet transits), **understand each object** (orbital parameters translated
into accurate, engaging explanations), and **report it** (bilingual ES/EN social media
drafts + tweet + ready-to-attach PNG charts).

### Code rules (mandatory)

- **Code is always English**: identifiers, comments, headers. Documentation lives in
  `docs/` in Spanish and English.
- **The header block above goes in EVERY `.py` file** (adjust module name).
- **Human voice**: short `# @args:` / `# @return:` comments above each method, in the
  spirit of the sibling project `saas/`. No robotic docstrings, no over-engineering.
- **Every GUI-visible string goes through `self.tr()`** (see CONTRIBUTING).
- **All network access goes through `core/db.py` (cache)**: never call `requests`
  outside `core/sources/`.

### Layout, workflow, decisions

See the Spanish section above (structure and commands are identical). All design
decisions live in `docs/adr/` (ADR-000 to ADR-037, bilingual). Read the ADR before
changing a decision; update it if you do.

**Active redesign (2026-08-24)**: the app is migrating to a project-centric workflow
(UX v3: ADR-019 to ADR-022). The master document with flows, phases and the **entry
point for the next chunk of work** is `docs/WORKFLOWS.md` — read it before writing
new code.
