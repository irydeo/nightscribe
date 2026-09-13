# Plan — Variables de largo periodo y campañas de observación (Track V)

> **Executado (plan escrito 2026-09-11; cerrado 2026-09-13): 40 subplanes
> autocontenidos, todos hechos, suite unitaria 1096.** Un subplan = un commit. Las tarjetas de subplan viven en
> `docs/PLANS/variables/` (un fichero por fase). Anclas verificadas a HEAD
> `4b7635a`. **El ejecutor es un modelo local pequeño (qwen3.8)**: las tarjetas
> llevan todo el código y los tests ya escritos para copiar; leer antes
> `docs/PLANS/variables/LEEME.md` (patrones y errores frecuentes).
> **Decisión registrada** en [ADR-035](../adr/ADR-035-variables-campaigns.md).

**rama**: `feature/variables-campaigns` (nace de `feature/hads`, HEAD
`4b7635a`; mergea de vuelta a `feature/object-card` al cerrar)
**fecha**: 2026-09-11 · **autor**: FJC (con la IA)

## Objetivo

Llevar al observatorio dos capacidades hermanas:

1. **Estrellas variables de largo periodo** como nuevo tipo de objetivo
   (`kind == "variable"`): Miras, simbióticas, novas recurrentes (T CrB),
   novas enanas, RCB, irregulares tipo WeSb 1, eclipsantes… Técnicamente es
   el **molde multi-noche del Track B de supernovas** (sesiones, puntos
   fotométricos, curva de luz, cadencia con memoria) — las HADS son la
   excepción de corto periodo (sesión única 2P), esto es la regla.
2. **Campañas de observación** como entidad de primer orden, **ortogonal al
   tipo de objeto** y **1:N con proyectos** (una campaña agrupa varios
   objetos; un proyecto cuelga de una campaña como mucho). Modelo tomado de
   las campañas reales del grupo obsSN (WeSb 1, T CrB, campañas finalizadas
   con SNs, novas enanas, cefeidas, EE Cep, un blázar…): grupo/coordinador,
   objetivo científico, protocolo (cadencia en noches, filtros, estrellas de
   comparación, notas), URLs de reporte y de datos, estado activa/finalizada.

La referencia de comportamiento son las propias páginas del grupo: WeSb 1 pide
«una medida por noche y filtro; si se detecta caída de brillo, subir la
cadencia; usar las 3 estrellas de comparación indicadas; reportar con la hora
juliana (HJD)». T CrB añade «cuidado, es brillante: no saturar».

## Decisiones (V-a … V-n), cerradas en la entrevista 2026-09-11

