/* ============================================================
 * NightScribe Landing Page — i18n strings
 * ------------------------------------------------------------
 * Edit ALL texts here, in both languages. Keys mirror the
 * data-i18n attributes in index.html. Keep quotes and commas
 * valid; plain Unicode is fine (★ ▼ → · & included).
 * ============================================================ */
window.I18N = {
  en: {
    // cb
    "cb.status": "ONLINE",

    // nav
    "nav.features": "CAPABILITIES",
    "nav.sources": "SOURCES",
    "nav.about": "SYSTEM",

    // cb
    "cb.get": "▼ GET",

    // hero
    "hero.kicker": "OBSERVATORY TERMINAL // GUI + CLI",
    "hero.version": "Tech Preview",
    "hero.tagline": "Plan the night. Understand the sky. Tell the story.",
    "hero.sub": "OPEN SOURCE · GPL v3",
    "hero.download": "★ DOWNLOAD",
    "hero.github": "GITHUB →",
    "hero.acquiring": "ACQUIRING TARGET...",

    // head
    "head.cap.kick": "// CAPABILITY CATALOGUE",
    "head.cap.title": "Capabilities",

    // feat.1
    "feat.1.title": "Plan Your Night",
    "feat.1.sub": "The best targets, ranked for YOUR observatory.",
    "feat.1.li.1": "8 data sources: NEOs, comets, supernovae, exoplanet transits, HADS stars, variable stars, PCCP candidates",
    "feat.1.li.2": "Smart scoring: 0–100 from Scientific Priority, Observability, Urgency, Outreach",
    "feat.1.li.3": "Safe observation windows against YOUR local horizon",
    "feat.1.li.4": "Real moon phase icon with exact terminator geometry",

    // feat.2
    "feat.2.title": "Smart Scoring",
    "feat.2.sub": "100 points of science, observability & urgency.",
    "feat.2.li.1": "Scientific Priority (35) — how important is this object?",
    "feat.2.li.2": "Observability (30) — altitude, darkness, Moon distance",
    "feat.2.li.3": "Urgency (20) — close approaches, fading transients, fading comets",
    "feat.2.li.4": "Outreach Hook (15) — social media appeal",

    // feat.3
    "feat.3.title": "Explore Any Object",
    "feat.3.sub": "From orbital mechanics to plain English.",
    "feat.3.li.1": "Auto-detects type: Sun, transient, exoplanet, HADS, variable, small body",
    "feat.3.li.2": "Data from JPL, SIMBAD, ExoClock, VSX, NASA Exoplanet Archive + more",
    "feat.3.li.3": "Interactive orbit, sky altitude chart, geocentric approach map",
    "feat.3.li.4": "Bilingual hook line + fact bullets, scientifically grounded",

    // feat.4
    "feat.4.title": "Supernovae & Transients",
    "feat.4.sub": "Blink comparison in one click.",
    "feat.4.li.1": "Align your FITS with PanSTARRS / DSS2 — plate solving included",
    "feat.4.li.2": "Animated GIF (blink/fade), side-by-side PNG, H.264 MP4 export",
    "feat.4.li.3": "Light curve with SN templates: Ia, II-P/L, Ib/c, SLSN, kilonova",
    "feat.4.li.4": "Multi-night follow-up, evolution animations, cadence tracking",

    // feat.5
    "feat.5.title": "Exoplanet Transits",
    "feat.5.sub": "Plan the capture window. Contribute to Ariel.",
    "feat.5.li.1": "Visual timeline: darkness, safe window, baseline, ingress, mid, egress",
    "feat.5.li.2": "Capture plan: frames, exposure, filters — ready to export",
    "feat.5.li.3": "EXOTIC handoff: pre-filled inits.json for NASA/JPL analysis",
    "feat.5.li.4": "Feed ESA's Ariel mission via ExoClock",

    // feat.6
    "feat.6.title": "Variable Stars & HADS",
    "feat.6.sub": "Light curves that tell a story.",
    "feat.6.li.1": "Hybrid HADS catalogue: bundled snapshot + live Google Sheets",
    "feat.6.li.2": "Multi-filter light curves with error bars and phase folding",
    "feat.6.li.3": "Next-extremum predictor: knows when max or min is coming",
    "feat.6.li.4": "Event advisor: detects brightness jumps and outbursts",

    // feat.7
    "feat.7.title": "Social Media Ready",
    "feat.7.sub": "Bilingual posts, tweet & charts — ready to publish.",
    "feat.7.li.1": "Bilingual ES/EN markdown posts with MPC code",
    "feat.7.li.2": "Tweet ≤280 chars with hashtags — copy-paste ready",
    "feat.7.li.3": "PNG charts: orbit, sky, field, transit, light curve, sun",
    "feat.7.li.4": "Instagram caption suggestion included",

    // feat.8
    "feat.8.title": "Project Lifecycle",
    "feat.8.sub": "From discovery to publication.",
    "feat.8.li.1": "Organized workflow: Plan → Process → Publish",
    "feat.8.li.2": "7 object kinds: SN, NEO, Comet, PCCP, Transit, HADS, Variable",
    "feat.8.li.3": "Per-kind outcomes: Confirmed, False Positive, Reported to MPC, ...",
    "feat.8.li.4": "Organized project folders with all generated files",

    // feat.9
    "feat.9.title": "Campaign Coordination",
    "feat.9.sub": "Coordinate multi-night efforts across observers.",
    "feat.9.li.1": "Define protocol: cadence, filters, comparison stars, notes",
    "feat.9.li.2": "Member health: cadence status, event alerts, imminent extrema",
    "feat.9.li.3": "Attach existing projects or create from within the campaign",
    "feat.9.li.4": "Monthly observer-coverage analysis for HADS / variable campaigns",

    // feat.10
    "feat.10.title": "Sun & Sky Monitor",
    "feat.10.sub": "Solar activity, moon phase, visible planets.",
    "feat.10.li.1": "Live SDO imagery, channel-selectable, with active region map",
    "feat.10.li.2": "Sunspot number, F10.7 flux, Kp index, aurora probability",
    "feat.10.li.3": "Moon almanac: real phase icon, illumination, rise/set",
    "feat.10.li.4": "Visible planets tonight with altitude and windows",

    // feat.11
    "feat.11.title": "Observatory Control",
    "feat.11.sub": "Connect to CCDciel. Point. Capture.",
    "feat.11.li.1": "CCDciel via JSON-RPC: CCD temp, tracking, slew state",
    "feat.11.li.2": "Goto with fresh ephemeris — astrometric correction included",
    "feat.11.li.3": "Push capture plans: frames, exposure, filters — or start directly",
    "feat.11.li.4": "Export sequences: NINA JSON, CCDciel .targets, generic CSV",

    // feat.12
    "feat.12.title": "Rich Visualizations",
    "feat.12.sub": "Orbits, sky charts, approach maps — all interactive.",
    "feat.12.li.1": "Animated orbit with time slider and hover data",
    "feat.12.li.2": "Sky chart: target, Moon, horizon, twilight, safe window",
    "feat.12.li.3": "Geocentric approach animation with Moon-distance scale",
    "feat.12.li.4": "All charts: dark theme, wheel zoom, drag pan, PNG export",

    // head
    "head.src.kick": "// STAR CATALOGUE",
    "head.src.title": "22 Data Sources",
    "head.src.note": "ALL NETWORK ACCESS CACHED LOCALLY — NO REDUNDANT API CALLS",

    // cat
    "cat.head.source": "SOURCE",
    "cat.head.type": "TYPE",

    // head
    "head.about.kick": "// SYSTEM INFORMATION",
    "head.about.title": "Built for Astronomers",

    // about
    "about.1.title": "Desktop App",
    "about.1.text": "PySide6 GUI + powerful CLI. Windows, macOS, Linux.",
    "about.2.title": "Bilingual ES/EN",
    "about.2.text": "Complete interface and content in both languages.",
    "about.3.title": "Offline First",
    "about.3.text": "Smart caching, per-source TTL. Sun, Moon, planets offline.",
    "about.4.title": "Open Source",
    "about.4.text": "GPL v3. 1146+ unit tests. Community-driven.",
    "about.author": "CREATOR: FRANCISCO JOSÉ CALVO FERNÁNDEZ — OBSERVATORIO IRYDEO · MPC Z41",

    // footer
    "footer.bar": "SESSION ENDED · THANK YOU FOR OBSERVING",
    "footer.download": "DOWNLOAD",
    "footer.docs": "DOCUMENTATION",
    "footer.github": "GITHUB",
    "footer.license": "LICENSE GPL v3",

    // type
    "type.catalogue": "Catalogue",
    "type.orbital": "Orbital",
    "type.ephemeris": "Ephemeris",
    "type.identifiers": "Identifiers",
    "type.transients": "Transients",
    "type.comets": "Comets",
    "type.candidates": "Candidates",
    "type.alerts": "Alerts",
    "type.transits": "Transits",
    "type.variables": "Variables",
    "type.lightcurves": "Light curves",
    "type.platesolve": "Plate solve",
    "type.exoplanets": "Exoplanets",
    "type.solar": "Solar",
    "type.sunspots": "Sunspots",
    "type.imagery": "Imagery",
    "type.cutouts": "Cutouts",
    "type.local": "Local",
    "type.offline": "Offline",

    // ui
    "ui.observe": "OBSERVE",
    "ui.hide": "HIDE",
    "ui.toggle.toEn": "Switch to English",
    "ui.toggle.toEs": "Cambiar a Español",
  },
  es: {
    // cb
    "cb.status": "EN LÍNEA",

    // nav
    "nav.features": "FUNCIONALIDADES",
    "nav.sources": "FUENTES",
    "nav.about": "SISTEMA",

    // cb
    "cb.get": "▼ OBTENER",

    // hero
    "hero.kicker": "TERMINAL DE OBSERVATORIO // GUI + CLI",
    "hero.version": "v1.0",
    "hero.tagline": "Planifica la noche. Entiende el cielo. Cuenta la historia.",
    "hero.sub": "BILINGÜE ES/EN · CÓDIGO ABIERTO · GPL v3 · MPC Z41",
    "hero.download": "★ DESCARGAR",
    "hero.github": "GITHUB →",
    "hero.acquiring": "ADQUIRIENDO OBJETIVO...",

    // head
    "head.cap.kick": "// CATÁLOGO DE FUNCIONALIDADES",
    "head.cap.title": "Funcionalidades",

    // feat.1
    "feat.1.title": "Planifica tu Noche",
    "feat.1.sub": "Los mejores objetivos, rankeados para TU observatorio.",
    "feat.1.li.1": "8 fuentes de datos: NEOs, cometas, supernovas, tránsitos de exoplanetas, estrellas HADS, estrellas variables, candidatos PCCP",
    "feat.1.li.2": "Scoring inteligente: 0–100 de Prioridad Científica, Observabilidad, Urgencia, Divulgación",
    "feat.1.li.3": "Ventanas de observación seguras contra TU horizonte local",
    "feat.1.li.4": "Icono de fase lunar real con geometría exacta del terminador",

    // feat.2
    "feat.2.title": "Scoring Inteligente",
    "feat.2.sub": "100 puntos de ciencia, observabilidad y urgencia.",
    "feat.2.li.1": "Prioridad Científica (35) — ¿cuán importante es este objeto?",
    "feat.2.li.2": "Observabilidad (30) — altitud, oscuridad, distancia lunar",
    "feat.2.li.3": "Urgencia (20) — acercamientos, transitorios que se apagan, cometas que se apagan",
    "feat.2.li.4": "Gancho Divulgativo (15) — atractivo para redes sociales",

    // feat.3
    "feat.3.title": "Explora Cualquier Objeto",
    "feat.3.sub": "De la mecánica orbital al lenguaje claro.",
    "feat.3.li.1": "Auto-detecta el tipo: Sol, transitorio, exoplaneta, HADS, variable, cuerpo menor",
    "feat.3.li.2": "Datos de JPL, SIMBAD, ExoClock, VSX, NASA Exoplanet Archive y más",
    "feat.3.li.3": "Órbita interactiva, gráfico de altitud, mapa de enfoque geocéntrico",
    "feat.3.li.4": "Línea de enganche bilingüe + datos clave, científicamente fundamentados",

    // feat.4
    "feat.4.title": "Supernovas y Transitorios",
    "feat.4.sub": "Comparación blink en un clic.",
    "feat.4.li.1": "Alinea tu FITS con PanSTARRS / DSS2 — plate solving incluido",
    "feat.4.li.2": "GIF animado (blink/fade), PNG lado a lado, exportación H.264 MP4",
    "feat.4.li.3": "Curva de luz con plantillas SN: Ia, II-P/L, Ib/c, SLSN, kilonova",
    "feat.4.li.4": "Seguimiento multi-noche, animaciones de evolución, seguimiento de cadencia",

    // feat.5
    "feat.5.title": "Tránsitos de Exoplanetas",
    "feat.5.sub": "Planifica la ventana de captura. Contribuye a Ariel.",
    "feat.5.li.1": "Línea temporal visual: oscuridad, ventana segura, baseline, ingreso, medio, egreso",
    "feat.5.li.2": "Plan de captura: fotogramas, exposición, filtros — listo para exportar",
    "feat.5.li.3": "Handoff EXOTIC: inits.json pre-rellenado para análisis NASA/JPL",
    "feat.5.li.4": "Alimenta la misión Ariel de ESA vía ExoClock",

    // feat.6
    "feat.6.title": "Estrellas Variables y HADS",
    "feat.6.sub": "Curvas de luz que cuentan una historia.",
    "feat.6.li.1": "Catálogo HADS híbrido: snapshot incluido + Google Sheets en vivo",
    "feat.6.li.2": "Curvas de luz multicolor con barras de error y fase plegada",
    "feat.6.li.3": "Predicción del próximo extremo: sabe cuándo llega el máximo o mínimo",
    "feat.6.li.4": "Asesor de eventos: detecta saltos de brillo y estallidos",

    // feat.7
    "feat.7.title": "Listo para Redes Sociales",
    "feat.7.sub": "Posts bilingües, tweet y gráficos — listos para publicar.",
    "feat.7.li.1": "Posts bilingües ES/EN en markdown con código MPC",
    "feat.7.li.2": "Tweet ≤280 caracteres con hashtags — listo para copiar",
    "feat.7.li.3": "Gráficos PNG: órbita, cielo, campo, tránsito, curva de luz, sol",
    "feat.7.li.4": "Sugerencia de caption de Instagram incluida",

    // feat.8
    "feat.8.title": "Ciclo de Vida del Proyecto",
    "feat.8.sub": "Del descubrimiento a la publicación.",
    "feat.8.li.1": "Flujo organizado: Planificar → Procesar → Publicar",
    "feat.8.li.2": "7 tipos de objeto: SN, NEO, Cometa, PCCP, Tránsito, HADS, Variable",
    "feat.8.li.3": "Resultados por tipo: Confirmado, Falso Positivo, Reportado al MPC, ...",
    "feat.8.li.4": "Carpetas de proyecto organizadas con todos los archivos generados",

    // feat.9
    "feat.9.title": "Campañas Coordinadas",
    "feat.9.sub": "Coordina esfuerzos multi-noche entre observadores.",
    "feat.9.li.1": "Define protocolo: cadencia, filtros, estrellas comparación, notas",
    "feat.9.li.2": "Salud de miembros: estado de cadencia, alertas de eventos, extremos inminentes",
    "feat.9.li.3": "Adjunta proyectos existentes o crea desde la campaña",
    "feat.9.li.4": "Análisis mensual de cobertura de observadores para campañas HADS / variables",

    // feat.10
    "feat.10.title": "Monitor Sol y Cielo",
    "feat.10.sub": "Actividad solar, fase lunar, planetas visibles.",
    "feat.10.li.1": "Imágenes SDO en vivo, selección de canal, mapa de regiones activas",
    "feat.10.li.2": "Número de manchas, flujo F10.7, índice Kp, probabilidad de auroras",
    "feat.10.li.3": "Almanaque lunar: icono de fase real, iluminación, salida/ocaso",
    "feat.10.li.4": "Planetas visibles esta noche con altitud y ventanas",

    // feat.11
    "feat.11.title": "Control del Observatorio",
    "feat.11.sub": "Conecta a CCDciel. Apunta. Captura.",
    "feat.11.li.1": "CCDciel vía JSON-RPC: temperatura CCD, tracking, estado de apuntado",
    "feat.11.li.2": "Goto con efemérides frescas — corrección astrométrica incluida",
    "feat.11.li.3": "Envía planes de captura: fotogramas, exposición, filtros — o inicia directamente",
    "feat.11.li.4": "Exporta secuencias: NINA JSON, CCDciel .targets, CSV genérico",

    // feat.12
    "feat.12.title": "Visualizaciones Ricas",
    "feat.12.sub": "Órbitas, mapas celestes, mapas de enfoque — todo interactivo.",
    "feat.12.li.1": "Órbita animada con slider de tiempo y datos al pasar",
    "feat.12.li.2": "Mapa celeste: objetivo, Luna, horizonte, crepúsculo, ventana segura",
    "feat.12.li.3": "Animación de enfoque geocéntrico con escala de distancias lunares",
    "feat.12.li.4": "Todos los gráficos: tema oscuro, zoom, arrastre, exportación PNG",

    // head
    "head.src.kick": "// CATÁLOGO ESTELAR",
    "head.src.title": "22 Fuentes de Datos",
    "head.src.note": "TODO ACCESO A RED SE CACHEADO LOCALMENTE — SIN LLAMADAS API REDUNDANTES",

    // cat
    "cat.head.source": "FUENTE",
    "cat.head.type": "TIPO",

    // head
    "head.about.kick": "// INFORMACIÓN DEL SISTEMA",
    "head.about.title": "Hecho para Astrónomos",

    // about
    "about.1.title": "Aplicación de Escritorio",
    "about.1.text": "GUI PySide6 + CLI potente. Windows, macOS, Linux.",
    "about.2.title": "Bilingüe ES/EN",
    "about.2.text": "Interfaz y contenido completos en ambos idiomas.",
    "about.3.title": "Primero Offline",
    "about.3.text": "Caché inteligente, TTL por fuente. Sol, Luna, planetas offline.",
    "about.4.title": "Código Abierto",
    "about.4.text": "GPL v3. 1146+ tests unitarios. Impulsado por la comunidad.",
    "about.author": "CREADOR: FRANCISCO JOSÉ CALVO FERNÁNDEZ — OBSERVATORIO IRYDEO · MPC Z41",

    // footer
    "footer.bar": "SESIÓN TERMINADA · GRACIAS POR OBSERVAR",
    "footer.download": "DESCARGAR",
    "footer.docs": "DOCUMENTACIÓN",
    "footer.github": "GITHUB",
    "footer.license": "LICENCIA GPL v3",

    // type
    "type.catalogue": "Catálogo",
    "type.orbital": "Orbital",
    "type.ephemeris": "Efemérides",
    "type.identifiers": "Identificadores",
    "type.transients": "Transitorios",
    "type.comets": "Cometas",
    "type.candidates": "Candidatos",
    "type.alerts": "Alertas",
    "type.transits": "Tránsitos",
    "type.variables": "Variables",
    "type.lightcurves": "Curvas de luz",
    "type.platesolve": "Plate solving",
    "type.exoplanets": "Exoplanetas",
    "type.solar": "Solar",
    "type.sunspots": "Manchas solares",
    "type.imagery": "Imágenes",
    "type.cutouts": "Recortes",
    "type.local": "Local",
    "type.offline": "Offline",

    // ui
    "ui.observe": "OBSERVAR",
    "ui.hide": "OCULTAR",
    "ui.toggle.toEn": "Switch to English",
    "ui.toggle.toEs": "Cambiar a Español",
  }
};
