"""
Fixes for OPF accessibility metadata.
Adds all required schema.org and dcterms accessibility properties.
"""

import re
import datetime
from lxml import etree
from typing import List, Optional, Tuple
from ..constants import NS, REQUIRED_A11Y_METADATA
from ..models import Issue


def normalize_dc_date(date_str: str) -> Tuple[Optional[str], bool]:
    """
    Try to normalize an invalid dc:date value to W3CDTF / ISO 8601 subset.

    Valid EPUB3 dc:date formats: YYYY, YYYY-MM, YYYY-MM-DD (and datetime variants).

    Returns:
        (normalized_str, True)   — value is valid or was fixed unambiguously
        (None, False)            — ambiguous or unresolvable; needs user input
    """
    s = date_str.strip()

    # ── Already valid W3CDTF? ───────────────────────────────────────────────
    if re.match(r'^\d{4}$', s):
        return (s, True)                          # YYYY
    if re.match(r'^\d{4}-\d{2}$', s):
        return (s, True)                          # YYYY-MM
    if re.match(r'^\d{4}-\d{2}-\d{2}(T.*)?$', s):
        try:
            datetime.date.fromisoformat(s[:10])
            return (s, True)                      # YYYY-MM-DD or YYYY-MM-DDT…
        except ValueError:
            pass  # invalid calendar values (e.g. 2023-13-01) → fall through

    # ── YYYY/MM/DD or YYYY.MM.DD — year-first, unambiguous ─────────────────
    m = re.match(r'^(\d{4})[/.](\d{1,2})[/.](\d{1,2})$', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            datetime.date(y, mo, d)
            return (f'{y:04d}-{mo:02d}-{d:02d}', True)
        except ValueError:
            pass

    # ── YYYY-M-D (valid values, missing zero-padding) ───────────────────────
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            datetime.date(y, mo, d)
            return (f'{y:04d}-{mo:02d}-{d:02d}', True)
        except ValueError:
            pass

    # ── X-X-YYYY (European DD-MM or American MM-DD, year last) ─────────────
    m = re.match(r'^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$', s)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12:
            # First segment > 12 → must be day: DD-MM-YYYY
            try:
                datetime.date(year, b, a)
                return (f'{year:04d}-{b:02d}-{a:02d}', True)
            except ValueError:
                pass
        elif b > 12:
            # Second segment > 12 → must be day: MM-DD-YYYY
            try:
                datetime.date(year, a, b)
                return (f'{year:04d}-{a:02d}-{b:02d}', True)
            except ValueError:
                pass
        else:
            # Both ≤ 12 — format is ambiguous (e.g. 01-07-2023)
            return (None, False)

    # ── Unresolvable ────────────────────────────────────────────────────────
    return (None, False)


OPF_NS = 'http://www.idpf.org/2007/opf'

# Accessibility summary text by primary language tag.
# Exported as a module-level constant so remediator.py can use the same
# table when applying a language override after initial processing.
A11Y_SUMMARY = {
    'es': ('Esta publicación ha sido optimizada para la accesibilidad. '
           'Incluye texto alternativo en las imágenes, estructura de documento '
           'adecuada y marcado semántico para tecnologías de apoyo.'),
    'ca': ('Aquesta publicació ha estat optimitzada per a l\'accessibilitat. '
           'Inclou text alternatiu a les imatges, estructura de document adequada '
           'i marcat semàntic per a tecnologies d\'assistència.'),
    'en': ('This publication has been optimized for accessibility. '
           'It includes alternative text for images, proper document structure, '
           'and semantic markup for assistive technologies.'),
    'fr': ('Cette publication a été optimisée pour l\'accessibilité. '
           'Elle comprend du texte alternatif pour les images, une structure '
           'de document appropriée et un balisage sémantique pour les technologies '
           'd\'assistance.'),
    'de': ('Diese Publikation wurde für Barrierefreiheit optimiert. '
           'Sie enthält Alternativtext für Bilder, eine geeignete Dokumentstruktur '
           'und semantische Auszeichnung für Hilfstechnologien.'),
    'pt': ('Esta publicação foi otimizada para acessibilidade. '
           'Inclui texto alternativo para imagens, estrutura de documento adequada '
           'e marcação semântica para tecnologias assistivas.'),
    'it': ('Questa pubblicazione è stata ottimizzata per l\'accessibilità. '
           'Include testo alternativo per le immagini, una struttura del documento '
           'appropriata e marcatura semantica per le tecnologie assistive.'),
    'gl': ('Esta publicación foi optimizada para a accesibilidade. '
           'Inclúe texto alternativo nas imaxes, estrutura de documento axeitada '
           'e marcado semántico para tecnoloxías de apoio.'),
    'eu': ('Argitalpen hau irisgarritasunerako optimizatu da. '
           'Irudien testu alternatiboa, dokumentu-egitura egokia eta markatze '
           'semantikoa ditu laguntza-teknologietarako.'),
}


def apply_metadata_fixes(opf_root: etree._Element, issues: List[Issue],
                          has_images: bool = True, language: str = 'es',
                          has_page_list: bool = False) -> List[str]:
    """
    Apply accessibility metadata fixes to the OPF root element.
    Returns a list of fix descriptions applied.
    """
    fixes_applied = []
    metadata_el = opf_root.find(f'{{{OPF_NS}}}metadata')
    if metadata_el is None:
        return fixes_applied

    # Indentation used by surrounding existing elements (detect or use 8 spaces)
    INDENT = '\n        '

    def _meta(property_name: str, value: str, extra_attrs: dict = None) -> etree._Element:
        """Create a <meta property="…">value</meta> element in the OPF namespace,
        with a trailing newline so each element appears on its own line."""
        el = etree.SubElement(metadata_el, f'{{{OPF_NS}}}meta')
        el.set('property', property_name)
        if extra_attrs:
            for k, v in extra_attrs.items():
                el.set(k, v)
        el.text = value
        el.tail = INDENT   # newline + indentation after each element
        return el

    # Schema.org / dcterms accessibility properties that this function manages.
    # Any meta element carrying one of these in a legacy EPUB2 name="…"
    # content="…" attribute is invalid in EPUB3 and must be removed so it
    # can be re-written in the correct EPUB3 property="…" style below.
    _MANAGED_PROPS = {
        'schema:accessMode',
        'schema:accessModeSufficient',
        'schema:accessibilityFeature',
        'schema:accessibilityHazard',
        'schema:accessibilitySummary',
        'dcterms:conformsTo',
        'dcterms:modified',
    }
    for _m in list(metadata_el.findall(f'{{{OPF_NS}}}meta')):
        if _m.get('name', '') in _MANAGED_PROPS:
            metadata_el.remove(_m)

    # Determine existing metadata — EPUB3 property="…" style only (EPUB2
    # name="…" entries have already been stripped above).
    existing_props = {}
    for meta in metadata_el.findall(f'{{{OPF_NS}}}meta'):
        prop = meta.get('property', '')
        if prop:
            existing_props[prop] = meta

    # schema:accessMode
    if 'schema:accessMode' not in existing_props:
        modes = ['textual']
        if has_images:
            modes.append('visual')
        for mode in modes:
            _meta('schema:accessMode', mode)
        fixes_applied.append({'key': 'xfix_schema_access_mode',
                               'args': {'value': ', '.join(modes)}})

    # schema:accessModeSufficient
    if 'schema:accessModeSufficient' not in existing_props:
        _meta('schema:accessModeSufficient', 'textual')
        fixes_applied.append({'key': 'xfix_schema_access_mode_suff', 'args': {}})

    # schema:accessibilityFeature
    if 'schema:accessibilityFeature' not in existing_props:
        features = ['structuralNavigation', 'tableOfContents', 'readingOrder']
        if has_images:
            # Will be updated to 'alternativeText' after image review
            features.append('displayTransformability')
        if has_page_list:
            features.append('pageNavigation')
        for feature in features:
            _meta('schema:accessibilityFeature', feature)
        fixes_applied.append({'key': 'xfix_schema_a11y_feature',
                               'args': {'value': ', '.join(features)}})
    elif has_page_list:
        # accessibilityFeature already existed — add pageNavigation if missing
        existing_features = {
            m.text.strip()
            for m in metadata_el.findall(f'{{{OPF_NS}}}meta')
            if m.get('property') == 'schema:accessibilityFeature' and m.text
        }
        if 'pageNavigation' not in existing_features:
            _meta('schema:accessibilityFeature', 'pageNavigation')
            fixes_applied.append({'key': 'xfix_page_navigation_feature', 'args': {}})

    # schema:accessibilityHazard
    # Valid values per EPUB Accessibility spec / schema.org vocabulary.
    # The legacy value 'none' was retired; the correct way to express "no
    # hazards" is three separate "noXxxHazard" declarations.
    _VALID_HAZARD_VALS = {
        'flashing', 'noFlashingHazard',
        'motionSimulation', 'noMotionSimulationHazard',
        'sound', 'noSoundHazard',
        'unknown',
    }
    # Collect every existing hazard element — both EPUB3 (property="…") and
    # EPUB2 (name="…" content="…") styles.
    existing_hazard_els = []
    for _m in metadata_el.findall(f'{{{OPF_NS}}}meta'):
        _prop = _m.get('property', '') or _m.get('name', '')
        if _prop == 'schema:accessibilityHazard':
            _val = (_m.text or _m.get('content', '') or '').strip()
            existing_hazard_els.append((_m, _val))

    # Remove elements whose value is invalid (e.g. the retired 'none').
    for _el, _val in existing_hazard_els:
        if _val not in _VALID_HAZARD_VALS:
            metadata_el.remove(_el)

    # Determine which valid values are already present after the cleanup.
    valid_hazard_vals = {_val for _, _val in existing_hazard_els
                         if _val in _VALID_HAZARD_VALS}

    # Add the standard "no hazards" declarations if none remain.
    if not valid_hazard_vals:
        hazards = ['noFlashingHazard', 'noMotionSimulationHazard', 'noSoundHazard']
        for hazard in hazards:
            _meta('schema:accessibilityHazard', hazard)
        fixes_applied.append({'key': 'xfix_schema_a11y_hazard',
                               'args': {'value': ', '.join(hazards)}})

    # schema:accessibilitySummary — auto-generated in the document's language.
    # The validate page always exposes the field so the user can customise it.
    if 'schema:accessibilitySummary' not in existing_props:
        # Use the first (primary) BCP-47 tag — language may already be a single
        # valid tag after analyzer.py normalisation, but guard against any
        # leftover comma-joined value just in case.
        primary_lang = language.split(',')[0].strip() if language else 'en'
        primary = primary_lang.split('-')[0].lower()  # subtag for summary lookup
        summary_text = A11Y_SUMMARY.get(primary, A11Y_SUMMARY['en'])
        xml_lang = '{http://www.w3.org/XML/1998/namespace}lang'
        _meta('schema:accessibilitySummary', summary_text,
              extra_attrs={xml_lang: primary_lang})
        fixes_applied.append({'key': 'xfix_schema_a11y_summary', 'args': {}})

    # dcterms:conformsTo
    if 'dcterms:conformsTo' not in existing_props:
        _meta('dcterms:conformsTo', 'EPUB Accessibility 1.1 - WCAG 2.1 Level AA')
        fixes_applied.append({'key': 'xfix_conforms_to',
                               'args': {'value': 'EPUB Accessibility 1.1 - WCAG 2.1 Level AA'}})

    # dcterms:modified — required exactly once in EPUB3 (OPF §3.4.7)
    # Format: YYYY-MM-DDTHH:MM:SSZ (UTC, no microseconds)
    if 'dcterms:modified' not in existing_props:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        _meta('dcterms:modified', ts)
        fixes_applied.append({'key': 'xfix_modified', 'args': {'value': ts}})

    # AccesPub generator tag — identifies the tool that processed the EPUB,
    # following the same convention as Sigil, Calibre and Adobe InDesign.
    # We overwrite any pre-existing generator meta to avoid duplicates.
    for m in list(metadata_el):
        if m.get('name') == 'generator' and 'AccesPub' in (m.get('content') or ''):
            metadata_el.remove(m)
    gen = etree.SubElement(metadata_el, f'{{{OPF_NS}}}meta')
    gen.set('name', 'generator')
    gen.set('content', 'AccesPub 1.0')
    gen.tail = '\n        '

    # Mark issues as fixed
    for issue in issues:
        if issue.type == 'metadata' and issue.auto_fixable:
            issue.fix_applied = True
            issue.fix_description = 'fix_desc_metadata'

    return fixes_applied
