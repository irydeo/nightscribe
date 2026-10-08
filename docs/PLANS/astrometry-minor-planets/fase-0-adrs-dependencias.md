# Fase 0: ADRs, dependencias y spike del build

> Fase del plan maestro [`PLAN.md`](PLAN.md). No se escribe código de producto
> en esta fase: se firman decisiones y se verifica que la base técnica existe.

## Decisiones

D18 (se reabre ADR-004), D19 (seis módulos), D20 (tres ADRs), y el checklist de
verificaciones de la sección 6 de `PLAN.md`.

## Por qué

Las fases siguientes no pueden empezar discutiendo la base. La reapertura de
ADR-004 no es un detalle de este módulo: cambia la política de dependencias de
toda la app y contradice documentos vivos (`docs/PLANS/variables/LEEME.md` dice
«Prohibido astropy/photutils»). Eso hay que firmarlo y dejarlo escrito **antes**
de que el primer `import astropy` aparezca en el árbol, o el siguiente que lea
el código no sabrá si es un error. Además, el riesgo real del plan es el
empaquetado en Windows: si astropy no entra en el build, mejor saberlo ahora
que en la fase 7.

## Implementación

### 0.1 ADRs nuevos

- **ADR-060 · Política de dependencias.** Reabre ADR-004. Regla nueva: numpy
  primero, y una librería estándar cuando aporta y su coste (peso del
  instalador, mantenimiento) está justificado. Lista blanca explícita:
  astropy, scipy, photutils; ccdproc, reproject, scikit-image y sep quedan
  autorizadas pero no se añaden sin necesidad demostrada. Declara que
  conviven dos WCS y dos centroides y por qué no se migran los módulos viejos
  en este plan. Toca ADR-018 (el lector FITS propio pasa a legado) y una nota
  en ADR-051 (el WCS TAN propio no desaparece).
- **ADR-061 · Calibración de imágenes.** Receta declarativa, biblioteca de
  masters indexada (cámara, ganancia, temperatura ±3 °C, exposición exacta,
  filtro), flat con dark-flat y normalización, calibración en memoria con
  export opcional, y la decisión de que es un paso reutilizable con pestaña
  propia.
- **ADR-062 · Astrometría por track & stack y validación.** **Reabre
  ADR-022**: NightScribe ahora sí genera medidas, pero acotado a objetos
  conocidos, con el usuario como revisor y remitente. Recoge D1 a D17 y D22 a
  D32: solo tracking directo, medida doble con el mismo centroide, efeméride
  por frame, barrido con score SNR+redondez, puerta de no detección,
  multiobservación por grupos, secuencia centrada, chequeo delegado en
  Find_Orb (con su normalización y su ventana; sin reimplementar el ajuste de
  órbitas), umbral de envío distinto del de detección, aviso de dithering,
  T_mid, ADES y 80 columnas, rmsRA/rmsDec, tablas nuevas y Undo por run. Anota
  el hueco del grid search y la regla de que el chequeo filtra, no demuestra.

Cada ADR es bilingüe (ES/EN) y entra en `docs/adr/README.md`.

### 0.2 Documentos vivos que hay que poner de acuerdo

- `AGENTS.md`: la frase «dependencias mínimas» y la lista de `core/` ganan los
  seis módulos nuevos; si menciona la prohibición de scipy/astropy, se
  corrige.
- `docs/PLANS/variables/LEEME.md`: la línea «Prohibido astropy/photutils
  (ADR-004)» se actualiza a la regla nueva.
- `docs/WORKFLOWS.es.md` y `docs/WORKFLOWS.md`: entrada del nuevo track con el
  punto de entrada a esta carpeta.
- `docs/DATA_SOURCES.*` (nuevo source `mpc_obs`) y `docs/DESIGN.*` si la lista
  de dependencias aparece allí.

### 0.3 Dependencias

- `requirements.txt`: añadir `astropy`, `scipy` y `photutils` fijadas. No se
  añaden ccdproc, reproject, scikit-image ni sep.
