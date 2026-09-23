# Fotometría en NightScribe: cómo se mide la luz

*[English version](PHOTOMETRY.md)*

Guía de usuario del proceso de reducción fotométrica tal como lo
implementa NightScribe: qué hace el programa con tus imágenes, con qué
parámetros, y qué precisión puedes esperar de los números que salen.
Todo lo que aquí se cuenta existe hoy en el código; nada es promesa.

---

## 1. La idea en tres frases

1. La fotometría **mide luz**: cuenta cuántos fotones llegaron de una
   estrella a cada píxel; no mide un «brillo absoluto».
2. La atmósfera, el telescopio y la cámara oscurecen o amplifican a
   **todas** las estrellas de la misma imagen por igual.
3. Por eso medimos **en diferencial**: la estrella objetivo frente a
   estrellas de comparación de la propia placa. Lo que es común se
   cancela; lo que queda es la diferencia verdadera.

A eso se le llama **fotometría de apertura diferencial**, y es la técnica
clásica del fotómetro fotoeléctrico llevada al CCD/CMOS.

---

## 2. Del FITS a la magnitud, paso a paso

Esto es lo que NightScribe ejecuta (en `core/series.py`) cada vez que
mide un punto. Los parámetros citados son los valores reales por
defecto del programa.

### 2.1 Localizar al objetivo con precisión de sub-píxel

La posición del objetivo viene del WCS de la placa (su solución
astrométrica): RA/Dec se convierten a píxel. Como esa posición cae entre
píxeles, se refina con un **centroide**: el centro de masas de la luz en
una caja de 11×11 píxeles alrededor de la posición inicial. El resultado
tiene precisión de fracción de píxel, que es lo que la fotometría
necesita para que la apertura caiga siempre centrada.

### 2.2 La apertura y el anillo de cielo

```
            . . . . . . . . . . . .        anillo de cielo:
            .                     .        entre r = 10 y r = 15 px
            .    . . . . . . .    .        (solo cielo; la mediana
            .    .           .    .         ignora estrellas vecinas)
            .    .  apertura .    .
            .    .   r = 6   .    .
            .    .    px     .    .
            .    .           .    .
            .    . . . . . . .    .
            .                     .
            . . . . . . . . . . . .
```

* **Apertura**: un círculo de radio 6 píxeles centrado en el centroide.
  Capta casi toda la luz de la estrella sin tragar demasiado cielo.
* **Anillo de cielo**: una corona entre 10 y 15 píxeles, lejos de la
  estrella pero cerca de su entorno. De él se toma la **mediana** (no la
  media: la mediana es inmune a píxeles de estrellas vecinas que caigan
  en el anillo).

### 2.3 Del flujo a la magnitud instrumental

**Fórmula 1: el flujo neto**

```
flujo neto = suma de los píxeles de la apertura
             − cielo_mediano × número de píxeles de la apertura
```

**Fórmula 2: la magnitud instrumental**

```
mag instrumental = −2,5 × log10(flujo neto)
```

Es «instrumental» porque depende de tu equipo, tu exposición y tu cielo:
solo es comparable dentro de la misma imagen (o de imágenes hermanas de
una serie, una vez compensadas). Por eso hace falta el paso siguiente:
comparar.

### 2.4 Guardas automáticas

Antes de fiarse de una medida, el motor la descarta si:

* la estrella está **saturada** (su pico supera el 85 % del máximo del
  frame: cerca del recorte del sensor los números mienten);
* el anillo de cielo **toca el borde** de la imagen o a otra fuente
  detectada (no está aislada);
* el flujo neto sale **negativo o nulo** (no hay estrella medible ahí).

---

## 3. Las estrellas de comparación: dos caminos

NightScribe tiene dos formas de conseguir «las otras estrellas», según
de dónde vengas.

### 3.1 El ensemble automático (series de supernovas)

En el análisis rápido de series (pestaña Seguimiento del proyecto de una
SN), el programa elige solo a sus comparaciones:

1. **Detección** de fuentes estelares en el frame de referencia:
   máximos locales 3×3 que superen `cielo + 5σ` del ruido de fondo, con
   separación mínima de 10 píxeles.
2. **Veto de variables por constancia**: cada candidata se mide en TODOS
   los frames de la serie; si su dispersión supera 0,1 mag, era una
   variable y queda fuera. También fuera: saturadas, no aisladas, o que
   no se pueden medir en al menos el 80 % de los frames.
3. Se ordenan por dispersión (las más constantes primero) y se toman
   **hasta 8 estrellas** (el mínimo sano son 3).

