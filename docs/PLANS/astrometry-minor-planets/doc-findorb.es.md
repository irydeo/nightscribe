# Find_Orb: qué es, cómo se instala y cómo lo usa NightScribe

> Sección de usuario del par `docs/ASTROMETRY.es.md` / `docs/ASTROMETRY.md`
> (fase 10 del plan). Aquí se documenta con todo el detalle para que el
> observador pueda montarlo sin ayuda. La versión inglesa es
> `doc-findorb.md`, hermana de este fichero.

## 1. Qué es Find_Orb y por qué lo usa NightScribe

**Find_Orb** es un programa de Bill Gray (Project Pluto) que determina la órbita
de un asteroide, un cometa o un satélite a partir de sus observaciones
astrométricas. Está probado por la comunidad desde hace años y es lo que
recomienda el propio Minor Planet Center.

NightScribe **no reimplementa el ajuste de órbitas**: sería reinventar la
rueda, y peor. Lo que hace es usar Find_Orb como árbitro del chequeo de
calidad: le pasa las observaciones del objeto (las nuestras y las de los demás
observadores) y lee qué residual tienen las nuestras contra la órbita que sale
de las otras. Si nuestro punto encaja, la medida es sólida; si se sale de la
nube, se avisa antes de enviarla al MPC.

Por qué esto importa: el apilado (track & stack) puede fabricar detecciones
fantasma. El MPC lo advierte y explica que un tracklet falso en el NEOCP puede
hacer que el objeto se pierda. Ver el objeto (la secuencia centrada) y
comprobarlo contra los demás (Find_Orb) son las dos redes de seguridad.

NightScribe **no distribuye Find_Orb**: solo detecta tu copia y la ejecuta,
igual que hace con ASTAP para resolver la placa. La licencia de Find_Orb es
GPL-2.0-or-later.

## 2. Instalación

### 2.1 Linux (y macOS): la vía fácil, conda-forge

Hay un paquete con **binarios ya compilados** para Linux y macOS, así que no
hace falta compilar nada:

```bash
conda install -c conda-forge findorb
# o, con micromamba (más ligero):
micromamba install -c conda-forge findorb
# o, con pixi:
pixi add findorb
```

El paquete instala **dos ejecutables**:

- `fo`: la versión **no interactiva**, que es la que usa NightScribe.
- `find_orb`: la versión interactiva, para mirar las cosas a mano.

Y arrastra **`findorb-data-de430t`**, las efemérides del JPL DE430t que
Find_Orb necesita para las perturbaciones. Se instala sola como dependencia.

Después de instalarlo, comprueba que existe:

```bash
which fo
```

Si tu procesador es ARM (aarch64) y el paquete no estuviera disponible para esa
arquitectura, usa la compilación de la sección 2.3.

### 2.2 Windows: binarios listos

En la página de descargas de Find_Orb
(`https://www.projectpluto.com/find_orb.htm`) descarga:

1. La **versión de consola** (64 bits): `find_c64.zip`. Descomprímela en una
   carpeta propia, por ejemplo `C:\Find_Orb`.
2. El **ejecutable no interactivo** `fo64.exe`, desde el enlace de descarga
   de `fo` de esa misma página, y déjalo **en la misma carpeta** que la
   consola. Find_Orb comparte con `fo` la configuración y los ficheros de
   efemérides, así que tienen que vivir juntos.

En NightScribe apuntarás al fichero `fo64.exe` (sección 3).

### 2.3 Compilar desde el código fuente (Linux, BSD, macOS)

La vía oficial para Linux, si no quieres conda: el código está en GitHub
(`https://github.com/Bill-Gray/find_orb`) y las instrucciones de compilación
están en `https://www.projectpluto.com/find_sou.htm`. En resumen, se clonan
cuatro repositorios **uno al lado del otro** (`find_orb`, `lunar`, `jpl_eph`,
`sat_code`), se construyen en orden (`lunar`, `jpl_eph`, `lunar` con
integración, `sat_code` y `find_orb`), y hacen falta `ncurses` y `zlib`. Es la
misma receta que sigue el paquete de conda-forge, que puedes usar como
referencia exacta.

## 3. Configurarlo en NightScribe

1. Abre **Ajustes** y ve a la zona de **Calibración** (o a «Site & equipment»).
2. En el campo **Find_Orb** elige el ejecutable:
   - Linux/macOS: `fo` (no `find_orb`, que es el interactivo).
   - Windows: `fo64.exe`.
3. Pulsa **Probar**. NightScribe lanza el binario sobre un fichero de
   observaciones de ejemplo y comprueba que responde. Si algo falla, te dice
   qué (no existe, no es el `fo`, no arranca).