- `installer/nightscribe.spec`: `collect_data_files` y `collect_submodules`
  para astropy (tablas IERS, datos internos) y lo que pida scipy. Probar el
  workflow `.github/workflows/windows-preview.yml`.
- Decidir la política de IERS: `astropy.utils.iers.conf.auto_download = False`
  y, si hace falta, empaquetar la tabla con fecha de corte documentada (misma
  política que el plan de series, D16). Se verifica en el punto 4 del
  checklist.

### 0.4 Spike del build

Antes de nada, un commit mínimo que importe astropy, scipy y photutils desde
un módulo de prueba y arranque en Linux y en el build de Windows de preview.
Si no entra, se documenta y se replantea antes de la fase 1.

## Checklist de verificaciones

Las diez de la sección 6 de `PLAN.md`, cada una cerrada con su resultado y su
fallback elegido, en una sección «Resultado» dentro de este fichero (como hace
`series-photometry.md`).

## Resultado (2026-10-04)

Cerrado en el árbol de trabajo (rama `feature/astrometry-minor-planets`):

- **ADRs**: escritos y aceptados ADR-060 (política de dependencias), ADR-061
  (calibración) y ADR-062 (astrometría por track & stack); reabiertos ADR-004
  (por ADR-060), ADR-018 (nota de legado del lector FITS) y ADR-022 (por
  ADR-062). Añadidos al `docs/adr/README.md`.
- **Documentos vivos**: `AGENTS.md` (regla «numpy primero»), el `LEEME` del track
  de variables (ya no prohíbe astropy) y este plan.
- **Dependencias**: `astropy>=6.0`, `scipy>=1.11` y `photutils>=1.10` en
  `pyproject.toml` y `requirements.txt`; `installer/nightscribe.spec` recoge los
  datos de astropy y nombra los submódulos que se usan. Instaladas en el `.venv`
  y verificadas: **astropy 7.0.1, scipy 1.15.3, photutils 3.0.0, numpy 2.2.4**.
- **Tests**: `tests/unit/test_dependencies.py` (con `importorskip`). Suite
  unitaria completa verde: **2592 passed**.
- **Verificación 13 (lectura)**: cerrada con el hallazgo de `BZERO`/`BSCALE`
  (astropy no mapea; hace falta `do_not_scale_image_data=True`).
- **Verificación 9 (`get-obs`)**: cerrada; `ADES_DF` en minúsculas, `OBS80`
  formateado, volumen real medido.

Pendiente (necesita al autor o su entorno):

- **Verificación 9 (`get-obs-neocp`)**: probar con un tracklet vivo del NEOCP.
- **Verificaciones 1 a 8, 10, 11 y 12**: SIP real del solver, Horizons, el build
  de Windows con PyInstaller, IERS sin red, el dataset real (secuencia +
  Tycho-Tracker), el tamaño real, la ida y vuelta del reporte, la biblioteca de
  masters, y la instalación guiada de Find_Orb (en este entorno no hay
  micromamba/conda ni `fo`).
- **Firma del autor** de los tres ADRs y las tres reaperturas (escritos y
  marcados como Accepted; revisar el texto).

## Tests

- No hay tests de producto. Se puede añadir un test trivial de que los tres
  paquetes se importan (`tests/unit/test_dependencies.py`), con
  `pytest.importorskip` para no romper entornos sin ellos durante la
  transición.
- Revisión de enlaces de docs: si se quiere, un test que recorra los `.md`
  locales y detecte enlaces rotos.

## Salida limpia

- ADR-004, ADR-018 y ADR-022 revisados y firmados por el autor.
- ADR-060, ADR-061 y ADR-062 publicados y en el README de ADRs.
- `requirements.txt` y el spec de PyInstaller actualizados; build de Windows
  verificado (o replanteado con el fallback escrito).
- Documentos vivos coherentes.
- Checklist de verificaciones cerrado; ninguna pregunta abierta antes de la
  fase 1.

## Hecho cuando

`git grep` no encuentra ninguna contradicción sobre dependencias, el build de
Windows de preview arranca con los tres paquetes importados, y el autor ha
firmado los tres ADRs y las tres reaperturas.
