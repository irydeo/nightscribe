# ADR-028: Settings as four tabs — el diálogo deja de crecer en vertical

**Estado / Status**: Accepted (actualizado 2026-09-10) · **Fecha / Date**: 2026-08-29

> **Actualización (2026-09-10)**: dos cambios de contenido y uno de UX sobre
> la base de este ADR.
>
> 1. **Contenido de Observing**: la pestaña 2 gana `grp_kinds` (el
>    whitelist de tipos para Tonight/Explore + `spn_best_pk`, el "cuántos
>    por tipo") y `grp_transits` (el filtro de apertura de ExoClock —
>    "ocultar tránsitos que exigen un telescopio mayor").
> 2. **CCDciel no tiene su propia pestaña** (ADR-030): `grp_ccdciel`
>    (host/port/auto-connect) vive dentro de **Integrations**, junto a
>    NEOfixer, Astrometry y el bot TNS — misma naturaleza (una integración
>    externa con credenciales opcionales o endpoint configurable). Así el
>    diálogo sigue en **tres** pestañas.
> 3. **Ayuda por campo, por debajo del campo**: cada campo con ayuda
>    (lat/lon, apertura, magnitud límite, pixel, .hrz, `min_alt`,
>    `best_pk`, filtro de telescopio ExoClock, directorio de proyectos,
>    aviso de Luna, auto-connect CCDciel, clave NEOfixer) lleva una
>    `QLabel` `lblH_*` **debajo** del propio widget, dentro de una fila
>    `QHBoxLayout` (etiqueta + campo + botón opcional). El estilo —
>    11 px, color `#8a90a6` (`C_TEXT_DIM`), `wordWrap` activado — se
>    aplica en `on_open_settings`; los textos viven en el `.ui` y pasan
>    por `self.tr()` (ES/EN vía `lupdate`/`lrelease`).
> 4. **Dos columnas por pestaña**: `_settings_two_columns(dlg)`
>    (`main_window.py`) re-fluye los `QGroupBox` de cada página del
>    `QTabWidget` en **dos columnas** lado a lado (un `QHBoxLayout` anidado
>    con dos `QWidget` + `QVBoxLayout`), balanceando por altura acumulada.
>    Cada columna se fija en su **ancho natural** (el mayor `sizeHint().width()`
>    de sus cajas) para que las filas anchas —etiqueta mín. 150 px + campo +
>    botón «Resolve coordinates»— nunca queden recortadas horizontalmente ni
>    la ayuda de uno o dos renglones se amontone verticalmente. El
>    `.ui` sigue siendo una sola columna plana (amigable con Qt Designer);
>    solo la altura visual cambia aquí. El diálogo se ajusta a
>    `max(820, sizeHint().width()) × sizeHint().height()`.
>
> **Actualización (2026-09-04)**: la pestaña **Charts** (`tab_charts` /
> `chart_zoom`) se ha eliminado — la opción de resolución "re-scale vs.
> re-draw 2×" se retiró al añadir los widgets vectoriales (ADR-029), que
> dibujan a resolución nativa y hacen la opción redundante. El diálogo
> queda por tanto en **tres** pestañas (Site & equipment / Observing /
> Integrations). El texto histórico de abajo conserva el porqué del
> reordenamiento; el resultado vigente es de tres pestañas.

## Español

**Contexto**: el diálogo de Ajustes era una única columna de `QGroupBox`
apilados (Site, Equipment, Camera, Horizon+Moon+Session, Charts,
NEOfixer, Astrometry, …). Con ADR-020 (horizonte local), ADR-021
(captura de imagen) y la opción `chart_zoom` la lista superaba las ocho
cajas y el diálogo medía ~560×720: en pantallas de 768 px de alto se
cortaba, y el usuario no encontraba el ajuste aunque sabía cómo
llamaba.

Además dos config-keys se editaban solo por consola de Python o
copiando el fichero de settings — no eran visibles en ningún sitio:

1. `language` — solo el menú Ayuda > Idioma lo cambiaba; en el diálogo
   de Ajustes no aparecía.
2. `tns_bot_name` / `tns_bot_key` — las credenciales de la API TNS (se
   usan en los posts) no tenían ningún campo en la GUI.

**Decisión**: reorganizar `settings_dialog.ui` como un `QTabWidget` de
cuatro pestañas, agrupando por tarea del usuario (no por origen del
ajuste). _Vigencia hoy: tres pestañas — la de Charts se retiró el
2026-09-04 (ver actualización de arriba):_

1. **Site & equipment** (`tab_site`) — quién es y con qué observa:
   `grp_language` (nuevo: `cmb_language`), `grp_site` (código MPC,
   nombre, lat/lon/altura), `grp_equip` (apertura, magnitud límite) y
   `grp_camera` (`spn_pixel_um`, `spn_focal_mm`).
