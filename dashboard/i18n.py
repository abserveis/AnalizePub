"""
Internationalisation helpers for AnalizePub.

Supported languages: en (English), es (Spanish), ca (Catalan).
Falls back to English for any missing key.

This module is intentionally minimal — AnalizePub has many fewer screens
than AccesPub (no credits, no licences, no manual review).
"""

from __future__ import annotations

# ── Helpers ──────────────────────────────────────────────────────────────────

SUPPORTED_LANGS = ('es', 'en', 'ca')
DEFAULT_LANG = 'es'


def t(lang: str, key: str, **kwargs) -> str:
    """Translate `key` to `lang`. Falls back to English, then to the key
    itself if missing in both. Substitutes `{name}` placeholders from kwargs.
    """
    table = _T.get(lang) or _T['en']
    value = table.get(key)
    if value is None:
        # Fallback to English then to the raw key.
        value = _T['en'].get(key, key)
    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError):
            return value
    return value


def lang_from_cookie_or_header(cookie_value: str | None,
                               accept_language: str | None) -> str:
    """Return the best-matching supported language."""
    if cookie_value and cookie_value in SUPPORTED_LANGS:
        return cookie_value
    if accept_language:
        for chunk in accept_language.split(','):
            code = chunk.split(';', 1)[0].strip().lower()
            if not code:
                continue
            primary = code.split('-', 1)[0]
            if primary in SUPPORTED_LANGS:
                return primary
    return DEFAULT_LANG


# ── Translations ─────────────────────────────────────────────────────────────

