# ADR-038: Prominencia de acciones, lenguaje llano y el dashboard «Necesita tu atención» / Action prominence, plain language and the attention dashboard

**Estado / Status**: Accepted · **Fecha / Date**: 2026-09-17 · **ejecutado /
executed**: 2026-09-17 (Track UX-PC, fases/phases U1–U6 — suite unitaria
1299 verde / green)

**Ver / See**: [docs/PLANS/ux-proyectos-campanas.md](../PLANS/ux-proyectos-campanas.md)
(plan del track / track plan) · ADR-019 (hub de proyectos, enmendado aquí) ·
ADR-030 (CCDciel completa su mudanza a la pestaña Observatorio) · ADR-035 y
ADR-037 (rol de la pestaña Campañas; «Señales» pasa a «Está pasando ahora»).

## Español

**Contexto**: con los tracks V/UX/SC/JO la app era funcionalmente completa,
pero la revisión con el observador (2026-09-17) la encontró **cargada y
autoexplicativa solo con manual**: la pestaña Projects mostraba ~20 acciones
y ~20 campos a la vez (lista con 13 controles, ciclo de vida disperso en 4
zonas, básico y avanzado al mismo nivel, CCDciel mezclado con la
planificación), y Campaigns mostraba 8 botones siempre visibles con no-ops
silenciosos y jerga de desarrollador («Signals», de `signals_report`).
La app ya *sabía* lo que necesitaba el usuario (`project.next_action`,
`campaign.project_signal`, ventanas locales) — pero lo tenía enterrado.

**Decisión** (todo ello pactado con el observador el 2026-09-17):

1. **La app habla primero**. El panel derecho de Projects, sin selección, es
   el dashboard **«Necesita tu atención»**: las 3-5 cosas que piden acción
   con la razón en palabras llanas y UN botón que aterriza exactamente donde
   se actúa. Estados: calma («Todo en orden — noches claras ✨») y vacío
   (enseña que los proyectos nacen en Tonight, con salto). Su fuente es
   **`core/attention.py`**, math 100 % local (next_action + señal de campaña
   + cadencia SN + detector de eventos), aditiva — la máquina de pasos y la
   API de campañas no cambian. La narrativa de la app queda: *Tonight =
   descubrir · Projects = tu trabajo te llama · Campaigns = el esfuerzo
   colectivo*.
2. **Prominencia a tres niveles**: primario (visible) · secundario (menú
   `⋯`) · avanzado (bloque colapsable, título en lenguaje llano que dice QUÉ
   hay dentro — nunca un cajón genérico «Advanced» sin más). **Ninguna
   funcionalidad se pierde: se reubica.** Una acción = un lugar visible (los
   menús contextuales se conservan como atajo estándar).
   - Projects: la lista queda en `Search…` + estado + `Filters ▸`
     (persistente) + `＋ New project…`; el ciclo de vida se consolida en el
     menú `⋯` de la cabecera del proyecto (tags, carpetas, Close/Reopen/
     Archive/Delete); la tarjeta **Next es el centro de mando** de la
     máquina de pasos (Mark done/Skip junto a Go →; las secciones conservan
     solo un pie discreto con «Reopen step»/«Skip step»); Calibration y
     «Lo que guardaste de la sesión» arrancan colapsados; el control en vivo
     de CCDciel (rueda de filtros, Send plan del plan guardado del objetivo,
     Start capture, época de coords) completa su mudanza a la pestaña
     **Observatory** (grupo «Live capture») y Plan conserva solo un enlace
     de estado.
   - Campaigns: «Está pasando ahora» (renombrado desde «Signals») como
     titulares arriba con frases completas ⚡/⏳/👁; cada campaña es una
     **tarjeta de salud** (●●●○ N de M al día + próxima acción en palabras);
     las acciones de la seleccionada van en la cabecera del detalle
     (Edit… / Close|Reopen según estado / ⋯) con **enablement real**.
