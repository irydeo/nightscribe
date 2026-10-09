# ADR-075: La IA como asistente no invasivo: el brief, el redactor y el endpoint

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-09

## Español

**Contexto**: el paso Publicar era pobre porque solo veía la ficha del objeto
enriquecido (el gancho, unos bullets y las etiquetas), nunca el trabajo del
observador: las visitas, las magnitudes medidas, el veredicto de la campaña, el
período, la profundidad de un tránsito, el residuo de la astrometría. Y la app
tiene todo eso. La tentación es meter un modelo de lenguaje a "escribirlo todo",
pero el valor del proyecto es justo lo contrario: datos medidos y explicados,
con el modelo de error intacto (ADR-063) y sin una cifra sin su porqué
(ADR-058). Un asistente que inventara, midiera o decidiera tiraría ese valor.

**Decisión**:

1. **Un motor, agnóstico de proveedor.** Un único cliente habla el formato de
   chat-completions de OpenAI (`core/sources/llm.py`): cubre los servicios
   gratuitos de la nube (OpenRouter, Groq, Google AI Studio...) **y** un servidor
   local (Ollama, LM Studio) cambiando solo la URL base. Sin atarse a un
   proveedor y con la vía local para no sacar nada de la máquina. La clave nunca
   se registra: solo viaja en la cabecera `Authorization`.
2. **El brief es la única fuente.** `core/object_brief.py` reúne, en una ficha
   factual y *explicada*, todo lo que la app sabe del proyecto: identidad y
   tipo, los parámetros del objeto **con su porqué** (los mismos renglones que
   la ficha, `orbits.explain_*`, para que el brief no pueda discrepar de ella),
   la noche planificada, las visitas, los puntos medidos y el veredicto de la
   campaña, y los ficheros que cuelgan del proyecto. Sin red y sin Qt: se prueba
   sin conexión.
3. **El redactor solo frasea.** `core/writer.py` construye el prompt (el brief +
   las reglas) y pide un JSON `{es, en, tweet}`. Las reglas son el contrato:
   solo los hechos del dossier, nunca una cifra ni una clasificación inventada,
   cada tipo o cifra con su significado (ADR-058), las dos lenguas diciendo lo
   mismo, y el tuit dentro de 280 caracteres. Un JSON ilegible es un fallo
   limpio, no medio post.
4. **La plantilla se queda.** `core/post.py` sigue siendo la respuesta sin
   conexión y el respaldo: si la IA está apagada o falla, el post se escribe con
   la plantilla y se dice. La IA nunca vacía las cajas que el observador ya
   estaba editando.
5. **Apagada por defecto y por tarea.** Sin endpoint configurado la app es
   exactamente la de antes; el botón de IA ni se ofrece. Se invoca, no se
   dispara; nada llama a la red hasta que el observador pulsa. El interruptor
   `ai_enabled` («Use a language model») manda: con él apagado, ninguna
   superficie de IA se ofrece (el menú, el botón del editor y Publicar quedan
   deshabilitados con su motivo), aunque haya endpoint.
6. **La carta de no invasividad**, que el asistente heredará:
   - **Apagada por defecto**: sin endpoint, la app es la de siempre.
   - **Se invoca, no se dispara**: siempre con un botón; nunca sola.
   - **Nunca escribe** en la base de datos ni en los ficheros: produce texto
     que el observador copia o aplica.
   - **No toca la medida, el planner, la clasificación ni el diseño.**
   - **Siempre marcada como IA**, con procedencia: nunca se confunde con un
     dato medido.
   - **Presentada como experimental**: el menú, la ventana del asistente, los
     botones de IA y Ajustes lo dicen con todas las letras; la plantilla sin
     conexión es la respuesta estable.
   - **Un único sitio** para el asistente, abierto por el observador y
     recordado; sin burbujas ni sugerencias automáticas.
   - **La conversación es efímera** (en memoria, con "Limpiar").

**Consecuencias**:

- Publicar pasa a contar la observación de verdad, con la voz del observador por
  encima; el borrador se revisa antes de publicar.
- La misma ficha servirá al **asistente conversacional** (la siguiente fase):
  una ventana no modal con ámbitos ("este objeto" desde el brief, "la app"
  desde los documentos) donde la app calcula y la IA explica; nunca decide.
- El coste de un proveedor de nube y el hardware de uno local son del
  observador; la privacidad se decide eligiendo la URL.
- Guardián: `tests/unit/test_object_brief.py` (la ficha lleva el trabajo propio
  y cada cifra su porqué), `test_writer.py` (el prompt y el JSON tolerante),
  `test_llm_source.py` (la URL, la cabecera y que la clave no se filtra en un
  error), `test_settings_tabs.py` (los campos y el preset), `test_post_ai.py`
  (el panel: el fallo se dice, el texto propio no se tira) y `test_ai_enabled.py`
  (el interruptor maestro cierra todas las superficies).

**Enmienda (2026-10-09, el asistente conversacional).** La misma ficha y el
mismo cliente alimentan una ventana no modal con **tres ámbitos**:

1. **Este objeto**: el brief del proyecto abierto (se enriquece en el hilo,
   nunca en el de la interfaz).
2. **La app**: `core/docs_index.py`, un índice local por palabras sobre
   `docs/user` y los ADR, troceados por secciones y por idioma. Sin embeddings
   ni red en esta versión.
3. **El editor**: el estado del editor (qué placa, qué pestaña, si tiene WCS)
   más los documentos. La app calcula el estado y, cuando el siguiente paso no
   admite duda (no hay placa), lo dice; la IA lo explica.

