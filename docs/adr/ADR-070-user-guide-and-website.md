# ADR-070: La guía de usuario y la web: una fuente, dos renderizados / The user guide and the website: one source, two renderings

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-08
**Ver / See**: ADR-005 (la interfaz en los `.ui`), ADR-013 (documentación bilingüe),
ADR-026 (la identidad visual), ADR-053 (el visor de documentación), ADR-058 (nada
sin explicación)

## Español

**Contexto**: la guía de usuario vive en `docs/user/` (índice y doce capítulos,
cada uno en español e inglés) y la aplicación la muestra en **Ayuda →
Documentación técnica** con su propio conversor de markdown (`gui/markdown.py`),
sin dependencias. La carpeta `website/` era otra cosa: una landing escrita a
mano, con una paleta cálida que ya no coincidía con la de la app, su propio
diccionario de textos en JavaScript y un taller de capturas que apuntaba al
shell de pestañas retirado en la Interfaz 1.0. Nadie la regeneraba, así que
contaba una historia distinta de la de la guía y de la del README.

**Decisión**: **una sola fuente, dos renderizados.**

1. **El texto se escribe una vez.** La landing es `README.md` / `README.es.md`
   y el manual es `docs/user/*.md`. La app los pinta como siempre; un
   generador (`website/tools/build_site.py`) los convierte en HTML estático.
   La prosa no se copia en ningún sitio.
2. **La identidad tampoco se copia.** El generador lee la paleta de
   `nightscribe/gui/theme.py` y los tipos de objetivo de `core/kinds.py` (con
   su español del catálogo `.ts`) y los inyecta en el CSS y en las tarjetas:
   la web habla los mismos colores y las mismas fichas que la app.
3. **La web es una landing y una guía.** La landing (una página por idioma,
   con navegación por secciones) responde qué es y qué hace: el héroe con el
   cielo de la app, la definición del README, los tipos como tarjetas con su
   chip, el detalle en acordeón y el índice de capítulos. La guía (una página
   por capítulo y idioma) lleva barra lateral, anterior/siguiente, anclas por
   encabezado y las cajas «Why …?» como *callouts*. El cromo es oscuro (el de
   la app) y la página de lectura es clara, que es como la app muestra un
   documento.
4. **El HTML se commitea y un test lo vigila.** La web funciona desde una
   carpeta, sin build, y `tests/unit/test_site_build.py` la regenera en un
   temporal y la compara byte a byte: editar la guía y no reconstruir falla en
   la suite en vez de publicar una página vieja. El mismo test comprueba que
   ningún enlace interno apunta a un fichero que no está, que cada capítulo
   tiene sus dos páginas y que no se carga nada de fuera.
5. **En el programa**, **Ayuda → Guía de usuario (web)** abre la página
   publicada en el navegador del sistema, en el idioma de la app. El visor
   interno sigue siendo la puerta sin red; esta es la que se lee en el móvil o
   se manda a alguien.
6. **Se publica sola**: `.github/workflows/pages.yml` construye la web y la
   sube a GitHub Pages en cada push a `main` o `release/v0.1` (y a mano). Lo
   que se publica es la SALIDA del generador, así que un commit olvidado no
   puede sacar una copia rancia.

**Alternativas**: una landing escrita a mano (es lo que había: se desincroniza
y acaba diciendo algo distinto que la guía); un generador de sitios estático
(pide una dependencia para un subconjunto de markdown que el proyecto ya
sabe leer, y abre un segundo dialecto); mostrar el HTML generado dentro de la
app (el CSS que entiende `QTextBrowser` es un subconjunto: la app ya tiene su
propio render, adaptado a ella, y compartir la fuente es lo que importa).

**Consecuencias**: la web **se regenera, no se edita**: la hoja de estilos y
el JavaScript se tocan en `website/tools/` (`site.css`, `site.js`), nunca en
`website/assets/`, que es salida. Un capítulo nuevo aparece en la web con solo
añadir su fila al índice de la guía, que es también lo que lista la app. La web
antigua, su taller de capturas y su paleta se retiran (el historial de git los
conserva). El despliegue pide activar Pages una vez en el repositorio
(*Source: GitHub Actions*).

