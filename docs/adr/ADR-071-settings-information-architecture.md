# ADR-071: Ajustes por tarea: raíl, buscador y secciones avanzadas / Settings by task: a rail, a search and advanced sections

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-08
**Ver / See**: ADR-005 (la interfaz en los `.ui`), ADR-028 (Ajustes como
pestañas, revisado aquí), ADR-046 (anotación de cartas), ADR-051 (solver de
placa), ADR-058 (nada sin explicación), ADR-061 (calibración de imágenes),
ADR-062 (astrometría), ADR-070 (guía y web)

## Español

**Contexto**: ADR-028 convirtió el diálogo de Ajustes en un `QTabWidget` y
ADR-020, ADR-046, ADR-051, ADR-061 y ADR-062 le fueron colgando contenido.
Al llegar a siete pestañas y veinte `QGroupBox`, la agrupación ya no seguía
la tarea del observador sino el origen del ajuste, y se notaba:

1. **La pestaña 1 ("Site & equipment") era un cajón**: idioma, identidad,
   equipo, escala de placa, perfil de cámara, método fotométrico y
   anotaciones de carta en la misma columna. Era la que fijaba el tamaño del
   diálogo.
2. **Integrations mezclaba dos naturalezas**: servicios externos con
   credenciales (CCDciel, NEOfixer, TNS, AAVSO) y herramientas locales (el
   solver de placa, Find_Orb, EXOTIC). El solver estaba *anidado dentro* de
   la caja "API keys (all optional)".
3. **Fotometría y astrometría estaban partidas**: fotometría era un solo
   checkbox en la pestaña 1, astrometría tenía pestaña propia y el solver
   (que ambas necesitan) vivía en Integrations. Quien mide saltaba entre tres
   pestañas.
4. **La cámara se pedía tres veces**: escala de placa (`grp_camera`), perfil
   fotométrico (`grp_camprofile`) y la apertura en `grp_equip`, más el paso
   de equipo de la Bienvenida. Ya existía `core/cameras.py` con presets y
   `profile_from_preset`, que debería rellenarlo todo.
5. **Development tenía una sola opción** (la barra de iconos del editor), y
   la propia guía ya la describía dentro de Interface.
6. **Ajustes vivos y sin GUI**: `ccd_saturate` y `flat_resid_mag` se leen al
   medir pero no se podían editar en ningún sitio. (Otros candidatos se
   descartaron a propósito: `calib_temp_tol_c`, `calib_export`,
   `calib_pseudo_flat` y `calib_astrometry` viven en las pestañas del editor
   por decisión de ADR-061, y `calib_root`, `findorb_run` y
   `astrometry_full_frame_final` no los usa el código.)

**Decisión**: reorganizar el diálogo por **tarea del observador** en seis
categorías, con un **raíl** a la izquierda, un **buscador** arriba y páginas
desplazables a la derecha.

1. **Seis categorías** (en orden): **Observatory** (dónde y quién),
   **Equipment** (telescopio, cámara, límites), **Observing** (horizonte,
   tipos, tránsitos, Luna, sesión y vigilias, carpeta de proyectos),
   **Measurement** (fotometría, calibración, astrometría, solver,
   Find_Orb, EXOTIC), **Integrations** (CCDciel y claves) e **Interface**
   (idioma, movimiento, editor, cartas y anotaciones). Development
   desaparece; su único interruptor pasa a Interface, como ya decía la guía.
2. **La cámara es una sola caja**, encabezada por el **preset**: al elegirlo
   rellena el tamaño de píxel y el perfil de partida, y un lector en vivo
   muestra la **escala de placa** (`206265 · píxel_um / focal_mm`) y el
   full well en ADU a la ganancia puesta. El perfil medido (full well,
   ganancia, ruido, dark, linealidad, exposición máxima) se pliega bajo un
   disclosure.
3. **Measurement junta lo que se mide**: el solver y Find_Orb salen de
   Integrations y se colocan junto a la astrometría que los usa; la
   biblioteca de masters se une a la calibración. La caja "API keys" queda
   con lo que de verdad es una credencial.
4. **Un buscador** filtra las filas por su etiqueta, su ayuda y el título de
   su sección (sin acentos ni mayúsculas). Las secciones **avanzadas** se
   abren colapsadas y se despliegan al buscar si coinciden. Es el único
   sitio donde se estrena el patrón; el buscador recorre el árbol de widgets,
   no una lista que pueda quedar desincronizada.
