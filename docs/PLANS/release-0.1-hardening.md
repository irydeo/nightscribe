# Plan: endurecimiento para la primera release pública 0.1

*Plan de trabajo de la auditoría previa a la salida / Pre-release audit working plan.*

- **Rama**: `release/v0.1-hardening` (renombrada desde `docs/tutorial-videos`, commit de referencia `94252a9`).
- **Alcance**: los hallazgos de la auditoría a cuatro roles (QA, UX, documentación y
  desarrollador) y el camino acordado hasta la primera versión pública, la **0.1.0**.
- **Estado**: auditoría cerrada; acuerdo firmado entre los cuatro roles. Las fases P0 y P1
  están listas para ejecutarse. Quedan dos decisiones de alcance pendientes del autor
  (sección 7).
- **Estilo**: este documento sigue las reglas de la casa (escribimos con «:», «,» y «;»; la
  semirraya «–» solo para rangos numéricos, nunca como raya).

---

## 1. Contexto y método

La aplicación llevaba hasta ahora en circuito cerrado. Antes de abrirla se hizo una auditoría
en paralelo con cuatro roles, cada uno con su dominio de veto, sobre el commit `94252a9`:

| Rol | Persigue | Veto |
|---|---|---|
| **QA / Tester** | Estabilidad, que haga lo que dice, sin pérdida de datos | Crash, pérdida o corrupción de datos, resultado silenciosamente erróneo |
| **UX** | Intuitivo, fácil, atractivo | Flujos que no se completan sin leer el manual |
| **Documentación** | Manual claro, de lo general a lo particular, con profundidad opcional | Promesas incumplidas y procedimientos que exigen leer el código |
| **Desarrollador** | Entender el software para evolucionarlo | Cambios razonables que obligan a tocar muchas capas |

Los cuatro informes se cruzaron en una matriz única (sección 3) y los desacuerdos se
resolvieron con una escalera de prioridad acordada de antemano (sección 4):

> pérdida de datos y seguridad > estabilidad (crash) > corrección científica > comprensibilidad
> UX > documentación > comodidad del desarrollador.

**Cada hallazgo lleva un ID** (`QA-nn`, `UX-nn`, `DOC-nn`, `DEV-nn`) que se conserva en este
documento para poder trazar de dónde salió. Donde varios roles vieron lo mismo, hay una fila
y se anotan las procedencias.

---

## 2. Veredicto

NightScribe está **técnicamente sano y no está listo para salir**. Son cosas distintas.

**Sano**: 3567 tests unitarios en verde, sin fallos ni errores; fronteras de capas respetadas de
verdad (ningún `requests` fuera de `core/sources/`, ningún `sqlite3` en la GUI, núcleo libre de
Qt); `core/explain.py` como única casa del significado; escrituras atómicas donde de verdad
importa; subprocesos con timeout y presupuesto; y una ciencia (fotometría, astrometría, serie,
período) con errores honestos implementados. Los cuatro roles coinciden en esto.

**No listo**: hay **12 bloqueantes únicos** (tres de código, dos de empaquetado, siete de
promesas incumplidas o huecos de manual) y un grupo de defectos altos que no impiden arrancar
pero sí impiden confiar.

El patrón que más se repite, y que ningún rol podía ver solo, es este: **el software hace más de
lo que documenta y promete más de lo que hace**. `core/transit_fit.py` existe y no está cableado
a nada; la fase 9 de `core/free_space.py` existe y no está cableada; el README promete paridad
CLI que no existe; el README llama externo a Find_Orb, que viaja dentro; la guía y el código
discrepan sobre los tipos de master; ADR-091 quedó sin revisar. Es una brecha de **honestidad**,
no de ingeniería, y es la que más caro se paga en una primera versión pública.

---

## 3. Matriz de hallazgos consolidada

### 3.1 Bloqueantes de salida (P0)