Es el criterio del astrónomo hecho algoritmo: una buena comparación es
la que no se mueve.

### 3.2 La secuencia de catálogo (pestaña Comparar del Editor FITS)

Para fotometría con magnitudes de catálogo, la pestaña **Comparar** del
Editor FITS trae estrellas con magnitud conocida alrededor del centro de
la placa:

* **Gaia EDR3**: magnitud G nativa y B, V, Rc, Ic **estimadas** a partir
  del color BP−RP con las transformaciones de Riello et al. 2021
  (válidas para BP−RP entre −0,5 y 4,0; Rc/Ic solo hasta 2,75). Los
  valores derivados se marcan siempre como «(est.)».
* **APASS DR9**: B y V **directas**, más las bandas Sloan.
* **Veto VSX**: toda estrella cruzada con el catálogo de variables de la
  AAVSO queda marcada con anillo rojo y no puede elegirse jamás como
  comparación.

La secuencia elegida (clic a clic, o la propuesta automática por brillo
parecido al objetivo) se exporta a CSV con todas las bandas.

### 3.3 La medida calibrada (pestaña Medir del Editor FITS)

Con la placa cargada y la secuencia construida, la pestaña **Medir**
convierte un clic en una magnitud de catálogo:

1. El clic mide el objetivo (centroide, apertura, cielo con sigma-clip;
  las guardas de la sección 2.4 hablan en lenguaje llano: «saturada»,
  «demasiado cerca del borde», «sin señal medible»).
2. Las estrellas de la secuencia se miden **en la misma placa**, con la
  misma apertura: eso es lo que hace comparable a lo comparable.
3. El **punto cero** es la mediana de `mag_catálogo − mag_instrumental`
  sobre las comps, con su error desde la desviación absoluta mediana
  (MAD) dividida por √N; las estrellas sin la banda elegida o no
  medibles se saltan y se cuentan.
4. La magnitud del objetivo es `instrumental + ZP`, con el error
   combinado: la ecuación CCD (si la cabecera trae GAIN/RDNOISE; si no,
   solo la dispersión de las comps, y el panel lo dice) más el error del
   punto cero.

El panel muestra todo lo usado y todo lo rechazado, y la banda por
defecto es V (directa en APASS, estimada por Riello 2021 en Gaia, y el
panel lo marca). La medida se exporta a CSV de una fila o a línea AAVSO
EFF con la secuencia en CNAME/CMAG/KNAME/KMAG. El archivo FITS en disco
nunca se modifica.

**Controles de calidad** (fase H, 2026-09-23):

* **Cielo**: mediana plana por defecto; en núcleos galácticos, el modo
  «Plano» ajusta una rampa al anillo y evalúa el cielo en la posición de
  la estrella (la mediana plana ahí está sesgada).
* **La apertura sigue al seeing**: se mide el FWHM de las comps en la
  placa y la apertura se dimensiona a 1,35 × FWHM (los campos quedan
  visibles y ajustables a mano).
* **Centroide de precisión** (fase I): la posición se refina con cielo
  local restado, solo píxeles significativos, caja escalada al seeing y
  dos pasadas; en fuentes débiles o con gradiente cae a centésimas de
  píxel de la posición real, en vez de las décimas del momento crudo.
* **«Sugerir aperturas»**: propone los radios desde la curva de
  crecimiento del propio objetivo y su entorno medido (vecino más
  cercano, gradiente del fondo), y explica las razones en lenguaje llano
  en el panel; tu edición manual nunca se pisa sola.
* **Término de color**: con al menos 6 comps con dispersión de B−V se
  ajusta `ZP + k·(B−V)` y se aplica con el B−V del objetivo (variables:
  el del VSX; una SN cerca del pico es ~0, y el panel avisa de la
  suposición). Sin dispersión suficiente, punto cero plano y se dice.
  Los outliers de las comps se rechazan por MAD antes de ajustar.
* **Saturación real**: el techo sale de la tarjeta SATURATE de la
  cabecera o del ajuste `ccd_saturate`; si nadie lo sabe, sigue la
  heurística de la meseta.
* **Error total honesto**: el panel distingue «interno» (fotones, si hay
  ganancia) de «total» (más dispersión del ZP, centelleo de Young con tu
  apertura y altura de Ajustes, término de color y un suelo de flat de
  0,007 mag configurable como `flat_resid_mag`).
* **La estrella check como semáforo**: si la secuencia tiene una, se
  mide y se compara con su catálogo; si se desvía más de 2,5σ_total, la
  medida se marca como NO fiable antes de que te fíes de ella.
