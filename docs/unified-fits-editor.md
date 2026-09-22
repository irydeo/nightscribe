# Unified FITS Editor (UFE)

Documento de origen del requisito, escrito por el observador. El plan vivo de
implementación está en `docs/PLANS/unified-fits-editor.md`.

## Situación actual

Hasta ahora, en el software, nos encontramos con diversos puntos en los que se
cargan imágenes FITS para diversas tareas, actualmente:

* El Blink: Utilizado principalmente para las Supernovas o fenómenos transitorios.
* La carta de comparación: Utilizado para conocer las mejores estrellas para
  comparar y obtener fotometría.
* Exportación de FITS anotados

Cada uno de ellos utiliza una interfaz diferente e incluso reimplementa
funcionalidades, con diferentes opciones y salidas.

## El problema

Precisamente esa duplicidad en la implementación junto con el forzar al usuario
a conocer diferentes interfaces, es lo que genera el problema, tanto a nivel de
desarrollo, ya que estamos hablando de mantener múltiples implementaciones
actualmente y más que vendrán en el futuro; arreglamos o mejoramos algo en la
exportación, pero en el Blink sigue mal...

## El objetivo

Se trata de crear un punto único dentro del software desde el cual se
visualicen las imágenes FITS y se trabaje sobre ellas; siempre que tengamos que
visualizar, editar, procesar... una imagen, este será el control que se va a
mostrar al usuario, desde el cual se podrá hacer todo lo que el software
permite sobre las imágenes.

## Funcionalidades

### Comunes

1. La implementación ha de realizarse de tal manera que sea extensible; como
   he dicho, ahora se trata de 3 funcionalidades, pero en el futuro vendrán
   más y ha de ser fácil extender y añadirlas al Unified FITS Editor (UFE).
2. Se ha de permitir un control extremadamente fino sobre el histograma, el
   motivo es que estamos trabajando sobre objetos muy sutiles y, sobre todo
   con las supernovas, al estar muy cercanas a los núcleos galácticos, es
   necesario ajustar histogramas para poder verlas.
   - Actualmente, los ajustes del histograma se realizan sobre barras
     desplazadoras, jugando con los puntos negros, blancos, gamma... para una
     primera versión está bien, pero hemos de permitir un ajuste más fino en
     los extremos.
   - AstroimageJ usa controles visuales
     (https://github.com/AstroImageJ/astroimagej); lo cual sería ideal.
3. Se ha de permitir invertir la imagen (los blancos pasan a ser negros y
   viceversa), lo que ayuda mucho a detectar objetos débiles sobre el fondo.
4. La exportación a PNG ha de ser una funcionalidad de serie.
5. Un zoom mejorado, no limitado a que la imagen entre completamente, puede
   que nos interese una zona muy concreta.

### Concretas

1. Toda la funcionalidad ahora disponible relativa a Blink, carta de
   comparación y anotaciones.

## Diseño y componentes

Se propone un diseño similar a este:

```
 _______________________________________________
|        Funcionalidades comunes               |
| _____________________________________________|
|                          |  Blink/Comp/Label |
|                          |                   |
| IMAGEN                   |  Controles por tab|
|                          |___________________|
|                          | Funcionalidades   |
|                          |     comunes       |
|__________________________|___________________|
|Histograma Visual o como ahora               |
|_____________________________________________|
```

La imagen ha de ocupar la mayoría del espacio disponible, a su derecha han de
aparecer los controles para editarla o trabajarla. En la parte superior, los
concretos, una tab para cada funcionalidad: Blink, Comparación, Anotar...
Justo debajo de las tabs anteriores, los controles generales, comunes a todas
las funcionalidades (otra opción es poner estos controles arriba, en forma de
iconos que al pulsarlos muestren los controles, por eso los he puesto en ambos
lados, para ver la mejor).

## Notas

1. Inicialmente, el Unified FITS Editor (UFE) va a convivir con las
   funcionalidades actuales, no las va a reemplazar; el único punto de entrada
   a él será una entrada en el menú herramientas.
2. Todo el desarrollo en la rama feature/ufe desde main.

## Fases

A. Creación del Unified FITS Editor (UFE): Carga de una imagen FITS
B. Implementación del histograma.
C. Implementación de las funcionalidades comunes.
D. Migración e integración de las funcionalidades concretas ya implementadas:
   Anotaciones.
E. Migración e integración de las funcionalidades concretas ya implementadas:
   Blink.
F. Migración e integración de las funcionalidades concretas ya implementadas:
   Comparación Fotométrica.