| # | Decisión | Valor |
|---|---|---|
| V-a | **Kind `variable` genérico** | Toda variable fotométrica; el tipo concreto (M, NR, EA, RCB…) llega de VSX o se teclea y solo afecta a ficha/narrativa. Molde multi-noche Track B; **sin** sesión 2P ni gate de ciclo (eso era la excepción HADS). |
| V-b | **Campaña 1:N ortogonal** | Tabla propia; cualquier kind puede colgar (las campañas obsSN mezclan SNs y variables); los objetos pueden no estar en ningún catálogo (alta manual). |
| V-c | **Fuente de datos VSX + SIMBAD + manual** | `core/sources/vsx.py`: API del VSX de la AAVSO **en el subdominio `vsx.aavso.org`** (www está tras Cloudflare y bloquea; el subdominio responde 200 limpio, verificado 2026-09-11). Caché 7 días vía `db.http_get`. Sin ficha VSX → SIMBAD resuelve coords (fuente ya existente) → entrada manual. Nunca rompe. |
| V-d | **Tonight: solo campañas vencidas** | Fase planner `campaigns` 100 % local (SQLite + matemática de cielo): si una campaña activa lleva ≥ `cadence_nights` sin visita (o nunca se visitó) y el objeto es visible esta noche, entra en la lista. Al día = no aparece. |
| V-e | **Predicción de extremos en v1** | `next_extremum(period_d, epoch_mjd)`: próximo máximo (pulsantes) o mínimo (eclipsantes: en VSX la época **es** el mínimo). Regla de tipo: el primer componente del tipo VSX que empieza por `EA`/`EB`/`EW`/`E/`/`E-` o es `E` → época=mínimo; **resto (incluido `ELL`) → máximo**. Eclipsantes: solo la fecha del mínimo, **sin** ventana horaria estilo tránsito. |
| V-f | **Contexto de surveys en la curva** | Sí (cierra el B12 pendiente de SN): botón bajo demanda «Descargar fotometría de surveys» → ALeRCE **ZTF API v1** (`https://api.alerce.online/ztf/v1/`, verificado 2026-09-11) → puntos grises `source="survey:ztf"` que los renderers ya estilizan. Nunca se mezclan con los propios. |
| V-g | **Quick-look también en variables** | `core/series.py` sirve sin cambios (WCS + coords); botón «Run quick-look» visible en el Follow-up de variables. |
| V-h | **Asesor de eventos en v1** | `variables.detect_event(points, threshold)`: por filtro, con ≥ 4 puntos propios (sin `survey:*`), `delta = mag_último − mediana(previos)`; si `|delta| ≥ threshold` (config `event_mag_threshold`, **0.5** por defecto, 0.2–2.0) → aviso en Follow-up + boost de urgencia en Tonight. `delta > 0` = descenso (dip); `< 0` = subida (erupción). |
| V-i | **Reporte fotométrico** | Por proyecto. **CSV** documentado (`name,hjd,mag,err,filter,comp_stars,observer,notes`) + **AAVSO Extended File Format**. HJD calculado en app (`variables.jd_to_hjd`, Sol de Schlyter de `ephem_minor`, error < 1 s). Excluye `quicklook` salvo checkbox. Fichero registrado en `project_files`. |
| V-j | **Gestor de campañas = diálogo modal** | Patrón Explore/Post/Blink: menú Herramientas + botón en el hub de Proyectos. Lista activas/finalizadas, crear/editar/finalizar/reabrir, alta de objetivos (VSX→SIMBAD→manual), adjuntar proyecto existente. Sin pestaña nueva. |
| V-k | **Campañas personales** | Sin export/import en v1. |
| V-l | **Cadencia por defecto 1 noche** | Editable 1–30 en el formulario de campaña. |
| V-m | **Sin ventanas estacionales** | `created` automático, `closed_at` al finalizar; la visibilidad del planner ya filtra sola. |
| V-n | **Migración `user_version` 6→7** | Tabla `campaigns` + `projects.campaign_id REFERENCES campaigns(id) ON DELETE SET NULL` (guardado por `PRAGMA table_info`, patrón v5/v6). |

## Hechos verificados en vivo (2026-09-11) — base de los fixtures

**VSX** `GET https://vsx.aavso.org/index.php?view=api.object&ident=<nombre>&format=json`:

- T CrB → `{"VSXObject":{"Name":"T CrB","AUID":"000-BBW-825","RA2000":"239.87567","Declination2000":"25.92017",...,"VariabilityType":"NR+ELL","Period":"227.5528","Epoch":"2455828.9","MaxMag":"2.0 V","MinMag":"10.8 V","SpectralType":"M3III+WD",...,"Constellation":"CrB"}}` — ojo: **RA/Dec en grados decimales como cadenas**, mags con banda (`"2.0 V"`), tipos compuestos con `+`, `Epoch` en **JD** (no MJD).
- omi Cet → tipo `M`, además `RiseDuration`. EE Cep → tipo `E-DO`, además `EclipseDuration` (días).
- WeSb 1 → `{"VSXObject":[]}` (**no está en VSX**: confirma el camino SIMBAD→manual). No encontrado = lista vacía, no error HTTP.

**ALeRCE ZTF v1**: `GET /ztf/v1/objects/?ra=&dec=&radius=` → `items[].oid`;
`GET /ztf/v1/objects/<oid>/lightcurve` → `{detections: [{mjd, fid, magpsf,
sigmapsf, magpsf_corr, sigmapsf_corr, sigmapsf_corr_ext, …}],
non_detections: [...]}`. `fid`: 1=g, 2=r, 3=i. `sigmapsf_corr == 100.0` marca
corrección inválida → usar `magpsf`/`sigmapsf`. WeSb 1 = `ZTF18abtsbfh`
(1145 detecciones).

**HJD de referencia** (calculados con `ephem_minor.sun_ra_dec`, convenio
`HJD = JD + (n̂·ŝ)·r·τ`, τ = 499.004784 s/UA; comprobado el signo: dirección
Solar → +496.17 s, anti-Solar → −496.17 s):