La ventana (`gui/assistant_window.py`) lleva un selector de ámbito, la
conversación, la entrada y, bajo cada respuesta, **las fuentes que se
inyectaron** (no se le pide al modelo que las cite: se muestran las que de
verdad se le dieron). La historia vive en la ventana y se olvida al cerrarla.
Entra por el menú Ayuda (ámbito app, con el objeto del proyecto abierto) y por
un botón «?» en la barra del editor (ámbito editor). El modelo se puede elegir
de una lista: `llm.list_models` pregunta al endpoint (`GET {base}/models`) y un
botón «Listar modelos» rellena el combo editable con los nombres exactos que
devuelva (los de un servidor local incluidos). Guardián:
`test_docs_index.py`, `test_assistant.py` y `test_assistant_window.py`.

## English

**Context**: the Publish step was poor because it only saw the enriched
catalogue entry (the hook, a few bullets and the hashtags), never the
observer's own work: the visits, the measured magnitudes, the campaign verdict,
the period, a transit's depth, the astrometry residual. And the app has all of
it. The temptation is to drop a language model in to "write it all", but the
project's value is the opposite: measured, explained data, with the error model
intact (ADR-063) and no figure without its why (ADR-058). An assistant that
invented, measured or decided would throw that value away.

**Decision**:

1. **One engine, provider-agnostic.** A single client speaks OpenAI's
   chat-completions shape (`core/sources/llm.py`): it covers the free cloud
   services (OpenRouter, Groq, Google AI Studio...) **and** a local server
   (Ollama, LM Studio) by changing only the base URL. No vendor lock, and the
   local route keeps everything on the machine. The key is never logged: it
   only rides in the `Authorization` header.
2. **The brief is the single source.** `core/object_brief.py` gathers, in a
   factual and *explained* fact sheet, everything the app knows about the
   project: identity and type, the object's parameters **with their why** (the
   very same rows the object card shows, `orbits.explain_*`, so the brief
   cannot disagree with it), the planned night, the visits, the measured points
   and the campaign verdict, and the files hanging from the project. No network
   and no Qt: it is testable offline.
3. **The writer only phrases.** `core/writer.py` builds the prompt (the brief +
   the rules) and asks for a JSON `{es, en, tweet}`. The rules are the
   contract: only the dossier's facts, never an invented figure or
   classification, every type or figure with its meaning (ADR-058), the two
   languages saying the same thing, and the tweet within 280 characters. An
   unreadable JSON is a clean failure, not half a post.
4. **The template stays.** `core/post.py` remains the offline answer and the
   fallback: if the AI is off or fails, the post is written with the template
   and it says so. The AI never empties the boxes the observer is editing.
5. **Off by default, and per task.** Without a configured endpoint the app is
   exactly as before; the AI button is not even offered. It is invoked, not
   triggered; nothing calls the network until the observer clicks. The
   `ai_enabled` switch ("Use a language model") is authoritative: with it off,
   no AI surface is offered (the menu, the editor button and Publish stay
   disabled with their reason), even if an endpoint is set.
6. **The non-invasiveness charter**, which the assistant will inherit:
   - **Off by default**: without an endpoint, the app is the usual one.
   - **Invoked, not triggered**: always with a button; never on its own.
   - **Never writes** to the database or to the files: it produces text the
     observer copies or applies.
   - **Does not touch** the measurement, the planner, the classification or the
     design.
   - **Always marked as AI**, with provenance: never confused with measured
     data.
   - **Presented as experimental**: the menu, the assistant window, the AI
     buttons and Settings say so in plain words; the offline template is the
     stable answer.
   - **A single place** for the assistant, opened by the observer and
     remembered; no bubbles, no automatic suggestions.
   - **The conversation is ephemeral** (in memory, with "Clear").

**Consequences**:

- Publish now tells the observation for real, with the observer's voice on top;
  the draft is reviewed before publishing.
- The same fact sheet will serve the **conversational assistant** (the next
  phase): a non-modal window with scopes ("this object" from the brief, "the
  app" from the documents) where the app computes and the AI explains; it never
  decides.
- The cost of a cloud provider and the hardware of a local one are the
  observer's; privacy is decided by choosing the URL.
- Guard: `tests/unit/test_object_brief.py` (the sheet carries the observer's own
  work and every figure its why), `test_writer.py` (the prompt and the tolerant
  JSON), `test_llm_source.py` (the URL, the header and that the key never leaks
  into an error), `test_settings_tabs.py` (the fields and the preset),
  `test_post_ai.py` (the panel: a failure is said, the observer's text is not
  thrown away) and `test_ai_enabled.py` (the master switch closes every
  surface).

**Amendment (2026-10-09, the conversational assistant).** The same fact sheet
and the same client feed a non-modal window with **three scopes**:

1. **This object**: the open project's brief (enriched in the worker thread,
   never on the UI one).
2. **The app**: `core/docs_index.py`, a local keyword index over `docs/user`
   and the ADRs, chunked by section and by language. No embeddings, no network
   in this version.
3. **The editor**: the editor's state (which plate, which tab, whether it has a
   WCS) plus the documents. The app computes the state and, when the next step
   admits no doubt (no plate), says it; the AI explains it.

The window (`gui/assistant_window.py`) carries a scope selector, the
conversation, the input and, under each answer, **the sources that were
injected** (the model is not asked to cite them: what it was actually given is
shown). The history lives in the window and is forgotten on close. It is
reached from the Help menu (app scope, with the open project's object) and from
a "?" button in the editor's bar (editor scope). The model can be picked from
a list: `llm.list_models` asks the endpoint (`GET {base}/models`) and a "List
models" button fills the editable combo with the exact names it returns (a
local server's included). Guard: `test_docs_index.py`, `test_assistant.py` and
`test_assistant_window.py`.