* **Restar la galaxia huésped**: descarga la referencia PS1 alineada
  (la del blink), la escala para que las estrellas desaparezcan y mide
  el objetivo en la imagen diferencia; las comps calibran en la placa
  original. Para SNe en núcleos es la diferencia entre «no medible» y
  «0,03–0,05 mag».

**Fórmula 3: la magnitud diferencial**

```
Δmag = mag instrumental(objetivo) − media(mag instrumental del ensemble)
```

Si la SN está 2 mag por debajo de la media del ensemble hoy y 1,5 mag
mañana, se ha debilitado 0,5 mag: el cero absoluto no importa, la
**evolución** es la señal.

---

## 4. Series temporales: el quicklook de supernovas

Con las imágenes apiladas de varias noches registradas en el proyecto,
el botón de análisis rápido ejecuta toda la cadena:

1. Carga cada apilado y localiza la SN por su WCS (sin WCS, el veredicto
   es `no_wcs`: resuelve la astrometría primero; el Editor FITS tiene el
   botón «Resolver astrometría…» para eso).
2. Construye el ensemble (sección 3.1).
3. Mide la SN en cada frame: un punto por noche con
   `{HJD, Δmag, error}`, donde el error es la dispersión del ensemble en
   ese frame.
4. Resume la campaña: **pendiente** en mag/día (ajuste lineal de la
   banda principal), **Δmag desde el pico** y, si el tipo de SN tiene
   plantilla, un **veredicto** («normal», «faster», «slower») comparando
   el último punto con la plantilla a la misma época (tolerancia de 3
   días y 0,3 mag).

Las fechas se guardan como **HJD** (día juliano heliocéntrico): el
tiempo corregido a la posición del Sol, para que curvas de meses no
lleven el vaivén de ±8 minutos de la órbita terrestre. Los puntos se
guardan en el proyecto y alimentan la curva de luz y el post.

---

## 5. Exportar las medidas

Desde el proyecto (pestaña Seguimiento) salen dos formatos:

### 5.1 CSV de trabajo

Una fila por punto: nombre, HJD, magnitud, error, filtro, y las
comparaciones en una celda unida por «+». Cabeceras con el nombre del
objeto y la nota de que las fechas son HJD. Es el formato para hojas de
cálculo y para releer puntos en NightScribe.

### 5.2 AAVSO EFF (Extended File Format)

El formato de intercambio de la AAVSO (WebObs/FotoDif), línea a línea:

```
NAME,DATE,MAG,MERR,FILT,TRANS,MTYPE,CNAME,CMAG,KNAME,KMAG,AMASS,GROUP,CHART,NOTES
```

* `DATE` es HJD (`#DATE=HJD` en la cabecera); los puntos sin HJD
  completo se omiten: el formato no tiene fecha vacía.
* `TRANS` se escribe `NA` con honestidad: NightScribe no transforma tu
  medida al sistema fotométrico estándar (eso requeriría conocer los
  coeficientes de color y extinción de tu equipo).
* `CNAME`/`CMAG` y `KNAME`/`KMAG` se rellenan desde la secuencia de
  comparación guardada en el proyecto (pestaña Comparar / carta);
  `na` cuando no la hay.
* `#OBSCODE` sale de tu código AAVSO en Ajustes, `#SOFTWARE=NightScribe`
  y `#OBSTYPE=CCD`.

**Qué significa MAG aquí**: en los puntos del quicklook es la magnitud
diferencial instrumental (Δmag contra el ensemble), no una magnitud
calibrada de catálogo. En la medida de la pestaña Medir sí es una
magnitud calibrada al catálogo vía el punto cero (TRANS sigue siendo
`NA` con honestidad: no hay transformación de color al sistema
estándar). Los puntos importados de fuera (medidos con otra
herramienta) conservan la magnitud con la que vinieron. Léelo siempre
con el filtro y el origen del punto a la vista.

---

## 6. Ejemplo trabajado, número a número

Una estrella en una placa típica de 16 bits:

* la apertura de r = 6 px contiene 113 píxeles;
* suma de la apertura: 245 000 ADU;
* mediana del anillo de cielo: 820 ADU/px.

```
flujo neto  = 245 000 − 820 × 113 = 152 340 ADU
mag inst    = −2,5 × log10(152 340) = −12,957
```

El ensemble de la noche son 6 estrellas con magnitudes instrumentales
−9,412 · −9,388 · −9,401 · −9,433 · −9,390 · −9,408:

```
media ensemble = −9,405     dispersión = 0,015 mag
Δmag = −12,957 − (−9,405) = −3,552 ± 0,015
```

