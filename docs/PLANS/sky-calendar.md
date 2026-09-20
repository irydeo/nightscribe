# Plan — Track SC2 «Calendario del cielo» + U7 (cierre UX-PC) (2026-09-17)

> **EJECUTADO COMPLETO (2026-09-17)** — U7 (`3a38c6d`) + SC0 (`f06573a`,
> `46acd46`) + SD (`9060ca9`) + SC1 (`27fd9da`) + SC2 (`4756416`) + SC3
> (este cierre). Suite unitaria **1366** verde, i18n **940** cadenas 0
> unfinished. Decisión documentada: **ADR-040** (+ revisión de ADR-036).
> La tabla de validación de las oposiciones y las 22 ventanas Horizons de
> los galileanos están en §«Estado de la sesión».

**rama**: U7 en `feature/ux-projects-campaigns` (la rama activa, ya en
GitHub); el track SC2 en rama nueva propia **`feature/sky-calendar`** que
nacerá de `feature/ux-projects-campaigns` post-U7. El destino de merge de
ambas se decide con el usuario; **`main` no se toca** por ahora.
**fecha**: 2026-09-17 · **autor**: FJC (con la IA)

## Estado actual del repo (verificado 2026-09-17)

- Rama activa `feature/ux-projects-campaigns`, HEAD `8fa3181` (merge de
  `origin/feature/campaigns-ux`: contiene los tracks V, UX, SC, JO, VU y
  UX-PC U1–U6). Subida a GitHub con tracking.
- Suite: **1320 tests unitarios** en verde; i18n **885** cadenas, 0
  unfinished.
- Entorno: `.venv/bin/python`; tests sin red:
  `.venv/bin/python -m pytest tests/unit`.

## Estado de la sesión (actualizado 2026-09-17 — empezar AQUÍ)

> Resumen de la sesión de implementación: lo hecho, lo validado con
> datos, el bug encontrado y su causa, y el orden exacto de lo que
> falta. Los números del §«Estado actual del repo» son históricos (al
> escribir el plan): hoy van **1322** tests en verde e i18n **890**
> cadenas.

**Hecho en esta sesión**

- **U7: completada y comprometida** — commit `3a38c6d` en
  `feature/ux-projects-campaigns` (tracking en GitHub ya configurado).
- **SC0: motor `core/skyevents.py` escrito** (553 líneas, puro, sin red)
  + extensión `ephem_minor.moon() → ecl_lat_deg`. **Aún sin tests y sin
  commit** (ambos ficheros pendientes en el árbol).
- Validación de la lista 2025–2026 contra astropy 7.0.1 (dist-packages,
  vía venv) y almanaques.

**Validado y confirmado por el observador (no re-litigar)**

Conjunciones, máximas elongaciones de Mercurio/Venus y eclipses (el par
2026-08-12 / 2026-08-28 incluido) — correctos. Oposiciones con tres
fuentes de verdad (motor ✓ astropy ✓ almanaque ✓):

| Oposición | Fecha | elong. pico | Dist. | Mag | Veredicto |
|---|---|---|---|---|---|
| Júpiter | 2026-01-10 | 179.7° | 4.23 UA | — | ✓ en el motor |
| Neptuno | 2026-09-26 | 178.6° | 28.88 UA | 7.8 | ✓ (la lectura vieja "[Uranus] 09-26" era un malentendido; el código actual emite Neptuno, correcto) |
| Urano | 2026-11-25/26 | 179.8° | 18.44 UA | 5.6 | ✓ — el "Júpiter 11-27" de la hoja del observador es ESTE, mal etiquetado |
| Saturno | 2026-10-04 (12:21 UT, Pececito) | 177.28° | 8.43 UA | 0.3 (almanaque) | ✗ **el motor no la emite — el único bug real** |
| Marte | — | máx. elong. ene–mar 2026: 11.7° | — | — | ✓ bien ausente: sin oposición en 2026 |