4. Deja activada la casilla de ejecutarlo automáticamente. Si prefieres no
   lanzarlo, NightScribe solo escribirá el fichero de observaciones para que lo
   abras tú a mano.

Si no configuras nada, el chequeo **no está disponible**: la app te lo dice en
la ficha, y las redes de seguridad que quedan son la secuencia centrada y el
umbral de SNR. Nunca finge un chequeo que no ha hecho.

## 4. Qué hace NightScribe con Find_Orb, paso a paso

1. **Baja las observaciones del objeto**: las publicadas en el MPC, o las del
   NEOCP si aún no está confirmado. Son datos públicos; no se sube nada tuyo.
2. **Escribe un fichero** con las nuestras y las de los demás, en formato
   ADES PSV (o 80 columnas).
3. **Lanza `fo`** en una carpeta temporal, con dos precauciones:
   - `-D <fichero de entorno>`: usa una configuración propia, para que el
     resultado no dependa de lo que tengas tú en `~/.find_orb`.
   - `-r 60,65`: límite de tiempo de CPU (avisa a los 60 s y mata a los 65),
     para que un ajuste atascado no cuelgue la app.
4. **Lee `total.json`**, el fichero donde `fo` escribe los elementos, las
   observaciones y **los residuos de cada una**. De ahí salen nuestros
   residuos y los de los demás.
5. **Decide**: compara nuestro residuo con la dispersión de los demás
   (robusta, para que un observador malo no infle el listón) y con nuestra
   propia incertidumbre. Si estamos muy fuera, bloquea el reporte por defecto;
   puedes forzarlo, y queda escrito que lo forzaste.
6. **Te enseña** el residuo, la dispersión, cuántos observatorios hay y el
   veredicto, con una explicación de qué significa cada cifra.

Para que el chequeo sea un *leave-one-out* de verdad, las nuestras se excluyen
del ajuste: Find_Orb calcula la órbita solo con las de los demás y luego dice
qué residual tienen las nuestras. Eso es exactamente lo que hace Tycho-Tracker.

## 5. Qué verás en la pantalla

- **Residual propio**: cuánto se separa nuestra medida de lo que predice la
  órbita, en segundos de arco.
- **Dispersión de los demás**: cuánto se separan ellos. Es la escala justa:
  con una órbita mala todos los residuos son grandes, y lo que importa es si
  estamos **fuera de la nube**.
- **Observatorios distintos** que han visto el objeto y **fecha de la última
  observación** (esto se ve también en la ficha del objeto).
- **Veredicto**: `ok`, `outlier` (bloquea, se puede forzar), `sin referencia`
  (no hay otras observaciones con las que comparar) o `no disponible` (no hay
  Find_Orb configurado).

## 6. Solución de problemas

- **«No disponible» aunque tengo Find_Orb.** Casi siempre es que has apuntado
  al interactivo (`find_orb`) en vez de al no interactivo (`fo` o `fo64.exe`).
- **La primera ejecución crea `~/.find_orb`.** Es normal: Find_Orb prepara su
  carpeta de configuración la primera vez. NightScribe no toca tu configuración
  porque usa `-D`.
- **`fo` escribe ficheros donde se ejecuta.** NightScribe lo lanza en una
  carpeta temporal y recoge `total.json` de ahí; no ensucia tu proyecto.
- **El objeto no tiene otras observaciones.** Un descubrimiento real no tiene
  con qué compararse: verás `sin referencia`, y no bloquea. Deciden el SNR y la
  secuencia centrada.
- **Un objeto recuperado tras meses.** Su órbita puede haber derivado; un
  residuo grande puede ser de la órbita, no tuyo. Por eso el veredicto se apoya
  en la dispersión de los demás y no en un número absoluto.
- **`fo` no converge.** Con arcos muy cortos puede no sacar una órbita útil; el
  chequeo lo marca como referencia débil y no bloquea. El MPC avisa de lo
  mismo: en un arco corto, una observación errónea encaja igual.
- **Windows: SmartScreen o el antivirus.** Un ejecutable descargado de internet
  puede dar aviso la primera vez; permite el fichero en tu carpeta de Find_Orb.

## 7. Privacidad, red y licencia

- **Red**: NightScribe baja las observaciones del objeto del MPC (datos
  públicos). Find_Orb se ejecuta **en tu máquina** y no necesita red: las
  efemérides DE430t son locales.
- **Lo tuyo no se sube**: el envío al MPC lo haces tú, como siempre.
- **Licencia**: Find_Orb es GPL-2.0-or-later. NightScribe no lo distribuye ni
  lo empaqueta; solo detecta y ejecuta tu copia, igual que con ASTAP.
