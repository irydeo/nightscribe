# Estrellas HADS en NightScribe — guía de campo y referencias

Gemelo bilingüe: [`HADS.md`](HADS.md) (inglés). Plan de implementación:
[`PLANS/hads-stars.md`](PLANS/hads-stars.md). Documento de decisión:
[`adr/ADR-034-hads-stars.md`](adr/ADR-034-hads-stars.md).

Este fichero es el *dossier de investigación* de la feature HADS: la ciencia,
los ficheros de datos empaquetados en el repo, el razonamiento de diseño
(tránsitos vs. HADS) y el rastro de referencias — para que cualquier humano o
agente de IA pueda seguir trabajando sin repetir la investigación.

---

## 1. Qué es una estrella HADS

**HADS** = **H**igh-**A**mplitude **D**elta **S**cuti (δ Scuti de alta
amplitud), subclase de las variables δ Scuti. Viven en la intersección de la
franja de inestabilidad clásica con la secuencia principal (tipos espectrales
de A tardía a F temprana).

Hechos físicos clave que guían el diseño de la feature:

| Propiedad | Valor | Fuente |
|---|---|---|
| Periodos de pulsación | ~1–3 h (la clase llega a ~6 h) | Kotysz 2020; McNamara 2000 |
| Amplitud pico a pico | ≥ 0.3 mag en V para la subclase HADS (la clase δ Scuti empieza en > 0.1) | AAVSO VSO; OGLE |
| Forma de la curva de luz | Asimétrica tipo "diente de sierra": subida rápida, bajada lenta | Atlas OGLE |
| Modos | Predomina el fundamental (F) radial; algunas de doble modo F + primer overtone (ratio de periodos 0.76–0.78, diagrama de Petersen); muy pocas de triple modo | Kotysz 2020; Wils et al. 2008 |
| Particularidades | Algunas son multiperiódicas o muestran modos no-radiales | Kotysz 2020; flags del catálogo |
| Historia | Llamadas en su día "enanas Cefeidas" (los trazos recuerdan a las Cefeidas) | OGLE |