**Marte 2026 — dictamen**: su evento de enero es la **conjunción**
(2026-01-09/10, 2.40 UA), NO una oposición. Oposición anterior
2025-01-16; próxima **2027-02-19**. El cálculo del observador ("~780 d
después de 2024-01-19") es erróneo (780 d cae en ~16 ago 2026, no en
enero) y 2024-01-19 ya no era una oposición de Marte. Explicárselo al
observador; **no añadir ningún evento**.

**Causa raíz del bug de Saturno (confirmada con datos)**

Una oposición es oposición en **longitud eclíptica** (Δλ = 180°), no en
elongación. Si Saturno está en oposición con latitud β ≈ −2.7°, su
elongación = 180° − |β| → pico en **177.28°**, que nunca cruza el umbral
`eln[i] < 180.0 − 1.5` de `_oppositions()`. Verificado el 2026-10-04:
Δλ Sol–Saturno = 179.59° (oposición real) y astropy da el mismo pico
177.2841° → la geometría del motor es **correcta**; el umbral es
**equivocado**.

- Código buggy: `core/skyevents.py::_oppositions()`, gate en
  `if eln[i] < 180.0 - OPPOSITION_DEG: continue` (~línea 405).
- **Fix**: detectar el cruce de longitud λ_planeta − λ_sol = 180°
  reutilizando `_ecl_lon()` (~línea 149) + `_bisect_crossing()`
  (~línea 120), el mismo patrón que usa ya el escaneo de conjunciones
  lunares de este módulo. Seguir reportando `elong_deg` = elongación real (177.3 es el
  valor verdadero, no un fallo de datos).
- **Látent**: el gate `|elong| < 2°` de `_sun_conjunctions()` (~línea
  443) puede perder conjunciones superiores de planetas de β alta
  (Saturno llega a β ≈ 3.4° → elong. mín. hasta ~3.4°). Mismo fix.
- La fila «Oposición» de la tabla de reglas de este doc queda
  **superada** — actualizarla junto al fix.
- Menor: magnitud de Saturno 0.6 (motor) vs ~0.3 (almanaque) — revisar
  la fórmula de magnitud de `ephem_minor` (baja prioridad).

**Tests de regresión que faltan** (`tests/unit/test_skyevents.py` NO
existe; los invariantes de SC0 tampoco están escritos):

- Júpiter opp 2026-01-10 ±1 d · Neptuno opp 2026-09-26 ±1 d ·
  Urano opp 2026-11-25/26 ±1 d · **Saturno opp 2026-10-04 ±1 d**
  (regresión del bug) · **ausencia** de oposición de Marte en 2026 ·
  sin eventos dobles Neptuno/Urano.

**Higiene del árbol (no mezclar commits)**

- **Commit SC0** = `nightscribe/core/skyevents.py` (nuevo) +
  `nightscribe/core/ephem_minor.py` (M, `moon(ecl_lat_deg)`) +
  `tests/unit/test_skyevents.py` (nuevo) + plan/ADR.
- **Otro stream, fuera de este commit**: `website/` (nuevo, sin
  trackear), `docs/adr/ADR-039-features-accordion.md` (nuevo, sin
  trackear), `docs/WORKFLOWS.es.md` (M, §7sexies del acordeón),
  `ns_probe_gui_boot.py` (nuevo, raíz).
- **ADR**: 039 lo ocupa ya el acordeón de la web → el ADR del cielo es
  **ADR-040** (referencias de este doc actualizadas).

**Rama**: hoy en `feature/ux-projects-campaigns` @ `3a38c6d`; crear
`feature/sky-calendar` de aquí para los tracks SC.

**Siguiente movimiento (orden exacto)**

1. ~~Fix de `_oppositions` + `_sun_conjunctions` con el patrón de
   longitud~~ **HECHO (2026-09-17)**: `_lambda_crossings()` direccional-
   agnóstica (los exteriores RETROGRADAN cerca de la oposición — el
   patrón de wrap 355/5 solo sirve para la Luna; sign-change + guarda
   |Δw|>180). Saturno 2026-10-04 ✓, Neptuno 09-26 ✓, Urano 11-25 ✓,
   Júpiter 01-10 ✓, Marte: conjunción 01-09 sin oposición ✓. Ojo: un
   primer intento con el patrón de la Luna no detectó NADA (dirección) —
   la regresión lo tiene cubierto.
