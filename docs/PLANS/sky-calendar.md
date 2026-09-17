# Plan — Track SC2 «Calendario del cielo» + U7 (cierre UX-PC) (2026-09-17)

> **Pendiente de ejecutar** (plan escrito 2026-09-17, autocontenido: lo
> puede retomar otro agente o persona sin más contexto). Todas las
> decisiones ya están pactadas con el observador — **no re-preguntarlas**,
> solo ejecutar. Ver §«Decisiones pactadas» y §«Reglas de la casa».

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

## Track SC2 — el sistema solar como fuente de eventos (ADR-039)

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
| Oposición (exteriores) | mínimo de \|elong−180°\| < ~1.5° | 🔴 |
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
| **SC0** | `core/skyevents.py` + tabla lluvias + `moon(ecl_lat_deg)` + tests de invariantes (fases ~7.38 d; perigeo/apogeo alternan ~13.9 d; oposiciones solo exteriores; elong. ≤28°/48°) + anclas reales verificadas al implementar (eclipse lunar total 2026-03-03 ±1 d; Perseidas 12-13 ago) |
| **SD** | `core/satellites.py` (galileanos, tránsito + sombra, filtro local, ±10 min etiquetado) + tests contra almanaques publicados |
| **SC1** | diálogo + contenido solar re-hogareado intacto + barra a 4 pestañas + menú + Ctrl+1..4 + tests GUI retarget (`test_campaigns_tab::test_campaigns_tab_exists` espera 5 pestañas → 4; tests de solar/skypost al diálogo) |
| **SC2** | chips en Tonight (prioridad, máx. 2-3, clic→diálogo) + tests |
| **SC3** | i18n ES/EN (§Reglas) + **ADR-039** (sistema solar como fuente de eventos; Sun & sky → Herramientas; satélites galileanos locales ±10 min, Horizons como afinado futuro) + revisión **ADR-036** (barra a 4) + WORKFLOWS sección nueva + AGENTS.md (módulos `core/skyevents.py`, `core/satellites.py`, `gui/skycal_dialog.py`) + suite completa verde + push |

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

1. Leer este documento entero.
2. `git checkout feature/ux-projects-campaigns && git pull` → ejecutar
   **U7** → commit + push.
3. `git checkout -b feature/sky-calendar` → fases SC0 → SD → SC1 → SC2 →
   SC3.
4. Al terminar: push de la rama y avisar al observador para la decisión
   de merges.
