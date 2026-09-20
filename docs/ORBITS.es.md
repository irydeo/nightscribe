# NightScribe — Explorador orbital («Explora»)

*[English version](ORBITS.md)*

El explorador orbital (`core/orbits.py`) traduce los parámetros orbitales y físicos
crudos a explicaciones **precisas, divulgativas y profundas** — la función que
diferencia a NightScribe de las tablas de efemérides.

## Familias orbitales

Clasificación a partir de los elementos SBDB (a, q, e) y el código de clase orbital.
Cada familia trae una breve explicación bilingüe (en `core/orbits.py`):

| Familia | Regla aproximada | En una frase |
|---|---|---|
| Atira | a < 1 UA, Q < 0,983 UA | vive por completo dentro de la órbita terrestre |
| Aten | a < 1 UA, Q > 0,983 UA | cruza la órbita de la Tierra desde dentro |
| Apollo | a > 1 UA, q < 1,017 UA | cruza la órbita de la Tierra desde fuera |
| Amor | 1,017 < q < 1,3 UA | se acerca a la Tierra pero no la cruza |
| Cinturón principal | 2,06 < a < 3,28 UA (aprox.) | el donut rocoso entre Marte y Júpiter |
| Hungaria, Hilda, ... | resonancias | subfamilias notables |
| Troyano | a ≈ 5,2 UA, cerca de L4/L5 | comparte la órbita de Júpiter, delante o detrás |
| Centauro | 5,5 < a < 30 UA | errante entre los planetas gigantes |
| Transneptuniano | a > 30 UA | las afueras heladas |
| Cometas: JFc / HTc / CTc / LPC | clase SBDB | familia de Júpiter (vuelve cada pocos años), tipo Halley, largo período («viene de la nube de Oort; no volverá en milenios»), dinámicamente nuevo |

## Parámetros traducidos

Cada parámetro recibe un valor, una analogía y un «por qué importa», en ES y EN, a dos
niveles de profundidad:

- **a (semieje mayor)** → distancia media; vía la tercera ley de Kepler, «su año dura
  X años terrestres».
- **e (excentricidad)** → 0 = círculo perfecto; con e = 0,5 «cae desde más allá de
  Marte hasta dentro de la órbita de Venus» — narrativa de cruces desde q y Q.
- **i (inclinación)** → inclinación sobre la «pista de aterrizaje» del sistema solar.
- **q / Q (perihelio / afelio)** → puntos más cercano y más lejano, con contexto
  planetario.
- **MOID** → distancia teórica mínima a la órbita terrestre; escala de riesgo honesta:
  PHA = MOID < 0,05 UA y H ≤ 22, explicado sin alarmismo; escala de Turín si se conoce.
- **H (magnitud absoluta)** → estimación de tamaño: diámetro desde H con albedo asumido
  por clase espectral (C≈0,057, S≈0,20, M≈0,14; núcleos cometarios ≈0,04), comparado
  con objetos cotidianos (escala de tamaños de narrative).
- **U (incertidumbre orbital 0–9)** → «qué tan bien conocemos su órbita» — enlaza con
  la planificación: *«por eso tu observación de esta noche importa»*.
- **período, velocidad en perihelio** → comparaciones a escala humana.
- **Próxima aproximación** (CAD) → fecha, distancia en distancias lunares, velocidad
  relativa.
- **Cometas: M1/K1** → magnitud esperada `m = M1 + 5·log10(Δ) + K1·log10(r)`;
  comparándola con la magnitud observada COBS se detectan outbursts.
- **Supernovas**: redshift/distancia de la anfitriona → tiempo de viaje de la luz,
  luminosidad de pico típica por tipo (Ia ≈ «5 000 millones de Soles»).
- **Exoplanetas**: clase del planeta desde radio/masa (Júpiter caliente, tipo
  Neptuno...), «su año dura X días», temperatura de equilibrio, profundidad del
  tránsito en mmag → «atenuará su estrella un Y%».

## «Datos que enganchan»

`orbits.py` clasifica los 2–3 datos más vendibles del objeto; `suggest.py` y
`post.py` los consumen. Las reglas son explícitas y están testeadas (ver SCORING.md).

## Fórmulas usadas (todas documentadas en el código)

- Estimación de magnitud visual: `m ≈ H + 5·log10(r·Δ)` (fase despreciada; uso divulgativo).
- Magnitud cometaria: `m = M1 + 5·log10(Δ) + K1·log10(r)`.
- Diámetro desde H: `D(km) = 1329 / sqrt(albedo) · 10^(-H/5)`.
- Energía cinética (solo si es PHA, siempre con nota tranquilizadora):
  `E = ½·ρ(4/3)π(D/2)³·v²`, ρ según clase espectral (C 1300, S 2700, M 5000 kg/m³).
- Redshift → distancia: `d ≈ z·c/H0`, H0 = 70 km/s/Mpc (z pequeño).
- Distancia lunar: 384 400 km. 1 UA = 149 597 870,7 km.
