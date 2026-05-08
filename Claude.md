# AnalizePub — Contexto del proyecto para Claude

## ¿Qué es AnalizePub?

Herramienta web **gratuita** de auditoría de accesibilidad para ficheros EPUB. Analiza el estado de un EPUB (EPUB2 o EPUB3) y genera un informe detallado con todos los problemas de accesibilidad detectados, sin modificar el fichero original.

AnalizePub **no corrige ni convierte** — solo analiza e informa. Su propósito es dar a editores y maquetadores una visión clara del estado de accesibilidad de sus EPUBs y mostrar qué habría que corregir para cumplir con la EAA (Directiva Europea de Accesibilidad).

**Relación con AccesPub:** AnalizePub es el hermano gratuito de AccesPub. El informe incluye un CTA hacia AccesPub para la corrección automática.

- **URL producción (objetivo):** https://analizepub.app (o https://analiza.accespub.app)
- **Repositorio GitHub:** https://github.com/abserveis/AnalizePub (por crear)
- **Propietario:** Alberto Barajas (info@abserveis.net)

---

## Propósito estratégico

1. **Herramienta de entrada gratuita** — el usuario que analiza su EPUB y ve problemas es el lead más cualificado para AccesPub
2. **Posicionamiento SEO** — una herramienta gratuita recibe enlaces orgánicos que AccesPub no puede recibir
3. **Autoridad de marca** — posiciona ab serveis/AccesPub como referencia técnica en accesibilidad EPUB en español
4. **Sin fricción** — sin registro, sin licencias, sin créditos. Sube el EPUB, obtén el informe.

---

## Qué hace y qué NO hace

### SÍ hace
- Analiza cualquier EPUB (EPUB2 y EPUB3)
- Detecta todos los problemas de accesibilidad (mismo motor que AccesPub)
- Ejecuta EPUBCheck y muestra los resultados
- Genera un informe descargable en HTML
- Muestra qué habría que corregir para cumplir con WCAG 2.1 AA y la EAA
- Indica si cada problema es corregible automáticamente o requiere intervención humana
- Muestra tres indicadores semáforo: EAA, WCAG, EPUBCheck

### NO hace
- No modifica el EPUB original (read-only)
- No convierte EPUB2 a EPUB3
- No aplica ninguna corrección
- No requiere registro ni cuenta de usuario
- No usa créditos ni licencias
- No genera alt text con IA
- No tiene panel de administración complejo

---

## Stack técnico

Idéntico a AccesPub, simplificado:

- **Lenguaje:** Python 3.11
- **Servidor web:** `http.server` estándar (`ThreadingHTTPServer`) — sin Flask ni frameworks externos
- **XML/EPUB:** `lxml`
- **Validación EPUB:** `epubcheck` (wrapper Python, requiere Java — `default-jre-headless`)
- **Iconos:** Lucide (CDN Cloudflare UMD)
- **Idiomas UI:** ES / EN / CA (catalán)
- **Sin Gemini/IA** — no hay corrección de alt text, no se necesita API key

---

## Origen del código — qué se reutiliza de AccesPub

El motor de análisis de AccesPub es 100% reutilizable sin cambios:

| Fichero AccesPub | Uso en AnalizePub | Cambios necesarios |
|---|---|---|
| `epub_a11y/analyzer.py` | ✅ Íntegro — es el núcleo | Ninguno |
| `epub_a11y/models.py` | ✅ Íntegro — dataclasses Issue, ImageItem, etc. | Ninguno |
| `epub_a11y/constants.py` | ✅ Íntegro — namespaces, mappings | Ninguno |
| `epub_a11y/fixes/contrast.py` | ✅ Solo la función de análisis (no la de fix) | Ninguno |
| `epub_a11y/fixes/metadata.py` | ✅ Solo `normalize_dc_date` para análisis | Ninguno |
| `epub_a11y/remediator.py` | ❌ No se usa | — |
| `epub_a11y/fixes/html_fixes.py` | ❌ No se usa | — |
| `epub_a11y/fixes/images.py` | ❌ No se usa | — |
| `epub_a11y/fixes/semantic.py` | ❌ No se usa | — |
| `epub_a11y/fixes/css_consolidator.py` | ❌ No se usa | — |
| `dashboard/app.py` (AccesPub) | 🔄 Base para el nuevo app.py | Reescribir: ~1000 líneas vs ~7000 |
| `dashboard/i18n.py` | 🔄 Base — adaptar y reducir | Mantener estructura, ajustar textos |
| `dashboard/static/style.css` | 🔄 Base — adaptar branding | Cambios mínimos de color/nombre |