5. **Una sola tabla de campos** (`gui/settings_spec.py`): `(objectName,
   clave_config, tipo, banderas)` la usan la carga y el guardado. Antes eran
   dos listas paralelas de unas 150 líneas que podían divergir; un test de
   ida y vuelta y otro que exige que todo campo mapee a una clave viva
   cierran esa clase de fallo. Los combos con un mapeo propio (preset,
   solver, marcador, idioma) y las listas parseadas (tipos, vigilias) siguen
   a mano, donde su índice o su dato se ve.
6. **La estructura vive en el `.ui`** (ADR-005): el raíl, el `QStackedWidget`
   con sus páginas desplazables y los grupos dentro de su página. El código
   solo rellena el raíl, pliega los avanzados y filtra. `_settings_two_columns`
   se retira: la página es una columna de secciones a todo lo ancho.

**Consecuencias**:

- El observador encuentra cada ajuste por tarea, y lo encuentra escribiendo.
- La cámara se pide una vez y conduce el preset; se deja de preguntar lo que
  se deduce (la escala de placa).
- Quien mide tiene fotometría, calibración, astrometría y solver en una
  página.
- `ccd_saturate` y `flat_resid_mag` son editables por primera vez, bajo
  "avanzado".
- Los tests: `test_settings_tabs.py` se reescribe para el raíl y las páginas
  (orden, contenido, buscador, plegado, ida y vuelta de la tabla);
  `test_settings_masters.py`, `test_settings_storage.py`,
  `test_ufe_integration.py`, `test_aavso.py` y `test_vigils.py` pasan a
  comprobar la tabla de campos en vez de las cadenas del método; la guarda
  `test_help_texts.py` y `test_i18n.py` siguen vigentes.
- i18n: las cadenas nuevas pasan por `lupdate`/`lrelease`; los rótulos del
  raíl se marcan con `QT_TRANSLATE_NOOP` para que salgan en el contexto
  `MainWindow`.
- Guía: `docs/user/10-settings.md` y su versión en español se reescriben por
  categorías y la web se regenera.

**Escopado**: no cambia ninguna clave de config ni su significado; no toca
la Bienvenida (que comparte `profile_from_preset`, así que un preset rellena
igual en los dos sitios); no duplica en Ajustes los mandos que ADR-061 quiso
junto a la receta en el editor.

## English

**Context**: ADR-028 turned the Settings dialog into a `QTabWidget`, and
ADR-020, ADR-046, ADR-051, ADR-061 and ADR-062 kept hanging content on it.
At seven tabs and twenty `QGroupBox`es the grouping no longer followed the
observer's task but the origin of the setting, and it showed:

1. **Tab 1 ("Site & equipment") was a dumping ground**: language, identity,
   equipment, plate scale, camera profile, photometry method and chart
   annotations in one column. It set the dialog's size.
2. **Integrations mixed two natures**: external services with credentials
   (CCDciel, NEOfixer, TNS, AAVSO) and local tools (the plate solver,
   Find_Orb, EXOTIC). The solver was *nested inside* the "API keys (all
   optional)" box.
3. **Photometry and astrometry were split**: photometry was a single
   checkbox on tab 1, astrometry had its own tab, and the solver (which both
   need) lived in Integrations. Whoever measured jumped between three tabs.
4. **The camera was asked three times**: plate scale (`grp_camera`),
   photometric profile (`grp_camprofile`) and the aperture in `grp_equip`,
   plus the Welcome equipment step. `core/cameras.py` already had presets
   and `profile_from_preset`, which should fill it all.