3. **Lenguaje llano (test del astrónomo)**: si hay que leer un ADR para
   entender una etiqueta, está mal. Renombres: `Signals` → «Está pasando
   ahora», `Session products` → «Lo que guardaste de la sesión»,
   `Quick-look` → «Quick analysis»/«Análisis rápido» (retirado de la GUI
   el 2026-09-23: la medición por sesión vive en el editor, ADR-044),
   `Finish` → `Close`
   (misma palabra que proyectos), `New project…` (en Campaigns) → «New
   project in this campaign…». Se quedan los términos reales de la
   comunidad: Campaign, Follow-up, Blink, HADS, PCCP.
4. **Ayuda contextual `ⓘ`**: ningún concepto se da por sabido. `ⓘ` junto a
   «New campaign…» (qué es una campaña, con ejemplo real), tooltips en las
   cinco pestañas, estados vacíos que enseñan.
5. **Filas ricas** en ambas pestañas (mismo lenguaje visual que Tonight,
   ADR-026): banda/chip del tipo, siguiente acción en palabras, puntos de
   progreso, chip «⊕ HH:MM–HH:MM esta noche» (math local con
   `planner.safe_window_for`), días desde la última actividad y **sparkline**
   de las propias medidas en SN/variables. Orden «Te necesita» por defecto:
   quien pide acción sube.

**Consecuencias**: la pestaña Projects con un proyecto abierto pasa de ~20 a
≤10 acciones visibles; Campaigns de 19 a ≤4. Los gestos no cambian (clic
selecciona, doble clic abre, clic derecho ofrece). Nada de esto toca la red
ni `core/` salvo el nuevo `attention.py` (puro, testeable offscreen).

## English

**Context**: after the V/UX/SC/JO tracks the app was functionally complete
but crowded and manual-dependent (audit of 2026-09-17 with the observer):
the Projects tab showed ~20 actions + ~20 fields at once, Campaigns showed
8 always-visible buttons with silent no-ops, and developer jargon leaked
into labels («Signals»). The app already *knew* what the user needed — it
just never said it.

**Decision** (agreed with the observer on 2026-09-17):

1. **The app speaks first**: the Projects right pane, with no selection, is
   the **"Needs your attention"** dashboard — the 3-5 things calling for
   action, each with its reason in plain words and ONE button landing
   exactly where you act. Calm and empty states included. Its source is the
   new, purely-local **`core/attention.py`** (additive; the step machine and
   the campaign API are untouched). The app's narrative reads: *Tonight =
   discover · Projects = your work calls you · Campaigns = the shared
   effort*.
2. **Three-level action prominence**: primary (visible) · secondary (`⋯`
   menus) · advanced (collapsed blocks with plain-language titles saying
   WHAT is inside). **No feature is lost — everything is relocated.** One
   action = one visible home (context menus stay as the standard shortcut).
   Projects: slim list (Search + status + `Filters ▸` + New), lifecycle in
   the header `⋯` menu, the **Next card is the step machine's command
   center** (Mark done/Skip beside Go →), Calibration and session products
   collapsed, and the live CCDciel capture completes its move to the
   **Observatory** tab. Campaigns: **"Happening now"** headlines (renamed
   from "Signals") + health cards per campaign + detail-header actions with
   real enablement.
3. **Plain language (the astronomer test)**: jargon renamed (see the Spanish
   list); community terms (Campaign, Follow-up, Blink, HADS, PCCP) stay.
4. **Contextual `ⓘ` help**: no concept is taken for granted (help button,
   tab tooltips, teaching empty states).
