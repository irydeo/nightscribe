# ADR-004: No astropy/astroquery dependency

**Estado / Status**: Reopened · **Fecha / Date**: 2026-08-21 · **Reabierto / Reopened**: 2026-10-04 por ADR-060

> **Reapertura (2026-10-04)**: ADR-060 sustituye la prohibición general por la
> regla «numpy primero, biblioteca estándar cuando aporta», y autoriza astropy,
> scipy y photutils para los módulos nuevos del plan de astrometría. Esta
> decisión sigue siendo válida para el código existente, que no se migra.
>
> **Reopening (2026-10-04)**: ADR-060 replaces the general ban with the rule
> "numpy first, standard library when it earns its place", and authorises
> astropy, scipy and photutils for the new modules of the astrometry plan. This
> decision still holds for the existing code, which is not migrated.

## Español

**Contexto**: `saas` calculaba visibilidad con astropy y efemérides con
astroquery.mpc. En el sistema de destino no están instaladas y son dependencias
pesadas para una app publicable.

**Decisión**: no depender de ellas. Visibilidad con math esférico propio
(`core/coords.py`: hora sidereal + alt-az, precisión sobrada para planificación);
efemérides por sitio vía NEOfixer `ephem` y JPL Horizons; Sol/Luna/planetas con
algoritmos de Schlyter (ver ADR-009).

**Alternativas**: astropy+astroquery (potentes pero ~cientos de MB y frágiles de
empaquetar); skyfield (más ligero, pero otra dependencia y ficheros de efemérides).

**Consecuencias**: instalación trivial, tests rápidos, todo offline salvo las fuentes
de datos. A cambio mantenemos ~200 líneas de math documentado y testeado.

## English

**Context**: `saas` computed visibility with astropy and ephemerides with
astroquery.mpc. They are not installed on the target system and are heavy
dependencies for a publishable app.

**Decision**: do not depend on them. Visibility with own spherical math
(`core/coords.py`: sidereal time + alt-az, plenty accurate for planning);
site ephemerides via NEOfixer `ephem` and JPL Horizons; Sun/Moon/planets with
Schlyter algorithms (see ADR-009).

**Alternatives**: astropy+astroquery (powerful but ~hundreds of MB and fragile to
package); skyfield (lighter, but another dependency plus ephemeris files).

**Consequences**: trivial install, fast tests, everything offline except data
sources. In exchange we maintain ~200 lines of documented, tested math.
