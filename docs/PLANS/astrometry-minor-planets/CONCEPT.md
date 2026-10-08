
# Minor Planets Astrometry - MVP

## 1. El Concepto Base (Shift & Stack)

* **El Problema:** Un asteroide débil que se mueve no se puede fotografiar bien ni con fotos cortas (mucho ruido de fondo) ni con fotos largas (el asteroide deja un trazo tenue al desplazarse por el sensor).
* **La Solución:** Tomar una secuencia de imágenes cortas, calcular cuánto se ha movido el asteroide en cada foto con respecto a la primera, y **desplazar digitalmente las imágenes en sentido opuesto** antes de apilarlas.
* **El Resultado:** El asteroide se "congelará" en un único punto concentrado donde su luz se suma, mientras que las estrellas fijas se convierten en trazos y son eliminadas mediante algoritmos estadísticos (como la **mediana**).


## 2. Las Dos Vías de Ejecución

| Vía | Cuándo se usa | Proceso | Tiempo de cómputo |
| --- | --- | --- | --- |
| **Grid Search (Búsqueda a ciegas)** | Descubrimiento de objetos desconocidos o sin datos orbitales. | El software prueba cientos de combinaciones de velocidad y ángulo hasta hacer emerger un punto. | Alto (requiere GPU o multiprocesamiento). |
| **Tracking Directo (Objeto Conocido)** | Seguimiento de asteroides con efemérides o parámetros orbitales disponibles. | Se consulta la velocidad teórica ($\text{dRA/dt}$, $\text{dDec/dt}$) y se apila en **un solo pase**. | Casi instantáneo (1-2 segundos). |


## 3. Arquitectura del Pipeline para NightScribe

El proceso completo desde la ingesta de archivos FITS hasta la astrometría final sigue estas 5 fases:

1. **Ingesta y Efemérides:** Se leen las marcas de tiempo FITS (`DATE-OBS`) y se obtienen las velocidades teóricas del objeto, idealmente, desde el sistema de efemérides que ya incorpora NightScribe.
2. **Plate Solving y Alineación:** ASTAP resuelve la primera imagen para obtener la escala de píxel y la matriz de transformación WCS. Las imágenes de la secuencia se alinean estelarmente con respecto al primer fotograma ($t_0$).
3. **Cálculo de Shift & Apilado:** Se convierte la velocidad angular a píxeles/minuto y se aplica un desplazamiento subpíxel a cada frame según su $\Delta t$. Se apila la pila mediante **mediana**, **sum**, **mean** o **Sigma clipped** (seleccionable por el usuario). Para la función rápida de "ajuste fino de velocidad" (donde pruebas 25 velocidades en segundos), se suele usar la **Mediana** por pura velocidad. Una vez encontrada la velocidad perfecta, la imagen final que se usa para medir la astrometría y reportar al MPC se apila usando el método que el usuario seleccione, como **Sigma Clipped**.
4. **Detección y Centroide:** Se localiza el pico de luz del asteroide en la coordenada esperada y se mide el centroide exacto a nivel subpíxel.
5. **Conversión y Reporte MPC:** Se mapea el centroide $(x,y)$ a coordenadas celestes ($\text{AR}, \text{Dec}$) usando el WCS del tiempo de referencia, listo para formatear en reporte oficial (ya sea el formato clásico de 80 columnas o el estándar moderno ADES).


## 4. Refinado de Velocidad para Calidad Profesional (*Fine-Tuning*)

Dado que las efemérides o el seguimiento de la montura pueden tener pequeñas derivas reales:

