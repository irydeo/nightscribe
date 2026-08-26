# NightScribe — Motor de sugerencias y scoring

*[English version](SCORING.md)*

El motor de sugerencias (`core/suggest.py`) convierte cinco listas heterogéneas de
objetivos en una respuesta: **«estos son tus mejores objetivos esta noche, y aquí está
el porqué»**. Todo son reglas simples y testeables — sin machine learning, sin magia.

## Score unificado: 0–100

Cada objetivo recibe un score construido con cuatro familias ponderadas:

| Familia | Peso | Qué mide |
|---|---|---|
| Prioridad científica | 0–35 | Score NEOfixer (NEOs), brillo+frescura (SNs), actividad/perihelio (cometas), score PCCP, prioridad ExoClock + deriva O-C (tránsitos) |
| Observabilidad | 0–30 | Altitud máxima esta noche, horas sobre la altitud mínima, magnitud vs. límites del usuario, interferencia lunar, % de tránsito cubierto |
| Urgencia | 0–20 | Urgencia NEOfixer, arco corto, días desde el descubrimiento, perihelio inminente, degradación de efeméride (O-C) |
| Gancho divulgativo ★ | 0–15 | «¿Qué buena historia es?» — nuestro diferencial |

★ Bonus divulgativos (se acumulan, tope 15):

- NEO: en el NEOCP, impactor potencial (Sentry), objetivo radar/NHATS,
  MOID < 0,05 UA, aproximación prevista < 10 LD próximamente.
- Cometa: dinámicamente nuevo (primera visita), perihelio en días, outburst
  detectado (mag observada ≫ predicción M1/K1), más brillante que 12 («¡prismáticos!»).
- Supernova: más brillante que 15, galaxia anfitriona famosa (M51, M101, NGC...),
  descubierta en la última semana.
- Tránsito: sistema famoso (HD 209458, TRAPPIST-1, 55 Cnc...), tránsito completo
  visible, prioridad alta para Ariel de la ESA.
- PCCP: score de cometa > 50 en la página del MPC.

### Realimentación del historial

Desde SQLite (`observations`): los objetivos **observados pero aún no publicados**
ganan +5 de urgencia («lo observaste el martes — ¡cuéntalo!»); los **ya publicados**
en los últimos 30 días pierden el bonus divulgativo (decaimiento por novedad).

## Top N con diversidad de tipos

`top_n` primero elige el mejor objetivo **de cada tipo** (NEO, SN, cometa, PCCP,
tránsito) y luego rellena los huecos con los siguientes mejores scores. Una noche
con un NEO, un cometa y un tránsito vale más que tres NEOs — científicamente y
para la audiencia.

Detalles por objeto en la app: **NObs** (observaciones acumuladas: más = órbita
más fiable — una comprobación rápida de realidad para candidatos NEO) y
**Descubierto** (fecha de descubrimiento para transitorios; fecha de la
aproximación para las alertas de acercamiento).

## Frases «por qué esta noche»

Una frase generada por objetivo del Top, ES + EN. Basada en reglas en `narrative.py`:
gana la primera regla que aplica, así las frases son específicas, no genéricas.
Ejemplos:

- NEOCP: *«En la página de confirmación del MPC: cada medida cuenta para su órbita.»*
- Arco corto: *«Arco de una sola oposición: esta semana es la ventana antes de perderlo.»*
- SN reciente: *«Descubierta hace 6 días y aún en aumento; su luz ha viajado
  55 millones de años.»*
- PCCP: *«Score de cometa 85/100 en el PCCP del MPC: tu imagen podría confirmarlo.»*
- Tránsito: *«Un planeta de 1,4 Júpiters eclipsa su estrella un 1,5% durante 3 h —
  tu curva de luz ayuda a la misión Ariel de la ESA.»*
- Aproximación: *«Pasa a 3,2 distancias lunares el jueves: más cerca que la Luna
  es una historia.»*

Cada tarjeta muestra además: magnitud, altitud máxima + hora (o ventana de tránsito),
coste estimado en minutos si se conoce, y botones de acción.

## Filtrado de factibilidad

El equipo del usuario entra por Configuración (apertura, magnitud límite).
La política es **híbrida** (ADR-025):

| Familia | Política | Dónde |
|---|---|---|
| SN, cometas, exoplanetas | **Duro** — fuera de alcance, fuera de la lista | `sources/rochester.py`, `sources/cobs.py`, `core/transits.py` |
| NEO, PCCP | **Suave** — la magnitud es una predicción, se hunde el score y se etiqueta; **nunca se descarta** | `core/suggest.py` → `beyond_limit()` |

Los objetivos fuera de alcance (en el caso suave) se muestran atenuados, nunca
ocultos: planificar es saber qué hay ahí arriba, aunque esta noche no puedas
con ello.

## Pruebas

Los tests unitarios usan objetivos sintéticos con propiedades conocidas («un NEOCP
brillante debe superar a un asteroide numerado de mag 21»); los funcionales ejecutan
el motor completo contra las fuentes reales para el sitio configurado.
