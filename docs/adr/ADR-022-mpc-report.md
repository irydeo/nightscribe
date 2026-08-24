# ADR-022: MPC report — paste and validate, never generate measurements

**Estado / Status**: Accepted · **Fecha / Date**: 2026-08-24

## Español

**Contexto**: en el flujo NEO (ADR-019, WORKFLOWS §5) el usuario mide sus imágenes con
su software astrométrico habitual (Astrometrica u otro). Preparar el reporte al Minor
Planet Center es hoy un paso manual y propenso a errores de formato. Decisión del
usuario: **no se trata de generar las medidas** — simplemente se pegan desde el
software que las haya generado.

**Decisión**: `core/mpc_report.py` —

1. **Entrada por pegado**: el usuario pega la salida de su software (formato MPC de 80
   columnas o ADES PSV) en el paso «Procesado» del proyecto NEO.
2. **Validación**: formato correcto por línea, código de observatorio igual al
   configurado (p. ej. Z41), designación del objeto consistente con el contexto del
   proyecto, fechas y coordenadas en rango. Errores en lenguaje humano, línea a línea.
3. **Empaquetado**: fichero listo para enviar por email al MPC, guardado en la carpeta
   del proyecto y registrado en `project_files`. **El envío lo hace el usuario** —
   igual que los posts: copiar y pegar, por decisión de diseño (DESIGN.md).

**Consecuencias**: NightScribe no hace astrometría (sigue siendo tarea del software
externo); se cierra el bucle «observar → medir → reportar → contar» sin salir del
proyecto. Tests unitarios con bloques 80-col/ADES válidos e inválidos.

## English

**Context**: in the NEO flow (ADR-019, WORKFLOWS §5) the user measures their images
with their usual astrometry software (Astrometrica or other). Preparing the Minor
Planet Center report is today a manual, format-error-prone step. User decision: **this
is not about generating measurements** — they are simply pasted from whatever software
produced them.

**Decision**: `core/mpc_report.py` —

1. **Paste input**: the user pastes their software output (MPC 80-column format or ADES
   PSV) in the "Process" step of the NEO project.
2. **Validation**: per-line format, observatory code matching the configured one (e.g.
   Z41), object designation consistent with the project context, dates and coordinates
   in range. Human-readable errors, line by line.
3. **Packaging**: a file ready to email to the MPC, saved in the project folder and
   registered in `project_files`. **Sending is done by the user** — same as posts:
   copy & paste, by design (DESIGN.md).

**Consequences**: NightScribe does no astrometry (that remains the external software's
job); the loop "observe → measure → report → tell" closes without leaving the project.
Unit tests with valid and invalid 80-col/ADES blocks.