2. **Observing** (`tab_observing`) — cómo filtra la noche:
   `grp_horizon` (fichero .hrz + Browse, margen, `spn_min_alt`,
   `lbl_horizon_stats` — la prioridad file>flat de ADR-020 queda hecha
   visible en la misma caja), `grp_moon` y `grp_session`
   (`spn_overhead`).
3. **Charts** (`tab_charts`) — calidad de los gráficos:
   `cmb_chart_zoom` (fast re-scale vs. re-draw 2×) + `lbl_chart_zoom`.
   _(retirada 2026-09-04: la opción `chart_zoom` eliminó con los
   widgets vectoriales de ADR-029, que dibujan a resolución nativa)_
4. **Integrations** (`tab_integrations`) — claves API opcionales:
   NEOfixer, Astrometry y las nuevas `edt_tns_bot` / `edt_tns_bot_key`.

Reglas del rediseño:

- **Ningún objectName cambia**: `edt_mpc_code`, `btn_resolve`,
  `edt_horizon_file`, `btn_horizon_browse`, `spn_min_alt`,
  `lbl_horizon_stats`, … continúan idénticos. `tests/unit/
  test_settings_horizon.py` y los helpers `_horizon_browse_into` /
  `_horizon_file_preview` de `main_window.py` siguen funcionando sin
  tocar.
- **El idioma vive en la pestaña 1** (`cmb_language`, siempre índice
  0 = System, 1 = Spanish, 2 = English). `on_open_settings` ya lo
  cargaba/guardaba; ahora es el único sitio donde el usuario lo ve.
  Un cambio solo aplica al reiniciar — misma regla que el menú, mismo
  mensaje de status bar («Settings saved — restart the app to change
  the language»).
- **Las claves TNS van a Integrations**, junto a NEOfixer y Astrometry
  (misma naturaleza: credenciales opcionales de una API externa).
- El diálogo pasa a ~640×520: cabe en una pantalla 768 px sin scroll
  y cada ajuste queda a una pestaña de distancia.

**Consecuencias**:

- El usuario encuentra cada ajuste por tarea (site / observing /
  charts / integrations) en vez de desplazarse por ocho cajas.
- `language` y `tns_bot_name`/`tns_bot_key` son editables en la GUI
  por primera vez.
- La prioridad horizonte>altitud mínima de ADR-020 (fichero usables →
  `min_alt` en gris) queda en la misma caja, sin saltar tres secciones.
- Tests nuevos: `tests/unit/test_settings_tabs.py` (offscreen) verifica
  el orden de pestañas, los objectNames por pestaña y — vía
  `inspect.getsource` — que `on_open_settings` siga mapeando
  `("system", "es", "en")` contra el índice del combo; el test de
  horizonte de ADR-020 pasa sin cambios.
- Impacto en i18n: 12 strings nuevos traducidos a ES (EN sigue siendo
  la base, `pyside6-lupdate`/`lrelease` según CONTRIBUTING); tanto
  `.qm` quedan sin `unfinished`.

**Escopado**: no cambia ninguna config-key ni su significado; no toca
el wizard de first-run (que sigue escribiendo el mismo config); no crea
una pestaña por cada ajuste futuro — si el diálogo vuelve a crecer,
se añade una pestaña nueva con el mismo criterio (tarea del usuario).

## English

**Status / Estado**: Accepted (updated 2026-09-10)

