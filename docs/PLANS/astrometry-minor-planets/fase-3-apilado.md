# Fase 3: reparto en grupos, motor de apilado, barrido y puerta de no detección

> Fase del plan maestro [`PLAN.md`](PLAN.md). Decisiones: D8, D9, D10, D11,
> D12, D22, D23, D27, D32.

## Por qué

Es el corazón del track & stack. Aquí se desplazan los frames para que el
asteroide caiga siempre en el mismo punto, se reparte la secuencia en las
observaciones que el usuario quiere, se combinan los frames, se afina la
velocidad y se decide si hay objeto o solo ruido. Es también donde vive la
decisión que evita el pecado clásico: medir el ruido y llamarlo asteroide.

## Implementación

### 3.0 Reparto en grupos (D22, D23)

- `split_groups(n_frames, n_obs) -> list[(start, end)]`: parte la secuencia en
  `n_obs` **grupos contiguos de igual número de frames**. El usuario dice
  cuántas observaciones quiere; el software decide el resto. Los grupos son
  contiguos en el tiempo, así que cada uno tiene su propio `T_mid`.

- `group_reference(frames, group) -> (t_mid, q_g)`: el instante de referencia
  del grupo es su `T_mid` (media de los `t_mid` de sus frames) y el punto `q_g`
  es la posición efemérica del objeto **en ese instante**, llevada a la rejilla
  de referencia con el WCS. Esto es lo que hace que la posición medida
  corresponda al tiempo que se reporta: si todos los grupos midieran en el
  mismo píxel, darían la misma posición para instantes distintos, que es el
  error clásico de este tipo de código (D23).

- `preview_groups(frames, n_obs, base_snr) -> list[GroupPreview]`: estima el
  SNR de cada grupo al elegir el número de observaciones. Como el SNR crece con
  `√n`, pedir más observaciones reparte la señal; la interfaz lo enseña antes
  de aceptar (D22). `GroupPreview` lleva `n_frames`, `t_mid` y `snr_est`.

### 3.1 Desplazamientos y región

Con cada frame ya registrado sobre la rejilla de referencia (fase 2), para un
grupo con su `q_g` el desplazamiento total de cada frame, en píxeles nativos,
es:

```
delta_i = p_i - T_i(q_g)
```

donde `p_i` es el objeto en coordenadas nativas del frame i y `T_i` lleva de la
rejilla de referencia a la nativa. El comentario del módulo explica la
convención con un esquema, porque confundir la dirección de `T_i` es el error
clásico de este tipo de código.

- `track_offsets(group, q_g) -> list[(dx, dy)]`: los `delta_i` del grupo.
- `cutout_box(group, q_g, margin_px) -> (x0, y0, x1, y1)`: el recorte que cubre
  la traza. El objeto siempre cae en `q_g`, pero las estrellas se desplazan a lo
  largo de la traza; el recorte tiene que cubrir todo el recorrido del objeto
  (la mitad, simétrica alrededor de `q_g`) más el margen. Recortar de menos deja
  fuera las estrellas que votan el fondo; recortar de más tira el tiempo. El
  tamaño sale del propio movimiento, no de un número mágico.

### 3.2 Combinación

- `stack(group, offsets, method, region, cfg, progress=None, cancel=None)
  -> (data, mask, report)`:
  - `method` en `sum | mean | median | sigma`. El **sigma-clipped** recorta los
    valores que se alejan más de `sigma` desviaciones de la mediana local y
    hace la media de los supervivientes, con un número de iteraciones
    configurable. Es el estándar profesional: conserva casi toda la SNR de la
    media y rechaza los trazos de estrellas como la mediana.
  - **Suma y media son equivalentes en señal** (la media es la suma dividida
    por el número de frames); se ofrecen las dos por claridad didáctica y
    porque el usuario las verá en el CONCEPT, pero la app explica que eligen lo
    mismo salvo la escala.
  - **Pesos iguales** (D11): el sigma-clipped ya rechaza lo malo; ponderar
    complica la explicación y aporta poco.
  - **Máscara de validez**: los bordes que quedan fuera del frame al desplazar
    se marcan y no votan, para que el apilado no arrastre ceros hacia el
    interior de la imagen.

**Disciplina de memoria** (D12 y D32). Cuatro reglas, y el porqué de cada una:

