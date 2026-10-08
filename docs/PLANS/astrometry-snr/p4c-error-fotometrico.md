# P4c: el error fotométrico del pipeline, medido

**Estado**: hecho. Es la medida que decide si merece la pena cambiar la
magnitud del reporte al filtro adaptado (el punto 3 de la lista).

## La idea, y por qué no hace falta catálogo

El error de magnitud de una medida es

    -2,5 · log10( F_medido / F_inyectado )

y **el punto cero se cancela en la razón**. Así que el instrumento puede
decir si el pipeline sesga el brillo, y cuánto, **sin red y sin catálogo**:
basta con saber qué flujo se puso. Un número **positivo** significa que el
pipeline lee la fuente **más débil** de lo que es, y eso es un error
**sistemático** de todas las magnitudes que publique, no una dispersión.

## Lo que mide ahora

- `injection.mag_error(medido, inyectado)`: el número de arriba.
- `recover(..., psf_fwhm=...)`: mide el flujo **dos veces**, con la regla de
  apertura de la propia app para ese seeing y con el **filtro adaptado**
  construido con esa PSF. Devuelve `flux`, `flux_mf` y `fwhm`.
- `completeness` y `motion_recovery` devuelven `err_mag` y `err_mag_mf` por
  intento y sus medianas, y el CLI los imprime en dos columnas.
- `inject_sequence` mide la PSF de la sesión cuando no se le da una: inyectar
  una fuente **más nítida** que la noche da un sesgo que es del banco y no
  del pipeline (medido: +0,15 mag con una fuente de 3,5 px en tomas de
  4,6 px, y era el desajuste).

## El resultado, en las tomas reales

30 tomas de 2025 UR, movimiento inyectado 6 px/min, PSF la de la sesión,
5 intentos por flujo:

| flujo inyectado | SNR | **d mag apertura** | **d mag filtro** |
| --- | --- | --- | --- |
| 6.000 ADU | 9,3 | **+0,541 ± 0,121** | **+0,234 ± 0,037** |
| 24.000 ADU | 44,0 | **+0,116 ± 0,016** | **+0,077 ± 0,007** |

Lo que dice:

1. **El pipeline lee más débil de lo que es** (positivo) y el sesgo **crece
   al bajar el SNR**: +0,08 mag a SNR 44 y +0,54 mag a SNR 9. A SNR 9 la
   posición medida del objeto vaga unos píxeles y una apertura de 6,2 px
   pierde una parte grande del flujo; por eso el sesgo no es constante.
2. **El filtro adaptado lo mejora en las dos filas**: a SNR 9 reduce el
   sesgo a la mitad (+0,234 frente a +0,541) y la dispersión **tres veces**
   (±0,037 frente a ±0,121), y a SNR 44 también gana (+0,077 frente a
   +0,116). Gana **justo donde importa**, que es el objeto débil.
3. A SNR alto el +0,08 mag que queda es la **PSF real no gaussiana**: sus
   alas se escapan de una apertura de 1,35×FWHM, y eso es física, no un
   fallo.

**Respuesta al punto 3, primera pregunta**: sí, el filtro mide mejor el
brillo. La segunda pregunta (si se adopta en el reporte) exige medir el cero
punto **con el mismo método** en las comparsas, y eso es el paso siguiente.

## La lección, otra vez, y va escrita

Persiguiendo un sesgo de +3,3 mag en las pruebas sintéticas descubrí que
**mi campo de prueba tenía las estrellas todas en una línea** (a y=40): con
la traslación en y sin información, el registro se inventaba un `dy` de 8,79
px en fotogramas **idénticos**, la posición del objeto salía 8 px
equivocada y el apilado salía estirado. El pipeline estaba bien; el banco no.

Con un campo repartido en 2-D el registro cuadra (`dy ≈ 0`) y el flujo
vuelve a **+0,012 mag quieto y +0,026 y +0,036 moviéndose** (0,5 y 2
px/min), o sea que el track & stack congela el objeto y mide su flujo sin
sesgo apreciable.

Es la tercera vez en esta campaña que **la primera medida de una mejora mide
el banco de pruebas** (el signo del desplazamiento subpíxel, la cadencia
irregular y ahora el campo degenerado). De ahí la regla que ya está en
`docs/SNR.es.md`: un campo de prueba necesita estrellas **repartidas**, y
cualquier cifra rara se comprueba contra un caso de respuesta conocida antes
de creerse.

## Verificación

**Tests**: `mag_error` con sus tres casos y con la medida que no ocurrió
(None, no cero); y el flujo inyectado vuelve dentro de una décima de
magnitud con las dos medidas, con la tabla de completitud llevando las dos
medianas.