5. **Rich rows** in both tabs (Tonight's visual language): next action in
   words, progress dots, "up tonight HH:MM–HH:MM" chip (local maths),
   activity age, sparkline of your own measurements for SN/variables, and
   the "Needs you" order floating urgency to the top.

**Consequences**: Projects drops from ~20 to ≤10 visible actions with a
project open, Campaigns from 19 to ≤4. Gestures unchanged. No network and
no `core/` changes beyond the additive, pure `attention.py`.

**Revisión (2026-10-06): la acción del panel es un botón grande, y nada más se
abre al entrar.** El observador lo pidió con estas palabras: «al final lo que
el usuario busca es algo simple, hacer clic sobre un botón y no marearse entre
settings». El nivel primario de la decisión 2 gana peso visual, y el avanzado
arranca cerrado de verdad:

1. **Un botón héroe por pestaña**: Astrometría «Stack the sequence» y
   Fotometría «Build the sequence (comparisons)…». Ancho completo, 16 px
   negrita, radio 12, **en el tono del tipo de objeto** (`theme.KIND_COLORS`,
   el mismo que ya pinta la pestaña activa del mástil y el chip de cada fila
   de proyecto) y con el **glifo del tipo** dibujado en el color de texto del
   botón (sobre un fondo del propio tono, el glifo se perdería). Sin proyecto
   (apertura desde Herramientas) el tono es el acento de la app y no hay
   glifo: el botón es «de la app», no de un objeto.
2. **Nada más se abre**: todos los bloques colapsables arrancan **cerrados**
   (con clave NUEVA donde antes arrancaban abiertos, o un «abierto» guardado
   los mantendría abiertos contra la regla), el plan de la noche (cuántas
   observaciones y la tabla de SNR) entra en su propio bloque, y las recetas
   también. Ninguna funcionalidad se pierde: se reubica.
3. **La línea del botón**: un subtítulo de una línea bajo la acción dice lo
   que va a hacer **con los valores actuales** (tomas, observaciones, con qué
   receta se mide el brillo, si se calibra y si se comprueba), construido de
   las MISMAS fuentes que los bloques, así que no puede contradecirlos. Es lo
   que hace seguro esconder los ajustes: el observador sabe qué va a pasar sin
   abrir nada.
4. **Estados, medidos**: hover +10 % hacia blanco, pulsado −10 % (y el texto
   baja un píxel: responde), foco cambiando el COLOR del filete a blanco (el
   grosor no cambia: el botón no se mueve bajo el cursor), deshabilitado con
   el gris del tema, y **mientras corre el botón pasa a «Cancel» en estilo
   *outline*** (deja de ser la acción justo cuando ya no lo es) con la barra de
   progreso rellena en el tono del tipo.
5. **Contraste**: el texto se elige con `chip_text_for` (los ocho tonos toman
   el texto oscuro) y el degradado va **de claro arriba al tono abajo**:
   oscurecerlo hacia abajo hundiría el contraste (medido: el rojo de SN a
   −20 % cae de 4.7:1 a 3.2:1) mientras que aclarar la parte alta lo sube.
   Base 4.7-9.2:1, hover 5.3-9.8:1, pulsado 3.9-7.5:1 (AA de texto grande, que
   es lo que es: 16 px negrita). El color nunca es la única señal: glifo,
   etiqueta y subtítulo.
6. **Sin animaciones y sin colores nuevos**: la app no tiene ninguna y el
   realce es por instancia (`theme.hero_button_style`, `theme.progress_style`,
   `CollapsibleSection.setAccent`), así que el asistente, la ficha y las demás
   pestañas no se mueven.

**Revision (2026-10-06): the action of a panel is a big button, and nothing
else opens on entry.** The observer asked for it in these words: "what the user
wants is something simple, to click a button and not get lost among settings".
The primary level of decision 2 gains visual weight, and the advanced level
starts really closed:

1. **One hero button per tab**: Astrometry "Stack the sequence" and Photometry
   "Build the sequence (comparisons)…". Full width, 16 px bold, radius 12,
   **in the object kind's hue** (`theme.KIND_COLORS`, the one that already
   paints the masthead's active tab and every project row's chip) and with the
   **kind's glyph** drawn in the button's text colour (on a surface of that
   same hue the glyph would vanish). With no project (opened from Tools) the
   hue is the app's accent and there is no glyph: the button is the app's, not
   an object's.
2. **Nothing else opens**: every collapsible block starts **closed** (with a
   NEW key where they used to start open, or a stored "open" would keep them
   open against the rule), the night's plan (how many observations and the SNR
   table) gets its own block, and so do the recipes. Nothing is lost: it is
   relocated.
3. **The button's line**: a one-line subtitle under the action says what it
   will do **with the current values** (frames, observations, which recipe the
   brightness is measured with, whether the frames are calibrated and whether
   the check runs), built from the SAME sources as the blocks, so it cannot
   contradict them. That is what makes hiding the knobs safe: the observer
   knows what is about to happen without opening anything.