1. **Lectura con `memmap=True, do_not_scale_image_data=True` y solo la ROI.**
   Se abre cada FITS mapeado en memoria y se lee únicamente la caja envolvente
   de la ROI con `hdu.section[y0:y1, x0:x1]`, que en el frame nativo se mueve
   con la transformación y el desplazamiento del frame. **Verificado el
   2026-10-04**: con `BZERO`/`BSCALE`/`BLANK` en la cabecera (el caso habitual
   del uint16 de las CMOS) astropy se niega a mapear y tanto `.data` como
   `.section` lanzan `ValueError: Cannot load a memory-mapped image`; con
   `do_not_scale_image_data=True` el mapeo funciona y devuelve el dato **crudo**
   (big-endian), así que el `BSCALE`/`BZERO` se aplica a mano y se convierte a
   float32 nativo. El **registro** (fase 2) sí usa el campo completo (o una
   versión bineada), porque vota con estrellas de todo el encuadre; eso pasa una
   vez por frame.
2. **float32 en los frames, float64 en los acumuladores.** Los frames se
   guardan en float32 (la mitad de memoria; 7 cifras significativas son mucho
   más que el ruido de fotones), pero las sumas sobre cientos o miles de
   valores se acumulan en float64, donde el error relativo de float32 crecería
   con N.
3. **La ROI del barrido se cachea una vez.** El barrido re-apila 25 veces; si
   cada pasada re-lee, se pierde lo ganado. Se cachea la ROI de los frames
   (pequeña) y los workers la comparten **primero con mmap + page cache**, que
   ya comparte las páginas físicas entre procesos; `multiprocessing.shared_memory`
   se añade **solo si el banco de pruebas lo pide** (menos código y menos fugas
   por defecto). mmap hace barato el leer, no el calcular.
4. **Franjas solo para el stack final a frame completo.** Ahí el conjunto de
   trabajo (cientos de 16 MP) no cabe: se recorre la salida en bandas y, para
   cada banda, se lee de cada frame la región que necesita (la banda mapeada
   por `T_i` más `delta_i`), con el tamaño de banda elegido para caber en el
   presupuesto. Un test comprueba que RAM y franjas dan **el mismo resultado**,
   porque un streaming que no coincide es una fuente silenciosa de error.
5. **Liberación explícita.** En cuanto el stack de un grupo está a salvo, se
   hace `del` de sus frames y se sueltan las referencias (nada de listas que
   los retengan), con `gc.collect()` por grupo como **seguro barato, no como
   solución**: los arrays de numpy no forman ciclos, `del` los libera por
   conteo de referencias, y el recolector no devuelve al sistema la memoria
   fragmentada. Lo que de verdad protege es acotar el conjunto de trabajo.

Un **test de memoria** (A16) mide el pico de RSS sobre el tamaño real del
checklist 6 y exige que quede por debajo del presupuesto fijado **antes** de
medir; el banco de pruebas compara las tres vías (RAM total, mmap + ROI,
franjas) en tiempo y en pico de memoria, y con eso se decide el multiproceso.

**Multiproceso** (D12): la combinación por franjas es paralelizable por bloques
independientes. Se usa cuando aporta y se mide; si en un hilo el tiempo es
aceptable, no se añade complejidad (la decisión se toma con el banco de
pruebas de esta fase, no antes).

- `stack_groups(frames, groups, offsets_by_group, method, ...)`: apila cada
  grupo con su `q_g` y su recorte. Devuelve una lista de stacks, uno por
  observación.

### 3.3 Barrido de fine-tuning (una vez, D22)

- `sweep(frames, base_motion, pct, steps, method="median", ...)
  -> SweepResult`: el barrido se hace **una vez sobre la secuencia completa**
  (no por grupo) y se aplica a todos: el rate cambia poco dentro de una noche,
  y repetirlo por grupo multiplicaría el cómputo sin ganar nada.
  - `base_motion` es la velocidad teórica (módulo y ángulo de posición) que
    sale de la efeméride. El barrido prueba una rejilla de 5×5 (25
    combinaciones) alrededor: 5 factores de **módulo** (por defecto de 0,95 a
    1,05) por 5 desfases de **ángulo de posición**. Se elige módulo y PA, y no
    componentes RA/Dec, porque los errores reales son de velocidad y de rumbo
    (la montura y la efeméride fallan en esos dos ejes) y así se explica al
    usuario sin matrices.
  - Para cada combinación se re-apila sobre el **recorte** de la secuencia
    completa (D11) con el método rápido (mediana) y se calcula el score.
  - **Score = SNR × redondez**, con `redondez = b/a` de los segundos momentos
    de la fuente (1 = circular). Maximizar el producto premia una fuente
    brillante **y** redonda; un trazo alargado tiene `b/a` pequeño y se
    penaliza aunque su SNR sea alto. El factor exacto se fija con el test
    sintético de esta fase, no con el dataset real.
  - Devuelve la mejor combinación, su score y toda la rejilla (para pintarla y
    guardarla en `astrometry_runs.sweep_json`).