> **Update (2026-09-10)**: three changes on top of this ADR.
>
> 1. **Observing content**: tab 2 now carries `grp_kinds` (the kinds
>    whitelist for Tonight/Explore + `spn_best_pk`, "how many per kind")
>    and `grp_transits` (the ExoClock aperture filter — "hide transits
>    that would need a bigger telescope").
> 2. **CCDciel has no tab of its own** (ADR-030): `grp_ccdciel`
>    (host/port/auto-connect) lives inside **Integrations**, next to
>    NEOfixer, Astrometry and the TNS bot — same nature (external
>    integrations with optional credentials or a configurable endpoint).
>    The dialog stays at **three** tabs.
> 3. **Per-field help, below the field**: every field that has help
>    (lat/lon, aperture, limit magnitude, pixel, .hrz, `min_alt`,
>    `best_pk`, the ExoClock scope filter, the projects directory, the
>    moon warning, the CCDciel auto-connect, the NEOfixer key) carries a
>    `QLabel` `lblH_*` **under** its own widget, inside a `QHBoxLayout`
>    row (label + field + optional button). The styling — 11 px,
>    `#8a90a6` (`C_TEXT_DIM`), `wordWrap` on — is applied in
>    `on_open_settings`; the texts live in the `.ui` and pass through
>    `self.tr()` (ES/EN via `lupdate`/`lrelease`).
> 4. **Two columns per tab**: `_settings_two_columns(dlg)`
>    (`main_window.py`) re-flows each `QTabWidget` page's `QGroupBox`
>    children into **two columns** side by side (a nested `QHBoxLayout`
>    with two `QWidget` + `QVBoxLayout`), balanced by cumulative height.
>    Each column is floored at its **natural width** (the largest
>    `sizeHint().width()` among its groups) so wide rows — 150 px label +
>    field + the «Resolve coordinates» button — are never clipped
>    horizontally and 1–2-line help texts never crowd vertically. The
>    `.ui` stays a single flat column (Qt-Designer friendly); only the
>    visual height changes here. The dialog is sized to
>    `max(820, sizeHint().width()) × sizeHint().height()`.

**Context**: the Settings dialog was a single column of stacked
`QGroupBox`es (Site, Equipment, Camera, Horizon+Moon+Session, Charts,
NEOfixer, Astrometry, …). After ADR-020 (local horizon), ADR-021
(image capture) and the `chart_zoom` option the list grew past eight
boxes and the dialog measured ~560×720: on 768 px tall screens it got
clipped, and users couldn't find a setting even when they knew its
name.

Two config-keys were only editable from a Python console or by hand
editing the settings file — no GUI exposed them:

1. `language` — only the Help > Language menu changed it; the Settings
   dialog didn't show it at all.
2. `tns_bot_name` / `tns_bot_key` — the TNS API credentials (used in
   the posts) had no fields anywhere in the GUI.

**Decision**: restructure `settings_dialog.ui` as a `QTabWidget` with
four tabs, grouped by user task (not by origin of the setting). _Current
state: three tabs — the Charts tab was removed on 2026-09-04 (see the
update note above):_

1. **Site & equipment** (`tab_site`) — who and with what you observe:
   `grp_language` (new: `cmb_language`), `grp_site` (MPC code, name,
   lat/lon/height), `grp_equip` (aperture, limit magnitude) and
   `grp_camera` (`spn_pixel_um`, `spn_focal_mm`).
2. **Observing** (`tab_observing`) — how the night is filtered:
   `grp_horizon` (.hrz file + Browse, margin, `spn_min_alt`,
   `lbl_horizon_stats` — the ADR-020 file>flat precedence is made
   visible in the same box), `grp_moon` and `grp_session`
   (`spn_overhead`).
3. **Charts** (`tab_charts`) — chart quality: `cmb_chart_zoom`
   (fast re-scale vs. 2× re-draw) + `lbl_chart_zoom`.
   _(removed 2026-09-04: the `chart_zoom` option went away with the
   vector widgets of ADR-029, which render at native resolution)_
4. **Integrations** (`tab_integrations`) — optional API keys:
   NEOfixer, Astrometry and the new `edt_tns_bot` / `edt_tns_bot_key`.

Redesign rules:

- **No objectName changes**: `edt_mpc_code`, `btn_resolve`,
  `edt_horizon_file`, `btn_horizon_browse`, `spn_min_alt`,
  `lbl_horizon_stats`, … all stay identical. `tests/unit/
  test_settings_horizon.py` and the `_horizon_browse_into` /
  `_horizon_file_preview` helpers in `main_window.py` keep working
   untouched.
- **Language lives on tab 1** (`cmb_language`, always index 0 =
  System, 1 = Spanish, 2 = English). `on_open_settings` already
  loaded/saved it; now it is the only place users see it. A change
  only applies on restart — same rule as the menu, same status-bar
  message ("Settings saved — restart the app to change the language").
- **TNS keys go to Integrations**, next to NEOfixer and Astrometry
  (same nature: optional credentials for an external API).
- The dialog is now ~640×520: fits a 768 px screen without scrolling
  and every setting is one tab away.

**Consequences**:

- Users find each setting by task (site / observing / charts /
  integrations) instead of scrolling through eight boxes.
- `language` and `tns_bot_name`/`tns_bot_key` are UI-editable for the
  first time.
- The ADR-020 horizon > minimum-altitude precedence (usable file →
  `min_alt` greyed out) now lives in the same box, no jumping across
  three sections.
- New tests: `tests/unit/test_settings_tabs.py` (offscreen) checks tab
  order, objectNames per tab and — via `inspect.getsource` — that
  `on_open_settings` still maps `("system", "es", "en")` against the
  combo index; the ADR-020 horizon test passes unchanged.
- i18n impact: 12 new strings translated to ES (EN stays the base,
  `pyside6-lupdate`/`lrelease` per CONTRIBUTING); both `.qm` have no
  `unfinished`.

**Scope**: no config-key or its meaning changes; the first-run wizard
(which writes the same config) is left alone; no new tab is created per
future setting — if the dialog grows again, a new tab is added with the
same criterion (user task).
