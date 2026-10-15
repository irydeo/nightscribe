# ADR-092: Ajustes amables: lo común primero, lo avanzado tras una puerta / Friendly settings: the common first, the advanced behind one door

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-15
**Ver / See**: ADR-005 (la interfaz en los `.ui`), ADR-028 (la ayuda bajo el
campo), ADR-058 (nada sin explicación), ADR-071 (la arquitectura de Ajustes
que aquí se revisa), ADR-074 (el catálogo de cámaras), ADR-075 (la IA),
ADR-081 (backends de observatorio), ADR-084 (start and follow)

## Español

**Contexto**: ADR-071 ordenó Ajustes por tarea (seis categorías, raíl,
buscador) y sus revisiones de 2026-10-13 terminaron con **todo visible**: 27
grupos y unos 110 ajustes sin ninguna jerarquía de uso. El resultado,
reportado al usarlo, es que el diálogo abruma:

1. **Todo habla al mismo volumen.** Quien entra a poner su código MPC ve con
   el mismo peso el barrido de velocidad de la astrometría o el margen de
   recorte en píxeles: mandos que tocan tres personas, una vez, y con
   valores por defecto saneados.
2. **Measurement era un muro de 11 grupos** seguidos, justo en la página que
   más se visita.
3. **Observatory era un solo grupo de 18 filas** que mezclaba tres
   naturalezas: dónde estás (coordenadas, cielo), quién eres (observador,
   email) y cómo firmas los reportes MPC (telescopio, tipo, f/, comentario),
   más dos checkboxes de guiado que son comportamiento de sesión, no un
   dato del sitio.
4. **El raíl era solo iconos**: seis pictogramas que había que sobrevolar
   para aprender. La propia app, en la barra del editor FITS, muestra
   «icono + texto» por defecto y ofrece «solo iconos» como opción experta;
   Ajustes no predicaba con el ejemplo.

La lección de 2026-10-13 sigue viva: plegar **cada grupo** produjo una pared
de títulos idénticos (monótona, y fea al plegar). Lo que falló fue plegar
**por grupo**; lo que falta es plegar **por nivel de experiencia**.

**Decisión**: «lo común primero, lo avanzado tras una puerta». No se quita
**nada**: mismo diálogo, mismas claves, mismos widgets; cambia la jerarquía.

1. **Una puerta «Advanced» por página** (`settings_view.make_advanced_doors`):
   los grupos expertos de una página se mudan, en su orden, a una única
   sección plegable al pie de la página, cerrada por defecto. La pertenencia
   es **declarativa** (`settings_spec.ADVANCED_GROUPS`, por objectName), así
   ningún grupo entra o sale de la puerta sin revisar esa línea, y un test
   la recorre en las dos direcciones. La puerta no es un `QGroupBox` a
   propósito: el índice del buscador recorre grupos, y una puerta que lo
   fuese se indexaría (y se ocultaría) a sí misma. El chevrón habla el
   idioma de la app (el mismo ▸/▾ del toggle «Filters» de Tonight).
   - **Equipment**: el perfil medido de la cámara (full well, linealidad,
     ganancia, ruido de lectura, dark, readout, exposición máxima de
     trabajo) pasa a su propio grupo tras la puerta; el preset ya lo rellena
     (ADR-071 ya quiso plegarlo) y la escala de placa en vivo se queda
     visible, con el preset, el píxel y la focal.
   - **Measurement**: quedan visibles Fotometría (el método), Plate solver
     y Calibration masters; tras la puerta van la fotometría avanzada, los
     cinco grupos de astrometría (incluidos los umbrales SNR de detección y
     de envío: el listón del MPC ya viene puesto), Find_Orb y EXOTIC. De 11
     grupos visibles a 3.
   - **Integrations**: la IA (opcional y experimental, ADR-075) va tras la
     puerta; el software de observatorio y las claves API se quedan.
   - **Observatory, Observing, Interface**: sin puerta; se arreglan
     dividiendo (punto 3) o ya son cortas.
