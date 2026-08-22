# NightScribe

*[English version](README.md)*

**Planifica tu noche, entiende cada objeto, cuenta tu ciencia.**

NightScribe es una aplicación de escritorio (GUI Qt6 + CLI) para observatorios
astronómicos amateur:

- **Esta noche** — los mejores NEOs, cometas, posibles cometas (PCCP), supernovas y
  tránsitos de exoplanetas visibles desde tu observatorio, ordenados por un score
  unificado con frases de «por qué esta noche».
- **Explora** — parámetros orbitales y físicos traducidos a explicaciones precisas y
  divulgativas (familias, MOID, tamaños, orígenes...).
- **Post** — borradores bilingües (ES/EN) para redes + tuit + gráficos PNG listos
  para adjuntar (órbita, cielo nocturno, Sol, antes/después de supernova).
- **Sistema solar ahora** — el Sol en directo (NASA SDO), la Luna y los planetas
  visibles esta noche.
- **Configuración** — asistente de primer arranque; tu código de observatorio MPC
  resuelve tus coordenadas automáticamente.

Las fuentes de datos incluyen NEOfixer, MPC (PCCP, ObsCodes), JPL SBDB/Horizons/CAD,
COBS, Rochester Astronomy, SIMBAD, ExoClock, NASA Exoplanet Archive, NOAA SWPC, SILSO
y NASA SDO.

## Inicio rápido

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nightscribe gui        # aplicación de escritorio
.venv/bin/python -m nightscribe tonight    # mejores objetivos de esta noche (CLI)
```

Consulta [INSTALL.es.md](INSTALL.es.md) para instrucciones completas por sistema
operativo y el instalador autónomo, y [CONTRIBUTING.es.md](CONTRIBUTING.es.md) para
colaborar.

## Documentación

Diseño, arquitectura, fuentes de datos, scoring y todas las decisiones (ADRs) están en
[`docs/`](docs/) (bilingüe ES/EN).

## Licencia

GPL v3 — (c) 2026 Francisco José Calvo Fernández (Observatorio Irydeo, MPC Z41).