Como los periodos son de 1–5 h y las amplitudes ≥ 0.3 mag, **una curva de luz
completa se captura en una sola noche corta** — literalmente ves a una estrella
cambiar de brillo en directo. AAVSO recomienda una HADS como **objetivo ideal
para dar los primeros pasos en fotometría digital** ("Your First Observing
Target"), con exposiciones cada ≤ 15 min para seguir la curva.

Ojo con la amplitud: para observación **visual** AAVSO aconseja ΔV ≥ 0.5 mag;
las amplitudes menores necesitan fotometría.

## 2. La figura de referencia: Patrick Wils

**Patrick Wils** es un astrónomo aficionado belga y una referencia mundial en
el estudio de estrellas variables. Coordina el seguimiento fotométrico a largo
plazo de las estrellas HADS vinculado a la **Vereniging Voor Sterrenkunde
(VVS)** de Bélgica, y forma parte del equipo técnico del **VSX de AAVSO**
(International Variable Star Index) — co-compilador, junto a Sebastián Otero,
Patrick Schmeer y Klaus Bernhard, del índice de más de un millón de objetos.
Sus catálogos de δ Scuti de doble y triple modo (Wils et al. 2008) se citan en
toda la literatura. La lista de objetivos HADS empaquetada en NightScribe
proviene de su programa de monitorización.

### Referencias (verbatim)

1. **HADS** — ponencia, reunión BAV, Hamburgo 2016:
   https://www.bav-astro.eu/images/BAV_Tagungen/Hamburg_2016/04_HADS.pdf
2. **AAVSO — logro de los 20 millones de observaciones**:
   https://www.aavso.org/20-million-observations
3. **VSX — About variable types**:
   https://vsx.aavso.org/index.php?view=about.vartypes
4. **Wils / estrellas variables (austriaca.at)**:
   https://www.austriaca.at/0xc1aa5572%200x00166b7b.pdf
5. **BAA — Short Period Pulsator Program**:
   https://britastro.org/forums/topic/short-period-pulsator-program

### Fuentes complementarias consultadas (para la narrativa y el scoring)

- Wils, P. et al. 2008 — clasificación de HADS de doble/triple modo (citado en
  arXiv:2510.24444: "Wils et al. (2008) list only four known HADS that pulsate
  in three radial modes simultaneously").
- Bibcode del artículo fundacional de VSX: `2006SASS...25...47W`.
- AAVSO — "Delta Scuti and the Delta Scuti variables" (Variable Star of the
  Season) https://www.aavso.org/vsots_delsct
- AAVSO — "Your First Observing Target" (HADS como primer objetivo fotométrico)
  https://wp-test.aavso.org/your-first-observing-target
- Atlas OGLE de curvas de luz de variables — δ Scuti
  https://ogle.astrouw.edu.pl/atlas/delta_Sct.html
- Kotysz, K. 2020, "Variability of HADS stars in TESS", PTA Proceedings,
  vol. 10, 180–182, pta.edu.pl/proc/v10p180
  — solo URL (el PDF no se commitea, ~9.7 MB). Contenido clave extraído en §4.

## 3. Ficheros de datos en el repo

### `nightscribe/assets/HADS-stars.csv` (catálogo runtime, v1)

168 estrellas. **ASCII, saltos de línea CRLF, algunos campos `Name` entre
comillas** (contienen comas dentro de los alias `(=…=…)`). Columnas:

| Columna | Ejemplo | Notas |
|---|---|---|
| `Name` | `GP And (=GSC 01739-01964)` | principal + alias parseables; puede arrastrar flags: `, multiperiodic?`, `-- Non-radial`, `-- change in amplitude?` |
| `RA` | `00 55 18.1` | `HH MM SS.s` → grados |
| `DEC` | `+23 09 49` | `±DD MM SS` → grados |
| `Max` | `10.4` | magnitud en el máximo |
| `Min` | `11` | magnitud en el mínimo |
| `Period_h` | `1.89` | periodo en horas |

Derivados: `amp = Max − Min`, `mag_median = (Max+Min)/2`.

Origen de la copia: el espacio de trabajo del observatorio
`/home/boreal/Develop/astronomy/ns-hads`. Atribución añadida a
`nightscribe/assets/ATTRIBUTION.txt`.

### `nightscribe/assets/hads-coverage/HADS-Project-YYYY.csv` (2011–2026, dato stretch)

El mismo listado de estrellas más **12 columnas mensuales** cuyas celdas llevan
códigos de observador separados por coma (p. ej. `JH`, `dsu08`, `pv28`, `SD28`,
`CKH`). Es la **cobertura mensual real** del programa de monitorización de
Wils: quién midió cada estrella cada mes. La fila de cabecera termina con
columnas sueltas `/,,,/` (ignorar; probablemente un artefacto de la herramienta
de autoría). Uso previsto (stretch): señal de urgencia "nadie cubre esta
estrella este mes". Ojo: es una **foto fija** que se queda vieja; el refresco =
sustituir el asset.

## 4. Ciencia extraída del póster de Kotysz (v10p180)

URL: https://pta.edu.pl/proc/v10p180 — "Variability of HADS stars in TESS",
Krzysztof Kotysz (Astronomical Institute, University of Wroclaw). PTA
Proceedings, oct. 2020, vol. 10, pp. 180–182.

- Se analizó una muestra de ~29 HADS + SX Phe de los sectores 1–4 de TESS
  (propuesta de 213 de estas estrellas para cadencia de 2 min).
- Tipos de pulsación hallados: (i) mono-modo con solo armónicos; (ii) doble
  modo con ratio de periodos 0.76–0.78 (fundamental + primer overtone);
  (iii) mono o doble modo con modos adicionales (presumiblemente no-radiales);
  algunos términos de baja frecuencia interpretables como modos g.
- Ejemplo de HADS no-radial: ASAS 032246-7237.8 = TIC 431589510, frecuencia
  principal f1 = 8.1919 d⁻¹ (periodo ≈ 0.12207 d ≈ 2.93 h), amplitud 81.7 ppt,
  con al menos tres modos no-radiales por debajo de 0.6 ppt.
- Las formas de la curva se estudian con descomposición de Fourier (R21, φ31);
  dos estrellas de la muestra resultaron ser RR Lyrae.
- La muestra final incluirá ~300 HADS/SX Phe; el diagrama de Petersen las
  separa de Cefeidas y RR Lyrae.

## 5. Diseño: tránsitos vs. HADS

| | Tránsitos de exoplaneta (existente) | HADS (nueva) |
|---|---|---|
| Evento | Predecible `t0 + n·P` | **Sin fase conocida**: solo el periodo del ciclo |
| Datos de catálogo | `t0`, `period`, `duration_h` | `period_h`, rango `Max`/`Min` |
| Gate de observabilidad | estrella arriba **a mitad de tránsito** | estrella arriba + **ventana contigua con ≥ 1 ciclo completo** (2 recomendados) |
| Consejo de captura | baseline + tránsito + baseline | **captura continua 2×P** (confirmar repetición + plegar) |
| Métrica clave | cobertura del tránsito (ingress/mid/egress) | **ciclos completos = hours_up / P** |
| Cadencia | resolver ingress (≥ 3 puntos) | **≥ 12 puntos/ciclo**, ≤ 15 min reales (AAVSO) |
| Resultado | curva de luz del tránsito | **ver pulsar la estrella en directo** |

Módulo núcleo: `core/hads.py` (sobre los patrones de `core/transits.py` —
`coords.samples_tonight`, gate de horizonte + margen según ADR-020). Sin `t0`,
sin fase, sin epoch en v1. Si una versión futura enriquece vía la API de VSX,
VSX almacena un `Epoch` (HJD de máximo/mínimo) que **sí** permitiría predecir
máximos al estilo tránsito — stretch documentado.

Ver [`PLANS/hads-stars.md`](PLANS/hads-stars.md) para el mapa completo de
integración (archivo-por-archivo, scoring, GUI, proyectos, tests, fases).