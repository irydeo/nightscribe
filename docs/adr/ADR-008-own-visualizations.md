# ADR-008: Own visualizations; third-party images only if public domain

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-21

## Español

**Contexto**: los posts necesitan gráficos atractivos, pero las imágenes de terceros
(mapas Raben, SolarMonitor, imágenes de descubrimiento de surveys) tienen copyright y
no pueden republicarse en redes sin permiso.

**Decisión**: NightScribe **genera sus propias visualizaciones** con estilo propio
(`viz/`). Imágenes externas solo si son dominio público (NASA SDO) o servicio público
con crédito (DESI Legacy Survey, CDS hips2fits). El resto se ofrece como enlaces que
se abren en el navegador. Las imágenes del propio observatorio son del usuario.

**Alternativas**: incrustar imágenes con copyright (riesgo legal); sin imágenes
(pierde el atractivo).

**Consecuencias**: exports limpios para redes, identidad visual propia, ninguna
sorpresa legal.

## English

**Context**: posts need attractive graphics, but third-party images (Raben maps,
SolarMonitor, survey discovery images) are copyrighted and cannot be republished on
social media without permission.

**Decision**: NightScribe **generates its own visualizations** with its own style
(`viz/`). External images only if public domain (NASA SDO) or public service with
credit (DESI Legacy Survey, CDS hips2fits). Everything else is offered as browser
links. The observatory's own images belong to the user.

**Alternatives**: embed copyrighted images (legal risk); no images (loses appeal).

**Consequences**: clean exports for social media, own visual identity, no legal
surprises.