_T: dict[str, dict[str, str]] = {

# ── Spanish (default) ───────────────────────────────────────────────────────
'es': {
    # Brand
    'brand_name':         'AnalizePub',
    'brand_tagline':      'Auditoría gratuita de accesibilidad EPUB',
    'brand_by':           'por ab serveis',

    # Navigation
    'nav_home':           'Inicio',
    'nav_help':           'Ayuda',
    'nav_legal':          'Aviso legal',

    # Footer
    'footer_text':        'AnalizePub — Análisis gratuito de accesibilidad EPUB',
    'footer_legal':       'Aviso legal',
    'footer_privacy':     'Privacidad',
    'footer_accespub':    'Conoce AccesPub',

    # Language
    'lang_label':         'Idioma:',
    'lang_es':            'Español',
    'lang_en':            'English',
    'lang_ca':            'Català',
    'lang_short_es':      'ES',
    'lang_short_en':      'EN',
    'lang_short_ca':      'CA',
    'confirm_lang_report':'Cambiar de idioma eliminará el informe actual y volverás al inicio. ¿Continuar?',
    'confirm_lang_file':  'Cambiar de idioma deseleccionará el archivo. ¿Continuar?',
    'skip_to_main':       'Saltar al contenido principal',
    'aria_main_nav':      'Navegación principal',
    'aria_brand':         'AnalizePub — Inicio',

    # ── Upload page ────────────────────────────────────────────────────────
    'upload_h1':          'Analiza la accesibilidad de tu EPUB',
    'upload_subtitle':    'Sube un EPUB y obtén un informe detallado con todos los problemas de '
                          'accesibilidad detectados. AnalizePub no modifica el fichero — solo '
                          'analiza e informa, gratis y sin registro.',

    'upload_click':       'Haz clic para seleccionar un EPUB',
    'upload_drag_hint':   'o arrastra y suelta el fichero aquí',
    'upload_choose':      'Elegir EPUB',
    'upload_analyze':     'Analizar →',
    'upload_hint':        'Soporta EPUB 2.0.1 y EPUB 3.x (solo reflowable, máx. 50 MB)',
    'upload_fixed_note':  'Los EPUB Fixed Layout no se analizan: estructuralmente no pueden ser accesibles.',
    'upload_privacy_note':'Tu fichero se procesa en memoria y se descarta tras el análisis. '
                          'Nunca guardamos copias del contenido.',
    'upload_invalid_type':'Solo se admiten ficheros .epub. Suelta un EPUB válido.',
    'upload_too_large':   'El fichero supera el límite de 50 MB.',
    'loading_text':       'Analizando tu EPUB…',
    'loading_hint':       'Puede tardar varios segundos en EPUBs grandes.',

    # What we check
    'what_h2':            '¿Qué analiza AnalizePub?',
    'what_intro':         'AnalizePub utiliza el mismo motor de análisis que AccesPub. Comprueba '
                          'todo lo que hay que comprobar para que un EPUB sea conforme a la EAA '
                          '(Directiva Europea de Accesibilidad) y al estándar WCAG 2.1 AA:',
    'what_li_metadata':   'Metadatos de accesibilidad obligatorios (schema:accessMode, accessibilityFeature…).',
    'what_li_lang':       'Idioma de la publicación y de cada documento.',
    'what_li_semantics':  'Estructura semántica (epub:type, roles DPUB-ARIA, secciones, navegación).',
    'what_li_images':     'Texto alternativo de las imágenes y detección de imágenes decorativas.',
    'what_li_tables':     'Tablas de datos: cabeceras, scope y captions.',
    'what_li_contrast':   'Contraste de color en CSS y estilos en línea.',
    'what_li_nav':        'Documento de navegación, page-list y orden de la TOC.',
    'what_li_epubcheck':  'Validación con EPUBCheck oficial.',

    # ── Report page ───────────────────────────────────────────────────────
    'report_h1':          'Informe de accesibilidad',
    'report_filename':    'Fichero analizado',
    'report_analyzed_at': 'Análisis realizado',
    'report_back':        '← Analizar otro EPUB',
    'report_download_html':'Descargar informe (HTML)',
    'report_print':       'Imprimir / Guardar como PDF',
    'report_session_expired': 'La sesión ha caducado. Sube de nuevo el EPUB para volver a analizarlo.',

    # Indicators (semaforos)
    'indic_title':        'Estado de accesibilidad',
    'indic_eaa':          'Conformidad EAA',
    'indic_wcag':         'Accesibilidad WCAG 2.1 AA',
    'indic_epubcheck':    'Validación EPUBCheck',
    'indic_status_ok':    'Conforme',
    'indic_status_warn':  'Mejorable',
    'indic_status_error': 'No conforme',
    'indic_eaa_ok':       'Sin problemas críticos para la EAA.',
    'indic_eaa_warn':     'Falta algún metadato o atributo. Subsanable sin conversión.',
    'indic_eaa_error':    'Hay incumplimientos críticos para la EAA.',
    'indic_wcag_ok':      'Sin problemas significativos de accesibilidad.',
    'indic_wcag_warn':    'Hay problemas de accesibilidad de severidad moderada.',
    'indic_wcag_error':   'Hay problemas serios de accesibilidad (WCAG).',
    'indic_epubcheck_ok': 'EPUBCheck no reporta errores ni avisos.',
    'indic_epubcheck_warn':'EPUBCheck reporta {n} avisos.',
    'indic_epubcheck_error':'EPUBCheck reporta {errors} errores y {warnings} avisos.',

    # Section A — Current state
    'sec_a_h2':           'Estado actual del EPUB',
    'sec_a_intro':        'Este es el estado del EPUB tal como está, sin tocar nada.',
    'meta_version':       'Versión EPUB',
    'meta_language':      'Idioma',
    'meta_title':         'Título',
    'meta_total_docs':    'Documentos',
    'meta_total_images':  'Imágenes',
    'meta_unknown':       'Desconocido',
    'epubcheck_h3':       'Resultado de EPUBCheck',
    'epubcheck_ok':       'EPUBCheck no ha detectado errores ni avisos.',
    'epubcheck_summary':  '{errors} errores · {warnings} avisos · {fatals} fatales',
    'epubcheck_show':     'Ver detalles',
    'epubcheck_hide':     'Ocultar detalles',
    'epubcheck_unavailable':'EPUBCheck no está disponible en este entorno.',
    'epubcheck_not_run':  'No se ha ejecutado EPUBCheck.',
    'epubcheck_col_severity':'Severidad',
    'epubcheck_col_id':   'Código',
    'epubcheck_col_location':'Ubicación',
    'epubcheck_col_message':'Mensaje',
    'sev_fatal':          'Fatal',
    'sev_error':          'Error',
    'sev_warning':        'Aviso',
    'sev_info':           'Info',
    'sev_usage':          'Uso',

    # Section B — What to fix
    'sec_b_h2':           'Qué habría que corregir para cumplir con la EAA',
    'sec_b_intro':        'Lista completa de problemas detectados por el motor de análisis. Se '
                          'indica si cada problema es corregible automáticamente o si necesita '
                          'una revisión humana.',
    'sec_b_no_issues':    '¡Enhorabuena! El motor de análisis no ha detectado ningún problema de accesibilidad.',
    'sec_b_summary':      '{total} problemas · {auto} corregibles automáticamente · {manual} requieren revisión',
    'sec_b_filter_all':   'Todos',
    'sec_b_filter_critical':'Críticos',
    'sec_b_filter_serious':'Graves',
    'sec_b_filter_moderate':'Moderados',
    'sec_b_filter_minor': 'Leves',

    # Issue table columns
    'issue_col_severity': 'Severidad',
    'issue_col_type':     'Tipo',
    'issue_col_location': 'Ubicación',
    'issue_col_description':'Descripción',
    'issue_col_fix':      'Corrección',

    # Issue severity labels
    'severity_critical':  'Crítico',
    'severity_serious':   'Grave',
    'severity_moderate':  'Moderado',
    'severity_minor':     'Leve',

    # Issue type labels
    'type_metadata':      'Metadatos',
    'type_html':          'HTML',
    'type_image':         'Imagen',
    'type_table':         'Tabla',
    'type_nav':           'Navegación',
    'type_language':      'Idioma',
    'type_css':           'CSS',
    'type_version':       'Versión',
    'type_other':         'Otros',
    'type_aria':          'ARIA',
    'type_landmarks':     'Landmarks',
    'type_a11y':          'Accesibilidad',
    'type_ncx':           'NCX',
    'type_opf':           'OPF',

    # Fix labels
    'fix_auto':           'Corregible automáticamente por AccesPub',
    'fix_manual':         'Requiere revisión humana',
    'fix_conversion':     'Requiere conversión EPUB2 → EPUB3',

    # ── Issue descriptions (engine emits these via description_key) ───────
    'issue_desc_lang_mismatch':       'El OPF declara idioma "{declared}" pero el contenido parece estar en "{detected}".',
    'issue_dc_identifier_empty':      'dc:identifier está vacío — se generará un urn:uuid automáticamente.',
    'issue_dc_required_empty':        'dc:{field} está vacío — necesario para EPUBCheck, debe rellenarse manualmente.',
    'issue_dc_optional_empty':        'dc:{field} está vacío — el campo opcional se eliminará durante la corrección.',
    'issue_dc_date_invalid_fixable':  'dc:date "{date}" no tiene formato W3CDTF. Se corregirá automáticamente.',
    'issue_dc_date_invalid_ambiguous':'dc:date "{date}" es ambiguo (podría ser DD-MM-YYYY o MM-DD-YYYY). Necesita corrección manual.',
    'issue_desc_orphan_pagebreaks':   '{n} elementos pagebreak en el contenido sin entrada correspondiente en el page-list.',
    'issue_desc_lang':                'Falta el atributo lang en el elemento <html>.',
    'issue_desc_title':               'Elemento <title> ausente o vacío en la cabecera del documento.',
    'issue_desc_caption':             'Tabla sin elemento <caption>.',
    'issue_desc_missing_th':          'Tabla sin elementos de cabecera <th>.',
    'issue_desc_th_scope':            'Elemento <th> sin atributo scope.',

    # ── Pattern-based translations (engine emits raw English; we match) ──
    'issue_pat_missing_a11y_meta':   'Falta el metadato de accesibilidad obligatorio: {prop}',
    'issue_pat_img_no_alt':          'Imagen sin atributo alt: {src}',
    'issue_pat_cover_no_alt':        'La imagen de portada no tiene texto alternativo: {href}',
    'issue_pat_epub2_to_3':          'El documento está en formato EPUB {version}. La normativa (EAA y EPUB Accessibility 1.1) no exige convertir a EPUB 3, pero EPUB 3 facilita mucho el cumplimiento por su soporte nativo de metadatos de accesibilidad, navegación HTML y semántica estructural.',
    'issue_pat_inline_styles':       'El documento contiene atributos style en línea. Se extraerán a la hoja de estilos.',
    'issue_pat_decorative_alt':      'Imagen decorativa: se marcará con alt="" automáticamente. Imagen: {src}',
    'issue_pat_empty_alt':           'Imagen con alt="" — verifica si es realmente decorativa: {src}',
    'issue_pat_generic_alt':         'Imagen con alt genérico ("{alt}") que no describe el contenido: {src}',
    'issue_pat_epub_type_role':      'Elemento con epub:type="{etype}" sin el role ARIA correspondiente "{role}".',
    'issue_pat_nav_no_label':        '<nav epub:type="{etype}"> sin aria-label — los lectores de pantalla no pueden distinguir el landmark.',
    'issue_pat_ncx_uid':             'NCX-001: el identificador NCX ("{ncx}") no coincide con el identificador único del OPF ("{opf}").',
    'issue_pat_contrast':            'Contraste de color insuficiente en "{selector}": {fg} sobre {bg} — ratio {ratio}.',

    # Manual review hints (informative, since AnalizePub does not do it)
    'review_images_h3':   'Imágenes que necesitan revisión humana',
    'review_images_body': 'Hay {n} imágenes en este EPUB cuyo texto alternativo necesita ser '
                          'redactado o revisado por una persona. AnalizePub no genera alt text; '
                          'AccesPub sí lo hace asistido por IA.',
    'review_tables_h3':   'Tablas que necesitan revisión humana',
    'review_tables_body': 'Hay {n} tablas que requieren decidir si son tablas de datos o de '
                          'maquetación, y si la primera fila debe convertirse en cabecera.',
    'review_lang_h3':     'Etiquetas de idioma que necesitan revisión',
    'review_lang_body':   'Hay {n} grupos de elementos con xml:lang sospechoso (un patrón típico '
                          'de exportación desde InDesign). Es necesario decidir si eliminarlos.',

    # ── CTA AccesPub ──────────────────────────────────────────────────────
    'cta_h2':             '¿Cómo arreglar todo esto?',
    'cta_epub2_title':    'Tu EPUB está en formato EPUB 2',
    'cta_epub2_body':     'La normativa (EAA y EPUB Accessibility 1.1) no exige convertir a '
                          'EPUB 3 — admite también EPUB 2 — pero EPUB 3 es lo que esperan la '
                          'mayoría de plataformas y catálogos, y facilita mucho el cumplimiento '
                          'por su soporte nativo de metadatos de accesibilidad, navegación HTML '
                          'y semántica estructural. AccesPub convierte EPUB 2 a EPUB 3 y aplica '
                          'todas las correcciones automáticas en una sola operación.',
    'cta_epub3_title':    'AccesPub puede aplicar {n} correcciones automáticas a este EPUB',
    'cta_epub3_body':     'AccesPub aplica las correcciones automáticas y te guía por las '
                          'decisiones que solo una persona puede tomar (alt text, tablas, idiomas).',
    'cta_clean_title':    'Tu EPUB es accesible',
    'cta_clean_body':     'No hace falta corregir nada importante. Si quieres asegurar el '
                          'cumplimiento total de la EAA, AccesPub puede aplicar pequeños retoques.',
    'cta_button':         'Ir a AccesPub',
    'cta_url':            'https://accespub.app',

    # ── Help page ─────────────────────────────────────────────────────────
    'help_h1':            'Ayuda y preguntas frecuentes',
    'help_q1':            '¿AnalizePub modifica mi EPUB?',
    'help_a1':            'No. AnalizePub únicamente lee el fichero y genera un informe. El EPUB '
                          'original no se altera, no se almacena y no se reenvía a ningún sitio.',
    'help_q2':            '¿Cuánto tarda el análisis?',
    'help_a2':            'Entre 5 y 20 segundos para un EPUB típico. Para EPUBs grandes (cerca '
                          'del límite de 50 MB) puede tardar más.',
    'help_q3':            '¿Qué pasa con mi fichero después?',
    'help_a3':            'El EPUB se descarta inmediatamente al terminar el análisis. Solo se '
                          'guarda el informe (sin contenido del libro) en una sesión temporal de '
                          '2 horas, después de la cual también se borra.',
    'help_q4':            '¿Por qué algunos problemas no son corregibles automáticamente?',
    'help_a4':            'Tareas como redactar el alt text de una imagen o decidir si una tabla '
                          'es de datos o de maquetación requieren juicio humano. AccesPub te '
                          'guía por esas decisiones; AnalizePub solo informa de cuántas hay.',
    'help_q5':            '¿AnalizePub funciona con EPUB 2?',
    'help_a5':            'Sí. Detecta todos los problemas y, además, te indica cuáles requieren '
                          'conversión a EPUB 3 para poder solucionarse.',
    'help_q6':            '¿Cuál es la diferencia con AccesPub?',
    'help_a6':            'AnalizePub solo analiza e informa (gratis). AccesPub corrige '
                          'automáticamente, convierte EPUB 2 a EPUB 3 y exporta el EPUB ya '
                          'remediado (de pago).',

    # ── Legal page ────────────────────────────────────────────────────────
    'legal_h1':           'Aviso legal y política de privacidad',
    'legal_owner_h2':     'Titular',
    'legal_owner_body':   'AnalizePub es un servicio prestado por Alberto Barajas, '
                          'bajo el nombre comercial «ab serveis». '
                          'NIF: 46629726D. Domicilio: Joan Miró, 19. 08319 Dosrius. '
                          'Contacto: info@abserveis.net.',
    'legal_purpose_h2':   'Finalidad del servicio',
    'legal_purpose_body': 'AnalizePub analiza ficheros EPUB y genera informes de accesibilidad. '
                          'No corrige el fichero, no convierte versiones y no exporta nada.',
    'legal_data_h2':      'Datos personales y privacidad',
    'legal_data_body':    'No recogemos datos personales. Las sesiones de análisis se identifican '
                          'mediante una cookie técnica anónima (UUID) que caduca a las 2 horas. '
                          'No usamos cookies de seguimiento, analítica de terceros ni publicidad.',
    'legal_files_h2':     'Tratamiento de tus ficheros',
    'legal_files_body':   'El EPUB se procesa en memoria y se descarta inmediatamente. Únicamente '
                          'se guarda el informe (sin contenido del libro) en un fichero temporal '
                          'que se borra a las 2 horas.',
    'legal_liability_h2': 'Limitación de responsabilidad',
    'legal_liability_body':'AnalizePub se ofrece "tal cual", sin garantías. El informe es '
                          'orientativo: la conformidad final con la EAA y WCAG depende de '
                          'múltiples factores y de la revisión humana. ab serveis no se hace '
                          'responsable del uso que se haga del informe.',

    # ── Errors / messages ─────────────────────────────────────────────────
    'err_no_file':        'No se ha enviado ningún fichero.',
    'err_invalid_epub':   'El fichero no es un EPUB válido.',
    'err_too_large':      'El fichero supera el tamaño máximo permitido (50 MB).',
    'err_fixed_layout':   'Los EPUB Fixed Layout no son procesables.',
    'err_analysis_failed':'El análisis ha fallado: {detail}',
    'err_session_missing':'No hay informe asociado a tu sesión. Sube un EPUB de nuevo.',
    'err_404':            'Página no encontrada.',
    'err_500':            'Error interno del servidor.',
},

# ── English ─────────────────────────────────────────────────────────────────
'en': {
    'brand_name':         'AnalizePub',
    'brand_tagline':      'Free EPUB accessibility audit',
    'brand_by':           'by ab serveis',

    'nav_home':           'Home',
    'nav_help':           'Help',
    'nav_legal':          'Legal',

    'footer_text':        'AnalizePub — Free EPUB accessibility analysis',
    'footer_legal':       'Legal notice',
    'footer_privacy':     'Privacy',
    'footer_accespub':    'Discover AccesPub',

    'lang_label':         'Language:',
    'lang_es':            'Español',
    'lang_en':            'English',
    'lang_ca':            'Català',
    'lang_short_es':      'ES',
    'lang_short_en':      'EN',
    'lang_short_ca':      'CA',
    'confirm_lang_report':'Changing language will discard the current report and bring you back to the home page. Continue?',
    'confirm_lang_file':  'Changing language will deselect the file. Continue?',
    'skip_to_main':       'Skip to main content',
    'aria_main_nav':      'Main navigation',
    'aria_brand':         'AnalizePub — Home',

    'upload_h1':          'Audit your EPUB for accessibility',
    'upload_subtitle':    'Upload an EPUB and get a detailed report listing every accessibility '
                          'issue we find. AnalizePub never modifies your file — it only audits '
                          'and reports. Free, no sign-up.',

    'upload_click':       'Click to select an EPUB',
    'upload_drag_hint':   'or drop the file here',
    'upload_choose':      'Choose EPUB',
    'upload_analyze':     'Analyse →',
    'upload_hint':        'EPUB 2.0.1 and EPUB 3.x supported (reflowable only, max 50 MB).',
    'upload_fixed_note':  'Fixed Layout EPUBs are not analysed: structurally they cannot be accessible.',
    'upload_privacy_note':'Your file is processed in memory and discarded right after the analysis. '
                          'We never keep copies of your content.',
    'upload_invalid_type':'Only .epub files are accepted.',
    'upload_too_large':   'This file exceeds the 50 MB limit.',
    'loading_text':       'Analysing your EPUB…',
    'loading_hint':       'May take a few seconds for large files.',

    'what_h2':            'What does AnalizePub check?',
    'what_intro':         'AnalizePub uses the same engine as AccesPub. It checks everything '
                          'required to make an EPUB compliant with the European Accessibility '
                          'Act (EAA) and WCAG 2.1 AA:',
    'what_li_metadata':   'Required accessibility metadata (schema:accessMode, accessibilityFeature…).',
    'what_li_lang':       'Publication and per-document language.',
    'what_li_semantics':  'Semantic structure (epub:type, DPUB-ARIA roles, sections, navigation).',
    'what_li_images':     'Image alt text and detection of decorative images.',
    'what_li_tables':     'Data tables: headers, scope, captions.',
    'what_li_contrast':   'Colour contrast in CSS and inline styles.',
    'what_li_nav':        'Navigation document, page-list and TOC ordering.',
    'what_li_epubcheck':  'Official EPUBCheck validation.',

    'report_h1':          'Accessibility report',
    'report_filename':    'Analysed file',
    'report_analyzed_at': 'Analysed on',
    'report_back':        '← Analyse another EPUB',
    'report_download_html':'Download report (HTML)',
    'report_print':       'Print / Save as PDF',
    'report_session_expired': 'Your session has expired. Upload your EPUB again to re-analyse.',

    'indic_title':        'Accessibility status',
    'indic_eaa':          'EAA compliance',
    'indic_wcag':         'WCAG 2.1 AA accessibility',
    'indic_epubcheck':    'EPUBCheck validation',
    'indic_status_ok':    'Compliant',
    'indic_status_warn':  'Improvable',
    'indic_status_error': 'Non-compliant',
    'indic_eaa_ok':       'No EAA-critical issues found.',
    'indic_eaa_warn':     'Some metadata or attribute is missing. Fixable without conversion.',
    'indic_eaa_error':    'Critical EAA breaches were found.',
    'indic_wcag_ok':      'No significant accessibility issues.',
    'indic_wcag_warn':    'Some moderate accessibility issues found.',
    'indic_wcag_error':   'Serious accessibility issues found (WCAG).',
    'indic_epubcheck_ok': 'EPUBCheck reports no errors or warnings.',
    'indic_epubcheck_warn':'EPUBCheck reports {n} warnings.',
    'indic_epubcheck_error':'EPUBCheck reports {errors} errors and {warnings} warnings.',

    'sec_a_h2':           'Current state of the EPUB',
    'sec_a_intro':        'This is what the file looks like as-is, without any modification.',
    'meta_version':       'EPUB version',
    'meta_language':      'Language',
    'meta_title':         'Title',
    'meta_total_docs':    'Documents',
    'meta_total_images':  'Images',
    'meta_unknown':       'Unknown',
    'epubcheck_h3':       'EPUBCheck result',
    'epubcheck_ok':       'EPUBCheck found no errors or warnings.',
    'epubcheck_summary':  '{errors} errors · {warnings} warnings · {fatals} fatal',
    'epubcheck_show':     'Show details',
    'epubcheck_hide':     'Hide details',
    'epubcheck_unavailable':'EPUBCheck is not available in this environment.',
    'epubcheck_not_run':  'EPUBCheck has not been run.',
    'epubcheck_col_severity':'Severity',
    'epubcheck_col_id':   'Code',
    'epubcheck_col_location':'Location',
    'epubcheck_col_message':'Message',
    'sev_fatal':          'Fatal',
    'sev_error':          'Error',
    'sev_warning':        'Warning',
    'sev_info':           'Info',
    'sev_usage':          'Usage',

    'sec_b_h2':           'What to fix to comply with the EAA',
    'sec_b_intro':        'Full list of issues detected by the analysis engine. Each issue is '
                          'tagged as auto-fixable or requiring human review.',
    'sec_b_no_issues':    'Excellent! The analysis engine found no accessibility issues.',
    'sec_b_summary':      '{total} issues · {auto} auto-fixable · {manual} need review',
    'sec_b_filter_all':   'All',
    'sec_b_filter_critical':'Critical',
    'sec_b_filter_serious':'Serious',
    'sec_b_filter_moderate':'Moderate',
    'sec_b_filter_minor': 'Minor',

    'issue_col_severity': 'Severity',
    'issue_col_type':     'Type',
    'issue_col_location': 'Location',
    'issue_col_description':'Description',
    'issue_col_fix':      'Fix',

    'severity_critical':  'Critical',
    'severity_serious':   'Serious',
    'severity_moderate':  'Moderate',
    'severity_minor':     'Minor',

    'type_metadata':      'Metadata',
    'type_html':          'HTML',
    'type_image':         'Image',
    'type_table':         'Table',
    'type_nav':           'Navigation',
    'type_language':      'Language',
    'type_css':           'CSS',
    'type_version':       'Version',
    'type_other':         'Other',
    'type_aria':          'ARIA',
    'type_landmarks':     'Landmarks',
    'type_a11y':          'Accessibility',
    'type_ncx':           'NCX',
    'type_opf':           'OPF',

    'fix_auto':           'Auto-fixable by AccesPub',
    'fix_manual':         'Requires human review',
    'fix_conversion':     'Requires EPUB 2 → EPUB 3 conversion',

    # ── Issue descriptions (description_key) ──────────────────────────────
    'issue_desc_lang_mismatch':       'The OPF declares language "{declared}" but the content appears to be in "{detected}".',
    'issue_dc_identifier_empty':      'dc:identifier is empty — a urn:uuid will be generated automatically.',
    'issue_dc_required_empty':        'dc:{field} is empty — required for EPUBCheck validation, must be filled manually.',
    'issue_dc_optional_empty':        'dc:{field} is empty — the optional field will be removed during remediation.',
    'issue_dc_date_invalid_fixable':  'dc:date "{date}" is not in W3CDTF format. Will be auto-corrected.',
    'issue_dc_date_invalid_ambiguous':'dc:date "{date}" is ambiguous (could be DD-MM-YYYY or MM-DD-YYYY). Manual correction needed.',
    'issue_desc_orphan_pagebreaks':   '{n} pagebreak element(s) in content without corresponding entries in the page-list nav.',
    'issue_desc_lang':                'Missing lang attribute on <html> element.',
    'issue_desc_title':               'Missing or empty <title> element in document head.',
    'issue_desc_caption':             'Table missing <caption> element.',
    'issue_desc_missing_th':          'Table has no <th> header elements.',
    'issue_desc_th_scope':            'Table header <th> missing scope attribute.',

    # ── Pattern-based translations ────────────────────────────────────────
    'issue_pat_missing_a11y_meta':   'Missing required accessibility metadata: {prop}',
    'issue_pat_img_no_alt':          'Image missing alt attribute: {src}',
    'issue_pat_cover_no_alt':        'Cover image has no alt text: {href}',
    'issue_pat_epub2_to_3':          'The document is in EPUB {version} format. Accessibility standards (the EAA and EPUB Accessibility 1.1) do not require converting to EPUB 3, but EPUB 3 makes compliance significantly easier thanks to native accessibility metadata, HTML navigation and structural semantics.',
    'issue_pat_inline_styles':       'Document contains inline style attributes. They will be extracted to the stylesheet.',
    'issue_pat_decorative_alt':      'Decorative image: will be marked with alt="" automatically. Image: {src}',
    'issue_pat_empty_alt':           'Image with alt="" — verify whether it is truly decorative: {src}',
    'issue_pat_generic_alt':         'Image with generic placeholder alt ("{alt}") that does not describe the content: {src}',
    'issue_pat_epub_type_role':      'Element with epub:type="{etype}" is missing the matching ARIA role "{role}".',
    'issue_pat_nav_no_label':        '<nav epub:type="{etype}"> has no aria-label — screen readers cannot distinguish the landmark.',
    'issue_pat_ncx_uid':             'NCX-001: NCX identifier ("{ncx}") does not match the OPF unique identifier ("{opf}").',
    'issue_pat_contrast':            'Insufficient color contrast in "{selector}": {fg} on {bg} — ratio {ratio}.',

    'review_images_h3':   'Images requiring human review',
    'review_images_body': '{n} images in this EPUB have alt text that needs to be written or '
                          'reviewed by a person. AnalizePub does not generate alt text; '
                          'AccesPub does, with AI assistance.',
    'review_tables_h3':   'Tables requiring human review',
    'review_tables_body': '{n} tables need a decision: data vs. layout, and whether the first '
                          'row should become a header.',
    'review_lang_h3':     'Language tags requiring review',
    'review_lang_body':   '{n} groups of elements carry a suspicious xml:lang attribute (typical '
                          'of InDesign exports). It must be decided whether to remove them.',

    'cta_h2':             'How can I fix all this?',
    'cta_epub2_title':    'Your EPUB is in EPUB 2 format',
    'cta_epub2_body':     'Accessibility standards (the EAA and EPUB Accessibility 1.1) do not '
                          'require converting to EPUB 3 — EPUB 2 is also supported — but EPUB 3 '
                          'is what most platforms and catalogues expect, and it makes compliance '
                          'significantly easier thanks to its native support for accessibility '
                          'metadata, HTML navigation and structural semantics. AccesPub converts '
                          'EPUB 2 to EPUB 3 and applies every automatic fix in one go.',
    'cta_epub3_title':    'AccesPub can apply {n} automatic fixes to this EPUB',
    'cta_epub3_body':     'AccesPub applies all auto-fixable issues and guides you through the '
                          'decisions only a human can make (alt text, tables, languages).',
    'cta_clean_title':    'Your EPUB is accessible',
    'cta_clean_body':     'Nothing significant to fix. If you want full EAA compliance, AccesPub '
                          'can apply final touches.',
    'cta_button':         'Go to AccesPub',
    'cta_url':            'https://accespub.app',

    'help_h1':            'Help & FAQ',
    'help_q1':            'Does AnalizePub modify my EPUB?',
    'help_a1':            'No. AnalizePub only reads the file and generates a report. The original '
                          'EPUB is never altered, stored or sent anywhere.',
    'help_q2':            'How long does the analysis take?',
    'help_a2':            'Between 5 and 20 seconds for a typical EPUB. Larger files (close to '
                          'the 50 MB limit) may take longer.',
    'help_q3':            'What happens to my file afterwards?',
    'help_a3':            'The EPUB is discarded the moment the analysis ends. Only the report '
                          '(without book content) is kept in a 2-hour temporary session, then '
                          'deleted.',
    'help_q4':            'Why are some issues not auto-fixable?',
    'help_a4':            'Tasks like writing alt text or deciding whether a table is data or '
                          'layout need human judgement. AccesPub guides you through those; '
                          'AnalizePub only reports how many there are.',
    'help_q5':            'Does AnalizePub work with EPUB 2?',
    'help_a5':            'Yes. It detects every issue and clearly flags those that need '
                          'EPUB 3 conversion to be solved.',
    'help_q6':            'How is this different from AccesPub?',
    'help_a6':            'AnalizePub only analyses and reports (free). AccesPub auto-fixes, '
                          'converts EPUB 2 → 3 and exports the remediated EPUB (paid).',

    'legal_h1':           'Legal notice & privacy policy',
    'legal_owner_h2':     'Owner',
    'legal_owner_body':   'AnalizePub is a service operated by Alberto Barajas, '
                          'doing business as «ab serveis». '
                          'Tax ID (NIF): 46629726D. Address: Joan Miró, 19. 08319 Dosrius. '
                          'Contact: info@abserveis.net.',
    'legal_purpose_h2':   'Service purpose',
    'legal_purpose_body': 'AnalizePub analyses EPUB files and generates accessibility reports. '
                          'It does not fix, convert or export anything.',
    'legal_data_h2':      'Personal data and privacy',
    'legal_data_body':    'We do not collect personal data. Analysis sessions are identified by '
                          'a technical, anonymous cookie (UUID) that expires after 2 hours. We '
                          'do not use third-party tracking, analytics or advertising cookies.',
    'legal_files_h2':     'How we handle your files',
    'legal_files_body':   'The EPUB is processed in memory and discarded immediately. Only the '
                          'report (no book content) is stored in a temporary file that is '
                          'deleted after 2 hours.',
    'legal_liability_h2': 'Liability',
    'legal_liability_body':'AnalizePub is provided "as is", without warranty. The report is '
                          'informational: final EAA / WCAG compliance depends on multiple '
                          'factors and on human review. ab serveis is not liable for any use of '
                          'the report.',

    'err_no_file':        'No file was uploaded.',
    'err_invalid_epub':   'The uploaded file is not a valid EPUB.',
    'err_too_large':      'The file exceeds the 50 MB limit.',
    'err_fixed_layout':   'Fixed Layout EPUBs cannot be processed.',
    'err_analysis_failed':'Analysis failed: {detail}',
    'err_session_missing':'No report associated with your session. Please upload an EPUB again.',
    'err_404':            'Page not found.',
    'err_500':            'Internal server error.',
},

# ── Catalan ─────────────────────────────────────────────────────────────────
'ca': {
    'brand_name':         'AnalizePub',
    'brand_tagline':      'Auditoria gratuïta d\'accessibilitat EPUB',
    'brand_by':           'per ab serveis',

    'nav_home':           'Inici',
    'nav_help':           'Ajuda',
    'nav_legal':          'Avís legal',

    'footer_text':        'AnalizePub — Anàlisi gratuït d\'accessibilitat EPUB',
    'footer_legal':       'Avís legal',
    'footer_privacy':     'Privacitat',
    'footer_accespub':    'Coneix AccesPub',

    'lang_label':         'Idioma:',
    'lang_es':            'Español',
    'lang_en':            'English',
    'lang_ca':            'Català',
    'lang_short_es':      'ES',
    'lang_short_en':      'EN',
    'lang_short_ca':      'CA',
    'confirm_lang_report':'Canviar d\'idioma eliminarà l\'informe actual i tornaràs a l\'inici. Continuar?',
    'confirm_lang_file':  'Canviar d\'idioma desseleccionarà el fitxer. Continuar?',
    'skip_to_main':       'Vés al contingut principal',
    'aria_main_nav':      'Navegació principal',
    'aria_brand':         'AnalizePub — Inici',

    'upload_h1':           'Analitza l\'accessibilitat del teu EPUB',
    'upload_subtitle':     'Puja un EPUB i obtén un informe detallat amb tots els problemes '
                           'd\'accessibilitat detectats. AnalizePub no modifica el fitxer — '
                           'només analitza i informa, gratis i sense registre.',

    'upload_click':       'Fes clic per seleccionar un EPUB',
    'upload_drag_hint':   'o arrossega i deixa el fitxer aquí',
    'upload_choose':      'Tria EPUB',
    'upload_analyze':     'Analitza →',
    'upload_hint':        'Suporta EPUB 2.0.1 i EPUB 3.x (només reflowable, màx. 50 MB)',
    'upload_fixed_note':  'Els EPUB Fixed Layout no s\'analitzen: estructuralment no poden ser accessibles.',
    'upload_privacy_note':'El teu fitxer es processa en memòria i es descarta després de '
                          'l\'anàlisi. Mai guardem còpies del contingut.',
    'upload_invalid_type':'Només s\'admeten fitxers .epub.',
    'upload_too_large':   'El fitxer supera el límit de 50 MB.',
    'loading_text':       'Analitzant el teu EPUB…',
    'loading_hint':       'Pot trigar uns segons en EPUBs grans.',

    'what_h2':            'Què analitza AnalizePub?',
    'what_intro':         'AnalizePub utilitza el mateix motor d\'anàlisi que AccesPub. Comprova '
                          'tot el necessari perquè un EPUB compleixi amb l\'EAA (Directiva '
                          'Europea d\'Accessibilitat) i amb WCAG 2.1 AA:',
    'what_li_metadata':   'Metadades d\'accessibilitat obligatòries (schema:accessMode, etc.).',
    'what_li_lang':       'Idioma de la publicació i de cada document.',
    'what_li_semantics':  'Estructura semàntica (epub:type, rols DPUB-ARIA, seccions, navegació).',
    'what_li_images':     'Text alternatiu de les imatges i detecció d\'imatges decoratives.',
    'what_li_tables':     'Taules de dades: capçaleres, scope i captions.',
    'what_li_contrast':   'Contrast de color en CSS i estils en línia.',
    'what_li_nav':        'Document de navegació, page-list i ordre del TOC.',
    'what_li_epubcheck':  'Validació amb EPUBCheck oficial.',

    'report_h1':          'Informe d\'accessibilitat',
    'report_filename':    'Fitxer analitzat',
    'report_analyzed_at': 'Anàlisi feta el',
    'report_back':        '← Analitza un altre EPUB',
    'report_download_html':'Baixa l\'informe (HTML)',
    'report_print':       'Imprimeix / Desa com a PDF',
    'report_session_expired': 'La sessió ha caducat. Torna a pujar l\'EPUB per analitzar-lo.',

    'indic_title':        'Estat d\'accessibilitat',
    'indic_eaa':          'Conformitat EAA',
    'indic_wcag':         'Accessibilitat WCAG 2.1 AA',
    'indic_epubcheck':    'Validació EPUBCheck',
    'indic_status_ok':    'Conforme',
    'indic_status_warn':  'Millorable',
    'indic_status_error': 'No conforme',
    'indic_eaa_ok':       'Sense problemes crítics per a l\'EAA.',
    'indic_eaa_warn':     'Falta alguna metadada o atribut. Solucionable sense conversió.',
    'indic_eaa_error':    'Hi ha incompliments crítics per a l\'EAA.',
    'indic_wcag_ok':      'Sense problemes significatius d\'accessibilitat.',
    'indic_wcag_warn':    'Hi ha problemes d\'accessibilitat de severitat moderada.',
    'indic_wcag_error':   'Hi ha problemes seriosos d\'accessibilitat (WCAG).',
    'indic_epubcheck_ok': 'EPUBCheck no reporta errors ni avisos.',
    'indic_epubcheck_warn':'EPUBCheck reporta {n} avisos.',
    'indic_epubcheck_error':'EPUBCheck reporta {errors} errors i {warnings} avisos.',

    'sec_a_h2':           'Estat actual de l\'EPUB',
    'sec_a_intro':        'Aquest és l\'estat del fitxer tal com està, sense tocar res.',
    'meta_version':       'Versió EPUB',
    'meta_language':      'Idioma',
    'meta_title':         'Títol',
    'meta_total_docs':    'Documents',
    'meta_total_images':  'Imatges',
    'meta_unknown':       'Desconegut',
    'epubcheck_h3':       'Resultat d\'EPUBCheck',
    'epubcheck_ok':       'EPUBCheck no ha detectat errors ni avisos.',
    'epubcheck_summary':  '{errors} errors · {warnings} avisos · {fatals} fatals',
    'epubcheck_show':     'Veure detalls',
    'epubcheck_hide':     'Ocultar detalls',
    'epubcheck_unavailable':'EPUBCheck no està disponible en aquest entorn.',
    'epubcheck_not_run':  'No s\'ha executat EPUBCheck.',
    'epubcheck_col_severity':'Severitat',
    'epubcheck_col_id':   'Codi',
    'epubcheck_col_location':'Ubicació',
    'epubcheck_col_message':'Missatge',
    'sev_fatal':          'Fatal',
    'sev_error':          'Error',
    'sev_warning':        'Avís',
    'sev_info':           'Info',
    'sev_usage':          'Ús',

    'sec_b_h2':           'Què caldria corregir per complir amb l\'EAA',
    'sec_b_intro':        'Llista completa de problemes detectats pel motor d\'anàlisi. S\'indica '
                          'si cada problema és corregible automàticament o si requereix revisió '
                          'humana.',
    'sec_b_no_issues':    'Enhorabona! El motor d\'anàlisi no ha detectat cap problema d\'accessibilitat.',
    'sec_b_summary':      '{total} problemes · {auto} corregibles automàticament · {manual} requereixen revisió',
    'sec_b_filter_all':   'Tots',
    'sec_b_filter_critical':'Crítics',
    'sec_b_filter_serious':'Greus',
    'sec_b_filter_moderate':'Moderats',
    'sec_b_filter_minor': 'Lleus',

    'issue_col_severity': 'Severitat',
    'issue_col_type':     'Tipus',
    'issue_col_location': 'Ubicació',
    'issue_col_description':'Descripció',
    'issue_col_fix':      'Correcció',

    'severity_critical':  'Crític',
    'severity_serious':   'Greu',
    'severity_moderate':  'Moderat',
    'severity_minor':     'Lleu',

    'type_metadata':      'Metadades',
    'type_html':          'HTML',
    'type_image':         'Imatge',
    'type_table':         'Taula',
    'type_nav':           'Navegació',
    'type_language':      'Idioma',
    'type_css':           'CSS',
    'type_version':       'Versió',
    'type_other':         'Altres',
    'type_aria':          'ARIA',
    'type_landmarks':     'Landmarks',
    'type_a11y':          'Accessibilitat',
    'type_ncx':           'NCX',
    'type_opf':           'OPF',

    'fix_auto':           'Corregible automàticament per AccesPub',
    'fix_manual':         'Requereix revisió humana',
    'fix_conversion':     'Requereix conversió EPUB 2 → EPUB 3',

    # ── Issue descriptions (description_key) ──────────────────────────────
    'issue_desc_lang_mismatch':       'L\'OPF declara idioma "{declared}" però el contingut sembla estar en "{detected}".',
    'issue_dc_identifier_empty':      'dc:identifier està buit — es generarà un urn:uuid automàticament.',
    'issue_dc_required_empty':        'dc:{field} està buit — necessari per validar EPUBCheck, cal omplir-lo manualment.',
    'issue_dc_optional_empty':        'dc:{field} està buit — el camp opcional s\'eliminarà durant la correcció.',
    'issue_dc_date_invalid_fixable':  'dc:date "{date}" no té format W3CDTF. Es corregirà automàticament.',
    'issue_dc_date_invalid_ambiguous':'dc:date "{date}" és ambigu (podria ser DD-MM-YYYY o MM-DD-YYYY). Cal correcció manual.',
    'issue_desc_orphan_pagebreaks':   '{n} elements pagebreak en el contingut sense entrada corresponent a la page-list.',
    'issue_desc_lang':                'Falta l\'atribut lang a l\'element <html>.',
    'issue_desc_title':               'Element <title> absent o buit a la capçalera del document.',
    'issue_desc_caption':             'Taula sense element <caption>.',
    'issue_desc_missing_th':          'Taula sense elements de capçalera <th>.',
    'issue_desc_th_scope':            'Element <th> sense atribut scope.',

    # ── Pattern-based translations ────────────────────────────────────────
    'issue_pat_missing_a11y_meta':   'Falta la metadada d\'accessibilitat obligatòria: {prop}',
    'issue_pat_img_no_alt':          'Imatge sense atribut alt: {src}',
    'issue_pat_cover_no_alt':        'La imatge de portada no té text alternatiu: {href}',
    'issue_pat_epub2_to_3':          'El document està en format EPUB {version}. La normativa (EAA i EPUB Accessibility 1.1) no exigeix convertir a EPUB 3, però EPUB 3 facilita molt el compliment pel seu suport natiu de metadades d\'accessibilitat, navegació HTML i semàntica estructural.',
    'issue_pat_inline_styles':       'El document conté atributs style en línia. S\'extrauran al full d\'estils.',
    'issue_pat_decorative_alt':      'Imatge decorativa: es marcarà amb alt="" automàticament. Imatge: {src}',
    'issue_pat_empty_alt':           'Imatge amb alt="" — verifica si és realment decorativa: {src}',
    'issue_pat_generic_alt':         'Imatge amb alt genèric ("{alt}") que no descriu el contingut: {src}',
    'issue_pat_epub_type_role':      'Element amb epub:type="{etype}" sense el role ARIA corresponent "{role}".',
    'issue_pat_nav_no_label':        '<nav epub:type="{etype}"> sense aria-label — els lectors de pantalla no poden distingir el landmark.',
    'issue_pat_ncx_uid':             'NCX-001: l\'identificador NCX ("{ncx}") no coincideix amb l\'identificador únic de l\'OPF ("{opf}").',
    'issue_pat_contrast':            'Contrast de color insuficient a "{selector}": {fg} sobre {bg} — ràtio {ratio}.',

    'review_images_h3':   'Imatges que requereixen revisió humana',
    'review_images_body': '{n} imatges del EPUB tenen text alternatiu que cal redactar o '
                          'revisar per una persona. AnalizePub no genera alt text; AccesPub '
                          'sí, amb assistència d\'IA.',
    'review_tables_h3':   'Taules que requereixen revisió humana',
    'review_tables_body': '{n} taules requereixen decidir si són de dades o de maquetació, i si '
                          'la primera fila ha de convertir-se en capçalera.',
    'review_lang_h3':     'Etiquetes d\'idioma a revisar',
    'review_lang_body':   '{n} grups d\'elements porten un xml:lang sospitós (típic d\'exportacions '
                          'd\'InDesign). Cal decidir si eliminar-los.',

    'cta_h2':             'Com corregir tot això?',
    'cta_epub2_title':    'El teu EPUB està en format EPUB 2',
    'cta_epub2_body':     'La normativa (EAA i EPUB Accessibility 1.1) no exigeix convertir a '
                          'EPUB 3 — admet també EPUB 2 — però EPUB 3 és el que esperen la '
                          'majoria de plataformes i catàlegs, i facilita molt el compliment pel '
                          'seu suport natiu de metadades d\'accessibilitat, navegació HTML i '
                          'semàntica estructural. AccesPub converteix EPUB 2 a EPUB 3 i aplica '
                          'totes les correccions automàtiques de cop.',
    'cta_epub3_title':    'AccesPub pot aplicar {n} correccions automàtiques a aquest EPUB',
    'cta_epub3_body':     'AccesPub aplica les correccions automàtiques i et guia per les '
                          'decisions que només una persona pot prendre (alt text, taules, idiomes).',
    'cta_clean_title':    'El teu EPUB és accessible',
    'cta_clean_body':     'No cal corregir res important. Si vols assegurar el compliment total '
                          'de l\'EAA, AccesPub pot aplicar petits retocs.',
    'cta_button':         'Vés a AccesPub',
    'cta_url':            'https://accespub.app',

    'help_h1':            'Ajuda i preguntes freqüents',
    'help_q1':            'AnalizePub modifica el meu EPUB?',
    'help_a1':            'No. AnalizePub només llegeix el fitxer i genera un informe. L\'EPUB '
                          'original no s\'altera, no es guarda ni es reenvia.',
    'help_q2':            'Quant triga l\'anàlisi?',
    'help_a2':            'Entre 5 i 20 segons per a un EPUB típic. Per a EPUBs grans (a prop '
                          'del límit de 50 MB) pot trigar més.',
    'help_q3':            'Què passa amb el fitxer després?',
    'help_a3':            'L\'EPUB es descarta immediatament en acabar l\'anàlisi. Només es '
                          'guarda l\'informe (sense contingut del llibre) en una sessió temporal '
                          'de 2 hores, després s\'esborra.',
    'help_q4':            'Per què alguns problemes no es corregeixen automàticament?',
    'help_a4':            'Tasques com redactar el text alternatiu d\'una imatge o decidir si una '
                          'taula és de dades o maquetació requereixen judici humà. AccesPub et '
                          'guia per aquestes decisions; AnalizePub només informa de quantes hi ha.',
    'help_q5':            'AnalizePub funciona amb EPUB 2?',
    'help_a5':            'Sí. Detecta tots els problemes i, a més, t\'indica quins requereixen '
                          'conversió a EPUB 3 per poder solucionar-se.',
    'help_q6':            'Quina és la diferència amb AccesPub?',
    'help_a6':            'AnalizePub només analitza i informa (gratis). AccesPub corregeix '
                          'automàticament, converteix EPUB 2 a EPUB 3 i exporta l\'EPUB '
                          'remediat (de pagament).',

    'legal_h1':           'Avís legal i política de privacitat',
    'legal_owner_h2':     'Titular',
    'legal_owner_body':   'AnalizePub és un servei prestat per Alberto Barajas, '
                          'sota el nom comercial «ab serveis». '
                          'NIF: 46629726D. Domicili: Joan Miró, 19. 08319 Dosrius. '
                          'Contacte: info@abserveis.net.',
    'legal_purpose_h2':   'Finalitat del servei',
    'legal_purpose_body': 'AnalizePub analitza fitxers EPUB i genera informes d\'accessibilitat. '
                          'No corregeix el fitxer, no converteix versions ni exporta res.',
    'legal_data_h2':      'Dades personals i privacitat',
    'legal_data_body':    'No recollim dades personals. Les sessions d\'anàlisi s\'identifiquen '
                          'amb una galeta tècnica anònima (UUID) que caduca al cap de 2 hores. '
                          'No fem servir galetes de seguiment, analítica de tercers ni publicitat.',
    'legal_files_h2':     'Tractament dels teus fitxers',
    'legal_files_body':   'L\'EPUB es processa en memòria i es descarta immediatament. Només es '
                          'guarda l\'informe (sense contingut del llibre) en un fitxer temporal '
                          'que s\'esborra al cap de 2 hores.',
    'legal_liability_h2': 'Limitació de responsabilitat',
    'legal_liability_body':'AnalizePub s\'ofereix "tal qual", sense garanties. L\'informe és '
                          'orientatiu: la conformitat final amb l\'EAA i WCAG depèn de molts '
                          'factors i de la revisió humana. ab serveis no es fa responsable de '
                          'l\'ús que es faci de l\'informe.',

    'err_no_file':        'No s\'ha enviat cap fitxer.',
    'err_invalid_epub':   'El fitxer no és un EPUB vàlid.',
    'err_too_large':      'El fitxer supera la mida màxima permesa (50 MB).',
    'err_fixed_layout':   'Els EPUB Fixed Layout no es poden processar.',
    'err_analysis_failed':'L\'anàlisi ha fallat: {detail}',
    'err_session_missing':'No hi ha cap informe associat a la teva sessió. Puja un EPUB de nou.',
    'err_404':            'Pàgina no trobada.',
    'err_500':            'Error intern del servidor.',
},

}
