# ADR-011: Comets via COBS + SBDB (M1/K1)

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: los cometas son parte de la identidad del observatorio (29P, 67P) y
tienen particularidades: magnitud cometaria (M1/K1), perihelio, origen (Oort /
familia de Júpiter), outbursts.

**Decisión**: **COBS** (`cobs.si/api/comet_list.api`) como fuente de cometas activos
con magnitud real observada; **SBDB** para datos físicos/orbitales (M1, K1, núcleo,
clase); brillo esperado con `m = M1 + 5·log10(Δ) + K1·log10(r)`; comparación
COBS vs. esperado para detectar outbursts. Visibilidad con Horizons/alt-az propio.

**Alternativas**: aerith.net (no respondía en la verificación); solo SBDB (sin
magnitudes observadas reales); solo NEOfixer (cubre cometas pero sin fotometría
cometaria).

**Consecuencias**: narrativa cometaria completa (origen, perihelio, outbursts);
detección automática de cometas en `enrich` vía `kind` de SBDB o prefijo P/C/D/A.

## English

**Context**: comets are part of the observatory's identity (29P, 67P) and have
peculiarities: cometary magnitude (M1/K1), perihelion, origin (Oort / Jupiter
family), outbursts.

**Decision**: **COBS** (`cobs.si/api/comet_list.api`) as the source of active comets
with real observed magnitudes; **SBDB** for physical/orbital data (M1, K1, nucleus,
class); expected brightness with `m = M1 + 5·log10(Δ) + K1·log10(r)`; COBS vs.
expected comparison to detect outbursts. Visibility via Horizons/own alt-az.

**Alternatives**: aerith.net (not responding during verification); SBDB only (no real
observed magnitudes); NEOfixer only (covers comets but without cometary photometry).

**Consequences**: full cometary narrative (origin, perihelion, outbursts); automatic
comet detection in `enrich` via SBDB `kind` or P/C/D/A prefix.