**Revisión (2026-10-08, las capturas).** La web muestra **capturas reales** de
la aplicación, tomadas a mano con los datos del observador: no son maquetas. Se
preparan con `website/tools/prepare_screens.py`, que las reduce a 1400 px y las
pasa a WebP (una captura de la interfaz oscura de 2181 px pesa 2,9 MB; la misma
a 1400 px y calidad 92 pesa 240 KB, sin pérdida visible al tamaño que la página
las muestra) y las deja en `website/assets/screens/`. El generador dibuja la
figura de un capítulo **solo si el fichero existe**, así que las capturas pueden
llegar de una en una y la página nunca queda rota. La aplicación no se toca: su
visor interno sigue sin imágenes.

**Revisión (2026-10-08, el móvil).** La web se midió a 320, 360, 390 y 430 px
con Chrome headless (dentro de un iframe, porque headless no maqueta por debajo
de 500) y salieron dos desbordes que en escritorio no se ven: la guía medía
**1764 px** en una pantalla de 390 (los enlaces del índice son `nowrap` y la
rejilla no podía encogerse por debajo de su contenido) y la portada **754** (un
bloque de código sin scroll propio). Ahora la rejilla de la guía usa
`minmax(0, 1fr)`, las cuatro rejillas `minmax(min(100%, X), 1fr)`, los bloques
de código llevan su propio scroll en cualquier sitio, el índice se pliega en
móvil (un `<details>` nativo) y el nombre de la marca cede por debajo de 420 px.
El menú de secciones, que la fila de enlaces no cabe en un móvil, pasa a un
`<details>` con el mismo contenido (sin JavaScript queda abierto; con él se
cierra al elegir una sección). `website/tools/check_mobile.py` repite la
medición y falla si una página desborda o si un titular no cabe en su caja
(el de la portada se cortaba a 320); la suite vigila las reglas del CSS que lo
hacen verdad.

**Revisión (2026-10-08, el reporte de fallos).** El enlace a la página de
incidencias del repositorio está **arriba y abajo**: en la barra, junto al
idioma, y en el pie de todas las páginas, en el idioma de la página; el README
lleva la misma línea en su sección de documentación.

**Revisión (2026-10-08, la puerta de la guía en la Bienvenida).** El botón «Ver
la guía completa» de la Bienvenida abría el visor interno de markdown; ahora
abre la guía **HTML** publicada (la misma página que Ayuda → Guía (web), en el
idioma de la app). La puerta general a la documentación dentro de la app
desaparece con él: el visor interno solo sobrevive donde abre un documento
concreto (el «?» de la serie en el UFE).

**Revisión (2026-10-15, la puerta offline vuelve).** El visor interno recupera una
puerta en la ventana principal: **Ayuda → Guía (offline)**, que abre la guía que
viaja dentro de la instalación, sin red. No es la puerta general que se retiró:
abre la guía, no cualquier documento, y su razón es el observatorio sin conexión,
que no tenía forma de llegar al manual desde la app aunque los `.md` viajen
empaquetados (el hueco que dejó la revisión de 2026-10-08). La guía web sigue
siendo la puerta principal y la que abre la Bienvenida.

## English

**Context**: the user guide lives in `docs/user/` (an index and twelve chapters,
each in Spanish and English) and the application shows it in **Help →
Technical Documentation** with its own markdown converter
(`gui/markdown.py`), dependency-free. The `website/` folder was something
else: a hand-written landing with a warm palette that no longer matched the
app's, its own JavaScript dictionary of texts and a screenshot pipeline aimed
at the tab shell retired in Interfaz 1.0. Nothing regenerated it, so it told a
different story from the guide's and the README's.

**Decision**: **one source, two renderings.**

1. **The text is written once.** The landing is `README.md` /
   `README.es.md` and the manual is `docs/user/*.md`. The app paints them as
   always; a generator (`website/tools/build_site.py`) turns them into static
   HTML. No prose is copied anywhere.
2. **The identity is not copied either.** The generator reads the palette from
   `nightscribe/gui/theme.py` and the target kinds from `core/kinds.py` (with
   their Spanish from the `.ts` catalogue) and injects them into the CSS and
   the cards: the site speaks the same colours and the same cards as the app.