2. ~~`tests/unit/test_skyevents.py`~~ **HECHO**: 16 tests (tabla de
   regresión + invariantes + anclas de eclipse). El invariante de ápsides
   se midió primero: el rango físico 2026 es 11.9–15.9 d (no ~13.9 fijo).
3. ~~Regenerar la lista y confirmar que Saturno aparece~~ ✓ (salida
   completa contrastada contra la tabla validada).
4. ~~Cerrar SC0~~ ✓ → ~~**SD**~~ ✓ (**2026-09-17**): `core/satellites.py`
   — IAU WGCCRE (NAIF pck00011) + radio JPL + fase empírica calibrada
   (`phase_cal_deg`: la PM del IAU sigue la ROTACIÓN del cuerpo, que
   libra; Ganímedes −2.13°, Calisto +0.62°). **Validación: 22 ventanas
   contra Horizons q12 en sep/oct/nov 2026, todas ≤10 min (peor 9.6)**.
   Convención W+180 documentada (Luna: 38.32 = 218.32−180). Sin
   precesión del polo (ICRF inercial). La verdad horneada vive en
   `tests/unit/test_satellites.py` (21 tests) + funcional
   `test_skyevents_functional.py`. Sombra = rayo Sol→luna ∩ esfera
   (asíncrono con la luna lejos de oposición, como debe). → SC1 → SC2 →
   SC3 con **ADR-040**.
5. Mensaje al observador: Marte (conjunción ≠ oposición), 09-26 =
   Neptuno, 11-25/26 = Urano (su "Júpiter 11-27"), Saturno arreglada.

**Notas de entorno**

- astropy 7.0.1 (dist-packages, vía venv): `SkyCoord` tiene
  `.separation()` pero **no** `.separation_to()`;
  `angular_separation()` ya no acepta dos coords.
- Los scripts de verificación vivieron en `/tmp/opencode/`
  (state_capture, astropy_truth, sat_fine, opscan, elas) — **efímeros**;
  todo lo necesario se re-deriva de la tabla validada de arriba.

## U7 — la franja «Está pasando ahora» se explica sola (cierre UX-PC)

Problema (observador, 2026-09-17): «Está pasando ahora» sin nada debajo
confunde (¿a qué se refiere?); «0 of 2 up to date» no dice QUÉ está al
día; «No signals right now» es jerga. Todo en `nightscribe/gui/`:

1. `ui/campaigns_tab.ui` — grupo `grp_signals`: nueva fila de ámbito
   `lbl_signals_scope` (dim, wordWrap, estático: *"Outbursts, brightness
   drops and predicted extrema — across the stars you follow (campaigns
   and vigils)"*) + `btn_signals_help` (QToolButton `ⓘ`).
2. `main_window.py::_refresh_campaign_signals`:
   - `lbl_cov` con miembros: `tr("Up to date: %1 of %2 campaign
     projects")` + tooltip *"Measured within their campaign's cadence"*.
   - Sin campañas: *"You follow no campaigns yet — create one below and
     its stars will show up here."*
   - Lista vacía: *"✨ All calm — when a star you follow erupts, dims or
     nears a predicted extremum, it will show up here."* (fila
     `Qt.NoItemFlags`; adiós "No signals right now").
3. `main_window.py::_campaign_signals_help()` — QMessageBox.information:
   iconos ⚡ (evento detectado en TUS medidas) · ⏳ (máximo/mínimo
   previsto) · 👁 (vigilia T CrB/R CrB); doble-clic abre el proyecto; la
   franja lee la caché del último cálculo de Tonight (nunca red).