| # | Hallazgo | Roles | Categoría | Evidencia | Esf. |
|---|---|---|---|---|---|
| **B1** | La copia de seguridad «pre-migración» se toma **después** de migrar: no hay rollback y el informe siempre dice «todo al día» | QA-01 | pérdida de datos | `__main__.py:22` importa `core.db` a nivel de módulo; `core/db.py:977` migra al instanciar. **Reproducido**: `user_version 0 -> 21` durante el import | S |
| **B2** | `solve.solve()` llama a `cancel.is_set()` sobre un *callable* plano: `AttributeError` que **aborta el track & stack** en el QC del WCS, siempre que no haya ASTAP local | QA-02 | crash | `core/solve.py:153` (existe el ayudante `is_cancelled()` y `sources/astap.py` lo usa). **Reproducido** | S |
| **B3** | `_night_of` usa mediodía **UTC**, no local: al este de ~UTC+6 una noche se parte en dos y la apertura óptima, el detrend multinoche y el QC salen sobre medias noches | QA-04 | resultado silenciosamente erróneo | `core/series_measure.py:1123-1129` frente a `core/journal.py:80-88` y ADR-036. **Reproducido** | M |
| **B4** | `Repository = "https://github.com/<pending>/nightscribe"` en los metadatos del paquete | DEV-01, QA-16 | release engineering | `pyproject.toml:56`; README e instalador usan `https://github.com/irydeo/nightscribe` | S |
| **B5** | El `.deb`, el `.rpm`, el PKGBUILD y el wheel **no empaquetan `docs/`**: `Ayuda > Documentación`, el «?» del editor y el índice offline del asistente quedan vacíos, y solo se ve bien en Windows | DEV-02 | feature rota y dependiente de plataforma | `nightscribe/paths.py:80-85`, `tools/build_deb.py:205-207`, `installer/rpm/nightscribe.spec:113-121`, `installer/arch/PKGBUILD`; el spec de Windows sí los lleva | M |
| **B6** | La guía promete un ajuste de tránsito dentro de la app que **no está cableado a nada**, y el README dice lo contrario («100 % external») | DOC-01 | promesa rota | `docs/user/06-photometry.md:171` frente a `core/transit_fit.py`, sin llamadas en `gui/` ni en `__main__.py` | S (decisión: retirar la frase) |
| **B7** | «Todo lo que hace la GUI tiene equivalente en CLI» es falso (editor, campañas, asistente, calendario) | DOC-02 | promesa rota | `README.md:546` frente a los 10 subcomandos reales | S |
| **B8** | Find_Orb: el README lo llama «herramienta externa opcional», la guía dice que viaja con la app, y el empaquetado confirma a la guía | DOC-03 | promesa rota | `README.md:106,525` frente a `installer/*` y `core/config.py:206-210` | S |
| **B9** | «Flat dark» como cuarto tipo de master: la guía se contradice y contradice al código | DOC-04 | contradicción | `docs/user/05-capture.md:200` frente a `docs/user/10-settings.md:113` y `core/calibration.py:99` (`KINDS = ("bias", "dark", "flat")`) | S |
| **B10** | La misión «entender cada objeto» (diálogo Explore) no tiene procedimiento en la guía | DOC-05 | hueco de manual | el diálogo existe (`gui/ui/main_window.ui:90-96`) y el README lo describe; `docs/user` solo lo nombra de pasada | M |
| **B11** | No hay capítulo de resolución de problemas | DOC-06 | hueco de manual | `docs/user/` sin capítulo de troubleshooting; sí lo tienen los docs técnicos, que no se publican (A14) | M |
| **B12** | La ayuda de la CLI está **solo en español**: un usuario en inglés no puede ni leer `--help` | UX-01, DEV-07, DOC-18 | promesa bilingüe y UX | `nightscribe/__main__.py:576-688` | M |

### 3.2 Altos (no impiden arrancar, impiden confiar)