2. **El buscador abre la puerta solo**: una coincidencia detrás de una
   puerta la despliega (un resultado de búsqueda tiene que estar visible,
   no plegado), y al vaciar la caja cada puerta vuelve al estado en que el
   observador la dejó (`user_open`): el buscador la toma prestada, no la
   roba.
3. **Observatory se divide en dos grupos**: «Site» (código MPC, nombre,
   coordenadas, altura, código AAVSO, brillo del cielo) y «Observer and
   reports» (observador, medidor, email, telescopio, tipo, f/, cámara,
   comentario MPC). Los dos checkboxes de guiado del follow run
   (`follow_guide`, `follow_calibrate`, ADR-084) se mudan a **Observing →
   Session defaults**: los lee el paso Captura al arrancar un run; son
   comportamiento de sesión, no una propiedad del sitio.
4. **El raíl muestra icono + nombre** (`ListMode`, 150 px): las seis
   categorías se leen sin sobrevolar nada, coherente con la barra del
   editor FITS. Los iconos (par apagado/activo) y los tooltips se quedan.
5. **Toques de amabilidad**: el placeholder del buscador enseña ejemplos
   («Search: gain, moon, api key…») y la intro de Observatory dice que se
   configura una vez.

**Consecuencias**:

- De 27 grupos siempre visibles a **14 visibles por defecto**: Observatory 2,
  Equipment 2 (+1 tras la puerta), Observing 6, Measurement 3 (+8),
  Integrations 3-4 (+1), Interface 4.
- Ninguna clave de config cambia de nombre, significado o valor por defecto;
  la tabla `FIELDS` solo reordena comentarios. Los `objectName` existentes no
  cambian, así que los tests de masters, storage, horizonte y EXOTIC pasan
  intactos.
- `open_settings_page("page_measurement")` (el botón «Calibration settings…»
  del editor) sigue aterrizando en la página de la biblioteca, que es común.
- Tests: `test_settings_tabs.py` actualiza el raíl (icono + nombre), añade
  `grp_reports` y `grp_camera_profile`, mueve los checkboxes de guiado a
  Observing y estrena tres guardas de la puerta (toda grupo declarado
  avanzado vive tras ella y empieza cerrada; el buscador la abre y la
  devuelve; la elección del observador sobrevive a una búsqueda). La guarda
  de las ayudas y la de i18n siguen vigentes.
- Guía: `docs/user/10-settings.md` y su versión en español se reescriben
  con el reparto común/avanzado y la web se regenera.
- i18n: las cadenas nuevas («Advanced», «Observer and reports», «Camera:
  measured profile», el placeholder y la intro) pasan por `tools/i18n.py`.

**Escopado**: no se quita ni se añade ningún ajuste; no cambia el flujo
Save/Cancel; el gate de backend CCDciel/NINA no cambia; la Bienvenida no se
toca. Un resumen de «qué falta por configurar» o un modo «solo lo tocado»
quedan fuera a propósito: el buscador ya es esa puerta.

## English

**Context**: ADR-071 organized Settings by task (six categories, a rail, a
search) and its 2026-10-13 reviews ended with **everything visible**: 27
groups and about 110 settings with no hierarchy of use. The reported result
is that the dialog overwhelms:

1. **Everything speaks at the same volume.** Whoever enters to set their MPC
   code sees, with the same weight, the astrometry velocity sweep or the
   cutout margin in pixels: controls three people touch, once, with sane
   defaults.
2. **Measurement was a wall of 11 groups** in a row, on the most visited
   page.
3. **Observatory was a single 18-row group** mixing three natures: where you
   are (coordinates, sky), who you are (observer, email) and how you sign
   the MPC reports (telescope, type, f/, comment), plus two guider
   checkboxes that are session behaviour, not a site fact.
4. **The rail was icon-only**: six glyphs that had to be hovered to be
   learned. The app itself, on the FITS editor's bar, shows "icon + text"
   by default and offers "icons only" as the expert option; Settings did
   not practise what it preached.

The 2026-10-13 lesson stays alive: folding **every group** produced a wall
of identical titles (monotonous, and ugly when folded). What failed was
folding **by group**; what was missing is folding **by experience level**.