4. `_connect`: conectar `btn_signals_help`.
5. Tests (`tests/unit/test_campaigns_tab.py`): actualizar
   `test_signals_console_empty_box` y
   `test_signals_console_lists_event_with_coverage` (los números siguen
   extrayéndose en orden N, M); nuevos: calma con campañas, guía sin
   campañas, ⓘ abre.
6. i18n (§Reglas): traducciones ES pactadas:
   - "Up to date: %1 of %2 campaign projects" → "Al día: %1 de %2
     proyectos de campaña"
   - "You follow no campaigns yet…" → "Aún no sigues ninguna campaña —
     créala abajo y sus estrellas aparecerán aquí."
   - "✨ All calm…" → "✨ Todo en calma — cuando una estrella que sigues
     erupcione, caiga de brillo o se acerque a un máximo previsto, lo
     verás aquí."
   - ámbito → "Erupciones, caídas de brillo y máximos previstos — en las
     estrellas que sigues (campañas y vigilias)"
7. Docs: esta fila en `ux-proyectos-campanas.md` + nota de suite en la
   sección 7vigies de `docs/WORKFLOWS.es.md`/`.md`.
8. Commit + `git push` (tracking ya configurado).

## Track SC2 — el sistema solar como fuente de eventos (ADR-040; el 039 lo ocupa el acordeón de la web)

**Visión pactada**: la pestaña «Sun & sky» pierde entidad como pestaña →
la barra queda en **4** (Tonight · Projects · Campaigns · Observatory,
Ctrl+1..4) y TODO su contenido (SDO/NOAA, datos solares NOAA/SILSO con la
caché actual, línea de impacto, almanaque, PNG para redes, post del cielo,
enlaces Raben/SolarMonitor/SIDC) se mueve **intacto** al diálogo de
Herramientas **«Calendario del cielo…»**, enriquecido con las secciones
nuevas. El sistema solar pasa a ser **fuente de eventos** de la app
(chips en Tonight).

### Motor de eventos — `core/skyevents.py` (nuevo, puro, sin red)

Horizonte **hoy + 60 días**. Base existente: `core/ephem_minor.py` (Sol,
Luna con fase/distancia/elongación, 7 planetas con ra/dec/dist/mag —
Schlyter) + `core/coords.py` (`angular_separation`, alt/az, crepúsculos)
+ horizonte (`core/horizon.py`). **Extensión aditiva necesaria**:
`ephem_minor.moon()` debe devolver también `ecl_lat_deg` (la calcula
internamente como `lat`; basta añadirla al dict de salida).

| Tipo | Regla (escaneo, paso ≤0.1 d) | Icono |
|---|---|---|
| Fases lunares | cruce de edad 0 / 7.38 / 14.77 / 22.15 d | 🌑🌓🌕🌗 |
| Perigeo / apogeo | extremos de `moon.dist_km` (con la distancia) | 🌕 |
| Luna–planeta | mínimo de separación < 4° (+ alt al anochecer + mag) | 🌙 |
| Planeta–planeta | mínimo < 1.5° | ✨ |
| Oposición (exteriores) | **SUPERADA —** cruce de longitud eclíptica λ_planeta−λ_sol = 180° (ver §Estado del bug de Saturno) | 🔴 |
| Máx. elongación (Mercurio/Venus) | máximo local de \|elong\|, E (tarde) / O (mañana) | ☿♀ |
| Conjunción con el Sol | \|elong\| < 2° | ☀️ |
| Eclipse (aprox.) | llena/nueva con \|ecl_lat\| pequeña → «probable», SIN horas de contacto (etiqueta honesta) | 🌘 |
| Lluvias de meteoros | tabla anual estática (pico, ZHR, radiante) | ☄️ |
| **Lunas de Júpiter** | tránsito del satélite y **de su sombra** — ver abajo | 🔭 |

API (datos puros; la GUI pone las palabras con `self.tr()`):

```python
def events(lat_deg, lon_deg, from_date=None, days=60):
    # @return: [{"jd", "date", "kind", "icon", "objects", "mag",
    #            "sep_deg", "alt_deg", "tonight": bool, ...}] por fecha
```