**Regla importante:** `analyzer.py` se invoca y se obtiene un `AnalysisReport` con todos los `Issue`. AnalizePub se detiene ahí. AccesPub continúa con `remediator.apply_auto_fixes()`.

---

## Estructura de ficheros del proyecto

```
analizepub/
├── CLAUDE.md                        ← este fichero
├── README.md
├── Dockerfile                       ← idéntico al de AccesPub (Python + Java para EPUBCheck)
├── fly.toml                         ← app=analizepub, region=ams
├── requirements.txt                 ← lxml, epubcheck (sin Pillow, sin google-generativeai)
├── .env.example
├── .gitignore
├── .github/
│   └── workflows/
│       └── deploy.yml               ← CI/CD: push a main → deploy en Fly.io
│
├── dashboard/
│   ├── app.py                       ← FICHERO PRINCIPAL (~1000 líneas)
│   ├── i18n.py                      ← traducciones ES/EN/CA (reducidas)
│   └── static/
│       └── style.css                ← estilos (base AccesPub, branding AnalizePub)
│
└── epub_a11y/                       ← COPIADO ÍNTEGRO de AccesPub (solo leer)
    ├── __init__.py
    ├── analyzer.py                  ← NO MODIFICAR
    ├── models.py                    ← NO MODIFICAR
    ├── constants.py                 ← NO MODIFICAR
    └── fixes/
        ├── contrast.py              ← NO MODIFICAR (se usa solo para análisis)
        └── metadata.py              ← NO MODIFICAR (se usa normalize_dc_date)
```

**Nota:** La carpeta `epub_a11y/` es un subconjunto copiado de AccesPub. No incluye `remediator.py`, `reporter.py`, ni los fixes que modifican EPUBs. Solo los ficheros necesarios para el análisis.

---

## Rutas HTTP (app.py de AnalizePub)

### GET
- `/` — página de upload
- `/report` — informe de análisis (requiere sesión activa)
- `/report/download` — descarga del informe HTML
- `/help` — ayuda y FAQ
- `/legal` — aviso legal / privacidad
- `/set-lang` — cambio de idioma UI
- `/static/*` — assets estáticos

### POST
- `/upload` — recibe el EPUB, lanza análisis, redirige a `/report`
- `/reset` — limpia la sesión y vuelve a `/`

**Total: 9 rutas** (vs ~30 en AccesPub)

---

## Estructura del informe (diseño B+C)

El informe tiene tres bloques:

### 1. Cabecera — Semáforos de estado (Opción C)
Tres indicadores visuales inmediatos:
- 🔴🟡🟢 **Conformidad EAA** — basado en issues críticos/graves de tipo metadata + version
- 🔴🟡🟢 **Accesibilidad WCAG** — basado en issues de imágenes, tablas, contraste, ARIA
- 🔴🟡🟢 **Validación EPUBCheck** — resultado directo de EPUBCheck (errores / warnings / ok)

Lógica de colores:
- 🔴 Rojo: hay errores críticos o graves
- 🟡 Amarillo: hay warnings o issues moderados, nada crítico
- 🟢 Verde: sin issues o solo leves

### 2. Sección A — Estado actual del EPUB
Lo que tiene el fichero tal como está (sea EPUB2 o EPUB3):
- Versión EPUB detectada, idioma, título
- Resultado EPUBCheck (errores y warnings)
- Issues corregibles sin conversión (idioma, algunos metadatos)
- Issues que requieren conversión a EPUB3 (marcados claramente)

### 3. Sección B — Qué habría que hacer para cumplir con la EAA
Lista completa de issues con:
- Tipo, severidad, ubicación
- Descripción del problema
- Si es corregible automáticamente o requiere revisión humana
- Indicador: "AccesPub puede corregir esto automáticamente"

### 4. CTA final — AccesPub
Bloque diferenciado según tipo de EPUB:
- Si EPUB2: "Tu EPUB necesita conversión a EPUB3. AccesPub lo hace automáticamente."
- Si EPUB3: "AccesPub puede aplicar {N} correcciones automáticas a este EPUB."

---

## Flujo de uso

```
1. Usuario accede a /
2. Sube un EPUB (máx. 50 MB, no Fixed Layout)
3. POST /upload → se extrae el EPUB en un directorio temporal
4. analyzer.analyze() → genera AnalysisReport con todos los Issue
5. EPUBCheck wrapper → genera ValidationResult
6. Se guarda todo en sesión (fichero JSON temporal)
7. Redirect a /report
8. render_report() → genera HTML con los tres bloques
9. Usuario puede descargar el informe como HTML
10. La sesión expira en 2h (más corta que AccesPub, no hay revisión manual)
```

