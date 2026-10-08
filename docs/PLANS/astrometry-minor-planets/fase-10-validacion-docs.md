# Fase 10: validación real, documentación bilingüe y cierre

> Fase del plan maestro [`PLAN.md`](PLAN.md). Decisiones: D17, D29 y los
> criterios C2, C3 y C4 de la sección 7 de `PLAN.md`.

## Por qué

Un motor validado solo con datos sintéticos no es un motor validado: la cadena
real incluye el WCS del solver, la calibración, el catálogo de las comparsas y
el formato del reporte. El plan cierra con la secuencia real del autor
comparada contra su salida de Tycho-Tracker, y con la documentación de usuario
que explica cada pieza con un ejemplo en los dos idiomas. Sin eso, el trabajo
no es reproducible ni enseñable.

## Implementación

### 10.1 Validación con datos reales (A10)

- **Test funcional** (`tests/functional/test_trackstack_live.py`, con red):
  corre la cadena completa sobre la secuencia real del asteroide conocido y
  comprueba el residual contra la referencia.
- **Referencia**: **Tycho-Tracker** es el referente (es la herramienta que usa
  el autor, la que el MPC documenta para synthetic tracking y la que produce
  astrometría en el mismo 80 columnas/ADES que nosotros). Se corre **el mismo
  set** con Tycho-Tracker y se comparan las posiciones. Criterio: residual
  **< 0,3″**, y **< 0,1″** en el caso bueno (checklist 5 de la fase 0).
- **Comparación adicional**: el residual propio contra la efeméride y contra
  la dispersión de los demás observadores (fase 5) sobre el mismo set, para
  verificar que el chequeo no marca en falso.
- Si el dataset real aún no está, la compuerta queda **abierta y visible** (no
  se baja el umbral para que un test pase): se cierra con lo sintético y se
  documenta como pendiente, con el fallback del checklist 5.

### 10.2 Documentación de usuario

- **`docs/ASTROMETRY.es.md` + `docs/ASTROMETRY.md`** (nuevo par bilingüe): qué
  es el track & stack y por qué; la calibración y la biblioteca de masters; el
  flujo paso a paso desde la visita (número de observaciones, apilado, barrido,
  secuencia centrada, medida, chequeo, reporte); qué significa cada cifra (SNR,
  residual, magnitud límite, rmsRA/rmsDec, observatorios distintos, última
  observación); cuándo fiarse y cuándo no (dithering, SNR de envío, el chequeo
  filtra y no demuestra); y solución de problemas. Cada pieza con un ejemplo.
  Incluye la sección completa de **Find_Orb** (qué es, instalación en Linux con
  conda-forge, Windows con `fo64.exe` y compilación del código fuente,
  configuración en Ajustes apuntando a `fo`, qué hace NightScribe con él paso a
  paso y solución de problemas), cuyo borrador ya existe como
  `doc-findorb.es.md` y `doc-findorb.md` y se integra aquí.
- **`docs/DATA_SOURCES.*`**: entrada del source `mpc_obs` (endpoints del MPC y
  del NEOCP, campos, TTL de caché).
- **`docs/WORKFLOWS.es.md` / `.md`**: el flujo de astrometría dentro del
  proyecto NEO/PCCP/cometa, enlazando `ASTROMETRY`.
- **`docs/adr/README.md`**: ADR-060, ADR-061 y ADR-062, y las reaperturas de
  ADR-004, ADR-018 y ADR-022.
- **`docs/PHOTOMETRY.*`**: nota de que la calibración (fase 1) es reutilizable
  por la fotometría de series, sin duplicar el motor.

### 10.3 i18n y explicaciones

- `lupdate` + traducción ES/EN, sin `unfinished` (ADR-014).
- Todas las cifras nuevas explicadas en `core/explain.py` con sus dos
  densidades (ADR-058): SNR, residual, magnitud límite, método de combinación,
  observatorios distintos y última observación.

### 10.4 Cierre del plan

- Revisión final de criterios (sección 7 de `PLAN.md`): A1 a A15 y C1 a C4.
- `PRECISION` u otro documento de números, si aplica, actualizado con el
  residual medido.
- Se deja escrito el estado real: qué compuertas están cerradas y cuáles
  abiertas (por ejemplo, el dataset real si no llegó, o la distorsión
  interpolada si el control de calidad la pidió).

## Tests

- `tests/functional/test_trackstack_live.py`: cadena completa con red (Horizons,
  MPC, ASTAP) sobre el set real; residual contra la referencia.
- `tests/unit/test_i18n.py` en verde (sin `unfinished`).
- Enlaces de docs locales sin romper.

## Salida limpia

Fin del plan: la calibración, el track & stack, la multiobservación, la
validación y el reporte están implementados, documentados en los dos idiomas y
validados con datos reales; las compuertas abiertas, si las hay, quedan
escritas con su porqué y su plan.

## Resultado (2026-10-04)

- **Documentación de usuario**: `docs/ASTROMETRY.es.md` y `docs/ASTROMETRY.md`
  publicados (flujo paso a paso, qué significa cada cifra, cuándo fiarse,
  Find_Orb, liberar espacio y solución de problemas). Los borradores
  `doc-findorb.es.md`/`doc-findorb.md` del plan quedan integrados en su
  sección 6.
- **`docs/DATA_SOURCES.md`**: entrada del source `mpc_obs` (endpoints, campos
  en minúsculas, la trampa del GET con cuerpo, y para qué se usa).
- **Validación real (A10)**: pendiente de ejecutar. El material está en
  `tests/data/astrometry/` (manifiesto, PNG de Tycho y fixture recortado) y
  el test funcional usa `NIGHTSCRIBE_ASTRO_DATASET`; necesita ASTAP, Horizons
  y los 2,5 GB locales. **La agrupación en observaciones queda por determinar
  empíricamente** (el folder no mapea de forma obvia a las posiciones
  publicadas).

## Hecho cuando

A10 pasa (residual < 0,3″, o la compuerta real queda documentada como abierta
con el dataset pendiente), la documentación bilingüe está publicada, la suite
unitaria y la funcional son verdes, y ningún criterio de la sección 7 queda sin
su resultado escrito.
