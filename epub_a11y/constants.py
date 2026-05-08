"""
Constants: XML namespaces, epub:type to ARIA role mapping,
and required accessibility metadata fields.
"""

# XML Namespaces
NS = {
    'container': 'urn:oasis:names:tc:opendocument:xmlns:container',
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'xhtml': 'http://www.w3.org/1999/xhtml',
    'epub': 'http://www.idpf.org/2007/ops',
    'ncx': 'http://www.daisy.org/z3986/2005/ncx/',
    'schema': 'http://schema.org/',
    'dcterms': 'http://purl.org/dc/terms/',
    'a11y': 'http://www.idpf.org/epub/vocab/package/a11y/#',
}

# epub:type → DPUB-ARIA role mapping
# Source: EPUB 3 Structural Semantics Vocabulary 1.1 + DPUB-ARIA 1.1
# Types with NO ARIA equivalent (epub:type only, no role attribute):
#   titlepage, halftitlepage, copyright-page, seriespage, preamble, toc-brief,
#   landmarks, loa, loi, lot, lov, subchapter, division,
#   frontmatter, bodymatter, backmatter
EPUB_TYPE_TO_ARIA = {
    # ── Document-level ───────────────────────────────────────────────────
    'abstract':        'doc-abstract',
    'acknowledgments': 'doc-acknowledgments',
    'afterword':       'doc-afterword',
    'appendix':        'doc-appendix',
    'bibliography':    'doc-bibliography',
    'chapter':         'doc-chapter',
    'colophon':        'doc-colophon',
    'conclusion':      'doc-conclusion',
    # 'cover' has no DPUB-ARIA equivalent — epub:type="cover" only, no role

    'credits':         'doc-credits',
    'dedication':      'doc-dedication',
    'endnotes':        'doc-endnotes',
    'epigraph':        'doc-epigraph',
    'epilogue':        'doc-epilogue',
    'errata':          'doc-errata',
    'foreword':        'doc-foreword',
    'glossary':        'doc-glossary',
    'index':           'doc-index',
    'introduction':    'doc-introduction',
    'page-list':       'doc-pagelist',
    'part':            'doc-part',
    'preface':         'doc-preface',
    'prologue':        'doc-prologue',
    'pullquote':       'doc-pullquote',
    'qna':             'doc-qna',
    'toc':             'doc-toc',
    # ── Inline / component ───────────────────────────────────────────────
    'backlink':        'doc-backlink',
    'biblioentry':     'doc-biblioentry',
    'biblioref':       'doc-biblioref',
    'credit':          'doc-credit',
    'endnote':         'doc-endnote',
    'footnote':        'doc-footnote',
    'glossref':        'doc-glossref',
    'noteref':         'doc-noteref',
    'notice':          'doc-notice',
    'pagebreak':       'doc-pagebreak',
    'subtitle':        'doc-subtitle',
    'tip':             'doc-tip',
}

# Heuristic patterns suggesting an image is decorative
DECORATIVE_IMAGE_PATTERNS = [
    r'spacer', r'separator', r'divider', r'bullet', r'dot',
    r'line', r'border', r'corner', r'arrow', r'icon-',
    r'bg[-_]', r'background', r'pixel', r'blank', r'empty',
    r'deco', r'ornament',
]

# Generic / placeholder alt text values that provide no real information
# for screen reader users.  Matching is case-insensitive after stripping.
GENERIC_ALT_TEXTS = {
    # English
    'illustration', 'illustrations',
    'image', 'images', 'img',
    'photo', 'photograph', 'photos',
    'picture', 'pictures',
    'figure', 'fig',
    'graphic', 'graphics',
    'drawing', 'artwork',
    'diagram',
    'icon',
    'logo',
    'banner',
    'cover',
    'thumbnail',
    'placeholder',
    'untitled',
    'unknown',
    # Spanish / Catalan
    'ilustración', 'ilustracion', 'ilustraciones',
    'imagen', 'imágenes', 'imagenes',
    'foto', 'fotografía', 'fotografia', 'fotos',
    'figura', 'figuras',
    'gráfico', 'grafico', 'gráficos', 'graficos',
    'dibujo',
    'dibuix',
    'icono', 'icona',
    'portada',
    'miniatura',
    # French
    'illustration',   # same
    'image',          # same
    'photo',          # same
    'figure',         # same
    'icône', 'icone',
    'couverture',
    # German
    'abbildung', 'bild', 'foto', 'grafik',
    'zeichnung', 'symbol',
    # Italian
    'immagine', 'illustrazione', 'foto', 'figura',
}

# Required accessibility metadata for EPUB 3
REQUIRED_A11Y_METADATA = {
    'schema:accessMode': ['textual'],
    'schema:accessModeSufficient': ['textual'],
    'schema:accessibilityFeature': ['structuralNavigation', 'tableOfContents'],
    'schema:accessibilityHazard': ['noFlashingHazard', 'noMotionSimulationHazard', 'noSoundHazard'],
    'dcterms:conformsTo': 'EPUB Accessibility 1.1 - WCAG 2.1 Level AA',
}
