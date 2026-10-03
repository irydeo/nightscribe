# ADR-056: Navegación con historial, migas y atajos / Navigation with history, breadcrumbs and shortcuts

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-01 ·
**ejecutado / executed**: 2026-10-01 (suite unitaria green, i18n 0
unfinished)

**Ver / See**: ADR-055 (el shell de Interfaz 1.0; esta ADR le añade el
historial) · ADR-019 (UX centrada en proyectos) · ADR-038 (la app habla
primero) · ADR-005 (los `.ui`; la barra de navegación es Designer)

## Español

**Contexto.** Interfaz 1.0 dejó seis pantallas (Home, Tonight, Campañas,
Detalle, Bienvenida, UFE) y un drawer, pero **cada pantalla decidía a dónde
ir** y no existía un «atrás» global: desde el detalle de un proyecto solo
se volvía al hub por atajo (Ctrl+1) o abriendo el drawer (que no tiene
entrada «Home»); desde un miembro de campaña, el retorno era inexistente;
un chip de cadencia te llevaba a Análisis sin vuelta. El usuario pidió «que
sea posible regresar al punto anterior siempre» y una navegación fluida.

**Decisión** (pactada con el observador, 2026-10-01):

1. **Una ubicación es un estado, no solo una vista**: `(vista, proyecto,
   pestaña, campaña)`. Así «atrás» restaura el proyecto **y su pestaña**,
   no solo la pantalla.
2. **Pila de historial** (`_nav_back` / `_nav_fwd`) con un único punto de
   entrada, `navigate(vista, pid, tab, cid, replace=False)`. Toda
   navegación apila la ubicación actual y limpia la de adelante; aplicar
   historial **no** apila (`_navigating` evita el bucle). `_goto_tab` queda
   como *setter* de bajo nivel para refrescos internos.
3. **Barra de navegación** en el chrome del shell (ADR-005):
   `[←] [→] [⌂] [ⓘ]` + **migas clicables** `Home › proyecto › pestaña`. Los
   botones se habilitan según las pilas; Home (raíz) deja «Atrás»
   deshabilitado.
4. **Atajos**: `Alt+←` atrás, `Alt+→` adelante, `Alt+Home`, `Ctrl+1..3`
   (ya existían) y los **botones laterales del ratón** (filtro de eventos
   de aplicación). `Esc` cierra el drawer; «Atrás» con el drawer abierto
   lo cierra primero.
5. **Crear un proyecto reemplaza Tonight**: al terminar la tarea, «Atrás»
   vuelve al hub, no al buscador (`replace=True`). Una selección de
   pestaña sí apila, así que «Atrás» recorre las pestañas por las que
   pasaste.
6. **Bienvenida es una entrada permanente** (barra, menú Ayuda y drawer).
   Abrirla a mano **no** re-arma el gate ni sella `app_version`; «Got it»
   solo vuelve atrás. El gate real (actualización pendiente sin confirmar)
   sigue bloqueando «Atrás».
7. **Robustez**: un proyecto borrado que quedó en el historial se salta y
   se cae a Home; los refrescos internos (`on_refresh_projects`,
   `_show_dashboard`) no ensucian el historial.

**Cabo suelto arreglado aquí**: `action_log` («Open the log…») estaba
cableado pero **no aparecía en ningún menú**; ahora vive en **Ayuda**,
junto a Documentación, Acerca de y Fuentes.

**Consecuencias.** Cualquier pantalla tiene retorno (botón, atajo o ratón);
las migas dicen dónde estás y permiten saltar; el drawer sigue siendo el
conmutador rápido y no entra en el historial. El coste es un estado de
navegación que hay que mantener: cada nuevo punto de entrada debe llamar a
`navigate`, y `_goto_tab` no debe usarse para navegación de usuario.

## English

**Context.** Interfaz 1.0 left six screens (Home, Tonight, Campaigns,
Detail, Welcome, UFE) and a drawer, but **each screen decided where to go**
and there was no global "back": from a project detail you returned to the
hub only by shortcut (Ctrl+1) or by opening the drawer (which has no
"Home" entry); from a campaign member the return did not exist; a cadence
chip took you to Analysis with no way back.

**Decision** (agreed with the observer, 2026-10-01):

1. **A location is a state, not just a view**: `(view, project, tab,
   campaign)`, so "back" restores the project **and its tab**.
2. **History stacks** (`_nav_back` / `_nav_fwd`) behind one entry point,
   `navigate(view, pid, tab, cid, replace=False)`. Applying history never
   records (`_navigating`). `_goto_tab` stays a low-level setter for
   internal refreshes.
3. **Navigation bar** in the shell chrome: `[←] [→] [⌂] [ⓘ]` plus
   clickable **breadcrumbs**. Home (the root) leaves "Back" disabled.
4. **Shortcuts**: `Alt+←`, `Alt+→`, `Alt+Home`, `Ctrl+1..3`, and the mouse
   side buttons (an application event filter). `Esc` closes the drawer;
   "Back" closes it first.
5. **Creating a project replaces Tonight**: "Back" returns to the hub. A
   tab pick does stack, so "Back" walks the tabs you visited.
6. **Welcome is a permanent entry** (bar, Help menu and drawer). Opening
   it by hand does not re-arm the gate nor seal `app_version`.
7. **Robustness**: a deleted project left in history is skipped to Home;
   internal refreshes do not dirty the history.

**Loose end fixed here**: `action_log` was wired but **in no menu**; it now
lives in **Help**.
