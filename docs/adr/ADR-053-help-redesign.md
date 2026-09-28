# ADR-053: Rediseño del menú Ayuda: guía curada, fuentes, novedades y Acerca de / Help menu redesign: curated guide, sources, what's new and About

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-28

## Español

**Contexto**: el menú Ayuda tenía solo tres entradas delgadas: «Technical
Documentation» (un navegador que lista *todos* los `.md` del repo, incluidos
`adr/` internos), «About» (un `QMessageBox`) y «Data sources» (otro
`QMessageBox` con una lista estática). Dos puertas a una misma cosa (los
docs) sin jerarquía: el usuario principiante se topara con la documentación
técnica de mantenedor antes que con una guía de uso, y las dos entradas de
información (about, fuentes) daban más bien poco.

**Decisión**: separar **quién** lee la ayuda y **qué** necesita, con cinco
entradas y dos puertas bien distintas:

- **Guía…** (`action_guide`): un documento curado y breve
  (`docs/GUIDE.{,es.}md`) para empezar a usar la app. Lenguaje llano, sin
  `adr/`, filtrado por idioma (ADR-013, espíritu de ADR-038: la app habla
  primero, en palabras del usuario).
- **Novedades…** (`action_whats_new`): un `docs/CHANGELOG.{,es.}md` breve
  de lo nuevo en la versión, en el mismo diálogo de documento.
- **Data sources**: ahora abre el documento real
  `docs/DATA_SOURCES.{,es.}md` en un diálogo de documento, no una caja
  estática.
- **Technical Documentation**: la puerta completa de siempre (navegador con
  árbol + búsqueda), que sigue incluyendo `adr/` para el mantenedor.
- **About NightScribe**: un diálogo real (`AboutDialog`) con versión exacta,
  autor, licencia, enlaces a GitHub y «report issue» pre-rellenado con la
  versión, y un botón que abre la carpeta de datos/config.

Dos piezas de interfaz nuevas (ADR-005):

- **`DocDialog`** (`gui/doc_dialog.py` + `gui/ui/doc_dialog.ui`): un diálogo
  de *un solo* documento, página clara (ADR-026), sin árbol. Reaprovecha el
  render de `gui/markdown.py`. Lo comparten «Guía», «Novedades» y
  «Data sources» (cada una pasa su `.md` y su idioma).
- **`AboutDialog`** (`gui/about_dialog.py` + `gui/ui/about_dialog.ui`):
  reemplaza el `QMessageBox.about`.

Y una mejora de **`DocViewer`** (la puerta técnica): parámetros `exclude`
(carpetas a no listar, p.ej. `adr`) y `locale` (filtra `*.es.md` para el
idioma activo), más una caja de búsqueda sobre el árbol que filtra en vivo.
Ambas puertas (Guía y Documentación) heredan el filtro por idioma y, en el
caso de la Guía, la exclusión de `adr/`.

**Alternativas**:
- Meter todo en un solo navegador con el árbol filtrado por pestañas (rechazado:
  una puerta para dos lectores distintos sigue confundiendo al usuario).
- Dejar «About» y «Data sources» como `QMessageBox` (rechazado: se quedan de
  largo y no dan enlaces ni accionan nada).
- No crear `GUIDE.md`/`CHANGELOG.md` y apuntar a `WORKFLOWS` (rechazado:
  `WORKFLOWS` es el documento maestro de diseño, no una guía de uso del
  usuario).

**Consecuencias**: el usuario entra por la **Guía** (curada) y encuentra
fuentes y novedades al lado; el mantenedor tiene el **DocViewer** completo
(ADR-013). ADR-036/038: lenguaje llano en las nuevas entradas. Los `adr/*`
siguen en la puerta técnica, no en la Guía. Cada `.ui` nuevo declara márgenes
11 y el huso se oculta (contrato ADR-005, cubierto en `tests/unit/
test_ui_files.py`). Toda cadena visible pasa por `self.tr()` y los `.ts`/`.qm`
se regeneran (ADR-014). Se añade una fila al índice
`docs/adr/README.md` y se actualiza el rango de ADRs en `AGENTS.md`.

## English

**Context**: the Help menu had only three thin entries: "Technical
Documentation" (a browser that lists *every* `.md` in the repo, `adr/`
included), "About" (a `QMessageBox`) and "Data sources" (another
`QMessageBox` with a static list). Two doors into the same place (the docs)
with no hierarchy: a beginner hit the maintainer's technical documentation
before any usage guide, and the two info entries (about, sources) gave very
little.

**Decision**: separate **who** reads the help and **what** they need, with
five entries and two clearly different doors:

- **Guide…** (`action_guide`): a curated, short document
  (`docs/GUIDE.{,es.}md`) to start using the app. Plain language, no `adr/`,
  locale-filtered (ADR-013, in the spirit of ADR-038: the app speaks first,
  in the user's words).
- **What's new…** (`action_whats_new`): a short `docs/CHANGELOG.{,es.}md` of
  what is new in this version, in the same document dialog.
- **Data sources**: now opens the real `docs/DATA_SOURCES.{,es.}md` in a
  document dialog, not a static box.
- **Technical Documentation**: the full door of before (browser with tree +
  search), still including `adr/` for the maintainer.
- **About NightScribe**: a real dialog (`AboutDialog`) with the exact
  version, author, licence, links to GitHub and a pre-filled "report issue"
  carrying the version, and a button that opens the data/config folder.

Two new UI pieces (ADR-005):

- **`DocDialog`** (`gui/doc_dialog.py` + `gui/ui/doc_dialog.ui`): a
  *single-document* dialog, light page (ADR-026), no tree. Reuses the
  `gui/markdown.py` renderer. Shared by "Guide", "What's new" and "Data
  sources" (each passes its `.md` and locale).
- **`AboutDialog`** (`gui/about_dialog.py` + `gui/ui/about_dialog.ui`):
  replaces the `QMessageBox.about`.

And an improvement to **`DocViewer`** (the technical door): `exclude`
(folders not to list, e.g. `adr`) and `locale` (filter `*.es.md` to the
active language) parameters, plus a search box above the tree that filters
live. Both doors (Guide and Documentation) inherit the locale filter and the
Guide also excludes `adr/`.

**Alternatives**:
- Everything in one browser with a per-tab filtered tree (rejected: one door
  for two different readers still confuses the user).
- Keep "About" and "Data sources" as `QMessageBox` (rejected: they stay thin
  and give no links and do nothing).
- Don't create `GUIDE.md`/`CHANGELOG.md` and point at `WORKFLOWS` (rejected:
  `WORKFLOWS` is the master design document, not a user usage guide).

**Consequences**: the user enters through the **Guide** (curated) and finds
sources and what's new next to it; the maintainer has the full **DocViewer**
(ADR-013). ADR-036/038: plain language in the new entries. The `adr/*` stay
in the technical door, not in the Guide. Every new `.ui` declares 11 margins
and hides the husk (ADR-005 contract, covered in `tests/unit/test_ui_files.py`).
Every visible string goes through `self.tr()` and the `.ts`/`.qm` are
regenerated (ADR-014). A row is added to the `docs/adr/README.md` index and
the ADR range in `AGENTS.md` is updated.