**Decision**: "the common first, the advanced behind one door". **Nothing**
is removed: same dialog, same keys, same widgets; the hierarchy changes.

1. **One "Advanced" door per page** (`settings_view.make_advanced_doors`):
   a page's expert groups move, in their order, into a single collapsible
   section at the bottom of the page, closed by default. Membership is
   **declarative** (`settings_spec.ADVANCED_GROUPS`, by objectName), so no
   group enters or leaves the door without that line being reviewed, and a
   test walks it both ways. The door is not a `QGroupBox` on purpose: the
   search index walks the groups, and a door that were one would index (and
   hide) itself. The chevron speaks the app's idiom (the same ▸/▾ as
   Tonight's "Filters" toggle).
   - **Equipment**: the camera's measured profile (full well, linearity,
     gain, read noise, dark, readout, working max exposure) moves to its own
     group behind the door; the preset already fills it (ADR-071 already
     wanted it folded) and the live plate scale stays visible, with the
     preset, the pixel and the focal length.
   - **Measurement**: Photometry (the method), Plate solver and Calibration
     masters stay visible; behind the door go the advanced photometry, the
     five astrometry groups (including the detection and submission SNR
     gates: the MPC's bar ships set), Find_Orb and EXOTIC. From 11 visible
     groups to 3.
   - **Integrations**: the AI (optional and experimental, ADR-075) goes
     behind the door; the observatory software and the API keys stay.
   - **Observatory, Observing, Interface**: no door; they are fixed by
     splitting (point 3) or are already short.
2. **The search opens the door by itself**: a match behind a door unfolds it
   (a search hit must be visible, not folded away), and clearing the box
   hands every door back to the state the observer left it in
   (`user_open`): the search borrows the door, it does not steal it.
3. **Observatory splits into two groups**: "Site" (MPC code, name,
   coordinates, height, AAVSO code, sky brightness) and "Observer and
   reports" (observer, measurer, email, telescope, type, f/, camera, MPC
   comment). The follow run's two guider checkboxes (`follow_guide`,
   `follow_calibrate`, ADR-084) move to **Observing → Session defaults**:
   the Capture step reads them when a run starts; they are session
   behaviour, not a property of the site.
4. **The rail shows icon + name** (`ListMode`, 150 px): the six categories
   read without hovering anything, consistent with the FITS editor's bar.
   The icons (the dim/active pair) and the tooltips stay.
5. **Friendliness touches**: the search placeholder teaches examples
   ("Search: gain, moon, api key…") and the Observatory intro says it is
   set once.

**Consequences**:

- From 27 always-visible groups to **14 visible by default**: Observatory 2,
  Equipment 2 (+1 behind the door), Observing 6, Measurement 3 (+8),
  Integrations 3-4 (+1), Interface 4.
- No config key changes its name, meaning or default; the `FIELDS` table
  only reorders comments. Existing `objectName`s do not change, so the
  masters, storage, horizon and EXOTIC tests pass untouched.
- `open_settings_page("page_measurement")` (the editor's "Calibration
  settings…" button) still lands on the library's page, which is common.
- Tests: `test_settings_tabs.py` updates the rail (icon + name), adds
  `grp_reports` and `grp_camera_profile`, moves the guider checkboxes to
  Observing and introduces three guards for the door (every group declared
  advanced lives behind it and starts closed; the search opens it and hands
  it back; the observer's choice survives a search). The help-text guard
  and the i18n one stay in force.
- Guide: `docs/user/10-settings.md` and its Spanish version are rewritten
  with the common/advanced split and the website is regenerated.
- i18n: the new strings ("Advanced", "Observer and reports", "Camera:
  measured profile", the placeholder and the intro) go through
  `tools/i18n.py`.

**Scope**: no setting is removed or added; the Save/Cancel flow does not
change; the CCDciel/NINA backend gate does not change; the Welcome is
untouched. A "what is left to configure" summary or a "only what I touched"
mode are left out on purpose: the search already is that door.