| # | Hallazgo | Roles | Por qué es alto |
|---|---|---|---|
| A1 | `free_space.restore()` **pisa** un fichero recapturado con el mismo nombre | QA-03 | pérdida de datos latente: hoy no está cableado (A2), se vuelve bloqueante en cuanto se exponga. Reproducido. Prerrequisito del paquete F9 |
| A2 | La fase 9 (liberar espacio) está implementada en `core/` y **sin puerta** en GUI ni CLI | QA-09 | funcionalidad anunciada que el observador no puede usar. Decisión 2026-10-15: **cablear** (paquete F9 en P2) |
| A3 | `Config.save()` no es atómico y `load()` cae en silencio a los valores por defecto | QA-05 | un corte durante un `set()` pierde coordenadas, código MPC, claves y perfil de cámara sin avisar |
| A4 | Las migraciones v18 y v20 hacen `ALTER TABLE astrometry_points` sin guarda de tabla: la base de datos no abre | QA-06 | el resto de migraciones sí se protege; el arreglo es barato y coherente |
| A5 | GPU **encendida por defecto** con kernels `float32` sin cobertura en CI, y `gpu.py`, `pyproject` y ADR-091 dicen lo contrario | QA-08, DOC-10 | riesgo científico y contradicción documental; ADR-091 sin revisar, contra la regla de AGENTS.md |
| A6 | El manual **no está en el menú Ayuda** y sin red no hay puerta a la documentación local, aunque los `.md` viajen instalados | UX-02 | el navegador `gui/doc_dialog.py` y `gui/doc_viewer.py` existe y no se llama desde la ventana principal |
| A7 | Un código MPC escrito y no resuelto deja el observatorio en **0,0 sin bloquear** | UX-04 | el planificador y los crepúsculos salen falsos y el usuario cree haber configurado el sitio |
| A8 | «Calcular la noche» **no se puede cancelar**, y `findorb.run()` ignora el parámetro `cancel` | UX-05, QA-07 | el botón Cancelar de Find_Orb no cancela; el patrón correcto ya existe en resolver, serie y apilado |
| A9 | La regla «nunca la raya» se incumple **1745 veces en docs** y 86 ficheros `.py`, incluido el propio `AGENTS.md` que la enuncia, y no tiene guardián | DEV-08, UX-12 | regla obligatoria que el manual viola: enseña que el reglamento es orientativo |
| A10 | Los mapas del desarrollador mienten: `AGENTS.md` (rango de ADR, ruta de `build_site.py`), `ARCHITECTURE.md` (omite toda la reducción), `DESIGN.md` (control de telescopio «fuera de alcance», pestañas y Z41 superados), ADR-070 (diez capítulos) | DEV-05, DOC-11, DOC-12, DOC-13, DOC-14 | el recién llegado trabaja con un plano equivocado |
| A11 | Añadir un tipo de objetivo toca ~35 ficheros con 505 literales, sin contrato ni test de completitud | DEV-04, DEV-18 | es lo que hace que solo el autor pueda evolucionar la app |
| A12 | `gui/main_window.py`: 14 286 líneas y 540 métodos en una clase | DEV-03 | garantiza conflictos en trabajo paralelo y revisiones inviables |
| A13 | El README omite el asistente y la clave de contaminación lumínica, y dice «cuatro claves» cuando hay cinco más la de IA | DOC-08 | la landing y la web ocultan funciones reales |
| A14 | Los docs técnicos (PHOTOMETRY, ASTROMETRY, SEQUENCES, UFE, MPC_SUBMISSION, etc.) no se publican ni se enlazan | DOC-07 | el usuario avanzado que quiere exprimir el programa acaba en el repositorio |

### 3.3 Medios y bajos (agrupados)

- **i18n fina**: cadenas ES idénticas al origen (UX-08), «PROYECTOS» en la interfaz inglesa
  (UX-09), «Ajustes» en un tooltip inglés (UX-10), elementos de combo sin `tr()` (UX-11), más de
  500 entradas obsoletas en los `.ts` (UX-18), `CONTRIBUTING.es` sin la regla de textos de ayuda
  (DOC-19).
- **Primer contacto**: el CTA dice «crear» y la fila dice «Explorar» (UX-03), estado vacío que
  culpa a la red sin comprobar (UX-06), confirmación de borrado poco informativa (UX-07), paso
  «tus datos a salvo» en instalación nueva (UX-21), la CLI sin subcomando no orienta (UX-15).