### Satélites galileanos — `core/satellites.py` (familia `satellite`)

- **Qué**: tránsitos de Io/Europa/Ganimedes/Calisto sobre el disco de
  Júpiter y **tránsitos de sus sombras** (la joya amateur). Solo para la
  localización del usuario: se listan si Júpiter está sobre el horizonte
  y de noche durante el evento (`coords.py` + horizonte ya existen).
- **Cómo (v1, offline)**: elementos medios de los 4 galileanos (modelo
  clásico tipo Meeus *Astronomical Algorithms* cap. 43/44, series
  truncadas) + proyección al plano del cielo geocéntrica; detección de
  conjunción inferior → ventanas de tránsito (luna y sombra). Precisión
  documentada y **etiquetada en la UI**: «~22:10 UT, ±10 min» (Io, el
  más rápido, el más sensible). Sirve para planificar la noche, no para
  cronometrar contactos.
- **Validación**: tests unitarios contra eventos publicados (almanaques
  BAA / Sky & Telescope) con tolerancia ±15 min.
- **Saturno/Titán**: FUERA de v1 — Titán solo transita en temporadas de
  cruce del plano de anillos (última ~2025, próxima ~2040). La ayuda del
  diálogo lo dice: «Sin temporada de tránsitos de Titán hasta ~2040».
  Cero falsas promesas.
- **Afinado exacto futuro (no v1)**: JPL Horizons ofrece circunstancias
  de fenómenos de satélites topocéntricos (~1 min; confirmado en su
  manual 2026: *"eclipse circumstances for non-Earth natural
  satellites"*; IDs: Io=501, Europa=502, Ganymede=503, Callisto=504,
  Titan=606, Júpiter=599). Convención del proyecto: **spike en vivo
  antes de escribir la fuente** (patrón `core/sources/aavso.py`).

### Diálogo «Calendario del cielo» (`gui/skycal_dialog.py`, nuevo)

Modelo a seguir: `gui/journal_dialog.py`. Orden de lectura:
1. «Esta noche» — línea de impacto actual (se mueve tal cual).
2. **Próximos eventos** (60 d): lista por fecha, icono, texto llano, nota
   de visibilidad; lo de esta noche destacado.
3. **Calendario lunar**: próximas 4 fases con fecha + perigeo/apogeo +
   icono real (`gui/moon_icon.py`).
4. **Los planetas**: visibilidad esta noche (mag, altura al anochecer,
   ventana) + marcas de sus próximos eventos.
5. **Lunas de Júpiter esta semana** (familia `satellite`).
6. **El Sol ahora**: SDO/NOAA/datos/divulgación **intactos**.

Reestructura: `ui/solar_tab.ui` pasa a cargarse dentro del diálogo
(añadir los grupos nuevos; decidir en SC1 si se renombra a
`ui/sky_calendar.ui` — sin drama). Los handlers actuales
(`on_refresh_sun`, `_channel_changed`, `_fill_almanac`,
`_planets_at_dusk`, `on_render_sun_post`, `on_sky_post`, enlaces) se
re-apuntan a los widgets del diálogo (se construye una vez, perezoso, y
se reusa). `main_window.ui`: fuera `tab_solar`; menú Tools gana
`action_skycal` («Sky calendar…») junto al Diario. `_build_tabs`,
constantes `TAB_*`, `_on_main_tab_changed`, atajos Ctrl+1..4.

### Chips en Tonight

Patrón `_LinkChip` de `_show_cadence_hints` (misma cabecera). Máx. 2-3;
prioridad: **eclipse > tránsito/sombra de galileano > oposición > máx.
elongación > Luna–planeta > fase lunar > lluvia > perigeo**. Clic → abre
el diálogo en ese evento. Se recalculan al arrancar y al recalcular
Tonight.

### Fases (una = un commit)

