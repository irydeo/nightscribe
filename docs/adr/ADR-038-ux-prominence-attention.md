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