- **Ayuda**: tooltips ensayo de hasta 1700 caracteres (UX-16), el «?» del editor depende del
  interruptor de IA (UX-20).
- **Robustez**: sin `sys.excepthook` (QA-15), `wcs_store` deja los FITS en `0600` (QA-13),
  escrituras no atómicas de productos derivados (QA-14), `_pack_desig` calcula mal la letra del
  siglo (QA-11, reproducido: `mAB12` en vez de `K26A12B`), `obsTime` de ADES sin la «Z» (QA-12,
  sin confirmar).
- **Suite**: la ejecución serial se cuelga al 80 % por estado de Qt entre ficheros; en paralelo
  (lo que usa el CI) pasa (QA-10).
- **Suite (QA-18, hallado el 2026-10-15 durante P0)**: con `-n auto` en una máquina de 12
  núcleos, un worker xdist **crashea** de forma no determinista en `test_track_stack_stack.py`
  (el test que cae cambia entre ejecuciones; con `-n 4` la suite queda verde, y el árbol base
  sin cambios también falla, así que es **preexistente**). El CI no lo ve porque sus runners
  tienen 2–4 núcleos. Mismo dominio que QA-10: fiabilidad de la suite en máquinas grandes.
- **Extensibilidad y proceso**: `db._migrate` de 586 líneas (DEV-12), red fuera del caché sin
  lista de exenciones (DEV-10), sin `docs/DEVELOPING.md` (DEV-11), sin guardianes de índice ADR
  ni de `requests` (DEV-13, DEV-14), `imageio-ffmpeg` dura frente a opcional (DEV-16), ficheros
  de herramientas de IA commiteados en la raíz (DEV-17), huecos de cobertura en migraciones y en
  `restore` (QA-17).

---

## 4. Registro de conflictos y acuerdo

| Conflicto | Posturas | Resolución | Quién cede |
|---|---|---|---|
| **La raya bloquea la 0.1?** | DEV invoca veto (regla obligatoria incumplida 1745 veces) frente al coste de limpiar todo | No bloquea la salida: es credibilidad, no función. Se corrige `AGENTS.md` (que la viola al enunciarla) y se añade guardián **solo para texto visible** (GUI y `docs/user`), no para los 1745 históricos | DEV cede en el alcance; mantiene el guardián |
| **GPU por defecto** | QA invoca veto científico (float32 sin cobertura) frente a ADR-089, decisión deliberada del 2026-10-15 | No se invierte el default a ciegas: se exige cobertura en CI con `pocl` y revisión de ADR-091 más `gpu.py`. Si la cobertura no es viable en el plazo, QA recupera el veto y pasa a *opt-in* | QA cede **condicionalmente** |
| **Extensibilidad y `main_window.py`** | DEV invoca veto («un cambio razonable obliga a tocar N capas») frente a «no bloquea el uso» | La escalera pone estabilidad por encima de comodidad del desarrollador: no bloquean la 0.1. Se entrega el **test de contrato de `kinds`** (barato) y se agenda el refactor | DEV cede en la salida; mantiene el veto sobre el calendario |
| **Funciones implementadas sin puerta** | DOC invoca veto por promesa (ajuste de tránsito); QA pide recortar la fase 9 | Se honra la promesa o se retira. Ajuste de tránsito: cablear (M) o quitar la frase (S). Fase 9: recorte explícito, como el propio plan preveía | DOC cede **si** se retira la promesa |
| **Tooltips ensayo frente a mandato didáctico** | UX pide acortar; AGENTS.md exige código didáctico | No hay conflicto real: ADR-058 ya da la respuesta (`short` para tooltip, `long` para ficha y post). Es una regla mal aplicada, no una regla a cambiar | Nadie cede: se aplica el ADR |
| **Manual en Ayuda frente a docs no empaquetados** | UX quiere la puerta ya; DEV demuestra que en Linux no hay a dónde ir | Es una **dependencia**, no un conflicto: B5 es precondición de A6 | Nadie cede |
| **Paridad GUI y CLI** | DOC veta la frase; construir la CLI que falta es enorme | No se construye CLI nueva: se corrige la frase. La paridad real (planificar y publicar) ya existe y se documenta | DOC cede en la exigencia |
| **Suite serial colgada** | QA quiere una señal estricta fiable; el arreglo de estado de Qt es arriesgado | No bloquea (el CI usa xdist). Se documenta que la suite se corre en paralelo y se pone timeout al fixture | QA cede |