| Fase | Entregable |
|---|---|
| **SC0** | `core/skyevents.py` + tabla lluvias + `moon(ecl_lat_deg)` + tests de invariantes + anclas reales (eclipses 2026-03-03/08-12, Perseidas) + fix oposiciones por Δλ | **Hecho** |
| **SD** | `core/satellites.py` (galileanos, tránsito + sombra, filtro local, ±10 min etiquetado) + tests contra Horizons (22 ventanas, peor 9.6 min) | **Hecho** |
| **SC1** ✓ | diálogo + contenido solar re-hogareado intacto + barra a 4 pestañas + menú + Ctrl+1..4 + tests GUI retarget (`test_campaigns_tab::test_campaigns_tab_exists` espera 5 pestañas → 4; tests de solar/skypost al diálogo) |
| **SC2** ✓ | chips en Tonight (prioridad, máx. 2-3, clic→diálogo) + tests | **Hecho** | **Hecho** |
| **SC3** | i18n ES/EN (§Reglas) + **ADR-040** (el 039 es el acordeón de la web) — sistema solar como fuente de eventos; Sun & sky → Herramientas; satélites galileanos locales ±10 min, Horizons como afinado futuro) + revisión **ADR-036** (barra a 4) + WORKFLOWS sección nueva + AGENTS.md (módulos `core/skyevents.py`, `core/satellites.py`, `gui/skycal_dialog.py`) + suite completa verde + push |

## Decisiones pactadas (2026-09-17; no re-preguntar)

1. Superficie de eventos: **chips en la cabecera de Tonight** (no filas,
   no proyectos).
2. Horizonte del calendario: **hoy + 60 días**.
3. Motor: **todo lo local**, incluidos eclipses aproximados (flag
   honesto) y lluvias (tabla estática).
4. Contenido solar heredado: **todo al diálogo, intacto**.
5. Satélites: **solo Júpiter en v1**, precisión local ±10 min etiquetada,
   Titán documentado como fuera de temporada, Horizons = opción futura.
6. Chips Tonight: máx. 2-3, lo grande primero.
7. U7 en la rama actual con push; SC2 en rama propia; **main no se
   toca** (el merge se decide con el observador más adelante).

## Reglas de la casa (AGENTS.md)

- Cabecera GPL en TODOS los `.py` nuevos (plantilla en AGENTS.md);
  código en inglés; comentarios `# @args:` / `# @return:` de voz humana.
- Toda cadena visible en la GUI pasa por `self.tr()`; pares ES/EN por
  `orbits.pick` cuando aplique.
- **Red solo desde `core/sources/` vía `core/db.py` (caché)**. El motor
  de eventos es 100 % local; lo solar usa la caché NOAA/SILSO existente.
- i18n (CONTRIBUTING):
  `pyside6-lupdate nightscribe/gui/*.py nightscribe/gui/widgets/*.py
  nightscribe/gui/ui/*.ui -ts nightscribe/gui/i18n/nightscribe_es.ts
  nightscribe/gui/i18n/nightscribe_en.ts` → rellenar (ES traducido, EN
  passthrough) → `pyside6-lrelease nightscribe/gui/i18n/nightscribe_*.ts`.
  El test `tests/unit/test_i18n.py` exige **0 unfinished**.
- Tests offscreen sin red (patrón `tests/unit/test_projects_hub.py`:
  QApplication + `theme.apply_theme` + db redirigida a tmp).
- Docs bilingües (ADR-013): ADR en `docs/adr/` (ES+EN en un fichero),
  sección nueva en `docs/WORKFLOWS.es.md` **y** `docs/WORKFLOWS.md`,
  AGENTS.md si cambia la estructura.
- Una fase = un commit; la app funcional y `pytest tests/unit` verde al
  cerrar cada fase.

## Punto de entrada para continuar

1. Leer §«Estado de la sesión» — el punto exacto de lo que falta y por
   dónde (U7 ya está hecha y comprometida, `3a38c6d`).
2. `git checkout feature/ux-projects-campaigns` (o su rama hija ya
   creada) → fix de oposiciones → tests de regresión → resto de fases
   SC0 → SD → SC1 → SC2 → SC3.
3. Al terminar: push de la rama y avisar al observador para la decisión
   de merges.
