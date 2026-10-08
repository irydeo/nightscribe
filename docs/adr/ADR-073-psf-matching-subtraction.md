# ADR-073: Host subtraction by PSF matching (optimal image subtraction)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-08

## Español

**Contexto**: la pestaña Fotometría (H2b) resta la referencia PS1 a la placa
para medir una SN sobre el núcleo de su galaxia. ADR-018 dejó la referencia
alineada «por construcción», pero la resta dejaba un punto negro en cada
estrella. La investigación (2026-10-08) midió las dos causas sobre un frame
real (AT2026acka, 2048², 1,07″/px):

1. **desajuste de registro**: la escala del cutout (pedida a la escala del
   WCS) difiere de la real en ~0,15 %, así que las estrellas caen cada vez
   más lejos hacia los bordes (dipolos adyacentes). Lo resuelve el registro
   por semejanza (`core/register`, ya en ADR-018 nota 2026-10-08);
2. **desajuste de PSF**: la observación es más ancha (FWHM ~4,7 px) que PS1
   (~4,1 px), así que la resta deja un núcleo oscuro con un anillo claro. Es
   el término dominante (~75 % del residuo) y **no lo arregla ningún
   registro**: hace falta igualar las PSF.

**Decisión**: igualar la PSF antes de restar, con un módulo propio,
`core/difference.py`, en dos capas (numpy puro, ADR-004):

1. **Igualado gaussiano dirigido por los datos**: medir la FWHM de las dos
   imágenes en las estrellas que comparten y ensanchar la referencia con la
   gaussiana diferencia, `σ = √(σ_obs² − σ_ref²)`, con la mediana sobre las
   estrellas (una estrella mala no la mueve). Un parámetro, siempre estable.
2. **Kernel óptimo (Alard & Lupton 1998; Bramich 2008)**: resolver por
   mínimos cuadrados regularizados el kernel pequeño `K` tal que
   `obs = K ⊛ ref + fondo`, sobre las estampas de las estrellas. La
   regularización es la suavidad del propio kernel (su laplaciano): sin ella
   los píxeles del kernel están tan correlacionados que el ajuste da un
   kernel puntiagudo e irreal (medido: un mínimo cuadrados crudo dio un
   núcleo de −47 donde el verdadero era +0,13).

**La capa que gana se elige por los números**: `match` calcula el residuo de
cada candidato (el RMS relativo de la resta en las estrellas, invariante a
escala porque el survey es otro filtro) y adopta el que menos deja. El
observador nunca recibe una resta peor que el igualado simple, y un kernel
que sobreensancha (alas anchas de seeing que el survey no tiene) se descarta
solo.

**El huésped extendido**: la escala que anula las estrellas se ajusta en
fuentes puntuales; el bulbo de una galaxia es extenso y de otro color (y PS1
es otro filtro), así que `obs − ganancia·ref` deja un pedestal suave sobre el
núcleo que tapa una SN sentada encima (medido en una SN real sobre NGC 7331:
residuo del núcleo 458, del bulbo 314).

**El color**: la escala `obs/ref` depende del color del objeto. Medido con
ocho comparsas en un frame real (ganancia frente a B−V):
`ganancia = 0,204 + 0,465·(B−V)`, con B−V de 0,53 a 1,03; de la comparsa azul
(0,45) a la roja (0,68) hay un **50 %**. El bulbo de NGC 7331 es rojo
(B−V≈0,9, ganancia ≈0,62) y las estrellas azules piden 0,48, así que la
escala de las estrellas (0,56) deja el bulbo sin cancelar. Por eso la escala
de la resta se ajusta **sobre los propios píxeles brillantes de la galaxia**
(fuera de las estrellas, con sigma-clip): recupera la ganancia del bulbo sin
necesitar un catálogo. Medido: el residuo del núcleo baja 399→166 y el del
bulbo 286→78, con el pico de la SN intacto (58 243). La ganancia de las
estrellas queda como reserva cuando no hay huésped extenso.

**El fondo residual**: un polinomio 2D de bajo orden, ajustado en rejilla
gruesa y con sigma-clip, se lleva lo que quede del pedestal (458→257 y
314→111 en el primer caso).

**Medido** (frame real, 80 estrellas): sin igualar 0,465; gaussiano σ=0,75
**0,353**; kernel 0,455. En este dato gana el gaussiano; en sintético el
kernel recupera el modelo al nivel del ruido (test).