| Caso | JD | RA° | Dec° | Corrección |
|---|---|---|---|---|
| WeSb 1 | 2459653.44800 | 15.2254 | +55.0667 | **+250.09 s** |
| T CrB | 2459653.44800 | 239.87567 | +25.92017 | **−196.45 s** |

## Arquitectura de datos

```
SQLite user_version 7
  campaigns(id, name, group_name, coordinator, goal, protocol JSON,
            report_url, data_url, status, created, closed_at)
  projects.campaign_id → campaigns(id) ON DELETE SET NULL

core/campaign.py        CRUD + protocol_get + projects_of + due_campaigns
core/variables.py       next_extremum / phase_at / jd_to_hjd / detect_event
core/sources/vsx.py     ficha VSX (caché 7 d)     core/sources/surveys.py  ALeRCE ZTF (caché 30 d)

Tonight: planner fase "campaigns" (local) → target dict + sub-dicts
         "campaign" {id, name, overdue_days, cadence_nights, never_visited,
                     event} y "variable" {var_type, period_d, epoch_mjd, max,
                     min, amp, spectral, next_extremum{kind,mjd,days}}
         → suggest (urgencia cadencia/evento, hook extremo) → GUI
```

## Protocolo de ejecución (obligatorio en cada subplan)

1. Lee `AGENTS.md` + `docs/PLANS/variables/LEEME.md` + **solo** tu tarjeta.
2. Baseline: `.venv/bin/python -m pytest tests/unit -q` → anota el conteo.
3. Implementa la tarjeta **tal cual** (el código y los tests ya vienen
   escritos). Si un ancla no coincide con la realidad: **para y reporta
   pegando la salida; no improvises**.
4. «Hecho» = checklist completo: el comando de test de la tarjeta en verde,
   suite unitaria verde (anota N→M), cabecera GPL en todo `.py` nuevo,
   código en inglés con comentarios `# @args:` / `# @return:`, cadenas de
   GUI por `self.tr()`, i18n ejecutado si la tarjeta tiene tabla de cadenas.
5. Un commit por subplan, con el mensaje literal de la tarjeta. Marca
   **Estado: Hecho (N→M)** en la tarjeta.
6. Prohibido: TODOs sin resolver, medias implementaciones, agrupar commits,
   editar tests no listados en la tarjeta, tocar ficheros no listados.

## Índice de subplanes (40)

