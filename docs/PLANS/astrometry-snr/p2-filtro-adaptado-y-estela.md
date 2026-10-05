# P2: el filtro adaptado y la estela

**Estado**: hecho.

## Por qué

A bajo SNR, medir una estrella con una apertura es tirar señal. Con una
forma conocida `m` (que suma uno) y ruido blanco `σ` por píxel, el mejor
estimador lineal del flujo es

    A = Σ(m · (p − cielo)) / Σ(m²)

y su relación señal-ruido

    SNR = Σ(m · (p − cielo)) / (σ · √Σ(m²))

que es el mayor SNR que **cualquier** filtro lineal puede alcanzar sobre
esos datos (Cauchy-Schwarz: el peso óptimo es proporcional a la forma). Una
apertura es el caso particular `m = 1` dentro del círculo, y **no** es
óptima: da a las alas ruidosas el mismo peso que al núcleo. La ganancia es
mayor justo donde importa, a bajo SNR.

Y la estela, que es la otra cara: un objeto que se mueve se emborrona a lo
largo de su camino. Un segmento uniforme de longitud `L` convolucionado con
una PSF redonda de anchura `σ` da una gaussiana cuyo eje largo lleva

    σ_largo² = σ² + L²/12

(variante de un segmento uniforme). Invirtiendo eso, "el objeto sale
alargado" se convierte en "la exposición fue 2,4 px demasiado larga para
este movimiento", que es un número sobre el que se puede actuar.

## Qué se hizo

1. **La PSF** (`photometry.gaussian_psf`, `photometry.empirical_psf`): una
   gaussiana normalizada (con relación de ejes y ángulo, para la estela), y
   la **empírica** como mediana de los recortes de las estrellas del
   apilado. La mediana y no la media: un rayo cósmico en una estrella no
   puede convertirse en parte de la forma.
2. **La medida** (`photometry.measure_matched`): el filtro adaptado, con el
   **mismo centroide y el mismo cielo** que la apertura y el mismo `σ`, de
   modo que la comparación mide **el filtro** y no otra cosa. Devuelve las
   dos respuestas, la de la apertura y la del filtro, con `n_eff` (el área
   efectiva `1/Σm²`).
3. **La forma** (`photometry.psf_elongation`): momentos segundos con
   **ventana de 2 FWHM y umbral a 1σ sobre el cielo**, y la inversión de la
   varianza para dar la estela en píxeles y el ángulo de posición. La
   ventana y el umbral son medidos, no elegidos: con ventana de 4 FWHM una
   estrella **redonda** reportaba 1,56 px de estela. La tabla que lo fija
   está en el comentario de la función, y de ahí sale `TRAIL_MIN_PX = 1,5`
   (por debajo, el objeto se llama redondo).
4. **En el motor**, por observación: la forma del objeto sobre **su**
   apilado (el FWHM lo dan las estrellas, porque en ese apilado son trazos)
   y el filtro adaptado con esa forma, así que un objeto estelado se filtra
   con la **línea** que de verdad es. El resultado lleva la estela, el PA y
   la ganancia del filtro, y la pestaña lo cuenta en palabras. El reporte
   **sigue usando la magnitud de la apertura**: el filtro entra como
   segunda opinión medida, no como sustituto silencioso.

## Verificación

**Test unitario** (sin red, `tests/unit/test_photometry_matched.py`), con
la fórmula como juez y no con un número recordado:

- Monte Carlo de 200 realizaciones: la ganancia medida cae sobre
  `√(n_ap/n_eff)` con un 5 % de margen, y el flujo del filtro tiene **menos
  dispersión** que el de la apertura con el mismo ruido;
- el flujo recuperado es el inyectado, y a alto SNR coincide con el de la
  apertura (el filtro no mide otra cosa, pesa mejor lo mismo);
- una estrella saturada se rechaza igual que en la apertura (es su
  veredicto, reutilizado);
- la estela vuelve en píxeles (3, 6 y 10 px inyectados) y con su ángulo
  (90° inyectados), y una estrella redonda **no** se llama estelada.

**Sobre los datos reales** (2025 UR, apilado de 139 tomas, FWHM 4,63 px,
apertura r = 6,3 px):

| Pico de la estrella | SNR apertura | SNR filtro (gaussiana) | SNR filtro (empírica) | Ganancia |
| --- | --- | --- | --- | --- |
| 19.744 | 1.088 | 1.771 | 1.776 | **1,63×** |
| 15.792 | 1.227 | 1.909 | 1.905 | **1,56×** |
| 15.552 | 995 | 1.565 | 1.568 | **1,57×** |
| 14.560 | 923 | 1.497 | 1.500 | **1,62×** |

Y la teoría coincide: con esa PSF y esa apertura, `√(n_ap/n_eff)` predice
**1,59×**. La PSF gaussiana y la empírica dan lo mismo **en estos datos**
(el perfil radial mide 4,63 px y la gaussiana con ese FWHM es un modelo
suficiente), así que el motor usa la gaussiana con la forma medida, que es
más barata y no arrastra el ruido de los recortes.

## Dos errores que se encontraron midiendo

Van escritos porque son el tipo de cosa que se repite:

- **La ventana de los momentos**: con 4 FWHM el ruido domina las alas y una
  estrella redonda y brillante reportaba **1,56 px de estela**. De ahí la
  ventana de 2 FWHM y el umbral de 1σ.
- **El desplazamiento subpíxel del apilado de prueba**: con el signo
  cambiado la estrella caía a la esquina, el apilado salía con un FWHM de
  12 px en vez de 4,6 y la primera medida dio una ganancia de **0,62** (el
  filtro parecía peor que la apertura). Con el signo bien, 1,6. La moraleja
  está en el propio código: la primera medida de una mejora casi siempre
  mide el banco de pruebas.

## Lo que no se hizo

- **Cambiar la magnitud del reporte al filtro adaptado.** El reporte sigue
  con la apertura, que es lo que valida el validador de ADR-022 y lo que el
  MPC espera; el filtro se reporta al lado. Cambiarlo es una decisión
  aparte, y con 1,6× de SNR medida la discusión es de calibración (el cero
  punto se mide con las comparsas, y ahí el filtro también ganaría), no de
  detección.