- `fine_tune(frames, ...) -> MotionSolution`: aplica el resultado del barrido
  como desplazamiento por frame (el módulo y el PA corregidos se convierten a
  un vector de velocidad) y lo deja listo para que cada grupo lo use al
  apilarse.

### 3.4 Detección y puerta de no detección

- `detect(stack, q, cfg) -> DetectionReport`:
  - Mide el **SNR** de la fuente en `q`: flujo en la apertura menos el cielo
    local, dividido por el ruido de la apertura (cielo + lectura + la propia
    fuente, con la ganancia). Se documenta la fórmula porque el SNR es una
    cifra que el usuario ve.
  - **Puerta** (D10): primero se apila con la velocidad **teórica** la
    secuencia completa (el máximo SNR posible). Si el SNR no supera
    `astrometry_snr_sigma` (3,5σ por defecto), **no se ejecuta el barrido**:
    barrer sobre ruido y quedarse con el máximo es la definición de
    sobreajustar. Se marca `NOT_DETECTED`.
  - **Magnitud límite**: si no hay detección, se calcula la magnitud del flujo
    que daría justo el umbral de SNR, y se ofrece al usuario. Es información
    útil: dice hasta dónde llegaba la pila. Necesita punto cero; si no hay
    comparsas, se da como magnitud instrumental y se dice. Se calcula para la
    secuencia completa y para cada grupo.
  - `DetectionReport`: `detected`, `snr`, `x`, `y`, `fwhm`, `roundness`,
    `mag_limit`, `notes`.

La puerta de D10 (3,5σ) decide **si hay algo y si se barre**. El listón de
**envío** es otro (D26, SNR ≥ 20 por observación) y se aplica en la fase 6
sobre el SNR de cada grupo.

## Tests

`tests/unit/test_track_stack.py`:

- **A1, velocidad sintética**: una secuencia sintética con un objeto de
  velocidad conocida (y estrellas fijas que dejan trazo) se apila; tras el
  barrido, la velocidad recuperada queda dentro del 1 % de la inyectada.
- **A2, métodos**: los cuatro métodos apilan; el sigma-clipped elimina el trazo
  de una estrella que cruza el objeto; suma y media dan la misma señal salvo
  escala; RAM y streaming coinciden exactamente.
- **A3, no detección**: con solo ruido, la puerta dispara, no hay barrido y la
  magnitud límite es coherente con el ruido; con un objeto real por encima del
  umbral, el barrido sí corre.
- **A11, grupos**: partir una secuencia de 300 frames en 3 grupos da 3 stacks,
  cada uno con su `q_g` y su `T_mid`; el `q_g` de cada grupo corresponde a la
  posición efemérica de su instante (no la del primero); el SNR por grupo baja
  aproximadamente como `√n`; `preview_groups` acierta el orden.
- **Redondez**: un objeto con el doble de desplazamiento residual tiene menor
  `b/a`; el score lo penaliza.
- **Recorte**: el recorte calculado cubre la traza completa (ni un píxel del
  objeto fuera) y no es mayor de lo necesario.
- **Lectura por `section`**: con un FITS sintético que usa `BZERO`, `memmap=True`
  a secas **falla** (se comprueba el error), y con
  `memmap=True, do_not_scale_image_data=True` el valor leído con `section` más
  el escalado a mano coincide con el de `hdu.data` leído sin memmap.
- **A16, memoria**: el pico de RSS del apilado sobre el tamaño real del
  checklist 6 queda por debajo del presupuesto fijado antes de medir; y el
  barrido no re-lee la ROI en cada pasada (se comprueba con un contador de
  lecturas).
- **Liberación**: tras apilar un grupo, sus frames se sueltan (el pico de RSS
  no crece con el número de grupos ya cerrados).
- **Rendimiento**: banco de pruebas con el tamaño real del checklist 6, que
  compara las tres vías (RAM total, mmap + ROI, franjas) en tiempo y en pico de
  memoria (no es compuerta, es la referencia para decidir el multiproceso).

## Salida limpia

El motor apila una secuencia desde tests y CLI, la reparte en observaciones,
afina la velocidad una vez y decide si hay objeto. La GUI todavía no lo expone.

## Hecho cuando

A1, A2, A3, A11 y A16 pasan con semilla fija y el banco de pruebas deja escrito
el tiempo y el pico de memoria de cada vía (RAM, mmap + ROI, franjas) para el
tamaño real.
