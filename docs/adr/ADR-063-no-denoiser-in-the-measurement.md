# ADR-063: Ningún denoiser de IA en el camino de la medida

**Estado / Status**: Accepted · **Fecha / Date**: 2026-10-05

## Español

**Contexto**: la campaña de SNR (`docs/PLANS/astrometry-snr/`) busca
detectar y medir objetos más débiles. Existen herramientas de reducción de
ruido con redes neuronales, muy usadas en astrofotografía de presentación,
con interfaz de línea de comandos que se podría invocar desde la app
(por ejemplo NoiseXTerminator, de pago). La pregunta del autor fue directa:
¿lo integramos para medir más débil?

**Decisión**: **no**. Un denoiser de IA no entra en el camino de la medida
(astrometría ni fotometría), y si algún día entra en la app es **solo para
presentación**, como herramienta externa opcional del usuario, apagada por
defecto, con su salida **rechazada** por el camino de la medida.

Las razones, en orden de peso:

1. **Rompe el modelo de error.** La ecuación CCD, la dispersión medida y las
   incertidumbres `rmsRA`/`rmsDec` que se envían al MPC suponen **ruido
   blanco**. Un filtro no lineal **correlaciona** el ruido: la dispersión
   medida después sale optimista y las incertidumbres dejan de ser ciertas.
   Enviar una incertidumbre que no es la real es peor que no enviar el dato.
2. **Puede mover el centroide.** La astrometría vive del centroide
   subpíxel. Cualquier filtro espacial no lineal puede sesgarlo, y el sesgo
   entra directo en la posición que se publica.
3. **El suelo del MPC existe por esto.** El MPC exige SNR ≥ 20 por
   observación y prohíbe las detecciones marginales precisamente para que no
   se cuelen fantasmas: un tracklet falso en el NEOCP puede hacer que el
   objeto se pierda. Subir el SNR con un denoiser es **exactamente** lo que
   ese suelo quiere evitar. NightScribe tiene además su propia red: la
   secuencia centrada en el objeto y el chequeo con Find_Orb.
4. **No es comparable con lo que ya hacemos.** El filtro adaptado (ADR-062,
   decisión 18) sube el SNR de **1,55 a 1,63×** sobre datos reales **sin
   tocar la estadística del ruido**: es el óptimo lineal, tiene una fórmula
   y se puede comprobar. Un denoiser cambia los píxeles y su ganancia no es
   verificable con una cuenta.
5. **Práctico**: es de pago, exige AVX y, en Linux, sus requisitos hablan de
   PixInsight, así que su CLI puede no correr en la máquina del observador.
   Sería la primera dependencia de pago (ASTAP, EXOTIC y Find_Orb son
   gratis/GPL).

**Dónde sí ayudaría, honestamente**: en los productos de **presentación**
(las figuras del post, la animación de parpadeo, la carta). Ahí la estética
es el objetivo y la medida no se toca. Si se integra, será por esa puerta y
con esa etiqueta.

**Cómo se decide si algún día entra**: con el instrumento de **inyección y
recuperación** (P4 del plan). Se inyecta una fuente móvil de SNR conocido en
las tomas reales, se mide con y sin el denoiser, y se comparan el **error de
centroide** y la **tasa de recuperación**. Si no bate al filtro adaptado, no
entra. La intuición no decide esto: los datos sí.

**Alternativas**: integrarlo en el camino de la medida (rechazado por los
puntos 1 a 3); prohibirlo también en presentación (rechazado: prohibir algo
inocuo por asociación es tan malo como permitir algo dañino); no decidir
nada y dejar que se cuele más adelante (rechazado: una decisión que no se
escribe es una decisión que se pierde, y esta protege el número que se
publica).

**Consecuencias**: la app no gana una dependencia de pago; la ganancia de
SNR se busca donde es verificable (pesos, filtro adaptado, estela,
diagnóstico, pseudo-flat); y la puerta de presentación queda abierta y
documentada para el futuro.

## English

**Context**: the SNR campaign (`docs/PLANS/astrometry-snr/`) is about
detecting and measuring fainter objects. Neural-network noise reduction
tools exist, widely used in presentation astrophotography, with a
command-line interface that could be driven from the app (NoiseXTerminator,
paid, for instance). The author's question was direct: do we integrate it to
measure fainter?

**Decision**: **no**. An AI denoiser does not enter the measurement path
(astrometry or photometry), and if it ever enters the app it is **for
presentation only**, as an optional user-installed external tool, off by
default, with its output **refused** by the measurement path.

The reasons, in order of weight:

1. **It breaks the error model.** The CCD equation, the measured scatter and
   the `rmsRA`/`rmsDec` uncertainties sent to the MPC assume **white noise**.
   A non-linear filter **correlates** the noise: the scatter measured
   afterwards comes out optimistic and the uncertainties stop being true.
   Sending an uncertainty that is not the real one is worse than not sending
   the datum.
2. **It can move the centroid.** Astrometry lives on the sub-pixel centroid.
   Any non-linear spatial filter can bias it, and the bias goes straight
   into the published position.
3. **The MPC's floor exists for this.** The MPC requires SNR >= 20 per
   observation and forbids marginal detections precisely so that ghosts do
   not slip through: a false tracklet on the NEOCP can lose the object.
   Raising the SNR with a denoiser is **exactly** what that floor means to
   prevent. NightScribe also has its own nets: the sequence centred on the
   object and the Find_Orb check.
4. **It is not comparable with what we already do.** The matched filter
   (ADR-062, decision 18) raises the SNR by **1.55 to 1.63x** on real data
   **without touching the noise statistics**: it is the linear optimum, it
   has a formula and it can be checked. A denoiser changes the pixels and
   its gain cannot be verified with an arithmetic.
5. **Practical**: it is paid, it needs AVX and, on Linux, its requirements
   mention PixInsight, so its CLI may not run on the observer's machine. It
   would be the first paid dependency (ASTAP, EXOTIC and Find_Orb are
   free/GPL).

**Where it would honestly help**: in the **presentation** products (the
post's figures, the blink animation, the chart). There aesthetics is the
goal and the measurement is untouched. If it is integrated, it will be
through that door and with that label.

**How it gets decided if it ever enters**: with the **injection and
recovery** instrument (P4 of the plan). A moving source of known SNR is
injected into the real frames, measured with and without the denoiser, and
the **centroid error** and the **recovery rate** are compared. If it does
not beat the matched filter, it does not enter. Intuition does not decide
this: the data does.

**Alternatives**: integrating it into the measurement path (rejected by
points 1 to 3); banning it in presentation too (rejected: forbidding
something harmless by association is as bad as allowing something harmful);
not deciding anything and letting it slip in later (rejected: a decision
that is not written down is a decision that is lost, and this one protects
the number that gets published).

**Consequences**: the app does not gain a paid dependency; the SNR gain is
pursued where it is verifiable (weights, matched filter, trail, diagnosis,
pseudo-flat); and the presentation door stays open and documented.