5. **Development had one option** (the editor's icon bar), and the guide
   already described it inside Interface.
6. **Live settings with no GUI**: `ccd_saturate` and `flat_resid_mag` are
   read when measuring but could not be edited anywhere. (Other candidates
   were dropped on purpose: `calib_temp_tol_c`, `calib_export`,
   `calib_pseudo_flat` and `calib_astrometry` live in the editor tabs by
   ADR-061's decision, and `calib_root`, `findorb_run` and
   `astrometry_full_frame_final` are unused by the code.)

**Decision**: reorganize the dialog by the **observer's task** into six
categories, with a **rail** on the left, a **search box** on top and
scrollable pages on the right.

1. **Six categories** (in order): **Observatory** (where and who),
   **Equipment** (telescope, camera, limits), **Observing** (horizon, kinds,
   transits, Moon, session and vigils, projects folder), **Measurement**
   (photometry, calibration, astrometry, solver, Find_Orb, EXOTIC),
   **Integrations** (CCDciel and keys) and **Interface** (language, motion,
   editor, charts and annotations). Development disappears; its only switch
   moves to Interface, as the guide already said.
2. **The camera is one box**, led by the **preset**: choosing it fills the
   pixel size and the starting profile, and a live readout shows the **plate
   scale** (`206265 · pixel_um / focal_mm`) and the full well in ADU at the
   gain set. The measured profile (full well, gain, read noise, dark,
   linearity, max exposure) folds behind a disclosure.
3. **Measurement gathers what is measured**: the solver and Find_Orb leave
   Integrations and sit next to the astrometry that uses them; the master
   library joins calibration. The "API keys" box keeps what really is a
   credential.
4. **A search box** filters the rows by their label, their help and their
   section title (accent and case insensitive). **Advanced** sections open
   collapsed and expand when the search matches them. It walks the widget
   tree, not a list that could drift.
5. **One field table** (`gui/settings_spec.py`): `(objectName, config key,
   kind, flags)` feeds both load and save. It used to be two parallel lists
   of ~150 lines that could diverge; a round-trip test and a test that every
   field maps to a live key close that class of bug. The combos with their
   own mapping (preset, solver, marker, language) and the parsed lists
   (kinds, vigils) stay hand-wired, where their index or data is visible.
6. **The structure lives in the `.ui`** (ADR-005): the rail, the
   `QStackedWidget` with its scrollable pages and the groups inside their
   page. The code only fills the rail, folds the advanced groups and
   filters. `_settings_two_columns` retires: a page is a full-width column
   of sections.

**Consequences**:

- The observer finds each setting by task, and finds it by typing.
- The camera is asked once and the preset drives it; what can be derived
  (the plate scale) stops being asked.
- Whoever measures has photometry, calibration, astrometry and the solver on
  one page.
- `ccd_saturate` and `flat_resid_mag` are editable for the first time, under
  "advanced".
- Tests: `test_settings_tabs.py` is rewritten for the rail and the pages
  (order, content, search, folding, table round-trip);
  `test_settings_masters.py`, `test_settings_storage.py`,
  `test_ufe_integration.py`, `test_aavso.py` and `test_vigils.py` check the
  field table instead of the method's strings; the `test_help_texts.py` and
  `test_i18n.py` guards stay.
- i18n: new strings go through `lupdate`/`lrelease`; the rail labels are
  marked with `QT_TRANSLATE_NOOP` so they land in the `MainWindow` context.
- Guide: `docs/user/10-settings.md` and its Spanish version are rewritten by
  category and the website is regenerated.

**Scope**: no config key or its meaning changes; the Welcome step is left
alone (it shares `profile_from_preset`, so a preset fills the same in both
places); the controls ADR-061 wanted next to the recipe in the editor are
not duplicated in Settings.

**Nota (2026-10-08): el raíl va con iconos.** El texto de cada categoría se
sustituyó por un **icono SVG** (16×16, trazo redondeado, la familia de
`assets/`), con el nombre en el **tooltip** y en el nombre accesible. Cada
categoría lleva su par `settings_<x>.svg` (apagado, `#456c9d`) y
`settings_<x>_on.svg` (activo, `#6ab0ff`), montados en un `QIcon` como modos
`Normal` y `Selected`: Qt pinta el brillante en la fila activa por sí solo,
sin código de estado. Un asset que falte cae al texto, así el raíl nunca
queda mudo. El raíl es un `QListWidget` en `IconMode` vertical, sin borde,
con una barra de acento marcando la sección activa.

**Note (2026-10-08): the rail goes with icons.** Each category's text was
replaced by an **SVG icon** (16×16, round caps, the `assets/` family), with
the name in the **tooltip** and the accessible name. Each category carries
its pair `settings_<x>.svg` (dim, `#456c9d`) and `settings_<x>_on.svg`
(active, `#6ab0ff`), mounted in a `QIcon` as its `Normal` and `Selected`
modes: Qt paints the bright one on the active row by itself, with no state
code. A missing asset falls back to the text, so the rail never goes mute.
The rail is a `QListWidget` in vertical `IconMode`, borderless, with an
accent bar marking the active section.