* **Micro-cuadrícula (±5%):** Una vez hecha la estimación teórica, el software prueba una variación muy estrecha (p. ej., 25 combinaciones alrededor de la velocidad base).
* **Criterio de Optimización:** Elige la combinación de velocidad que **maximiza la relación señal-ruido ($\text{SNR}$)** y la redondez del asteroide.
* **Beneficio:** Garantiza un punto perfectamente simétrico, logrando astrometría de alta precisión (error $< 0.1"$).


## 5. Gestión Lógica de "No Detección" (NEOs Tempranos / Falsos Positivos)

Si en el apilado base inicial con la velocidad teórica no se detecta ninguna fuente que supere un umbral de seguridad (p. ej., $\text{SNR} < 3.5\sigma$):

* **Cancelación de Fine-Tuning:** El software **no ejecuta el ajuste fino**, evitando así medir el "ruido de fondo" y generar falsos positivos (*overfitting*).
* **Salida de Contingencia:** Mantiene la pila teórica base, marca el objeto como `NOT_DETECTED` y puede ofrecer al observador la **magnitud límite** de la toma apilada.


## Notas sobre los algoritmos de apilado
La elección del algoritmo de combinación determina si el asteroide destacará sobre el fondo negro o si quedará oculto por el ruido y los trazos de las estrellas al realizar el *Track & Stack*.

| Método | Ventaja Principal | Inconveniente Principal | Uso en Track & Stack |
| --- | --- | --- | --- |
| **Suma (Sum) / Media (Mean)** | Máxima relación Señal/Ruido (SNR) teórica. | No elimina **ningún** artefacto. | ❌ Descartado (deja trazos de estrellas). |
| **Mediana (Median)** | Elimina trazos de estrellas rápidamente. | Pierde un ~20% de la SNR original. | 🟡 Bueno (rápido, ideal para probar). |
| **Sigma Clipped** | Combina la SNR de la media con la limpieza de la mediana. | Es computacionalmente el más lento. | ✅ El estándar profesional. |

---

### 1. Suma (Sum) / Media (Mean)

En términos de señal, sumar los píxeles o calcular su media aritmética es matemáticamente equivalente (la media es solo la suma dividida por el número de fotos).

* **Ventajas:** Si solo existiera ruido de fondo aleatorio, este método conserva el 100% de la luz del asteroide. Alcanza la máxima SNR posible dictada por la física.
* **Inconvenientes:** Promedia **todo**. Al desplazar las imágenes para seguir al asteroide, las estrellas de fondo se mueven. Con la suma o la media, esas estrellas dejan líneas brillantes (trazos) a lo largo de toda la imagen. Un asteroide débil quedará completamente invisible si cruza por encima de uno de estos trazos estelares.

### 2. Mediana (Median)

Ordena los valores de un píxel en todas las fotos y se queda con el valor del medio.

* **Ventajas:** Es excelente rechazando "eventos pasajeros". Si una estrella, un satélite o un rayo cósmico pasa por un píxel durante un par de fotos, esos valores altos quedarán en los extremos y la mediana los ignorará, dejando el píxel con el valor del cielo oscuro. Las estrellas desaparecen casi por arte de magia.
* **Inconvenientes:** Estadísticamente, calcular la mediana sobre ruido aleatorio (el fondo del cielo) penaliza la relación señal-ruido. Una imagen apilada con mediana tiene aproximadamente un **20% más de ruido de fondo** que una apilada con la media. Además, si tienes muy pocas imágenes (menos de 5), la mediana no funciona bien para eliminar las estrellas.

### 3. Sigma Clipped (Media con recorte estadístico)

Es un algoritmo híbrido e inteligente. Primero calcula la mediana de un píxel, luego mide la desviación estándar (Sigma, $\sigma$). Si el valor de ese píxel en una de las fotos se aleja demasiado (ej. está a más de $2.5\sigma$ debido a una estrella), descarta ese píxel de esa foto en concreto. Finalmente, hace una **Media (Mean)** con los valores que "sobrevivieron" al corte.

* **Ventajas:** Es el "Santo Grial". Elimina los trazos de las estrellas y satélites con la misma eficacia que la mediana, pero al hacer una media con los píxeles válidos restantes, **retiene casi el 100% de la SNR ideal**. El asteroide se verá más brillante y el fondo más suave que con la mediana.
* **Inconvenientes:** El tiempo de cálculo. Tiene que hacer múltiples iteraciones matemáticas por cada uno de los millones de píxeles. En CPU, puede ser entre 3 y 5 veces más lento que una simple mediana. Además, requiere ajustar bien los parámetros (el umbral Sigma y el número de iteraciones).