**Acuerdo alcanzado:** los cuatro roles firman el plan de la sección 5. Los únicos vetos vivos
son el de QA sobre B1, B2 y B3 (pérdida de datos, crash y resultado erróneo) y el de DEV sobre el
*calendario* del refactor, no sobre la salida.

---

## 5. Plan de trabajo por fases

### P0: sin esto no se publica (código y empaquetado)

- **B1** import perezoso de `core.db` en `__main__.py`, para que la copia de seguridad se tome
  antes de migrar.
- **B2** usar `solve.is_cancelled(cancel)` en `solve.py:153`.
- **B3** frontera de noche desde el mediodía **local** del sitio (reutilizar
  `journal.night_of` o pasar la longitud).
- **B4** fijar `Repository` y `Homepage` en `pyproject.toml`.
- **B5** empaquetar `docs/` en `.deb`, `.rpm`, PKGBUILD y wheel, con la rama correspondiente en
  `paths.docs_dir()` y un test de empaquetado que lo verifique.

*Aceptación:* tres tests nuevos en verde (el import del entry point no cambia `user_version`;
`solve.solve` con un *callable* plano; una noche al este de UTC+6); `pytest tests/unit -n auto`
verde; y un `.deb` construido que abra la ayuda **sin red**.

*Estado (2026-10-15): **implementado** en `release/v0.1-hardening`.* B1 a B5 aplicados, con tres
tests nuevos y guardianes de empaquetado. Verificado con artefactos reales: el wheel lleva 237
entradas de `docs/` con su estructura y el `.deb` 250, ambos con `user/`, `adr/` y `PLANS/`. La
suite unitaria pasa (3576 en verde con `-n 4`) salvo el flake preexistente QA-18 (ver 3.3).

### P1: honestidad y coherencia (barato y visible)

- **B6** (hecho 2026-10-15) retirar la frase del ajuste de tránsito in-app en
  `docs/user/06-photometry.md` y su gemela ES. `core/transit_fit.py` se conserva como la vía
  interna de paridad contra EXOTIC (ADR-015) y el README, que ya dice «100 % external», no se
  toca.
- **B7**, **B8**, **B9** correcciones del README y de la guía.
- **A5** revisión de ADR-091, `gpu.py` coherente y cobertura OpenCL en CI o paso a *opt-in*.
- **A10** `AGENTS.md`, `ARCHITECTURE.md`, `DESIGN.md` y ADR-070 al día.
- **A13** README con el asistente, la clave de contaminación lumínica y el recuento de claves.
- **DEV-13** guardián de completitud del índice de ADR.
- **UX-09**, **UX-10**, **UX-14**, **UX-15**.

*Aceptación:* ningún documento contradice al código en los puntos listados; ADR-091 lleva su
revisión; el índice de ADR tiene guardián.

### P2: primer contacto y UX (lo que hace abandonar)

- **B12** ayuda de la CLI bilingüe.
- **A6** documentación local en el menú Ayuda (tras B5).
- **A7** bloquear o resolver el código MPC sin coordenadas.
- **A8** cancelación real en «Calcular la noche» y en Find_Orb.
- **F9** cablear la fase 9 (liberar espacio) en la ventana de visita. **A1 primero**: `restore`
  con destino ocupado resuelve con `_unique` y registra el nombre real (nunca pisa un fichero
  recapturado). Después la acción con confirmación (§9.5), las dos casillas (§9.3: originales a
  `procesados`, calibrados borrados), progreso y cancelación, restauración y el cierre de los
  handles de mmap (D32). Tests: `restore` con destino ocupado y el resto de la fase 9.