3. **The site is a landing and a guide.** The landing (one page per language,
   navigation by sections) answers what it is and what it does: the hero with
   the app's sky, the README's definition, the kinds as cards with their chip,
   the long chapter folded into an accordion and the chapter index. The guide
   (one page per chapter per language) carries a sidebar, previous/next,
   heading anchors and the "Why …?" boxes as callouts. The chrome is dark (the
   app's) and the reading page is light, which is how the app shows a
   document.
4. **The HTML is committed and a test watches it.** The site works from a
   folder, with no build, and `tests/unit/test_site_build.py` regenerates it
   into a temporary folder and compares it byte by byte: editing the guide and
   not rebuilding fails the suite instead of publishing a stale page. The same
   test checks that no internal link points at a file that is not there, that
   every chapter has its two pages, and that nothing is loaded from outside.
5. **In the program**, **Help → User guide (web)** opens the published page in
   the OS browser, in the app's language. The in-app viewer stays the offline
   door; this one is what you read on a phone or send to somebody.
6. **It publishes itself**: `.github/workflows/pages.yml` builds the site and
   uploads it to GitHub Pages on every push to `main` or `release/v0.1` (and on
   demand). What goes live is the generator's OUTPUT, so a forgotten commit
   cannot ship a stale copy.

**Alternatives**: a hand-written landing (that is what there was: it drifts,
and ends up saying something different from the guide); a static site
generator (a dependency for a markdown subset the project already reads, and a
second dialect); showing the generated HTML inside the app (`QTextBrowser`
understands a subset of CSS: the app already has its own render, adapted to
it, and sharing the source is what matters).

**Consequences**: the site is **regenerated, not edited**: the stylesheet and
the JavaScript are touched in `website/tools/` (`site.css`, `site.js`), never
in `website/assets/`, which is output. A new chapter appears on the site by
adding its row to the guide's index, which is also what the app lists. The old
website, its screenshot pipeline and its palette are removed (git's history
keeps them). The deployment asks for enabling Pages once in the repository
(*Source: GitHub Actions*).

**Revision (2026-10-08, the screenshots).** The site shows **real captures** of
the application, taken by hand with the observer's own data: they are not
mockups. They are prepared with `website/tools/prepare_screens.py`, which
resizes them to 1400 px and converts them to WebP (a 2181 px capture of the
dark interface weighs 2.9 MB; the same at 1400 px and quality 92 weighs
240 KB, with no visible loss at the size the page shows them) and leaves them
in `website/assets/screens/`. The generator draws a chapter's figure **only
when its file exists**, so the captures can arrive a few at a time and the page
is never broken. The application is untouched: its in-app viewer still shows
no images.

**Revision (2026-10-08, the phone).** The site was measured at 320, 360, 390
and 430 px with headless Chrome (inside an iframe, because headless will not
lay out a viewport narrower than 500) and two overflows came out that are
invisible on a desktop: the guide measured **1764 px** on a 390 px screen (the
contents' links are `nowrap` and the grid could not shrink below its content)
and the landing **754** (a code block without its own scroll). The guide's grid
now uses `minmax(0, 1fr)`, the four grids `minmax(min(100%, X), 1fr)`, the code
blocks carry their own scroll wherever they are, the contents fold away on a
phone (a native `<details>`) and the brand's name steps aside below 420 px.
The sections menu, which the links row cannot hold on a phone, becomes a
`<details>` with the same content (open with no JavaScript; the script closes
it when a section is picked). `website/tools/check_mobile.py` repeats the
measurement and fails when a page overflows or when a heading does not fit its
own box (the landing's was cut at 320); the suite watches the CSS rules that
make it true.

**Revision (2026-10-08, reporting a bug).** The link to the repository's issue
tracker sits **at the top and at the bottom**: in the bar, next to the
language, and in the footer of every page, in the page's language; the README
carries the same line in its documentation section.

**Revision (2026-10-08, the guide's door on Welcome).** Welcome's "See the full
guide" button opened the in-app markdown viewer; it now opens the published
**HTML** guide (the same page as Help > User guide (web), in the app's
language). The general in-app door to the documentation goes away with it: the
in-app viewer only survives where it opens one concrete document (the UFE
series "?").

**Revision (2026-10-15, the offline door returns).** The in-app viewer gets a
door back in the main window: **Help > User guide (offline)**, which opens the
guide the install carries, with no network. It is not the general door that was
removed: it opens the guide, not any document, and its reason is the observatory
with no connection, which had no way to reach the manual from the app even though
the `.md` files travel inside the packages (the gap the 2026-10-08 revision left).
The web guide is still the main door and the one Welcome opens.

**Revision (2026-10-16, the offline manual is a manual and the advanced guide is its own
section).** The in-app viewer listed every `.md` under `docs/`, ADRs and work plans
included, so the manual opened on a list of design records. It now shows, in the app's
own language, the **user guide** and the two topic documents its "?" buttons open (UFE,
SEQUENCES), with the topic documents for enthusiasts and the design decisions behind a
**collapsed "Advanced documentation" branch**; the work plans (`docs/PLANS`) are not
listed at all. The same split is on the website: a new **Advanced guide** section
(`build_advanced`) publishes one page per topic document, grouped into "How it is built"
and "How the science is done", plus an index of the ADRs linked to the repository, where
they are readable as they are; the work plans stay in the repository. The guide's
sidebar and the landing link to it.

**Revisión (2026-10-16, el manual offline es un manual y la guía avanzada tiene su
sección).** El visor de la app listaba todos los `.md` de `docs/`, ADRs y planes de
trabajo incluidos, así que el manual se abría con una lista de registros de diseño.
Ahora muestra, en el idioma de la app, la **guía de usuario** y los dos documentos de
tema que abren sus botones «?» (UFE, SEQUENCES), con los documentos de tema para
entusiastas y las decisiones de diseño tras una **rama «Documentación avanzada»
plegada**; los planes de trabajo (`docs/PLANS`) no se listan. La misma división está en
la web: una sección nueva **Guía avanzada** (`build_advanced`) publica una página por
documento de tema, agrupadas en «Cómo está construido» y «Cómo se hace la ciencia», más
un índice de los ADRs enlazados al repositorio, donde se leen tal cual; los planes se
quedan en el repositorio. El lateral de la guía y la landing enlazan con ella.

**Revisión (2026-10-17, la landing es más corta y los enlaces externos no se tocan)**: el
README **es** la landing, así que todo lo que engorda al README engorda a la portada. Tenía
606 líneas y la mitad (277) eran «What you can do: in detail», que es justo lo que la guía
cuenta capítulo a capítulo; ahora son **220** líneas: el detalle vive en la guía (con
enlaces a los capítulos), las fuentes de datos en una lista corta que enlaza
`docs/DATA_SOURCES.md`, y la noche completa y la CLI se resumen en unas pocas líneas con su
enlace. Con eso desaparece el acordeón de la portada (`DETAIL_SECTION` y `_accordion` se
retiran de `build_site.py`). Y dos arreglos en el generador: **una URL absoluta nunca se
reescribe** (el enlace de la guía a `INSTALL.md` salía como `.../blob/main/INSTALL.html`,
un 404, porque el reescritor trataba una URL de GitHub como si fuera un capítulo; el
mismo agujero estaba en los tres reescritores) y un enlace `../` apunta a la **raíz del
repositorio**, no a `docs/` (el enlace a `AGENTS.md` de los documentos de tema salía como
`docs/AGENTS.md`, otro 404). Los guardianes: una URL absoluta no se toca, y **ningún enlace
a nuestro propio repositorio puede apuntar a un fichero que no exista con esa extensión**
(el test de enlaces roto saltaba los `http`, que es por lo que los dos pasaron).

**Review (2026-10-17, the landing is shorter and external links are left alone)**: the
README **is** the landing, so everything that fattens the README fattens the front page. It
had 606 lines and half of them (277) were "What you can do: in detail", which is exactly
what the guide tells chapter by chapter; it is **220** now: the detail lives in the guide
(with links to the chapters), the data sources are a short list linking
`docs/DATA_SOURCES.md`, and the whole night and the CLI are a few lines with their link.
The landing's accordion goes with it (`DETAIL_SECTION` and `_accordion` are removed from
`build_site.py`). And two fixes in the generator: **an absolute URL is never rewritten**
(the guide's link to `INSTALL.md` shipped as `.../blob/main/INSTALL.html`, a 404, because
the rewriter treated a GitHub URL as a chapter; the same hole was in all three rewriters)
and a `../` link points at the **repository root**, not at `docs/` (the topic documents'
link to `AGENTS.md` shipped as `docs/AGENTS.md`, another 404). The guards: an absolute URL
is left alone, and **no link to our own repository may point at a file that does not exist
with that extension** (the broken-links test skipped `http`, which is why both passed).
