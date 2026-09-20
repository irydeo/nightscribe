# Track V — Fase E: cierre (i18n + docs)

> Subplanes VE.1–VE.2 del plan maestro
> [../variables-campaigns.md](../variables-campaigns.md). Anclas verificadas
> a HEAD `4b7635a`. Lee antes `LEEME.md`.
> Precondición: todas las tarjetas anteriores hechas.

---

## VE.1 — i18n ES/EN completo (barrido final)

**Contexto a leer (solo esto)**: `LEEME.md` §3 (pipeline i18n) y §5 (errores
frecuentes); `tests/unit/test_i18n.py` (lo que exige).

**Toca**: `nightscribe/gui/i18n/nightscribe_es.ts`,
`nightscribe/gui/i18n/nightscribe_en.ts`, los `.qm` compilados.

**Escribe exactamente esto**:

1. Cada tarjeta GUI ya trajo su tabla de cadenas y su `lupdate`+`lrelease`
   parcial. Esta tarjeta es el **barrido de cierre**:
   ```bash
   pyside6-lupdate nightscribe/gui/*.py nightscribe/gui/widgets/*.py \
       nightscribe/gui/ui/*.ui \
       -ts nightscribe/gui/i18n/nightscribe_es.ts \
           nightscribe/gui/i18n/nightscribe_en.ts
   ```
2. Abre ambos `.ts` y busca `<translation type="unfinished"/>`: completa lo
   que quede. Las traducciones correctas son las de las tablas de las
   tarjetas VB.2, VB.4, VC.2, VC.4, VC.5, VC.6, VC.8, VC.9, VC.10, VD.1,
   VD.2, VD.6, VD.7 (recógelas de ahí; EN suele ser igual a la fuente).
3. `pyside6-lrelease nightscribe/gui/i18n/nightscribe_*.ts`
4. `.venv/bin/python -m pytest tests/unit/test_i18n.py -q` — debe quedar
   verde (falla con cualquier `unfinished` o vacía).

**Ejecuta**: el pipeline completo + `tests/unit/test_i18n.py` + suite
unitaria.
**Hecho cuando**: `test_i18n.py` verde; suite verde (N→M). Anota el número
total de cadenas (lo dice `lrelease` o el propio test): **714** cadenas.
**Commit**: `Gui/i18n: full ES/EN pass for the variables & campaigns track (ADR-035, subplan VE.1)`
**Estado**: Hecho ✅ (2 tests en test_i18n.py; suite 1096 passed; 714 cadenas ES y EN, 0 unfinished)

---

## VE.2 — Cierre documental

**Contexto a leer (solo esto)**:
`docs/adr/ADR-035-variables-campaigns.md` (el ADR del track);
`docs/WORKFLOWS.es.md` (sección `7quaterdecies`, :757-787 — el molde);
`docs/WORKFLOWS.md` (la misma sección en inglés);
`AGENTS.md` (sección «Estructura»).

**Toca**: `docs/adr/ADR-035-variables-campaigns.md`;
`docs/WORKFLOWS.es.md`; `docs/WORKFLOWS.md`; `AGENTS.md`;
este maestro (`docs/PLANS/variables-campaigns.md`) y las tarjetas (marcar
estados); `docs/DATA_SOURCES.md` y `docs/DATA_SOURCES.es.md`.

**Escribe exactamente esto**:

1. **ADR-035**: cambia el estado a `Accepted` (si no lo está ya) y añade una
   línea de revisión «rev. <fecha>: ejecutado completo — suite unitaria N».
2. **WORKFLOWS.es.md / WORKFLOWS.md**: nueva sección tras la 7quaterdecies:

```markdown
### 7quindecies. Track V — Variables de largo periodo y campañas (FECHA, ADR-035)

Plan: `docs/PLANS/variables-campaigns.md` (maestro) +
`docs/PLANS/variables/fase-*.md` (40 subplanes). Rama
`feature/variables-campaigns`.

Nuevo kind `variable` (molde multi-noche del Track B; las HADS eran la
excepción) y entidad **campaña** 1:N ortogonal (migración v7), tomada de las
campañas reales del grupo obsSN (WeSb 1, T CrB). Tonight gana la fase local
`campaigns` (solo vencidas, V-d); ficha con VSX (subdominio `vsx.aavso.org`,
el www está tras Cloudflare) → SIMBAD → manual; predicción de extremos con la
época VSX; asesor de eventos (dip/erupción, umbral configurable); contexto de
surveys ZTF/ALeRCE en la curva (cierra la opción B12); reporte CSV + AAVSO
EFF con **HJD calculado en la app** (Sol de Schlyter).

**Estado**: suite unitaria verde (N). **Fuera de esta iteración**: ventana
horaria de eclipses, compartir campañas, AAVSO Alert Notices, ASAS-SN Sky
Patrol, monitor en vivo.
```

   (La versión inglesa es la traducción fiel; N = el conteo final de VE.1.)
3. **AGENTS.md**: en «Estructura», junto a `hads.py` y `sources/`, refleja:
   `core/campaign.py` (CRUD campañas + due_campaigns), `core/variables.py`
   (extremos, HJD, asesor de eventos), `core/photometry_export.py` (CSV +
   AAVSO EFF), `core/sources/vsx.py` (AAVSO VSX, TTL 7 d),
   `core/sources/surveys.py` (ALeRCE ZTF, TTL 30 d). Toca las dos columnas
   (ES y EN) si el fichero las separa.
4. **DATA_SOURCES.md / .es.md**: sección nueva para VSX (endpoint, TTL,
   qué se extrae, degradación) y ALeRCE/ZTF (dos llamadas, TTL, qué se
   dibuja), con la fecha de verificación (2026-09-11).
5. Marca **Estado: Hecho** en las 40 tarjetas y el maestro, y el estado del
   track en `docs/PLANS/project-concept-v2.md` **no aplica** (este track no
   es hijo suyo: no lo toques).
6. **Funcional con red** (opcional pero recomendado): añade
   `tests/functional/test_vsx_live.py` consultando «T CrB» real (molde:
   `tests/functional/test_hads_live.py`) — marca `pytest.mark` como los
   demás funcionales.

**Ejecuta**: `.venv/bin/python -m pytest tests/unit -q` y, si hay red,
`.venv/bin/python -m pytest tests/functional -k vsx -q`
**Hecho cuando**: suite verde (anota N→M); docs consistentes.
**Commit**: `Docs: Track V close — ADR-035 executed, WORKFLOWS 7quindecies, AGENTS.md, DATA_SOURCES (subplan VE.2)`
**Estado**: Hecho ✅ (2026-09-13; suite 1096; ADR-035 → Accepted; WORKFLOWS 7quindecies ES/EN; AGENTS.md estructura; DATA_SOURCES VSX + ALeRCE; tarjetas y maestro marcados)

---

## Cierre del track

Con VE.1+VE.2 hechas, el track se mergea a `feature/object-card` (regla del
maestro: una fase = un commit ya verificado; el merge lo hace el humano).