Lectura: el objetivo brilla 3,55 mag más que la estrella media del
ensemble, con una incertidumbre interna de 0,015 mag. Mañana, la misma
cuenta dirá si subió o bajó.

---

## 7. Precisión: qué esperar y de qué depende

Los dos presupuestos de error que conviene no mezclar:

### 7.1 El error interno (el que reporta el programa)

Ruido de disparo de la fuente y del cielo, ruido de lectura, y la
dispersión entre comparaciones. Con una estrella bien medida (SNR > 50)
y un buen ensemble: **0,01–0,02 mag**. Con una SN de mag 18–19 pegada a
un núcleo galáctico: **0,05–0,15 mag**.

### 7.2 Los sistemáticos (los que no salen en el error)

Por orden de impacto habitual:

1. **La placa sin reducir**: NightScribe mide, no reduce. Los apilados
   deben venir ya corregidos de bias, darks y **flats**; un campo plano
   sin corregir introduce errores del 1–5 % según la posición en el
   sensor.
2. **El término de color**: tu filtro y tu cámara no responden como el
   sistema estándar. Si el objetivo y las comparaciones tienen colores
   B−V muy distintos (una SN azul frente a estrellas solares), aparece
   una deriva de centésimas de magnitud. Regla práctica: elige
   comparaciones de color parecido al objetivo (el B−V está en la
   pestaña Comparar), o deja que la pestaña Medir lo ajuste con las
   comps (fase H).
3. **La transformación de catálogo**: la V derivada de Gaia añade
   ~0,01–0,03 mag de sistemático; la V directa de APASS lo evita.
4. **El cielo con gradiente**: cerca de un núcleo galáctico el fondo no
   es plano y la mediana del anillo sesga. Reducir la apertura y acortar
   exposiciones ayuda; interpreta los errores con cuidado.

**Veredicto**: con placa reducida y buena secuencia, 0,02–0,05 mag de
precisión total realista; lo publicable en AAVSO vive en ese rango.

¿Y para bajar de ahí? Qué hace falta para la fotometría de precisión
(incluidos los tránsitos de exoplanetas), explicado para el observador
y con apéndice técnico de implementación:
[docs/PRECISION.es.md](PRECISION.es.md).

---

## 8. Buenas prácticas (checklist del observador)

* [ ] Placas apiladas y reducidas (bias/dark/flat) antes de medir.
* [ ] Astrometría resuelta (sin WCS no hay localización del objetivo).
* [ ] Ni el objetivo ni las comparaciones saturadas (la guarda del 85 %
      ya vigila; el histograma del Editor FITS te lo muestra).
* [ ] La misma apertura para toda la serie (el programa la fija por ti).
* [ ] Una estrella **check** en la secuencia: si ella se mueve, la noche
      no es de fiar; si solo se mueve el objetivo, es astrofísica.
* [ ] Anota el filtro real de cada sesión; mezclar bandas contamina la
      pendiente de la curva.
* [ ] Repite la medida por noche: dos puntos por sesión detectan
      problemas que uno solo esconde.

---

## 9. Glosario mínimo

* **Magnitud instrumental**: la que sale del logaritmo del flujo neto;
  solo comparable dentro de la misma imagen o serie compensada.
* **Δmag**: diferencia de magnitud instrumental entre el objetivo y el
  conjunto de comparaciones.
* **Punto cero (ZP)**: la constante que convierte la magnitud
  instrumental en magnitud de catálogo. En el flujo de series no se usa
  (Δmag ya cancela lo común); la pestaña Medir del Editor FITS sí lo
  calcula a partir de las comps (mediana de `cat − inst`).
* **Ensemble**: el grupo de estrellas constantes elegido como referencia
  en una serie.
* **Check**: la estrella testigo que vigila que la noche y la secuencia
  se comportan.
* **HJD**: día juliano heliocéntrico; el tiempo medido desde el Sol.
* **B−V**: índice de color (azul menos visual); describe la «temperatura
  de color» de la estrella y gobierna los términos de color.
* **VSX**: el catálogo de estrellas variables de la AAVSO; por eso sus
  miembros nunca son comparaciones.
* **EFF**: Extended File Format de la AAVSO, el formato de entrega de
  medidas fotométricas.

---

*Detalles de implementación y decisiones: `core/series.py`,
`core/compstars.py`, `core/phototrans.py`, `core/photometry_export.py`;
ADR-018 (FITS/WCS propio), ADR-042 (secuencias fotométricas), ADR-044
(Editor FITS unificado).*