4. **States, measured**: hover +10% toward white, pressed −10% (and the text
   drops a pixel: it answers), focus by changing the border's COLOUR to white
   (the width never changes: the button does not move under the cursor),
   disabled in the theme's grey, and **while it runs the button becomes
   "Cancel" in an outline style** (it stops being the action exactly when it
   is not) with the progress bar filling in the kind's hue.
5. **Contrast**: the text is picked by `chip_text_for` (all eight hues take the
   dark text) and the gradient goes **from light at the top to the hue at the
   bottom**: darkening it downwards would eat the contrast (measured: the SN
   red at −20% drops from 4.7:1 to 3.2:1) while lifting the top stop raises it.
   Base 4.7-9.2:1, hover 5.3-9.8:1, pressed 3.9-7.5:1 (AA for large text, which
   is what it is: 16 px bold). Colour is never the only cue: glyph, label and
   subtitle.
6. **No animations and no new colours**: the app has none and the highlight is
   per instance (`theme.hero_button_style`, `theme.progress_style`,
   `CollapsibleSection.setAccent`), so the wizard, the object card and the
   other tabs do not move.

**Revisión (2026-10-06, segunda): todo vive en un grupo, y el grupo es una
tarjeta.** El observador afinó la regla: «TODO ha de estar agrupado por
defecto, no podemos tener nada fuera de un grupo, también los resultados; el
objetivo es tener una interfaz muy limpia y clara».

1. **Nada fuera de un grupo**, salvo dos cosas y solo dos: los **textos que
   guían sobre el botón principal** (su subtítulo, la línea del objeto y el
   texto «Haz clic en una estrella…» de Fotometría, que sube de la mitad de
   medida a debajo del botón) y las **barras de progreso** (con su línea de
   estado, que es la voz del propio botón mientras corre). El **resultado
   también va en grupos**: notas, observaciones, medida, comprobación e
   informe.
2. **Ciclo de vida por tipo de grupo**: los de **decisión** (el plan, los
   ajustes) están siempre y arrancan **cerrados**; los de **resultado**
   aparecen **con la ejecución** y arrancan **abiertos** la primera vez (son
   noticias, no decisiones), y a partir de ahí se recuerda lo que el
   observador eligió. Un grupo sin nada que decir no se enseña: «Lo que
   encontró la ejecución» con una caja vacía sería un título sobre nada.
3. **El grupo es una TARJETA**: el mismo skin que las secciones de la ficha
   del objeto (`theme.section_card_style`: fondo `C_BASE`, borde de 1 px,
   radio 10 y **espina de 3 px** en el tono apagado del tipo) con el título
   dentro **en el color del acento**, como «Parameters». Se pidió porque sin
   borde «al desplegarlo no sabes dónde termina».
4. **Sin huecos verticales**: cada columna es **un solo scroll** con un
   espaciador al final, así que todo queda agrupado arriba. El splitter de
   Fotometría repartía la altura entre dos mitades plegadas y el aire sobrante
   se acumulaba en medio; se ha ido.
5. **El botón grande, ajustado a lo ancho**: 16 px con el glifo a 18 px y
   `padding: 12px 16px`. Medido: la columna mide 380 px y el hueco útil 362; la
   etiqueta española («Construir la secuencia (comparsas)…») medía 363 px con
   el glifo a 22 y `padding` 20, **un píxel más de lo que hay**, y salía
   recortada. Con 16/18 son 351 px. El aire de fuera lo pone el contenedor.

**Revision (2026-10-06, second): everything lives in a group, and the group is a
card.** The observer sharpened the rule: "EVERYTHING must be grouped by default,
we cannot have anything outside a group, the results too; the goal is a very
clean and clear interface".