- **UX-03**, **UX-06**, **UX-07**, **UX-21**.
- **B10** capítulo Explore, **B11** capítulo de resolución de problemas, **A14** enlazar los docs
  de tema desde la guía.

*Aceptación:* un usuario nuevo completa *primer arranque, primer proyecto, calcular la noche*
sin abrir el manual, y `--help` responde en el idioma del sistema.

### P3: mantenibilidad (no bloquea la salida, sí la evolución por terceros)

- **A11** test de contrato de `kinds` (cada `id` con caso en planner, enrich, suggest, narrative,
  glyph, overview).
- **DEV-14** guardián de «`requests` solo en `core/sources/`».
- **A9** guardián de la raya en texto visible y corrección de `AGENTS.md`.
- **QA-17**, **A4** tests de migración v18, v20 y v21 (el de `restore` con destino ocupado vive
  en el paquete F9).
- **DEV-11** `docs/DEVELOPING.md` con tres recetas (nueva fuente, nuevo tipo, nueva pestaña UFE).
- **QA-18** acotar el paralelismo de la suite en máquinas grandes (limitar los workers de xdist
  o los hilos del combine por proceso) para que un contribuyente de 16 núcleos no vea un crash
  no determinista.

*Agendado, fuera de la 0.1:* refactor de `main_window.py` (A12), `db._migrate` (DEV-12) y los
módulos grandes secundarios.

### P4: pulido

Resto de i18n, tooltips a densidad `short`, colores incrustados, `sys.excepthook`, escrituras
atómicas de derivados, permisos del FITS, `imageio-ffmpeg`, `_pack_desig`, `obsTime`.

---

## 6. Checklist de publicación de la 0.1

- [ ] `pyproject.toml`: URL real, clasificador a `4 - Beta`, versión == tag
- [ ] `CHANGELOG.md` y proceso de release en `CONTRIBUTING` (DEV-06, QA-16)
- [ ] `.deb`, `.rpm`, PKGBUILD y wheel con `docs/` y ayuda offline verificada por test
- [ ] README sin promesas incumplidas (CLI, Find_Orb, recuento de claves, asistente)
- [ ] Suite verde en las dos plataformas; los 33 *skips* explicados o cubiertos
- [ ] ADR-091 revisada y `gpu.py` coherente
- [ ] Guía con capítulo Explore, troubleshooting y sin la contradicción del flat dark
- [ ] Licencia GPL y aviso de Find_Orb presentes en los paquetes

---

## 7. Decisiones tomadas

1. **Ajuste de tránsito in-app (B6)**: **retirar la frase** (2026-10-15). La guía deja de
   prometer el ajuste dentro de la app; `core/transit_fit.py` sigue siendo la compuerta interna
   de paridad contra EXOTIC (ADR-015) y el README («100 % external») ya era correcto.
2. **Fase 9, liberar espacio (A2)**: **cablear** (2026-10-15), con el arreglo de A1 incluido. Es
   el paquete F9 de P2.

---

## 8. Límites de la auditoría

Nadie construyó artefactos reales (B5 es análisis estático de los scripts de empaquetado),
nadie ejecutó la GUI con pantalla, nadie probó hardware (ASTAP, Find_Orb, CCDciel, cámara) ni
red. El entorno de auditoría no tenía `pyopencl` ni `batman`, por eso 32 tests de GPU y el de
paridad del tránsito se saltaron. QA-12 (`obsTime` sin «Z») queda **sin confirmar** contra el
validador del MPC.

---

## 9. Qué NO tocar (consenso de los cuatro roles)

- La ciencia del núcleo: `coords`, `ephem_minor`, `periodogram`, `photometry`, `calibration`,
  `gain`, la combinación 1/σ² de `astrometry` y el motor de serie.
- Las fronteras de capas, que hoy se respetan.
- La i18n de la GUI y `core/explain.py` como única casa del significado.
- La vista Bienvenida y Ajustes, el mejor escaparate del producto.
- Las escrituras atómicas ya correctas y los presupuestos de subproceso.
