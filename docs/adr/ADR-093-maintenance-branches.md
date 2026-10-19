# ADR-093: Ramas de mantenimiento: parches de una línea ya publicada

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-19

## Español

**Contexto**: la 0.1.0 está publicada y un observador encontró un fallo real: en
una placa normalizada (un master de PixInsight en coma flotante 0..1, que es lo
que exportan PixInsight y Siril por defecto) la propuesta de comparsas devolvía
**cero** estrellas y el error de la fotometría salía de **52 magnitudes** (ADR-066
lleva la medida). El arreglo tiene que llegar **a la versión publicada**, que es
la que sufre el fallo, y también a `main`, que es donde se construye la 0.2.

Hasta hoy el proceso de release de `CONTRIBUTING` describe **una sola línea**:
se aterriza en `main` y se etiqueta. Eso vale para una release, no para un
parche: si el parche entra sólo en `main`, la 0.1.1 no se puede construir sin
arrastrar todo lo que `main` haya ganado por el camino; y si entra sólo en una
rama, `main` se queda con el fallo. No había nada escrito sobre ramas: las que
existen (`release/v0.1-hardening`, `release/v0.1.0`) son de **preparación** de
una release, se fusionan y mueren.

**Decisión**:

1. **Una rama de mantenimiento por línea de versión**: `release/vX.Y.x`. Nace
   del tag de la release que mantiene (o de `main`, que en ese momento es el
   mismo commit) y **vive mientras esa línea sea la publicada**. Se congela o se
   borra cuando sale la siguiente menor.
2. **El parche se hace EN la rama**, no en `main`: es la rama que se etiqueta y
   por tanto la que se construye. Así los artefactos de la 0.1.1 son
   exactamente «0.1.0 + los parches», y nada más.
3. **El tag se corta desde la rama** (`vX.Y.Z`). `release.yml` construye desde el
   commit etiquetado, y el job de test falla si la versión construida no coincide
   con el tag, así que la release no puede llevar otro contenido.
4. **Todo lo que entra en la rama se hace cherry-pick a `main` el mismo día.**
   Es la mitad que impide que las dos líneas se separen. El fichero que entra en
   conflicto es siempre el `CHANGELOG` (la sección nueva se inserta justo debajo
   de `[Unreleased]`, que es donde `main` acumula lo suyo), así que el
   cherry-pick se hace pronto: mientras el `[Unreleased]` de `main` esté intacto,
   entra limpio.
5. La dirección del flujo es por tanto **arreglar en la rama y adelantar a
   `main`** (el `hotfix` clásico), y no al revés.

**Consecuencias**:

- Hay dos sitios donde mirar, y el cherry-pick es manual: una regla de proceso
  que sólo funciona si se cumple el punto 4 el mismo día.
- Después del cherry-pick, `main` sigue diciendo `<siguiente>.devN` (el commit
  del cherry-pick no desciende del tag). Es lo correcto: `main` es desarrollo, y
  la versión publicada es la del tag.
- El apartado Release de `CONTRIBUTING` gana la mecánica del parche, porque el
  orden se invierte (etiquetar desde la rama y después adelantar a `main`).
- Un parche puede necesitar tocar los dos ficheros del arreglo y sus tests; el
  ADR no cambia eso, sólo dice dónde vive el commit.

**Alternativas**:

- **Una rama por parche** (`release/v0.1.1`, `release/v0.1.2`...): descartada.
  Funciona para un parche suelto, pero no hay un sitio donde se vea la línea, y
  con tres parches hay tres ramas que se olvidan.
- **Arreglar en `main` y backportear a la rama**: descartada aquí. Es mejor
  cuando el tronco va a refactorizar justo esos ficheros, porque entonces el
  backport es el que duele; en este caso `photometry` y `compstars` están en la
  lista de «no tocar» de la auditoría de la 0.1, así que el riesgo es bajo y lo
  que manda es que la línea publicada sea construible de una pieza.
- **Etiquetar desde `main`** (lo que hace el proceso actual): descartada para un
  parche, por el motivo del contexto: la 0.1.1 arrastraría el desarrollo de la
  0.2.

## English

**Context**: 0.1.0 is out and an observer found a real bug: on a normalised
plate (a PixInsight master in 32-bit float, 0..1, which is what PixInsight and
Siril write by default) the comparison-star proposal returned **zero** stars and
the photometry error came out as **52 magnitudes** (ADR-066 carries the
measurement). The fix has to reach **the published version**, which is the one
that suffers the bug, and also `main`, where 0.2 is being built.

Until today the release process in `CONTRIBUTING` describes **a single line**:
land on `main` and tag. That works for a release, not for a patch: if the patch
only lands on `main`, 0.1.1 cannot be built without dragging in everything
`main` has gained on the way; and if it only lands on a branch, `main` keeps the
bug. Nothing was written about branches: the ones that exist
(`release/v0.1-hardening`, `release/v0.1.0`) **prepare** a release, get merged
and die.

**Decision**:

1. **One maintenance branch per version line**: `release/vX.Y.x`. It is born
   from the tag of the release it maintains (or from `main`, which is the same
   commit at that moment) and **lives while that line is the published one**. It
   is frozen or deleted when the next minor comes out.
2. **The patch is made ON the branch**, not on `main`: the branch is what gets
   tagged and therefore what gets built. That way the 0.1.1 artifacts are
   exactly "0.1.0 + the patches", and nothing else.
3. **The tag is cut from the branch** (`vX.Y.Z`). `release.yml` builds from the
   tagged commit, and the test job fails when the built version does not match
   the tag, so a release cannot carry other content.
4. **Everything that lands on the branch is cherry-picked to `main` the same
   day.** That is the half that keeps the two lines from drifting apart. The
   file that always conflicts is the `CHANGELOG` (the new section is inserted
   right below `[Unreleased]`, which is where `main` accumulates its own), so
   the cherry-pick is done early: while `main`'s `[Unreleased]` is untouched, it
   applies cleanly.
5. The direction of the flow is therefore **fix on the branch and forward to
   `main`** (the classic hotfix), not the other way round.

**Consequences**:

- There are two places to look, and the cherry-pick is manual: a process rule
  that only works if point 4 is honoured the same day.
- After the cherry-pick, `main` still reports `<next>.devN` (the cherry-picked
  commit does not descend from the tag). That is correct: `main` is development,
  and the published version is the tag's.
- The Release section of `CONTRIBUTING` gains the patch mechanics, because the
  order is reversed (tag from the branch, then forward to `main`).
- A patch may need to touch the fix's two files and their tests; the ADR does
  not change that, it only says where the commit lives.

**Alternatives**:

- **One branch per patch** (`release/v0.1.1`, `release/v0.1.2`...): rejected. It
  works for a single patch, but there is no one place where the line is visible,
  and with three patches there are three branches that get forgotten.
- **Fix on `main` and backport to the branch**: rejected here. It is better when
  the trunk is about to refactor those very files, because then the backport is
  the painful one; in this case `photometry` and `compstars` are on the "do not
  touch" list of the 0.1 audit, so the risk is low and what matters is that the
  published line is buildable in one piece.
- **Tag from `main`** (what the current process does): rejected for a patch, for
  the reason in the context: 0.1.1 would drag 0.2's development along.
