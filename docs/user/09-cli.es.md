# 09. La línea de comandos

Todo lo importante de NightScribe se puede hacer sin abrir la ventana, con
`python -m nightscribe <comando>` (o `nightscribe <comando>` si instalaste el
paquete). Útil para scripts, cron y noches con prisa.

| Comando | Qué hace |
|---------|----------|
| `gui` | Arranca la aplicación de escritorio |
| `tonight` | Los mejores objetivos de esta noche, con su score y el porqué |
| `explore <objeto>` | La ficha explicada de un objeto (órbita, física, visibilidad) |
| `post <objeto>` | Los borradores ES/EN y el tuit |
| `solar` | El estado del Sol (manchas, llamaradas, viento) |
| `blink <objeto> <fits>` | Blink de tu FITS contra la referencia PanSTARRS (supernovas) |
| `history` | Tu historial de observaciones |
| `sequence <objeto>` | Secuencia fotométrica propuesta y carta de comparación |
| `inject` | Inyección/recuperación: mide hasta qué magnitud llega de verdad tu pipeline |
| `project …` | Gestión de proyectos: `list`, `create`, `show`, `advance`, `close`, `reopen`, `files` |

Ejemplos:

```bash
python -m nightscribe tonight            # el plan de la noche en el terminal
python -m nightscribe explore 2021EQ3    # la ficha de un NEO
python -m nightscribe project list       # tus proyectos activos
python -m nightscribe project show "T CrB"
```

> **¿Por qué `inject` merece un comando propio?** Porque «mi telescopio llega
> a magnitud 20» es una frase que hay que medir, no creer. `inject` siembra
> fuentes de brillo conocido en tus propias tomas y comprueba cuáles
> recupera el pipeline: el resultado es tu límite *real*, con tu cielo, tu
> cámara y tu reducción. Es el número honesto que deberías poner en la
> magnitud límite de Configuración.

La GUI y el CLI comparten base de datos, caché y ajustes: lo que hagas en uno
lo ve el otro.