| Sub | Título | Fichero | Depende de |
|---|---|---|---|
| V0.1 | Migración v7: `campaigns` + `projects.campaign_id` | [fase-0-data.md](variables/fase-0-data.md) | — |
| V0.2 | `core/campaign.py`: CRUD | ídem | V0.1 |
| V0.3 | `campaign.py`: protocolo + `due_campaigns` | ídem | V0.2 |
| V0.4 | `project.py`: kind `variable`, `campaign_id`, CLI help | ídem | V0.1 |
| V0.5 | `core/variables.py`: `next_extremum` + `phase_at` | ídem | — |
| V0.6 | `variables.py`: `jd_to_hjd` (referencias congeladas) | ídem | V0.5 |
| V0.7 | `variables.py`: `detect_event` | ídem | V0.5 |
| V0.8 | `core/sources/vsx.py` + fixtures | ídem | — |
| V0.9 | `core/sources/surveys.py` (ALeRCE) + fixtures | ídem | — |
| VA.1 | Planner: fase `campaigns` (target básico) | [fase-a-core.md](variables/fase-a-core.md) | V0.3, V0.4 |
| VA.2 | Planner: sub-dicts `variable` + flag de evento | ídem | VA.1, V0.5, V0.7 |
| VA.3 | `suggest`: scoring (4 familias) | ídem | VA.2 |
| VA.4 | `suggest`: fragmentos ES/EN | ídem | VA.3 |
| VB.1 | Theme: color `#65cf30` + label `VAR` | [fase-b-gui.md](variables/fase-b-gui.md) | — |
| VB.2 | GUI listable: icono, columnas, orden, labels de fase | ídem | VB.1, VA.1 |
| VB.3 | Config: `enabled_kinds` + migración amable + `event_mag_threshold` | ídem | — |
| VB.4 | Settings checkbox + combos de proyectos (`.ui`) | ídem | VB.2, VB.3 |
| VB.5 | `enrich.detect_type`: variables antes de la regex exoplaneta | ídem | V0.4 |
| VB.6 | `enrich`: rama de datos variable (VSX→SIMBAD→manual) | ídem | VB.5, V0.8 |
| VC.1 | `orbits.explain_variable` (tabla ES/EN) | [fase-c-projects.md](variables/fase-c-projects.md) | VB.6 |
| VC.2 | Chips + plegado con época en la ficha | ídem | VC.1 |
| VC.3 | `_create_project`: whitelist de contexto | ídem | V0.4 |
| VC.4 | `gui/campaigns_dialog.py`: esqueleto + accesos | ídem | V0.2 |
| VC.5 | Gestor: crear/editar campaña | ídem | VC.4 |
| VC.6 | Gestor: finalizar/reabrir + badge en cabecera | ídem | VC.5 |
| VC.7 | Gestor: añadir objetivo (VSX→SIMBAD→manual) | ídem | VC.6, V0.8 |
| VC.8 | Gestor: adjuntar/desadjuntar proyecto existente | ídem | VC.6 |
| VC.9 | Hub: filtro por campaña | ídem | VC.4, V0.4 |
| VC.10 | Follow-up variable: botones, protocolo, cadencia | ídem | V0.4, VC.7 |
| VD.1 | Chip Tonight generalizado + aviso de evento en Follow-up | [fase-d-report.md](variables/fase-d-report.md) | VC.10, VA.1 |
| VD.2 | Plan tab: bloque variable/campaña | ídem | VC.10 |
| VD.3 | Secuencia CCDciel multi-filtro del protocolo | ídem | VD.2 |
| VD.4 | `core/photometry_export.py`: CSV | ídem | V0.6 |
| VD.5 | `photometry_export.py`: AAVSO EFF | ídem | VD.4 |
| VD.6 | Diálogo de exportación + `project_files` | ídem | VD.5, VC.10 |
| VD.7 | Botón surveys en Follow-up (sn + variable) | ídem | V0.9, VC.10 |
| VD.8 | Narrativa: hook/facts/hashtags variable | ídem | VB.6 |
| VD.9 | Post: curva de luz en `build_charts` para variable | ídem | VD.8, VC.2 |
| VE.1 | i18n ES/EN completo (volcado de tablas) | [fase-e-close.md](variables/fase-e-close.md) | todas las de GUI |
| VE.2 | Cierre: ADR-035 rev, WORKFLOWS 7quindecies, AGENTS.md, suite | ídem | todas |

## Riesgos y mitigaciones

- **VSX tras Cloudflare en el dominio www** → usamos `vsx.aavso.org`
  (verificado limpio). Si cambia → degradación a ficha manual (Tonight es
  local, nunca rompe).
- **ALeRCE cambia su API** → el botón de surveys avisa y nada más se rompe.
- **Falsos positivos de `detect_type`** (p. ej. «GQ Lup b» es planeta) → la
  regex de variable exige exactamente dos tokens y va antes de la exoplanet
  solo con esa forma; tests de colisión incluidos (lección «GP And»).
- **Época VSX ambigua en tipos compuestos** (T CrB = NR+ELL: la época es de
  la modulación orbital, no de la erupción) → regla documentada (V-e); la
  predicción se etiqueta siempre como «esperado».
- **Campaña sin objetivos** → aviso en el gestor («no aparecerá en Esta
  noche hasta tener un objetivo»).
- **Eventos falsos por mezclar bandas** → `detect_event` trabaja por filtro
  y nunca con puntos `survey:*`.

## Fuera de alcance (v2+)

- Ventana horaria de eclipses estilo tránsito (línea de tiempo).
- Compartir campañas (export/import JSON) e importar la hoja de respuestas
  del grupo como puntos de contexto.
- AAVSO Alert Notices; ASAS-SN Sky Patrol (alternativa a ALeRCE).
- T CrB erupcionada → proyecto SN aparte (el flujo SN ya existe).
- Monitor de flujo en vivo (aparcado en HADS, H-l), fotometría absoluta,
  lanzar FotoDif como subproceso.

## PUNTO DE ENTRADA (para el ejecutor local)

1. Lee `AGENTS.md`, `docs/PLANS/variables/LEEME.md` y este maestro.
2. Ejecuta en orden: V0.1 → … → V0.9 → VA.1 → … → VE.2. Una tarjeta por
   sesión, con contexto fresco. No abras `gui/main_window.py` entero:
   trabaja siempre con los rangos de línea de la tarjeta.
3. Si algo contradice una decisión V-a…V-n o un ancla no coincide: **para y
   reporta**; no escribas el mínimo sin reportar.