1. **Nothing outside a group**, except two things and only two: the **texts
   that guide the observer about the main button** (its subtitle, the object's
   line and Photometry's "Click a star..." line, which moves up from the
   measure half to under the button) and the **progress bars** (with their
   status line, which is the button's own voice while it runs). The **result
   is grouped too**: notes, observations, measurement, check and report.
2. **A life cycle per kind of group**: the **decision** ones (the plan, the
   settings) are always there and start **closed**; the **result** ones appear
   **with the run** and start **open** the first time (they are news, not
   decisions), and from then on the observer's choice is remembered. A group
   with nothing to say is not shown: "What the run found" with an empty box
   would be a title about nothing.
3. **The group is a CARD**: the same skin as the object card's sections
   (`theme.section_card_style`: a `C_BASE` fill, a 1 px border, a 10 px radius
   and a **3 px spine** in the quiet composite of the kind's hue) with the
   title inside **in the accent colour**, like "Parameters". It was asked for
   because without a border "when you expand it you cannot tell where it ends".
4. **No vertical gaps**: each column is **one scroll area** with a trailing
   stretch, so everything stays at the top. Photometry's splitter handed each
   folded half a share of the height and the spare air collected in the middle;
   it is gone.
5. **The big button, fitted to the width**: 16 px with the glyph at 18 px and
   `padding: 12px 16px`. Measured: the column is 380 px wide and the useful
   slot 362; the Spanish label ("Construir la secuencia (comparsas)…") measured
   363 px with the glyph at 22 and `padding` 20, **one pixel more than there
   is**, and came out clipped. With 16/18 it is 351 px. The outside air comes
   from its container.

**Revisión (2026-10-06): los grupos nacen cerrados y avisan.** El panel de
Astrometría y el de Fotometría comparten una gramática de grupos plegables
(`CollapsibleSection`). Se pidió que **todos** los grupos estén cerrados por
defecto, también los de resultado, y que un grupo que tenga algo dentro lo
diga sin necesidad de abrirlo. Así queda:

- **Cerrado por defecto, siempre**: la elección del observador se recuerda (la
  clave de config), pero el estado inicial es cerrado. Donde el defecto se
  invierte se usa una **clave nueva** (`..._open2`), porque un «abierto»
  guardado por el diseño anterior lo dejaría abierto contra la regla nueva.
- **Aviso común** (`CollapsibleSection.setNotice(texto, level)`, el mismo
  widget para los dos paneles): un chip en la cabecera con la noticia (un
  número, «nuevo», «⚠») y, cuando es un problema, el **título en color de
  aviso**. Abrir el grupo **consume** el aviso: un aviso que sigue ahí
  después de mirarlo es un aviso que miente. Con el grupo abierto no se pinta
  (lo estás viendo).
- **Mensajes fuera de grupo, bajo el botón**: el panel de Astrometría tenía el
  párrafo del run en una etiqueta que crecía hasta 204 px de una columna de
  380 y empujaba los grupos fuera de la pantalla. Ahora hay **una línea
  elidida** bajo el botón héroe (texto completo en el tooltip y en la línea
  única de la ventana, U4), y el detalle vive en su grupo, que es donde tiene
  sitio y scroll. El progreso sube con ella.
- **Un solo dueño del escenario sigue siendo el panel**: el aviso no cambia
  quién responde a los clics.

**Revision (2026-10-06): the groups are born closed, and they announce.**
The Astrometry and the Photometry panels share one grammar of collapsible
groups (`CollapsibleSection`). Asked for: **every** group closed by default,
the result ones too, and a group that holds something must say so without
being opened. This is how it lands:

- **Closed by default, always**: the observer's own choice is remembered (the
  config key), but the initial state is closed. Where the default is reversed a
  **fresh key** is used (`..._open2`), because an "open" stored by the previous
  design would keep it open against the new rule.
- **One notice, shared** (`CollapsibleSection.setNotice(text, level)`, the same
  widget for both panels): a chip on the header with the news (a number, "new",
  "⚠") and, when it is a problem, the **title in the alert colour**. Opening the
  group **consumes** the notice: a notice that stays after you looked is a
  notice that lies. With the group open it is not painted (you are looking at
  it).
- **Messages outside a group, under the button**: the Astrometry panel kept the
  run's paragraph in a label that grew to 204 px of a 380 px column and pushed
  the groups off the screen. There is now **one elided line** under the hero
  button (the whole text in the tooltip and in the window's single line, U4),
  and the detail lives in its own group, where it has room and a scroll. The
  progress bar travels with it.
- **The stage still has one owner**: the notice does not change who answers the
  clicks.