**Consecuencias**: la resta es más limpia (≈25 % menos residuo aquí) y el
código es honesto sobre sus límites: no promete cero residuo, porque un
survey de otra época e instrumento no se cancela del todo con una
convolución. El coste es ~1 s por resta (una convolución gaussiana separable
+ un ajuste de kernel pequeño). El módulo es numpy puro y no toca los
píxeles del usuario (solo el survey).

**Alternativas**: (a) solo el gaussiano, más simple pero deja más residuo en
algunos campos; (b) kernel libre sin regularizar, inestable (probado: kernel
irreal); (c) `astropy`/`reproject`, prohibido por ADR-004 y de sobra para
esto.

## English

**Context**: the Photometry tab (H2b) subtracts the PS1 reference from the
plate to measure a SN on its host core. ADR-018 left the reference aligned
"by construction", but the subtraction left a black dot on every star. The
investigation (2026-10-08) measured the two causes on a real frame
(AT2026acka, 2048², 1.07″/px):

1. **registration error**: the cutout's scale (asked for at the WCS scale)
   differs from the real one by ~0.15 %, so the stars land further and
   further off toward the edges (adjacent dipoles). The similarity
   registration solves it (`core/register`, already in ADR-018 note
   2026-10-08);
2. **PSF mismatch**: the observation is broader (FWHM ~4.7 px) than PS1
   (~4.1 px), so the subtraction leaves a dark core with a bright ring. It
   is the dominant term (~75 % of the residual) and **no registration fixes
   it**: the point spreads must be matched.

**Decision**: match the PSF before subtracting, in a module of its own,
`core/difference.py`, in two layers (pure numpy, ADR-004):

1. **Data-driven Gaussian match**: measure the FWHM of the two images on the
   stars they share and broaden the reference with the difference Gaussian,
   `σ = √(σ_obs² − σ_ref²)`, with the median over the stars (one bad star
   cannot move it). One parameter, always stable.
2. **Optimal kernel (Alard & Lupton 1998; Bramich 2008)**: solve, by
   regularized least squares, the small kernel `K` such that
   `obs = K ⊛ ref + background`, over the stars' stamps. The regularization
   is the kernel's own smoothness (its Laplacian): without it the kernel
   pixels are so correlated that the fit gives a spiky, unphysical kernel
   (measured: a raw least squares gave a −47 core where the true one was
   +0.13).

**The winning layer is chosen by the numbers**: `match` computes each
candidate's residual (the relative RMS of the subtraction on the stars,
scale-invariant because the survey is another filter) and adopts the one
that leaves the least. The observer never gets a worse subtraction than the
simple match, and a kernel that over-broadens (a broad seeing halo the
survey lacks) is discarded by its own numbers.

**The extended host**: the scale that cancels the stars is fitted on point
sources; a galaxy's bulge is extended and has another colour (and PS1
another filter), so `obs − gain·ref` leaves a smooth pedestal over the core
that hides a SN sitting on it (measured on a real SN on NGC 7331: core
residual 458, bulge 314).

**The colour**: the `obs/ref` scale depends on the object's colour. Measured
with eight comps on a real frame (gain against B-V):
`gain = 0.204 + 0.465*(B-V)`, B-V from 0.53 to 1.03; from the blue comp
(0.45) to the red one (0.68) there is a **50 %** swing. NGC 7331's bulge is
red (B-V≈0.9, gain ≈0.62) and the blue stars want 0.48, so the star scale
(0.56) leaves the bulge uncancelled. The subtraction's scale is therefore
fitted **on the galaxy's own bright pixels** (outside the stars, sigma-
clipped): it recovers the bulge's gain without a catalogue. Measured: the
core's residual falls 399→166 and the bulge's 286→78, with the SN's peak
untouched (58,243). The star gain stays as the fallback when there is no
extended host.

**The residual background**: a low-order 2D polynomial, fitted on a coarse
grid and sigma-clipped, takes what is left of the pedestal (458→257 and
314→111 in the first case).

**Measured** (real frame, 80 stars): no match 0.465; Gaussian σ=0.75
**0.353**; kernel 0.455. On this data the Gaussian wins; on synthetic data
the kernel recovers the model to the noise level (test).

**Consequences**: the subtraction is cleaner (~25 % less residual here) and
the code is honest about its limits: it does not promise zero residual,
because a survey from another epoch and instrument is not fully cancelled by
a convolution. The cost is ~1 s per subtraction (one separable Gaussian
convolution + a small kernel fit). The module is pure numpy and never
touches the observer's pixels (only the survey's).

**Alternatives**: (a) the Gaussian alone, simpler but leaves more residual
on some fields; (b) a free unregularized kernel, unstable (tested: an
unphysical kernel); (c) `astropy`/`reproject`, forbidden by ADR-004 and
overkill here.