---

## Gestión de sesiones (simplificada)

Sin sistema de licencias ni usuarios. Solo sesiones de análisis:

- Sesión = UUID generado en el upload
- Se guarda como cookie de sesión
- Datos en `/tmp/analizepub_sessions/{session_id}/`
  - `report.json` — AnalysisReport serializado
  - `validation.json` — resultado EPUBCheck
  - `meta.json` — nombre del fichero, timestamp
- TTL: 2 horas (auto-limpieza al arrancar o en el siguiente upload)
- El EPUB original NO se guarda (se analiza en memoria con un tempdir y se descarta)

---

## Despliegue (Fly.io)

- **App:** `analizepub` | **Región:** `ams` (Amsterdam)
- **VM:** shared-cpu-1x, 256 MB RAM (suficiente, sin estado complejo)
- **Sin volumen persistente** — las sesiones van a `/tmp` (efímeras, correcto para esta app)
- **Auto-stop/start:** activado

### Variables de entorno
| Variable | Descripción |
|---|---|
| `HOST` | `0.0.0.0` |
| `PORT` | `8080` |

Sin `GOOGLE_API_KEY` — no se usa Gemini en AnalizePub.

### CI/CD
Igual que AccesPub: push a `main` → GitHub Actions → `fly deploy --remote-only`.

### Comandos de operación
```bash
fly status --app analizepub
fly logs --app analizepub
fly ssh console --app analizepub
fly releases list --app analizepub
fly deploy --image registry.fly.io/analizepub:deployment-XXXXX --app analizepub
```

---

## Decisiones técnicas

- **Sin base de datos ni volumen persistente:** las sesiones son efímeras. Si la máquina se reinicia, las sesiones activas se pierden — aceptable porque el análisis tarda segundos y el usuario puede re-subir.
- **Sin sistema de licencias:** la app es completamente libre y abierta.
- **Sin autenticación:** no hay panel de admin porque no hay nada que administrar.
- **EPUBCheck síncrono:** el análisis completo (analyzer + EPUBCheck) es síncrono en el handler de upload. Para EPUBs grandes puede tardar 10-20 segundos — aceptable para una herramienta gratuita sin SLA.
- **EPUB original no persiste:** se analiza en `tempfile.TemporaryDirectory()` y se descarta. Solo se guarda el informe JSON.

---

## Diferencias clave respecto a AccesPub

| Característica | AccesPub | AnalizePub |
|---|---|---|
| Precio | De pago (créditos) | Gratuito |
| Modifica el EPUB | Sí (remediación completa) | No (solo lectura) |
| Sistema de licencias | Sí | No |
| Usuarios admin | Sí | No |
| Revisión manual imágenes | Sí | No |
| Revisión manual tablas | Sí | No |
| Generación alt text IA | Sí (Gemini) | No |
| Conversión EPUB2→3 | Sí | No |
| Exportación EPUB remediado | Sí | No |
| Volumen persistente | Sí (`/data`) | No (`/tmp`) |
| Líneas de app.py | ~7000 | ~1000 |
| Rutas HTTP | ~30 | ~9 |

---

## Estado del proyecto (mayo 2026)

### Por hacer (orden sugerido)
1. Crear repositorio GitHub `abserveis/AnalizePub`
2. Copiar motor de análisis (`epub_a11y/` reducido) desde AccesPub
3. Escribir `dashboard/app.py` nuevo (~1000 líneas)
4. Adaptar `dashboard/i18n.py` con textos de AnalizePub
5. Adaptar `dashboard/static/style.css` con branding AnalizePub
6. Escribir `Dockerfile` y `fly.toml`
7. Configurar GitHub Actions para CI/CD
8. Deploy en Fly.io (`fly launch --name analizepub`)
9. Configurar dominio `analizepub.app` o subdominio de `accespub.app`

### Definiciones pendientes antes de empezar a codificar
- [ ] Dominio final: ¿`analizepub.app` independiente o `analiza.accespub.app`?
- [ ] ¿Límite de uso anti-abuso? (rate limiting por IP, o sin límite)
- [ ] ¿Tamaño máximo de fichero? (sugerido: igual que AccesPub, 50 MB)
- [ ] ¿Informe descargable en HTML únicamente o también PDF?